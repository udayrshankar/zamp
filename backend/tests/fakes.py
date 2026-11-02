from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.errors import DuplicatePurchaseOrderError, PageReadError
from app.domain.models import (
    Document,
    DocumentError,
    DocumentStatus,
    ExtractionResult,
    ExtractionSummary,
    PurchaseOrder,
    PurchaseOrderData,
    RenderedImage,
    TextLine,
)
from app.domain.runs import Run, RunError, RunStatus

GOOD_TEXT = "Invoice INV-1001 issued to Acme Manufacturing for office furniture and delivery"


def words(text: str, y: float = 10.0) -> list[TextLine]:
    fragments = []
    x = 0.0
    for word in text.split():
        fragments.append(TextLine(text=word, bbox=(x, y, x + 10 * len(word), y + 10)))
        x += 10 * len(word) + 5
    return fragments


@dataclass
class FakePage:
    number: int = 1
    text: str = ""
    coverage: float = 0.0
    render_error: bool = False
    pixels: bytes = b""

    def fragments(self) -> list[TextLine]:
        return words(self.text)

    def image_coverage(self) -> float:
        return self.coverage

    def render(self, dpi: int) -> RenderedImage:
        if self.render_error:
            raise PageReadError("render failed")
        return RenderedImage(
            width=10, height=10, channels=3, samples=b"", pixels_per_point=dpi / 72
        )

    def render_to_fit(self, max_width: int, max_height: int) -> RenderedImage:
        if self.render_error:
            raise PageReadError("render failed")
        return RenderedImage(
            width=max_width,
            height=max_height,
            channels=3,
            samples=self.pixels,
            pixels_per_point=2.0,
        )


@dataclass
class FakePdf:
    fake_pages: list[FakePage]

    @property
    def page_count(self) -> int:
        return len(self.fake_pages)

    def pages(self) -> Iterator[FakePage]:
        return iter(self.fake_pages)

    def __enter__(self) -> "FakePdf":
        return self

    def __exit__(self, *_: object) -> None:
        return None


@dataclass
class FakeReader:
    pdf: FakePdf

    def open(self, data: bytes) -> FakePdf:
        return self.pdf


@dataclass
class FakeOcrEngine:
    lines: list[TextLine] = field(default_factory=list)

    def recognize(self, image: RenderedImage) -> list[TextLine]:
        return self.lines


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def save(self, filename: str, data: bytes) -> str:
        file_id = str(len(self.files) + 1)
        self.files[file_id] = data
        return file_id

    async def load(self, file_id: str) -> bytes:
        return self.files[file_id]

    async def delete(self, file_id: str) -> None:
        self.files.pop(file_id, None)


class FakeRepository:
    def __init__(self) -> None:
        self.documents: dict[str, Document] = {}

    async def ensure_indexes(self) -> None:
        return None

    async def insert(self, document: Document) -> None:
        self.documents[document.id] = document

    async def delete(self, document_id: str) -> None:
        self.documents.pop(document_id, None)

    async def get(self, document_id: str) -> Document | None:
        return self.documents.get(document_id)

    async def list(self, limit: int, offset: int) -> tuple[list[Document], int]:
        ordered = sorted(self.documents.values(), key=lambda d: d.created_at, reverse=True)
        return ordered[offset : offset + limit], len(ordered)

    async def mark_processing(self, document_id: str) -> None:
        self._update(document_id, status=DocumentStatus.PROCESSING)

    async def save_result(self, document_id: str, result: ExtractionResult) -> None:
        self._update(document_id, status=DocumentStatus.COMPLETED, **dict(result))

    async def mark_failed(self, document_id: str, error: DocumentError) -> None:
        self._update(document_id, status=DocumentStatus.FAILED, error=error)

    async def fail_unfinished(self, error: DocumentError) -> int:
        unfinished = [
            document.id
            for document in self.documents.values()
            if document.status in (DocumentStatus.QUEUED, DocumentStatus.PROCESSING)
        ]
        for document_id in unfinished:
            await self.mark_failed(document_id, error)
        return len(unfinished)

    def _update(self, document_id: str, **fields: object) -> None:
        self.documents[document_id] = self.documents[document_id].model_copy(
            update={**fields, "updated_at": datetime.now(UTC)}
        )


