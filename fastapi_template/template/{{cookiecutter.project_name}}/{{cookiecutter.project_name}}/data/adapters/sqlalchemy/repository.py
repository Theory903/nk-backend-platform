from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from {{cookiecutter.project_name}}.data.adapters.sqlalchemy.persistence import RecordRow
from {{cookiecutter.project_name}}.data.models import Record


class SqlalchemyRepository:
    """
    Repository protocol implementation over a scoped AsyncSession.

    Commits belong to the caller's unit of work; this class only flushes.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, record_id: str) -> BaseModel | None:
        row = await self.session.get(RecordRow, record_id)
        return row.to_domain() if row else None

    async def create(self, item: BaseModel) -> BaseModel:
        row = RecordRow.from_domain(_as_record(item))
        self.session.add(row)
        await self.session.flush()
        return row.to_domain()

    async def update(self, item: BaseModel) -> BaseModel:
        record = _as_record(item)
        if record.id is None:
            raise KeyError("id is required for update")
        row = await self.session.get(RecordRow, record.id)
        if row is None:
            raise KeyError(record.id)
        row.name = record.name
        await self.session.flush()
        return row.to_domain()

    async def delete(self, record_id: str) -> bool:
        result = await self.session.execute(
            sa_delete(RecordRow).where(RecordRow.id == record_id),
        )
        await self.session.flush()
        return bool(result.rowcount)

    async def list(self, limit: int = 50, offset: int = 0) -> list[BaseModel]:
        rows = await self.session.execute(
            select(RecordRow)
            .order_by(RecordRow.created_at, RecordRow.id)
            .limit(limit)
            .offset(offset),
        )
        return [row.to_domain() for row in rows.scalars().fetchall()]

    async def count(self) -> int:
        total = await self.session.execute(select(func.count()).select_from(RecordRow))
        return int(total.scalar_one())


def _as_record(item: BaseModel) -> Record:
    if isinstance(item, Record):
        return item
    raise TypeError(f"unsupported domain model: {type(item)!r}")
