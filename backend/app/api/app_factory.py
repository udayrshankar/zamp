from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.dependencies import Container, build_container
from app.api.routes import documents, health, purchase_orders, runs
from app.core.config import Settings, settings
from app.domain.errors import (
    DocumentNotFoundError,
    DomainError,
    DuplicatePurchaseOrderError,
    EmptyFileError,
    FileTooLargeError,
    NotAPdfError,
    PurchaseOrderNotFoundError,
    RunInProgressError,
    RunNotAwaitingPoError,
    RunNotFoundError,
    UnknownPoNumberError,
)

ERROR_RESPONSES: dict[type[DomainError], tuple[int, str]] = {
    EmptyFileError: (400, "EMPTY_FILE"),
    NotAPdfError: (415, "NOT_A_PDF"),
    FileTooLargeError: (413, "FILE_TOO_LARGE"),
    DocumentNotFoundError: (404, "DOCUMENT_NOT_FOUND"),
    PurchaseOrderNotFoundError: (404, "PURCHASE_ORDER_NOT_FOUND"),
    DuplicatePurchaseOrderError: (409, "DUPLICATE_PO_NUMBER"),
    RunNotFoundError: (404, "RUN_NOT_FOUND"),
    RunNotAwaitingPoError: (409, "RUN_NOT_AWAITING_PO"),
    RunInProgressError: (409, "RUN_IN_PROGRESS"),
    UnknownPoNumberError: (422, "UNKNOWN_PO_NUMBER"),
}


def _handle_domain_error(_: Request, error: Exception) -> JSONResponse:
    status_code, code = ERROR_RESPONSES.get(type(error), (500, "INTERNAL_ERROR"))
    message = str(error) if status_code < 500 else "Unexpected error."
    return JSONResponse(status_code=status_code, content={"code": code, "message": message})


def create_app(
    config: Settings = settings,
    container_factory: Callable[[Settings], Container] = build_container,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = container_factory(config)
        await container.startup()
        app.state.container = container
        yield
        await container.shutdown()

    app = FastAPI(title=config.APP_NAME, version="0.1.0", lifespan=lifespan)
    app.state.max_upload_bytes = config.MAX_UPLOAD_MB * 1024 * 1024

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(DomainError, _handle_domain_error)

    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(purchase_orders.router)
    app.include_router(runs.router)
    return app
