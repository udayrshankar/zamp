"""Units of measure: a line billed in one unit is checked against a PO line in
another, and units that don't convert go to a person."""

import pytest

from app.domain.models import PurchaseOrder
from app.domain.runs import CheckOutcome, CheckResult, LineItem
from app.workflow import units
from app.workflow.checks import PoLineCheck
from app.workflow.checks.lines import match_line, po_lines_of
from tests.unit.test_checks import context, earlier_run, invoice, verification


def steel_po(**row) -> PurchaseOrder:
    line = {"description": "TMT Steel Rod, 12 mm, Fe 500", "qty": 2, "unit_price": 62000, **row}
    return PurchaseOrder(id="po-1", po_number="PO-7", fields={"line_items": [line]})


TONNES = steel_po(unit="MT")


def bill(quantity: float, unit: str | None, rate: float, description="TMT Steel Rod, 12 mm, Fe 500"):
    return LineItem(
        description=description, quantity=quantity, unit=unit, unit_price=rate, amount=quantity * rate
    )


def check(lines, order=TONNES, earlier=()) -> CheckResult:
    facts = verification(invoice(line_items=lines))
    return PoLineCheck().run(context(facts, order=order, earlier=earlier))


class TestParse:
    @pytest.mark.parametrize("text", ["kg", "KGS", "Kg.", "kilograms", "per kg"])
    def test_spellings_of_kg(self, text):
        assert units.parse(text) == units.parse("kg")

    @pytest.mark.parametrize("text", ["MT", "ton", "Tonnes", "metric tons"])
    def test_tons_are_metric_tonnes(self, text):
        assert units.ratio(units.parse(text), units.parse("kg")) == 1000

    @pytest.mark.parametrize("text", [None, "", "N/A", "null"])
    def test_no_unit(self, text):
        assert units.parse(text) is None

    def test_an_unknown_unit_matches_only_itself(self):
        assert units.ratio(units.parse("Boxes"), units.parse("box")) == 1
        assert units.ratio(units.parse("box"), units.parse("carton")) is None

    def test_different_dimensions_do_not_convert(self):
        assert units.ratio(units.parse("kg"), units.parse("litre")) is None

    @pytest.mark.parametrize(
        ("description", "unit"),
        [("Copper Cable, 16 sq mm (metre)", "metre"), ("Sand, per tonne", "tonne"), ("Paint (in L)", "litre")],
    )
    def test_a_unit_named_in_a_description(self, description, unit):
        assert units.in_text(description).label == unit

    @pytest.mark.parametrize(
        "description", ["HPLC Column, C18, 250 mm", "Mounting Resin, 1 kg", "Housekeeping (per month)"]
    )
    def test_sizes_in_a_description_are_not_its_unit(self, description):
        assert units.in_text(description) is None


class TestPoLinesInOtherUnits:
    def test_kg_billed_against_tonnes_ordered_passes(self):
        assert check([bill(2000, "kg", 62)]).outcome is CheckOutcome.PASS

    def test_tonnes_billed_against_kg_ordered_passes(self):
        order = steel_po(qty=2000, unit_price=62, unit="kg")

        assert check([bill(2, "tonnes", 62000)], order=order).outcome is CheckOutcome.PASS

    def test_more_than_ordered_after_converting_needs_review(self):
        result = check([bill(2500, "kg", 62)])

        assert result.outcome is CheckOutcome.REVIEW
        assert "2.5 tonne billed in total, but the PO orders 2 tonne" in result.message

    def test_a_higher_price_after_converting_needs_review(self):
        result = check([bill(2000, "kg", 70)])

        assert result.outcome is CheckOutcome.REVIEW
        assert "70,000.00 a tonne" in result.message

    def test_units_that_do_not_convert_need_review_with_the_reason(self):
        result = check([bill(2000, "litres", 62)])

        assert result.outcome is CheckOutcome.REVIEW
        assert "billed in litre, but the PO orders it in tonne" in result.message

    def test_earlier_invoices_in_another_unit_count_towards_the_po(self):
        earlier = earlier_run()
        earlier.verification.invoice.line_items[:] = [bill(1.5, "MT", 62000)]

        result = check([bill(1000, "kg", 62)], earlier=[earlier])

        assert result.outcome is CheckOutcome.REVIEW
        assert "2.5 tonne billed in total" in result.message

    def test_a_missing_unit_is_taken_as_the_po_unit(self):
        assert check([bill(2, None, 62000)]).outcome is CheckOutcome.PASS

    def test_a_po_without_units_compares_as_before(self):
        assert check([bill(2, "kg", 62000)], order=steel_po()).outcome is CheckOutcome.PASS

    def test_the_unit_key_is_read_whatever_its_case(self):
        assert po_lines_of(steel_po(UOM="MT").fields)[0].unit == units.parse("tonne")

    def test_a_unit_word_in_a_description_does_not_stop_a_match(self):
        lines = po_lines_of(steel_po(description="TMT Steel Rod, 12 mm, Fe 500 (MT)").fields)

        assert match_line("TMT Steel Rod 12 mm Fe 500, in kg", lines) == 0
