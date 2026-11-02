from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx
from fastapi import Request
from pymongo import AsyncMongoClient

from app.core.config import Settings
from app.core.pipeline_factory import build_pipeline
from app.infrastructure.gridfs_storage import GridFsStorage
from app.infrastructure.mongo_repository import MongoDocumentRepository
from app.infrastructure.nvidia_llm import NvidiaLlmClient
from app.infrastructure.purchase_order_repository import MongoPurchaseOrderRepository
from app.infrastructure.run_repository import MongoRunRepository
from app.services.document_service import DocumentService
from app.services.purchase_order_service import PurchaseOrderService
from app.services.run_orchestrator import RunOrchestrator
from app.workflow.checks import Tolerance, build_checks
from app.workflow.invoice_verifier import InvoiceVerifier
from app.workflow.po_detector import PoDetector


@dataclass(slots=True)
class Container:
    """Everything built at startup, plus how to release it at shutdown."""

    document_service: DocumentService
    purchase_order_service: PurchaseOrderService
    startup: Callable[[], Awaitable[None]]
    shutdown: Callable[[], Awaitable[None]]
    run_orchestrator: RunOrchestrator | None = None


def build_container(settings: Settings) -> Container:
    """Composition root: the only place the API meets concrete infrastructure."""
    if not settings.MONGO_DB_URL:
        raise RuntimeError("MONGO_DB_URL is not set. Add it to backend/.env.")

    client = AsyncMongoClient(settings.MONGO_DB_URL, tz_aware=True)
    database = client[settings.MONGO_DB_NAME]
    repository = MongoDocumentRepository(database)
    # One worker: PyMuPDF is not thread-safe and OCR is CPU-bound.
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="extraction")
    service = DocumentService(
        repository=repository,
        storage=GridFsStorage(database),
        extractor=build_pipeline(settings),
        executor=executor,
        max_upload_bytes=settings.MAX_UPLOAD_MB * 1024 * 1024,
    )
    purchase_orders = MongoPurchaseOrderRepository(database)
    purchase_order_service = PurchaseOrderService(purchase_orders)
    runs = MongoRunRepository(database)
    llm_http = httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS)
    llm = NvidiaLlmClient(llm_http, settings.LLM_URL, settings.NVIDIA_KEY, settings.LLM_MODEL)
    orchestrator = RunOrchestrator(
        runs=runs,
        documents=service,
        purchase_orders=purchase_order_service,
        detector=PoDetector(llm),
        verifier=InvoiceVerifier(llm),
        checks=build_checks(
            Tolerance(settings.ACCEPT_TOLERANCE_PERCENT, settings.REJECT_TOLERANCE_PERCENT)
        ),
    )

    async def startup() -> None:
        await repository.ensure_indexes()
        await purchase_orders.ensure_indexes()
        await runs.ensure_indexes()
        await service.recover_interrupted()
        await orchestrator.recover_interrupted()

    async def shutdown() -> None:
        executor.shutdown(wait=False, cancel_futures=True)
        await llm_http.aclose()
        await client.close()

    return Container(
        document_service=service,
        purchase_order_service=purchase_order_service,
        run_orchestrator=orchestrator,
        startup=startup,
        shutdown=shutdown,
    )


def get_document_service(request: Request) -> DocumentService:
    return request.app.state.container.document_service


def get_purchase_order_service(request: Request) -> PurchaseOrderService:
    return request.app.state.container.purchase_order_service


def get_run_orchestrator(request: Request) -> RunOrchestrator:
    return request.app.state.container.run_orchestrator
