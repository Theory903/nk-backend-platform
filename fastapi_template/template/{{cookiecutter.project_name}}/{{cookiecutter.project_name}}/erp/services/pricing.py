"""NK port of ERPNext taxes_and_totals — full calculation pipeline (no Frappe)."""

from __future__ import annotations

from {{cookiecutter.project_name}}.erp.schemas.transaction import (
    ItemLine,
    TaxLine,
    TransactionDocument,
    TransactionTotals,
)

NOT_APPLICABLE_TAX = -1
CURRENCY_PRECISION = 2
QTY_PRECISION = 6


def flt(value: float | None, precision: int = CURRENCY_PRECISION) -> float:
    if value is None:
        return 0.0
    return round(float(value), precision)


class PricingService:
    """ERPNext-compatible tax and totals engine."""

    def calculate(self, doc: TransactionDocument) -> TransactionTotals:
        if not doc.items:
            return TransactionTotals(
                net_total=0.0,
                total_taxes=0.0,
                discount_amount=0.0,
                shipping_amount=0.0,
                grand_total=0.0,
                item_lines=[],
                base_net_total=0.0,
                base_grand_total=0.0,
                rounding_adjustment=0.0,
                rounded_total=0.0,
            )

        items = [self._calc_item_values(item, doc) for item in doc.items if not getattr(item, "is_alternative", False)]
        net_total = flt(sum(i["net_amount"] for i in items))
        base_net_total = flt(net_total * doc.conversion_rate)

        tax_rows = self._calculate_taxes(doc, items, net_total)
        total_taxes = flt(sum(t["tax_amount"] for t in tax_rows))

        discount = self._discount_amount(doc, net_total)
        if doc.apply_discount_on == "Grand Total" and discount:
            net_after_discount = max(net_total - discount, 0.0)
            # Recompute proportional tax after grand-total discount
            if net_total:
                ratio = net_after_discount / net_total
                total_taxes = flt(total_taxes * ratio)
                for t in tax_rows:
                    t["tax_amount"] = flt(t["tax_amount"] * ratio)
            net_total = net_after_discount

        shipping = flt(doc.shipping_amount)
        grand_total = flt(net_total + total_taxes + shipping)
        rounding = self._rounding_adjustment(grand_total, doc.currency)
        rounded_total = flt(grand_total + rounding)

        return TransactionTotals(
            net_total=net_total,
            total_taxes=total_taxes,
            discount_amount=flt(discount),
            shipping_amount=shipping,
            grand_total=grand_total,
            item_lines=items,
            base_net_total=flt(net_total * doc.conversion_rate),
            base_grand_total=flt(rounded_total * doc.conversion_rate),
            rounding_adjustment=rounding,
            rounded_total=rounded_total,
            tax_rows=tax_rows,
        )

    def _calc_item_values(self, item: ItemLine, doc: TransactionDocument) -> dict:
        qty = flt(item.qty, QTY_PRECISION)
        rate = flt(item.rate)
        if item.amount is not None:
            amount = flt(item.amount)
        else:
            amount = flt(qty * rate)
        if item.discount_percentage:
            amount = flt(amount * (1 - item.discount_percentage / 100.0))
        net_amount = amount
        if any(t.included_in_print_rate for t in doc.taxes):
            net_amount = self._exclusive_net_amount(item, doc, amount, qty)
        return {
            "item_code": item.item_code,
            "qty": qty,
            "rate": rate,
            "amount": amount,
            "net_rate": flt(net_amount / qty if qty else net_amount),
            "net_amount": net_amount,
            "item_tax_rate": item.item_tax_rate,
            "tax_amount": 0.0,
            "base_net_amount": flt(net_amount * doc.conversion_rate),
        }

    def _exclusive_net_amount(
        self, item: ItemLine, doc: TransactionDocument, amount: float, qty: float
    ) -> float:
        total_slope = 0.0
        for tax in doc.taxes:
            if not tax.included_in_print_rate:
                continue
            rate = item.item_tax_rate if item.item_tax_rate is not None else tax.rate
            if tax.charge_type == "On Net Total":
                total_slope += rate / 100.0
            elif tax.charge_type == "Actual":
                continue
            elif tax.charge_type == "On Item Quantity" and qty:
                amount -= flt(rate * qty)
        if total_slope:
            return flt(amount / (1 + total_slope))
        return amount

    def _calculate_taxes(
        self,
        doc: TransactionDocument,
        items: list[dict],
        net_total: float,
    ) -> list[dict]:
        if not doc.taxes:
            for row in items:
                rate = row.get("item_tax_rate")
                if rate:
                    row["tax_amount"] = flt(float(row["net_amount"]) * float(rate) / 100.0)
            return []

        rows: list[dict] = []
        running_net = net_total
        for tax in doc.taxes:
            tax_amount = tax.tax_amount
            if tax.charge_type == "Actual" and tax_amount is not None:
                amount = flt(tax_amount)
            elif tax.charge_type == "On Net Total":
                base = net_total
                amount = flt(base * tax.rate / 100.0)
            elif tax.charge_type == "On Previous Row Amount" and rows:
                amount = flt(rows[-1]["tax_amount"] * tax.rate / 100.0)
            else:
                amount = flt(running_net * tax.rate / 100.0)
            if tax.included_in_print_rate:
                amount = 0.0
            rows.append(
                {
                    "description": tax.description,
                    "rate": tax.rate,
                    "charge_type": tax.charge_type,
                    "tax_amount": amount,
                    "included_in_print_rate": tax.included_in_print_rate,
                }
            )
            running_net += amount
        return rows

    def _discount_amount(self, doc: TransactionDocument, net_total: float) -> float:
        if doc.discount_amount:
            return min(flt(doc.discount_amount), net_total)
        if doc.additional_discount_percentage:
            return flt(net_total * doc.additional_discount_percentage / 100.0)
        return 0.0

    def _rounding_adjustment(self, grand_total: float, currency: str) -> float:
        # ERPNext-style nearest 0.05 for common currencies
        if currency.upper() in {"USD", "EUR", "GBP", "INR"}:
            rounded = round(grand_total * 20) / 20
            return flt(rounded - grand_total)
        return 0.0

    def item_details(
        self,
        *,
        item_code: str,
        standard_rate: float,
        qty: float = 1.0,
        item_tax_rate: float | None = None,
        price_list_rate: float | None = None,
        warehouse: str | None = None,
    ) -> dict[str, object]:
        rate = price_list_rate if price_list_rate is not None else standard_rate
        doc = TransactionDocument(
            items=[ItemLine(item_code=item_code, qty=qty, rate=rate, item_tax_rate=item_tax_rate)],
        )
        totals = self.calculate(doc)
        row = totals.item_lines[0] if totals.item_lines else {}
        return {
            "item_code": item_code,
            "qty": qty,
            "rate": rate,
            "price_list_rate": rate,
            "amount": row.get("amount", 0.0),
            "net_amount": row.get("net_amount", 0.0),
            "item_tax_rate": item_tax_rate,
            "grand_total": totals.rounded_total or totals.grand_total,
            "warehouse": warehouse or "Stores - Default",
            "stock_uom": "Nos",
        }
