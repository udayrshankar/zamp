from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from app.domain.errors import (
    LlmError,
    RunInProgressError,
    RunNotAwaitingPoError,
    RunNotFoundError,
    UnknownPoNumberError,
)
from app.domain.models import Document, DocumentStatus, PurchaseOrder, WarningCode
from app.domain.ports import RunRepository
from app.domain.runs import (
    Decision,
    PoSource,
    Run,
    RunError,
    RunStatus,
    StageName,
    StageStatus,
)
from app.services.document_service import DocumentService
from app.services.purchase_order_service import PurchaseOrderService
from app.workflow.checks import Check, CheckContext
from app.workflow.decision_policy import decide
from app.workflow.invoice_verifier import InvoiceVerifier
from app.workflow.po_detector import PoDetector
from app.workflow.po_matcher import find_by_number, match_purchase_order

logger = logging.getLogger(__name__)

NO_REFERENCE_PROMPT = "No purchase order reference was found on this invoice."
UNREADABLE_PROMPT = "The purchase order could not be detected automatically."


class RunOrchestrator:
    """Moves an invoice through its stages, saving after each one, so the live
    view and the audit trail both come from the same record."""

    def __init__(
        self,
        runs: RunRepository,
        documents: DocumentService,
        purchase_orders: PurchaseOrderService,
        detector: PoDetector,
        verifier: InvoiceVerifier,
        checks: list[Check],
    ) -> None:
        self._runs = runs
        self._documents = documents
        self._purchase_orders = purchase_orders
        self._detector = detector
        self._verifier = verifier
        self._checks = checks

    async def start(self, filename: str, data: bytes) -> Run:
        document = await self._documents.upload(filename, data)
        run = Run(document_id=document.id, filename=filename, sha256=document.sha256)
        await self._runs.insert(run)
        return run

    async def execute(self, run_id: str) -> None:
        await self._guarded(run_id, self._read_and_detect)

    async def provide_purchase_order(self, run_id: str, po_number: str) -> Run:
        order = find_by_number(po_number, await self._purchase_orders.all())
        if order is None:
            raise UnknownPoNumberError(f"No purchase order numbered {po_number} exists.")

        run = await self._claim(run_id)
        self._assign_order(run, order, PoSource.USER_SUPPLIED)
        run.end_stage(
            StageName.PO_CONFIRMATION,
            StageStatus.COMPLETED,
            f"The user chose {order.po_number}.",
        )
        await self._save(run)
        return run

    async def decline_purchase_order(self, run_id: str) -> Run:
        run = await self._claim(run_id)
        run.end_stage(
            StageName.PO_CONFIRMATION,
            StageStatus.COMPLETED,
            "The user said no purchase order exists.",
        )
        run.conclude(
            Decision.REVIEW,
            ["The user said this invoice has no purchase order, so it can't be matched."],
        )
        await self._save(run)
        return run

    async def resume(self, run_id: str) -> None:
        await self._guarded(run_id, self._continue_with_order)

    async def recover_interrupted(self) -> int:
        """Work runs in this process, so anything mid-flight at startup is lost.
        Runs waiting for a user aren't working, so they carry on as they were."""
        return await self._runs.fail_unfinished(
            RunError(
                code="INTERRUPTED",
                message="Processing stopped because the server restarted. Please upload again.",
            )
        )

    async def get(self, run_id: str) -> Run:
        run = await self._runs.get(run_id)
        if run is None:
            raise RunNotFoundError("Run not found.")
        return run

    async def list(self, limit: int, offset: int) -> tuple[list[Run], int]:
        return await self._runs.list(limit, offset)

    async def delete(self, run_id: str) -> None:
        """Removes a run with its document and PDF. The run goes first, so a
        failure part-way leaves a stray file rather than a run with no invoice."""
        run = await self._runs.delete_unless_working(run_id)
        if run is None:
            await self.get(run_id)
            raise RunInProgressError("This run is still being processed.")
        await self._documents.delete(run.document_id)

    async def _claim(self, run_id: str) -> Run:
        run = await self._runs.claim_awaiting_po(run_id)
        if run is not None:
            return run
        await self.get(run_id)
        raise RunNotAwaitingPoError("This run is not waiting for a purchase order.")

    async def _guarded(self, run_id: str, step: Callable[[Run], Awaitable[None]]) -> None:
        run = await self.get(run_id)
        try:
            await step(run)
        except Exception:
            logger.exception("Run %s crashed", run_id)
            for stage in run.stages:
                if stage.status is StageStatus.RUNNING:
                    run.end_stage(stage.name, StageStatus.FAILED, "This stage crashed.")
            run.decision = Decision.REVIEW
            run.reasons = ["Something went wrong while processing, so this needs a person."]
            run.error = RunError(
                code="INTERNAL_ERROR", message="Something went wrong while processing this run."
            )
            run.status = RunStatus.FAILED
            await self._save(run)

    async def _read_and_detect(self, run: Run) -> None:
        run.status = RunStatus.RUNNING
        document = await self._extract(run)
        if document is None:
            return
        order = await self._detect(run, _full_text(document))
        if order is not None:
            await self._verify_and_decide(run, document, order)

    async def _continue_with_order(self, run: Run) -> None:
        document = await self._documents.get(run.document_id)
        order = await self._purchase_orders.get(run.purchase_order_id)
        await self._verify_and_decide(run, document, order)

    async def _extract(self, run: Run) -> Document | None:
        run.begin_stage(StageName.EXTRACTION)
        await self._save(run)

        await self._documents.process(run.document_id)
        document = await self._documents.get(run.document_id)

        if document.status is DocumentStatus.FAILED:
            message = document.error.message if document.error else "The file could not be read."
            await self._conclude_early(run, StageName.EXTRACTION, message)
            return None
        if any(warning.code is WarningCode.NO_TEXT_FOUND for warning in document.warnings):
            await self._conclude_early(
                run, StageName.EXTRACTION, "No text was found in this document."
            )
            return None

        summary = document.summary
        run.end_stage(
            StageName.EXTRACTION,
            StageStatus.COMPLETED,
            f"Read {document.page_count} page(s): {summary.native_pages} from the text layer, "
            f"{summary.parse_pages} with Nemotron Parse, {summary.ocr_pages} with OCR.",
        )
        await self._save(run)
        return document

    async def _detect(self, run: Run, text: str) -> PurchaseOrder | None:
        run.begin_stage(StageName.PO_DETECTION)
        await self._save(run)

        try:
            candidates = await self._detector.detect(text)
        except LlmError as error:
            run.end_stage(StageName.PO_DETECTION, StageStatus.FAILED, error.message)
            await self._pause(run, UNREADABLE_PROMPT, [])
            return None

        found = [candidate.value for candidate in candidates]
        match = match_purchase_order(candidates, await self._purchase_orders.all())
        detail = {
            "candidates": [
                {"value": candidate.value, "evidence": candidate.evidence}
                for candidate in candidates
            ]
        }
        if match.order is not None:
            self._assign_order(run, match.order, PoSource.DETECTED)
            run.end_stage(
                StageName.PO_DETECTION,
                StageStatus.COMPLETED,
                f"Matched {match.order.po_number}.",
                detail,
            )
            run.end_stage(
                StageName.PO_CONFIRMATION, StageStatus.SKIPPED, "No confirmation was needed."
            )
            await self._save(run)
            return match.order

        if match.ambiguous:
            numbers = [order.po_number for order in match.ambiguous]
            prompt = f"The reference on this invoice could mean any of: {', '.join(numbers)}."
        elif found:
            numbers = []
            prompt = f"No purchase order matches the reference {', '.join(found)}."
        else:
            numbers = []
            prompt = NO_REFERENCE_PROMPT
        run.end_stage(StageName.PO_DETECTION, StageStatus.COMPLETED, prompt, detail)
        await self._pause(run, prompt, numbers)
        return None

    async def _pause(self, run: Run, prompt: str, suggestions: list[str]) -> None:
        run.begin_stage(StageName.PO_CONFIRMATION)
        run.stage(StageName.PO_CONFIRMATION).status = StageStatus.WAITING
        run.po_prompt = prompt
        run.po_suggestions = suggestions
        run.status = RunStatus.AWAITING_PO
        await self._save(run)

    async def _verify_and_decide(
        self, run: Run, document: Document, order: PurchaseOrder
    ) -> None:
        text = _full_text(document)
        run.begin_stage(StageName.VERIFICATION)
        await self._save(run)

        try:
            run.verification = await self._verifier.verify(text, order)
        except LlmError as error:
            await self._conclude_early(run, StageName.VERIFICATION, error.message)
            return
        run.end_stage(
            StageName.VERIFICATION,
            StageStatus.COMPLETED,
            f"Compared the invoice with {order.po_number}.",
        )

        run.begin_stage(StageName.CHECKS)
        await self._save(run)
        context = CheckContext(
            verification=run.verification,
            order=order,
            document=document,
            invoice_text=text,
            earlier_runs=[
                earlier for earlier in await self._runs.list_decided() if earlier.id != run.id
            ],
        )
        run.checks = [check.run(context) for check in self._checks]
        failed = sum(check.outcome != "pass" for check in run.checks)
        run.end_stage(
            StageName.CHECKS,
            StageStatus.COMPLETED,
            f"{len(run.checks) - failed} of {len(run.checks)} checks passed.",
        )

        run.begin_stage(StageName.DECISION)
        await self._save(run)
        run.conclude(*decide(run.checks))
        await self._save(run)

    async def _conclude_early(self, run: Run, stage: StageName, reason: str) -> None:
        """A run that can't finish still gets a decision: a person looks at it."""
        run.end_stage(stage, StageStatus.FAILED, reason)
        run.begin_stage(StageName.DECISION)
        run.conclude(Decision.REVIEW, [reason])
        await self._save(run)

    def _assign_order(self, run: Run, order: PurchaseOrder, source: PoSource) -> None:
        run.purchase_order_id = order.id
        run.po_number = order.po_number
        run.po_source = source

    async def _save(self, run: Run) -> None:
        await self._runs.save(run)


def _full_text(document: Document) -> str:
    return "\n\n".join(
        f"--- Page {page.number} ---\n{page.text}" for page in document.pages if page.text
    )
