# -*- coding: utf-8 -*-
"""Utilities for delegating handwriting-heavy fields to an expert LLM."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.config import settings

try:  # pragma: no cover - prefer modern OpenAI client
    from openai import AuthenticationError, OpenAI, OpenAIError
except ImportError:  # pragma: no cover - fallback for legacy client
    OpenAI = None  # type: ignore
    try:
        import openai  # type: ignore
    except ImportError:  # pragma: no cover - library not available
        openai = None  # type: ignore

    try:
        from openai.error import AuthenticationError, OpenAIError  # type: ignore
    except ImportError:  # pragma: no cover - final fallback
        AuthenticationError = Exception
        OpenAIError = Exception
else:  # pragma: no cover - compatibility shim
    try:
        import openai  # type: ignore
    except ImportError:  # pragma: no cover - handle missing legacy client
        openai = None  # type: ignore

logger = logging.getLogger(__name__)


FieldConfigMap = Dict[str, Dict[str, Any]]
FieldMapping = Dict[str, Dict[str, Any]]


def determine_specialist_candidates(
    template_fields: Iterable[Dict[str, Any]],
    primary_mapping: FieldMapping,
    *,
    low_confidence_floor: float,
    allowed_tiers: Iterable[str],
) -> FieldConfigMap:
    """Return field definitions that should be routed to the specialist model."""

    tier_set = {tier.strip().lower() for tier in allowed_tiers if tier}
    candidates: FieldConfigMap = {}
    normalized_fields: Dict[str, Dict[str, Any]] = {}

    for field in template_fields or []:
        if not isinstance(field, dict):
            continue
        name = str(field.get("field_name", "")).strip()
        if not name:
            continue
        normalized_fields[name] = field

        tier = str(field.get("llm_tier", "standard")).strip().lower() or "standard"
        handwriting_flag = bool(field.get("auto_detected_handwriting"))

        if tier in tier_set or handwriting_flag:
            candidates[name] = field

    for field_name, mapping in (primary_mapping or {}).items():
        try:
            confidence = float(mapping.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0

        threshold = normalized_fields.get(field_name, {}).get("handwriting_threshold")
        if threshold in (None, ""):
            threshold = low_confidence_floor

        try:
            threshold_value = float(threshold)
        except (TypeError, ValueError):
            threshold_value = low_confidence_floor

        if confidence < threshold_value:
            field_def = normalized_fields.get(field_name)
            if field_def:
                candidates[field_name] = field_def

    return candidates


def merge_field_mappings(
    primary_mapping: FieldMapping,
    specialist_mapping: FieldMapping,
) -> FieldMapping:
    """Combine primary and specialist mapping results into a single map."""

    merged: FieldMapping = {}

    for field_name, payload in (primary_mapping or {}).items():
        if not isinstance(payload, dict):
            continue

        merged[field_name] = {
            "value": payload.get("value"),
            "confidence": float(payload.get("confidence", 0.0) or 0.0),
            "source": payload.get("source", "llm-primary"),
            "evidence": payload.get("evidence"),
        }

    for field_name, payload in (specialist_mapping or {}).items():
        if not isinstance(payload, dict):
            continue

        specialist_conf = float(payload.get("confidence", 0.0) or 0.0)
        specialist_value = payload.get("value")
        specialist_source = payload.get("source", "llm-specialist")

        existing = merged.get(field_name)
        if not existing or specialist_conf >= existing.get("confidence", 0.0):
            merged[field_name] = {
                "value": specialist_value,
                "confidence": specialist_conf,
                "source": specialist_source,
                "evidence": payload.get("evidence"),
            }
            if existing:
                alternates = existing.get("alternates") or []
                alternates.append({
                    "value": existing.get("value"),
                    "confidence": existing.get("confidence", 0.0),
                    "source": existing.get("source", "llm-primary"),
                })
                merged[field_name]["alternates"] = alternates
        else:
            alternates = existing.get("alternates") or []
            alternates.append({
                "value": specialist_value,
                "confidence": specialist_conf,
                "source": specialist_source,
            })
            existing["alternates"] = alternates

    return merged


class HandwritingInterpreter:
    """Specialist LLM client that focuses on handwriting-heavy fields."""

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        *,
        temperature: Optional[float] = None,
        context_window: Optional[int] = None,
    ) -> None:
        self.api_key = api_key
        self.model = model or settings.AI_HANDWRITING_MODEL
        self.temperature = (
            settings.AI_HANDWRITING_TEMPERATURE if temperature is None else temperature
        )
        self.context_window = (
            settings.AI_HANDWRITING_CONTEXT_WINDOW
            if context_window is None
            else context_window
        )

        self._has_valid_api_key = bool(api_key and api_key.strip())
        self._client = None
        if self._has_valid_api_key:
            if OpenAI is not None:  # pragma: no cover - requires modern SDK
                self._client = OpenAI(api_key=api_key)
            else:  # pragma: no cover - legacy SDK
                if openai is not None:
                    openai.api_key = api_key  # type: ignore[union-attr]
                else:
                    logger.warning(
                        "Uzman modeli için OpenAI legacy istemcisi bulunamadı."
                    )
                    self._has_valid_api_key = False

    def build_prompt(
        self,
        ocr_result: Dict[str, Any],
        field_configs: FieldConfigMap,
        primary_mapping: FieldMapping,
        *,
        field_hints: Optional[Dict[str, Any]] = None,
        document_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a detailed prompt for the handwriting specialist model."""

        document_summary = {
            "word_count": ocr_result.get("word_count"),
            "extraction_source": ocr_result.get("source"),
            "average_confidence": ocr_result.get("average_confidence"),
        }

        base_text = (ocr_result.get("text") or "").strip()
        snippet = base_text[:1000]
        field_results = ocr_result.get("field_results") or {}

        sections: List[str] = []
        sections.append("Belge özeti: " + json.dumps(document_summary, ensure_ascii=False))
        if document_info:
            sections.append(
                "Belge metaverisi: " + json.dumps(document_info, ensure_ascii=False)
            )
        sections.append("Genel OCR metin önizlemesi (ilk 1000 karakter):\n" + snippet)

        hints = field_hints or {}

        for field_name, config in field_configs.items():
            primary_data = primary_mapping.get(field_name, {})
            field_context = {
                "field_config": config,
                "primary_suggestion": primary_data,
                "field_ocr": field_results.get(field_name, {}),
                "hint": hints.get(field_name),
            }
            sections.append(
                f"Alan: {field_name}\n" + json.dumps(field_context, ensure_ascii=False)
            )

        instructions = (
            "Lütfen sadece JSON döndür. Şema: {\"field_mappings\": {"
            "<alan_adı>: {\"value\": str | null, \"confidence\": float, \"notes\": str?}}}."
            " Değerleri tahmin ederken OCR bağlamını ve ipuçlarını kullan."
        )
        sections.append("Çıktı Talimatı: " + instructions)

        return "\n\n".join(sections)

    def interpret_fields(
        self,
        ocr_result: Dict[str, Any],
        field_configs: FieldConfigMap,
        primary_mapping: FieldMapping,
        *,
        field_hints: Optional[Dict[str, Any]] = None,
        document_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Invoke the specialist model and parse the mapping response."""

        if not field_configs:
            return {"field_mappings": {}, "message": "No specialist fields requested."}

        prompt = self.build_prompt(
            ocr_result,
            field_configs,
            primary_mapping,
            field_hints=field_hints,
            document_info=document_info,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "Sen el yazısı çözümleme uzmanısın."
                    " Lütfen değerleri dikkatle değerlendir ve sadece JSON döndür."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        if not self._has_valid_api_key:
            logger.warning("Uzman modeli çağrılmadı: API anahtarı eksik.")
            return {
                "field_mappings": {},
                "error": "OpenAI API key is missing for specialist model.",
                "prompt": prompt,
            }

        start_time = time.perf_counter()
        response_payload: Dict[str, Any] = {
            "field_mappings": {},
            "prompt": prompt,
        }

        try:
            if self._client is not None:  # pragma: no cover - requires modern SDK
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_completion_tokens=self.context_window,
                    response_format={"type": "json_object"},
                )
                response_payload.update(self._parse_openai_response(response))
            elif openai is not None:  # pragma: no cover - legacy SDK
                response = openai.ChatCompletion.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.context_window,
                )
                response_payload.update(self._parse_openai_response(response))
            else:
                response_payload["error"] = "OpenAI client is not available."
                response_payload["latency_seconds"] = time.perf_counter() - start_time
                return response_payload

            latency = time.perf_counter() - start_time
            response_payload["latency_seconds"] = latency

            usage = response_payload.get("usage") or {}
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            if prompt_tokens or completion_tokens:
                total = (prompt_tokens or 0) + (completion_tokens or 0)
                response_payload["estimated_cost"] = self._estimate_cost(total)

        except AuthenticationError:
            logger.exception("Uzman modeli kimlik doğrulama hatası")
            response_payload["error"] = "Authentication failed for specialist model."
        except OpenAIError as exc:  # pragma: no cover - requires API access
            logger.exception("Uzman modeli çağrısı başarısız")
            response_payload["error"] = str(exc)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.exception("Uzman modeli beklenmeyen hata")
            response_payload["error"] = str(exc)

        return response_payload

    @staticmethod
    def _parse_openai_response(response: Any) -> Dict[str, Any]:
        """Normalize responses from both modern and legacy OpenAI SDKs."""

        if response is None:
            return {"field_mappings": {}, "error": "Empty response from specialist model."}

        content: Optional[str] = None
        if hasattr(response, "output") and response.output:  # pragma: no cover
            content = response.output[0].content[0].text  # type: ignore[attr-defined]
        elif hasattr(response, "choices") and response.choices:
            first_choice = response.choices[0]
            if hasattr(first_choice, "message"):
                content = getattr(first_choice.message, "content", None)
            else:
                content = getattr(first_choice, "text", None)

        if not content:
            return {"field_mappings": {}, "error": "Specialist model returned no content."}

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Uzman modeli JSON parse edilemedi: %s", content[:200])
            return {
                "field_mappings": {},
                "error": "Failed to parse specialist model response.",
                "raw_response": content,
            }

        field_mappings = data.get("field_mappings")
        if not isinstance(field_mappings, dict):
            return {
                "field_mappings": {},
                "error": "Specialist model response missing field_mappings.",
                "raw_response": data,
            }

        normalized: FieldMapping = {}
        for field_name, payload in field_mappings.items():
            if not isinstance(payload, dict):
                continue
            normalized[field_name] = {
                "value": payload.get("value"),
                "confidence": float(payload.get("confidence", 0.0) or 0.0),
                "source": "llm-specialist",
                "notes": payload.get("notes"),
            }

        usage = getattr(response, "usage", None)
        usage_payload = None
        if usage:
            usage_payload = {
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            }

        return {"field_mappings": normalized, "usage": usage_payload}

    @staticmethod
    def _estimate_cost(total_tokens: int) -> float:
        """Very rough heuristic for cost calculation (token-based)."""

        if not total_tokens:
            return 0.0

        # Heuristic: assume $0.00002 per token (~$0.02 per 1K tokens)
        return round(total_tokens * 0.00002, 6)


class ExpertModelExecutor:
    """Manage sequential or parallel specialist model calls."""

    def __init__(
        self,
        interpreter: HandwritingInterpreter,
        *,
        max_workers: Optional[int] = None,
    ) -> None:
        self.interpreter = interpreter
        self.max_workers = max_workers or 1
        self._executor: Optional[ThreadPoolExecutor]
        if self.max_workers > 1:
            self._executor = ThreadPoolExecutor(max_workers=self.max_workers)
        else:
            self._executor = None

    def dispatch(self, tasks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute specialist inference tasks sequentially or in parallel."""

        results: List[Dict[str, Any]] = []
        task_list = list(tasks or [])
        if not task_list:
            return results

        start_time = time.perf_counter()

        if self._executor:
            futures: List[Future] = []
            for task in task_list:
                futures.append(
                    self._executor.submit(
                        self.interpreter.interpret_fields,
                        task["ocr_result"],
                        task["field_configs"],
                        task.get("primary_mapping", {}),
                        field_hints=task.get("field_hints"),
                        document_info=task.get("document_info"),
                    )
                )

            for future in futures:
                results.append(future.result())
        else:
            for task in task_list:
                results.append(
                    self.interpreter.interpret_fields(
                        task["ocr_result"],
                        task["field_configs"],
                        task.get("primary_mapping", {}),
                        field_hints=task.get("field_hints"),
                        document_info=task.get("document_info"),
                    )
                )

        elapsed = time.perf_counter() - start_time
        logger.info(
            "Uzman modeli çağrıları tamamlandı: task_count=%s, toplam_süre=%.3fs",
            len(task_list),
            elapsed,
        )

        total_cost = sum(
            result.get("estimated_cost", 0.0)
            for result in results
            if isinstance(result, dict)
        )
        if total_cost:
            logger.info("Uzman modeli tahmini maliyet: $%.4f", total_cost)

        return results

    def close(self) -> None:
        """Release underlying thread pool resources."""

        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

