from datetime import UTC, datetime
from typing import Any

from pymongo import DESCENDING
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.models import (
    Document,
    DocumentError,
    DocumentStatus,
    ExtractionResult,
)

COLLECTION = "documents"


def _to_mongo(document: Document) -> dict[str, Any]:
    data = document.model_dump(exclude={"id"})
    data["_id"] = document.id
    return data


def _from_mongo(data: dict[str, Any]) -> Document:
    return Document(id=data.pop("_id"), **data)


class MongoDocumentRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self._documents = database[COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._documents.create_index("sha256")
        await self._documents.create_index([("created_at", DESCENDING)])

    async def insert(self, document: Document) -> None:
        await self._documents.insert_one(_to_mongo(document))

    async def delete(self, document_id: str) -> None:
        await self._documents.delete_one({"_id": document_id})

    async def get(self, document_id: str) -> Document | None:
        data = await self._documents.find_one({"_id": document_id})
        return _from_mongo(data) if data else None

    async def list(self, limit: int, offset: int) -> tuple[list[Document], int]:
        cursor = (
            self._documents.find({}, {"pages": 0})
            .sort("created_at", DESCENDING)
            .skip(offset)
            .limit(limit)
        )
        documents = [_from_mongo(data) async for data in cursor]
        return documents, await self._documents.count_documents({})

    async def mark_processing(self, document_id: str) -> None:
        await self._set(document_id, {"status": DocumentStatus.PROCESSING})

    async def save_result(self, document_id: str, result: ExtractionResult) -> None:
        await self._set(
            document_id,
            {"status": DocumentStatus.COMPLETED, **result.model_dump()},
        )

    async def mark_failed(self, document_id: str, error: DocumentError) -> None:
        await self._set(
            document_id,
            {"status": DocumentStatus.FAILED, "error": error.model_dump()},
        )

    async def fail_unfinished(self, error: DocumentError) -> int:
        result = await self._documents.update_many(
            {"status": {"$in": [DocumentStatus.QUEUED, DocumentStatus.PROCESSING]}},
            {
                "$set": {
                    "status": DocumentStatus.FAILED,
                    "error": error.model_dump(),
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        return result.modified_count

    async def _set(self, document_id: str, fields: dict[str, Any]) -> None:
        await self._documents.update_one(
            {"_id": document_id},
            {"$set": {**fields, "updated_at": datetime.now(UTC)}},
        )
