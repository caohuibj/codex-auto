"""Append-only structured audit logging with secret redaction."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codex_auto.models import AuditEvent, TaskState

_SECRET_KEY = re.compile(r"(api[_-]?key|authorization|token|secret|password)", re.IGNORECASE)
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _BEARER.sub("Bearer [REDACTED]", value)
    return value


class JsonlAuditLog:
    def __init__(self, path: str | Path, task_id: str, max_payload_chars: int = 20_000) -> None:
        self.path = Path(path)
        self.task_id = task_id
        self.max_payload_chars = max_payload_chars
        self._sequence = self._last_sequence()

    def _last_sequence(self) -> int:
        if not self.path.exists():
            return 0
        last = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
                if value.get("task_id") == self.task_id:
                    last = max(last, int(value.get("sequence", 0)))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
        return last

    def append(self, event_type: str, state: TaskState, payload: dict[str, Any]) -> AuditEvent:
        self._sequence += 1
        clean_payload = redact(payload)
        serialized = json.dumps(clean_payload, ensure_ascii=False, default=str)
        if len(serialized) > self.max_payload_chars:
            clean_payload = {
                "truncated": True,
                "original_chars": len(serialized),
                "preview": serialized[: self.max_payload_chars],
            }
        event = AuditEvent(
            sequence=self._sequence,
            timestamp=datetime.now(UTC),
            task_id=self.task_id,
            event_type=event_type,
            state=state,
            payload=clean_payload,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json() + "\n")
        return event
