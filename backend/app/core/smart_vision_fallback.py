# -*- coding: utf-8 -*-
"""Fallback helper that invokes OpenAI Vision models when OCR quality is low."""
from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from ..utils.smart_openai import extract_reasoning_response_text

logger = logging.getLogger(__name__)

try:  # pragma: no cover - prefer modern OpenAI client when available
    from openai import OpenAI, OpenAIError
except Exception:  # pragma: no cover - importlib fallback for legacy SDKs
    OpenAI = None  # type: ignore
    try:  # pragma: no cover - legacy OpenAI SDK structure
        from openai.error import OpenAIError  # type: ignore
    except Exception:  # pragma: no cover - fallback to generic exception
        OpenAIError = Exception


@dataclass
class OCRQualityReport:
    """Represents the quality evaluation for OCR output."""

    score: float
    reasons: List[str]
    should_fallback: bool


class OCRQualityAnalyzer:
    """Detects low quality OCR extractions that should trigger vision fallback."""

    def __init__(
        self,
        *,
        min_average_confidence: float = 0.55,
        min_word_count: int = 5,
        allow_empty_text: bool = False,
    ) -> None:
        self.min_average_confidence = min_average_confidence
        self.min_word_count = min_word_count
        self.allow_empty_text = allow_empty_text

    def evaluate(self, ocr_result: Optional[Dict[str, Any]]) -> OCRQualityReport:
        """Return a quality report for the provided OCR result."""

        if not ocr_result:
            logger.debug("OCRQualityAnalyzer: boş OCR sonucu vision fallback'i tetikleyecek.")
            return OCRQualityReport(score=0.0, reasons=["empty_result"], should_fallback=True)

        text = (ocr_result.get("text") or "").strip()
        average_conf = float(ocr_result.get("average_confidence") or 0.0)
        word_count = int(ocr_result.get("word_count") or 0)
        reported_error = ocr_result.get("error")

        if not word_count and text:
            word_count = len(text.split())

        reasons: List[str] = []

        if reported_error:
            reasons.append("ocr_error")

        if not text:
            reasons.append("empty_text")
        elif word_count < self.min_word_count:
            reasons.append("low_word_count")

        if average_conf < self.min_average_confidence:
            reasons.append("low_confidence")

        if text and self.allow_empty_text:
            reasons = [reason for reason in reasons if reason != "empty_text"]

        # Combine heuristics into a bounded score [0, 1]
        confidence_component = max(min(average_conf, 1.0), 0.0)
        density_component = 1.0
        if self.min_word_count > 0:
            density_component = min(word_count / float(self.min_word_count), 1.0)

        score = round((confidence_component * 0.7) + (density_component * 0.3), 3)

        should_fallback = bool(reasons)

        logger.debug(
            "OCRQualityAnalyzer değerlendirmesi: score=%.2f, reasons=%s, fallback=%s",
            score,
            reasons,
            should_fallback,
        )

        return OCRQualityReport(score=score, reasons=reasons, should_fallback=should_fallback)


