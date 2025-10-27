# -*- coding: utf-8 -*-
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import logging
import os

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./digitalization.db")

# Create engine with UTF-8 support
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False
)

# Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# Database Models
class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    version = Column(String(50), default="1.0")
    target_fields = Column(JSON, nullable=False)  # List of field definitions
    extraction_rules = Column(JSON, nullable=True)  # AI-generated mapping rules
    sample_document_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    fields = relationship("TemplateField", back_populates="template", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="template")
    batch_jobs = relationship("BatchJob", back_populates="template")


class TemplateField(Base):
    __tablename__ = "template_fields"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("templates.id", ondelete="CASCADE"), nullable=False)
    field_name = Column(String(255), nullable=False)
    data_type = Column(String(50), nullable=False)  # text, number, date
    required = Column(Boolean, default=False)
    calculated = Column(Boolean, default=False)
    calculation_rule = Column(String(500), nullable=True)
    regex_hint = Column(String(500), nullable=True)
    ocr_psm = Column(Integer, nullable=True)
    ocr_roi = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, nullable=True, server_default=text("1"))
    auto_learned_type = Column(String(50), nullable=True)
    learning_enabled = Column(Boolean, default=True, nullable=False, server_default=text("1"))
    last_learned_at = Column(DateTime, nullable=True)
    processing_mode = Column(String(50), nullable=False, default="auto", server_default=text("'auto'"))
    llm_tier = Column(String(50), nullable=False, default="standard", server_default=text("'standard'"))
    handwriting_threshold = Column(Float, nullable=True, default=None)
    auto_detected_handwriting = Column(Boolean, nullable=False, default=False, server_default=text("0"))

    # Relationships
    template = relationship("Template", back_populates="fields")
    hints = relationship(
        "TemplateFieldHint",
        back_populates="template_field",
        cascade="all, delete-orphan",
    )
    correction_feedback = relationship("CorrectionFeedback", back_populates="template_field")


class TemplateFieldHint(Base):
    __tablename__ = "template_field_hints"
    __table_args__ = (
        UniqueConstraint(
            "template_field_id",
            "hint_type",
            name="uq_template_field_hints_field_type",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    template_field_id = Column(
        Integer,
        ForeignKey("template_fields.id", ondelete="CASCADE"),
        nullable=False,
    )
    hint_type = Column(String(100), nullable=False)
    hint_payload = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, nullable=True)

    template_field = relationship("TemplateField", back_populates="hints")


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("templates.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), default="processing")  # processing, completed, failed
    total_files = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)
    failed_files = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    template = relationship("Template", back_populates="batch_jobs")
    documents = relationship("Document", back_populates="batch_job")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    batch_job_id = Column(Integer, ForeignKey("batch_jobs.id", ondelete="SET NULL"), nullable=True)
    template_id = Column(Integer, ForeignKey("templates.id", ondelete="SET NULL"), nullable=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    upload_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default="pending")  # pending, processing, completed, failed

    # Relationships
    batch_job = relationship("BatchJob", back_populates="documents")
    template = relationship("Template", back_populates="documents")
    extracted_data = relationship("ExtractedData", back_populates="document", cascade="all, delete-orphan")
    correction_feedback = relationship(
        "CorrectionFeedback",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class CorrectionFeedback(Base):
    __tablename__ = "correction_feedback"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "template_field_id",
            "corrected_value",
            name="uq_correction_feedback_document_field_value",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    template_field_id = Column(Integer, ForeignKey("template_fields.id", ondelete="SET NULL"), nullable=True)
    original_value = Column(Text, nullable=True)
    corrected_value = Column(Text, nullable=False)
    feedback_context = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    applied_at = Column(DateTime, nullable=True)
    created_by = Column(Integer, nullable=True)
    applied_by = Column(Integer, nullable=True)
    applied = Column(Boolean, default=False, nullable=False, server_default=text("0"))

    document = relationship("Document", back_populates="correction_feedback")
    template_field = relationship("TemplateField", back_populates="correction_feedback")


class ExtractedData(Base):
    __tablename__ = "extracted_data"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    field_values = Column(JSON, nullable=False)  # {field_name: value}
    confidence_scores = Column(JSON, nullable=False)  # {field_name: 0.0-1.0}
    validation_status = Column(String(50), default="pending")  # pending, approved, rejected
    validated_at = Column(DateTime, nullable=True)

    # Relationships
    document = relationship("Document", back_populates="extracted_data")


def init_db():
    logger = logging.getLogger(__name__)

    if engine.dialect.name != "sqlite":
        return True

    database_path = engine.url.database

    if not database_path or database_path == ":memory:":
        return True

    # Normalize path to provide accurate feedback to the operator
    normalized_path = os.path.abspath(database_path)

    if os.path.exists(normalized_path):
        return True

    logger.warning(
        "Veritabanı dosyası bulunamadı (%s). Lütfen `alembic upgrade head` komutunu çalıştırın.",
        normalized_path,
    )

    return False


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
