# -*- coding: utf-8 -*-
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.handwriting_interpreter import (
    HandwritingInterpreter,
    determine_specialist_candidates,
    merge_field_mappings,
)


def test_determine_specialist_candidates_combines_tier_and_confidence() -> None:
    template_fields = [
        {'field_name': 'amount', 'llm_tier': 'standard'},
        {'field_name': 'signature', 'llm_tier': 'handwriting'},
        {'field_name': 'notes', 'handwriting_threshold': 0.8},
    ]
    primary_mapping = {
        'amount': {'confidence': 0.4},
        'notes': {'confidence': 0.5},
    }

    candidates = determine_specialist_candidates(
        template_fields,
        primary_mapping,
        low_confidence_floor=0.6,
        allowed_tiers=('handwriting', 'guided'),
    )

    assert set(candidates.keys()) == {'amount', 'signature', 'notes'}


def test_merge_field_mappings_prefers_highest_confidence_and_tracks_alternates() -> None:
    primary = {
        'amount': {'value': '100', 'confidence': 0.55, 'source': 'llm-primary'},
        'date': {'value': '2024-01-01', 'confidence': 0.9, 'source': 'llm-primary'},
    }
    specialist = {
        'amount': {'value': '100.00', 'confidence': 0.8, 'source': 'llm-specialist'},
        'date': {'value': '2024-02-01', 'confidence': 0.7, 'source': 'llm-specialist'},
        'signature': {'value': 'Ada Lovelace', 'confidence': 0.6, 'source': 'llm-specialist'},
    }

    merged = merge_field_mappings(primary, specialist)

    assert merged['amount']['value'] == '100.00'
    assert merged['amount']['source'] == 'llm-specialist'
    assert merged['date']['value'] == '2024-01-01'
    assert merged['date']['source'] == 'llm-primary'
    assert merged['date']['alternates'][0]['value'] == '2024-02-01'
    assert merged['signature']['value'] == 'Ada Lovelace'


def test_handwriting_prompt_includes_field_level_context() -> None:
    interpreter = HandwritingInterpreter(
        api_key="dummy",
        model="test-model",
        temperature=0.1,
        context_window=128,
    )

    ocr_result = {
        'text': 'Lorem ipsum dolor sit amet',
        'field_results': {
            'signature': {
                'text': 'Signed by A.L.',
                'roi': [10, 10, 100, 50],
                'bounding_box': {'x': 10, 'y': 10, 'w': 90, 'h': 40},
            }
        },
        'word_count': 5,
        'source': 'ocr',
    }
    field_configs = {
        'signature': {'field_name': 'signature', 'llm_tier': 'handwriting'},
    }
    primary_mapping = {
        'signature': {'value': None, 'confidence': 0.2},
    }

    prompt = interpreter.build_prompt(
        ocr_result,
        field_configs,
        primary_mapping,
        field_hints={'signature': {'type_hint': 'name'}},
        document_info={'document_id': 1},
    )

    assert 'Signed by A.L.' in prompt
    assert 'roi' in prompt
    assert 'field_config' in prompt
