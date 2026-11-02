from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, UploadFile, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_run_orchestrator
from app.domain.runs import Run
from app.services.run_orchestrator import RunOrchestrator

router = APIRouter(prefix="/api/v1/runs", tags=["Invoice Runs"])

Orchestrator = Annotated[RunOrchestrator, Depends(get_run_orchestrator)]


class RunPage(BaseModel):
    items: list[Run]
    total: int
    limit: int
    offset: int


class PurchaseOrderChoice(BaseModel):
    po_number: str = Field(min_length=1)


@router.post("", response_model=Run, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    file: UploadFile,
    request: Request,
    background_tasks: BackgroundTasks,
    orchestrator: Orchestrator,
) -> Run:
    max_bytes = request.app.state.max_upload_bytes
    run = await orchestrator.start(file.filename or "invoice.pdf", await file.read(max_bytes + 1))
    background_tasks.add_task(orchestrator.execute, run.id)
    return run


@router.get("", response_model=RunPage)
async def list_runs(
    orchestrator: Orchestrator,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RunPage:
    runs, total = await orchestrator.list(limit, offset)
    return RunPage(items=runs, total=total, limit=limit, offset=offset)


@router.get("/{run_id}", response_model=Run)
async def get_run(run_id: str, orchestrator: Orchestrator) -> Run:
    return await orchestrator.get(run_id)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(run_id: str, orchestrator: Orchestrator) -> None:
    await orchestrator.delete(run_id)


@router.post("/{run_id}/purchase-order", response_model=Run)
async def provide_purchase_order(
    run_id: str,
    choice: PurchaseOrderChoice,
    background_tasks: BackgroundTasks,
    orchestrator: Orchestrator,
) -> Run:
    run = await orchestrator.provide_purchase_order(run_id, choice.po_number)
    background_tasks.add_task(orchestrator.resume, run.id)
    return run


@router.post("/{run_id}/no-purchase-order", response_model=Run)
async def decline_purchase_order(run_id: str, orchestrator: Orchestrator) -> Run:
    return await orchestrator.decline_purchase_order(run_id)
