# -*- coding: utf-8 -*-
from pydantic import BaseModel, Field, root_validator
from typing import Optional, List, Dict, Any
from datetime import datetime

try:  # pragma: no cover - compatibility shim
    from pydantic import ConfigDict  # type: ignore
except ImportError:  # pragma: no cover - Pydantic v1 fallback
    ConfigDict = None  # type: ignore


class OCRSettings(BaseModel):
    """Structured OCR preferences that can override engine behaviour."""

    language: Optional[str] = None
    psm: Optional[int] = Field(default=None, ge=0)
    oem: Optional[int] = Field(default=None, ge=0)
    dpi: Optional[int] = Field(default=None, ge=0)
    whitelist: Optional[str] = None
    blacklist: Optional[str] = None
    config: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    tesseract_cmd: Optional[str] = None

    class Config:
        extra = 'allow'


class PreprocessingProfile(BaseModel):
    """Structured preprocessing options for the ImageProcessor."""

    denoise: Optional[bool] = None
    denoise_strength: Optional[float] = None
    deskew: Optional[bool] = None
    contrast: Optional[bool] = None
    clahe_clip_limit: Optional[float] = None
    clahe_tile_grid_size: Optional[int] = None
    threshold: Optional[bool] = None
    adaptive_threshold: Optional[bool] = None
    threshold_block_size: Optional[int] = None
    threshold_constant: Optional[float] = None

    class Config:
        extra = 'allow'


class ExtractionRegexRule(BaseModel):
    """Regex helper used to pre/post process extracted values."""

    pattern: str
    flags: Optional[List[str]] = None
    description: Optional[str] = None

    class Config:
        extra = 'allow'


class ExtractionFieldRule(BaseModel):
    """Per-field overrides such as ROI, OCR, regex hints and fallbacks."""

    enabled: Optional[bool] = True
    roi: Optional[Any] = None
    ocr: Optional[OCRSettings] = None
    preprocessing: Optional[PreprocessingProfile] = None
    fallback_value: Optional[Any] = None
    type_hint: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    regex_rules: List[ExtractionRegexRule] = Field(default_factory=list)

    class Config:
        extra = 'allow'

    @root_validator(pre=True)
    def _unify_regex_sources(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(values, dict):
            return values

        values = dict(values)
        regex_sources: List[Any] = []

        for key in ('regex', 'regexes', 'regex_rules', 'regex_overrides', 'patterns'):
            raw = values.pop(key, None)
            if raw is None:
                continue
            if isinstance(raw, dict):
                raw = [raw]
            if isinstance(raw, list):
                regex_sources.extend(raw)

        if regex_sources:
            values['regex_rules'] = regex_sources

        return values

    def to_hint(self) -> Dict[str, Any]:
        hint: Dict[str, Any] = {}

        if self.type_hint:
            hint['type_hint'] = self.type_hint
        if self.fallback_value is not None:
            hint['fallback_value'] = self.fallback_value
        if self.regex_rules:
            hint['regex_patterns'] = [rule.dict(exclude_none=True) for rule in self.regex_rules]
        if self.roi is not None:
            hint['roi'] = self.roi
        if self.ocr is not None:
            hint['ocr'] = self.ocr.dict(exclude_none=True)
        if self.preprocessing is not None:
            hint['preprocessing'] = self.preprocessing.dict(exclude_none=True)
        if self.metadata:
            hint['metadata'] = self.metadata
        if self.enabled is False:
            hint['enabled'] = False

        return {k: v for k, v in hint.items() if v not in (None, {}, [], '')}

    def audit_summary(self) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}

        if self.enabled is not None:
            summary['enabled'] = self.enabled
        if self.type_hint:
            summary['type_hint'] = self.type_hint
        if self.fallback_value is not None:
            summary['fallback_value'] = self.fallback_value
        if self.roi is not None:
            summary['roi'] = self.roi
        if self.ocr is not None:
            summary['ocr'] = self.ocr.dict(exclude_none=True)
        if self.preprocessing is not None:
            summary['preprocessing'] = self.preprocessing.dict(exclude_none=True)
        if self.regex_rules:
            summary['regex'] = [rule.dict(exclude_none=True) for rule in self.regex_rules]
        if self.metadata:
            summary['metadata'] = self.metadata

        return {k: v for k, v in summary.items() if v not in (None, {}, [], '')}

    def to_runtime_dict(self) -> Dict[str, Any]:
        runtime: Dict[str, Any] = {}

        if self.enabled is not None:
            runtime['enabled'] = self.enabled
        if self.roi is not None:
            runtime['roi'] = self.roi
        if self.ocr is not None:
            ocr_options = self.ocr.dict(exclude_none=True)
            runtime['ocr'] = ocr_options
            runtime['ocr_options'] = ocr_options
        if self.preprocessing is not None:
            runtime['preprocessing'] = self.preprocessing.dict(exclude_none=True)
        if self.regex_rules:
            runtime['regex'] = [rule.dict(exclude_none=True) for rule in self.regex_rules]
        if self.fallback_value is not None:
            runtime['fallback_value'] = self.fallback_value
        if self.type_hint:
            runtime['type_hint'] = self.type_hint
        if self.metadata:
            runtime['metadata'] = self.metadata

        return runtime


