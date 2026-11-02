"""Rules about the document itself: required fields, faithful reading, scan quality."""

from app.domain.models import PurchaseOrder, WarningCode
from app.workflow.checks.base import (
    NUMBER,
    CheckContext,
    CheckResult,
    cents,
    passed,
    review,
    squeeze,
)

_REVIEW_WARNINGS = {
    WarningCode.PARSE_FALLBACK: "A page needed the backup OCR",
    WarningCode.LOW_OCR_CONFIDENCE: "A page had low OCR confidence",
    WarningCode.PAGE_FAILED: "A page could not be read",
}


class RequiredFieldsCheck:
    name = "required_fields"

    def run(self, context: CheckContext) -> CheckResult:
        invoice = context.verification.invoice
        source = squeeze(context.invoice_text)
        missing = [
            label
            for label, value in (
                ("invoice number", invoice.invoice_number),
                ("invoice date", invoice.invoice_date),
                ("vendor", invoice.vendor),
            )
            if value is None or squeeze(value) not in source
        ]
        if invoice.total is None:
            missing.append("total")
        if missing:
            return review(self, f"The invoice is missing: {', '.join(missing)}.")
        return passed(self, "All required fields are on the invoice.")


class ReadingAccuracyCheck:
    """Confirms the numbers the LLM reported are really in the documents."""

    name = "reading_accuracy"

    def run(self, context: CheckContext) -> CheckResult:
        verification = context.verification
        invoice_total = verification.invoice.total
        printed = {
            cents(float(number.replace(",", "")))
            for number in NUMBER.findall(context.invoice_text)
        }
        if invoice_total is not None and cents(invoice_total) not in printed:
            return review(
                self, f"The total {invoice_total:,.2f} does not appear on the invoice."
            )

        po = verification.purchase_order
        if po.total is not None and _field_amount(context.order, po.total_field) != cents(po.total):
            return review(
                self, f"The PO total {po.total:,.2f} was not found in field {po.total_field!r}."
            )
        return passed(self, "Reported amounts match the source documents.")


def _field_amount(order: PurchaseOrder, field: str | None) -> int | None:
    value = order.fields.get(field) if field else None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return cents(value)
    if isinstance(value, str):
        match = NUMBER.search(value)
        return cents(float(match.group().replace(",", ""))) if match else None
    return None


class ExtractionQualityCheck:
    name = "extraction_quality"

    def run(self, context: CheckContext) -> CheckResult:
        problems = sorted(
            {
                _REVIEW_WARNINGS[warning.code]
                for warning in context.document.warnings
                if warning.code in _REVIEW_WARNINGS
            }
        )
        if problems:
            return review(self, f"{'; '.join(problems)}, so the text may be wrong.")
        return passed(self, "The document was read cleanly.")


class ReadingAgreementCheck:
    """When the models read the invoice differently and the document itself
    can't settle which reading is right, a person decides."""

    name = "reading_agreement"

    def run(self, context: CheckContext) -> CheckResult:
        if context.readings_agree:
            return passed(self, "The models' readings agree, or the document settles them.")
        return review(
            self,
            "The models read the total differently, and the document doesn't settle "
            "which is right.",
        )
