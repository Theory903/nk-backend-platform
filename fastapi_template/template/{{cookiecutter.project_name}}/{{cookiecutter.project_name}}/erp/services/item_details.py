"""NK port of erpnext/stock/get_item_details.py (session-aware subset)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.erp.services.masters import MastersService
from {{cookiecutter.project_name}}.erp.services.pricing import PricingService


class ItemDetailsService:
    def __init__(self, session: AsyncSession, *, org_id: str) -> None:
        self._session = session
        self._org_id = org_id
        self._masters = MastersService(session, org_id=org_id)
        self._pricing = PricingService()

    async def get(
        self,
        item_code: str,
        *,
        qty: float = 1.0,
        customer_id: str | None = None,
        supplier_id: str | None = None,
        warehouse: str | None = None,
        price_list: str | None = None,
    ) -> dict[str, object]:
        item = await self._masters.get_item_by_code(item_code)
        if item is None:
            return {"item_code": item_code, "found": False}
        rate = item.standard_rate
        if price_list == "Standard Selling":
            rate = item.standard_rate
        details = self._pricing.item_details(
            item_code=item.item_code,
            standard_rate=item.standard_rate,
            qty=qty,
            price_list_rate=rate,
            warehouse=warehouse,
        )
        details.update(
            {
                "found": True,
                "item_name": item.item_name,
                "stock_uom": item.stock_uom,
                "is_stock_item": item.is_stock_item,
                "customer_id": customer_id,
                "supplier_id": supplier_id,
                "price_list": price_list or "Standard Selling",
            }
        )
        return details