class SmartVisionFallback:
    """Orchestrates quality analysis and OpenAI Vision extraction."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        quality_analyzer: Optional[OCRQualityAnalyzer] = None,
        client: Any = None,
    ) -> None:
        self.model = model
        self._quality_analyzer = quality_analyzer or OCRQualityAnalyzer()
        self._client = client
        self._last_quality_report: Optional[OCRQualityReport] = None

        if self._client is None and OpenAI is not None and api_key:
            try:
                self._client = OpenAI(api_key=api_key)
                logger.debug("SmartVisionFallback OpenAI istemcisi hazırlandı (modern SDK).")
            except Exception as exc:  # pragma: no cover - requires SDK runtime
                logger.warning("OpenAI Vision istemcisi oluşturulamadı: %s", exc)
                self._client = None

        if not api_key:
            logger.warning("OpenAI Vision fallback API anahtarı belirtilmemiş.")

    @property
    def last_quality_report(self) -> Optional[OCRQualityReport]:
        """Return the most recent OCR quality report."""

        return self._last_quality_report

    def evaluate_quality(self, ocr_result: Optional[Dict[str, Any]]) -> OCRQualityReport:
        """Evaluate OCR output quality and memoize the report."""

        self._last_quality_report = self._quality_analyzer.evaluate(ocr_result)
        return self._last_quality_report

    def should_trigger_fallback(self, ocr_result: Optional[Dict[str, Any]]) -> bool:
        """Return ``True`` when the fallback should be executed."""

        report = self.evaluate_quality(ocr_result)
        return report.should_fallback

    # pylint: disable=too-many-locals
    def extract_with_vision(
        self,
        file_path: str,
        template_fields: Iterable[Dict[str, Any]],
        *,
        ocr_fallback: str = "",
    ) -> Dict[str, Any]:
        """Invoke the configured vision model and return parsed field mappings."""

        if not self._client:
            logger.warning("OpenAI Vision istemcisi hazır değil, fallback çalıştırılamadı.")
            return {"field_mappings": {}, "error": "client_unavailable"}

        instructions = self._build_instruction_prompt(template_fields, ocr_fallback)
        logger.debug("Vision fallback istemi hazırlandı: %s", instructions)

        response_payload: Any
        try:
            responses_api = getattr(self._client, "responses", None)
            if responses_api is not None and hasattr(responses_api, "create"):
                response_payload = responses_api.create(
                    model=self.model,
                    input=[
                        {
                            "role": "system",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": (
                                        "You are an intelligent OCR assistant. "
                                        "Extract the requested structured data with confidences."
                                    ),
                                }
                            ],
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": instructions},
                                {
                                    "type": "input_image",
                                    "image_url": f"file://{file_path}",
                                },
                            ],
                        },
                    ],
                )
            else:
                chat_api = getattr(self._client, "chat", None)
                completions = getattr(chat_api, "completions", None)
                if completions is None or not hasattr(completions, "create"):
                    logger.error("OpenAI istemcisi vision çağrısını desteklemiyor.")
                    return {"field_mappings": {}, "error": "unsupported_client"}

                response_payload = completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an intelligent OCR assistant. "
                                "Extract the requested structured data with confidences."
                            ),
                        },
                        {
                            "role": "user",
                            "content": instructions,
                        },
                    ],
                )
        except OpenAIError as exc:  # pragma: no cover - requires API access
            logger.error("OpenAI Vision çağrısı başarısız: %s", exc)
            return {"field_mappings": {}, "error": str(exc)}
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("OpenAI Vision beklenmeyen hata: %s", exc)
            return {"field_mappings": {}, "error": str(exc)}

        field_mappings = self._parse_field_mappings(response_payload)
        logger.info(
            "Vision fallback tamamlandı: alan_sayısı=%d, kaynak=%s",
            len(field_mappings),
            self.model,
        )

        return {
            "field_mappings": field_mappings,
            "raw_response": response_payload,
        }

    def _build_instruction_prompt(
        self,
        template_fields: Iterable[Dict[str, Any]],
        ocr_fallback: str,
    ) -> str:
        """Create a concise prompt guiding the vision model."""

        field_descriptions: List[str] = []
        for index, field in enumerate(template_fields):
            field_name = (field or {}).get("field_name") or (field or {}).get("name")
            if not field_name:
                field_name = f"field_{index + 1}"

            hint = (field or {}).get("hint")
            requirement = "(required)" if (field or {}).get("required") else ""
            description = f"- {field_name}{requirement}"
            if hint:
                description += f": {hint}"
            field_descriptions.append(description)

        field_block = "\n".join(field_descriptions) or "- Extract any key fields visible in the document."

        instructions = (
            "Analyze the provided document image and return a JSON object with a "
            "'field_mappings' dictionary. Each field must include 'value', 'confidence' "
            "(0-1 range) and 'source' set to 'vision'.\n"
            f"Fields to extract:\n{field_block}\n"
        )

        ocr_fallback = (ocr_fallback or "").strip()
        if ocr_fallback:
            instructions += (
                "\nPrevious OCR result was low quality. Use it as a rough hint when needed:\n"
                f"---\n{ocr_fallback}\n---\n"
            )

        instructions += "Return only valid JSON."
        return instructions

    def _parse_field_mappings(self, response_payload: Any) -> Dict[str, Dict[str, Any]]:
        """Extract the field mapping dictionary from OpenAI responses."""

        if isinstance(response_payload, dict):
            mappings = self._extract_from_dict(response_payload)
            if mappings:
                return mappings

        text_output = extract_reasoning_response_text(response_payload)
        if not text_output and isinstance(response_payload, dict):
            text_output = (
                response_payload.get("output_text")
                or response_payload.get("text")
            )

        if not text_output:
            choices = getattr(response_payload, "choices", None)
            if choices:
                texts = [
                    getattr(choice, "message", {}).get("content")
                    if isinstance(getattr(choice, "message", None), dict)
                    else getattr(choice, "text", "")
                    for choice in choices
                ]
                text_output = "\n".join([str(item or "").strip() for item in texts if item])

        if not text_output:
            logger.warning("Vision fallback yanıtında çözümlenebilir metin bulunamadı.")
            return {}

        try:
            parsed = json.loads(text_output)
        except json.JSONDecodeError:
            logger.warning(
                "Vision fallback yanıtı JSON formatında değil: %s", text_output
            )
            return {}

        if isinstance(parsed, dict):
            mappings = self._extract_from_dict(parsed)
            if mappings:
                return mappings

        logger.warning("Vision fallback yanıtından alan eşleşmeleri çıkarılamadı.")
        return {}

    @staticmethod
    def _extract_from_dict(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract normalized mappings from dictionary payload."""

        if "field_mappings" in payload and isinstance(payload["field_mappings"], dict):
            return _normalize_field_mapping(payload["field_mappings"])

        if "fields" in payload and isinstance(payload["fields"], dict):
            return _normalize_field_mapping(payload["fields"])

        return {}


