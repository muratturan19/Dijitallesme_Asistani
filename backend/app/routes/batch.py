# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import logging
import asyncio

from ..config import settings
from ..database import get_db, BatchJob, Document, ExtractedData, Template
from ..models import BatchStartRequest, BatchStatusResponse
from ..core.image_processor import ImageProcessor
from ..core.ocr_engine import OCREngine
from ..core.ai_field_mapper import AIFieldMapper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batch", tags=["batch"])


async def process_document_task(
    document_id: int,
    template_id: int,
    db_path: str
):
    """
    Background task to process a single document

    Args:
        document_id: Document ID
        template_id: Template ID
        db_path: Database path for creating new session
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Create new DB session for background task
    engine = create_engine(db_path, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # Get document and template
        document = db.query(Document).filter(Document.id == document_id).first()
        template = db.query(Template).filter(Template.id == template_id).first()

        if not document or not template:
            logger.error(f"Belge veya şablon bulunamadı: doc={document_id}, tpl={template_id}")
            return

        # Update status
        document.status = "processing"
        db.commit()

        # Process image
        image_processor = ImageProcessor(settings.TEMP_DIR)
        preprocessed_path = image_processor.process_file(document.file_path)

        if not preprocessed_path:
            raise Exception("Resim işleme hatası")

        # Run OCR
        ocr_engine = OCREngine(settings.TESSERACT_CMD, settings.TESSERACT_LANG)
        ocr_result = ocr_engine.extract_text(preprocessed_path)

        if not ocr_result or not ocr_result.get('text'):
            raise Exception("OCR hatası")

        # AI Mapping
        ai_mapper = AIFieldMapper(settings.OPENAI_API_KEY, settings.OPENAI_MODEL)
        mapping_result = ai_mapper.map_fields(
            ocr_result['text'],
            template.target_fields,
            ocr_result
        )

        # Extract field values and confidence scores
        field_values = {}
        confidence_scores = {}

        for field_name, field_data in mapping_result['field_mappings'].items():
            field_values[field_name] = field_data['value']
            confidence_scores[field_name] = field_data['confidence']

        # Save extracted data
        extracted_data = ExtractedData(
            document_id=document.id,
            field_values=field_values,
            confidence_scores=confidence_scores,
            validation_status="pending"
        )

        db.add(extracted_data)

        # Update document status
        document.status = "completed"
        db.commit()

        logger.info(f"Belge işlendi: {document_id}")

    except Exception as e:
        logger.error(f"Belge işleme hatası {document_id}: {str(e)}")
        if document:
            document.status = "failed"
            db.commit()

    finally:
        db.close()


@router.post("/start", response_model=Dict[str, Any])
async def start_batch_processing(
    request: BatchStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Start batch processing job

    Creates batch job and processes files in background
    """
    try:
        # Get pending documents for this template
        documents = db.query(Document).filter(
            Document.template_id == request.template_id,
            Document.status == "pending"
        ).all()

        if not documents:
            raise HTTPException(
                status_code=404,
                detail="İşlenecek belge bulunamadı"
            )

        # Create batch job
        batch_job = BatchJob(
            template_id=request.template_id,
            status="processing",
            total_files=len(documents),
            processed_files=0,
            failed_files=0
        )

        db.add(batch_job)
        db.commit()
        db.refresh(batch_job)

        # Link documents to batch job
        for doc in documents:
            doc.batch_job_id = batch_job.id

        db.commit()

        # Start background processing
        db_path = settings.DATABASE_URL

        for doc in documents:
            background_tasks.add_task(
                process_document_task,
                doc.id,
                request.template_id,
                db_path
            )

        logger.info(f"Toplu işlem başlatıldı: {batch_job.id}, {len(documents)} belge")

        return {
            'batch_job_id': batch_job.id,
            'total_files': len(documents),
            'message': 'Toplu işlem başlatıldı'
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Toplu işlem başlatma hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{batch_job_id}", response_model=BatchStatusResponse)
async def get_batch_status(batch_job_id: int, db: Session = Depends(get_db)):
    """
    Get batch job status and progress
    """
    try:
        # Get batch job
        batch_job = db.query(BatchJob).filter(
            BatchJob.id == batch_job_id
        ).first()

        if not batch_job:
            raise HTTPException(status_code=404, detail="Toplu işlem bulunamadı")

        # Count processed and failed
        total_docs = db.query(Document).filter(
            Document.batch_job_id == batch_job_id
        ).count()

        completed_docs = db.query(Document).filter(
            Document.batch_job_id == batch_job_id,
            Document.status == "completed"
        ).count()

        failed_docs = db.query(Document).filter(
            Document.batch_job_id == batch_job_id,
            Document.status == "failed"
        ).count()

        # Update batch job
        batch_job.processed_files = completed_docs
        batch_job.failed_files = failed_docs

        # Check if completed
        if completed_docs + failed_docs >= total_docs:
            batch_job.status = "completed"

        db.commit()

        # Calculate progress
        progress = (completed_docs + failed_docs) / total_docs * 100 if total_docs > 0 else 0

        # Get low confidence items
        low_confidence_items = []

        extracted_data_list = db.query(ExtractedData).join(Document).filter(
            Document.batch_job_id == batch_job_id,
            ExtractedData.validation_status == "pending"
        ).all()

        for extracted_data in extracted_data_list:
            # Check if any field has low confidence
            has_low_confidence = False
            for field, confidence in extracted_data.confidence_scores.items():
                if confidence < 0.5:
                    has_low_confidence = True
                    break

            if has_low_confidence:
                low_confidence_items.append({
                    'document_id': extracted_data.document_id,
                    'extracted_data_id': extracted_data.id,
                    'confidence_scores': extracted_data.confidence_scores
                })

        return BatchStatusResponse(
            batch_job_id=batch_job.id,
            status=batch_job.status,
            progress=progress,
            total_files=total_docs,
            processed_files=completed_docs,
            failed_files=failed_docs,
            low_confidence_items=low_confidence_items
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Durum sorgulama hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list", response_model=List[Dict[str, Any]])
async def list_batch_jobs(db: Session = Depends(get_db)):
    """
    List all batch jobs
    """
    try:
        batch_jobs = db.query(BatchJob).order_by(
            BatchJob.created_at.desc()
        ).all()

        result = []
        for job in batch_jobs:
            result.append({
                'batch_job_id': job.id,
                'template_id': job.template_id,
                'status': job.status,
                'total_files': job.total_files,
                'processed_files': job.processed_files,
                'failed_files': job.failed_files,
                'created_at': job.created_at.isoformat()
            })

        return result

    except Exception as e:
        logger.error(f"Toplu işlem listesi hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{batch_job_id}", response_model=Dict[str, str])
async def delete_batch_job(batch_job_id: int, db: Session = Depends(get_db)):
    """
    Delete batch job and associated documents
    """
    try:
        batch_job = db.query(BatchJob).filter(
            BatchJob.id == batch_job_id
        ).first()

        if not batch_job:
            raise HTTPException(status_code=404, detail="Toplu işlem bulunamadı")

        # Delete associated documents
        db.query(Document).filter(
            Document.batch_job_id == batch_job_id
        ).delete()

        # Delete batch job
        db.delete(batch_job)
        db.commit()

        logger.info(f"Toplu işlem silindi: {batch_job_id}")

        return {"message": "Toplu işlem başarıyla silindi"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Toplu işlem silme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
