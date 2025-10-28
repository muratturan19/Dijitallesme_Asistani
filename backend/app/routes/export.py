# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import logging
from pathlib import Path
import re

from ..config import settings
from ..database import get_db, BatchJob, Document, ExtractedData, Template
from ..core.export_manager import ExportManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/batch/{batch_job_id}")
async def export_batch_results(
    batch_job_id: int,
    db: Session = Depends(get_db)
):
    """
    Export batch job results to Excel

    Returns Excel file with all extracted data
    """
    try:
        # Get batch job
        batch_job = db.query(BatchJob).filter(
            BatchJob.id == batch_job_id
        ).first()

        if not batch_job:
            raise HTTPException(status_code=404, detail="Toplu işlem bulunamadı")

        # Get template
        template = db.query(Template).filter(
            Template.id == batch_job.template_id
        ).first()

        if not template:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")

        # Get all extracted data for this batch
        batch_documents = db.query(Document).filter(
            Document.batch_job_id == batch_job_id,
            Document.status == "completed"
        ).all()

        if not batch_documents:
            raise HTTPException(
                status_code=404,
                detail="Dışa aktarılacak veri bulunamadı"
            )

        # Collect all completed documents for this template to include previous runs
        all_documents = db.query(Document).filter(
            Document.template_id == template.id,
            Document.status == "completed"
        ).order_by(Document.upload_date.asc()).all()

        extracted_data_list: List[Dict[str, Any]] = []

        for doc in all_documents:
            extracted_data = db.query(ExtractedData).filter(
                ExtractedData.document_id == doc.id
            ).first()

            if extracted_data:
                extracted_data_list.append({
                    'document_name': doc.filename,
                    'field_values': extracted_data.field_values,
                    'confidence_scores': extracted_data.confidence_scores
                })

        # Export to Excel
        export_manager = ExportManager(settings.OUTPUT_DIR)

        safe_template_name = re.sub(r"[^0-9A-Za-zğüşöçıİĞÜŞÖÇ]+", "_", template.name).strip("_") or "template"
        filename = f"template_{template.id}_{safe_template_name}_results.xlsx"
        excel_path = export_manager.export_to_excel(
            template.target_fields,
            extracted_data_list,
            filename,
            metadata={
                "Toplu İş ID": batch_job_id,
                "Şablon ID": template.id,
                "Şablon Adı": template.name,
                "Toplam Belge": len(extracted_data_list)
            }
        )

        logger.info(f"Excel dışa aktarıldı: {excel_path}")

        # Return file
        return FileResponse(
            path=excel_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dışa aktarma hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/validation/{batch_job_id}")
async def export_validation_report(
    batch_job_id: int,
    db: Session = Depends(get_db)
):
    """
    Export validation report with confidence scores

    Returns Excel file with validation details
    """
    try:
        # Get batch job
        batch_job = db.query(BatchJob).filter(
            BatchJob.id == batch_job_id
        ).first()

        if not batch_job:
            raise HTTPException(status_code=404, detail="Toplu işlem bulunamadı")

        # Get all documents with extracted data
        documents = db.query(Document).filter(
            Document.batch_job_id == batch_job_id
        ).all()

        if not documents:
            raise HTTPException(
                status_code=404,
                detail="Dışa aktarılacak veri bulunamadı"
            )

        extracted_data_list = []

        for doc in documents:
            extracted_data = db.query(ExtractedData).filter(
                ExtractedData.document_id == doc.id
            ).first()

            if extracted_data:
                extracted_data_list.append({
                    'document_name': doc.filename,
                    'field_values': extracted_data.field_values,
                    'confidence_scores': extracted_data.confidence_scores,
                    'validation_status': extracted_data.validation_status
                })

        # Export validation report
        export_manager = ExportManager(settings.OUTPUT_DIR)

        filename = f"batch_{batch_job_id}_validation.xlsx"
        excel_path = export_manager.export_validation_report(
            extracted_data_list,
            filename
        )

        logger.info(f"Doğrulama raporu dışa aktarıldı: {excel_path}")

        # Return file
        return FileResponse(
            path=excel_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rapor dışa aktarma hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/template/{template_id}")
async def export_template_excel(
    template_id: int,
    db: Session = Depends(get_db)
):
    """
    Export empty Excel template based on template definition

    Returns Excel file with headers only
    """
    try:
        # Get template
        template = db.query(Template).filter(
            Template.id == template_id
        ).first()

        if not template:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")

        # Create template Excel
        export_manager = ExportManager(settings.OUTPUT_DIR)

        filename = f"template_{template_id}_{template.name}.xlsx"
        excel_path = export_manager.create_template_excel(
            template.target_fields,
            filename
        )

        logger.info(f"Şablon Excel oluşturuldu: {excel_path}")

        # Return file
        return FileResponse(
            path=excel_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Şablon dışa aktarma hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/document/{document_id}")
async def export_single_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    """
    Export single document results to Excel

    Returns Excel file with single document data
    """
    try:
        # Get document
        document = db.query(Document).filter(
            Document.id == document_id
        ).first()

        if not document:
            raise HTTPException(status_code=404, detail="Belge bulunamadı")

        # Get template
        template = db.query(Template).filter(
            Template.id == document.template_id
        ).first()

        if not template:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")

        # Get extracted data
        extracted_data = db.query(ExtractedData).filter(
            ExtractedData.document_id == document_id
        ).first()

        if not extracted_data:
            raise HTTPException(
                status_code=404,
                detail="Çıkarılmış veri bulunamadı"
            )

        extracted_data_list = [{
            'document_name': document.filename,
            'field_values': extracted_data.field_values,
            'confidence_scores': extracted_data.confidence_scores
        }]

        # Export to Excel
        export_manager = ExportManager(settings.OUTPUT_DIR)

        filename = f"document_{document_id}_results.xlsx"
        excel_path = export_manager.export_to_excel(
            template.target_fields,
            extracted_data_list,
            filename
        )

        logger.info(f"Belge Excel'e aktarıldı: {excel_path}")

        # Return file
        return FileResponse(
            path=excel_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Belge dışa aktarma hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
