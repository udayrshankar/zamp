"""Runs the labelled invoices through the real pipeline and the real LLM.

Run from backend/: uv run python scripts/run_eval.py
It calls the LLM about twice per invoice, and exits non-zero on a wrong accept.
"""

import argparse
import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import Settings, settings  # noqa: E402
from app.core.pipeline_factory import build_pipeline  # noqa: E402
from app.domain.models import PurchaseOrderData  # noqa: E402
from app.infrastructure.llm_chain import FallbackLlmClient  # noqa: E402
from app.infrastructure.llm_panel import ParallelLlmPanel  # noqa: E402
from app.infrastructure.model_health import ModelHealth  # noqa: E402
from app.infrastructure.nvidia_llm import NvidiaLlmClient  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402
from app.services.purchase_order_service import PurchaseOrderService  # noqa: E402
from app.services.run_orchestrator import RunOrchestrator  # noqa: E402
from app.workflow.checks import Tolerance, build_checks  # noqa: E402
from app.workflow.invoice_verifier import InvoiceVerifier  # noqa: E402
from app.workflow.po_detector import PoDetector  # noqa: E402
from tests.eval.cases import ACCEPT, CASES, PURCHASE_ORDERS  # noqa: E402
from tests.fakes import (  # noqa: E402
    FakePurchaseOrderRepository,
    FakeRepository,
    FakeRunRepository,
    FakeStorage,
)


async def run_once(verbose: bool) -> tuple[int, int]:
    """Returns how many cases were right and how many were wrong accepts."""
    orders = PurchaseOrderService(FakePurchaseOrderRepository())
    for order in PURCHASE_ORDERS:
        await orders.create(PurchaseOrderData(**order))

    correct = wrong_accepts = 0
    with ThreadPoolExecutor(max_workers=1) as executor:
        async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as http:
            models = [
                NvidiaLlmClient(http, settings.LLM_URL, settings.NVIDIA_KEY, model)
                for model in settings.LLM_MODELS
            ]
            health = ModelHealth(settings.LLM_MODELS, cooldown_seconds=settings.LLM_COOLDOWN_SECONDS)
            orchestrator = RunOrchestrator(
                runs=FakeRunRepository(),
                documents=DocumentService(
                    repository=FakeRepository(),
                    storage=FakeStorage(),
                    extractor=build_pipeline(Settings(NVIDIA_KEY="")),
                    executor=executor,
                    max_upload_bytes=settings.MAX_UPLOAD_MB * 1024 * 1024,
                ),
                purchase_orders=orders,
                detector=PoDetector(FallbackLlmClient(models, health)),
                verifier=InvoiceVerifier(
                    ParallelLlmPanel(
                        models, health, settings.LLM_PANEL_SIZE, settings.LLM_PANEL_DEADLINE_SECONDS
                    )
                ),
                checks=build_checks(
                    Tolerance(
                        settings.ACCEPT_TOLERANCE_PERCENT, settings.REJECT_TOLERANCE_PERCENT
                    )
                ),
            )

            for index, case in enumerate(CASES):
                run = await orchestrator.start(f"case-{index}.pdf", case.invoice.to_pdf())
                await orchestrator.execute(run.id)
                run = await orchestrator.get(run.id)
                if run.status == "awaiting_po" and case.answer_po:
                    await orchestrator.provide_purchase_order(run.id, case.answer_po)
                    await orchestrator.resume(run.id)
                    run = await orchestrator.get(run.id)

                got = str(run.decision or run.status)
                correct += got == case.expected
                wrong = got == ACCEPT and case.expected != ACCEPT
                wrong_accepts += wrong
                mark = "ok " if got == case.expected else "XX "
                print(f"{mark}{case.name}: expected {case.expected}, got {got}")
                if verbose and got != case.expected:
                    print(f"     PO {run.po_number}; {run.po_prompt or ''}")
                    for stage in run.stages:
                        if stage.status == "failed":
                            print(f"     failed {stage.name}: {stage.summary}")
                    for reason in run.reasons:
                        print(f"     - {reason}")
                    for check in run.checks:
                        if check.outcome != "pass":
                            print(f"     [{check.name}] {check.message}")
    return correct, wrong_accepts


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=1, help="repeat to measure consistency")
    parser.add_argument("--quiet", action="store_true", help="hide the reasons for wrong answers")
    args = parser.parse_args()

    print(f"Models: {', '.join(settings.LLM_MODELS)} (panel of {settings.LLM_PANEL_SIZE})")
    total_wrong_accepts = 0
    for attempt in range(args.repeat):
        correct, wrong_accepts = await run_once(not args.quiet)
        total_wrong_accepts += wrong_accepts
        print(
            f"== Run {attempt + 1}: {correct}/{len(CASES)} correct, "
            f"{wrong_accepts} wrong accept(s)"
        )
    return 1 if total_wrong_accepts else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
