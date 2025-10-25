# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
import os
import subprocess
from pathlib import Path

import pytesseract

from .config import settings
from .database import init_db
from .routes import upload, template, batch, export, diag

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Tesseract configuration
def configure_tesseract() -> None:
    """Ensure Tesseract executable and data paths are configured."""
    tesseract_cmd = settings.TESSERACT_CMD.strip().strip('"')
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd or pytesseract.pytesseract.tesseract_cmd

    tess_path = Path(tesseract_cmd)
    tess_dir = None

    if tess_path.is_file():
        tess_dir = tess_path.parent
    elif tess_path.parts:
        possible_path = Path(os.getenv("PROGRAMFILES", "")) / "Tesseract-OCR" / "tesseract.exe"
        if possible_path.is_file():
            tess_dir = possible_path.parent
            pytesseract.pytesseract.tesseract_cmd = str(possible_path)

    if tess_dir:
        current_path = os.environ.get("PATH", "")
        path_parts = [p for p in current_path.split(os.pathsep) if p]
        if str(tess_dir) not in path_parts:
            path_parts.append(str(tess_dir))
            os.environ["PATH"] = os.pathsep.join(path_parts)

    tessdata_prefix = settings.TESSDATA_PREFIX or (str(tess_dir / "tessdata") if tess_dir else "")
    if tessdata_prefix:
        os.environ["TESSDATA_PREFIX"] = tessdata_prefix

    logger.info("tesseract_cmd = %s", pytesseract.pytesseract.tesseract_cmd)

    try:
        result = subprocess.run(
            [pytesseract.pytesseract.tesseract_cmd, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        logger.info("Tesseract stdout: %s", result.stdout.strip())
        logger.info("Tesseract rc: %s", result.returncode)
    except FileNotFoundError:
        logger.warning("Tesseract executable bulunamadı: %s", pytesseract.pytesseract.tesseract_cmd)
    except Exception as exc:
        logger.exception("Tesseract doğrulaması sırasında hata: %s", exc)


# Create FastAPI app
app = FastAPI(
    title="Dijitalleşme Asistanı API",
    description="Belge dijitalleştirme ve veri çıkarma sistemi",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database and create tables on startup"""
    logger.info("Uygulama başlatılıyor...")

    # Configure Tesseract environment
    configure_tesseract()

    # Initialize database
    init_db()
    logger.info("Veritabanı hazır")

    # Create directories
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Dizinler oluşturuldu")

    logger.info("✅ Dijitalleşme Asistanı API başlatıldı!")


# Health check endpoint
@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "message": "Dijitalleşme Asistanı API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "database": "connected",
        "uploads_dir": str(settings.UPLOAD_DIR),
        "outputs_dir": str(settings.OUTPUT_DIR)
    }


# Include routers
app.include_router(upload.router)
app.include_router(template.router)
app.include_router(batch.router)
app.include_router(export.router)
app.include_router(diag.router)

# Mount static files (for serving uploaded files)
try:
    app.mount(
        "/uploads",
        StaticFiles(directory=str(settings.UPLOAD_DIR)),
        name="uploads"
    )
except RuntimeError:
    # Directory might not exist yet
    pass

try:
    app.mount(
        "/outputs",
        StaticFiles(directory=str(settings.OUTPUT_DIR)),
        name="outputs"
    )
except RuntimeError:
    # Directory might not exist yet
    pass


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {
        "error": "Not Found",
        "detail": "İstenen kaynak bulunamadı",
        "path": str(request.url)
    }


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return {
        "error": "Internal Server Error",
        "detail": "Sunucu hatası oluştu",
        "message": str(exc)
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
