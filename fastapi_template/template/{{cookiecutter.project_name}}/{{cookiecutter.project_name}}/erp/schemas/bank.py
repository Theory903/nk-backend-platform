"""Bank transaction import schemas."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


class BankRowImport(BaseModel):
    bank_account: str = Field(default="Cash - NK", min_length=1)
    posting_date: date
    description: str = ""
    deposit: float = Field(default=0.0, ge=0)
    withdrawal: float = Field(default=0.0, ge=0)
    reference: str | None = None


class BankImportRequest(BaseModel):
    rows: list[BankRowImport] = Field(min_length=1)


class BankReconcileRequest(BaseModel):
    bank_transaction_id: uuid.UUID
    voucher_type: str = Field(min_length=1)
    voucher_id: uuid.UUID


class BankMatchSuggestion(BaseModel):
    bank_transaction_id: uuid.UUID
    voucher_type: str
    voucher_id: uuid.UUID
    amount: float
    score: float


class BankCsvImport(BaseModel):
    csv_text: str = Field(min_length=1)
    bank_account: str = Field(default="Cash - NK", min_length=1)
