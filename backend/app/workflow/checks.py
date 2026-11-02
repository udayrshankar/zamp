"""The rules that decide an invoice. Each one is small and independent, so a new
rule is a new class added to `build_checks`.

These are code rather than LLM judgement because they have to be right, and
repeatable, every time. The LLM reads the documents; these confirm what it read.
"""

import re
from dataclasses import dataclass
from typing import Protocol

from app.domain.models import Document, PurchaseOrder, WarningCode
from app.domain.runs import (
    CheckOutcome,
    CheckResult,
    Decision,
    Discrepancy,
    Run,
    VerificationOutput,
)
from app.workflow.po_matcher import normalise

_COMPANY_NOISE = {"PVT", "PRIVATE", "LTD", "LIMITED", "LLC", "INC", "CO", "CORP", "THE", "AND"}
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_LINE_NOISE = {"and", "for", "the", "with", "per", "set", "pack", "box", "item", "unit"}
_CURRENCY_CODE = re.compile(r"\b(INR|USD|EUR|GBP|AED|SGD|JPY|CNY|AUD|CAD|CHF)\b")
_REVIEW_WARNINGS = {
    WarningCode.PARSE_FALLBACK: "A page needed the backup OCR",
    WarningCode.LOW_OCR_CONFIDENCE: "A page had low OCR confidence",
    WarningCode.PAGE_FAILED: "A page could not be read",
}


@dataclass(frozen=True, slots=True)
class Tolerance:
    accept_percent: float
    reject_percent: float


@dataclass(frozen=True, slots=True)
class CheckContext:
    verification: VerificationOutput
    order: PurchaseOrder
    document: Document
    invoice_text: str
    earlier_runs: list[Run]


class Check(Protocol):
    name: str

    def run(self, context: CheckContext) -> CheckResult:
        ...


def _cents(amount: float) -> int:
    return round(amount * 100)


def _money(cents: int) -> str:
    return f"{cents / 100:,.2f}"


def _passed(check: Check, message: str) -> CheckResult:
    return CheckResult(name=check.name, outcome=CheckOutcome.PASS, message=message)


def _review(check: Check, message: str) -> CheckResult:
    return CheckResult(name=check.name, outcome=CheckOutcome.REVIEW, message=message)


def _reject(check: Check, message: str) -> CheckResult:
    return CheckResult(name=check.name, outcome=CheckOutcome.REJECT, message=message)


class RequiredFieldsCheck:
    name = "required_fields"

    def run(self, context: CheckContext) -> CheckResult:
        invoice = context.verification.invoice
        source = _squeeze(context.invoice_text)
        missing = [
            label
            for label, value in (
                ("invoice number", invoice.invoice_number),
                ("invoice date", invoice.invoice_date),
                ("vendor", invoice.vendor),
            )
            if value is None or _squeeze(value) not in source
        ]
        if invoice.total is None:
            missing.append("total")
        if missing:
            return _review(self, f"The invoice is missing: {', '.join(missing)}.")
        return _passed(self, "All required fields are on the invoice.")


class ReadingAccuracyCheck:
    """Confirms the numbers the LLM reported are really in the documents."""

    name = "reading_accuracy"

    def run(self, context: CheckContext) -> CheckResult:
        verification = context.verification
        invoice_total = verification.invoice.total
        printed = {
            _cents(float(number.replace(",", "")))
            for number in _NUMBER.findall(context.invoice_text)
        }
        if invoice_total is not None and _cents(invoice_total) not in printed:
            return _review(
                self, f"The total {invoice_total:,.2f} does not appear on the invoice."
            )

        po = verification.purchase_order
        if po.total is not None and _field_amount(context.order, po.total_field) != _cents(po.total):
            return _review(
                self, f"The PO total {po.total:,.2f} was not found in field {po.total_field!r}."
            )
        return _passed(self, "Reported amounts match the source documents.")


def _field_amount(order: PurchaseOrder, field: str | None) -> int | None:
    value = order.fields.get(field) if field else None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return _cents(value)
    if isinstance(value, str):
        match = _NUMBER.search(value)
        return _cents(float(match.group().replace(",", ""))) if match else None
    return None


