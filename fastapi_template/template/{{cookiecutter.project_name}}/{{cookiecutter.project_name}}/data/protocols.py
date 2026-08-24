from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@runtime_checkable
class Repository(Protocol):
    """
    Uniform persistence contract implemented by every storage adapter.

    Application code depends on this protocol only; adapters are selected
    through configuration and must satisfy the shared contract suite.
    """

    async def get(self, record_id: str) -> BaseModel | None:
        """Return the record with the given id or None."""
        ...

    async def create(self, item: BaseModel) -> BaseModel:
        """Persist a new record and return it with its assigned id."""
        ...

    async def update(self, item: BaseModel) -> BaseModel:
        """Replace an existing record; raises KeyError when absent."""
        ...

    async def delete(self, record_id: str) -> bool:
        """Delete by id; returns True when a row was removed."""
        ...

    async def list(self, limit: int = 50, offset: int = 0) -> list[BaseModel]:
        """Return records ordered by creation, paginated."""
        ...

    async def count(self) -> int:
        """Total number of stored records."""
        ...


@runtime_checkable
class UnitOfWork(Protocol):
    """
    Transaction boundary abstraction.

    SQL adapters map to real transactions; document adapters use sessions
    when the deployment supports multi-document transactions.
    """

    async def __aenter__(self) -> "UnitOfWork":
        ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...
