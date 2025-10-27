# -*- coding: utf-8 -*-
"""Learning service that captures user feedback and derives field hints."""

from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import CorrectionFeedback, TemplateField, TemplateFieldHint

logger = logging.getLogger(__name__)


class TemplateLearningService:
    """Persist user corrections and infer template field hints."""

    _LEARNING_HINT_TYPE = "auto_learning"

    _DATE_PATTERNS: Sequence[Tuple[re.Pattern[str], str]] = (
        (re.compile(r"^\d{4}-\d{2}-\d{2}$"), r"\d{4}-\d{2}-\d{2}"),
        (
            re.compile(r"^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$"),
            r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}",
        ),
    )
    _NUMBER_PATTERN = re.compile(r"^-?\d+(?:[.,]\d+)?$")
    _ALNUM_PATTERN = re.compile(r"^[A-Z0-9]+$")

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def record_correction(
        self,
        *,
        document_id: int,
        template_field_id: Optional[int],
        original_value: Optional[Any] = None,
        corrected_value: Optional[Any] = None,
        context: Optional[Dict[str, Any]] = None,
        created_by: Optional[int] = None,
    ) -> CorrectionFeedback:
        """Persist a user correction for later learning."""

        feedback_context = dict(context or {})
        original_text = None if original_value is None else str(original_value)
        corrected_text = None if corrected_value is None else str(corrected_value)

        feedback = CorrectionFeedback(
            document_id=document_id,
            template_field_id=template_field_id,
            original_value=original_text,
            corrected_value=corrected_text or "",
            feedback_context=feedback_context,
            created_by=created_by,
        )

        self.db.add(feedback)

        try:
            self.db.flush()
        except IntegrityError:
            logger.debug(
                "Correction feedback duplicate detected for document_id=%s, field_id=%s",
                document_id,
                template_field_id,
            )
            self.db.rollback()
            existing = (
                self.db.query(CorrectionFeedback)
                .filter(
                    CorrectionFeedback.document_id == document_id,
                    CorrectionFeedback.template_field_id == template_field_id,
                    CorrectionFeedback.corrected_value == corrected_text,
                )
                .first()
            )
            if existing:
                existing.original_value = original_text
                existing.feedback_context = feedback_context
                if created_by is not None:
                    existing.created_by = created_by
                self.db.flush()
                self.db.commit()
                return existing
            raise

        self.db.commit()
        return feedback

    def generate_field_hint(
        self,
        template_field_id: int,
        *,
        sample_limit: int = 50,
    ) -> Optional[TemplateFieldHint]:
        """Generate learning hints for a specific template field."""

        field = self.db.query(TemplateField).filter(
            TemplateField.id == template_field_id
        ).first()
        if not field:
            logger.warning("TemplateField %s not found for learning", template_field_id)
            return None

        if field.learning_enabled is False:
            logger.info(
                "TemplateField %s learning disabled; skipping hint generation",
                template_field_id,
            )
            return None

        corrections = (
            self.db.query(CorrectionFeedback)
            .filter(CorrectionFeedback.template_field_id == template_field_id)
            .order_by(CorrectionFeedback.created_at.desc())
            .limit(sample_limit)
            .all()
        )

        values = self._collect_corrected_values(corrections)

        if not values:
            logger.info(
                "No correction values available to learn from for field %s",
                template_field_id,
            )
            return None

        type_hint = self._infer_type(values)
        regex_pattern = self._infer_pattern(values, type_hint)

        hint_payload = self._build_hint_payload(values, type_hint, regex_pattern)

        hint = (
            self.db.query(TemplateFieldHint)
            .filter(
                TemplateFieldHint.template_field_id == template_field_id,
                TemplateFieldHint.hint_type == self._LEARNING_HINT_TYPE,
            )
            .first()
        )

        if hint:
            hint.hint_payload = hint_payload
        else:
            hint = TemplateFieldHint(
                template_field_id=template_field_id,
                hint_type=self._LEARNING_HINT_TYPE,
                hint_payload=hint_payload,
            )
            self.db.add(hint)

        if type_hint:
            field.auto_learned_type = type_hint
        field.last_learned_at = datetime.now(UTC)

        self.db.flush()
        self.db.commit()

        return hint

    def generate_template_hints(
        self, template_id: int, *, sample_limit: int = 50
    ) -> Dict[int, Dict[str, Any]]:
        """Generate learning hints for all fields in a template."""

        hints: Dict[int, Dict[str, Any]] = {}

        fields = (
            self.db.query(TemplateField)
            .filter(TemplateField.template_id == template_id)
            .all()
        )

        for field in fields:
            hint = self.generate_field_hint(field.id, sample_limit=sample_limit)
            if hint:
                hints[field.id] = hint.hint_payload

        return hints

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _collect_corrected_values(
        self, corrections: Iterable[CorrectionFeedback]
    ) -> List[str]:
        values: List[str] = []
        for feedback in corrections:
            value = (feedback.corrected_value or "").strip()
            if value:
                values.append(value)
        return values

    def _infer_type(self, values: Sequence[str]) -> Optional[str]:
        counters = Counter()

        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            if self._match_date(normalized):
                counters["date"] += 1
            elif self._match_number(normalized):
                counters["number"] += 1
            else:
                counters["text"] += 1

        if not counters:
            return None

        most_common = counters.most_common(1)[0]
        if most_common[1] >= max(1, len(values) // 2):
            return most_common[0]

        if counters.get("date") and counters["date"] >= counters.get("number", 0):
            return "date"
        if counters.get("number"):
            return "number"
        return "text"

    def _infer_pattern(
        self, values: Sequence[str], type_hint: Optional[str]
    ) -> Optional[str]:
        if not values:
            return None

        if type_hint == "date":
            pattern = self._dominant_date_pattern(values)
            if pattern:
                return pattern
            return r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"

        if type_hint == "number":
            return self._number_pattern(values)

        alnum_pattern = self._alphanumeric_pattern(values)
        if alnum_pattern:
            return alnum_pattern

        if len(set(values)) == 1:
            return re.escape(values[0])

        return None

    def _match_date(self, value: str) -> bool:
        for regex, _ in self._DATE_PATTERNS:
            if regex.match(value):
                return True
        return False

    def _dominant_date_pattern(self, values: Sequence[str]) -> Optional[str]:
        matches: Counter[str] = Counter()

        for value in values:
            for regex, pattern in self._DATE_PATTERNS:
                if regex.match(value):
                    matches[pattern] += 1

        if not matches:
            return None

        pattern, count = matches.most_common(1)[0]
        if count >= max(1, len(values) // 2):
            return pattern
        return None

    def _match_number(self, value: str) -> bool:
        normalized = value.replace(" ", "")
        normalized = normalized.replace("'", "")
        return bool(self._NUMBER_PATTERN.match(normalized))

    def _number_pattern(self, values: Sequence[str]) -> str:
        lengths = {
            len(re.sub(r"[^0-9]", "", value))
            for value in values
            if value
        }

        if not lengths:
            return r"-?\d+(?:[.,]\d+)?"

        if len(lengths) == 1:
            length = lengths.pop()
            return rf"-?\d{{{max(length, 1)}}}(?:[.,]\d+)?"

        max_length = max(lengths)
        return rf"-?\d{{1,{max_length}}}(?:[.,]\d+)?"

    def _alphanumeric_pattern(self, values: Sequence[str]) -> Optional[str]:
        alnum_values = [value for value in values if self._ALNUM_PATTERN.match(value)]
        if not alnum_values:
            return None

        lengths = {len(value) for value in alnum_values}
        if not lengths:
            return None

        if len(lengths) == 1:
            length = lengths.pop()
            return rf"[A-Z0-9]{{{length}}}"

        return rf"[A-Z0-9]{{{min(lengths)},{max(lengths)}}}"

    def _build_hint_payload(
        self,
        values: Sequence[str],
        type_hint: Optional[str],
        regex_pattern: Optional[str],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "source": "auto-learning",
            "examples": list(dict.fromkeys(values))[:5],
        }

        if type_hint:
            payload["type_hint"] = type_hint

        if regex_pattern:
            payload["regex_patterns"] = [
                {
                    "pattern": regex_pattern,
                    "flags": None,
                    "source": "auto-learning",
                }
            ]

        return payload


__all__ = ["TemplateLearningService"]

