from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class AuditEvent:
    event_id: str
    event_type: str
    session_id: str
    user_id: str
    action: str
    status: str
    details: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class AuditLogger:
    def __init__(self, log_path: str | Path):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._events: list[AuditEvent] = []

    def reset(self) -> None:
        self._events = []
        self.log_path.write_text("", encoding="utf-8")

    def append(self, event: AuditEvent) -> None:
        self._events.append(event)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def list_events(
        self,
        *,
        event_type: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        rows = self._events
        if event_type:
            rows = [row for row in rows if row.event_type == event_type]
        if action:
            rows = [row for row in rows if row.action == action]
        return [asdict(row) for row in rows[-limit:]]
