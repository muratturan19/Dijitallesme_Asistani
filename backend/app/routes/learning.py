# -*- coding: utf-8 -*-
"""Router exposing template learning endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.template_learning_service import TemplateLearningService
from ..database import CorrectionFeedback, get_db


class UserCorrectionRequest(BaseModel):
    """Schema representing a single correction submitted by a user."""

    document_id: int = Field(..., example=101, description="Belgenin benzersiz kimliği")
    template_field_id: Optional[int] = Field(
        None,
        example=12,
        description="Düzeltilen şablon alanının kimliği",
    )
    original_value: Optional[str] = Field(
        None,
        example="Yanlış değer",
        description="Sistemin önerdiği veya tespit ettiği mevcut değer",
    )
    corrected_value: str = Field(
        ...,
        example="Doğru değer",
        description="Kullanıcının onayladığı veya düzelttiği değer",
    )
    context: Optional[Dict[str, Any]] = Field(
        None,
        example={"reason": "manual_review", "notes": "OCR düzeltildi"},
        description="Düzeltmeye ait ek bağlamsal bilgiler",
    )
    user_id: Optional[int] = Field(
        None,
        example=7,
        description="Düzeltmeyi yapan kullanıcı kimliği (opsiyonel)",
    )


class CorrectionFeedbackResponse(BaseModel):
    """Persisted correction feedback representation."""

    id: int = Field(..., example=1)
    document_id: int = Field(..., example=101)
    template_field_id: Optional[int] = Field(None, example=12)
    original_value: Optional[str] = Field(None, example="Yanlış değer")
    corrected_value: str = Field(..., example="Doğru değer")
    feedback_context: Optional[Dict[str, Any]] = Field(None, example={"reason": "manual_review"})
    created_at: datetime = Field(..., example="2024-01-01T12:00:00Z")
    created_by: Optional[int] = Field(None, example=7)

    class Config:
        orm_mode = True


class BatchCorrectionRequest(BaseModel):
    """Schema for submitting multiple corrections at once."""

    corrections: List[UserCorrectionRequest] = Field(
        ...,
        min_items=1,
        example=[
            {
                "document_id": 101,
                "template_field_id": 12,
                "original_value": "Yanlış değer",
                "corrected_value": "Doğru değer",
                "context": {"reason": "manual_review"},
            }
        ],
        description="Toplu olarak kaydedilecek düzeltmeler listesi",
    )


class BatchCorrectionResponse(BaseModel):
    """Response schema for batch correction persistence."""

    saved: List[CorrectionFeedbackResponse] = Field(
        ...,
        description="Veritabanına kaydedilen düzeltme girdileri",
    )


class LearnedHintsResponse(BaseModel):
    """Response schema wrapping generated learning hints."""

    template_id: int = Field(..., example=5)
    hints: Dict[int, Dict[str, Any]] = Field(
        ...,
        example={
            12: {
                "type_hint": "number",
                "regex_patterns": [{"pattern": "-?\\d+", "source": "auto-learning"}],
                "examples": ["1234", "9876"],
            }
        },
        description="Alan kimliği ile eşleşen öğrenilmiş ipuçları",
    )


router = APIRouter(prefix="/api/learning", tags=["learning"])


@router.post(
    "/corrections",
    response_model=CorrectionFeedbackResponse,
    status_code=201,
    summary="Tekil kullanıcı düzeltmesini kaydet",
)
def save_user_correction(
    payload: UserCorrectionRequest,
    db: Session = Depends(get_db),
) -> CorrectionFeedbackResponse:
    """Persist a single correction using the template learning service."""

    service = TemplateLearningService(db)
    feedback = service.record_correction(
        document_id=payload.document_id,
        template_field_id=payload.template_field_id,
        original_value=payload.original_value,
        corrected_value=payload.corrected_value,
        context=payload.context,
        created_by=payload.user_id,
    )

    return CorrectionFeedbackResponse.from_orm(feedback)


@router.post(
    "/corrections/batch",
    response_model=BatchCorrectionResponse,
    status_code=201,
    summary="Toplu kullanıcı düzeltmelerini kaydet",
)
def save_batch_corrections(
    batch_request: BatchCorrectionRequest,
    db: Session = Depends(get_db),
) -> BatchCorrectionResponse:
    """Persist multiple corrections in a single request."""

    service = TemplateLearningService(db)
    saved_feedback: List[CorrectionFeedback] = []

    for correction in batch_request.corrections:
        feedback = service.record_correction(
            document_id=correction.document_id,
            template_field_id=correction.template_field_id,
            original_value=correction.original_value,
            corrected_value=correction.corrected_value,
            context=correction.context,
            created_by=correction.user_id,
        )
        saved_feedback.append(feedback)

    return BatchCorrectionResponse(
        saved=[CorrectionFeedbackResponse.from_orm(item) for item in saved_feedback]
    )


@router.get(
    "/hints/{template_id}",
    response_model=LearnedHintsResponse,
    summary="Şablon için öğrenilmiş ipuçlarını getir",
)
def get_learned_hints(
    template_id: int,
    sample_limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Düzeltme örneklerinden kaç tanesinin analiz edileceği",
    ),
    db: Session = Depends(get_db),
) -> LearnedHintsResponse:
    """Generate and return learned hints for a template using feedback records."""

    service = TemplateLearningService(db)
    hints = service.generate_template_hints(template_id=template_id, sample_limit=sample_limit)

    return LearnedHintsResponse(template_id=template_id, hints=hints)


@router.get(
    "/corrections/history",
    response_model=List[CorrectionFeedbackResponse],
    summary="Düzeltme geçmişini listele",
)
def get_correction_history(
    document_id: Optional[int] = Query(
        None,
        description="Filtrelemek için belge kimliği",
        example=101,
    ),
    template_field_id: Optional[int] = Query(
        None,
        description="Filtrelemek için şablon alanı kimliği",
        example=12,
    ),
    limit: int = Query(
        50,
        ge=1,
        le=500,
        description="Döndürülecek maksimum kayıt sayısı",
    ),
    db: Session = Depends(get_db),
) -> List[CorrectionFeedbackResponse]:
    """Return correction history filtered by document or template field."""

    if document_id is None and template_field_id is None:
        raise HTTPException(
            status_code=400,
            detail="Belge veya şablon alanı kimliklerinden en az biri sağlanmalıdır.",
        )

    service = TemplateLearningService(db)
    query = service.db.query(CorrectionFeedback)

    if document_id is not None:
        query = query.filter(CorrectionFeedback.document_id == document_id)
    if template_field_id is not None:
        query = query.filter(CorrectionFeedback.template_field_id == template_field_id)

    history = (
        query.order_by(CorrectionFeedback.created_at.desc()).limit(limit).all()
    )

    return [CorrectionFeedbackResponse.from_orm(item) for item in history]


__all__ = ["router"]
