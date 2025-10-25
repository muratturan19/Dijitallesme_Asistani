# -*- coding: utf-8 -*-
import json
import logging
import re
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - prefer modern OpenAI client
    from openai import OpenAI, AuthenticationError, OpenAIError
except ImportError:  # pragma: no cover - fallback for legacy client
    OpenAI = None  # type: ignore
    import openai  # type: ignore

    try:
        from openai.error import AuthenticationError, OpenAIError  # type: ignore
    except ImportError:  # pragma: no cover - final fallback
        AuthenticationError = Exception
        OpenAIError = Exception
else:
    import openai  # type: ignore

logger = logging.getLogger(__name__)


class AIFieldMapper:
    """Uses OpenAI GPT-4 to intelligently map extracted text to template fields"""

    def __init__(self, api_key: str, model: str = "gpt-4"):
        """
        Initialize AI field mapper

        Args:
            api_key: OpenAI API key
            model: Model name (default: gpt-4)
        """
        self.api_key = api_key
        self.model = model
        self._has_valid_api_key = bool(api_key and api_key.strip())

        self._client = None
        if self._has_valid_api_key:
            if OpenAI is not None:
                # Modern OpenAI client (>=1.0)
                self._client = OpenAI(api_key=api_key)
            else:
                # Legacy client (<1.0)
                openai.api_key = api_key

        if not self._has_valid_api_key:
            logger.error(
                "OpenAI API anahtarı ayarlanmamış veya boş. AI eşleme işlemi yapılamayacak."
            )

    def map_fields(
        self,
        ocr_text: str,
        template_fields: List[Dict[str, Any]],
        ocr_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Map OCR extracted text to template fields using AI

        Args:
            ocr_text: Full extracted text from OCR
            template_fields: List of target field definitions
            ocr_data: Optional detailed OCR data with bounding boxes

        Returns:
            Dictionary with field mappings and confidence scores
        """
        if not self._has_valid_api_key:
            return self._create_empty_mapping(
                template_fields,
                "OpenAI API anahtarı ayarlanmamış veya geçersiz."
            )

        try:
            # Build prompt for GPT-4
            regex_hits = self._pre_detect_fields(ocr_text)
            prompt = self._build_mapping_prompt(
                ocr_text,
                template_fields,
                regex_hits=regex_hits if regex_hits else None
            )

            # Call OpenAI API (supports both legacy and modern clients)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Sen bir belge analiz uzmanısın. Görevi, OCR ile çıkarılan "
                        "metinden belirli alanları tespit etmek ve değerlerini bulmaktır. "
                        "Cevaplarını JSON formatında ver. Türkçe karakterleri doğru tanı."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            if self._client is not None:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=2000
                )
                ai_message = response.choices[0].message.content
            else:
                response = openai.ChatCompletion.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=2000
                )
                ai_message = response.choices[0].message.content

            # Parse response
            result = self._parse_ai_response(
                ai_message,
                template_fields
            )

            if ocr_data and isinstance(ocr_data, dict):
                self._merge_ocr_confidence(result, ocr_data)

            logger.info(f"AI haritalama tamamlandı: {len(result)} alan")
            return result

        except AuthenticationError as e:
            logger.error("OpenAI API kimlik doğrulama hatası: %s", str(e))
            return self._create_empty_mapping(
                template_fields,
                "OpenAI API anahtarı doğrulanamadı"
            )
        except OpenAIError as e:
            logger.error("OpenAI API hatası: %s", str(e))
            return self._create_empty_mapping(template_fields, str(e))
        except Exception as e:
            logger.error(f"AI haritalama hatası: {str(e)}")
            # Return empty mappings with low confidence
            return self._create_empty_mapping(template_fields, str(e))

    def _build_mapping_prompt(
        self,
        ocr_text: str,
        template_fields: List[Dict[str, Any]],
        regex_hits: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Build prompt for GPT-4

        Args:
            ocr_text: OCR extracted text
            template_fields: Template field definitions

        Returns:
            Formatted prompt string
        """
        # Format field definitions
        fields_description = []
        for field in template_fields:
            field_desc = f"- {field['field_name']} ({field['data_type']})"
            if field.get('required'):
                field_desc += " [Zorunlu]"
            fields_description.append(field_desc)

        fields_str = "\n".join(fields_description)

        prompt = f"""
Aşağıdaki OCR metni bir belgeden çıkarılmıştır. Bu metindeki bilgileri belirtilen alanlara eşleştir.

HEDEF ALANLAR:
{fields_str}

OCR METNİ:
{ocr_text}

GÖREV:
Her alan için:
1. Değeri bul (bulunamazsa null)
2. Güven skoru belirle (0.0-1.0 arası)
3. Bulunan değerin belgede nerede olduğunu açıkla (kısa)

Yanıtını şu JSON formatında ver:
{{
  "mappings": {{
    "alan_adı": {{
      "value": "bulunan değer veya null",
      "confidence": 0.0-1.0,
      "source": "değerin belgede nerede olduğu"
    }}
  }},
  "overall_confidence": 0.0-1.0
}}

ÖNEMLİ:
- Türkçe karakterleri koru (ş, ğ, ü, ö, ç, İ)
- Tarihler için DD/MM/YYYY veya DD.MM.YYYY formatını kullan
- Sayılar için nokta ayracını koru (ör: 1.234,56)
- Emin değilsen confidence düşük ver
- Kesinlikle JSON formatında yanıt ver
"""

        if regex_hits:
            prompt += "\n\nÖN BULGULAR (Regex): " + json.dumps(regex_hits, ensure_ascii=False)

        return prompt

    def _pre_detect_fields(self, ocr_text: str) -> Dict[str, str]:
        """
        Perform lightweight regex-based detections to guide the LLM.

        Args:
            ocr_text: OCR extracted text.

        Returns:
            Dictionary of field hints detected via regex.
        """
        if not ocr_text:
            return {}

        fields: Dict[str, str] = {}

        if match := re.search(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", ocr_text):
            fields["Tarih"] = match.group(0)

        if match := re.search(r"MAK[-\s]*\d{4,}", ocr_text, re.IGNORECASE):
            fields["Makine No"] = match.group(0)

        return fields

    def _merge_ocr_confidence(
        self,
        result: Dict[str, Any],
        ocr_data: Dict[str, Any]
    ) -> None:
        """
        Merge OCR engine confidence scores with AI-produced confidences.

        Args:
            result: Parsed AI response.
            ocr_data: Detailed OCR data that may include confidence scores.
        """
        confidence_scores = ocr_data.get("confidence_scores")
        if not isinstance(confidence_scores, dict):
            return

        normalized_scores: Dict[str, float] = {}
        for key, value in confidence_scores.items():
            if not isinstance(key, str):
                continue
            try:
                score = float(value)
            except (TypeError, ValueError):
                continue
            normalized_scores[key.lower()] = max(0.0, min(score, 1.0))

        if not normalized_scores:
            return

        field_mappings = result.get("field_mappings", {})
        if not isinstance(field_mappings, dict):
            return

        collected_confidences: List[float] = []

        for mapping in field_mappings.values():
            value = mapping.get('value') if isinstance(mapping, dict) else None
            if value is None:
                continue

            if not isinstance(value, str):
                value_str = str(value)
            else:
                value_str = value

            lowered_value = value_str.lower()
            matched_scores = [
                score for token, score in normalized_scores.items() if token in lowered_value
            ]

            if not matched_scores:
                continue

            avg_confidence = sum(matched_scores) / len(matched_scores)
            if isinstance(mapping, dict):
                current_conf = float(mapping.get('confidence', 0.0))
                merged_conf = max(current_conf, avg_confidence)
                mapping['confidence'] = merged_conf
                collected_confidences.append(merged_conf)

        if collected_confidences:
            overall_conf = result.get('overall_confidence')
            try:
                overall_conf_value = float(overall_conf)
            except (TypeError, ValueError):
                overall_conf_value = 0.0

            averaged = sum(collected_confidences) / len(collected_confidences)
            result['overall_confidence'] = max(overall_conf_value, averaged)

    def _parse_ai_response(
        self,
        response_text: str,
        template_fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Parse AI response and format for application

        Args:
            response_text: Raw AI response
            template_fields: Template field definitions

        Returns:
            Formatted mapping result
        """
        try:
            # Try to parse JSON from response
            # Sometimes GPT wraps JSON in markdown code blocks
            response_text = response_text.strip()

            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]

            response_text = response_text.strip()

            # Parse JSON
            ai_result = json.loads(response_text)

            # Format result
            result = {
                'field_mappings': {},
                'overall_confidence': ai_result.get('overall_confidence', 0.5)
            }

            mappings = ai_result.get('mappings', {})

            for field in template_fields:
                field_name = field['field_name']

                if field_name in mappings:
                    mapping = mappings[field_name]
                    result['field_mappings'][field_name] = {
                        'value': mapping.get('value'),
                        'confidence': float(mapping.get('confidence', 0.0)),
                        'source': mapping.get('source', ''),
                        'data_type': field['data_type']
                    }
                else:
                    # Field not found
                    result['field_mappings'][field_name] = {
                        'value': None,
                        'confidence': 0.0,
                        'source': 'Bulunamadı',
                        'data_type': field['data_type']
                    }

            return result

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse hatası: {str(e)}\nYanıt: {response_text}")
            return self._create_empty_mapping(template_fields, "JSON parse hatası")
        except Exception as e:
            logger.error(f"Yanıt işleme hatası: {str(e)}")
            return self._create_empty_mapping(template_fields, str(e))

    def _create_empty_mapping(
        self,
        template_fields: List[Dict[str, Any]],
        error_msg: str = ""
    ) -> Dict[str, Any]:
        """
        Create empty mapping with low confidence (fallback)

        Args:
            template_fields: Template field definitions
            error_msg: Error message to include

        Returns:
            Empty mapping result
        """
        result = {
            'field_mappings': {},
            'overall_confidence': 0.0,
            'error': error_msg
        }

        for field in template_fields:
            result['field_mappings'][field['field_name']] = {
                'value': None,
                'confidence': 0.0,
                'source': 'Hata oluştu',
                'data_type': field['data_type']
            }

        return result

    def validate_and_correct(
        self,
        extracted_data: Dict[str, Any],
        user_corrections: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Learn from user corrections to improve future mappings

        Args:
            extracted_data: Original extracted data
            user_corrections: User-provided corrections

        Returns:
            Updated extraction rules
        """
        # This would ideally store corrections to improve future mappings
        # For now, just merge corrections
        updated_data = extracted_data.copy()

        for field, correction in user_corrections.items():
            if field in updated_data['field_mappings']:
                updated_data['field_mappings'][field]['value'] = correction
                updated_data['field_mappings'][field]['confidence'] = 1.0
                updated_data['field_mappings'][field]['source'] = 'Kullanıcı düzeltmesi'

        return updated_data

    def calculate_field_status(self, confidence: float) -> str:
        """
        Determine field status based on confidence score

        Args:
            confidence: Confidence score (0.0-1.0)

        Returns:
            Status: "high", "medium", or "low"
        """
        if confidence >= 0.8:
            return "high"
        elif confidence >= 0.5:
            return "medium"
        else:
            return "low"
