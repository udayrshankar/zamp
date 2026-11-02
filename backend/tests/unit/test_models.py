from app.domain.models import PurchaseOrder


def test_timestamps_match_mongodb_millisecond_precision():
    order = PurchaseOrder(po_number="PO-1")

    assert order.created_at.microsecond % 1000 == 0
