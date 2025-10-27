# -*- coding: utf-8 -*-
import os
import shutil
from typing import Tuple
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()


def _get_env_float(name: str, default: float) -> float:
    """Safely parse float values from environment variables."""

    value = os.getenv(name)
    if value in (None, ""):
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_env_int(name: str, default: int) -> int:
    """Safely parse integer values from environment variables."""

    value = os.getenv(name)
    if value in (None, ""):
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Settings:
    """Application configuration settings"""

    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5")
    AI_PRIMARY_MODEL: str = os.getenv("AI_PRIMARY_MODEL", OPENAI_MODEL)
    AI_PRIMARY_TEMPERATURE: float = _get_env_float("AI_PRIMARY_TEMPERATURE", 0.8)
    AI_PRIMARY_CONTEXT_WINDOW: int = _get_env_int("AI_PRIMARY_CONTEXT_WINDOW", 2000)

    AI_HANDWRITING_MODEL: str = os.getenv("AI_HANDWRITING_MODEL", "gpt-4.1-handwriting")
    AI_HANDWRITING_TEMPERATURE: float = _get_env_float("AI_HANDWRITING_TEMPERATURE", 0.3)
    AI_HANDWRITING_CONTEXT_WINDOW: int = _get_env_int("AI_HANDWRITING_CONTEXT_WINDOW", 4000)
    AI_HANDWRITING_LOW_CONFIDENCE_THRESHOLD: float = _get_env_float(
        "AI_HANDWRITING_LOW_CONFIDENCE_THRESHOLD", 0.55
    )
    AI_HANDWRITING_MAX_WORKERS: int = _get_env_int("AI_HANDWRITING_MAX_WORKERS", 2)
    AI_HANDWRITING_TIERS: Tuple[str, ...] = tuple(
        tier.strip().lower()
        for tier in os.getenv("AI_HANDWRITING_TIERS", "handwriting,guided").split(",")
        if tier.strip()
    )

    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./digitalization.db")

    # Tesseract Configuration
    TESSERACT_CMD: str = os.getenv("TESSERACT_CMD", "tesseract")
    TESSDATA_PREFIX: str = os.getenv("TESSDATA_PREFIX", "")
    TESSERACT_LANG: str = "tur+eng"  # Turkish + English

    # File Upload Configuration
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
    MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
    ALLOWED_EXTENSIONS: set = {".pdf", ".jpg", ".jpeg", ".png", ".xlsx", ".xls", ".csv"}
    ALLOWED_TEMPLATE_EXTENSIONS: set = {".xlsx", ".xls", ".csv"}

    # Directory Configuration
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOAD_DIR: Path = BASE_DIR / os.getenv("UPLOAD_DIR", "uploads")
    OUTPUT_DIR: Path = BASE_DIR / os.getenv("OUTPUT_DIR", "outputs")
    TEMP_DIR: Path = UPLOAD_DIR / "temp"

    # CORS Configuration
    CORS_ORIGINS: list = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ]

    # Batch Processing
    MAX_BATCH_SIZE: int = 100

    def __init__(self):
        """Create necessary directories on initialization"""
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.TEMP_DIR.mkdir(parents=True, exist_ok=True)


# Create settings instance
settings = Settings()


# Validation
def validate_config():
    """Validate critical configuration"""
    if not settings.OPENAI_API_KEY:
        print("⚠️  UYARI: OPENAI_API_KEY ayarlanmamış. AI özellikleri çalışmayacak.")

    tesseract_cmd = settings.TESSERACT_CMD.strip().strip('"')
    cmd_path = Path(tesseract_cmd)
    if cmd_path.is_file():
        exists = cmd_path.exists()
    else:
        exists = shutil.which(tesseract_cmd) is not None

    if not exists and tesseract_cmd not in {"", "tesseract"}:
        print(f"⚠️  UYARI: Tesseract bulunamadı: {settings.TESSERACT_CMD}")
        print("   Tesseract'ı yükleyin: https://github.com/tesseract-ocr/tesseract")

    return True


# Run validation on import
validate_config()
