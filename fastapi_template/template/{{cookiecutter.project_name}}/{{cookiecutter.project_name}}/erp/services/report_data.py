"""ERPNext report row builders — aging buckets and replica field shapes."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


def parse_ageing_ranges(raw: str | None) -> list[int]:
    if not raw:
        return [30, 60, 90, 120]
    out: list[int] = []
    for part in raw.replace(" ", "").split(","):
        if part.isdigit():
            out.append(int(part))
    return out or [30, 60, 90, 120]


def age_bucket(days: int, ranges: list[int]) -> int:
    if days <= 0:
        return 0
    for idx, upper in enumerate(ranges, start=1):
        if days <= upper:
            return idx
    return len(ranges) + 1


def ageing_columns(ranges: list[int]) -> list[dict[str, str]]:
    cols = [
        {"field": "posting_date", "label": "Posting Date"},
        {"field": "party_type", "label": "Party Type"},
        {"field": "party", "label": "Party"},
        {"field": "party_account", "label": "Party Account"},
        {"field": "voucher_type", "label": "Voucher Type"},
        {"field": "voucher_no", "label": "Voucher No"},
        {"field": "due_date", "label": "Due Date"},
        {"field": "payment_term", "label": "Payment Term"},
        {"field": "invoiced", "label": "Invoiced"},
        {"field": "paid", "label": "Paid"},
        {"field": "credit_note", "label": "Credit Note"},
        {"field": "outstanding", "label": "Outstanding"},
        {"field": "age", "label": "Age (Days)"},
    ]
    for idx, upper in enumerate(ranges):
        cols.append({"field": f"range{idx + 1}", "label": f"{upper} Days"})
    cols.append({"field": f"range{len(ranges) + 1}", "label": f"Above {ranges[-1]} Days"})
    return cols


def build_receivable_row(
    *,
    party_type: str,
    party: str,
    party_account: str,
    voucher_type: str,
    voucher_no: str,
    posting_date: date,
    due_date: date,
    amount: float,
    outstanding: float,
    report_date: date,
    ranges: list[int],
    currency: str = "USD",
    payment_term: str = "",
) -> dict[str, Any]:
    age_days = max((report_date - due_date).days, 0)
    paid = round(amount - outstanding, 2)
    bucket = age_bucket(age_days, ranges)
    row: dict[str, Any] = {
        "posting_date": posting_date.isoformat(),
        "party_type": party_type,
        "party": party,
        "party_account": party_account,
        "voucher_type": voucher_type.replace("_", " ").title(),
        "voucher_no": voucher_no,
        "due_date": due_date.isoformat(),
        "payment_term": payment_term,
        "invoiced": amount,
        "paid": paid,
        "credit_note": 0.0,
        "outstanding": outstanding,
        "age": age_days,
        "currency": currency,
    }
    for idx in range(1, len(ranges) + 2):
        row[f"range{idx}"] = outstanding if bucket == idx else 0.0
    return row
