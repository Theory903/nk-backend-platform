from bson import ObjectId
from bson.errors import InvalidId
from pydantic import BaseModel

from {{cookiecutter.project_name}}.data.adapters.mongo.documents import RecordDocument
from {{cookiecutter.project_name}}.data.models import Record


class BeanieRepository:
    """
    Repository protocol implementation over a Beanie document collection.

    Mongo owns identifier generation; external ids are converted to
    ObjectIds and malformed values behave as missing records.
    """

    async def get(self, record_id: str) -> BaseModel | None:
        object_id = _to_object_id(record_id)
        if object_id is None:
            return None
        document = await RecordDocument.get(object_id)
        return document.to_domain() if document else None

    async def create(self, item: BaseModel) -> BaseModel:
        record = _as_record(item)
        document = await RecordDocument.from_domain(record).insert()
        return document.to_domain()

    async def update(self, item: BaseModel) -> BaseModel:
        record = _as_record(item)
        if record.id is None:
            raise KeyError("id is required for update")
        object_id = _to_object_id(record.id)
        if object_id is None:
            raise KeyError(record.id)
        document = await RecordDocument.get(object_id)
        if document is None:
            raise KeyError(record.id)
        document.name = record.name
        await document.replace()
        return document.to_domain()

    async def delete(self, record_id: str) -> bool:
        object_id = _to_object_id(record_id)
        if object_id is None:
            return False
        document = await RecordDocument.get(object_id)
        if document is None:
            return False
        await document.delete()
        return True

    async def list(self, limit: int = 50, offset: int = 0) -> list[BaseModel]:
        documents = (
            await RecordDocument.find_all(skip=offset, limit=limit)
            .sort(+RecordDocument.created_at)
            .to_list()
        )
        return [document.to_domain() for document in documents]

    async def count(self) -> int:
        return await RecordDocument.count()


def _to_object_id(value: str) -> ObjectId | None:
    try:
        return ObjectId(value)
    except InvalidId:
        return None


def _as_record(item: BaseModel) -> Record:
    if isinstance(item, Record):
        return item
    raise TypeError(f"unsupported domain model: {type(item)!r}")
