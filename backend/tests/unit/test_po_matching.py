import pytest

from app.domain.models import PurchaseOrder
from app.domain.runs import (
    InvoiceFacts,
    LineItem,
    PoCandidate,
    PoDetectionOutput,
    PoFacts,
    VerificationOutput,
)
from app.workflow.invoice_verifier import InvoiceVerifier
from app.workflow.po_detector import PoDetector
from app.workflow.po_matcher import find_by_number, match_purchase_order
from tests.fakes import FakeLlm

ORDERS = [
    PurchaseOrder(po_number="PO-88213"),
    PurchaseOrder(po_number="PO-55120"),
    PurchaseOrder(po_number="ACME/2026/88213"),
]


def candidate(value: str) -> PoCandidate:
    return PoCandidate(value=value, evidence=value)


@pytest.mark.parametrize("value", ["PO-55120", "po 55120", "PO55120", "55120"])
def test_exact_references_ignore_format(value):
    assert match_purchase_order([candidate(value)], ORDERS).order.po_number == "PO-55120"


def test_exact_match_wins_over_a_shared_number():
    result = match_purchase_order([candidate("PO-88213")], ORDERS)

    assert result.order.po_number == "PO-88213"


def test_indirect_reference_finds_a_single_order_by_its_number():
    result = match_purchase_order([candidate("55120/ACME")], ORDERS)

    assert result.order.po_number == "PO-55120"


def test_a_number_shared_by_two_orders_is_ambiguous():
    result = match_purchase_order([candidate("88213/X")], ORDERS)

    assert result.order is None
    assert {order.po_number for order in result.ambiguous} == {"PO-88213", "ACME/2026/88213"}


def test_unknown_reference_matches_nothing():
    result = match_purchase_order([candidate("PO-11111")], ORDERS)

    assert result.order is None
    assert result.ambiguous == []


def test_two_references_to_different_orders_are_ambiguous():
    result = match_purchase_order([candidate("PO-55120"), candidate("PO-88213")], ORDERS)

    assert result.order is None
    assert len(result.ambiguous) == 2


def test_short_digit_runs_are_not_treated_as_po_numbers():
    orders = [PurchaseOrder(po_number="PO-2026-77")]

    assert match_purchase_order([candidate("2026/AB")], orders).order is not None
    assert match_purchase_order([candidate("77/AB")], orders).order is None


def test_a_shared_year_does_not_match_every_order():
    orders = [
        PurchaseOrder(po_number="IITM/PUR/2026-27/0417"),
        PurchaseOrder(po_number="IITM/PUR/2026-27/0425"),
    ]

    result = match_purchase_order([candidate("PUR/2026-27/0425")], orders)

    assert result.order.po_number == "IITM/PUR/2026-27/0425"


def test_find_by_number_ignores_format():
    assert find_by_number("po55120", ORDERS).po_number == "PO-55120"
    assert find_by_number("PO-1", ORDERS) is None


class TestDetector:
    TEXT = "Invoice No: INV-1\nYour ref 88213/ACME dated 2 Oct"

    async def detect(self, *candidates: PoCandidate) -> list[PoCandidate]:
        llm = FakeLlm(PoDetectionOutput(candidates=list(candidates)))
        return await PoDetector(llm).detect(self.TEXT)

    async def test_keeps_a_reference_found_in_the_text(self):
        found = PoCandidate(value="88213/ACME", evidence="Your ref 88213/ACME dated 2 Oct")

        assert await self.detect(found) == [found]

    async def test_drops_a_made_up_value(self):
        invented = PoCandidate(value="PO-99999", evidence="Your ref 88213/ACME dated 2 Oct")

        assert await self.detect(invented) == []

    async def test_drops_made_up_evidence(self):
        invented = PoCandidate(value="88213/ACME", evidence="PO Reference: 88213/ACME")

        assert await self.detect(invented) == []

    async def test_tolerates_different_spacing(self):
        spaced = PoCandidate(value="88213/ ACME", evidence="Your  ref 88213/ACME dated 2 Oct")

        assert len(await self.detect(spaced)) == 1


class TestVerifierRowRetry:
    TEXT = "1 | Chair | 2 | 500.00\n2 | Desk | 1 | 400.00"

    def answer(self, rows: int) -> VerificationOutput:
        lines = [
            LineItem(description=f"Row {n}", quantity=1, unit_price=1, amount=1)
            for n in range(rows)
        ]
        return VerificationOutput(
            invoice=InvoiceFacts(
                invoice_number=None,
                invoice_date=None,
                vendor=None,
                currency=None,
                line_items=lines,
                subtotal=None,
                tax=None,
                charges=[],
                total=None,
            ),
            purchase_order=PoFacts(
                vendor_field=None,
                vendor=None,
                total_field=None,
                total=None,
                currency_field=None,
                currency=None,
            ),
            vendor_match="unclear",
            discrepancies=[],
        )

    async def test_asks_again_when_rows_are_missing(self):
        llm = FakeLlm(self.answer(1), self.answer(2))

        output = await InvoiceVerifier(llm).verify(self.TEXT, ORDERS[0])

        assert len(output.invoice.line_items) == 2
        assert "has 2 rows" in llm.calls[1][1]

    async def test_a_complete_answer_is_not_questioned(self):
        llm = FakeLlm(self.answer(2))

        await InvoiceVerifier(llm).verify(self.TEXT, ORDERS[0])

        assert len(llm.calls) == 1

    async def test_keeps_the_first_answer_if_the_retry_is_no_better(self):
        llm = FakeLlm(self.answer(1), self.answer(1))

        output = await InvoiceVerifier(llm).verify(self.TEXT, ORDERS[0])

        assert len(output.invoice.line_items) == 1
