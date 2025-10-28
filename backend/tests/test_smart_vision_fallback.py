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


class DummyCompletions:
    """Stub for the chat.completions endpoint."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.payload = payload
        self.last_kwargs: Optional[Dict[str, Any]] = None

    def create(self, **kwargs: Any) -> Dict[str, Any]:
        self.last_kwargs = kwargs
        return self.payload


class DummyChat:
    """Stub that exposes a completions attribute."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.completions = DummyCompletions(payload)


class DummyChatClient:
    """Client stub that mimics chat.completions availability."""

    def __init__(self, payload: Dict[str, Any]) -> None:
        self.chat = DummyChat(payload)


@pytest.fixture
def low_quality_ocr_result() -> Dict[str, Any]:
    """Return a synthetic OCR output that should trigger fallback."""

    return {
        'text': '123',
        'average_confidence': 0.2,
        'word_count': 2,
    }


def test_low_confidence_triggers_vision_call(
    low_quality_ocr_result: Dict[str, Any], tmp_path
) -> None:
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

    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake image bytes")

    response = fallback.extract_with_vision(
        str(image_path),
        [{'field_name': 'invoice_no'}],
        ocr_fallback=low_quality_ocr_result['text'],
    )

    assert 'field_mappings' in response
    assert response['field_mappings']['invoice_no']['value'] == 'V123'
    assert client.responses.last_kwargs is not None
    assert client.responses.last_kwargs['model'] == 'gpt-4o-mini'
    content = client.responses.last_kwargs['input'][1]['content'][1]
    assert content['type'] == 'input_image'
    assert str(content['image_url']).startswith('data:')


def test_chat_completions_payload_includes_image(tmp_path) -> None:
    """Fallback should send both text instructions and the encoded image."""

    payload = {
        'field_mappings': {
            'invoice_no': {
                'value': 'V123',
                'confidence': 0.92,
                'source': 'vision',
            }
        }
    }

    client = DummyChatClient(payload)
    fallback = SmartVisionFallback(
        api_key="dummy",
        model="gpt-4o-mini",
        client=client,
    )

    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake image bytes")

    response = fallback.extract_with_vision(
        str(image_path),
        [{'field_name': 'invoice_no'}],
        ocr_fallback="previous",
    )

    assert 'field_mappings' in response
    completions = client.chat.completions
    assert completions.last_kwargs is not None
    messages = completions.last_kwargs['messages']
    assert messages[1]['role'] == 'user'
    content = messages[1]['content']
    assert isinstance(content, list)
    assert content[0]['type'] == 'text'
    assert content[0]['text'].startswith('Analyze the provided document image')
    assert content[1]['type'] == 'input_image'
    assert str(content[1]['image_url']).startswith('data:')


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


def test_parse_handles_markdown_json_block(tmp_path) -> None:
    """Vision response payloads wrapped in code fences should be parsed."""

    fenced_json = """```json\n{\n  \"field_mappings\": {\n    \"invoice_no\": {\n      \"value\": \"V123\",\n      \"confidence\": 0.9,\n      \"source\": \"vision\"\n    }\n  }\n}\n```"""

    payload = {'text': fenced_json}

    client = DummyClient(payload)
    fallback = SmartVisionFallback(
        api_key="dummy",
        model="gpt-4o-mini",
        client=client,
    )

    image_path = tmp_path / "test.png"
    image_path.write_bytes(b"fake image bytes")

    response = fallback.extract_with_vision(
        str(image_path),
        [{'field_name': 'invoice_no'}],
    )

    assert 'field_mappings' in response
    assert response['field_mappings']['invoice_no']['value'] == 'V123'
