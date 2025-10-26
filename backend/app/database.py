# -*- coding: utf-8 -*-
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
    Text,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
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
    name = Column(String(255), nullable=False)
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

    # Relationships
    template = relationship("Template", back_populates="fields")


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


# Create all tables
def _ensure_column(conn, table: str, column: str, ddl: str) -> None:
    """Ensure the given column exists in the SQLite table."""

    result = conn.execute(text(f"PRAGMA table_info({table});"))
    columns = {row[1] for row in result}

    if column not in columns:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl};"))


def init_db():
    Base.metadata.create_all(bind=engine)

    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            _ensure_column(
                conn,
                "template_fields",
                "regex_hint",
                "regex_hint VARCHAR(500) NULL",
            )
            _ensure_column(
                conn,
                "template_fields",
                "ocr_psm",
                "ocr_psm INTEGER NULL",
            )
            _ensure_column(
                conn,
                "template_fields",
                "ocr_roi",
                "ocr_roi TEXT NULL",
            )
            _ensure_column(
                conn,
                "template_fields",
                "enabled",
                "enabled BOOLEAN NULL DEFAULT 1",
            )


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
