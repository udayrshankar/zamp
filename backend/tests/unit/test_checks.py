import pytest

from app.domain.models import (
    Document,
    ExtractionWarning,
    PurchaseOrder,
    WarningCode,
)
from app.domain.runs import (
    CheckOutcome,
    CheckResult,
    Charge,
    Decision,
    InvoiceFacts,
    LineItem,
    PoFacts,
    Run,
    VerificationOutput,
)
from app.workflow.checks import (
    ArithmeticCheck,
    CheckContext,
    CurrencyCheck,
    DuplicateCheck,
    ExtractionQualityCheck,
    PoAmountCheck,
    ReadingAccuracyCheck,
    RequiredFieldsCheck,
    Tolerance,
    VendorCheck,
    build_checks,
)
from app.workflow.decision_policy import decide

ORDER = PurchaseOrder(
    id="po-1",
    po_number="PO-1",
    fields={"supplier": "Northwind Supplies Ltd", "grand_total": 1000.0, "note": "n/a"},
)
TEXT = (
    "Invoice INV-1 dated 1 Oct 2026 from Northwind Supplies Ltd\n"
    "Subtotal 900.00\nGST 100.00\nTotal 1,000.00"
)
TOLERANCE = Tolerance(accept_percent=2, reject_percent=10)


def invoice(**changes) -> InvoiceFacts:
    values = {
        "invoice_number": "INV-1",
        "invoice_date": "1 Oct 2026",
        "vendor": "Northwind Supplies Ltd",
        "currency": None,
        "line_items": [
            LineItem(description="Chair", quantity=2, unit_price=250, amount=500),
            LineItem(description="Desk", quantity=1, unit_price=400, amount=400),
        ],
        "subtotal": 900.0,
        "tax": 100.0,
        "charges": [],
        "total": 1000.0,
    }
    return InvoiceFacts(**{**values, **changes})


def po_facts(**changes) -> PoFacts:
    values = {
        "vendor_field": "supplier",
        "vendor": "Northwind Supplies Ltd",
        "total_field": "grand_total",
        "total": 1000.0,
        "currency_field": None,
        "currency": None,
    }
    return PoFacts(**{**values, **changes})


def verification(invoice_facts=None, po=None, vendor_match="yes", discrepancies=()):
    return VerificationOutput(
        invoice=invoice_facts or invoice(),
        purchase_order=po or po_facts(),
        vendor_match=vendor_match,
        discrepancies=list(discrepancies),
    )


def document(warnings=(), sha256="new-hash") -> Document:
    return Document(
        filename="a.pdf", sha256=sha256, size_bytes=1, file_id="1", warnings=list(warnings)
    )


def context(result=None, earlier=(), doc=None, text=TEXT, order=ORDER) -> CheckContext:
    return CheckContext(
        verification=result or verification(),
        order=order,
        document=doc or document(),
        invoice_text=text,
        earlier_runs=list(earlier),
    )


def earlier_run(total=400.0, decision=Decision.ACCEPT, sha256="old", number="INV-0", vendor="Other"):
    return Run(
        document_id="d",
        filename="earlier.pdf",
        sha256=sha256,
        purchase_order_id="po-1",
        decision=decision,
        verification=verification(invoice(total=total, invoice_number=number, vendor=vendor)),
    )


class TestRequiredFields:
    def test_complete_invoice_passes(self):
        assert RequiredFieldsCheck().run(context()).outcome is CheckOutcome.PASS

    @pytest.mark.parametrize("field", ["invoice_number", "invoice_date", "vendor", "total"])
    def test_missing_field_needs_review(self, field):
        result = RequiredFieldsCheck().run(context(verification(invoice(**{field: None}))))

        assert result.outcome is CheckOutcome.REVIEW


