"""Utility helpers for interacting with OpenAI responses and reasoning models."""
from __future__ import annotations

import inspect
import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)


def _method_accepts_keyword(method: Any, keyword: str) -> bool:
    """Return ``True`` if the callable ``method`` accepts ``keyword``.

    Some OpenAI SDK releases expose ``responses.create`` without ``**kwargs``
    support which causes ``TypeError`` when we pass optional parameters like
    ``response_format``.  The helper inspects the signature defensively and
    ensures we only forward the keyword when it is explicitly supported.
    """

    if method is None:
        return False

    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        return False

    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            return True

    return keyword in signature.parameters


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


def _normalize_content_block(item: Any) -> Optional[Dict[str, Any]]:
    """Convert mixed content inputs into Responses API content blocks."""

    if item is None:
        return None

    def _normalize_text_payload(value: Any) -> Dict[str, Any]:
        text_value = "" if value is None else str(value)
        return {"type": "input_text", "text": text_value}

    if isinstance(item, dict):
        block: Dict[str, Any] = dict(item)
        block_type = (block.get("type") or "").lower()

        if block_type in {"input_text", "text", "plain_text", "message"}:
            text_value = block.get("text")
            if text_value is None:
                text_value = block.get("value")
            return _normalize_text_payload(text_value)

        if block_type in {"input_image", "image"}:
            block["type"] = "input_image"
            return block

        if "text" in block:
            return _normalize_text_payload(block.get("text"))
        if "value" in block:
            return _normalize_text_payload(block.get("value"))

        return _normalize_text_payload(block)

    if isinstance(item, str):
        return {"type": "input_text", "text": item}

    return {"type": "input_text", "text": str(item)}


def _normalize_message_for_responses(message: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a chat message into Responses API compatible structure."""

    content = message.get("content")

    blocks: List[Dict[str, Any]] = []
    if isinstance(content, list):
        for item in content:
            block = _normalize_content_block(item)
            if block is not None:
                blocks.append(block)
    elif content is not None:
        block = _normalize_content_block(content)
        if block is not None:
            blocks.append(block)

    normalized_message = {key: value for key, value in message.items() if key != "content"}
    normalized_message["content"] = blocks

    return normalized_message


def _normalize_messages_for_responses(
    messages: Sequence[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Convert chat messages to the structure expected by Responses API."""

    return [_normalize_message_for_responses(message) for message in messages]


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
        "input": _normalize_messages_for_responses(messages),
        "reasoning": {"effort": reasoning_effort},
    }

    if response_format:
        if isinstance(response_format, dict):
            response_format_type = response_format.get("type")
        else:
            response_format_type = None
        if response_format_type == "json_object":
            request_kwargs["text"] = {"format": {"type": "json_object"}}
            logger.debug("Responses.create response_format json_object metne dönüştürüldü.")
        else:
            logger.debug(
                "Responses.create response_format desteklenmiyor, parametre atlandı: type=%s",
                response_format_type,
            )

    if temperature is not None:
        logger.debug("Reasoning modeli temperature parametresi yok sayıldı: %s", temperature)

    if extra_kwargs:
        unsupported_kwargs = {"temperature", "max_completion_tokens", "max_tokens"}
        filtered_kwargs = {
            key: value
            for key, value in extra_kwargs.items()
            if key not in unsupported_kwargs
        }
        dropped = set(extra_kwargs) - set(filtered_kwargs)
        if dropped:
            logger.debug(
                "Reasoning modeli desteklenmeyen ek parametreler yok sayıldı: %s",
                ", ".join(sorted(dropped)),
            )
        if filtered_kwargs:
            request_kwargs.update(filtered_kwargs)

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