class ArithmeticCheck:
    name = "arithmetic"

    def run(self, context: CheckContext) -> CheckResult:
        invoice = context.verification.invoice
        amounts = [item.amount for item in invoice.line_items]
        added = sum(_cents(charge.amount) for charge in invoice.charges) + _cents(invoice.tax or 0)

        if amounts and None not in amounts:
            line_sum = sum(_cents(amount) for amount in amounts)
            allowance = len(amounts)
            if invoice.subtotal is not None:
                if abs(line_sum - _cents(invoice.subtotal)) > allowance:
                    return _review(
                        self,
                        f"Line items add up to {_money(line_sum)}, "
                        f"but the subtotal says {invoice.subtotal:,.2f}.",
                    )
            elif invoice.total is not None and abs(line_sum + added - _cents(invoice.total)) > allowance:
                return _review(
                    self,
                    f"Line items and charges add up to {_money(line_sum + added)}, "
                    f"but the total says {invoice.total:,.2f}.",
                )

        if invoice.subtotal is not None and invoice.total is not None:
            expected = _cents(invoice.subtotal) + added
            if abs(expected - _cents(invoice.total)) > 1:
                return _review(
                    self,
                    f"Subtotal, tax and charges add up to {_money(expected)}, "
                    f"but the total says {invoice.total:,.2f}.",
                )
        return _passed(self, "The invoice arithmetic adds up.")


class PoAmountCheck:
    """Compares everything billed so far against the PO, so that invoices which
    look fine alone can't add up to more than was ordered. Invoices in review
    count too: until someone rejects one, it may still be paid."""

    name = "po_amount"

    def __init__(self, tolerance: Tolerance) -> None:
        self._tolerance = tolerance

    def run(self, context: CheckContext) -> CheckResult:
        invoice_total = context.verification.invoice.total
        po_total = context.verification.purchase_order.total
        if invoice_total is None:
            return _review(self, "The invoice has no total to compare with the PO.")
        if po_total is None:
            return _review(self, "The PO has no total to compare with the invoice.")

        earlier = sum(
            _cents(run.verification.invoice.total)
            for run in context.earlier_runs
            if run.decision is not Decision.REJECT
            and run.purchase_order_id == context.order.id
            and run.verification is not None
            and run.verification.invoice.total is not None
        )
        limit = _cents(po_total)
        billed = earlier + _cents(invoice_total)
        over = billed - limit
        billed_text = (
            f"{_money(billed)} billed in total, including {_money(earlier)} earlier"
            if earlier
            else f"Invoice total {_money(billed)}"
        )
        comparison = f"{billed_text}, against a PO of {_money(limit)}"

        # Whole cents, so that exactly 2% or 10% lands on the right side.
        if over * 100 > self._tolerance.reject_percent * limit:
            return _reject(self, f"{comparison}: over by more than {self._tolerance.reject_percent:g}%.")
        if over * 100 > self._tolerance.accept_percent * limit:
            return _review(self, f"{comparison}: over by more than {self._tolerance.accept_percent:g}%.")
        if over < 0:
            return _passed(self, f"{comparison}: {_money(-over)} still open on the PO.")
        return _passed(self, f"{comparison}: within tolerance.")


class DuplicateCheck:
    name = "duplicate"

    def run(self, context: CheckContext) -> CheckResult:
        invoice = context.verification.invoice
        number = normalise(invoice.invoice_number or "")
        for run in context.earlier_runs:
            if run.decision is Decision.REJECT:
                continue
            if run.sha256 == context.document.sha256:
                return _reject(self, f"This exact file was already processed as {run.filename}.")
            earlier = run.verification.invoice if run.verification else None
            if earlier is None or not number or normalise(earlier.invoice_number or "") != number:
                continue
            same_vendor = _company(earlier.vendor) == _company(invoice.vendor)
            same_total = earlier.total is not None and earlier.total == invoice.total
            if same_vendor or same_total:
                return _reject(
                    self,
                    f"Invoice {invoice.invoice_number} was already processed as {run.filename}.",
                )
        return _passed(self, "No earlier invoice matches this one.")


def _company(name: str | None) -> set[str]:
    words = re.findall(r"[A-Z0-9]+", (name or "").upper())
    return set(words) - _COMPANY_NOISE


