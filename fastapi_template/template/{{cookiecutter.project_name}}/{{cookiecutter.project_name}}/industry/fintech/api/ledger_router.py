from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from {{cookiecutter.project_name}}.industry.fintech.compliance.aml import AllowAllAmlChecker, AmlChecker
from {{cookiecutter.project_name}}.industry.fintech.compliance.kyc import InMemoryKycProvider, KycProvider, assert_kyc_allows
from {{cookiecutter.project_name}}.industry.fintech.compliance.limits import LimitChecker, LimitExceededError
from {{cookiecutter.project_name}}.industry.fintech.ledger.models import LedgerLine
from {{cookiecutter.project_name}}.industry.fintech.ledger.service import (
    DuplicateReferenceError,
    LedgerInvariantError,
    LedgerService,
)

_ledger = LedgerService()
_kyc: KycProvider = InMemoryKycProvider()
_aml: AmlChecker = AllowAllAmlChecker()
_limits = LimitChecker()


def get_ledger() -> LedgerService:
    return _ledger


def get_kyc() -> KycProvider:
    return _kyc


def get_aml() -> AmlChecker:
    return _aml


def get_limits() -> LimitChecker:
    return _limits


router = APIRouter(prefix="/fintech/ledger", tags=["fintech"])


@router.post("/transactions")
async def post_transaction(
    lines: list[LedgerLine],
    external_reference: str,
    org_id: str,
    ledger: Annotated[LedgerService, Depends(get_ledger)],
    kyc: Annotated[KycProvider, Depends(get_kyc)],
    aml: Annotated[AmlChecker, Depends(get_aml)],
    limits: Annotated[LimitChecker, Depends(get_limits)],
) -> dict[str, str]:
    total = sum(ln.amount_minor for ln in lines)
    try:
        await assert_kyc_allows(kyc, org_id, total)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    screening = await aml.screen(org_id, total)
    if not screening.allowed:
        raise HTTPException(status_code=403, detail=screening.reason)
    try:
        limits.check_and_record(org_id, total)
        limits.check_and_record(f"{org_id}:{lines[0].account_id}" if lines else org_id, total)
    except LimitExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if not lines[0].entry_id:
        for ln in lines:
            ln.entry_id = str(uuid.uuid4())
    try:
        entry = await ledger.post_transaction(lines, external_reference, org_id)
    except DuplicateReferenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LedgerInvariantError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"entry_id": entry.id, "status": entry.status.value}


@router.get("/accounts/{account_id}/balance")
async def get_balance(
    account_id: str,
    ledger: Annotated[LedgerService, Depends(get_ledger)],
) -> dict[str, int]:
    return {"balance_minor": ledger.get_balance(account_id)}


@router.get("/accounts/{account_id}/statement")
async def get_statement(
    account_id: str,
    limit: int = 50,
    offset: int = 0,
    ledger: Annotated[LedgerService, Depends(get_ledger)] = Depends(get_ledger),  # type: ignore[assignment]
) -> list[LedgerLine]:
    return ledger.get_statement(account_id, limit=limit, offset=offset)


@router.post("/transactions/{entry_id}/approve")
async def approve(
    entry_id: str,
    approver_id: str,
    ledger: Annotated[LedgerService, Depends(get_ledger)],
) -> dict[str, str]:
    try:
        entry = await ledger.approve_entry(entry_id, approver_id)
    except (KeyError, LedgerInvariantError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"entry_id": entry.id, "status": entry.status.value}
