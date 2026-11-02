"""Normalising readings and choosing the best of several."""

import pytest

from app.domain.llm import AnswerStatus, ModelAnswer
from app.domain.runs import Charge, InvoiceFacts, LineItem
from app.workflow.consensus import choose
from app.workflow.facts import normalise_invoice
from tests.unit.test_checks import invoice, verification

TEXT = (
    "Invoice No: INV-1 dated 1 Oct 2026 from Northwind Supplies Ltd\n"
    "Subtotal 900.00\nCGST @ 9% 81.00\nSGST @ 9% 81.00\nTotal 1,062.00"
)
SPLIT_TAX = [Charge(label="CGST @ 9%", amount=81.0), Charge(label="SGST @ 9%", amount=81.0)]


def facts(**changes) -> InvoiceFacts:
    return invoice(**{"tax": None, "charges": SPLIT_TAX, "total": 1062.0, **changes})


class TestNormalise:
    @pytest.mark.parametrize(
        ("tax", "charges"),
        [
            (None, SPLIT_TAX),
            (81.0, SPLIT_TAX),  # half the GST in `tax` and both halves again in charges
            (162.0, SPLIT_TAX),  # the whole GST in `tax` and again in charges
            (162.0, []),
        ],
    )
    def test_split_gst_is_counted_once(self, tax, charges):
        normalised = normalise_invoice(facts(tax=tax, charges=charges), "PO-1")

        assert normalised.tax == 162.0
        assert normalised.charges == []

    def test_half_in_tax_and_the_other_half_as_a_charge_adds_up(self):
        normalised = normalise_invoice(facts(tax=81.0, charges=SPLIT_TAX[1:]), "PO-1")

        assert normalised.tax == 162.0

    def test_other_charges_are_kept(self):
        freight = Charge(label="Freight", amount=50.0)

        normalised = normalise_invoice(facts(charges=[*SPLIT_TAX, freight]), "PO-1")

        assert normalised.charges == [freight]

    def test_the_po_number_is_not_an_invoice_number(self):
        normalised = normalise_invoice(facts(invoice_number="po/1"), "PO-1")

        assert normalised.invoice_number is None


def answer(model: str, **changes) -> ModelAnswer:
    return ModelAnswer(model, AnswerStatus.ANSWERED, 1.0, output=verification(facts(**changes)))


class TestChoose:
    def test_no_answers_means_no_consensus(self):
        failed = ModelAnswer("a", AnswerStatus.FAILED, 1.0, error="down")

        assert choose([failed], TEXT, "PO-1") is None

    def test_the_reading_the_document_supports_wins_over_a_majority(self):
        answers = [
            answer("a", total=1000.0),
            answer("b", total=1000.0),
            answer("c"),
        ]

        consensus = choose(answers, TEXT, "PO-1")

        assert consensus.chosen.model == "c"
        assert consensus.chosen.output.invoice.total == 1062.0

    def test_among_equally_supported_readings_agreement_decides(self):
        answers = [
            answer("a", invoice_date="2 Oct 2026"),
            answer("b"),
            answer("c"),
        ]

        assert choose(answers, TEXT, "PO-1").chosen.model == "b"

    def test_a_reading_whose_line_contradicts_itself_loses(self):
        """A fax read as 6 x 21.50 = 129,000 instead of 6 x 21,500."""
        misread = [LineItem(description="Chair", quantity=6, unit_price=21.5, amount=900)]
        answers = [answer("a", line_items=misread), answer("b")]

        assert choose(answers, TEXT, "PO-1").chosen.model == "b"

    def test_ties_go_to_the_model_listed_first(self):
        assert choose([answer("a"), answer("b")], TEXT, "PO-1").chosen.model == "a"

    def test_a_po_number_offered_as_invoice_number_loses(self):
        answers = [answer("a", invoice_number="PO-1"), answer("b")]

        assert choose(answers, TEXT, "PO-1").chosen.model == "b"

    def test_totals_agreed_by_two_models_are_settled(self):
        answers = [answer("a"), answer("b"), answer("c", total=999.0)]

        assert choose(answers, TEXT, "PO-1").readings_agree

    def test_three_different_totals_none_printed_are_unsettled(self):
        answers = [answer("a", total=11.11), answer("b", total=22.22), answer("c", total=33.33)]

        assert not choose(answers, TEXT, "PO-1").readings_agree

    def test_a_single_reading_is_settled(self):
        assert choose([answer("a")], TEXT, "PO-1").readings_agree

    def test_failed_answers_are_left_out(self):
        failed = ModelAnswer("down", AnswerStatus.FAILED, 9.0, error="timed out")

        consensus = choose([failed, answer("b")], TEXT, "PO-1")

        assert [reading.model for reading in consensus.readings] == ["b"]
