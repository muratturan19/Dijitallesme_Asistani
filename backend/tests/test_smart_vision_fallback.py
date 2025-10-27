# -*- coding: utf-8 -*-
"""Tests for the SmartVisionFallback helper and OCR quality analysis."""
from __future__ import annotations

from typing import Any, Dict, Optional

import pytest

from backend.app.core.smart_vision_fallback import (
    OCRQualityAnalyzer,
    SmartVisionFallback,
    merge_ocr_and_vision_results,
)


class DummyResponses:
    """Lightweight stub that mimics the OpenAI responses client."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload
        self.last_kwargs: Optional[Dict[str, Any]] = None

    def create(self, **kwargs: Any) -> Dict[str, Any]:
        self.last_kwargs = kwargs
        return self.payload


class DummyClient:
    """OpenAI client stub with only the responses endpoint."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.responses = DummyResponses(payload)


@pytest.fixture
def low_quality_ocr_result() -> Dict[str, Any]:
    """Return a synthetic OCR output that should trigger fallback."""

    return {
        'text': '123',
        'average_confidence': 0.2,
        'word_count': 2,
    }


def test_low_confidence_triggers_vision_call(low_quality_ocr_result: Dict[str, Any]) -> None:
    """Vision fallback should run and return parsed field mappings."""

    payload = {
        'field_mappings': {
            'invoice_no': {
                'value': 'V123',
                'confidence': 0.92,
                'source': 'vision',
            }
        }
    }
    client = DummyClient(payload)

    analyzer = OCRQualityAnalyzer(min_average_confidence=0.8, min_word_count=5)
    fallback = SmartVisionFallback(
        api_key="dummy",
        model="gpt-4o-mini",
        quality_analyzer=analyzer,
        client=client,
    )

    assert fallback.should_trigger_fallback(low_quality_ocr_result) is True
    report = fallback.last_quality_report
    assert report is not None
    assert 'low_confidence' in report.reasons

    response = fallback.extract_with_vision(
        "/tmp/test.png",
        [{'field_name': 'invoice_no'}],
        ocr_fallback=low_quality_ocr_result['text'],
    )

    assert 'field_mappings' in response
    assert response['field_mappings']['invoice_no']['value'] == 'V123'
    assert client.responses.last_kwargs is not None
    assert client.responses.last_kwargs['model'] == 'gpt-4o-mini'


def test_merge_prefers_highest_confidence() -> None:
    """Merged results must keep the entry with the highest confidence."""

    ocr_mappings = {
        'invoice_no': {
            'value': '123',
            'confidence': 0.5,
            'source': 'ocr',
        }
    }
    vision_mappings = {
        'invoice_no': {
            'value': 'V123',
            'confidence': 0.95,
            'source': 'vision',
        }
    }

    merged = merge_ocr_and_vision_results(ocr_mappings, vision_mappings)

    assert merged['invoice_no']['value'] == 'V123'
    assert merged['invoice_no']['source'] == 'vision'
    alternates = merged['invoice_no'].get('alternates', [])
    assert any(item.get('value') == '123' for item in alternates)
    assert any(item.get('source') == 'ocr' for item in alternates)
