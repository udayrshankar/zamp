from datetime import UTC, datetime
from typing import Any

from pymongo import DESCENDING, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.domain.errors import DuplicatePurchaseOrderError
from app.domain.models import PurchaseOrder, PurchaseOrderData

COLLECTION = "purchase_orders"


def _to_mongo(purchase_order: PurchaseOrder) -> dict[str, Any]:
    data = purchase_order.model_dump(exclude={"id"})
    data["_id"] = purchase_order.id
    return data


def _from_mongo(data: dict[str, Any]) -> PurchaseOrder:
    return PurchaseOrder(id=data.pop("_id"), **data)


def _duplicate(po_number: str) -> DuplicatePurchaseOrderError:
    return DuplicatePurchaseOrderError(f"PO number {po_number} already exists.")


class MongoPurchaseOrderRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self._purchase_orders = database[COLLECTION]

    async def ensure_indexes(self) -> None:
        # The unique index, not a check before writing, is what stops two
        # simultaneous requests from creating the same PO number.
        await self._purchase_orders.create_index("po_number", unique=True)
        await self._purchase_orders.create_index([("created_at", DESCENDING)])

    async def insert(self, purchase_order: PurchaseOrder) -> None:
        try:
            await self._purchase_orders.insert_one(_to_mongo(purchase_order))
        except DuplicateKeyError as error:
            raise _duplicate(purchase_order.po_number) from error

    async def get(self, purchase_order_id: str) -> PurchaseOrder | None:
        data = await self._purchase_orders.find_one({"_id": purchase_order_id})
        return _from_mongo(data) if data else None

    async def list(self, limit: int, offset: int) -> tuple[list[PurchaseOrder], int]:
        cursor = (
            self._purchase_orders.find({})
            .sort("created_at", DESCENDING)
            .skip(offset)
            .limit(limit)
        )
        purchase_orders = [_from_mongo(data) async for data in cursor]
        return purchase_orders, await self._purchase_orders.count_documents({})

    async def replace(
        self, purchase_order_id: str, data: PurchaseOrderData
    ) -> PurchaseOrder | None:
        try:
            updated = await self._purchase_orders.find_one_and_update(
                {"_id": purchase_order_id},
                {"$set": {**data.model_dump(), "updated_at": datetime.now(UTC)}},
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError as error:
            raise _duplicate(data.po_number) from error
        return _from_mongo(updated) if updated else None

    async def delete(self, purchase_order_id: str) -> bool:
        result = await self._purchase_orders.delete_one({"_id": purchase_order_id})
        return result.deleted_count == 1
