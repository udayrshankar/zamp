from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.api.app_factory import create_app
from app.api.dependencies import Container
from app.core.config import Settings
from app.services.document_service import DocumentService
from app.services.purchase_order_service import PurchaseOrderService
from tests.fakes import (
    FakeExtractor,
    FakePurchaseOrderRepository,
    FakeRepository,
    FakeStorage,
)

PDF = b"%PDF-1.7 content"


@pytest.fixture
def client():
    executor = ThreadPoolExecutor(max_workers=1)
    service = DocumentService(
        repository=FakeRepository(),
        storage=FakeStorage(),
        extractor=FakeExtractor(),
        executor=executor,
        max_upload_bytes=1024 * 1024,
    )

    async def startup() -> None:
        await service.recover_interrupted()

    async def shutdown() -> None:
        executor.shutdown()

    def factory(_: Settings) -> Container:
        return Container(
            service, PurchaseOrderService(FakePurchaseOrderRepository()), startup, shutdown
        )

    app = create_app(Settings(MAX_UPLOAD_MB=1), factory)
    with TestClient(app) as test_client:
        yield test_client


def upload(client, data=PDF, filename="invoice.pdf"):
    return client.post("/api/v1/documents", files={"file": (filename, data, "application/pdf")})


def test_upload_is_accepted_and_processed(client):
    response = upload(client)

    assert response.status_code == 202
    document = client.get(f"/api/v1/documents/{response.json()['id']}").json()
    assert document["status"] == "completed"
    assert document["summary"]["native_pages"] == 1


@pytest.mark.parametrize(
    ("data", "status", "code"),
    [
        (b"", 400, "EMPTY_FILE"),
        (b"not a pdf", 415, "NOT_A_PDF"),
        (b"%PDF" + b"x" * (1024 * 1024), 413, "FILE_TOO_LARGE"),
    ],
)
def test_bad_uploads_get_a_clear_error(client, data, status, code):
    response = upload(client, data)

    assert response.status_code == status
    assert response.json()["code"] == code


def test_list_is_newest_first_and_omits_page_text(client):
    upload(client, filename="first.pdf")
    upload(client, filename="second.pdf")

    body = client.get("/api/v1/documents").json()

    assert body["total"] == 2
    assert [item["filename"] for item in body["items"]] == ["second.pdf", "first.pdf"]
    assert "pages" not in body["items"][0]


def test_original_file_can_be_downloaded(client):
    document_id = upload(client, filename="résumé invoice.pdf").json()["id"]

    response = client.get(f"/api/v1/documents/{document_id}/file")

    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert "r%C3%A9sum%C3%A9" in response.headers["content-disposition"]


def test_unknown_document_is_404(client):
    response = client.get("/api/v1/documents/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "DOCUMENT_NOT_FOUND"


def test_invalid_pagination_is_rejected(client):
    assert client.get("/api/v1/documents?limit=0").status_code == 422