def _normalize_field_mapping(mapping: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Ensure mapping entries contain confidence and source metadata."""

    normalized: Dict[str, Dict[str, Any]] = {}

    for field_name, entry in mapping.items():
        if entry is None:
            continue

        if isinstance(entry, dict):
            value = entry.get("value")
            confidence = entry.get("confidence", entry.get("score", 0.0))
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = 0.0

            normalized[field_name] = {
                "value": value,
                "confidence": confidence,
                "source": entry.get("source", "vision"),
            }

            alternates = entry.get("alternates")
            if isinstance(alternates, list):
                normalized[field_name]["alternates"] = alternates
            continue

        normalized[field_name] = {
            "value": entry,
            "confidence": 0.0,
            "source": "vision",
        }

    return normalized


def merge_ocr_and_vision_results(
    ocr_mappings: Optional[Dict[str, Dict[str, Any]]],
    vision_mappings: Optional[Dict[str, Dict[str, Any]]],
) -> Dict[str, Dict[str, Any]]:
    """Merge OCR and vision mappings preferring the highest confidence."""

    merged: Dict[str, Dict[str, Any]] = {}

    if ocr_mappings:
        merged = copy.deepcopy(ocr_mappings)

    if not vision_mappings:
        return merged

    for field_name, vision_entry in vision_mappings.items():
        if not isinstance(vision_entry, dict):
            continue

        existing = merged.get(field_name)
        vision_conf = float(vision_entry.get("confidence") or 0.0)

        if not existing:
            merged[field_name] = copy.deepcopy(vision_entry)
            merged[field_name].setdefault("source", "vision")
            continue

        ocr_conf = float(existing.get("confidence") or 0.0)

        if vision_conf > ocr_conf:
            alternates = _build_alternates(existing)
            vision_copy = copy.deepcopy(vision_entry)
            if alternates:
                vision_copy.setdefault("alternates", []).extend(alternates)
            else:
                vision_copy.setdefault("alternates", []).append(
                    {
                        "value": existing.get("value"),
                        "confidence": ocr_conf,
                        "source": existing.get("source", "ocr"),
                    }
                )
            merged[field_name] = vision_copy
        else:
            alternates = _build_alternates(vision_entry)
            if alternates:
                existing.setdefault("alternates", []).extend(alternates)
            existing.setdefault("alternates", []).append(
                {
                    "value": vision_entry.get("value"),
                    "confidence": vision_conf,
                    "source": vision_entry.get("source", "vision"),
                }
            )

    return merged


def _build_alternates(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return normalized alternates list for an entry."""

    alternates_raw = entry.get("alternates")
    if not isinstance(alternates_raw, list):
        return []

    alternates: List[Dict[str, Any]] = []
    for item in alternates_raw:
        if not isinstance(item, dict):
            continue
        alternates.append(
            {
                "value": item.get("value"),
                "confidence": float(item.get("confidence") or 0.0),
                "source": item.get("source", entry.get("source", "vision")),
            }
        )
    return alternates
