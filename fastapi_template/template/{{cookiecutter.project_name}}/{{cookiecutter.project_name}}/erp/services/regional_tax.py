"""Regional tax template application — ERPNext Sales Taxes and Charges Template port."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from {{cookiecutter.project_name}}.erp.schemas.transaction import TaxLine, TransactionDocument
from {{cookiecutter.project_name}}.erp.services.pricing import PricingService

_TEMPLATES_PATH = Path(__file__).resolve().parents[1] / "tax_templates.yaml"


class RegionalTaxService:
    """Apply country/state tax templates to transaction documents."""

    def __init__(self) -> None:
        self._pricing = PricingService()
        self._templates = self._load_templates()

    def _load_templates(self) -> dict[str, Any]:
        if not _TEMPLATES_PATH.is_file():
            return {}
        data = yaml.safe_load(_TEMPLATES_PATH.read_text(encoding="utf-8")) or {}
        return data.get("templates") or {}

    def list_templates(self, *, country: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, tpl in self._templates.items():
            if country and tpl.get("country") not in {country, "*"}:
                continue
            rows.append(
                {
                    "id": key,
                    "title": tpl.get("title", key),
                    "country": tpl.get("country"),
                    "state": tpl.get("state"),
                    "tax_category": tpl.get("tax_category"),
                    "tax_count": len(tpl.get("taxes") or []),
                }
            )
        return rows

    def apply_template(
        self,
        doc: TransactionDocument,
        template_id: str,
    ) -> tuple[TransactionDocument, dict[str, Any]]:
        tpl = self._templates.get(template_id)
        if tpl is None:
            raise KeyError(f"tax template {template_id!r} not found")
        taxes = [
            TaxLine(
                description=str(row.get("description") or "Tax"),
                rate=float(row.get("rate") or 0),
                charge_type=str(row.get("charge_type") or "On Net Total"),
                included_in_print_rate=bool(row.get("included_in_print_rate", False)),
            )
            for row in tpl.get("taxes") or []
        ]
        enriched = doc.model_copy(update={"taxes": taxes})
        totals = self._pricing.calculate(enriched)
        return enriched, {
            "template_id": template_id,
            "title": tpl.get("title"),
            "tax_category": tpl.get("tax_category"),
            "totals": totals.model_dump(),
        }

    def resolve_template(
        self,
        *,
        country: str,
        state: str | None = None,
        tax_category: str | None = None,
    ) -> str | None:
        """Pick best-matching template id for country/state/category."""
        candidates: list[tuple[int, str]] = []
        for key, tpl in self._templates.items():
            tpl_country = str(tpl.get("country") or "")
            if tpl_country not in {country, "*"}:
                continue
            score = 0
            if tpl_country == country:
                score += 2
            if state and tpl.get("state") == state:
                score += 3
            if tax_category and tpl.get("tax_category") == tax_category:
                score += 2
            candidates.append((score, key))
        if not candidates:
            return None
        candidates.sort(key=lambda x: (-x[0], x[1]))
        return candidates[0][1]
