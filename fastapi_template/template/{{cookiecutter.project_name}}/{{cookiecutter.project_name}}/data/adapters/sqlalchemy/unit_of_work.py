"""SQLAlchemy async Unit of Work.

Provides an explicit transaction boundary around application operations.

Usage:

    async with SqlalchemyUnitOfWork(session_factory) as uow:
        repo = SqlalchemyRepository(uow.session)

        record = await repo.create(data)

        await uow.commit()

    # No commit -> automatic rollback.
    # Exception -> automatic rollback.
    # Session -> always closed.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class UnitOfWorkError(RuntimeError):
    """Base exception for Unit of Work failures."""


class UnitOfWorkNotActiveError(UnitOfWorkError):
    """Raised when an operation requires an active Unit of Work."""


class UnitOfWorkAlreadyCommittedError(UnitOfWorkError):
    """Raised when attempting to commit an already committed transaction."""


class SqlalchemyUnitOfWork:
    """
    Transactional Unit of Work for SQLAlchemy async sessions.

    Guarantees:

      - one session per unit of work
      - one transaction per unit of work
      - explicit commit
      - automatic rollback on exception
      - automatic rollback when commit was not requested
      - session cleanup on every exit
      - no transaction ownership leakage to repositories

    Repositories should only flush.

    The Unit of Work owns commit/rollback.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

        self.session: AsyncSession | None = None
        self._transaction = None

        self._active = False
        self._committed = False
        self._rolled_back = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def __aenter__(self) -> SqlalchemyUnitOfWork:
        if self._active:
            raise UnitOfWorkError(
                "unit of work is already active",
            )

        self.session = self._session_factory()

        try:
            self._transaction = await self.session.begin()
            self._active = True
            return self

        except Exception:
            await self.session.close()
            self.session = None
            raise

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        tb: object,
    ) -> None:
        try:
            if self._active and not self._committed:
                await self.rollback()

        finally:
            if self.session is not None:
                await self.session.close()

            self.session = None
            self._transaction = None
            self._active = False

    # ------------------------------------------------------------------
    # Transaction control
    # ------------------------------------------------------------------

    async def commit(self) -> None:
        """
        Commit the current transaction.

        After a successful commit the Unit of Work is considered
        completed and cannot be committed again.
        """
        self._require_active()

        if self._committed:
            raise UnitOfWorkAlreadyCommittedError(
                "unit of work has already been committed",
            )

        if self._rolled_back:
            raise UnitOfWorkError(
                "cannot commit a rolled-back unit of work",
            )

        assert self.session is not None

        try:
            await self.session.commit()
            self._committed = True

        except Exception:
            # A failed commit must not leave the session's transaction
            # in an unusable state.
            try:
                await self.session.rollback()
            finally:
                self._rolled_back = True

            raise

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        self._require_active()

        if self._committed:
            return

        if self._rolled_back:
            return

        assert self.session is not None

        await self.session.rollback()

        self._rolled_back = True

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        """Whether this Unit of Work currently owns an active session."""
        return self._active

    @property
    def is_committed(self) -> bool:
        """Whether this Unit of Work successfully committed."""
        return self._committed

    @property
    def is_rolled_back(self) -> bool:
        """Whether this Unit of Work rolled back."""
        return self._rolled_back

    def _require_active(self) -> None:
        if not self._active or self.session is None:
            raise UnitOfWorkNotActiveError(
                "unit of work is not active; use it inside 'async with'",
            )


__all__ = [
    "SqlalchemyUnitOfWork",
    "UnitOfWorkError",
    "UnitOfWorkNotActiveError",
    "UnitOfWorkAlreadyCommittedError",
]