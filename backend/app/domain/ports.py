from __future__ import annotations

from collections.abc import Iterator
from types import TracebackType
from typing import Protocol, Self, TypeVar

from pydantic import BaseModel

from app.domain.llm import ModelAnswer
from app.domain.models import (
    Document,
    DocumentError,
    ExtractionResult,
    PageResult,
    PurchaseOrder,
    PurchaseOrderData,
    RenderedImage,
    RoutingReason,
    TextLine,
)
from app.domain.runs import Run, RunError

T = TypeVar("T", bound=BaseModel)


class PdfPage(Protocol):
    @property
    def number(self) -> int:
        """1-based page number."""
        ...

    def fragments(self) -> list[TextLine]:
        """Words from the embedded text layer, in no guaranteed order."""
        ...

    def image_coverage(self) -> float:
        """Share of the page area covered by images, from 0.0 to 1.0."""
        ...

    def render(self, dpi: int) -> RenderedImage:
        ...

    def render_to_fit(self, max_width: int, max_height: int) -> RenderedImage:
        ...


class PdfDocument(Protocol):
    @property
    def page_count(self) -> int:
        ...

    def pages(self) -> Iterator[PdfPage]:
        ...

    def __enter__(self) -> Self:
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        ...


class PdfReader(Protocol):
    def open(self, data: bytes) -> PdfDocument:
        """Raises EncryptedPdfError or CorruptPdfError."""
        ...


class OcrEngine(Protocol):
    def recognize(self, image: RenderedImage) -> list[TextLine]:
        """Returns fragments with bboxes in image pixels.

        An empty list means nothing was found. Raises PageReadError on failure.
        """
        ...


class PageParser(Protocol):
    def parse(self, image: RenderedImage) -> list[TextLine]:
        """Returns lines with bboxes in image pixels. Raises PageReadError on failure."""
        ...


class PageExtractor(Protocol):
    """Reads one page. Implementations are interchangeable: they return the
    same PageResult shape and raise only ExtractionError subclasses."""

    def extract(self, page: PdfPage, reason: RoutingReason) -> PageResult:
        ...


class TextExtractor(Protocol):
    def run(self, data: bytes) -> ExtractionResult:
        """Raises ExtractionError subclasses for files that can't be read."""
        ...


class FileStorage(Protocol):
    async def save(self, filename: str, data: bytes) -> str:
        ...

    async def load(self, file_id: str) -> bytes:
        ...

    async def delete(self, file_id: str) -> None:
        """Removes the file. Does nothing if it is already gone."""
        ...


class DocumentRepository(Protocol):
    async def ensure_indexes(self) -> None:
        ...

    async def delete(self, document_id: str) -> None:
        ...

    async def insert(self, document: Document) -> None:
        ...

    async def get(self, document_id: str) -> Document | None:
        ...

    async def list(self, limit: int, offset: int) -> tuple[list[Document], int]:
        """Returns a page of documents without page text, plus the total count."""
        ...

    async def mark_processing(self, document_id: str) -> None:
        ...

    async def save_result(self, document_id: str, result: ExtractionResult) -> None:
        ...

    async def mark_failed(self, document_id: str, error: DocumentError) -> None:
        ...

    async def fail_unfinished(self, error: DocumentError) -> int:
        """Fails every queued or processing document. Returns how many changed."""
        ...


class PurchaseOrderRepository(Protocol):
    async def ensure_indexes(self) -> None:
        ...

    async def insert(self, purchase_order: PurchaseOrder) -> None:
        """Raises DuplicatePurchaseOrderError if the PO number is taken."""
        ...

    async def get(self, purchase_order_id: str) -> PurchaseOrder | None:
        ...

    async def list(self, limit: int, offset: int) -> tuple[list[PurchaseOrder], int]:
        ...

    async def replace(
        self, purchase_order_id: str, data: PurchaseOrderData
    ) -> PurchaseOrder | None:
        """Returns None if the PO doesn't exist. Raises DuplicatePurchaseOrderError
        if the new PO number belongs to another PO."""
        ...

    async def delete(self, purchase_order_id: str) -> bool:
        """Returns False if the PO doesn't exist."""
        ...


class LlmClient(Protocol):
    async def complete_json(self, system: str, user: str, output: type[T]) -> T:
        """Returns the answer validated against `output`. Raises LlmError."""
        ...


class NamedLlmClient(LlmClient, Protocol):
    """A client for one specific model."""

    @property
    def model(self) -> str:
        ...


class LlmPanel(Protocol):
    async def ask_all(self, system: str, user: str, output: type[T]) -> list[ModelAnswer[T]]:
        """Puts the same question to several models. Never raises: a model that
        fails is reported as a failed answer."""
        ...


class RunRepository(Protocol):
    async def ensure_indexes(self) -> None:
        ...

    async def insert(self, run: Run) -> None:
        ...

    async def save(self, run: Run) -> None:
        ...

    async def get(self, run_id: str) -> Run | None:
        ...

    async def list(self, limit: int, offset: int) -> tuple[list[Run], int]:
        ...

    async def list_decided(self) -> list[Run]:
        ...

    async def delete_unless_working(self, run_id: str) -> Run | None:
        """Atomically deletes a run that nothing is working on, and returns it.
        None if it doesn't exist or is queued or running."""
        ...

    async def claim_awaiting_po(self, run_id: str) -> Run | None:
        """Atomically moves a waiting run to running. None if it wasn't waiting."""
        ...

    async def fail_unfinished(self, error: RunError) -> int:
        ...
