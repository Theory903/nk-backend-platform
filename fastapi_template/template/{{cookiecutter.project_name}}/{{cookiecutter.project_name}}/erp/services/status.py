"""Status workflow engine — NK port of ERPNext status_updater predicates."""

from __future__ import annotations

from typing import Callable


StatusPredicate = Callable[[dict[str, object]], bool]


def lead_status(lead: dict[str, object]) -> str:
    if lead.get("status") == "Converted":
        return "Converted"
    if lead.get("status") in {"Do Not Contact", "Lost Quotation"}:
        return str(lead["status"])
    if lead.get("opportunity_id"):
        return "Opportunity"
    return str(lead.get("status") or "Lead")


def issue_status(issue: dict[str, object]) -> str:
    explicit = issue.get("status")
    if explicit in {"Open", "Replied", "On Hold", "Resolved", "Closed"}:
        return str(explicit)
    return "Open"


def apply_status_map(
    doc: dict[str, object],
    status_map: list[tuple[str, StatusPredicate]],
    *,
    default: str,
) -> str:
    for label, predicate in status_map:
        if predicate(doc):
            return label
    return default
