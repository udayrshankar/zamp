from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.api.app_factory import create_app
from app.api.dependencies import Container
from app.core.config import Settings
from app.domain.models import PurchaseOrderData
from app.domain.runs import PoDetectionOutput
from app.services.document_service import DocumentService
from app.services.purchase_order_service import PurchaseOrderService
from app.services.run_orchestrator import RunOrchestrator
from app.workflow.checks import Tolerance, build_checks
from app.workflow.invoice_verifier import InvoiceVerifier
from app.workflow.po_detector import PoDetector
from tests.fakes import (
    FakePanel,
    FakeLlm,
    FakePurchaseOrderRepository,
    FakeRepository,
    FakeRunRepository,
    FakeStorage,
)
from tests.unit.test_run_orchestrator import UNREFERENCED, TextExtractor, verified

URL = "/api/v1/runs"
PDF = b"%PDF-1.7 content"


def build_client(llm: FakeLlm, extractor: TextExtractor | None = None):
    executor = ThreadPoolExecutor(max_workers=1)
    documents = DocumentService(
        repository=FakeRepository(),
        storage=FakeStorage(),
        extractor=extractor or TextExtractor(),
        executor=executor,
        max_upload_bytes=1024 * 1024,
    )
    orders = PurchaseOrderService(FakePurchaseOrderRepository())
    orchestrator = RunOrchestrator(
        runs=FakeRunRepository(),
        documents=documents,
        purchase_orders=orders,
        detector=PoDetector(llm),
        verifier=InvoiceVerifier(FakePanel(llm)),
        checks=build_checks(Tolerance(2, 10)),
    )

    async def startup() -> None:
        await orders.create(
            PurchaseOrderData(
                po_number="PO-1", fields={"supplier": "Northwind Ltd", "grand_total": 1000.0}
            )
        )

    async def shutdown() -> None:
        executor.shutdown()

    def factory(_: Settings) -> Container:
        return Container(documents, orders, startup, shutdown, orchestrator)

    return TestClient(create_app(Settings(MAX_UPLOAD_MB=1), factory))


@pytest.fixture
def client():
    # The invoice prints its PO, so it is matched without asking the LLM.
    with build_client(FakeLlm(verified())) as test_client:
        yield test_client


@pytest.fixture
def paused_client():
    llm = FakeLlm(PoDetectionOutput(candidates=[]), verified())
    with build_client(llm, TextExtractor(text=UNREFERENCED)) as test_client:
        yield test_client


def upload(client, data=PDF):
    return client.post(URL, files={"file": ("invoice.pdf", data, "application/pdf")})


def test_upload_runs_to_a_decision(client):
    response = upload(client)

    assert response.status_code == 202
    run = client.get(f"{URL}/{response.json()['id']}").json()
    assert run["status"] == "completed"
    assert run["decision"] == "accept"
    assert run["po_number"] == "PO-1"
    assert [stage["name"] for stage in run["stages"]][0] == "extraction"
    assert run["verification"]["invoice"]["total"] == 1000.0


def test_bad_upload_is_rejected_before_a_run_starts(client):
    response = upload(client, b"not a pdf")

    assert response.status_code == 415
    assert client.get(URL).json()["total"] == 0


def test_list_shows_runs(client):
    upload(client)

    body = client.get(URL).json()

    assert body["total"] == 1
    assert body["items"][0]["decision"] == "accept"


def test_paused_run_resumes_with_a_po(paused_client):
    run_id = upload(paused_client).json()["id"]
    assert paused_client.get(f"{URL}/{run_id}").json()["status"] == "awaiting_po"

    response = paused_client.post(f"{URL}/{run_id}/purchase-order", json={"po_number": "PO-1"})

    assert response.status_code == 200
    run = paused_client.get(f"{URL}/{run_id}").json()
    assert run["decision"] == "accept"
    assert run["po_source"] == "user_supplied"


def test_unknown_po_is_refused(paused_client):
    run_id = upload(paused_client).json()["id"]

    response = paused_client.post(f"{URL}/{run_id}/purchase-order", json={"po_number": "PO-9"})

    assert response.status_code == 422
    assert response.json()["code"] == "UNKNOWN_PO_NUMBER"


def test_po_for_a_finished_run_is_a_conflict(client):
    run_id = upload(client).json()["id"]

    response = client.post(f"{URL}/{run_id}/purchase-order", json={"po_number": "PO-1"})

    assert response.status_code == 409
    assert response.json()["code"] == "RUN_NOT_AWAITING_PO"


def test_declining_a_po_gives_a_review_decision(paused_client):
    run_id = upload(paused_client).json()["id"]

    response = paused_client.post(f"{URL}/{run_id}/no-purchase-order")

    assert response.json()["decision"] == "review"


def test_unknown_run_is_404(client):
    response = client.get(f"{URL}/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "RUN_NOT_FOUND"


def test_delete_removes_the_run(client):
    run_id = upload(client).json()["id"]

    assert client.delete(f"{URL}/{run_id}").status_code == 204
    assert client.get(f"{URL}/{run_id}").status_code == 404
    assert client.get(URL).json()["total"] == 0


def test_a_paused_run_can_be_deleted(paused_client):
    run_id = upload(paused_client).json()["id"]

    assert paused_client.delete(f"{URL}/{run_id}").status_code == 204


def test_deleting_an_unknown_run_is_404(client):
    response = client.delete(f"{URL}/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "RUN_NOT_FOUND"


def test_deleting_a_run_in_progress_is_a_conflict(client):
    run_id = upload(client).json()["id"]
    orchestrator = client.app.state.container.run_orchestrator
    orchestrator._runs.runs[run_id].status = "running"

    response = client.delete(f"{URL}/{run_id}")

    assert response.status_code == 409
    assert response.json()["code"] == "RUN_IN_PROGRESS"
