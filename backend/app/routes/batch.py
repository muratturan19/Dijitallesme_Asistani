# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
import logging
import asyncio
import time

from ..config import settings
from ..database import get_db, BatchJob, Document, ExtractedData, Template
from ..models import BatchStartRequest, BatchStatusResponse
from ..core.image_processor import ImageProcessor
from ..core.ocr_engine import OCREngine
from .ocr_utils import (
    build_runtime_configuration,
    run_field_level_ocr
)
from ..core.ai_field_mapper import AIFieldMapper
from ..core.handwriting_interpreter import (
    ExpertModelExecutor,
    HandwritingInterpreter,
    determine_specialist_candidates,
    merge_field_mappings,
)
from ..core.template_learning_service import TemplateLearningService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/batch", tags=["batch"])


async def _run_learning_refresh(db_path: str, template_id: int) -> None:
    """Refresh learned hints in background after batch corrections."""

    await asyncio.sleep(0)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_path, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    process_started = time.perf_counter()

    try:
        service = TemplateLearningService(db)
        hints = service.generate_template_hints(template_id=template_id)
        logger.debug(
            "Otomatik öğrenme yenilemesi planlandı: template=%s, alan_sayısı=%d",
            template_id,
            len(hints),
        )
    except Exception:
        logger.exception(
            "Otomatik öğrenme yenilemesi başarısız oldu: template=%s",
            template_id,
        )
    finally:
        db.close()


