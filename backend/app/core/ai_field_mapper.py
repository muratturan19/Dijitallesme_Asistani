# -*- coding: utf-8 -*-
import json
import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.config import settings

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
    """Uses OpenAI GPT models (default: gpt-5) to map OCR text to template fields"""

    def __init__(self, api_key: str, model: str = settings.OPENAI_MODEL):
        """
        Initialize AI field mapper

        Args:
            api_key: OpenAI API key
            model: Model name (default: gpt-5)
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
        ocr_data: Optional[Dict[str, Any]] = None,
        field_hints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Map OCR extracted text to template fields using AI

        Args:
            ocr_text: Full extracted text from OCR
            template_fields: List of target field definitions
            ocr_data: Optional detailed OCR data with bounding boxes
            field_hints: Optional overrides such as regex/type/fallback hints

        Returns:
            Dictionary with field mappings and confidence scores
        """
        if not self._has_valid_api_key:
            return self._create_empty_mapping(
                template_fields,
                "OpenAI API anahtarı ayarlanmamış veya geçersiz."
            )

        try:
            # Build prompt for the configured OpenAI model
            hints = field_hints or {}
            field_context = [
                self._build_field_context(
                    field,
                    hints.get(field.get('field_name')) if isinstance(field, dict) else None
                )
                for field in template_fields
            ]
            field_evidence = self._pre_detect_fields(
                ocr_text,
                template_fields,
                hints if hints else None
            )
            prompt = self._build_mapping_prompt(
                ocr_text,
                field_context,
                field_evidence=field_evidence if field_evidence else None,
                field_hints=self._summarize_field_hints(hints)
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
                self._merge_ocr_confidence(result, ocr_data, template_fields)

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
            raw_error = str(e)
            user_friendly_error = raw_error
            if 'field_hints' in raw_error and '_build_mapping_prompt' in raw_error:
                user_friendly_error = 'field_hints parametresi uyumsuz. Lütfen tekrar deneyin.'

            logger.error(f"AI haritalama hatası: {raw_error}")
            # Return empty mappings with low confidence
            return self._create_empty_mapping(template_fields, user_friendly_error)

    def _build_mapping_prompt(
        self,
        ocr_text: str,
        template_fields: List[Dict[str, Any]],
        regex_hits: Optional[Dict[str, Any]] = None,
        field_hints: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> str:
        """Build the deterministic mapping prompt with full instructions and metadata."""

        # Accept historical call signatures gracefully.
        field_evidence: Optional[Dict[str, Any]] = kwargs.get('field_evidence')

        # Merge hints provided by previous "regex_hits" argument and the new "field_hints".
        merged_hints: Dict[str, Any] = {}
        if isinstance(regex_hits, dict):
            merged_hints.update(regex_hits)
            # If explicit field_evidence not passed, keep backward compatible behaviour.
            if field_evidence is None:
                field_evidence = regex_hits
        elif regex_hits:
            try:
                merged_hints.update(dict(regex_hits))
            except Exception:  # pragma: no cover - defensive
                pass

        if isinstance(field_hints, dict):
            merged_hints.update(field_hints)

        if template_fields and all('name' in field for field in template_fields):
            field_context = template_fields
        else:
            field_context = [self._build_field_context(field) for field in template_fields]

        instruction_block = (
            "Amaç: OCR çıktısından hedef alan değerlerini tespit etmek, verilen "
            "kısıtları uygulamak ve normalize edilmiş JSON yanıtı üretmek.\n"
            "Öncelik Hiyerarşisi:\n"
            "  1. Regex ipuçları ve ROI/PSM eşleşmeleriyle doğrulanmış sonuçlar.\n"
            "  2. Aynı satır/sütun bağlamındaki açık metin eşleşmeleri.\n"
            "  3. Destekleyici kanıtı olan çıkarımlar.\n"
            "  4. Kanıt yoksa değeri null döndür.\n"
            "Normalizasyon Kuralları:\n"
            "  - Tarihler: DD.MM.YYYY veya DD/MM/YYYY, gün ve ay iki haneli.\n"
            "  - Sayılar: Binlik ayracı nokta, ondalık virgül (ör: 1.234,56).\n"
            "  - Metinler: Baş/son boşlukları temizle, Türkçe karakterleri koru.\n"
            "Güven Politikası:\n"
            "  - Regex+OCR teyidi varsa ≥0.9.\n"
            "  - Bağlamla desteklenen ancak zayıf kanıtlı sonuçlar 0.4-0.7.\n"
            "  - Emin değilsen 0.3 altı ve gerekirse null.\n"
            "Deterministik Ayarlar:\n"
            "  - Metinde olmayan bilgiyi uydurma.\n"
            "  - Tüm alanları JSON şemasında sırayla döndür, anahtar adlarını değiştirme.\n"
            "  - Kaynak açıklamalarını kısa ve kanıt gösterir şekilde yaz."
        )

        output_schema = {
            "mappings": {
                "Alan Adı": {
                    "value": "<string|null>",
                    "confidence": 0.0,
                    "source": "<kısa kanıt açıklaması>"
                }
            },
            "overall_confidence": 0.0
        }

        prompt_sections = [
            "Aşağıdaki OCR metni bir belgeden çıkarılmıştır."
            " Talimatlara sıkı sıkıya bağlı kalarak alan değerlerini belirle.",
            "\nTALİMAT SETİ:\n" + instruction_block,
            "\nALAN METAVERİSİ:\n" + json.dumps(
                field_context, ensure_ascii=False, indent=2
            )
        ]

        if merged_hints:
            prompt_sections.append(
                "\nALAN KURALLARI:\n" + json.dumps(
                    merged_hints, ensure_ascii=False, indent=2
                )
            )

        prompt_sections.extend([
            "\nÇIKTI ŞEMASI:\n" + json.dumps(
                output_schema, ensure_ascii=False, indent=2
            ),
            "\nOCR METNİ:\n" + ocr_text,
            (
                "\nYANIT FORMATIN:\n"
                "Yanıtını yalnızca geçerli JSON ile ver."
            )
        ])

        if field_evidence:
            prompt_sections.append(
                "\nÖN BULGULAR (Regex/Heuristik):\n" + json.dumps(
                    field_evidence, ensure_ascii=False, indent=2
                )
            )

        return "\n".join(prompt_sections)

    def _build_field_context(
        self,
        field: Dict[str, Any],
        hints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Normalize field metadata for prompting."""

        data_type = field.get('data_type', 'text')
        context: Dict[str, Any] = {
            'name': field.get('field_name'),
            'type': data_type,
            'required': bool(field.get('required', False)),
            'normalization': self._field_normalization_hint(data_type)
        }

        regex_hint = field.get('regex_hint')
        if regex_hint:
            context['regex_hint'] = regex_hint

        examples = field.get('examples') or field.get('format_examples') or field.get('example')
        if isinstance(examples, str):
            examples = [examples]
        if not examples:
            examples = self._default_examples_for_type(data_type)
        if examples:
            context['examples'] = examples

        ocr_psm = field.get('ocr_psm')
        if ocr_psm not in (None, ''):
            context['ocr_psm'] = ocr_psm

        ocr_roi = field.get('ocr_roi')
        if ocr_roi is not None:
            context['ocr_roi'] = ocr_roi

        if field.get('calculated'):
            context['calculated'] = True

        if hints:
            type_hint = hints.get('type_hint')
            if type_hint and 'type_hint' not in context:
                context['type_hint'] = type_hint

            fallback = hints.get('fallback_value')
            if fallback is not None:
                context['fallback_value'] = fallback

            regex_patterns = hints.get('regex_patterns')
            if regex_patterns:
                context['regex_overrides'] = regex_patterns

            roi_hint = hints.get('roi')
            if roi_hint is not None and 'ocr_roi' not in context:
                context['ocr_roi'] = roi_hint

            ocr_hint = hints.get('ocr')
            if ocr_hint:
                context['ocr_overrides'] = ocr_hint

            preprocessing_hint = hints.get('preprocessing')
            if preprocessing_hint:
                context['preprocessing'] = preprocessing_hint

            if hints.get('metadata'):
                context['metadata'] = hints['metadata']

        return context

    def _default_examples_for_type(self, data_type: str) -> List[str]:
        """Provide deterministic formatting examples by data type."""

        if data_type == 'date':
            return ['31.12.2023', '01/01/2024']
        if data_type == 'number':
            return ['1.234,56', '12.345,00']
        return []

    def _field_normalization_hint(self, data_type: str) -> str:
        """Return normalization hint for a data type."""

        hints = {
            'date': 'Tarihleri DD.MM.YYYY veya DD/MM/YYYY biçimine dönüştür.',
            'number': 'Sayıları 1.234,56 formatında yaz, gereksiz karakterleri kaldır.',
            'text': 'Metni olduğu gibi aktar, baş/son boşlukları temizle.'
        }
        return hints.get(data_type, hints['text'])

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        """Safely convert to float."""

        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_token(token: str) -> str:
        """Normalize tokens for fuzzy OCR comparisons."""

        return re.sub(r'[^0-9a-zA-ZçğıöşüÇĞİÖŞÜ]', '', token).lower()

    def _regex_flag_value(self, flags: Optional[Any]) -> int:
        """Convert flag descriptors into a Python regex flag bitmask."""

        if flags is None:
            return re.IGNORECASE

        if isinstance(flags, int):
            return flags

        flag_value = 0
        candidates: List[Any]

        if isinstance(flags, str):
            candidates = [flags]
        elif isinstance(flags, (list, tuple, set)):
            candidates = list(flags)
        else:
            return re.IGNORECASE

        for candidate in candidates:
            if isinstance(candidate, int):
                flag_value |= candidate
                continue
            if not isinstance(candidate, str):
                continue
            attr = getattr(re, candidate.upper(), None)
            if isinstance(attr, int):
                flag_value |= attr

        return flag_value or re.IGNORECASE

    def _summarize_field_hints(self, hints: Dict[str, Any]) -> Dict[str, Any]:
        """Return a sanitized view of field hints for prompting."""

        summary: Dict[str, Any] = {}

        for field_name, data in hints.items():
            if not isinstance(field_name, str) or not isinstance(data, dict):
                continue

            entry: Dict[str, Any] = {}
            for key in ('type_hint', 'fallback_value', 'regex_patterns', 'ocr', 'preprocessing', 'roi', 'enabled'):
                value = data.get(key)
                if value in (None, {}, [], ''):
                    continue
                entry[key] = value

            metadata = data.get('metadata')
            if isinstance(metadata, dict) and metadata:
                entry['metadata'] = metadata

            if entry:
                summary[field_name] = entry

        return summary

    def _build_word_confidence_map(self, ocr_data: Dict[str, Any]) -> Dict[str, List[float]]:
        """Aggregate OCR confidences per normalized token."""

        if not isinstance(ocr_data, dict):
            return {}

        token_confidences: Dict[str, List[float]] = defaultdict(list)

        confidence_scores = ocr_data.get('confidence_scores')
        if isinstance(confidence_scores, dict):
            for token, score in confidence_scores.items():
                if not isinstance(token, str):
                    continue
                float_score = self._safe_float(score)
                if float_score is None:
                    continue
                float_score = max(0.0, min(float_score, 1.0))
                lowered = token.strip().lower()
                if lowered:
                    token_confidences[lowered].append(float_score)
                normalized = self._normalize_token(token)
                if normalized and normalized != lowered:
                    token_confidences[normalized].append(float_score)

        words_with_bbox = ocr_data.get('words_with_bbox')
        if isinstance(words_with_bbox, list):
            for entry in words_with_bbox:
                if not isinstance(entry, dict):
                    continue
                word = entry.get('word')
                confidence = self._safe_float(entry.get('confidence'))
                if not word or confidence is None:
                    continue
                confidence = max(0.0, min(confidence, 1.0))
                lowered = word.strip().lower()
                if lowered:
                    token_confidences[lowered].append(confidence)
                normalized = self._normalize_token(word)
                if normalized and normalized != lowered:
                    token_confidences[normalized].append(confidence)

        # Remove empty entries
        return {token: scores for token, scores in token_confidences.items() if scores}

    def _compute_value_ocr_confidence(
        self,
        value: str,
        word_conf_map: Dict[str, List[float]]
    ) -> Optional[float]:
        """Return OCR confidence aligned with the provided value."""

        if not value:
            return None

        tokens = re.findall(r"[0-9A-Za-zçğıöşüÇĞİÖŞÜ]+", value)
        if not tokens:
            tokens = [value]

        confidences: List[float] = []

        for token in tokens:
            lowered = token.strip().lower()
            candidates = word_conf_map.get(lowered)
            if not candidates:
                normalized = self._normalize_token(token)
                candidates = word_conf_map.get(normalized)
            if candidates:
                confidences.append(sum(candidates) / len(candidates))

        if not confidences:
            return None

        coverage = len(confidences) / len(tokens) if tokens else 1.0
        avg_conf = sum(confidences) / len(confidences)

        return max(0.0, min(1.0, avg_conf * coverage))

    def _pre_detect_fields(
        self,
        ocr_text: str,
        template_fields: List[Dict[str, Any]],
        field_hints: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Perform lightweight detections (regex + heuristics) to guide the LLM."""

        if not ocr_text or not template_fields:
            return {}

        evidence: Dict[str, Any] = {}
        hints = field_hints or {}

        # 1) Respect user-provided regex hints per field.
        for field in template_fields:
            field_name = field.get('field_name')
            if not field_name:
                continue

            pattern_candidates: List[Dict[str, Any]] = []

            pattern_text = field.get('regex_hint')
            if pattern_text:
                pattern_candidates.append({
                    'pattern': pattern_text,
                    'flags': None,
                    'source': 'template'
                })

            hint_data = hints.get(field_name)
            if isinstance(hint_data, dict):
                hint_patterns = hint_data.get('regex_patterns') or []
                if isinstance(hint_patterns, dict):
                    hint_patterns = [hint_patterns]
                for hint_pattern in hint_patterns:
                    if not isinstance(hint_pattern, dict):
                        continue
                    pattern_candidates.append({
                        'pattern': hint_pattern.get('pattern'),
                        'flags': hint_pattern.get('flags'),
                        'source': hint_pattern.get('source', 'hint')
                    })

            if not pattern_candidates:
                continue

            pattern_evidence: List[Dict[str, Any]] = []
            for candidate in pattern_candidates:
                pattern_str = candidate.get('pattern')
                if not pattern_str:
                    continue
                try:
                    compiled = re.compile(
                        pattern_str,
                        self._regex_flag_value(candidate.get('flags'))
                    )
                except re.error as exc:
                    logger.warning(
                        "Geçersiz regex (%s) alanı %s için: %s",
                        pattern_str,
                        field_name,
                        exc
                    )
                    continue

                matches = compiled.findall(ocr_text)
                if not matches:
                    continue

                normalized_matches: List[str] = []
                for match in matches:
                    if isinstance(match, tuple):
                        normalized_matches.append(" ".join(part for part in match if part))
                    else:
                        normalized_matches.append(str(match))

                if normalized_matches:
                    pattern_evidence.append({
                        'pattern': compiled.pattern,
                        'source': candidate.get('source', 'regex'),
                        'matches': normalized_matches
                    })

            if not pattern_evidence:
                continue

            if len(pattern_evidence) == 1:
                evidence[field_name] = pattern_evidence[0]
            else:
                evidence[field_name] = {'patterns': pattern_evidence}

        # 2) Apply general heuristics for commonly formatted data types.
        date_matches = re.findall(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", ocr_text)
        if date_matches:
            deduped_dates = list(dict.fromkeys(date_matches))[:3]
            for field in template_fields:
                if (
                    field.get('data_type') == 'date'
                    and field.get('field_name') not in evidence
                    and deduped_dates
                ):
                    evidence[field['field_name']] = {
                        'pattern': 'auto_date',
                        'matches': deduped_dates
                    }

        number_matches = re.findall(
            r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\b",
            ocr_text
        )
        if number_matches:
            deduped_numbers = list(dict.fromkeys(number_matches))[:5]
            for field in template_fields:
                if (
                    field.get('data_type') == 'number'
                    and field.get('field_name') not in evidence
                    and deduped_numbers
                ):
                    evidence[field['field_name']] = {
                        'pattern': 'auto_number',
                        'matches': deduped_numbers
                    }

        return evidence

    def _merge_ocr_confidence(
        self,
        result: Dict[str, Any],
        ocr_data: Dict[str, Any],
        template_fields: List[Dict[str, Any]]
    ) -> None:
        """Blend OCR confidences with LLM scores using template metadata."""

        field_mappings = result.get('field_mappings')
        if not isinstance(field_mappings, dict) or not field_mappings:
            return

        word_conf_map = self._build_word_confidence_map(ocr_data)
        metadata_index = {
            field.get('field_name'): field for field in template_fields if field.get('field_name')
        }

        collected_confidences: List[float] = []

        for field_name, mapping in field_mappings.items():
            if not isinstance(mapping, dict):
                continue

            metadata = metadata_index.get(field_name, {})
            llm_conf = self._safe_float(mapping.get('confidence')) or 0.0
            value = mapping.get('value')
            value_str = str(value).strip() if value not in (None, "") else ""

            ocr_conf = None
            if value_str and word_conf_map:
                ocr_conf = self._compute_value_ocr_confidence(value_str, word_conf_map)

            regex_ok = True
            regex_hint = metadata.get('regex_hint')
            if regex_hint and value_str:
                try:
                    regex_ok = bool(re.search(regex_hint, value_str))
                except re.error:
                    regex_ok = True

            combined_conf = llm_conf
            if ocr_conf is not None:
                combined_conf = (llm_conf * 0.6) + (ocr_conf * 0.4)

            if not regex_ok:
                combined_conf = min(combined_conf, llm_conf * 0.5)

            if metadata.get('required') and not value_str:
                combined_conf = 0.0

            combined_conf = max(0.0, min(1.0, combined_conf))

            mapping['confidence'] = combined_conf
            mapping['confidence_breakdown'] = {
                'llm': llm_conf,
                'ocr': ocr_conf,
                'regex_valid': regex_ok
            }

            collected_confidences.append(combined_conf)

        if collected_confidences:
            result['overall_confidence'] = sum(collected_confidences) / len(collected_confidences)

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
                metadata = {
                    'data_type': field.get('data_type'),
                    'required': bool(field.get('required', False)),
                    'regex_hint': field.get('regex_hint'),
                    'ocr_psm': field.get('ocr_psm'),
                    'ocr_roi': field.get('ocr_roi')
                }

                if field_name in mappings:
                    mapping = mappings[field_name]
                    result['field_mappings'][field_name] = {
                        'value': mapping.get('value'),
                        'confidence': float(mapping.get('confidence', 0.0)),
                        'source': mapping.get('source', ''),
                        'data_type': field['data_type'],
                        'required': metadata['required'],
                        'metadata': metadata
                    }
                else:
                    # Field not found
                    result['field_mappings'][field_name] = {
                        'value': None,
                        'confidence': 0.0,
                        'source': 'Bulunamadı',
                        'data_type': field['data_type'],
                        'required': metadata['required'],
                        'metadata': metadata
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
                'data_type': field['data_type'],
                'required': bool(field.get('required', False)),
                'metadata': {
                    'data_type': field.get('data_type'),
                    'required': bool(field.get('required', False)),
                    'regex_hint': field.get('regex_hint'),
                    'ocr_psm': field.get('ocr_psm'),
                    'ocr_roi': field.get('ocr_roi')
                }
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
