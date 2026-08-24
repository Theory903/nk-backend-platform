from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class SqlalchemyUnitOfWork:
    """
    Unit of work over the application's async session factory.

    Entering opens a transaction; commit finalizes it, rollback discards.
    Exiting without commit rolls back automatically.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> "SqlalchemyUnitOfWork":
        self.session = self._session_factory()
        await self.session.begin()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        assert self.session is not None
        try:
            if not self._committed:
                await self.session.rollback()
        finally:
            await self.session.close()
            self.session = None

    async def commit(self) -> None:
        assert self.session is not None
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        assert self.session is not None
        await self.session.rollback()
