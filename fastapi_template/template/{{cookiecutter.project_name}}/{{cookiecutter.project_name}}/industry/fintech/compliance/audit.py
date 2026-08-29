from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class FintechAuditEvent:
    entry_id: str
    org_id: str
    external_reference: str
    actor_id: str
    created_at: datetime


def make_audit_event(entry_id: str, org_id: str, external_reference: str, actor_id: str) -> FintechAuditEvent:
    return FintechAuditEvent(
        entry_id=entry_id,
        org_id=org_id,
        external_reference=external_reference,
        actor_id=actor_id,
        created_at=datetime.now(timezone.utc),
    )
