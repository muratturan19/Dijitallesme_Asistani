"""Utilities for masking and unmasking sensitive data before LLM calls."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, MutableMapping, Optional


logger = logging.getLogger(__name__)


@dataclass
class MaskPattern:
    """Helper describing a masking rule."""

    label: str
    pattern: re.Pattern[str]


class DataMasker:
    """Masks sensitive strings such as phone numbers and emails."""

    _PATTERNS: List[MaskPattern] = [
        MaskPattern(
            "IBAN",
            re.compile(r"(?<!\w)(?:TR\s?\d{2}(?:\s?\d{4}){5}\s?\d{0,2}|TR\s?\d{24})(?!\w)", re.IGNORECASE),
        ),
        MaskPattern(
            "TC",
            re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)"),
        ),
        MaskPattern(
            "PHONE",
            re.compile(r"(?<!\d)(?:\+?90[-\s]?|0)?\d{3}[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2}(?!\d)"),
        ),
        MaskPattern(
            "EMAIL",
            re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
        ),
    ]

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled
        self._counter = 0
        self._value_to_token: Dict[str, str] = {}
        self._token_to_value: Dict[str, str] = {}

    def mask_text(self, text: Optional[str]) -> Optional[str]:
        if not self.enabled or not text:
            return text

        masked = text
        for pattern in self._PATTERNS:
            masked = pattern.pattern.sub(
                lambda match: self._store_replacement(pattern.label, match.group(0)),
                masked,
            )

        return masked

    def mask_messages(self, messages: Iterable[MutableMapping[str, Any]]) -> List[Dict[str, Any]]:
        return [self._mask_structure(message) for message in messages]

    def mask_structure(self, payload: Any) -> Any:
        return self._mask_structure(payload)

    def unmask_text(self, text: Optional[str]) -> Optional[str]:
        if not self.enabled or not text:
            return text

        unmasked = text
        for token, original in self._token_to_value.items():
            unmasked = unmasked.replace(token, original)

        return unmasked

    def unmask_structure(self, payload: Any) -> Any:
        if not self.enabled:
            return payload

        if isinstance(payload, str):
            return self.unmask_text(payload)

        if isinstance(payload, list):
            return [self.unmask_structure(item) for item in payload]

        if isinstance(payload, dict):
            return {key: self.unmask_structure(value) for key, value in payload.items()}

        return payload

    def has_tokens(self) -> bool:
        return bool(self._token_to_value)

    def _store_replacement(self, label: str, value: str) -> str:
        existing = self._value_to_token.get(value)
        if existing:
            return existing

        self._counter += 1
        token = f"__{label}_MASK_{self._counter}__"
        self._value_to_token[value] = token
        self._token_to_value[token] = value
        logger.debug("Veri maskelendi: label=%s, token=%s", label, token)
        return token

    def _mask_structure(self, payload: Any) -> Any:
        if not self.enabled:
            return payload

        if isinstance(payload, str):
            return self.mask_text(payload)

        if isinstance(payload, list):
            return [self._mask_structure(item) for item in payload]

        if isinstance(payload, dict):
            return {key: self._mask_structure(value) for key, value in payload.items()}

        return payload


__all__ = ["DataMasker"]

