# -*- coding: utf-8 -*-
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.ai_field_mapper import AIFieldMapper


def test_build_mapping_prompt_includes_field_metadata():
    mapper = AIFieldMapper(api_key="")

    fields = [
        {
            'field_name': 'invoice_total',
            'data_type': 'number',
            'required': True,
            'metadata': {'llm_guidance': 'Toplam tutarı yalnızca fatura metninden çıkar.'}
        }
    ]

    prompt = mapper._build_mapping_prompt("OCR TEXT", fields)

    assert '"metadata"' in prompt
    assert 'Toplam tutarı yalnızca fatura metninden çıkar.' in prompt