class TemplateExtractionRules(BaseModel):
    """Structured container describing how extraction should run."""

    ocr: Optional[OCRSettings] = None
    preprocessing: Optional[PreprocessingProfile] = None
    regex_overrides: Dict[str, List[ExtractionRegexRule]] = Field(default_factory=dict)
    fallback_values: Dict[str, Any] = Field(default_factory=dict)
    fields: Dict[str, ExtractionFieldRule] = Field(default_factory=dict)
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        extra = 'allow'

    @root_validator(pre=True)
    def _coerce_legacy_format(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(values, dict):
            return values

        normalized = dict(values)
        field_block = normalized.get('fields')
        recognized = {'ocr', 'preprocessing', 'regex_overrides', 'fallback_values', 'fields', 'metadata'}

        if not isinstance(field_block, dict):
            field_block = {}

        for key in list(normalized.keys()):
            if key in recognized:
                continue
            field_block[key] = normalized.pop(key)

        regex_overrides = normalized.get('regex_overrides')
        if isinstance(regex_overrides, dict):
            normalized['regex_overrides'] = {
                str(field): (
                    value if isinstance(value, list) else [value]
                )
                for field, value in regex_overrides.items()
                if value is not None
            }

        normalized['fields'] = field_block
        return normalized

    def dict(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:  # type: ignore[override]
        kwargs.setdefault('exclude_none', True)
        return super().dict(*args, **kwargs)

    def build_field_hints(self) -> Dict[str, Dict[str, Any]]:
        hints: Dict[str, Dict[str, Any]] = {}

        for field_name, rule in self.fields.items():
            if rule.enabled is False:
                continue
            hint = rule.to_hint()
            if hint:
                hints[field_name] = hint

        for field_name, rules in self.regex_overrides.items():
            if not rules:
                continue
            entry = hints.setdefault(field_name, {})
            patterns = entry.setdefault('regex_patterns', [])
            patterns.extend(rule.dict(exclude_none=True) for rule in rules)

        for field_name, fallback in self.fallback_values.items():
            entry = hints.setdefault(field_name, {})
            if fallback is not None:
                entry['fallback_value'] = fallback

        return {
            name: {k: v for k, v in data.items() if v not in (None, {}, [], '')}
            for name, data in hints.items()
            if any(v not in (None, {}, [], '') for v in data.values())
        }

    def get_field_rule_configs(self) -> Dict[str, Dict[str, Any]]:
        configs: Dict[str, Dict[str, Any]] = {}

        for field_name, rule in self.fields.items():
            if rule.enabled is False:
                continue
            runtime = rule.to_runtime_dict()
            if runtime:
                configs[field_name] = runtime

        return configs

    def effective_language(self, default_language: str) -> str:
        if self.ocr and self.ocr.language:
            return self.ocr.language
        return default_language

    def audit_summary(
        self,
        *,
        effective_language: Optional[str] = None,
        global_ocr_options: Optional[Dict[str, Any]] = None,
        preprocessing_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}

        if self.ocr or effective_language or global_ocr_options:
            ocr_details: Dict[str, Any] = {}
            if self.ocr:
                ocr_details.update(self.ocr.dict(exclude_none=True))
            if effective_language:
                ocr_details['language'] = effective_language
            if global_ocr_options:
                ocr_details['options'] = global_ocr_options
            summary['ocr'] = {k: v for k, v in ocr_details.items() if v not in (None, {}, [], '')}

        if self.preprocessing or preprocessing_profile:
            preprocessing_details: Dict[str, Any] = {}
            if self.preprocessing:
                preprocessing_details.update(self.preprocessing.dict(exclude_none=True))
            if preprocessing_profile:
                preprocessing_details.update({k: v for k, v in preprocessing_profile.items() if v is not None})
            summary['preprocessing'] = {
                k: v for k, v in preprocessing_details.items() if v not in (None, {}, [], '')
            }

        if self.regex_overrides:
            summary['regex_overrides'] = {
                field: [rule.dict(exclude_none=True) for rule in rules if rule]
                for field, rules in self.regex_overrides.items()
                if rules
            }

        if self.fallback_values:
            summary['fallback_values'] = {
                field: value for field, value in self.fallback_values.items()
                if value not in (None, '')
            }

        field_summaries: Dict[str, Any] = {}
        for field_name, rule in self.fields.items():
            details = rule.audit_summary()
            if details:
                field_summaries[field_name] = details

        if field_summaries:
            summary['fields'] = field_summaries

        if self.metadata:
            summary['metadata'] = self.metadata

        return {k: v for k, v in summary.items() if v not in (None, {}, [], '')}


# Template Models
class TemplateFieldCreate(BaseModel):
    field_name: str
    data_type: str = Field(..., pattern="^(text|number|date)$")
    required: bool = False
    calculated: bool = False
    calculation_rule: Optional[str] = None
    regex_hint: Optional[str] = None
    ocr_psm: Optional[int] = None
    ocr_roi: Optional[str] = None
    enabled: bool = True


class TemplateFieldResponse(TemplateFieldCreate):
    id: int
    template_id: int

    class Config:
        from_attributes = True


class TemplateCreate(BaseModel):
    name: str
    target_fields: List[Dict[str, Any]]
    extraction_rules: Optional[TemplateExtractionRules] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    version: Optional[str] = None
    extraction_rules: Optional[TemplateExtractionRules] = None
    target_fields: Optional[List[Dict[str, Any]]] = None


class TemplateFieldsUpdate(BaseModel):
    target_fields: List[Dict[str, Any]]


class TemplateResponse(BaseModel):
    id: int
    name: str
    version: str
    target_fields: List[Dict[str, Any]]
    extraction_rules: Optional[TemplateExtractionRules]
    sample_document_path: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Document Models
class DocumentUpload(BaseModel):
    filename: str
    template_id: Optional[int] = None
    batch_job_id: Optional[int] = None


class DocumentResponse(BaseModel):
    id: int
    filename: str
    file_path: str
    upload_date: datetime
    status: str
    template_id: Optional[int]
    batch_job_id: Optional[int]

    class Config:
        from_attributes = True


# Extracted Data Models
class ExtractedDataCreate(BaseModel):
    document_id: int
    field_values: Dict[str, Any]
    confidence_scores: Dict[str, float]


class ExtractedDataUpdate(BaseModel):
    field_values: Optional[Dict[str, Any]] = None
    validation_status: Optional[str] = None


class ExtractedDataResponse(BaseModel):
    id: int
    document_id: int
    field_values: Dict[str, Any]
    confidence_scores: Dict[str, float]
    validation_status: str
    validated_at: Optional[datetime]

    class Config:
        from_attributes = True


# Batch Job Models
class BatchJobCreate(BaseModel):
    template_id: int
    total_files: int


class BatchJobResponse(BaseModel):
    id: int
    template_id: Optional[int]
    status: str
    total_files: int
    processed_files: int
    failed_files: int
    created_at: datetime

    class Config:
        from_attributes = True


# API Request/Response Models
class AnalyzeRequest(BaseModel):
    document_id: int
    template_id: int


class AnalyzeResponse(BaseModel):
    suggested_mapping: Dict[str, Dict[str, Any]]
    ocr_text: str
    confidence: float


class SaveTemplateRequest(BaseModel):
    template_id: int
    name: str
    confirmed_rules: TemplateExtractionRules = Field(..., alias='confirmed_mapping')
    target_fields: Optional[List[Dict[str, Any]]] = None

    if ConfigDict is not None:
        model_config = ConfigDict(populate_by_name=True)
    else:  # pragma: no cover - compatibility path for Pydantic v1
        class Config:  # type: ignore
            allow_population_by_field_name = True


class TestTemplateRequest(BaseModel):
    template_id: int


class BatchStartRequest(BaseModel):
    template_id: int


class BatchStatusResponse(BaseModel):
    batch_job_id: int
    status: str
    progress: float
    total_files: int
    processed_files: int
    failed_files: int
    low_confidence_items: List[Dict[str, Any]]
    applied_rules: Optional[Dict[str, Any]] = None


# Field Mapping Models
class FieldMapping(BaseModel):
    field_name: str
    extracted_value: Any
    confidence: float
    status: str  # "high", "medium", "low"


class MappingResult(BaseModel):
    mappings: List[FieldMapping]
    overall_confidence: float
    needs_review: bool


# Error Response
class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None


# Success Response
class SuccessResponse(BaseModel):
    message: str
    data: Optional[Dict[str, Any]] = None
