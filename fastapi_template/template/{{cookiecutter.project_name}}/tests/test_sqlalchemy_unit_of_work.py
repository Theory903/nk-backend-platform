"""Unit tests for SqlalchemyUnitOfWork (explicit-commit semantics)."""

from __future__ import annotations

{%- if cookiecutter.orm == "sqlalchemy" %}
from unittest.mock import AsyncMock, MagicMock

import pytest

from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.unit_of_work import (
    SqlalchemyUnitOfWork,
    UnitOfWorkAlreadyCommittedError,
    UnitOfWorkError,
    UnitOfWorkNotActiveError,
)


def _make_session_factory() -> tuple[MagicMock, AsyncMock]:
    session = AsyncMock()
    session.begin = AsyncMock(return_value=MagicMock())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()

    factory = MagicMock(return_value=session)
    return factory, session


@pytest.mark.anyio
async def test_commit_on_success() -> None:
    factory, session = _make_session_factory()
    uow = SqlalchemyUnitOfWork(factory)

    async with uow:
        assert uow.is_active is True
        await uow.commit()
        assert uow.is_committed is True

    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()
    session.close.assert_awaited_once()
    assert uow.is_active is False
    assert uow.session is None


@pytest.mark.anyio
async def test_no_commit_rolls_back_on_clean_exit() -> None:
    factory, session = _make_session_factory()
    uow = SqlalchemyUnitOfWork(factory)

    async with uow:
        assert uow.is_active is True
        # Intentionally no commit — exit must rollback.

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    session.close.assert_awaited_once()
    assert uow.is_rolled_back is True
    assert uow.is_active is False


@pytest.mark.anyio
async def test_exception_rolls_back() -> None:
    factory, session = _make_session_factory()
    uow = SqlalchemyUnitOfWork(factory)

    with pytest.raises(RuntimeError, match="boom"):
        async with uow:
            raise RuntimeError("boom")

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
    session.close.assert_awaited_once()
    assert uow.is_rolled_back is True


@pytest.mark.anyio
async def test_double_commit_raises() -> None:
    factory, session = _make_session_factory()
    uow = SqlalchemyUnitOfWork(factory)

    async with uow:
        await uow.commit()
        with pytest.raises(UnitOfWorkAlreadyCommittedError):
            await uow.commit()

    session.commit.assert_awaited_once()


@pytest.mark.anyio
async def test_commit_after_rollback_raises() -> None:
    factory, session = _make_session_factory()
    uow = SqlalchemyUnitOfWork(factory)

    async with uow:
        await uow.rollback()
        with pytest.raises(UnitOfWorkError, match="rolled-back"):
            await uow.commit()

    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_failed_commit_rolls_back_and_reraises() -> None:
    factory, session = _make_session_factory()
    session.commit = AsyncMock(side_effect=RuntimeError("db down"))
    uow = SqlalchemyUnitOfWork(factory)

    async with uow:
        with pytest.raises(RuntimeError, match="db down"):
            await uow.commit()
        assert uow.is_rolled_back is True
        assert uow.is_committed is False

    session.rollback.assert_awaited()
    session.close.assert_awaited_once()


@pytest.mark.anyio
async def test_commit_when_not_active_raises() -> None:
    factory, _session = _make_session_factory()
    uow = SqlalchemyUnitOfWork(factory)

    with pytest.raises(UnitOfWorkNotActiveError):
        await uow.commit()


@pytest.mark.anyio
async def test_rollback_when_not_active_raises() -> None:
    factory, _session = _make_session_factory()
    uow = SqlalchemyUnitOfWork(factory)

    with pytest.raises(UnitOfWorkNotActiveError):
        await uow.rollback()


@pytest.mark.anyio
async def test_reenter_raises() -> None:
    factory, session = _make_session_factory()
    uow = SqlalchemyUnitOfWork(factory)

    async with uow:
        with pytest.raises(UnitOfWorkError, match="already active"):
            await uow.__aenter__()

    session.close.assert_awaited_once()


@pytest.mark.anyio
async def test_no_records_attribute() -> None:
    """UoW does not auto-wire repositories; callers build SqlalchemyRepository(session)."""
    factory, _session = _make_session_factory()
    uow = SqlalchemyUnitOfWork(factory)

    async with uow:
        assert not hasattr(uow, "records") or getattr(uow, "records", None) is None
        assert uow.session is not None

{%- else %}
import pytest


@pytest.mark.skip(reason="SqlalchemyUnitOfWork requires orm=sqlalchemy")
def test_sqlalchemy_unit_of_work_skipped() -> None:
    pass

{%- endif %}
