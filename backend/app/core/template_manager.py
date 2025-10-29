# -*- coding: utf-8 -*-
import json
import openpyxl
import logging
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..database import Template, TemplateField
from ..models import TemplateExtractionRules

logger = logging.getLogger(__name__)


class TemplateNameConflictError(Exception):
    def __init__(self, existing_name: str):
        self.existing_name = existing_name
        message = (
            f'"{existing_name}" adlı şablon zaten mevcut. '
            "Lütfen farklı bir isim seçin."
        )
        super().__init__(message)


class TemplateManager:
    """Manages template operations and Excel parsing"""

    def __init__(self, db: Session):
        """
        Initialize template manager

        Args:
            db: Database session
        """
        self.db = db

    @staticmethod
    def _normalize_template_name(name: str) -> str:
        if name is None:
            return ""
        return str(name).strip()

    @classmethod
    def _normalize_template_lookup_key(cls, name: str) -> str:
        return cls._normalize_template_name(name).lower()

    def _get_template_by_name(self, name: str) -> Optional[Template]:
        lookup_key = self._normalize_template_lookup_key(name)

        if not lookup_key:
            return None

        return (
            self.db.query(Template)
            .filter(func.lower(Template.name) == lookup_key)
            .first()
        )

    def _ensure_unique_name(self, name: str, current_id: Optional[int] = None) -> str:
        normalized_name = self._normalize_template_name(name)

        if not normalized_name:
            return normalized_name

        existing = self._get_template_by_name(normalized_name)

        if existing and existing.id != current_id:
            raise TemplateNameConflictError(existing.name)

        return normalized_name

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
            'amount', 'price', 'quantity', 'total', 'sayı'
        ]
        if any(keyword in field_lower for keyword in number_keywords):
            return 'number'

        # Default to text
        return 'text'

    def _normalize_rules(
        self,
        extraction_rules: Optional[Union[TemplateExtractionRules, Dict[str, Any]]]
    ) -> Dict[str, Any]:
        if isinstance(extraction_rules, TemplateExtractionRules):
            return extraction_rules.dict()
        if isinstance(extraction_rules, dict):
            return {
                key: value
                for key, value in extraction_rules.items()
                if value is not None
            }
        return {}

    @staticmethod
    def _to_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value

        if value in (None, ""):
            return default

        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "1", "yes", "on"}:
                return True
            if lowered in {"false", "0", "no", "off"}:
                return False

        return bool(value)

    @staticmethod
    def _normalize_ocr_psm(value: Any) -> Optional[int]:
        if value in (None, "", "null", "None"):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning("OCR PSM değeri sayı olarak parse edilemedi: %s", value)
            return None

    @staticmethod
    def _normalize_ocr_roi(value: Any) -> Optional[str]:
        if value in (None, "", "null", "None"):
            return None

        if isinstance(value, str):
            stripped = value.strip()
            if stripped.lower() in {"null", "none", ""}:
                return None
            return stripped

        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            logger.warning("OCR ROI değeri serileştirilemedi, metne çevriliyor: %s", value)
            return str(value)

    @staticmethod
    def _normalize_processing_mode(value: Any) -> str:
        if value in (None, "", "null", "None"):
            return "auto"

        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or "auto"

        return str(value).strip().lower() or "auto"

    @staticmethod
    def _normalize_llm_tier(value: Any) -> str:
        if value in (None, "", "null", "None"):
            return "standard"

        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or "standard"

        return str(value).strip().lower() or "standard"

    @staticmethod
    def _normalize_handwriting_threshold(value: Any) -> Optional[float]:
        if value in (None, "", "null", "None"):
            return None

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            logger.warning(
                "El yazısı eşiği değeri sayı olarak parse edilemedi: %s",
                value,
            )
            return None

        if numeric < 0:
            numeric = 0.0
        if numeric > 1:
            numeric = 1.0

        return numeric

    @staticmethod
    def _normalize_metadata(metadata: Any) -> Dict[str, Any]:
        if not isinstance(metadata, dict):
            if metadata not in (None, "", {}):
                logger.warning(
                    "Şablon alanı metadata bilgisi sözlük değil: tür=%s", type(metadata)
                )
            return {}

        def sanitize(value: Any, depth: int = 0) -> Any:
            if depth > 5:
                logger.debug("Metadata derinliği sınırı aşıldı, değer kırpıldı.")
                return None

            if isinstance(value, (str, int, float, bool)) or value is None:
                return value

            if isinstance(value, list):
                return [sanitize(item, depth + 1) for item in value]

            if isinstance(value, dict):
                sanitized_dict: Dict[str, Any] = {}
                for key, item in value.items():
                    sanitized_value = sanitize(item, depth + 1)
                    sanitized_dict[str(key)] = sanitized_value
                return sanitized_dict

            return str(value)

        return {str(key): sanitize(raw_value) for key, raw_value in metadata.items()}

    def _normalize_field(self, field_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(field_data, dict):
            return None

        normalized = dict(field_data)

        field_name = str(normalized.get('field_name', '')).strip()
        if not field_name:
            return None

        normalized['field_name'] = field_name
        data_type = normalized.get('data_type', 'text') or 'text'
        normalized['data_type'] = str(data_type).lower()
        normalized['required'] = self._to_bool(normalized.get('required'), False)
        normalized['calculated'] = self._to_bool(normalized.get('calculated'), False)
        normalized['enabled'] = self._to_bool(normalized.get('enabled'), True)
        normalized['calculation_rule'] = normalized.get('calculation_rule') or None
        normalized['regex_hint'] = normalized.get('regex_hint') or None
        normalized['ocr_psm'] = self._normalize_ocr_psm(normalized.get('ocr_psm'))
        normalized['ocr_roi'] = self._normalize_ocr_roi(normalized.get('ocr_roi'))
        normalized['processing_mode'] = self._normalize_processing_mode(
            normalized.get('processing_mode')
        )
        normalized['llm_tier'] = self._normalize_llm_tier(
            normalized.get('llm_tier')
        )
        normalized['handwriting_threshold'] = self._normalize_handwriting_threshold(
            normalized.get('handwriting_threshold')
        )
        normalized['auto_detected_handwriting'] = self._to_bool(
            normalized.get('auto_detected_handwriting'),
            False,
        )
        normalized['metadata'] = self._normalize_metadata(normalized.get('metadata'))

        return normalized

    def _normalize_fields(self, fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized_fields: List[Dict[str, Any]] = []

        for field_data in fields or []:
            normalized = self._normalize_field(field_data)
            if normalized:
                normalized_fields.append(normalized)

        return normalized_fields

    def create_template(
        self,
        name: str,
        fields: List[Dict[str, Any]],
        sample_doc_path: Optional[str] = None,
        extraction_rules: Optional[Union[TemplateExtractionRules, Dict[str, Any]]] = None
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
            normalized_name = self._ensure_unique_name(name)
            normalized_fields = self._normalize_fields(fields)

            # Create template
            template = Template(
                name=normalized_name,
                target_fields=normalized_fields,
                extraction_rules=self._normalize_rules(extraction_rules),
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
                    ocr_psm=field_data.get('ocr_psm'),
                    ocr_roi=field_data.get('ocr_roi'),
                    enabled=field_data.get('enabled', True),
                    processing_mode=field_data.get('processing_mode', 'auto'),
                    llm_tier=field_data.get('llm_tier', 'standard'),
                    handwriting_threshold=field_data.get('handwriting_threshold'),
                    auto_detected_handwriting=field_data.get('auto_detected_handwriting', False),
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
                    normalized_fields = self._normalize_fields(value)
                    self.db.query(TemplateField).filter(
                        TemplateField.template_id == template_id
                    ).delete(synchronize_session=False)

                    for field_data in normalized_fields:
                        template_field = TemplateField(
                            template_id=template.id,
                            field_name=field_data['field_name'],
                            data_type=field_data.get('data_type', 'text'),
                            required=field_data.get('required', False),
                            calculated=field_data.get('calculated', False),
                            calculation_rule=field_data.get('calculation_rule'),
                            regex_hint=field_data.get('regex_hint'),
                            ocr_psm=field_data.get('ocr_psm'),
                            ocr_roi=field_data.get('ocr_roi'),
                            enabled=field_data.get('enabled', True),
                            processing_mode=field_data.get('processing_mode', 'auto'),
                            llm_tier=field_data.get('llm_tier', 'standard'),
                            handwriting_threshold=field_data.get('handwriting_threshold'),
                            auto_detected_handwriting=field_data.get('auto_detected_handwriting', False),
                        )
                        self.db.add(template_field)

                    template.target_fields = normalized_fields
                    continue

                if key == 'extraction_rules':
                    setattr(template, key, self._normalize_rules(value))
                    continue

                if key == 'name':
                    template.name = self._ensure_unique_name(value, current_id=template.id)
                    continue

                if hasattr(template, key):
                    setattr(template, key, value)

            self.db.commit()
            self.db.refresh(template)

            logger.info(f"Şablon güncellendi: {template_id}")
            return template

        except TemplateNameConflictError:
            self.db.rollback()
            raise

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

            template.extraction_rules = self._normalize_rules(extraction_rules)
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
