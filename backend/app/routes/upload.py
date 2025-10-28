# -*- coding: utf-8 -*-
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
import shutil
from pathlib import Path
from typing import Dict, Any
import logging

from ..config import settings
from ..database import get_db, Document
from ..utils.audit_logger import AuditLogger
from ..models import DocumentResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])


def validate_file(file: UploadFile, allowed_extensions: set) -> bool:
    """Validate file type and size"""
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in allowed_extensions:
        return False

    return True


@router.post("/sample", response_model=Dict[str, Any])
async def upload_sample_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload sample source document (PDF/Image)

    Returns:
        document_id and preview_url
    """
    try:
        # Validate file
        if not validate_file(file, settings.ALLOWED_EXTENSIONS):
            raise HTTPException(
                status_code=400,
                detail=f"Geçersiz dosya türü. İzin verilenler: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )

        # Create unique filename
        timestamp = Path(file.filename).stem
        file_ext = Path(file.filename).suffix
        unique_filename = f"sample_{timestamp}_{file.filename}"

        # Save file
        file_path = settings.UPLOAD_DIR / unique_filename

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Create document record
        document = Document(
            filename=file.filename,
            file_path=str(file_path),
            status="pending"
        )

        db.add(document)
        db.commit()
        db.refresh(document)

        AuditLogger(db).log_event(
            "upload",
            "document",
            document.id,
            metadata={
                "filename": file.filename,
                "destination": "sample",
            },
        )

        logger.info(f"Örnek belge yüklendi: {document.id}")

        return {
            "document_id": document.id,
            "filename": file.filename,
            "preview_url": f"/uploads/{unique_filename}",
            "message": "Belge başarıyla yüklendi"
        }

    except Exception as e:
        logger.error(f"Belge yükleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/template", response_model=Dict[str, Any])
async def upload_template_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload Excel template file

    Parses columns and returns field definitions
    """
    try:
        # Validate file
        if not validate_file(file, settings.ALLOWED_TEMPLATE_EXTENSIONS):
            raise HTTPException(
                status_code=400,
                detail=f"Geçersiz şablon dosyası. İzin verilenler: {', '.join(settings.ALLOWED_TEMPLATE_EXTENSIONS)}"
            )

        # Save file
        timestamp = Path(file.filename).stem
        file_ext = Path(file.filename).suffix
        unique_filename = f"template_{timestamp}_{file.filename}"

        file_path = settings.UPLOAD_DIR / unique_filename

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Parse Excel template
        from ..core.template_manager import TemplateManager
        template_manager = TemplateManager(db)

        fields = template_manager.parse_excel_template(str(file_path))

        if not fields:
            raise HTTPException(
                status_code=400,
                detail="Excel şablonu parse edilemedi veya alan bulunamadı"
            )

        logger.info(f"Excel şablonu yüklendi: {len(fields)} alan bulundu")

        AuditLogger(db).log_event(
            "upload",
            "template_file",
            None,
            metadata={
                "filename": file.filename,
                "parsed_fields": len(fields),
            },
        )

        return {
            "template_file": unique_filename,
            "fields": fields,
            "field_count": len(fields),
            "message": "Şablon başarıyla yüklendi"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Şablon yükleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch", response_model=Dict[str, Any])
async def upload_batch_files(
    files: list[UploadFile] = File(...),
    template_id: int = None,
    db: Session = Depends(get_db)
):
    """
    Upload multiple files for batch processing

    Returns:
        List of uploaded file IDs
    """
    try:
        if len(files) > settings.MAX_BATCH_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Maksimum {settings.MAX_BATCH_SIZE} dosya yüklenebilir"
            )

        uploaded_docs = []
        audit_logger = AuditLogger(db)

        for file in files:
            # Validate file
            if not validate_file(file, settings.ALLOWED_EXTENSIONS):
                logger.warning(f"Geçersiz dosya atlandı: {file.filename}")
                continue

            # Save file
            timestamp = Path(file.filename).stem
            file_ext = Path(file.filename).suffix
            unique_filename = f"batch_{timestamp}_{file.filename}"

            file_path = settings.UPLOAD_DIR / unique_filename

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Create document record
            document = Document(
                filename=file.filename,
                file_path=str(file_path),
                template_id=template_id,
                status="pending"
            )

            db.add(document)
            db.commit()
            db.refresh(document)

            audit_logger.log_event(
                "upload",
                "document",
                document.id,
                metadata={
                    "filename": file.filename,
                    "destination": "batch",
                    "template_id": template_id,
                },
            )

            uploaded_docs.append({
                "document_id": document.id,
                "filename": file.filename
            })

        logger.info(f"Toplu yükleme: {len(uploaded_docs)} dosya")

        return {
            "uploaded_count": len(uploaded_docs),
            "documents": uploaded_docs,
            "message": f"{len(uploaded_docs)} dosya başarıyla yüklendi"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Toplu yükleme hatası: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
