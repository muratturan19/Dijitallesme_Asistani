# -*- coding: utf-8 -*-
from pathlib import Path
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from app.core.template_learning_service import TemplateLearningService
from app.database import Base, CorrectionFeedback, Document, Template, TemplateField


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    TestingSession = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _prepare_template_environment(db: Session):
    template = Template(name="Invoice", target_fields=[], extraction_rules={})
    db.add(template)
    db.flush()

    field = TemplateField(
        template_id=template.id,
        field_name="InvoiceDate",
        data_type="date",
        required=False,
    )
    document = Document(
        template_id=template.id,
        filename="sample.pdf",
        file_path="/tmp/sample.pdf",
    )

    db.add_all([field, document])
    db.flush()
    db.commit()

    return template, field, document


def test_record_correction_persists_feedback(db_session: Session):
    _, field, document = _prepare_template_environment(db_session)
    service = TemplateLearningService(db_session)

    feedback = service.record_correction(
        document_id=document.id,
        template_field_id=field.id,
        original_value="2023-03-01",
        corrected_value="2023-03-05",
        context={"reason": "typo"},
        created_by=42,
    )

    stored = (
        db_session.query(CorrectionFeedback)
        .filter(CorrectionFeedback.id == feedback.id)
        .one()
    )

    assert stored.corrected_value == "2023-03-05"
    assert stored.feedback_context == {"reason": "typo"}
    assert stored.created_by == 42


def test_generate_field_hint_creates_learning_hint(db_session: Session):
    _, field, document = _prepare_template_environment(db_session)
    service = TemplateLearningService(db_session)

    service.record_correction(
        document_id=document.id,
        template_field_id=field.id,
        corrected_value="12.03.2024",
    )
    service.record_correction(
        document_id=document.id,
        template_field_id=field.id,
        corrected_value="05.11.2023",
    )

    hint = service.generate_field_hint(field.id)

    assert hint is not None
    assert hint.hint_payload["type_hint"] == "date"
    regex_patterns = hint.hint_payload.get("regex_patterns", [])
    assert regex_patterns and any("\\d{1,2}" in pattern["pattern"] for pattern in regex_patterns)

    db_session.refresh(field)
    assert field.auto_learned_type == "date"
    assert field.last_learned_at is not None

    # Running again should update the same hint instead of creating duplicates
    hint_again = service.generate_field_hint(field.id)
    assert hint_again.id == hint.id

