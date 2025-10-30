# -*- coding: utf-8 -*-
from pathlib import Path
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.database import Base, Template, TemplateField  # noqa: E402
from app.core.template_manager import TemplateManager  # noqa: E402


def create_test_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    return TestingSession, engine


def test_update_field_metadata_preserves_field_row_and_updates_json():
    SessionLocal, engine = create_test_session()
    session = SessionLocal()

    try:
        template = Template(name="Test Template", target_fields=[])
        session.add(template)
        session.commit()

        template_field = TemplateField(
            template_id=template.id,
            field_name="invoice_total",
            data_type="text",
            required=False,
            calculated=False,
            enabled=True,
            processing_mode="auto",
            llm_tier="standard",
        )
        session.add(template_field)
        session.commit()

        template.target_fields = [
            {
                'id': template_field.id,
                'field_name': template_field.field_name,
                'data_type': template_field.data_type,
                'required': template_field.required,
            }
        ]
        session.commit()
        session.refresh(template)

        manager = TemplateManager(session)
        updated_field = manager.update_field_metadata(
            template.id,
            template_field.id,
            {'llm_guidance': 'Toplamı kontrol et.'},
        )

        session.refresh(template)

        assert updated_field is not None
        assert updated_field['metadata']['llm_guidance'] == 'Toplamı kontrol et.'
        assert template.target_fields[0]['metadata']['llm_guidance'] == 'Toplamı kontrol et.'

        remaining_fields = session.query(TemplateField).filter(
            TemplateField.template_id == template.id
        ).all()
        assert len(remaining_fields) == 1
        assert remaining_fields[0].id == template_field.id

        cleared_field = manager.update_field_metadata(
            template.id,
            template_field.id,
            {},
        )

        session.refresh(template)

        assert cleared_field is not None
        assert 'metadata' not in template.target_fields[0]

    finally:
        session.close()
        engine.dispose()
