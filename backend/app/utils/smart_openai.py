"""Utility helpers for interacting with OpenAI responses and reasoning models."""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _iter_content_items(output: Iterable[Any]) -> Iterable[Any]:
    """Yield individual content items from a reasoning response output list."""

    for block in output:
        content = getattr(block, "content", None)
        if content is None and isinstance(block, dict):
            content = block.get("content")

        if not content:
            continue

        for item in content:
            if item is None:
                continue
            yield item


def _text_value_from_piece(piece: Any) -> Optional[str]:
    """Extract string value from a response content piece."""

    if isinstance(piece, dict):
        text_obj = piece.get("text")
        value = piece.get("value")
    else:
        text_obj = getattr(piece, "text", None)
        value = getattr(piece, "value", None)

    if value:
        value_str = str(value).strip()
        if value_str:
            return value_str

    if text_obj is None and isinstance(piece, dict):
        text_obj = piece.get("value")

    if text_obj is None:
        return None

    if isinstance(text_obj, dict):
        value = text_obj.get("value") or text_obj.get("text")
        if value:
            value_str = str(value).strip()
            if value_str:
                return value_str

    value_attr = getattr(text_obj, "value", None)
    if value_attr:
        value_str = str(value_attr).strip()
        if value_str:
            return value_str

    text_attr = getattr(text_obj, "text", None)
    if text_attr:
        value_str = str(text_attr).strip()
        if value_str:
            return value_str

    text_str = str(text_obj).strip()
    return text_str or None


def extract_reasoning_response_text(response: Any) -> Optional[str]:
    """Return concatenated text value from a modern reasoning response."""

    if response is None:
        return None

    output = getattr(response, "output", None)
    if not output and isinstance(response, dict):
        output = response.get("output")

    if output:
        parts: List[str] = []
        for piece in _iter_content_items(output):
            text = _text_value_from_piece(piece)
            if text:
                parts.append(text)
        combined = "".join(parts).strip()
        if combined:
            return combined

    output_text = getattr(response, "output_text", None)
    if output_text:
        output_text = str(output_text).strip()
        if output_text:
            return output_text

    return None


def _call_reasoning_model(
    client: Any,
    *,
    model: str,
    messages: Sequence[Dict[str, Any]],
    response_format: Optional[Dict[str, Any]] = None,
    temperature: Optional[float] = None,
    reasoning_effort: str = "medium",
    extra_kwargs: Optional[Dict[str, Any]] = None,
) -> Any:
    """Invoke OpenAI Responses API for reasoning models with consistent defaults."""

    request_kwargs: Dict[str, Any] = {
        "model": model,
        "input": messages,
        "reasoning": {"effort": reasoning_effort},
    }

    if response_format:
        request_kwargs["response_format"] = response_format

    if temperature is not None:
        request_kwargs["temperature"] = temperature

    if extra_kwargs:
        request_kwargs.update(extra_kwargs)

    logger.debug(
        "Calling reasoning model: model=%s, has_response_format=%s", model, bool(response_format)
    )

    return client.responses.create(**request_kwargs)


def call_reasoning_model(
    client: Any,
    *,
    model: str,
    messages: Sequence[Dict[str, Any]],
    response_format: Optional[Dict[str, Any]] = None,
    temperature: Optional[float] = None,
    reasoning_effort: str = "medium",
    extra_kwargs: Optional[Dict[str, Any]] = None,
) -> Any:
    """Public wrapper around :func:`_call_reasoning_model`."""

    return _call_reasoning_model(
        client,
        model=model,
        messages=messages,
        response_format=response_format,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        extra_kwargs=extra_kwargs,
    )


__all__ = [
    "call_reasoning_model",
    "extract_reasoning_response_text",
]