class TestRequiredFieldsAreReal:
    def test_a_value_that_is_not_on_the_invoice_counts_as_missing(self):
        result = RequiredFieldsCheck().run(
            context(verification(invoice(invoice_number="INV-777")))
        )

        assert result.outcome is CheckOutcome.REVIEW
        assert "invoice number" in result.message

    @pytest.mark.parametrize("placeholder", ["null", "None", " N/A ", "", "unknown"])
    def test_placeholder_text_from_the_llm_means_missing(self, placeholder):
        facts = invoice(invoice_number=placeholder)

        assert facts.invoice_number is None
        assert (
            RequiredFieldsCheck().run(context(verification(facts))).outcome
            is CheckOutcome.REVIEW
        )

    def test_two_invoices_without_numbers_are_not_duplicates(self):
        earlier = earlier_run(number="null", vendor="Northwind Supplies Ltd")
        current = verification(invoice(invoice_number="null"))

        result = DuplicateCheck().run(context(current, earlier=[earlier]))

        assert result.outcome is CheckOutcome.PASS


class TestReadingAccuracy:
    def test_accurate_reading_passes(self):
        assert ReadingAccuracyCheck().run(context()).outcome is CheckOutcome.PASS

    def test_total_that_is_not_on_the_invoice_needs_review(self):
        result = ReadingAccuracyCheck().run(context(verification(invoice(total=7777.0))))

        assert result.outcome is CheckOutcome.REVIEW

    def test_po_total_from_the_wrong_field_needs_review(self):
        result = ReadingAccuracyCheck().run(context(verification(po=po_facts(total=999.0))))

        assert result.outcome is CheckOutcome.REVIEW

    def test_po_total_from_a_field_that_does_not_exist_needs_review(self):
        result = ReadingAccuracyCheck().run(
            context(verification(po=po_facts(total_field="invented")))
        )

        assert result.outcome is CheckOutcome.REVIEW

    def test_po_total_stored_as_text_is_understood(self):
        order = PurchaseOrder(po_number="PO-2", fields={"grand_total": "INR 1,000.00"})

        assert ReadingAccuracyCheck().run(context(order=order)).outcome is CheckOutcome.PASS


class TestArithmetic:
    def test_correct_invoice_passes(self):
        assert ArithmeticCheck().run(context()).outcome is CheckOutcome.PASS

    def test_lines_that_miss_the_subtotal_need_review(self):
        result = ArithmeticCheck().run(context(verification(invoice(subtotal=950.0, total=1050.0))))

        assert result.outcome is CheckOutcome.REVIEW
        assert "900.00" in result.message

    def test_total_that_misses_the_sum_needs_review(self):
        result = ArithmeticCheck().run(context(verification(invoice(total=1100.0))))

        assert result.outcome is CheckOutcome.REVIEW

    def test_charges_are_part_of_the_total(self):
        facts = invoice(charges=[Charge(label="Handling", amount=25)], total=1025.0)

        assert ArithmeticCheck().run(context(verification(facts))).outcome is CheckOutcome.PASS

    def test_rounding_of_a_cent_per_line_is_allowed(self):
        facts = invoice(subtotal=900.01, tax=99.99)

        assert ArithmeticCheck().run(context(verification(facts))).outcome is CheckOutcome.PASS

    def test_embedded_tax_with_no_subtotal_passes(self):
        facts = invoice(subtotal=None, tax=None, total=900.0)

        assert ArithmeticCheck().run(context(verification(facts))).outcome is CheckOutcome.PASS

    def test_lines_without_amounts_are_not_summed(self):
        facts = invoice(line_items=[LineItem(description="Bundle", quantity=None, unit_price=None, amount=None)])

        assert ArithmeticCheck().run(context(verification(facts))).outcome is CheckOutcome.PASS


