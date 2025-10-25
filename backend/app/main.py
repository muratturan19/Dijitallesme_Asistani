# -*- coding: utf-8 -*-
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import logging
from pathlib import Path

from .config import settings
from .database import init_db
from .routes import upload, template, batch, export

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
