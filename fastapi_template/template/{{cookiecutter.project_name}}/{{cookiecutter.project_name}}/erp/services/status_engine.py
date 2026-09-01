"""ERPNext status_updater port — predicate-based status resolution."""

from __future__ import annotations

from typing import Any, Callable

StatusPredicate = Callable[[dict[str, Any]], bool]

# NK port of erpnext/controllers/status_updater.py status_map (core doctypes)
STATUS_MAP: dict[str, list[tuple[str, StatusPredicate | None]]] = {
    "Lead": [
        ("Converted", lambda d: bool(d.get("customer_id"))),
        ("Opportunity", lambda d: bool(d.get("opportunity_id"))),
        ("Lead", lambda d: True),
    ],
    "Opportunity": [
        ("Lost", lambda d: d.get("status") == "Lost"),
        ("Converted", lambda d: d.get("status") == "Converted"),
        ("Closed", lambda d: d.get("status") == "Closed"),
        ("Open", lambda d: True),
    ],
    "Quotation": [
        ("Cancelled", lambda d: d.get("docstatus") == 2),
        ("Ordered", lambda d: d.get("per_ordered", 0) >= 100),
        ("Partially Ordered", lambda d: 0 < d.get("per_ordered", 0) < 100),
        ("Open", lambda d: d.get("docstatus") == 1),
        ("Draft", lambda d: True),
    ],
    "sales_order": [
        ("Cancelled", lambda d: d.get("docstatus") == 2),
        ("Completed", lambda d: d.get("per_delivered", 0) >= 100 and d.get("per_billed", 0) >= 100 and d.get("docstatus") == 1),
        ("To Bill", lambda d: d.get("per_delivered", 0) >= 100 and d.get("per_billed", 0) < 100 and d.get("docstatus") == 1),
        ("To Deliver", lambda d: d.get("per_delivered", 0) < 100 and d.get("per_billed", 0) >= 100 and d.get("docstatus") == 1),
        ("To Deliver and Bill", lambda d: d.get("per_delivered", 0) < 100 and d.get("per_billed", 0) < 100 and d.get("docstatus") == 1),
        ("On Hold", lambda d: d.get("status") == "On Hold"),
        ("Closed", lambda d: d.get("status") == "Closed"),
        ("Draft", lambda d: True),
    ],
    "purchase_order": [
        ("Cancelled", lambda d: d.get("docstatus") == 2),
        ("Completed", lambda d: d.get("per_received", 0) >= 100 and d.get("per_billed", 0) >= 100 and d.get("docstatus") == 1),
        ("To Bill", lambda d: d.get("per_received", 0) >= 100 and d.get("per_billed", 0) < 100 and d.get("docstatus") == 1),
        ("To Receive", lambda d: d.get("per_received", 0) < 100 and d.get("per_billed", 0) >= 100 and d.get("docstatus") == 1),
        ("To Receive and Bill", lambda d: d.get("per_received", 0) < 100 and d.get("per_billed", 0) < 100 and d.get("docstatus") == 1),
        ("On Hold", lambda d: d.get("status") == "On Hold"),
        ("Draft", lambda d: True),
    ],
    "delivery_note": [
        ("Cancelled", lambda d: d.get("docstatus") == 2),
        ("Completed", lambda d: d.get("per_billed", 0) >= 100 and d.get("docstatus") == 1),
        ("Partially Billed", lambda d: 0 < d.get("per_billed", 0) < 100 and d.get("docstatus") == 1),
        ("To Bill", lambda d: d.get("per_billed", 0) == 0 and d.get("docstatus") == 1),
        ("Draft", lambda d: True),
    ],
    "purchase_receipt": [
        ("Cancelled", lambda d: d.get("docstatus") == 2),
        ("Completed", lambda d: d.get("per_billed", 0) >= 100 and d.get("docstatus") == 1),
        ("To Bill", lambda d: d.get("per_billed", 0) == 0 and d.get("docstatus") == 1),
        ("Draft", lambda d: True),
    ],
    "sales_invoice": [
        ("Cancelled", lambda d: d.get("docstatus") == 2),
        ("Paid", lambda d: d.get("outstanding_amount", 1) <= 0 and d.get("docstatus") == 1),
        ("Unpaid", lambda d: d.get("outstanding_amount", 0) > 0 and d.get("docstatus") == 1),
        ("Draft", lambda d: True),
    ],
    "Issue": [
        ("Closed", lambda d: d.get("status") == "Closed"),
        ("Resolved", lambda d: d.get("status") == "Resolved"),
        ("Open", lambda d: d.get("status") in ("Open", "Replied", "On Hold")),
    ],
    "work_order": [
        ("Cancelled", lambda d: d.get("docstatus") == 2),
        ("Completed", lambda d: d.get("status") == "Completed"),
        ("In Process", lambda d: d.get("status") == "In Process"),
        ("Submitted", lambda d: d.get("docstatus") == 1),
        ("Draft", lambda d: True),
    ],
    "stock_entry": [
        ("Cancelled", lambda d: d.get("docstatus") == 2),
        ("Submitted", lambda d: d.get("docstatus") == 1),
        ("Draft", lambda d: True),
    ],
    "payment_entry": [
        ("Cancelled", lambda d: d.get("docstatus") == 2),
        ("Submitted", lambda d: d.get("docstatus") == 1),
        ("Draft", lambda d: True),
    ],
    "material_request": [
        ("Cancelled", lambda d: d.get("docstatus") == 2),
        ("Pending", lambda d: d.get("status") == "Pending"),
        ("Submitted", lambda d: d.get("docstatus") == 1),
        ("Draft", lambda d: True),
    ],
    "timesheet": [
        ("Cancelled", lambda d: d.get("docstatus") == 2),
        ("Submitted", lambda d: d.get("docstatus") == 1),
        ("Draft", lambda d: True),
    ],
}


def resolve_status(doctype: str, doc: dict[str, Any]) -> str:
    """Return ERPNext-equivalent status label for a document dict."""
    rules = STATUS_MAP.get(doctype) or STATUS_MAP.get(doctype.replace("_", " ").title())
    if not rules:
        return str(doc.get("status") or "Draft")
    for label, predicate in rules:
        if predicate is None or predicate(doc):
            return label
    return str(doc.get("status") or "Draft")


def document_status_payload(row: Any) -> dict[str, Any]:
    """Build status predicate input from ErpDocument ORM row."""
    meta = row.meta or {}
    totals = row.totals or {}
    return {
        "docstatus": row.docstatus,
        "status": row.status,
        "per_delivered": row.per_delivered,
        "per_billed": row.per_billed,
        "per_received": meta.get("per_received", row.per_delivered),
        "per_ordered": meta.get("per_ordered", 0),
        "customer_id": str(row.customer_id) if row.customer_id else None,
        "opportunity_id": meta.get("opportunity_id"),
        "outstanding_amount": meta.get("outstanding_amount", totals.get("grand_total", 0)),
    }
