from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pymongo import DESCENDING, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.domain.runs import Run, RunError, RunStatus

COLLECTION = "invoice_runs"


def _to_mongo(run: Run) -> dict[str, Any]:
    data = run.model_dump(exclude={"id"})
    data["_id"] = run.id
    return data


def _from_mongo(data: dict[str, Any]) -> Run:
    return Run(id=data.pop("_id"), **data)


class MongoRunRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self._runs = database[COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._runs.create_index([("created_at", DESCENDING)])
        await self._runs.create_index("decision")

    async def insert(self, run: Run) -> None:
        await self._runs.insert_one(_to_mongo(run))

    async def save(self, run: Run) -> None:
        run.updated_at = datetime.now(UTC)
        await self._runs.replace_one({"_id": run.id}, _to_mongo(run))

    async def get(self, run_id: str) -> Run | None:
        data = await self._runs.find_one({"_id": run_id})
        return _from_mongo(data) if data else None

    async def list(self, limit: int, offset: int) -> tuple[list[Run], int]:
        cursor = self._runs.find({}).sort("created_at", DESCENDING).skip(offset).limit(limit)
        runs = [_from_mongo(data) async for data in cursor]
        return runs, await self._runs.count_documents({})

    async def list_decided(self) -> list[Run]:
        cursor = self._runs.find({"decision": {"$ne": None}}).sort("created_at", DESCENDING)
        return [_from_mongo(data) async for data in cursor]

    async def delete_unless_working(self, run_id: str) -> Run | None:
        # Atomic, so a run can't start working between a check and the delete.
        data = await self._runs.find_one_and_delete(
            {"_id": run_id, "status": {"$nin": [RunStatus.QUEUED, RunStatus.RUNNING]}}
        )
        return _from_mongo(data) if data else None

    async def claim_awaiting_po(self, run_id: str) -> Run | None:
        # Atomic, so a double submit can't resume the same run twice.
        data = await self._runs.find_one_and_update(
            {"_id": run_id, "status": RunStatus.AWAITING_PO},
            {"$set": {"status": RunStatus.RUNNING, "updated_at": datetime.now(UTC)}},
            return_document=ReturnDocument.AFTER,
        )
        return _from_mongo(data) if data else None

    async def fail_unfinished(self, error: RunError) -> int:
        result = await self._runs.update_many(
            {"status": {"$in": [RunStatus.QUEUED, RunStatus.RUNNING]}},
            {
                "$set": {
                    "status": RunStatus.FAILED,
                    "error": error.model_dump(),
                    "updated_at": datetime.now(UTC),
                }
            },
        )
        return result.modified_count
