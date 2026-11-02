from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_purchase_order_service
from app.api.schemas import PurchaseOrderPage
from app.domain.models import PurchaseOrder, PurchaseOrderData
from app.services.purchase_order_service import PurchaseOrderService

router = APIRouter(prefix="/api/v1/purchase-orders", tags=["Purchase Orders"])

Service = Annotated[PurchaseOrderService, Depends(get_purchase_order_service)]


@router.post("", response_model=PurchaseOrder, status_code=status.HTTP_201_CREATED)
async def create_purchase_order(data: PurchaseOrderData, service: Service) -> PurchaseOrder:
    return await service.create(data)


@router.get("", response_model=PurchaseOrderPage)
async def list_purchase_orders(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PurchaseOrderPage:
    purchase_orders, total = await service.list(limit, offset)
    return PurchaseOrderPage(items=purchase_orders, total=total, limit=limit, offset=offset)


@router.get("/{purchase_order_id}", response_model=PurchaseOrder)
async def get_purchase_order(purchase_order_id: str, service: Service) -> PurchaseOrder:
    return await service.get(purchase_order_id)


@router.put("/{purchase_order_id}", response_model=PurchaseOrder)
async def replace_purchase_order(
    purchase_order_id: str, data: PurchaseOrderData, service: Service
) -> PurchaseOrder:
    return await service.replace(purchase_order_id, data)


@router.delete("/{purchase_order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_purchase_order(purchase_order_id: str, service: Service) -> None:
    await service.delete(purchase_order_id)
