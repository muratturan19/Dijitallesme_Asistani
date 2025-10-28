# -*- coding: utf-8 -*-
import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Dict, Optional
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.handwriting_interpreter import (
    HandwritingInterpreter,
    determine_specialist_candidates,
    merge_field_mappings,
)
from app.core.smart_vision_fallback import merge_ocr_and_vision_results


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


def test_specialist_candidates_ignore_vision_boost_for_primary_selection() -> None:
    template_fields = [
        {'field_name': 'signature', 'llm_tier': 'handwriting'},
    ]
    primary_mapping = {
        'signature': {'confidence': 0.25, 'source': 'llm-primary'},
    }
    vision_mapping = {
        'signature': {'confidence': 0.95, 'source': 'vision'},
    }

    augmented = merge_ocr_and_vision_results(primary_mapping, vision_mapping)

    assert augmented['signature']['confidence'] == 0.95

    candidates = determine_specialist_candidates(
        template_fields,
        primary_mapping,
        low_confidence_floor=0.6,
        allowed_tiers=('handwriting',),
    )

    assert 'signature' in candidates
    assert candidates['signature']['llm_tier'] == 'handwriting'


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
        'pages': [
            {
                'page_number': 1,
                'text': 'Signed by A.L. appears on the cheque',
                'lines': [
                    {
                        'text': 'Signed by A.L.',
                        'confidence': 0.45,
                        'bounding_box': {'x': 10, 'y': 10, 'w': 90, 'h': 40},
                    },
                    {
                        'text': 'Other content',
                        'confidence': 0.92,
                    },
                ],
            }
        ],
        'low_confidence_lines': [
            {
                'text': 'Signed by A.L.',
                'confidence': 0.45,
                'page_number': 1,
                'bounding_box': {'x': 10, 'y': 10, 'w': 90, 'h': 40},
            }
        ],
        'field_results': {
            'signature': {
                'text': 'Signed by A.L.',
                'roi': [10, 10, 100, 50],
                'lines': [
                    {
                        'text': 'Signed by A.L.',
                        'confidence': 0.45,
                        'bounding_box': {'x': 10, 'y': 10, 'w': 90, 'h': 40},
                    }
                ],
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

    sections = prompt.split('\n\n')

    general_section = next(
        section for section in sections if section.startswith('Genel OCR metin önizlemesi:')
    )
    _, general_payload = general_section.split('\n', 1)
    general_data = json.loads(general_payload)

    assert general_data['segments'], 'Genel segment listesi boş olmamalı'
    assert any(seg.get('field') == 'signature' for seg in general_data['segments'])
    assert any('bounding_box' in seg for seg in general_data['segments'])

    field_section = next(
        section for section in sections if section.startswith('Alan: signature')
    )
    _, field_payload = field_section.split('\n', 1)
    field_data = json.loads(field_payload)

    assert field_data['targeted_snippets'], 'Alan kırpıntıları eksik'
    primary_snippet = field_data['targeted_snippets'][0]
    assert primary_snippet['text'].startswith('Signed by A.L.')
    assert primary_snippet['bounding_box']['w'] == 90


def test_reasoning_model_omits_top_p_for_responses_transport() -> None:
    interpreter = HandwritingInterpreter(
        api_key="",
        model="gpt-5.1-mini",
        temperature=0.42,
        context_window=256,
    )

    interpreter._has_valid_api_key = True  # type: ignore[attr-defined]
    interpreter._client = object()  # type: ignore[attr-defined]

    captured: Dict[str, Any] = {}

    def fake_call(
        client: Any,
        *,
        model: str,
        messages: Any,
        response_format: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
        reasoning_effort: str = "medium",
        extra_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Any:
        captured["model"] = model
        captured["temperature"] = temperature
        captured["extra_kwargs"] = extra_kwargs

        response_payload = {
            "field_mappings": {
                "signature": {"value": "Ada", "confidence": 0.88},
            }
        }

        return {
            "output": [
                {
                    "content": [
                        {"text": {"value": json.dumps(response_payload)}}
                    ]
                }
            ]
        }

    from app.core import handwriting_interpreter as module

    original_call = module.call_reasoning_model
    module.call_reasoning_model = fake_call

    try:
        result = interpreter.interpret_fields(
            {"text": "dummy", "field_results": {}},
            {"signature": {"field_name": "signature"}},
            {},
        )
    finally:
        module.call_reasoning_model = original_call

    assert captured["model"] == "gpt-5.1-mini"
    assert captured["temperature"] is None
    assert captured["extra_kwargs"] == {"max_output_tokens": 256}

    metadata = result.get("model_metadata") or {}
    assert metadata.get("transport") == "responses"
    reasoning_params = metadata.get("reasoning_parameters") or {}
    assert "top_p" not in reasoning_params
    assert reasoning_params.get("max_output_tokens") == 256


def test_template_analyze_includes_specialist_model_metadata() -> None:
    from app.config import settings
    from app.routes import template as template_module

    class FakeDocument:
        def __init__(self) -> None:
            self.id = 1
            self.status = "pending"
            self.file_path = "dummy.pdf"
            self.template_id = 99

    class FakeTemplate:
        def __init__(self) -> None:
            self.id = 99
            self.target_fields = [
                {"field_name": "signature", "enabled": True, "llm_tier": "handwriting"}
            ]
            self.extraction_rules = {}

    class FakeQuery:
        def __init__(self, result: Any) -> None:
            self._result = result

        def filter(self, *args: Any, **kwargs: Any) -> "FakeQuery":
            return self

        def first(self) -> Any:
            return self._result

    class FakeSession:
        def __init__(self, document: FakeDocument) -> None:
            self._document = document
            self.commits = 0

        def query(self, model: Any) -> FakeQuery:
            if getattr(model, "__name__", "") == "Document":
                return FakeQuery(self._document)
            return FakeQuery(None)

        def commit(self) -> None:
            self.commits += 1

        def add(self, _obj: Any) -> None:
            pass

        def close(self) -> None:
            pass

    class FakeTemplateManager:
        def __init__(self, _db: Any) -> None:
            pass

        def get_template(self, _template_id: int) -> FakeTemplate:
            return FakeTemplate()

    class FakeLearningService:
        def __init__(self, _db: Any) -> None:
            pass

        def load_learned_hints(self, _template_id: int) -> Dict[str, Dict[str, Any]]:
            return {}

    class FakeImageProcessor:
        def __init__(self, _temp_dir: Any) -> None:
            pass

        def process_file(self, _path: str, *, profile: Dict[str, Any]) -> Any:
            return SimpleNamespace(
                text="",
                image_path="image.png",
                original_image_path=None,
            )

    class FakeOCREngine:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def extract_text(self, _image_path: str, *, options: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "text": "primary text",
                "word_count": 2,
                "average_confidence": 0.3,
                "field_results": {},
            }

    class FakeAIFieldMapper:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def map_fields(
            self,
            _text: str,
            _template_fields: Any,
            _ocr_result: Dict[str, Any],
            *,
            field_hints: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            return {
                "field_mappings": {
                    "signature": {
                        "value": None,
                        "confidence": 0.2,
                        "source": "llm-primary",
                    }
                }
            }

        def calculate_field_status(self, confidence: float) -> str:
            return "low" if confidence < 0.5 else "high"

    class FakeInterpreter:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def interpret_fields(
            self,
            _ocr_result: Dict[str, Any],
            _field_configs: Dict[str, Any],
            _primary_mapping: Dict[str, Any],
            *,
            field_hints: Optional[Dict[str, Any]] = None,
            document_info: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            return {
                "field_mappings": {
                    "signature": {"value": "Ada", "confidence": 0.91}
                },
                "model_metadata": {
                    "model": "gpt-5",
                    "transport": "responses",
                    "reasoning_effort": "high",
                    "reasoning_parameters": {"max_output_tokens": 2048},
                },
            }

    def fake_runtime_config(_rules: Dict[str, Any], _lang: str, *, learned_hints: Any) -> Dict[str, Any]:
        return {
            "preprocessing_profile": {},
            "ocr_options": {},
            "field_rules": {"signature": {}},
            "field_hints": {},
            "summary": ["default"],
            "rules": SimpleNamespace(
                ocr=SimpleNamespace(tesseract_cmd=settings.TESSERACT_CMD)
            ),
            "language": settings.TESSERACT_LANG,
        }

    def fake_run_field_level_ocr(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
        return {}

    original_api_key = settings.OPENAI_API_KEY
    settings.OPENAI_API_KEY = "test-key"

    document = FakeDocument()
    fake_db = FakeSession(document)
    request = SimpleNamespace(document_id=document.id, template_id=document.template_id)
    result: Dict[str, Any] = {}

    try:
        with patch("app.routes.template.TemplateManager", FakeTemplateManager), patch(
            "app.routes.template.TemplateLearningService", FakeLearningService
        ), patch(
            "app.routes.template.build_runtime_configuration", fake_runtime_config
        ), patch(
            "app.routes.template.ImageProcessor", FakeImageProcessor
        ), patch(
            "app.routes.template.OCREngine", FakeOCREngine
        ), patch(
            "app.routes.template.AIFieldMapper", FakeAIFieldMapper
        ), patch(
            "app.routes.template.HandwritingInterpreter", FakeInterpreter
        ), patch(
            "app.routes.template.run_field_level_ocr", fake_run_field_level_ocr
        ):
            result = asyncio.run(template_module.analyze_document(request, db=fake_db))
    finally:
        settings.OPENAI_API_KEY = original_api_key

    assert "specialist" in result
    specialist = result["specialist"]
    assert specialist["model"]["model"] == "gpt-5"
    assert specialist["model"]["reasoning_effort"] == "high"
    assert specialist["model"]["reasoning_parameters"]["max_output_tokens"] == 2048
