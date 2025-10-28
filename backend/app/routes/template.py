# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional
import logging

from ..config import settings
from ..database import get_db, Template, Document
from ..models import (
    TemplateCreate, TemplateResponse, AnalyzeRequest,
    ReanalyzeRequest, SaveTemplateRequest, TestTemplateRequest, TemplateFieldsUpdate
)
from ..core.template_manager import TemplateManager, TemplateNameConflictError
from ..core.image_processor import ImageProcessor
from ..core.ocr_engine import OCREngine
from .ocr_utils import (
    build_runtime_configuration,
    run_field_level_ocr
)
from ..core.ai_field_mapper import AIFieldMapper
from ..core.handwriting_interpreter import (
    HandwritingInterpreter,
    determine_specialist_candidates,
    merge_field_mappings,
)
from ..core.template_learning_service import TemplateLearningService
from ..core.smart_vision_fallback import (
    SmartVisionFallback,
    merge_ocr_and_vision_results,
)

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
        all_template_fields: List[Dict[str, Any]] = []
        template_fields: List[Dict[str, Any]] = []

        runtime_config: Optional[Dict[str, Any]] = None

        learned_hints: Dict[str, Dict[str, Any]] = {}

        if request.template_id:
            template_manager = TemplateManager(db)
            template = template_manager.get_template(request.template_id)

            if not template:
                raise HTTPException(status_code=404, detail="Şablon bulunamadı")

            all_template_fields = template.target_fields or []
            template_fields = [
                field for field in all_template_fields
                if field.get('enabled', True)
            ]
            learning_service = TemplateLearningService(db)
            learned_hints = learning_service.load_learned_hints(template.id)
            runtime_config = build_runtime_configuration(
                template.extraction_rules,
                settings.TESSERACT_LANG,
                learned_hints=learned_hints or None
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="Şablon ID'si gerekli"
            )

        # Update document status
        document.status = "processing"
        db.commit()

        runtime_config = runtime_config or build_runtime_configuration(
            {},
            settings.TESSERACT_LANG,
            learned_hints=learned_hints or None
        )
        global_profile = runtime_config['preprocessing_profile']
        global_ocr_options = runtime_config['ocr_options']
        field_rules = runtime_config['field_rules']
        field_hints = runtime_config['field_hints']
        applied_rules = runtime_config['summary']
        rules_obj = runtime_config['rules']

        # 1. Preprocess document
        image_processor = ImageProcessor(settings.TEMP_DIR)
        processed_document = image_processor.process_file(
            document.file_path,
            profile=global_profile
        )

        if not processed_document:
            raise HTTPException(
                status_code=500,
                detail="Resim işleme hatası"
            )

        ocr_cmd = rules_obj.ocr.tesseract_cmd if getattr(rules_obj, 'ocr', None) else None
        ocr_engine = OCREngine(
            ocr_cmd or settings.TESSERACT_CMD,
            runtime_config['language']
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
            ocr_result = ocr_engine.extract_text(
                processed_document.image_path,
                options=global_ocr_options
            )
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

        vision_fallback = SmartVisionFallback(
            settings.OPENAI_API_KEY,
            settings.AI_VISION_MODEL,
        )
        vision_quality = vision_fallback.evaluate_quality(ocr_result)
        vision_response: Optional[Dict[str, Any]] = None

        if vision_quality.should_fallback:
            logger.info(
                "Vision fallback tetiklendi: belge=%s, sebepler=%s",
                document.id,
                vision_quality.reasons,
            )
            vision_response = vision_fallback.extract_with_vision(
                document.file_path,
                template_fields,
                ocr_fallback=ocr_result.get('text', ''),
            )
        else:
            logger.debug(
                "Vision fallback gerekli görülmedi: score=%.2f",
                vision_quality.score,
            )

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

        if template_fields:
            logger.debug(
                "AIFieldMapper'e iletilen ipuçları: toplam=%d, öğrenilmiş_alanlar=%s",
                len(field_hints or {}),
                sorted(learned_hints.keys()) if learned_hints else []
            )
            mapping_result = ai_mapper.map_fields(
                ocr_result['text'],
                template_fields,
                ocr_result,
                field_hints=field_hints
            )
        else:
            mapping_result = {
                'field_mappings': {},
                'overall_confidence': 0.0
            }

        primary_llm_mapping = mapping_result.get('field_mappings') or {}

        augmented_mapping = primary_llm_mapping
        if vision_response and vision_response.get('field_mappings'):
            augmented_mapping = merge_ocr_and_vision_results(
                primary_llm_mapping,
                vision_response['field_mappings'],
            )

        candidate_configs = determine_specialist_candidates(
            template_fields,
            primary_llm_mapping,
            low_confidence_floor=settings.AI_HANDWRITING_LOW_CONFIDENCE_THRESHOLD,
            allowed_tiers=settings.AI_HANDWRITING_TIERS,
        )

        specialist_mapping: Dict[str, Any] = {}
        specialist_usage: Optional[Dict[str, Any]] = None
        specialist_error: Optional[str] = None
        specialist_metadata: Optional[Dict[str, Any]] = None

        if candidate_configs:
            logger.info(
                "Uzman modeli tetiklendi: belge=%s, alanlar=%s",
                document.id,
                sorted(candidate_configs.keys()),
            )
            interpreter = HandwritingInterpreter(settings.OPENAI_API_KEY)
            specialist_response = interpreter.interpret_fields(
                ocr_result,
                candidate_configs,
                augmented_mapping,
                field_hints=field_hints,
                document_info={
                    'document_id': document.id,
                    'template_id': request.template_id,
                },
            )
            specialist_mapping = specialist_response.get('field_mappings') or {}
            specialist_usage = specialist_response.get('usage')
            specialist_error = specialist_response.get('error')
            specialist_metadata = specialist_response.get('model_metadata')

            if specialist_error:
                logger.warning(
                    "Uzman modeli hatası: belge=%s, hata=%s",
                    document.id,
                    specialist_error,
                )
            else:
                logger.info(
                    "Uzman modeli tamamlandı: belge=%s, eşleşen_alanlar=%d",
                    document.id,
                    len(specialist_mapping),
                )

        merged_mappings = merge_field_mappings(
            augmented_mapping,
            specialist_mapping,
        )

        # Format response
        suggested_mapping: Dict[str, Any] = {}
        for field_name, field_data in merged_mappings.items():
            confidence = field_data.get('confidence', 0.0)
            status = ai_mapper.calculate_field_status(confidence)

            entry = {
                'value': field_data.get('value'),
                'confidence': confidence,
                'status': status,
                'source': field_data.get('source', ''),
            }
            if field_data.get('alternates'):
                entry['alternates'] = field_data['alternates']
            if field_data.get('notes'):
                entry['notes'] = field_data['notes']

            suggested_mapping[field_name] = entry

        for field in all_template_fields:
            field_name = field.get('field_name')
            if not field_name or field_name in suggested_mapping:
                continue

            suggested_mapping[field_name] = {
                'value': None,
                'confidence': 0.0,
                'status': 'high',
                'source': ''
            }

        # Update document status
        document.status = "completed"
        db.commit()

        logger.info(f"Analiz tamamlandı: Belge {document.id}")

        error_message = mapping_result.get('error')

        combined_confidence = mapping_result.get('overall_confidence', 0.0)
        if specialist_mapping:
            confidences = [
                float(item.get('confidence', 0.0) or 0.0)
                for item in specialist_mapping.values()
                if isinstance(item, dict)
            ]
            if confidences:
                combined_confidence = max(
                    combined_confidence,
                    sum(confidences) / len(confidences),
                )

        response_payload = {
            'suggested_mapping': suggested_mapping,
            'ocr_text': ocr_result['text'],
            'overall_confidence': combined_confidence,
            'word_count': ocr_result.get('word_count', 0),
            'extraction_source': ocr_result.get('source', 'ocr'),
            'applied_rules': applied_rules,
            'error': error_message
        }

        vision_payload: Dict[str, Any] = {
            'triggered': vision_quality.should_fallback,
            'quality_score': vision_quality.score,
            'reasons': vision_quality.reasons,
            'model': settings.AI_VISION_MODEL,
        }

        if vision_response:
            if vision_response.get('error'):
                vision_payload['error'] = vision_response['error']
            if vision_response.get('field_mappings'):
                vision_payload['resolved_fields'] = sorted(
                    vision_response['field_mappings'].keys()
                )

        response_payload['vision_fallback'] = vision_payload

        if candidate_configs:
            response_payload['specialist'] = {
                'requested_fields': sorted(candidate_configs.keys()),
                'resolved_fields': sorted(specialist_mapping.keys()),
                'usage': specialist_usage,
                'error': specialist_error,
            }
            if specialist_metadata:
                response_payload['specialist']['model'] = specialist_metadata

        if error_message:
            response_payload['message'] = (
                'Analiz uyarı ile tamamlandı: '
                f"{error_message}"
            )
        else:
            response_payload['message'] = (
                'Analiz başarıyla tamamlandı - kaynak: '
                f"{ocr_result.get('source', 'ocr')}"
            )

        if vision_quality.should_fallback:
            response_payload['message'] += " (Vision fallback uygulandı)"

        return response_payload

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analiz hatası: {str(e)}")
        if document:
            document.status = "failed"
            db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reanalyze", response_model=Dict[str, Any])
async def reanalyze_fields(
    request: ReanalyzeRequest,
    db: Session = Depends(get_db)
):
    """Re-run the handwriting specialist on a subset of template fields."""

    try:
        sanitized_fields = [
            field_name.strip()
            for field_name in request.fields
            if isinstance(field_name, str) and field_name.strip()
        ]

        if not sanitized_fields:
            raise HTTPException(
                status_code=400,
                detail="En az bir geçerli alan adı belirtmelisiniz",
            )

        document = db.query(Document).filter(
            Document.id == request.document_id
        ).first()

        if not document:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")

        template = db.query(Template).filter(
            Template.id == request.template_id
        ).first()

        if not template:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")

        template_fields: List[Dict[str, Any]] = template.target_fields or []
        template_field_map: Dict[str, Dict[str, Any]] = {
            str(field.get('field_name')).strip(): field
            for field in template_fields
            if isinstance(field, dict) and str(field.get('field_name')).strip()
        }

        missing_fields = sorted(
            field_name
            for field_name in sanitized_fields
            if field_name not in template_field_map
        )

        valid_fields = [
            field_name
            for field_name in sanitized_fields
            if field_name in template_field_map
        ]

        if not valid_fields:
            raise HTTPException(
                status_code=400,
                detail="Seçilen alanlar mevcut şablonda bulunamadı",
            )

        learning_service = TemplateLearningService(db)
        learned_hints = learning_service.load_learned_hints(template.id)

        runtime_config = build_runtime_configuration(
            template.extraction_rules,
            settings.TESSERACT_LANG,
            learned_hints=learned_hints or None,
        )

        image_processor = ImageProcessor(settings.TEMP_DIR)
        processed_document = image_processor.process_file(
            document.file_path,
            profile=runtime_config['preprocessing_profile'],
        )

        if not processed_document:
            raise HTTPException(
                status_code=500,
                detail="Resim işleme hatası",
            )

        ocr_component = getattr(runtime_config['rules'], 'ocr', None)
        ocr_cmd = getattr(ocr_component, 'tesseract_cmd', None) if ocr_component else None
        ocr_engine = OCREngine(
            ocr_cmd or settings.TESSERACT_CMD,
            runtime_config['language'],
        )

        if processed_document.text:
            cleaned_text = processed_document.text.strip()
            word_count = len(cleaned_text.split()) if cleaned_text else 0
            ocr_result: Dict[str, Any] = {
                'text': cleaned_text,
                'words_with_bbox': [],
                'confidence_scores': {},
                'average_confidence': 1.0,
                'word_count': word_count,
                'source': 'text-layer',
            }
        else:
            ocr_source_path = (
                processed_document.image_path
                or getattr(processed_document, 'original_image_path', None)
            )

            if not ocr_source_path:
                raise HTTPException(
                    status_code=500,
                    detail="OCR için görüntü yolu bulunamadı",
                )

            ocr_result = ocr_engine.extract_text(
                ocr_source_path,
                options=runtime_config['ocr_options'],
            )
            ocr_result['source'] = 'ocr'
            cleaned_text = (ocr_result.get('text') or '').strip()
            word_count = len(cleaned_text.split()) if cleaned_text else 0
            ocr_result['text'] = cleaned_text
            ocr_result['word_count'] = word_count

        if not ocr_result or not ocr_result.get('text'):
            raise HTTPException(
                status_code=500,
                detail="OCR hatası - metin çıkarılamadı",
            )

        field_rules = runtime_config['field_rules'] or {}
        selected_rules = {
            name: rules
            for name, rules in field_rules.items()
            if name in valid_fields
        }

        if selected_rules:
            field_level_results = run_field_level_ocr(
                image_processor,
                ocr_engine,
                processed_document,
                document.file_path,
                selected_rules,
            )
            if field_level_results:
                existing_results = ocr_result.setdefault('field_results', {})
                existing_results.update(field_level_results)

        field_hints = runtime_config['field_hints'] or {}
        relevant_hints = {
            name: hint
            for name, hint in field_hints.items()
            if name in valid_fields
        }

        def _normalize_primary_mapping(
            raw_mapping: Optional[Dict[str, Any]],
            allowed: List[str],
        ) -> Dict[str, Dict[str, Any]]:
            normalized: Dict[str, Dict[str, Any]] = {}

            if not isinstance(raw_mapping, dict):
                return normalized

            for field_name in allowed:
                payload = raw_mapping.get(field_name)
                if not isinstance(payload, dict):
                    continue

                try:
                    confidence_value = float(payload.get('confidence', 0.0) or 0.0)
                except (TypeError, ValueError):
                    confidence_value = 0.0

                entry: Dict[str, Any] = {
                    'value': payload.get('value'),
                    'confidence': confidence_value,
                    'source': payload.get('source') or payload.get('origin') or 'user-mapping',
                }

                if payload.get('evidence') is not None:
                    entry['evidence'] = payload.get('evidence')
                if payload.get('notes'):
                    entry['notes'] = payload.get('notes')

                normalized[field_name] = entry

            return normalized

        primary_mapping = _normalize_primary_mapping(
            request.current_mapping,
            valid_fields,
        )

        candidate_configs = determine_specialist_candidates(
            template_fields,
            primary_mapping,
            low_confidence_floor=settings.AI_HANDWRITING_LOW_CONFIDENCE_THRESHOLD,
            allowed_tiers=settings.AI_HANDWRITING_TIERS,
            requested_fields=valid_fields,
        )

        if not candidate_configs:
            operation_metadata = {
                'operation': 'reanalyze',
                'document_id': document.id,
                'template_id': template.id,
                'requested_fields': sanitized_fields,
                'processed_fields': [],
                'resolved_fields': [],
                'missing_fields': missing_fields,
                'ocr_source': ocr_result.get('source', 'unknown'),
                'word_count': ocr_result.get('word_count', 0),
            }

            return {
                'updated_fields': {},
                'message': 'Seçilen alanlar uzman modele yönlendirilemedi.',
                'specialist': {
                    'requested_fields': sanitized_fields,
                    'resolved_fields': [],
                    'missing_fields': missing_fields,
                },
                'operation': operation_metadata,
            }

        interpreter = HandwritingInterpreter(settings.OPENAI_API_KEY)
        specialist_response = interpreter.interpret_fields(
            ocr_result,
            candidate_configs,
            primary_mapping,
            field_hints=relevant_hints or None,
            document_info={
                'document_id': document.id,
                'template_id': template.id,
                'operation': 'reanalyze',
            },
        )

        specialist_mapping = specialist_response.get('field_mappings') or {}

        merged_mappings = merge_field_mappings(
            primary_mapping,
            specialist_mapping,
        )

        def _calculate_status(confidence: float) -> str:
            if confidence >= 0.8:
                return 'high'
            if confidence >= 0.5:
                return 'medium'
            return 'low'

        field_updates: Dict[str, Dict[str, Any]] = {}
        for field_name in valid_fields:
            merged_entry = merged_mappings.get(field_name)
            if not merged_entry:
                continue

            confidence_value = float(merged_entry.get('confidence', 0.0) or 0.0)
            update: Dict[str, Any] = {
                'value': merged_entry.get('value'),
                'confidence': confidence_value,
                'status': _calculate_status(confidence_value),
                'source': merged_entry.get('source', ''),
            }
            if merged_entry.get('alternates'):
                update['alternates'] = merged_entry['alternates']
            if merged_entry.get('notes'):
                update['notes'] = merged_entry['notes']

            field_updates[field_name] = update

        latency_seconds = specialist_response.get('latency_seconds')
        estimated_cost = specialist_response.get('estimated_cost')
        specialist_usage = specialist_response.get('usage')
        specialist_error = specialist_response.get('error')
        specialist_model = specialist_response.get('model_metadata')

        unresolved_fields = [
            field_name
            for field_name in valid_fields
            if field_name not in specialist_mapping
        ]

        operation_metadata = {
            'operation': 'reanalyze',
            'document_id': document.id,
            'template_id': template.id,
            'requested_fields': sanitized_fields,
            'processed_fields': sorted(candidate_configs.keys()),
            'resolved_fields': sorted(specialist_mapping.keys()),
            'unresolved_fields': unresolved_fields,
            'missing_fields': missing_fields,
            'ocr_source': ocr_result.get('source', 'unknown'),
            'word_count': ocr_result.get('word_count', 0),
            'latency_seconds': latency_seconds,
        }

        specialist_info: Dict[str, Any] = {
            'requested_fields': sanitized_fields,
            'resolved_fields': sorted(specialist_mapping.keys()),
            'usage': specialist_usage,
            'latency_seconds': latency_seconds,
            'estimated_cost': estimated_cost,
            'error': specialist_error,
        }

        if unresolved_fields:
            specialist_info['unresolved_fields'] = unresolved_fields
        if missing_fields:
            specialist_info['missing_fields'] = missing_fields
        if specialist_model:
            specialist_info['model'] = specialist_model

        message: str
        if specialist_error:
            message = f"Uzman modeli hatası: {specialist_error}"
        elif field_updates:
            message = f"{len(field_updates)} alan yeniden analiz edildi."
        else:
            message = "Uzman modeli yeni bir sonuç üretmedi."

        return {
            'updated_fields': field_updates,
            'message': message,
            'specialist': specialist_info,
            'operation': operation_metadata,
        }

    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.exception("Yeniden analiz işlemi başarısız oldu: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
                'extraction_rules': request.confirmed_rules,
                'target_fields': request.target_fields if request.target_fields is not None else None
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

    except TemplateNameConflictError as conflict:
        raise HTTPException(status_code=409, detail=str(conflict)) from conflict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Şablon kaydetme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{template_id}/fields", response_model=Dict[str, Any])
async def update_template_fields(
    template_id: int,
    payload: TemplateFieldsUpdate,
    db: Session = Depends(get_db)
):
    """Update template field configuration."""
    try:
        template_manager = TemplateManager(db)
        updates = {'target_fields': payload.target_fields}

        if payload.name is not None:
            updates['name'] = payload.name

        template = template_manager.update_template(
            template_id,
            updates
        )

        if not template:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")

        logger.info("Şablon alanları güncellendi: %s", template_id)

        return {
            'template_id': template.id,
            'field_count': len(payload.target_fields),
            'message': 'Alan ayarları güncellendi'
        }

    except TemplateNameConflictError as conflict:
        raise HTTPException(status_code=409, detail=str(conflict)) from conflict

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Şablon alan güncelleme hatası: %s", str(e))
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

    except TemplateNameConflictError as conflict:
        raise HTTPException(status_code=409, detail=str(conflict)) from conflict

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