class FakeExtractor:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def run(self, data: bytes) -> ExtractionResult:
        if self.error:
            raise self.error
        return ExtractionResult(page_count=1, pages=[], summary=ExtractionSummary(native_pages=1))


class FakePurchaseOrderRepository:
    def __init__(self) -> None:
        self.purchase_orders: dict[str, PurchaseOrder] = {}

    async def ensure_indexes(self) -> None:
        return None

    async def insert(self, purchase_order: PurchaseOrder) -> None:
        self._check_number_is_free(purchase_order.po_number, purchase_order.id)
        self.purchase_orders[purchase_order.id] = purchase_order

    async def get(self, purchase_order_id: str) -> PurchaseOrder | None:
        return self.purchase_orders.get(purchase_order_id)

    async def list(self, limit: int, offset: int) -> tuple[list[PurchaseOrder], int]:
        ordered = sorted(
            self.purchase_orders.values(), key=lambda order: order.created_at, reverse=True
        )
        return ordered[offset : offset + limit], len(ordered)

    async def replace(
        self, purchase_order_id: str, data: PurchaseOrderData
    ) -> PurchaseOrder | None:
        existing = self.purchase_orders.get(purchase_order_id)
        if existing is None:
            return None
        self._check_number_is_free(data.po_number, purchase_order_id)
        updated = existing.model_copy(
            update={**data.model_dump(), "updated_at": datetime.now(UTC)}
        )
        self.purchase_orders[purchase_order_id] = updated
        return updated

    async def delete(self, purchase_order_id: str) -> bool:
        return self.purchase_orders.pop(purchase_order_id, None) is not None

    def _check_number_is_free(self, po_number: str, own_id: str) -> None:
        for order in self.purchase_orders.values():
            if order.po_number == po_number and order.id != own_id:
                raise DuplicatePurchaseOrderError(po_number)


class FakeRunRepository:
    def __init__(self) -> None:
        self.runs: dict[str, Run] = {}

    async def ensure_indexes(self) -> None:
        return None

    async def insert(self, run: Run) -> None:
        self.runs[run.id] = run.model_copy(deep=True)

    async def save(self, run: Run) -> None:
        self.runs[run.id] = run.model_copy(deep=True)

    async def get(self, run_id: str) -> Run | None:
        run = self.runs.get(run_id)
        return run.model_copy(deep=True) if run else None

    async def list(self, limit: int, offset: int) -> tuple[list[Run], int]:
        ordered = sorted(self.runs.values(), key=lambda run: run.created_at, reverse=True)
        return ordered[offset : offset + limit], len(ordered)

    async def list_decided(self) -> list[Run]:
        return [run for run in self.runs.values() if run.decision is not None]

    async def delete_unless_working(self, run_id: str) -> Run | None:
        run = self.runs.get(run_id)
        if run is None or run.status in (RunStatus.QUEUED, RunStatus.RUNNING):
            return None
        return self.runs.pop(run_id)

    async def claim_awaiting_po(self, run_id: str) -> Run | None:
        run = self.runs.get(run_id)
        if run is None or run.status is not RunStatus.AWAITING_PO:
            return None
        run.status = RunStatus.RUNNING
        return run.model_copy(deep=True)

    async def fail_unfinished(self, error: RunError) -> int:
        unfinished = [
            run
            for run in self.runs.values()
            if run.status in (RunStatus.QUEUED, RunStatus.RUNNING)
        ]
        for run in unfinished:
            run.status = RunStatus.FAILED
            run.error = error
        return len(unfinished)


class FakeLlm:
    """Returns queued answers by output type, or raises a queued error."""

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, str, type]] = []

    async def complete_json(self, system: str, user: str, output: type) -> object:
        self.calls.append((system, user, output))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakePanel:
    """A panel of one: puts each question to a FakeLlm and reports its answer,
    or its error, the way a real panel would."""

    MODEL = "fake-model"

    def __init__(self, llm: FakeLlm) -> None:
        self.llm = llm

    async def ask_all(self, system: str, user: str, output: type) -> list:
        from app.domain.errors import LlmError
        from app.domain.llm import AnswerStatus, ModelAnswer

        try:
            answer = await self.llm.complete_json(system, user, output)
        except LlmError as error:
            return [ModelAnswer(self.MODEL, AnswerStatus.FAILED, 0.0, error=error.message)]
        return [ModelAnswer(self.MODEL, AnswerStatus.ANSWERED, 0.0, output=answer)]
