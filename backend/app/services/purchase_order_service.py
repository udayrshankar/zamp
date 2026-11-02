from __future__ import annotations

from app.domain.errors import PurchaseOrderNotFoundError
from app.domain.models import PurchaseOrder, PurchaseOrderData
from app.domain.ports import PurchaseOrderRepository

NOT_FOUND_MESSAGE = "Purchase order not found."
MAX_ORDERS = 5000


class PurchaseOrderService:
    def __init__(self, repository: PurchaseOrderRepository) -> None:
        self._repository = repository

    async def create(self, data: PurchaseOrderData) -> PurchaseOrder:
        purchase_order = PurchaseOrder(**data.model_dump())
        await self._repository.insert(purchase_order)
        return purchase_order

    async def get(self, purchase_order_id: str) -> PurchaseOrder:
        purchase_order = await self._repository.get(purchase_order_id)
        if purchase_order is None:
            raise PurchaseOrderNotFoundError(NOT_FOUND_MESSAGE)
        return purchase_order

    async def list(self, limit: int, offset: int) -> tuple[list[PurchaseOrder], int]:
        return await self._repository.list(limit, offset)

    async def all(self) -> list[PurchaseOrder]:
        purchase_orders, _ = await self._repository.list(MAX_ORDERS, 0)
        return purchase_orders

    async def replace(self, purchase_order_id: str, data: PurchaseOrderData) -> PurchaseOrder:
        purchase_order = await self._repository.replace(purchase_order_id, data)
        if purchase_order is None:
            raise PurchaseOrderNotFoundError(NOT_FOUND_MESSAGE)
        return purchase_order

    async def delete(self, purchase_order_id: str) -> None:
        if not await self._repository.delete(purchase_order_id):
            raise PurchaseOrderNotFoundError(NOT_FOUND_MESSAGE)
