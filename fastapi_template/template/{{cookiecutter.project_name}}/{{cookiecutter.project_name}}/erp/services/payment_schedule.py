"""Payment schedule builder — ERPNext payment terms port."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


DEFAULT_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "net-30": [{"payment_term": "Net 30", "invoice_portion": 100.0, "credit_days": 30}],
    "30-70": [
        {"payment_term": "Advance 30%", "invoice_portion": 30.0, "credit_days": 0},
        {"payment_term": "Balance 70%", "invoice_portion": 70.0, "credit_days": 30},
    ],
    "50-50": [
        {"payment_term": "Advance 50%", "invoice_portion": 50.0, "credit_days": 0},
        {"payment_term": "Balance 50%", "invoice_portion": 50.0, "credit_days": 15},
    ],
}


def build_payment_schedule(
    grand_total: float,
    posting_date: date,
    *,
    terms: list[dict[str, Any]] | None = None,
    template_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return payment schedule rows with due dates and amounts."""
    if terms:
        source = terms
    elif template_id and template_id in DEFAULT_TEMPLATES:
        source = DEFAULT_TEMPLATES[template_id]
    else:
        source = DEFAULT_TEMPLATES["net-30"]

    schedule: list[dict[str, Any]] = []
    allocated = 0.0
    for idx, term in enumerate(source):
        portion = float(term.get("invoice_portion") or term.get("portion") or 0)
        credit_days = int(term.get("credit_days") or term.get("due_days") or 0)
        if idx == len(source) - 1:
            amount = round(grand_total - allocated, 2)
        else:
            amount = round(grand_total * portion / 100.0, 2)
            allocated += amount
        due_date = posting_date + timedelta(days=credit_days)
        schedule.append(
            {
                "payment_term": str(term.get("payment_term") or term.get("description") or f"Term {idx + 1}"),
                "invoice_portion": portion,
                "credit_days": credit_days,
                "due_date": due_date.isoformat(),
                "payment_amount": amount,
                "outstanding": amount,
                "paid_amount": 0.0,
            }
        )
    return schedule


def split_outstanding_by_schedule(
    schedule: list[dict[str, Any]],
    total_outstanding: float,
) -> list[dict[str, Any]]:
    """Allocate remaining outstanding across terms proportionally."""
    if not schedule or total_outstanding <= 0:
        return schedule
    total = sum(float(row.get("payment_amount") or 0) for row in schedule) or 1.0
    rows: list[dict[str, Any]] = []
    remaining = total_outstanding
    for idx, term in enumerate(schedule):
        share = float(term.get("payment_amount") or 0) / total
        if idx == len(schedule) - 1:
            outstanding = round(remaining, 2)
        else:
            outstanding = round(total_outstanding * share, 2)
            remaining -= outstanding
        rows.append({**term, "outstanding": outstanding, "paid_amount": float(term.get("payment_amount") or 0) - outstanding})
    return rows
