"""The stricter rules added after the evaluation. Each test names the real case
it stops, or the false alarm it must not raise."""

import pytest

from app.domain.models import PurchaseOrder
from app.domain.runs import CheckOutcome, CheckResult, LineItem
from app.workflow.checks import (
    BankDetailsCheck,
    CheckContext,
    InvoiceDateCheck,
    LineArithmeticCheck,
    PoLineCheck,
    ReadingAgreementCheck,
    TaxRateCheck,
    VendorCheck,
)
from tests.unit.test_checks import (
    ORDER,
    TEXT,
    context,
    document,
    earlier_run,
    invoice,
    verification,
)

ITEMISED = PurchaseOrder(
    id="po-1",
    po_number="PO-2",
    fields={
        "line_items": [
            {"description": "Chair", "qty": 2, "unit_price": 250},
            {"description": "Desk", "qty": 1, "unit_price": 400},
        ]
    },
)


def line(
    description: str, quantity: float, unit_price: float, amount: float, discount=None
) -> LineItem:
    return LineItem(
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        discount_percent=discount,
        amount=amount,
    )


def po_with_line(description: str, qty: float) -> PurchaseOrder:
    return PurchaseOrder(
        id="po-1",
        po_number="PO-9",
        fields={"line_items": [{"description": description, "qty": qty}]},
    )


class TestPoLines:
    def run(self, lines, order=ITEMISED, earlier=()) -> CheckResult:
        facts = verification(invoice(line_items=lines))
        return PoLineCheck().run(context(facts, order=order, earlier=earlier))

    def test_lines_within_the_po_pass(self):
        assert self.run(invoice().line_items).outcome is CheckOutcome.PASS

    def test_a_line_not_on_the_po_needs_review(self):
        result = self.run([*invoice().line_items, line("Gaming headset", 1, 9, 9)])

        assert result.outcome is CheckOutcome.REVIEW
        assert "Gaming headset" in result.message

    def test_a_month_named_on_a_service_line_still_matches(self):
        order = po_with_line("Housekeeping Services, Academic Zone (per month)", 6)
        bill = line("Housekeeping Services, Academic Zone, October 2026", 1, 9, 9)

        assert self.run([bill], order=order).outcome is CheckOutcome.PASS

    def test_a_description_cut_short_still_matches(self):
        order = po_with_line("Corrugated Shipper Box 5-ply, 450x300x300", 10)
        bill = line("Corrugated Shipper Box 5-ply, 450x300x30.", 10, 1, 10)

        assert self.run([bill], order=order).outcome is CheckOutcome.PASS

    @pytest.mark.parametrize(
        "description",
        ["Tablet 10 inch, Android, Wi-Fi only (equivalent)", "Tablet 10 inch, Android, Wi-Fi only"],
    )
    def test_a_substitute_product_needs_review(self, description):
        """H32: a cheaper "equivalent" billed instead of the 4G tablet ordered."""
        order = po_with_line("Tablet 10 inch, Android, 4G", 20)

        assert (
            self.run([line(description, 20, 17200, 344000)], order=order).outcome
            is CheckOutcome.REVIEW
        )

    def test_more_than_the_ordered_quantity_needs_review_even_under_the_total(self):
        """H31: 540 kg billed on a 500 kg PO line, at a lower rate."""
        result = self.run([line("Chair", 3, 100, 300)])

        assert result.outcome is CheckOutcome.REVIEW
        assert "3 billed in total, but the PO orders 2" in result.message

    def test_earlier_invoices_count_towards_the_ordered_quantity(self):
        earlier = earlier_run()
        earlier.verification.invoice.line_items[:] = [line("Chair", 2, 250, 500)]

        assert (
            self.run([line("Chair", 1, 250, 250)], earlier=[earlier]).outcome is CheckOutcome.REVIEW
        )

    def test_a_partial_delivery_passes(self):
        assert self.run([line("Chair", 1, 250, 250)]).outcome is CheckOutcome.PASS

    def test_a_higher_price_than_the_po_needs_review(self):
        result = self.run([line("Desk", 1, 450, 450)])

        assert result.outcome is CheckOutcome.REVIEW
        assert "PO price is 400.00" in result.message

    def test_a_discount_bringing_the_price_to_the_po_price_passes(self):
        order = PurchaseOrder(
            id="po-1",
            po_number="PO-7",
            fields={
                "line_items": [
                    {"description": "Vacuum Sealer Bags", "qty": 20000, "unit_price": 3.8}
                ]
            },
        )

        bill = line("Vacuum Sealer Bags", 20000, 4.0, 76000, discount=5)

        assert self.run([bill], order=order).outcome is CheckOutcome.PASS

    def test_a_po_with_only_a_total_has_no_lines_to_compare(self):
        assert self.run(invoice().line_items, order=ORDER).outcome is CheckOutcome.PASS


class TestLineArithmetic:
    def run(self, item: LineItem) -> CheckOutcome:
        return LineArithmeticCheck().run(context(verification(invoice(line_items=[item])))).outcome

    def test_correct_line_passes(self):
        assert self.run(line("Ladle", 40, 650, 26000)) is CheckOutcome.PASS

    def test_wrong_line_amount_needs_review(self):
        """H30: 40 x 650 printed as 28,000."""
        assert self.run(line("Ladle", 40, 650, 28000)) is CheckOutcome.REVIEW

    def test_a_discounted_line_passes(self):
        assert self.run(line("Bags", 20000, 4, 76000, discount=5)) is CheckOutcome.PASS

    def test_a_discount_the_model_missed_is_not_a_false_alarm_when_gross_matches(self):
        assert self.run(line("Bags", 20000, 4, 80000)) is CheckOutcome.PASS

    def test_a_line_missing_a_value_is_not_judged(self):
        item = LineItem(description="X", quantity=None, unit_price=5, amount=9)

        assert self.run(item) is CheckOutcome.PASS


