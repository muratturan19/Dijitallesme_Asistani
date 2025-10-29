# -*- coding: utf-8 -*-
import inspect
import json
import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.config import settings
from app.utils.data_masker import DataMasker
from app.utils.smart_openai import (
    call_reasoning_model,
    extract_reasoning_response_text,
)

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
    """Uses OpenAI GPT models (default: gpt-4o) to map OCR text to template fields"""

    def __init__(
        self,
        api_key: str,
        model: str = settings.AI_PRIMARY_MODEL,
        *,
        temperature: Optional[float] = None,
        context_window: Optional[int] = None,
    ):
        """
        Initialize AI field mapper

        Args:
            api_key: OpenAI API key
            model: Model name (default: gpt-4o)
        """
        self.api_key = api_key
        self.model = model
        self.temperature = (
            settings.AI_PRIMARY_TEMPERATURE if temperature is None else temperature
        )
        self.context_window = (
            settings.AI_PRIMARY_CONTEXT_WINDOW
            if context_window is None
            else context_window
        )
        self._has_valid_api_key = bool(api_key and api_key.strip())

        self._client = None
        self._responses_accepts_response_format = False
        self._chat_accepts_response_format = False
        if self._has_valid_api_key:
            if OpenAI is not None:
                # Modern OpenAI client (>=1.0)
                self._client = OpenAI(api_key=api_key)
                self._refresh_response_format_support()
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
            logger.info(
                "AI alan eşleme süreci başladı: field_count=%s, ocr_text_length=%s",
                len(template_fields),
                len(ocr_text or "")
            )
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

            masker = DataMasker(enabled=settings.DATA_MASKING_ENABLED)
            prompt_preview = prompt
            if masker.enabled:
                prompt_preview = masker.mask_text(prompt) or ""

            logger.info(
                "AI istemci konfigürasyonu hazır: client_type=%s, hints=%s, regex_hits=%s",
                "modern" if self._client is not None else "legacy",
                len(hints),
                len(field_evidence or {})
            )
            logger.info(
                "Oluşturulan prompt özeti: uzunluk=%s, ilk_200_karakter=%s",
                len(prompt),
                (prompt_preview or "")[:200]
            )

            source = (ocr_data or {}).get('source', 'unknown') if ocr_data else 'unknown'
            is_reasoning_model = str(self.model).startswith("gpt-5")
            max_completion_tokens = max(1, int(self.context_window or 2000))
            temperature = None if is_reasoning_model else self.temperature
            response_format = {"type": "json_object"}
            token_limit_for_logging = None if is_reasoning_model else max_completion_tokens

            logger.info(
                "AI eşleme çağrısı: model=%s, response_format=%s, token_limit=%s, temperature=%s",
                self.model,
                response_format.get('type'),
                token_limit_for_logging,
                temperature if temperature is not None else "auto",
            )
            logger.info("OCR kaynağı: %s", source)
            logger.debug(
                "Regex ön bulgusu olan alan sayısı: %s, field hint alan sayısı: %s",
                len(field_evidence or {}),
                len(hints),
            )

            # Call OpenAI API (supports both legacy and modern clients)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Sen bir belge analiz uzmanısın. Görevin, OCR ile çıkarılan metinden "
                        "belirli alanları tespit etmek ve değerlerini bulmaktır. Sadece geçerli "
                        "JSON döndür. Açıklama, başlık, markdown veya code fence ekleme. Türkçe "
                        "karakterleri doğru tanı."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            if masker.enabled:
                messages = masker.mask_messages(messages)

            logger.info("OpenAI API çağrısı hazırlanıyor...")
            if self._client is not None:
                self._refresh_response_format_support()
                if is_reasoning_model:
                    responses_response_format = None
                    if response_format and self._responses_accepts_response_format:
                        responses_response_format = response_format
                    elif response_format:
                        logger.debug(
                            "response_format desteği olmayan Responses.create kullanımı tespit edildi"
                        )

                    response = call_reasoning_model(
                        self._client,
                        model=self.model,
                        messages=messages,
                        response_format=responses_response_format,
                        temperature=temperature,
                    )
                else:
                    request_kwargs = {
                        "model": self.model,
                        "messages": messages,
                    }
                    if temperature is not None:
                        request_kwargs["temperature"] = temperature
                    if response_format and self._chat_accepts_response_format:
                        request_kwargs["response_format"] = response_format
                    else:
                        logger.debug(
                            "response_format desteği olmayan ChatCompletions.create kullanımı tespit edildi"
                        )
                    if max_completion_tokens is not None:
                        request_kwargs["max_completion_tokens"] = max_completion_tokens

                    response = self._client.chat.completions.create(**request_kwargs)
            else:
                request_kwargs = {
                    "model": self.model,
                    "messages": messages,
                }
                if temperature is not None:
                    request_kwargs["temperature"] = temperature
                if (not is_reasoning_model) and max_completion_tokens is not None:
                    request_kwargs["max_tokens"] = max_completion_tokens

                response = openai.ChatCompletion.create(**request_kwargs)

            logger.info(
                "OpenAI yanıtı alındı: response_type=%s, has_choices=%s",
                type(response).__name__,
                bool(getattr(response, 'choices', None) or (
                    isinstance(response, dict) and response.get('choices')
                ))
            )
            logger.debug(
                "OpenAI yanıtı ham veri özeti: %s",
                self._safe_dump_response(response)
            )

            raw_ai_message = self._extract_ai_message(response)

            if not raw_ai_message:
                logger.error("OpenAI'den boş yanıt alındı")
                logger.error(
                    "Boş yanıt hatası için OpenAI response içeriği: %s",
                    self._safe_dump_response(response)
                )
                return self._create_empty_mapping(
                    template_fields,
                    "OpenAI'den geçerli yanıt alınamadı"
                )

            logger.debug(
                "AI ham yanıtı (ilk 1000 karakter): %s",
                raw_ai_message[:1000]
            )

            ai_message = masker.unmask_text(raw_ai_message)

            # Parse response
            result = self._parse_ai_response(
                ai_message,
                template_fields,
                field_evidence=field_evidence
            )

            result = masker.unmask_structure(result)

            if ocr_data and isinstance(ocr_data, dict):
                self._merge_ocr_confidence(result, ocr_data, template_fields)

            logger.info(
                "AI haritalama tamamlandı: %s alan",
                len(result.get('field_mappings', {}))
            )
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

    @staticmethod
    def _supports_kwarg(method: Any, keyword: str) -> bool:
        """Return True if the given callable accepts the provided keyword."""

        if method is None:
            return False

        try:
            signature = inspect.signature(method)
        except (TypeError, ValueError):  # pragma: no cover - fall back safely
            return False

        for parameter in signature.parameters.values():
            if parameter.kind == inspect.Parameter.VAR_KEYWORD:
                return True

        return keyword in signature.parameters

    def _refresh_response_format_support(self) -> None:
        """Recalculate response_format support flags for the current client."""

        self._responses_accepts_response_format = False
        self._chat_accepts_response_format = False

        if self._client is None:
            return

        responses_create = getattr(getattr(self._client, "responses", None), "create", None)
        self._responses_accepts_response_format = self._supports_kwarg(
            responses_create,
            "response_format",
        )

        chat_completions = getattr(getattr(self._client, "chat", None), "completions", None)
        chat_create = getattr(chat_completions, "create", None)
        self._chat_accepts_response_format = self._supports_kwarg(
            chat_create,
            "response_format",
        )

    @staticmethod
    def _safe_dump_response(response: Any) -> str:
        """Safely serialize OpenAI response objects for logging."""

        if response is None:
            return "<empty response>"

        try:
            model_dump = getattr(response, "model_dump", None)
            if callable(model_dump):
                dumped = model_dump()
                return json.dumps(dumped, ensure_ascii=False, default=str)[:4000]
        except Exception as exc:  # pragma: no cover - defensive logging path
            logger.debug("OpenAI yanıtı model_dump sırasında hata: %s", exc)

        try:
            return json.dumps(response, ensure_ascii=False, default=str)[:4000]
        except TypeError:
            try:
                response_dict = getattr(response, "__dict__", None)
                if response_dict:
                    return json.dumps(response_dict, ensure_ascii=False, default=str)[:4000]
            except Exception:  # pragma: no cover - defensive
                pass

        return repr(response)[:4000]

    @staticmethod
    def _extract_ai_message(response: Any) -> Optional[str]:
        """Return the textual message content from an OpenAI response."""

        if response is None:
            logger.info("_extract_ai_message: response nesnesi None geldi")
            return None

        reasoning_text = extract_reasoning_response_text(response)
        if reasoning_text:
            logger.info(
                "_extract_ai_message: reasoning output işlendi (uzunluk=%s)",
                len(reasoning_text),
            )
            return reasoning_text

        output_items = getattr(response, "output", None)
        if output_items:
            logger.info(
                "_extract_ai_message: output alanı mevcut ancak metin çıkarılamadı (öğe_sayısı=%s)",
                len(output_items),
            )

        try:
            choices = response.choices  # type: ignore[attr-defined]
        except AttributeError:
            choices = response.get('choices') if isinstance(response, dict) else None

        if not choices:
            logger.info(
                "_extract_ai_message: choices alanı bulunamadı veya boş. response_türü=%s",
                type(response).__name__
            )
            return None

        try:
            choice = choices[0]
        except (IndexError, TypeError):
            logger.info("_extract_ai_message: choices[0] alınamadı")
            return None

        message = getattr(choice, 'message', None)
        if message is None and isinstance(choice, dict):
            message = choice.get('message')

        if message is None:
            logger.info("_extract_ai_message: message alanı bulunamadı")
            return None

        parsed = getattr(message, 'parsed', None)
        if parsed is None and isinstance(message, dict):
            parsed = message.get('parsed')

        if parsed is not None:
            logger.info("_extract_ai_message: parsed içerik bulundu, tip=%s", type(parsed).__name__)
            if isinstance(parsed, (dict, list)):
                try:
                    return json.dumps(parsed, ensure_ascii=False)
                except TypeError:
                    return str(parsed)
            return str(parsed)

        content = getattr(message, 'content', None)
        if content is None and isinstance(message, dict):
            content = message.get('content')

        if isinstance(content, str):
            logger.info("_extract_ai_message: content string olarak bulundu (uzunluk=%s)", len(content))
            return content.strip()

        if isinstance(content, list):
            logger.info("_extract_ai_message: content list olarak bulundu (öğe_sayısı=%s)", len(content))
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue

                item_dict: Optional[Dict[str, Any]] = None
                if isinstance(item, dict):
                    item_dict = item
                else:
                    item_dict = getattr(item, 'model_dump', None)
                    if callable(item_dict):
                        try:
                            item_dict = item.model_dump()
                        except Exception:  # pragma: no cover - defensive
                            item_dict = None
                    if item_dict is None:
                        try:
                            item_dict = dict(item)
                        except Exception:  # pragma: no cover - defensive
                            item_dict = None

                if item_dict:
                    text = item_dict.get('text')
                    if text:
                        parts.append(str(text))
                        continue

                    json_payload = item_dict.get('json')
                    if json_payload is not None:
                        try:
                            parts.append(json.dumps(json_payload, ensure_ascii=False))
                        except TypeError:
                            parts.append(str(json_payload))
                        continue

                text_attr = getattr(item, 'text', None)
                if text_attr:
                    parts.append(str(text_attr))

            if parts:
                return ''.join(parts).strip()
            return None

        if content is not None:
            text = str(content).strip()
            logger.info("_extract_ai_message: content diğer tipten stringe çevrildi (uzunluk=%s)", len(text))
            return text or None

        return None

    def _build_mapping_prompt(
        self,
        ocr_text: str,
        template_fields: List[Dict[str, Any]],
        *,
        field_hints: Optional[Dict[str, Any]] = None,
        field_evidence: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> str:
        """Build the deterministic mapping prompt with full instructions and metadata."""

        # Accept historical call signatures gracefully.
        legacy_regex_hits = kwargs.get('regex_hits')
        if field_evidence is None and isinstance(legacy_regex_hits, dict):
            field_evidence = legacy_regex_hits

        # Merge hints provided by previous "regex_hits" argument and the new "field_hints".
        merged_hints: Dict[str, Any] = {}
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
                "ALAN_ADI": {
                    "value": None,
                    "confidence": 0.0,
                    "source": ""
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
            "\nÇIKTI ŞEMASI (örnek):\n" + json.dumps(
                output_schema, ensure_ascii=False, separators=(',', ':')
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

        metadata = field.get('metadata')
        if isinstance(metadata, dict):
            context['metadata'] = dict(metadata)

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
                merged_metadata = {}
                if isinstance(context.get('metadata'), dict):
                    merged_metadata.update(context['metadata'])
                if isinstance(hints.get('metadata'), dict):
                    merged_metadata.update(hints['metadata'])
                if merged_metadata:
                    context['metadata'] = merged_metadata

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

    def _strip_code_fences(self, response_text: str) -> str:
        """Remove common markdown code fences from an LLM response."""
        text = response_text.strip()

        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]

        if text.endswith("```"):
            text = text[:-3]

        return text.strip()

    def _extract_json_object(self, response_text: str) -> Optional[str]:
        """Try to extract the first complete JSON object from text."""
        brace_depth = 0
        start_index: Optional[int] = None

        for index, char in enumerate(response_text):
            if char == '{':
                if brace_depth == 0:
                    start_index = index
                brace_depth += 1
            elif char == '}':
                if brace_depth:
                    brace_depth -= 1
                    if brace_depth == 0 and start_index is not None:
                        return response_text[start_index:index + 1]

        return None

    def _safe_json_loads(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from AI response, handling markdown and extra text."""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            cleaned_text = self._strip_code_fences(response_text)
            if cleaned_text != response_text:
                try:
                    return json.loads(cleaned_text)
                except json.JSONDecodeError:
                    pass

            extracted_source = cleaned_text if cleaned_text else response_text
            extracted_json = self._extract_json_object(extracted_source)
            if extracted_json:
                return json.loads(extracted_json)
            raise

    def _log_parse_failure(self, response_text: str, error: Exception) -> None:
        """Log detailed information about JSON parsing issues."""
        length = len(response_text or "")
        start_fragment = (response_text or "")[:200]
        end_fragment = (response_text or "")[-200:] if length > 200 else start_fragment

        logger.error(
            "JSON parse hatası: %s | Uzunluk=%s | İlk200='%s' | Son200='%s'",
            error,
            length,
            start_fragment.replace("\n", " "),
            end_fragment.replace("\n", " ")
        )

    def _extract_evidence_match(self, evidence: Any) -> Optional[str]:
        """Extract the most reliable textual match from evidence."""
        if not isinstance(evidence, dict):
            return None

        matches = evidence.get('matches')
        if isinstance(matches, list) and matches:
            return str(matches[0]).strip()

        patterns = evidence.get('patterns')
        if isinstance(patterns, list):
            for pattern_info in patterns:
                if not isinstance(pattern_info, dict):
                    continue
                nested_matches = pattern_info.get('matches')
                if isinstance(nested_matches, list) and nested_matches:
                    return str(nested_matches[0]).strip()

        value = evidence.get('value')
        if value not in (None, ""):
            return str(value).strip()

        return None

    def _evidence_confidence(self, evidence: Any) -> float:
        """Estimate confidence based on evidence provenance."""
        if not isinstance(evidence, dict):
            return 0.6

        source = str(evidence.get('source', '')).lower()
        pattern = str(evidence.get('pattern', '')).lower()

        base_confidence = 0.6

        if source in {'template', 'regex', 'hint'}:
            base_confidence = 0.9
        elif source:
            base_confidence = 0.8

        if pattern in {'auto_date', 'auto_number'}:
            base_confidence = max(base_confidence, 0.75)

        patterns = evidence.get('patterns')
        if isinstance(patterns, list) and patterns:
            first_pattern = next((p for p in patterns if isinstance(p, dict)), None)
            if first_pattern:
                base_confidence = max(base_confidence, self._evidence_confidence(first_pattern))

        return max(0.0, min(base_confidence, 0.95))

    def _describe_evidence_source(self, evidence: Any) -> str:
        """Create a short human readable description for evidence."""
        if not isinstance(evidence, dict):
            return "Ön tespit"

        pattern = str(evidence.get('pattern', '')).lower()
        source = evidence.get('source')

        if pattern in {'auto_date', 'auto_number'}:
            return f"Ön tespit ({pattern})"

        if source:
            return f"Regex eşleşmesi ({source})"

        patterns = evidence.get('patterns')
        if isinstance(patterns, list):
            for pattern_info in patterns:
                description = self._describe_evidence_source(pattern_info)
                if description:
                    return description

        return "Regex ön tespiti"

    def _build_partial_mapping_from_evidence(
        self,
        template_fields: List[Dict[str, Any]],
        field_evidence: Optional[Dict[str, Any]],
        error_msg: str
    ) -> Dict[str, Any]:
        """Construct partial mapping results using regex and heuristic evidence."""

        evidence_map = field_evidence or {}
        field_mappings: Dict[str, Any] = {}
        confidences: List[float] = []

        for field in template_fields:
            field_name = field.get('field_name')
            if not field_name:
                continue

            metadata = {
                'data_type': field.get('data_type'),
                'required': bool(field.get('required', False)),
                'regex_hint': field.get('regex_hint'),
                'ocr_psm': field.get('ocr_psm'),
                'ocr_roi': field.get('ocr_roi')
            }

            mapping_entry = {
                'value': None,
                'confidence': 0.0,
                'source': 'Bulunamadı',
                'data_type': field.get('data_type'),
                'required': bool(field.get('required', False)),
                'metadata': metadata
            }

            evidence = evidence_map.get(field_name)
            value = self._extract_evidence_match(evidence)

            if value:
                confidence = self._evidence_confidence(evidence)
                mapping_entry['value'] = value
                mapping_entry['confidence'] = confidence
                mapping_entry['source'] = self._describe_evidence_source(evidence)
                confidences.append(confidence)

            field_mappings[field_name] = mapping_entry

        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        return {
            'field_mappings': field_mappings,
            'overall_confidence': overall_confidence,
            'error': error_msg
        }

    def _parse_ai_response(
        self,
        response_text: str,
        template_fields: List[Dict[str, Any]],
        field_evidence: Optional[Dict[str, Any]] = None
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
            ai_result = self._safe_json_loads(response_text)

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

            result.pop('error', None)
            return result

        except json.JSONDecodeError as e:
            self._log_parse_failure(response_text, e)
            partial = self._build_partial_mapping_from_evidence(
                template_fields,
                field_evidence,
                "JSON parse hatası"
            )
            logger.warning("JSON parse hatası sonrası regex tabanlı kısmi sonuç döndürülüyor")
            return partial
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
