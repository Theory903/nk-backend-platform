"""Transaction document schemas — NK port of ERPNext taxes_and_totals inputs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ItemLine(BaseModel):
    item_code: str | None = None
    qty: float = Field(default=1.0, ge=0)
    rate: float = Field(default=0.0)
    amount: float | None = None
    discount_percentage: float = Field(default=0.0, ge=0, le=100)
    item_tax_rate: float | None = None
    is_alternative: bool = False


class TaxLine(BaseModel):
    description: str = ""
    rate: float = Field(default=0.0)
    tax_amount: float | None = None
    charge_type: str = "On Net Total"
    included_in_print_rate: bool = False
    row_id: int | None = None


class TransactionDocument(BaseModel):
    """Minimal transaction payload for pricing/tax calculation."""

    currency: str = "USD"
    conversion_rate: float = Field(default=1.0, gt=0)
    apply_discount_on: str = "Grand Total"
    additional_discount_percentage: float = Field(default=0.0, ge=0, le=100)
    discount_amount: float = Field(default=0.0, ge=0)
    items: list[ItemLine] = Field(default_factory=list)
    taxes: list[TaxLine] = Field(default_factory=list)
    shipping_amount: float = Field(default=0.0, ge=0)


class TransactionTotals(BaseModel):
    net_total: float
    total_taxes: float
    discount_amount: float
    shipping_amount: float
    grand_total: float
    item_lines: list[dict[str, float | str | None]]
    base_net_total: float = 0.0
    base_grand_total: float = 0.0
    rounding_adjustment: float = 0.0
    rounded_total: float = 0.0
    tax_rows: list[dict[str, float | str | bool | None]] = Field(default_factory=list)