class TestTaxRate:
    def run(self, text: str, subtotal=900.0, tax=100.0) -> CheckOutcome:
        facts = invoice(subtotal=subtotal, tax=tax)
        return TaxRateCheck().run(context(verification(facts), text=text)).outcome

    def test_split_gst_at_the_printed_rate_passes(self):
        assert self.run("CGST @ 9% 81.00\nSGST @ 9% 81.00", tax=162.0) is CheckOutcome.PASS

    def test_tax_above_the_printed_rate_needs_review(self):
        """P05: GST printed at 18% but charged at 19.6%."""
        outcome = self.run("CGST @ 9% 96.04\nSGST @ 9% 96.04", subtotal=980, tax=192.08)

        assert outcome is CheckOutcome.REVIEW

    def test_igst_is_the_whole_rate(self):
        assert self.run("IGST @ 18% 162.00", tax=162.0) is CheckOutcome.PASS

    def test_a_gstin_is_not_mistaken_for_a_rate(self):
        assert self.run("GSTIN 29AAAFM0000B1Z2 18% off") is CheckOutcome.PASS

    def test_no_printed_rate_is_not_judged(self):
        assert self.run("GST 100.00") is CheckOutcome.PASS

    def test_several_rates_of_one_kind_are_not_judged(self):
        assert self.run("GST @ 5% 10.00\nGST @ 18% 90.00") is CheckOutcome.PASS


DATED = PurchaseOrder(
    id="po-1", po_number="PO-1", fields={**ORDER.fields, "po_date": "20 Oct 2026"}
)


class TestFraudSignals:
    def test_an_invoice_dated_before_its_po_needs_review(self):
        """P01: invoiced twelve days before the PO existed."""
        facts = verification(invoice(invoice_date="08 Oct 2026"))

        assert InvoiceDateCheck().run(context(facts, order=DATED)).outcome is CheckOutcome.REVIEW

    @pytest.mark.parametrize("date", ["20 Oct 2026", "25.10.2026", "not a date"])
    def test_on_or_after_the_po_or_unreadable_passes(self, date):
        facts = verification(invoice(invoice_date=date))

        assert InvoiceDateCheck().run(context(facts, order=DATED)).outcome is CheckOutcome.PASS

    @pytest.mark.parametrize(
        "notice",
        [
            "IMPORTANT: Our bank details have changed. Please remit to A/c 998877.",
            "Kindly transfer the amount to our new account.",
        ],
    )
    def test_a_change_of_bank_details_needs_review(self, notice):
        """P03: the classic payment-diversion notice."""
        assert (
            BankDetailsCheck().run(context(text=f"{TEXT}\n{notice}")).outcome is CheckOutcome.REVIEW
        )

    def test_ordinary_bank_details_pass(self):
        text = f"{TEXT}\nBank: HDFC A/c 12345 IFSC HDFC0001"

        assert BankDetailsCheck().run(context(text=text)).outcome is CheckOutcome.PASS


class TestVendorGstin:
    VENDOR = "29AAAFM0000B1Z2"
    BUYER = "29AAACM0000Z1Z5"
    ORDER = PurchaseOrder(
        id="po-1", po_number="PO-1", fields={**ORDER.fields, "vendor_gstin": VENDOR}
    )

    def run(self, text: str, vendor="Northwind Supplies Ltd", vendor_match="yes") -> CheckOutcome:
        facts = verification(invoice(vendor=vendor), vendor_match=vendor_match)
        return VendorCheck().run(context(facts, text=text, order=self.ORDER)).outcome

    def test_the_po_gstin_on_the_invoice_confirms_the_vendor(self):
        outcome = self.run(f"GSTIN {self.VENDOR} buyer {self.BUYER}", vendor="Northwind Pvt")

        assert outcome is CheckOutcome.PASS

    def test_a_misread_character_still_confirms_the_vendor(self):
        assert self.run("GSTIN 29AAAFM0O00B1Z2") is CheckOutcome.PASS

    def test_same_name_with_another_gstin_needs_review(self):
        """P02: an impostor using the vendor's name."""
        assert self.run(f"GSTIN 07AAAFM9999X1Z0 buyer {self.BUYER}") is CheckOutcome.REVIEW

    def test_another_name_and_gstin_is_rejected_even_if_the_llm_is_unsure(self):
        """H25: a different company quoting a real PO."""
        outcome = self.run(
            f"GSTIN 29AAAFW0000J1Z9 buyer {self.BUYER}",
            vendor="Whitefield Traders",
            vendor_match="unclear",
        )

        assert outcome is CheckOutcome.REJECT

    def test_no_gstin_on_the_invoice_falls_back_to_names(self):
        assert self.run("no tax ids here") is CheckOutcome.PASS


class TestReadingAgreement:
    def test_unsettled_readings_need_review(self):
        unsettled = CheckContext(
            verification=verification(),
            order=ORDER,
            document=document(),
            invoice_text=TEXT,
            earlier_runs=[],
            readings_agree=False,
        )

        assert ReadingAgreementCheck().run(unsettled).outcome is CheckOutcome.REVIEW

    def test_agreeing_readings_pass(self):
        assert ReadingAgreementCheck().run(context()).outcome is CheckOutcome.PASS
