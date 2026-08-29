from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone

from {{cookiecutter.project_name}}.industry.fintech.ledger.service import LedgerService


def daily_summary(service: LedgerService, day: date) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for lines in service._lines.values():  # noqa: SLF001
        entry = service._entries.get(lines[0].entry_id)  # noqa: SLF001
        if entry is None:
            continue
        entry_day = datetime.fromtimestamp(entry.created_at.timestamp(), tz=timezone.utc).date() if isinstance(entry.created_at, datetime) else entry.created_at
        if entry_day == day:
            for ln in lines:
                totals[ln.account_id] += ln.amount_minor
    return dict(totals)
