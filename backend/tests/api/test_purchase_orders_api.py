import pytest
from fastapi.testclient import TestClient

from app.api.app_factory import create_app
from app.api.dependencies import Container
from app.core.config import Settings
from app.services.purchase_order_service import PurchaseOrderService
from tests.fakes import FakePurchaseOrderRepository

URL = "/api/v1/purchase-orders"
ORDER = {
    "po_number": "PO-88213",
    "fields": {
        "vendor": "Northwind Office Supplies",
        "handling_charges": 25.5,
        "line_items": [{"description": "Chair", "qty": 2, "unit_price": 250.0}],
        "approved": True,
        "notes": None,
    },
}


@pytest.fixture
def client():
    async def noop() -> None:
        return None

    def factory(_: Settings) -> Container:
        service = PurchaseOrderService(FakePurchaseOrderRepository())
        return Container(None, service, noop, noop)

    with TestClient(create_app(Settings(), factory)) as test_client:
        yield test_client


def create(client, **overrides):
    return client.post(URL, json={**ORDER, **overrides})


def test_create_keeps_every_custom_field_and_its_type(client):
    response = create(client)

    assert response.status_code == 201
    body = response.json()
    assert body["fields"] == ORDER["fields"]
    assert body["id"]
    assert client.get(f"{URL}/{body['id']}").json() == body


def test_only_the_po_number_is_required(client):
    response = client.post(URL, json={"po_number": "PO-1"})

    assert response.status_code == 201
    assert response.json()["fields"] == {}


@pytest.mark.parametrize("body", [{}, {"po_number": ""}, {"po_number": "   "}])
def test_po_number_cannot_be_missing_or_blank(client, body):
    assert client.post(URL, json=body).status_code == 422


@pytest.mark.parametrize("name", ["", "  ", "a.b", "$set"])
def test_unsafe_field_names_are_rejected(client, name):
    assert create(client, fields={name: 1}).status_code == 422


def test_po_number_is_trimmed(client):
    assert create(client, po_number="  PO-9  ").json()["po_number"] == "PO-9"


def test_duplicate_po_number_is_a_conflict(client):
    create(client)

    response = create(client)

    assert response.status_code == 409
    assert response.json()["code"] == "DUPLICATE_PO_NUMBER"


def test_update_can_add_change_and_remove_fields(client):
    created = create(client).json()

    response = client.put(
        f"{URL}/{created['id']}",
        json={"po_number": "PO-88213-A", "fields": {"vendor": "Contoso", "freight": 40}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["po_number"] == "PO-88213-A"
    assert body["fields"] == {"vendor": "Contoso", "freight": 40}
    assert body["created_at"] == created["created_at"]
    assert body["updated_at"] >= created["updated_at"]


def test_update_can_keep_its_own_po_number(client):
    created = create(client).json()

    assert client.put(f"{URL}/{created['id']}", json=ORDER).status_code == 200


def test_update_cannot_take_another_po_number(client):
    create(client)
    other = create(client, po_number="PO-2").json()

    response = client.put(f"{URL}/{other['id']}", json=ORDER)

    assert response.status_code == 409


def test_delete_removes_the_order(client):
    created = create(client).json()

    assert client.delete(f"{URL}/{created['id']}").status_code == 204
    assert client.get(f"{URL}/{created['id']}").status_code == 404


@pytest.mark.parametrize(
    ("method", "body"), [("get", None), ("put", ORDER), ("delete", None)]
)
def test_unknown_order_is_404(client, method, body):
    response = client.request(method, f"{URL}/missing", json=body)

    assert response.status_code == 404
    assert response.json()["code"] == "PURCHASE_ORDER_NOT_FOUND"


def test_list_is_newest_first_and_paginated(client):
    create(client, po_number="PO-1")
    create(client, po_number="PO-2")

    body = client.get(URL, params={"limit": 1}).json()

    assert body["total"] == 2
    assert [order["po_number"] for order in body["items"]] == ["PO-2"]
