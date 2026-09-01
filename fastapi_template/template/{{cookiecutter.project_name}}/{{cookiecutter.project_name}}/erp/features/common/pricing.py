"""Pricing facade — delegates to erp.services.pricing."""

from __future__ import annotations

from {{cookiecutter.project_name}}.erp.schemas.transaction import TransactionDocument, TransactionTotals
from {{cookiecutter.project_name}}.erp.services.pricing import PricingService

_service = PricingService()


def calculate_totals(doc: TransactionDocument) -> TransactionTotals:
    return _service.calculate(doc)


def calculate_totals_stub(cart_json: str) -> dict[str, object]:
    """Backward-compatible JSON helper for agent tools."""
    import json

    try:
        payload = json.loads(cart_json) if cart_json.strip().startswith("{") else {"items": []}
    except json.JSONDecodeError:
        payload = {"items": [], "raw": cart_json[:500]}
    doc = TransactionDocument.model_validate(payload)
    totals = _service.calculate(doc)
    return totals.model_dump()
