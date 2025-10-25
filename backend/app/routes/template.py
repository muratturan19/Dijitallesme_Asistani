# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import logging

from ..config import settings
from ..database import get_db, Template, Document
from ..models import (
    TemplateCreate, TemplateResponse, AnalyzeRequest,
    SaveTemplateRequest, TestTemplateRequest
)
from ..core.template_manager import TemplateManager
from ..core.image_processor import ImageProcessor
from ..core.ocr_engine import OCREngine
from ..core.ai_field_mapper import AIFieldMapper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/template", tags=["template"])


@router.post("/analyze", response_model=Dict[str, Any])
async def analyze_document(
    request: AnalyzeRequest,
    db: Session = Depends(get_db)
):
    """
    Analyze document with OCR and AI field mapping

    Runs OCR on document and uses AI to map fields
    """
    try:
        # Get document
        document = db.query(Document).filter(
            Document.id == request.document_id
        ).first()

        if not document:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")

        # Get template (for field definitions)
        # If template_id provided, use it; otherwise create temporary template
        template_fields = []

        if request.template_id:
            template_manager = TemplateManager(db)
            template = template_manager.get_template(request.template_id)

            if not template:
                raise HTTPException(status_code=404, detail="Şablon bulunamadı")

            template_fields = template.target_fields
        else:
            raise HTTPException(
                status_code=400,
                detail="Şablon ID'si gerekli"
            )

        # Update document status
        document.status = "processing"
        db.commit()

        # 1. Preprocess document
        image_processor = ImageProcessor(settings.TEMP_DIR)
        processed_document = image_processor.process_file(document.file_path)

        if not processed_document:
            raise HTTPException(
                status_code=500,
                detail="Resim işleme hatası"
            )

        # 2. Run OCR only when needed
        if processed_document.text:
            logger.info(
                "Belge metin katmanından işlendi, OCR atlandı: %s",
                document.id
            )
            cleaned_text = processed_document.text.strip()
            word_count = len(cleaned_text.split()) if cleaned_text else 0
            ocr_result = {
                'text': cleaned_text,
                'words_with_bbox': [],
                'confidence_scores': {},
                'average_confidence': 1.0,
                'word_count': word_count,
                'source': 'text-layer'
            }
        else:
            ocr_engine = OCREngine(
                settings.TESSERACT_CMD,
                settings.TESSERACT_LANG
            )
            ocr_result = ocr_engine.extract_text(processed_document.image_path)
            ocr_result['source'] = 'ocr'

        if not ocr_result or not ocr_result.get('text'):
            raise HTTPException(
                status_code=500,
                detail="OCR hatası - metin çıkarılamadı"
            )

        # 3. AI Field Mapping
        if not settings.OPENAI_API_KEY:
            raise HTTPException(
                status_code=500,
                detail="OpenAI API anahtarı yapılandırılmamış"
            )

        ai_mapper = AIFieldMapper(
            settings.OPENAI_API_KEY,
            settings.OPENAI_MODEL
        )

        mapping_result = ai_mapper.map_fields(
            ocr_result['text'],
            template_fields,
            ocr_result
        )

        # Format response
        suggested_mapping = {}
        for field_name, field_data in mapping_result['field_mappings'].items():
            confidence = field_data['confidence']
            status = ai_mapper.calculate_field_status(confidence)

            suggested_mapping[field_name] = {
                'value': field_data['value'],
                'confidence': confidence,
                'status': status,
                'source': field_data.get('source', '')
            }

        # Update document status
        document.status = "completed"
        db.commit()

        logger.info(f"Analiz tamamlandı: Belge {document.id}")

        return {
            'suggested_mapping': suggested_mapping,
            'ocr_text': ocr_result['text'],
            'overall_confidence': mapping_result['overall_confidence'],
            'word_count': ocr_result.get('word_count', 0),
            'extraction_source': ocr_result.get('source', 'ocr'),
            'message': (
                'Analiz başarıyla tamamlandı - kaynak: '
                f"{ocr_result.get('source', 'ocr')}"
            )
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analiz hatası: {str(e)}")
        if document:
            document.status = "failed"
            db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save", response_model=Dict[str, Any])
async def save_template(
    request: SaveTemplateRequest,
    db: Session = Depends(get_db)
):
    """
    Save template with confirmed field mappings
    """
    try:
        template_manager = TemplateManager(db)

        # Update template with confirmed mapping
        template = template_manager.update_template(
            request.template_id,
            {
                'name': request.name,
                'extraction_rules': request.confirmed_mapping
            }
        )

        if not template:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")

        logger.info(f"Şablon kaydedildi: {template.id}")

        return {
            'template_id': template.id,
            'template_name': template.name,
            'message': 'Şablon başarıyla kaydedildi'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Şablon kaydetme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test", response_model=Dict[str, Any])
async def test_template(
    document_id: int,
    template_id: int,
    db: Session = Depends(get_db)
):
    """
    Test template extraction on a new document
    """
    try:
        # Re-use analyze endpoint logic
        request = AnalyzeRequest(
            document_id=document_id,
            template_id=template_id
        )

        result = await analyze_document(request, db)

        return {
            **result,
            'message': 'Test başarıyla tamamlandı'
        }

    except Exception as e:
        logger.error(f"Test hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create", response_model=TemplateResponse)
async def create_template(
    template: TemplateCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new template
    """
    try:
        template_manager = TemplateManager(db)

        new_template = template_manager.create_template(
            name=template.name,
            fields=template.target_fields,
            extraction_rules=template.extraction_rules
        )

        logger.info(f"Yeni şablon oluşturuldu: {new_template.id}")

        return new_template

    except Exception as e:
        logger.error(f"Şablon oluşturma hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=List[TemplateResponse])
async def list_templates(db: Session = Depends(get_db)):
    """
    Get all templates
    """
    try:
        template_manager = TemplateManager(db)
        templates = template_manager.get_all_templates()

        return templates

    except Exception as e:
        logger.error(f"Şablon listesi hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: int, db: Session = Depends(get_db)):
    """
    Get template by ID
    """
    try:
        template_manager = TemplateManager(db)
        template = template_manager.get_template(template_id)

        if not template:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")

        return template

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Şablon getirme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{template_id}", response_model=Dict[str, str])
async def delete_template(template_id: int, db: Session = Depends(get_db)):
    """
    Delete template
    """
    try:
        template_manager = TemplateManager(db)
        success = template_manager.delete_template(template_id)

        if not success:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")

        return {"message": "Şablon başarıyla silindi"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Şablon silme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{template_id}/stats", response_model=Dict[str, Any])
async def get_template_stats(template_id: int, db: Session = Depends(get_db)):
    """
    Get template usage statistics
    """
    try:
        template_manager = TemplateManager(db)
        stats = template_manager.get_template_stats(template_id)

        if not stats:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"İstatistik hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
