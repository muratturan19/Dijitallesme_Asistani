# -*- coding: utf-8 -*-
import openpyxl
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from sqlalchemy.orm import Session
from ..database import Template, TemplateField

logger = logging.getLogger(__name__)


class TemplateManager:
    """Manages template operations and Excel parsing"""

    def __init__(self, db: Session):
        """
        Initialize template manager

        Args:
            db: Database session
        """
        self.db = db

    def parse_excel_template(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Parse Excel template and extract column names/structure

        Args:
            file_path: Path to Excel file

        Returns:
            List of field definitions
        """
        try:
            # Load workbook
            wb = openpyxl.load_workbook(file_path, data_only=True)
            ws = wb.active

            # Get header row (first row)
            headers = []
            for cell in ws[1]:
                if cell.value:
                    headers.append(str(cell.value).strip())

            if not headers:
                logger.error("Excel dosyasında başlık satırı bulunamadı")
                return []

            # Create field definitions
            fields = []
            for header in headers:
                # Try to infer data type from header name
                data_type = self._infer_data_type(header)

                field = {
                    'field_name': header,
                    'data_type': data_type,
                    'required': False,
                    'calculated': False,
                    'calculation_rule': None,
                    'regex_hint': None,
                    'ocr_psm': None,
                    'ocr_roi': None,
                    'enabled': True
                }

                fields.append(field)

            logger.info(f"Excel şablonu parse edildi: {len(fields)} alan bulundu")
            return fields

        except Exception as e:
            logger.error(f"Excel parse hatası {file_path}: {str(e)}")
            return []

    def _infer_data_type(self, field_name: str) -> str:
        """
        Infer data type from field name

        Args:
            field_name: Field name

        Returns:
            Data type: "text", "number", or "date"
        """
        field_lower = field_name.lower()

        # Date patterns
        date_keywords = ['tarih', 'date', 'gün', 'ay', 'yıl', 'saat']
        if any(keyword in field_lower for keyword in date_keywords):
            return 'date'

        # Number patterns
        number_keywords = [
            'tutar', 'fiyat', 'miktar', 'adet', 'toplam', 'kdv',
            'amount', 'price', 'quantity', 'total', 'sayı', 'no'
        ]
        if any(keyword in field_lower for keyword in number_keywords):
            return 'number'

        # Default to text
        return 'text'

    def create_template(
        self,
        name: str,
        fields: List[Dict[str, Any]],
        sample_doc_path: Optional[str] = None,
        extraction_rules: Optional[Dict[str, Any]] = None
    ) -> Template:
        """
        Create new template in database

        Args:
            name: Template name
            fields: Field definitions
            sample_doc_path: Path to sample document
            extraction_rules: AI-generated extraction rules

        Returns:
            Created Template object
        """
        try:
            normalized_fields = []
            for field_data in fields:
                normalized_fields.append({
                    **field_data,
                    'enabled': field_data.get('enabled', True)
                })

            # Create template
            template = Template(
                name=name,
                target_fields=normalized_fields,
                extraction_rules=extraction_rules or {},
                sample_document_path=sample_doc_path
            )

            self.db.add(template)
            self.db.commit()
            self.db.refresh(template)

            # Create template fields
            for field_data in normalized_fields:
                template_field = TemplateField(
                    template_id=template.id,
                    field_name=field_data['field_name'],
                    data_type=field_data['data_type'],
                    required=field_data.get('required', False),
                    calculated=field_data.get('calculated', False),
                    calculation_rule=field_data.get('calculation_rule'),
                    regex_hint=field_data.get('regex_hint'),
                    ocr_psm=str(field_data.get('ocr_psm')) if field_data.get('ocr_psm') is not None else None,
                    ocr_roi=field_data.get('ocr_roi'),
                    enabled=field_data.get('enabled', True)
                )
                self.db.add(template_field)

            self.db.commit()

            logger.info(f"Şablon oluşturuldu: {name} (ID: {template.id})")
            return template

        except Exception as e:
            self.db.rollback()
            logger.error(f"Şablon oluşturma hatası: {str(e)}")
            raise

    def get_template(self, template_id: int) -> Optional[Template]:
        """
        Get template by ID

        Args:
            template_id: Template ID

        Returns:
            Template object or None
        """
        try:
            template = self.db.query(Template).filter(
                Template.id == template_id
            ).first()

            return template

        except Exception as e:
            logger.error(f"Şablon getirme hatası: {str(e)}")
            return None

    def get_all_templates(self) -> List[Template]:
        """
        Get all templates

        Returns:
            List of Template objects
        """
        try:
            templates = self.db.query(Template).order_by(
                Template.created_at.desc()
            ).all()

            return templates

        except Exception as e:
            logger.error(f"Şablon listesi getirme hatası: {str(e)}")
            return []

    def update_template(
        self,
        template_id: int,
        updates: Dict[str, Any]
    ) -> Optional[Template]:
        """
        Update template

        Args:
            template_id: Template ID
            updates: Fields to update

        Returns:
            Updated Template object or None
        """
        try:
            template = self.get_template(template_id)

            if not template:
                logger.error(f"Şablon bulunamadı: {template_id}")
                return None

            # Update fields
            for key, value in updates.items():
                if key == 'target_fields' and isinstance(value, list):
                    normalized_fields = []
                    self.db.query(TemplateField).filter(
                        TemplateField.template_id == template_id
                    ).delete(synchronize_session=False)

                    for field_data in value:
                        field_data = {
                            **field_data,
                            'enabled': field_data.get('enabled', True)
                        }
                        normalized_fields.append(field_data)

                        template_field = TemplateField(
                            template_id=template.id,
                            field_name=field_data['field_name'],
                            data_type=field_data.get('data_type', 'text'),
                            required=field_data.get('required', False),
                            calculated=field_data.get('calculated', False),
                            calculation_rule=field_data.get('calculation_rule'),
                            regex_hint=field_data.get('regex_hint'),
                            ocr_psm=str(field_data.get('ocr_psm')) if field_data.get('ocr_psm') is not None else None,
                            ocr_roi=field_data.get('ocr_roi'),
                            enabled=field_data.get('enabled', True)
                        )
                        self.db.add(template_field)

                    template.target_fields = normalized_fields
                    continue

                if hasattr(template, key):
                    setattr(template, key, value)

            self.db.commit()
            self.db.refresh(template)

            logger.info(f"Şablon güncellendi: {template_id}")
            return template

        except Exception as e:
            self.db.rollback()
            logger.error(f"Şablon güncelleme hatası: {str(e)}")
            return None

    def delete_template(self, template_id: int) -> bool:
        """
        Delete template

        Args:
            template_id: Template ID

        Returns:
            True if successful, False otherwise
        """
        try:
            template = self.get_template(template_id)

            if not template:
                logger.error(f"Şablon bulunamadı: {template_id}")
                return False

            self.db.delete(template)
            self.db.commit()

            logger.info(f"Şablon silindi: {template_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Şablon silme hatası: {str(e)}")
            return False

    def save_extraction_rules(
        self,
        template_id: int,
        extraction_rules: Dict[str, Any]
    ) -> bool:
        """
        Save AI-generated extraction rules to template

        Args:
            template_id: Template ID
            extraction_rules: Extraction rules from AI

        Returns:
            True if successful, False otherwise
        """
        try:
            template = self.get_template(template_id)

            if not template:
                return False

            template.extraction_rules = extraction_rules
            self.db.commit()

            logger.info(f"Çıkarma kuralları kaydedildi: {template_id}")
            return True

        except Exception as e:
            self.db.rollback()
            logger.error(f"Kural kaydetme hatası: {str(e)}")
            return False

    def get_template_stats(self, template_id: int) -> Dict[str, Any]:
        """
        Get template usage statistics

        Args:
            template_id: Template ID

        Returns:
            Statistics dictionary
        """
        try:
            from ..database import Document, ExtractedData

            template = self.get_template(template_id)

            if not template:
                return {}

            # Count documents
            total_docs = self.db.query(Document).filter(
                Document.template_id == template_id
            ).count()

            # Count completed
            completed_docs = self.db.query(Document).filter(
                Document.template_id == template_id,
                Document.status == 'completed'
            ).count()

            # Count validated
            validated = self.db.query(ExtractedData).join(Document).filter(
                Document.template_id == template_id,
                ExtractedData.validation_status == 'approved'
            ).count()

            stats = {
                'template_id': template_id,
                'template_name': template.name,
                'total_documents': total_docs,
                'completed_documents': completed_docs,
                'validated_documents': validated,
                'success_rate': (completed_docs / total_docs * 100) if total_docs > 0 else 0
            }

            return stats

        except Exception as e:
            logger.error(f"İstatistik hatası: {str(e)}")
            return {}
