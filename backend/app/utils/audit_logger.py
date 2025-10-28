"""Helper utilities for writing audit trail entries."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.database import AuditLog


logger = logging.getLogger(__name__)


class AuditLogger:
    """Persist audit log entries without disrupting primary flows."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def log_event(
        self,
        event_type: str,
        resource_type: str,
        resource_id: Optional[int] = None,
        *,
        user_id: Optional[int] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[AuditLog]:
        entry = AuditLog(
            event_type=event_type,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id,
            description=description,
            payload=metadata,
            ip_address=ip_address,
        )

        try:
            add = getattr(self._db, "add", None)
            if callable(add):
                add(entry)

            commit = getattr(self._db, "commit", None)
            if callable(commit):
                commit()

            refresh = getattr(self._db, "refresh", None)
            if callable(refresh):
                refresh(entry)

            logger.debug(
                "Audit log kaydedildi: event=%s, resource=%s:%s",
                event_type,
                resource_type,
                resource_id,
            )
            return entry
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.error("Audit log kaydedilemedi: %s", exc)
            rollback = getattr(self._db, "rollback", None)
            if callable(rollback):
                try:
                    rollback()
                except Exception:  # pragma: no cover - defensive
                    logger.debug("Audit log rollback başarısız", exc_info=True)
            return None


__all__ = ["AuditLogger"]

