from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

MAX_MINOR = 2**63 - 1


class AccountType(StrEnum):
    asset = "asset"
    liability = "liability"
    equity = "equity"
    revenue = "revenue"
    expense = "expense"


class JournalStatus(StrEnum):
    posted = "posted"
    pending_approval = "pending_approval"


class LedgerDirection(StrEnum):
    debit = "debit"
    credit = "credit"


class Account(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$", description="ISO 4217")
    type: AccountType
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("currency")
    @classmethod
    def upper_currency(cls, v: str) -> str:
        return v.upper()


class JournalEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    org_id: str
    external_reference: str
    status: JournalStatus = JournalStatus.posted
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"frozen": True}


class LedgerLine(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    entry_id: str
    account_id: str
    amount_minor: int = Field(ge=0, le=MAX_MINOR)
    direction: LedgerDirection

    @field_validator("amount_minor")
    @classmethod
    def check_minor(cls, v: int) -> int:
        if not isinstance(v, int):
            raise ValueError("amount_minor must be int minor units, never float")
        if v < 0 or v > MAX_MINOR:
            raise ValueError(f"amount_minor out of range 0..{MAX_MINOR}")
        return v