class VendorCheck:
    """Rejecting needs both the LLM and the names to disagree, because a wrong
    rejection of a real supplier is hard to notice."""

    name = "vendor"

    def run(self, context: CheckContext) -> CheckResult:
        verification = context.verification
        invoice_vendor = _company(verification.invoice.vendor)
        po_vendor = _company(verification.purchase_order.vendor)
        if not invoice_vendor or not po_vendor:
            return _review(self, "The vendor could not be compared with the PO.")

        names = f"{verification.invoice.vendor} / {verification.purchase_order.vendor}"
        shared = invoice_vendor & po_vendor
        if invoice_vendor == po_vendor or (shared and verification.vendor_match == "yes"):
            return _passed(self, f"The vendor matches: {names}.")
        if not shared and verification.vendor_match == "no":
            return _reject(self, f"The vendor does not match the PO: {names}.")
        return _review(self, f"The vendor match is unclear: {names}.")


class CurrencyCheck:
    """Reads the invoice text as well as the LLM's answer, because a missed
    currency would otherwise look like there was nothing to compare."""

    name = "currency"

    def run(self, context: CheckContext) -> CheckResult:
        po = _po_currency(context)
        if not po:
            return _passed(self, "The PO doesn't set a currency.")

        printed = set(_CURRENCY_CODE.findall(context.invoice_text))
        reported = context.verification.invoice.currency
        if reported:
            printed.add(normalise(reported))
        others = sorted(printed - {po})
        if others:
            return _review(self, f"The invoice is in {', '.join(others)} but the PO is in {po}.")
        return _passed(self, "No currency conflict.")


def _po_currency(context: CheckContext) -> str:
    field = context.order.fields.get("currency")
    reported = context.verification.purchase_order.currency
    value = field if isinstance(field, str) else reported
    return normalise(value or "")


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
            return _review(self, f"{'; '.join(problems)}, so the text may be wrong.")
        return _passed(self, "The document was read cleanly.")


class ReportedDiscrepancyCheck:
    """Compares invoice lines with PO lines. Code confirms every line is on the
    PO, because the LLM can miss one. Beyond that, what the LLM reports can only
    make the outcome stricter: it can send an invoice to review, never approve one."""

    name = "reported_discrepancies"

    def run(self, context: CheckContext) -> CheckResult:
        # A PO with only a total has no lines to conflict with, so anything
        # reported against it is noise, and invoices split across a PO would
        # otherwise never pass.
        if not _is_itemised(context.order):
            return _passed(self, "The PO lists no line items to compare.")

        unknown = _lines_not_on_po(context)
        if unknown:
            return _review(self, f"Not on the PO: {', '.join(unknown)}.")

        source = _squeeze(context.invoice_text)
        found = [
            item
            for item in context.verification.discrepancies
            if _squeeze(item.evidence) in source and _is_real_conflict(item)
        ]
        if found:
            return _review(self, " ".join(item.description for item in found))
        return _passed(self, "The invoice lines agree with the PO lines.")


def _is_real_conflict(item: Discrepancy) -> bool:
    """The LLM names the two values and code does the comparing, so a claimed
    difference between two equal prices, or a partial quantity, is dropped."""
    if item.kind == "item_not_on_po":
        return True
    if item.invoice_value is None or item.po_value is None:
        return False
    if item.kind == "quantity_over_po":
        return item.invoice_value > item.po_value
    return _cents(item.invoice_value) != _cents(item.po_value)


def _lines_not_on_po(context: CheckContext) -> list[str]:
    po_lines = [
        _words(" ".join(str(value) for value in line.values()))
        for field in context.order.fields.values()
        if isinstance(field, list)
        for line in field
        if isinstance(line, dict)
    ]
    if not po_lines:
        return []

    def is_on_po(words: set[str]) -> bool:
        return any(len(words & line) * 2 >= len(words) for line in po_lines)

    return [
        item.description
        for item in context.verification.invoice.line_items
        if not is_on_po(_words(item.description))
    ]


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{3,}", text.lower())) - _LINE_NOISE


def _is_itemised(order: PurchaseOrder) -> bool:
    return any(isinstance(value, list) and value for value in order.fields.values())


def _squeeze(text: str) -> str:
    return "".join(text.split()).casefold()


def build_checks(tolerance: Tolerance) -> list[Check]:
    return [
        RequiredFieldsCheck(),
        ReadingAccuracyCheck(),
        ArithmeticCheck(),
        DuplicateCheck(),
        VendorCheck(),
        CurrencyCheck(),
        PoAmountCheck(tolerance),
        ExtractionQualityCheck(),
        ReportedDiscrepancyCheck(),
    ]
