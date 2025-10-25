# -*- coding: utf-8 -*-
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# Template Models
class TemplateFieldCreate(BaseModel):
    field_name: str
    data_type: str = Field(..., pattern="^(text|number|date)$")
    required: bool = False
    calculated: bool = False
    calculation_rule: Optional[str] = None


class TemplateFieldResponse(TemplateFieldCreate):
    id: int
    template_id: int

    class Config:
        from_attributes = True


class TemplateCreate(BaseModel):
    name: str
    target_fields: List[Dict[str, Any]]
    extraction_rules: Optional[Dict[str, Any]] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    version: Optional[str] = None
    extraction_rules: Optional[Dict[str, Any]] = None


class TemplateResponse(BaseModel):
    id: int
    name: str
    version: str
    target_fields: List[Dict[str, Any]]
    extraction_rules: Optional[Dict[str, Any]]
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
    confirmed_mapping: Dict[str, Any]


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
