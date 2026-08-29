# mypy: ignore-errors
import uuid
from datetime import date, datetime, timezone

import pytest

from {{cookiecutter.project_name}}.industry.fintech.compliance.aml import AllowAllAmlChecker, DenyHighValueAmlChecker
from {{cookiecutter.project_name}}.industry.fintech.compliance.kyc import InMemoryKycProvider, KycStatus, assert_kyc_allows
from {{cookiecutter.project_name}}.industry.fintech.compliance.limits import LimitChecker, LimitExceededError
from {{cookiecutter.project_name}}.industry.fintech.ledger.models import LedgerDirection, LedgerLine
from {{cookiecutter.project_name}}.industry.fintech.ledger.service import LedgerService


@pytest.mark.anyio
async def test_limit_blocks() -> None:
    checker = LimitChecker(daily_limit_minor=1000, monthly_limit_minor=10000)
    checker.check_and_record("org1", 600)
    with pytest.raises(LimitExceededError):
        checker.check_and_record("org1", 600)


@pytest.mark.anyio
async def test_kyc_blocks_high_value() -> None:
    kyc = InMemoryKycProvider()
    kyc.set_status("org1", KycStatus.unverified)
    with pytest.raises(Exception):
        await assert_kyc_allows(kyc, "org1", amount_minor=200_00, threshold_minor=100_00)
    kyc.set_status("org1", KycStatus.verified)
    await assert_kyc_allows(kyc, "org1", amount_minor=200_00, threshold_minor=100_00)


@pytest.mark.anyio
async def test_aml_allow_all() -> None:
    checker = AllowAllAmlChecker()
    res = await checker.screen("org1", 999999)
    assert res.allowed


@pytest.mark.anyio
async def test_daily_summary() -> None:
    from {{cookiecutter.project_name}}.industry.fintech.compliance.reporting import daily_summary

    svc = LedgerService()

    async def post(amt: int, ref: str) -> None:
        eid = str(uuid.uuid4())
        lines = [
            LedgerLine(entry_id=eid, account_id="a1", amount_minor=amt, direction=LedgerDirection.debit),
            LedgerLine(entry_id=eid, account_id="a2", amount_minor=amt, direction=LedgerDirection.credit),
        ]
        await svc.post_transaction(lines, external_reference=ref, org_id="org1")

    await post(100, "r1")
    await post(200, "r2")
    today = datetime.now(timezone.utc).date()
    totals = daily_summary(svc, today)
    assert totals.get("a1") == 300
