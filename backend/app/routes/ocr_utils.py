# -*- coding: utf-8 -*-
"""Shared helpers for applying template OCR overrides."""

from typing import Any, Dict, Optional, Union

from ..core.image_processor import ImageProcessor, ProcessedDocument
from ..core.ocr_engine import OCREngine
from ..models import TemplateExtractionRules


def _rules_to_dict(
    config: Optional[Union[TemplateExtractionRules, Dict[str, Any]]]
) -> Optional[Dict[str, Any]]:
    if isinstance(config, TemplateExtractionRules):
        return config.dict()
    return config



def resolve_nested_dict(
    rules: Optional[Dict[str, Any]],
    *keys: str
) -> Optional[Dict[str, Any]]:
    """Return the first nested dict found for provided keys."""

    if not isinstance(rules, dict):
        return None

    for key in keys:
        nested = rules.get(key)
        if isinstance(nested, dict):
            return nested

    return None


def resolve_ocr_options(
    config: Optional[Union[TemplateExtractionRules, Dict[str, Any]]]
) -> Optional[Dict[str, Any]]:
    """Extract Tesseract configuration overrides from config maps."""

    config = _rules_to_dict(config)
    if not isinstance(config, dict):
        return None

    options: Dict[str, Any] = {}

    nested = resolve_nested_dict(
        config,
        'ocr_options',
        'ocr',
        'tesseract',
        'options'
    )
    if nested:
        options.update({k: v for k, v in nested.items() if v is not None})

    allowed_keys = {
        'psm',
        'oem',
        'language',
        'whitelist',
        'char_whitelist',
        'blacklist',
        'config',
        'dpi',
        'variables'
    }

    for key in allowed_keys:
        if key in config and config[key] is not None and key not in options:
            options[key] = config[key]

    return options or None


def resolve_preprocessing_profile(
    config: Optional[Union[TemplateExtractionRules, Dict[str, Any]]]
) -> Optional[Dict[str, Any]]:
    """Extract preprocessing profile overrides from config maps."""

    config = _rules_to_dict(config)
    if not isinstance(config, dict):
        return None

    profile = resolve_nested_dict(
        config,
        'preprocessing',
        'preprocess',
        'image_processing',
        'processing'
    ) or {}

    allowed_keys = {
        'denoise',
        'denoise_strength',
        'deskew',
        'contrast',
        'clahe_clip_limit',
        'clahe_tile_grid_size',
        'threshold',
        'threshold_block_size',
        'threshold_constant',
        'adaptive_threshold'
    }

    merged = {k: v for k, v in profile.items() if v is not None}

    for key in allowed_keys:
        if key in config and config[key] is not None and key not in merged:
            merged[key] = config[key]

    return merged or None


def resolve_field_rules(
    extraction_rules: Optional[Union[TemplateExtractionRules, Dict[str, Any]]]
) -> Dict[str, Dict[str, Any]]:
    """Return mapping of field name to rule definitions."""

    if isinstance(extraction_rules, TemplateExtractionRules):
        return extraction_rules.get_field_rule_configs()

    if not isinstance(extraction_rules, dict):
        return {}

    field_section = resolve_nested_dict(
        extraction_rules,
        'fields',
        'field_rules',
        'field_overrides',
        'fields_config'
    )

    candidates = field_section if isinstance(field_section, dict) else extraction_rules

    field_rules: Dict[str, Dict[str, Any]] = {}

    reserved_keys = {
        'ocr_options',
        'ocr',
        'tesseract',
        'preprocessing',
        'preprocess',
        'image_processing',
        'processing'
    }

    for key, value in candidates.items():
        if key in reserved_keys:
            continue
        if not isinstance(value, dict):
            continue
        if any(sub_key in value for sub_key in ('roi', 'region', 'box', 'ocr', 'ocr_options', 'tesseract')):
            field_rules[str(key)] = value
            continue
        if any(sub_key in value for sub_key in (
            'psm', 'oem', 'language', 'whitelist', 'char_whitelist', 'preprocessing', 'preprocess'
        )):
            field_rules[str(key)] = value

    return field_rules


def run_field_level_ocr(
    image_processor: ImageProcessor,
    ocr_engine: OCREngine,
    processed_document: ProcessedDocument,
    original_document_path: str,
    field_rules: Dict[str, Dict[str, Any]]
) -> Dict[str, Dict[str, Any]]:
    """Execute OCR for configured fields and return per-field results."""

    if not field_rules:
        return {}

    base_image_path = (
        processed_document.original_image_path
        or processed_document.image_path
        or original_document_path
    )

    if not base_image_path:
        return {}

    results: Dict[str, Dict[str, Any]] = {}

    for field_name, config in field_rules.items():
        if not isinstance(config, dict):
            continue
        if config.get('enabled') is False:
            continue

        roi = config.get('roi') or config.get('region') or config.get('box')
        profile = resolve_preprocessing_profile(config)

        region_path = image_processor.prepare_field_image(
            base_image_path,
            field_name,
            roi=roi,
            preprocessing_profile=profile
        )

        if not region_path:
            continue

        options = resolve_ocr_options(config)
        field_result = ocr_engine.extract_text(
            region_path,
            options=options
        )

        field_result['image_path'] = region_path

        if roi is not None:
            field_result['roi'] = roi
        if profile:
            field_result['preprocessing'] = profile
        if options:
            field_result['ocr_options'] = options

        results[field_name] = field_result

    return results


def build_runtime_configuration(
    extraction_rules: Optional[Union[TemplateExtractionRules, Dict[str, Any]]],
    default_language: str
) -> Dict[str, Any]:
    """Prepare reusable runtime structures from stored template rules."""

    rules_obj = (
        extraction_rules
        if isinstance(extraction_rules, TemplateExtractionRules)
        else TemplateExtractionRules.parse_obj(extraction_rules or {})
    )

    effective_language = rules_obj.effective_language(default_language)
    preprocessing_profile = resolve_preprocessing_profile(rules_obj)
    ocr_options = resolve_ocr_options(rules_obj)
    field_rules = resolve_field_rules(rules_obj)
    field_hints = rules_obj.build_field_hints()
    applied_summary = rules_obj.audit_summary(
        effective_language=effective_language,
        global_ocr_options=ocr_options,
        preprocessing_profile=preprocessing_profile
    )

    return {
        'rules': rules_obj,
        'language': effective_language,
        'ocr_options': ocr_options,
        'preprocessing_profile': preprocessing_profile,
        'field_rules': field_rules,
        'field_hints': field_hints,
        'summary': applied_summary
    }
