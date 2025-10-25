# -*- coding: utf-8 -*-
import openai
import json
import logging
from typing import Dict, List, Any, Optional

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
        openai.api_key = api_key

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
        try:
            # Build prompt for GPT-4
            prompt = self._build_mapping_prompt(ocr_text, template_fields)

            # Call OpenAI API
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
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
                ],
                temperature=0.1,  # Low temperature for consistent results
                max_tokens=2000
            )

            # Parse response
            result = self._parse_ai_response(
                response.choices[0].message.content,
                template_fields
            )

            logger.info(f"AI haritalama tamamlandı: {len(result)} alan")
            return result

        except Exception as e:
            logger.error(f"AI haritalama hatası: {str(e)}")
            # Return empty mappings with low confidence
            return self._create_empty_mapping(template_fields, str(e))

    def _build_mapping_prompt(
        self,
        ocr_text: str,
        template_fields: List[Dict[str, Any]]
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

        return prompt

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