def _schedule_learning_refresh(db_path: str, template_id: int) -> None:
    """Schedule automatic learning refresh when corrections become available."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_run_learning_refresh(db_path, template_id))
        return

    loop.create_task(_run_learning_refresh(db_path, template_id))


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

        learning_service = TemplateLearningService(db)
        learned_hints = learning_service.load_learned_hints(template.id)

        runtime_config = build_runtime_configuration(
            template.extraction_rules,
            settings.TESSERACT_LANG,
            learned_hints=learned_hints or None
        )
        global_profile = runtime_config['preprocessing_profile']
        global_ocr_options = runtime_config['ocr_options']
        field_rules = runtime_config['field_rules']
        field_hints = runtime_config['field_hints']
        applied_rules = runtime_config['summary']
        rules_obj = runtime_config['rules']

        # Update status
        document.status = "processing"
        db.commit()

        # Process document
        image_processor = ImageProcessor(settings.TEMP_DIR)
        processed_document = image_processor.process_file(
            document.file_path,
            profile=global_profile
        )

        if not processed_document:
            raise Exception("Resim işleme hatası")

        # Run OCR if required
        ocr_cmd = rules_obj.ocr.tesseract_cmd if getattr(rules_obj, 'ocr', None) else None
        ocr_engine = OCREngine(
            ocr_cmd or settings.TESSERACT_CMD,
            runtime_config['language']
        )

        if processed_document.text:
            logger.info(
                "Toplu iş belgesi metin katmanından işlendi, OCR atlandı: %s",
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
            ocr_result = ocr_engine.extract_text(
                processed_document.image_path,
                options=global_ocr_options
            )
            ocr_result['source'] = 'ocr'

        if not ocr_result or not ocr_result.get('text'):
            raise Exception("OCR hatası")

        # AI Mapping
        ai_mapper = AIFieldMapper(
            settings.OPENAI_API_KEY,
            settings.AI_PRIMARY_MODEL,
            temperature=settings.AI_PRIMARY_TEMPERATURE,
            context_window=settings.AI_PRIMARY_CONTEXT_WINDOW,
        )
        if (
            field_rules
            and processed_document
            and (processed_document.image_path or processed_document.original_image_path)
        ):
            field_results = run_field_level_ocr(
                image_processor,
                ocr_engine,
                processed_document,
                document.file_path,
                field_rules
            )

            if field_results:
                ocr_result.setdefault('field_results', field_results)

        logger.debug(
            "AIFieldMapper'e iletilen ipuçları: toplam=%d, öğrenilmiş_alanlar=%s",
            len(field_hints or {}),
            sorted(learned_hints.keys()) if learned_hints else []
        )

        mapping_result = ai_mapper.map_fields(
            ocr_result['text'],
            template.target_fields,
            ocr_result,
            field_hints=field_hints
        )

        primary_field_mappings = mapping_result.get('field_mappings') or {}
        candidate_configs = determine_specialist_candidates(
            template.target_fields,
            primary_field_mappings,
            low_confidence_floor=settings.AI_HANDWRITING_LOW_CONFIDENCE_THRESHOLD,
            allowed_tiers=settings.AI_HANDWRITING_TIERS,
        )

        specialist_mapping: Dict[str, Any] = {}
        specialist_results: List[Dict[str, Any]] = []
        specialist_error: Optional[str] = None

        if candidate_configs:
            logger.info(
                "Belge %s için uzman modeli tetiklendi: alanlar=%s",
                document.id,
                sorted(candidate_configs.keys()),
            )
            interpreter = HandwritingInterpreter(settings.OPENAI_API_KEY)
            executor = ExpertModelExecutor(
                interpreter,
                max_workers=settings.AI_HANDWRITING_MAX_WORKERS,
            )
            try:
                specialist_results = executor.dispatch([
                    {
                        'ocr_result': ocr_result,
                        'field_configs': candidate_configs,
                        'primary_mapping': primary_field_mappings,
                        'field_hints': field_hints,
                        'document_info': {
                            'document_id': document.id,
                            'template_id': template.id,
                            'batch_job_id': document.batch_job_id,
                        },
                    }
                ])
            finally:
                executor.close()

            if specialist_results:
                specialist_mapping = specialist_results[0].get('field_mappings') or {}
                specialist_error = specialist_results[0].get('error')
                if specialist_error:
                    logger.warning(
                        "Uzman modeli hatası (doc=%s): %s",
                        document.id,
                        specialist_error,
                    )
            else:
                logger.warning(
                    "Uzman modeli sonuç döndürmedi: belge=%s",
                    document.id,
                )

        merged_mappings = merge_field_mappings(
            primary_field_mappings,
            specialist_mapping,
        )

        for field in template.target_fields or []:
            name = field.get('field_name')
            if name and name not in merged_mappings:
                merged_mappings[name] = {
                    'value': None,
                    'confidence': 0.0,
                    'source': 'unmapped',
                }

        # Extract field values and confidence scores
        field_values = {}
        confidence_scores = {}

        for field_name, field_data in merged_mappings.items():
            field_values[field_name] = field_data.get('value')
            confidence_scores[field_name] = field_data.get('confidence', 0.0)

        if specialist_results:
            estimated_cost = sum(
                result.get('estimated_cost', 0.0)
                for result in specialist_results
                if isinstance(result, dict)
            )
            if estimated_cost:
                logger.info(
                    "Uzman modeli tahmini maliyeti: doc=%s, cost=$%.4f",
                    document.id,
                    estimated_cost,
                )

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

        logger.info(
            "Belge işlendi: %s (kaynak: %s)",
            document_id,
            ocr_result.get('source', 'ocr')
        )
        logger.debug("Uygulanan kurallar: %s", applied_rules)

        processing_duration = time.perf_counter() - process_started
        logger.info(
            "Belge işleme süresi: %.3fs (doc=%s)",
            processing_duration,
            document.id,
        )

        _schedule_learning_refresh(db_path, template_id)

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
        template = db.query(Template).filter(
            Template.id == request.template_id
        ).first()

        if not template:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")

        learning_service = TemplateLearningService(db)
        learned_hints = learning_service.load_learned_hints(template.id)

        runtime_config = build_runtime_configuration(
            template.extraction_rules,
            settings.TESSERACT_LANG,
            learned_hints=learned_hints or None
        )

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
            'applied_rules': runtime_config['summary'],
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

        applied_rules: Optional[Dict[str, Any]] = None
        if batch_job.template:
            learning_service = TemplateLearningService(db)
            learned_hints = learning_service.load_learned_hints(batch_job.template.id)
            runtime_config = build_runtime_configuration(
                batch_job.template.extraction_rules,
                settings.TESSERACT_LANG,
                learned_hints=learned_hints or None
            )
            applied_rules = runtime_config['summary']

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
            low_confidence_items=low_confidence_items,
            applied_rules=applied_rules
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