class TestPoAmount:
    @pytest.mark.parametrize(
        ("total", "outcome"),
        [
            (1000.00, CheckOutcome.PASS),
            (1020.00, CheckOutcome.PASS),  # exactly 2% over
            (1020.01, CheckOutcome.REVIEW),
            (1100.00, CheckOutcome.REVIEW),  # exactly 10% over
            (1100.01, CheckOutcome.REJECT),
            (400.00, CheckOutcome.PASS),  # partial billing
        ],
    )
    def test_tolerance_boundaries(self, total, outcome):
        result = PoAmountCheck(TOLERANCE).run(context(verification(invoice(total=total))))

        assert result.outcome is outcome

    def test_missing_po_total_needs_review(self):
        result = PoAmountCheck(TOLERANCE).run(context(verification(po=po_facts(total=None))))

        assert result.outcome is CheckOutcome.REVIEW

    def test_earlier_invoices_count_towards_the_po(self):
        current = verification(invoice(total=250.0))

        result = PoAmountCheck(TOLERANCE).run(
            context(current, earlier=[earlier_run(400.0), earlier_run(400.0)])
        )

        assert result.outcome is CheckOutcome.REVIEW
        assert "1,050.00" in result.message

    def test_third_split_invoice_can_be_rejected(self):
        current = verification(invoice(total=500.0))

        result = PoAmountCheck(TOLERANCE).run(
            context(current, earlier=[earlier_run(400.0), earlier_run(400.0)])
        )

        assert result.outcome is CheckOutcome.REJECT

    def test_rejected_invoices_do_not_count(self):
        result = PoAmountCheck(TOLERANCE).run(
            context(
                verification(invoice(total=900.0)),
                earlier=[earlier_run(900.0, Decision.REJECT)],
            )
        )

        assert result.outcome is CheckOutcome.PASS

    def test_invoices_in_review_count_because_they_may_still_be_paid(self):
        result = PoAmountCheck(TOLERANCE).run(
            context(
                verification(invoice(total=900.0)),
                earlier=[earlier_run(900.0, Decision.REVIEW)],
            )
        )

        assert result.outcome is CheckOutcome.REJECT

    def test_invoices_on_other_orders_do_not_count(self):
        other = earlier_run(900.0)
        other.purchase_order_id = "po-2"

        result = PoAmountCheck(TOLERANCE).run(context(earlier=[other]))

        assert result.outcome is CheckOutcome.PASS


class TestDuplicate:
    def test_new_invoice_passes(self):
        assert DuplicateCheck().run(context(earlier=[earlier_run()])).outcome is CheckOutcome.PASS

    def test_same_file_is_rejected(self):
        result = DuplicateCheck().run(context(earlier=[earlier_run(sha256="new-hash")]))

        assert result.outcome is CheckOutcome.REJECT

    def test_rescan_with_the_same_number_and_vendor_is_rejected(self):
        earlier = earlier_run(number="inv 1", vendor="NORTHWIND SUPPLIES")

        result = DuplicateCheck().run(context(earlier=[earlier]))

        assert result.outcome is CheckOutcome.REJECT

    def test_same_number_and_total_from_a_renamed_vendor_is_rejected(self):
        earlier = earlier_run(number="INV-1", total=1000.0, vendor="Different Name")

        assert DuplicateCheck().run(context(earlier=[earlier])).outcome is CheckOutcome.REJECT

    def test_same_number_from_another_vendor_is_not_a_duplicate(self):
        earlier = earlier_run(number="INV-1", total=5.0, vendor="Different Name")

        assert DuplicateCheck().run(context(earlier=[earlier])).outcome is CheckOutcome.PASS

    def test_a_rejected_invoice_can_be_resubmitted(self):
        earlier = earlier_run(sha256="new-hash", decision=Decision.REJECT)

        assert DuplicateCheck().run(context(earlier=[earlier])).outcome is CheckOutcome.PASS


