# mypy: ignore-errors
import uuid

import pytest

from {{cookiecutter.project_name}}.industry.fintech.ledger.models import (
    Account,
    AccountType,
    JournalEntry,
    LedgerDirection,
    LedgerLine,
    MAX_MINOR,
)
from {{cookiecutter.project_name}}.industry.fintech.ledger.service import (
    DuplicateReferenceError,
    ImmutableEntryError,
    LedgerInvariantError,
    LedgerService,
)


def _lines(entry_id: str, a1: str, a2: str, amount: int = 1000) -> list[LedgerLine]:
    return [
        LedgerLine(entry_id=entry_id, account_id=a1, amount_minor=amount, direction=LedgerDirection.debit),
        LedgerLine(entry_id=entry_id, account_id=a2, amount_minor=amount, direction=LedgerDirection.credit),
    ]


@pytest.mark.anyio
async def test_unbalanced_raises() -> None:
    svc = LedgerService()
    eid = str(uuid.uuid4())
    lines = [
        LedgerLine(entry_id=eid, account_id="a1", amount_minor=100, direction=LedgerDirection.debit),
        LedgerLine(entry_id=eid, account_id="a2", amount_minor=99, direction=LedgerDirection.credit),
    ]
    with pytest.raises(LedgerInvariantError):
        await svc.post_transaction(lines, external_reference="ref-1", org_id="org1")


@pytest.mark.anyio
async def test_balanced_persists_atomically() -> None:
    svc = LedgerService()
    eid = str(uuid.uuid4())
    lines = _lines(eid, "a1", "a2", 500)
    entry = await svc.post_transaction(lines, external_reference="ref-2", org_id="org1")
    assert entry.id == eid
    assert svc.get_balance("a1") == 500
    assert svc.get_balance("a2") == -500


@pytest.mark.anyio
async def test_balance_sum() -> None:
    svc = LedgerService()
    for amt in [100, 200]:
        eid = str(uuid.uuid4())
        await svc.post_transaction(_lines(eid, "a1", "a2", amt), external_reference=f"ref-{amt}", org_id="org1")
    assert svc.get_balance("a1") == 300


@pytest.mark.anyio
async def test_duplicate_external_reference_rejected() -> None:
    svc = LedgerService()
    eid1 = str(uuid.uuid4())
    await svc.post_transaction(_lines(eid1, "a1", "a2"), external_reference="dup", org_id="org1")
    eid2 = str(uuid.uuid4())
    with pytest.raises(DuplicateReferenceError):
        await svc.post_transaction(_lines(eid2, "a1", "a2"), external_reference="dup", org_id="org1")


@pytest.mark.anyio
async def test_immutable_guard() -> None:
    svc = LedgerService()
    eid = str(uuid.uuid4())
    await svc.post_transaction(_lines(eid, "a1", "a2"), external_reference="ref-imm", org_id="org1")
    with pytest.raises(ImmutableEntryError):
        svc.update_entry(eid, foo="bar")
    with pytest.raises(ImmutableEntryError):
        svc.delete_entry(eid)


@pytest.mark.anyio
async def test_overflow_rejected() -> None:
    svc = LedgerService()
    eid = str(uuid.uuid4())
    with pytest.raises(Exception):
        LedgerLine(entry_id=eid, account_id="a1", amount_minor=MAX_MINOR + 1, direction=LedgerDirection.debit)


@pytest.mark.anyio
async def test_maker_checker_threshold() -> None:
    svc = LedgerService(maker_checker_threshold_minor=1000)
    eid = str(uuid.uuid4())
    entry = await svc.post_transaction(_lines(eid, "a1", "a2", 2000), external_reference="ref-mc", org_id="org1")
    assert entry.status.value == "pending_approval"
    assert svc.get_balance("a1") == 0
    approved = await svc.approve_entry(eid, approver_id="mgr")
    assert approved.status.value == "posted"
    assert svc.get_balance("a1") == 2000