class TestVendor:
    def outcome(self, invoice_vendor, po_vendor, llm):
        result = verification(invoice(vendor=invoice_vendor), po_facts(vendor=po_vendor), llm)
        return VendorCheck().run(context(result)).outcome

    def test_same_name_passes_even_if_the_llm_disagrees(self):
        assert self.outcome("Northwind Ltd", "NORTHWIND LIMITED", "no") is CheckOutcome.PASS

    def test_variant_name_confirmed_by_the_llm_passes(self):
        assert (
            self.outcome("Northwind Supplies", "Northwind Office Supplies Pvt Ltd", "yes")
            is CheckOutcome.PASS
        )

    def test_rejects_only_when_the_llm_and_names_agree(self):
        assert self.outcome("Contoso Traders", "Northwind Supplies", "no") is CheckOutcome.REJECT

    def test_llm_saying_yes_cannot_override_unrelated_names(self):
        assert self.outcome("Contoso Traders", "Northwind Supplies", "yes") is CheckOutcome.REVIEW

    def test_shared_word_but_llm_says_no_needs_review(self):
        assert self.outcome("Northwind Foods", "Northwind Supplies", "no") is CheckOutcome.REVIEW

    def test_missing_po_vendor_needs_review(self):
        assert self.outcome("Northwind", None, "unclear") is CheckOutcome.REVIEW


class TestCurrency:
    INR_ORDER = PurchaseOrder(po_number="PO-3", fields={"currency": "INR"})

    def test_conflict_needs_review(self):
        result = verification(invoice(currency="USD"), po_facts(currency="INR"))

        assert CurrencyCheck().run(context(result)).outcome is CheckOutcome.REVIEW

    def test_a_currency_the_llm_missed_is_found_in_the_text(self):
        result = CurrencyCheck().run(
            context(text="Total Amount (USD) 100.00", order=self.INR_ORDER)
        )

        assert result.outcome is CheckOutcome.REVIEW
        assert "USD" in result.message

    def test_the_po_currency_on_the_invoice_is_fine(self):
        result = CurrencyCheck().run(
            context(text="Total Amount (INR) 100.00", order=self.INR_ORDER)
        )

        assert result.outcome is CheckOutcome.PASS

    def test_missing_currency_is_no_conflict(self):
        assert CurrencyCheck().run(context()).outcome is CheckOutcome.PASS


class TestExtractionQuality:
    @pytest.mark.parametrize(
        "code",
        [WarningCode.PARSE_FALLBACK, WarningCode.LOW_OCR_CONFIDENCE, WarningCode.PAGE_FAILED],
    )
    def test_shaky_reading_needs_review(self, code):
        doc = document([ExtractionWarning(code=code, message="x")])

        assert ExtractionQualityCheck().run(context(doc=doc)).outcome is CheckOutcome.REVIEW

    def test_a_blank_page_is_fine(self):
        doc = document([ExtractionWarning(code=WarningCode.BLANK_PAGE, message="x")])

        assert ExtractionQualityCheck().run(context(doc=doc)).outcome is CheckOutcome.PASS


def check(outcome: CheckOutcome, message: str = "m") -> CheckResult:
    return CheckResult(name="c", outcome=outcome, message=message)


class TestDecisionPolicy:
    def test_all_passing_is_accepted(self):
        assert decide([check(CheckOutcome.PASS)])[0] is Decision.ACCEPT

    def test_any_flag_means_review(self):
        decision, reasons = decide([check(CheckOutcome.PASS), check(CheckOutcome.REVIEW, "why")])

        assert decision is Decision.REVIEW
        assert reasons == ["why"]

    def test_reject_beats_review_and_keeps_both_reasons(self):
        decision, reasons = decide(
            [check(CheckOutcome.REVIEW, "flag"), check(CheckOutcome.REJECT, "stop")]
        )

        assert decision is Decision.REJECT
        assert reasons == ["stop", "flag"]

    def test_a_clean_invoice_passes_every_check(self):
        results = [item.run(context()) for item in build_checks(TOLERANCE)]

        assert decide(results)[0] is Decision.ACCEPT
