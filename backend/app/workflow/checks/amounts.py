"""Rules about money: the invoice's own arithmetic, the PO's limit, currency and tax."""

import re

from app.domain.runs import Decision
from app.workflow.checks.base import (
    CheckContext,
    CheckResult,
    Tolerance,
    cents,
    money,
    passed,
    reject,
    review,
)
from app.workflow.po_matcher import normalise

_CURRENCY_CODE = re.compile(r"\b(INR|USD|EUR|GBP|AED|SGD|JPY|CNY|AUD|CAD|CHF)\b")


class ArithmeticCheck:
    name = "arithmetic"

    def run(self, context: CheckContext) -> CheckResult:
        invoice = context.verification.invoice
        amounts = [item.amount for item in invoice.line_items]
        added = sum(cents(charge.amount) for charge in invoice.charges) + cents(invoice.tax or 0)

        if amounts and None not in amounts:
            line_sum = sum(cents(amount) for amount in amounts)
            allowance = len(amounts)
            if invoice.subtotal is not None:
                if abs(line_sum - cents(invoice.subtotal)) > allowance:
                    return review(
                        self,
                        f"Line items add up to {money(line_sum)}, "
                        f"but the subtotal says {invoice.subtotal:,.2f}.",
                    )
            elif invoice.total is not None and abs(line_sum + added - cents(invoice.total)) > allowance:
                return review(
                    self,
                    f"Line items and charges add up to {money(line_sum + added)}, "
                    f"but the total says {invoice.total:,.2f}.",
                )

        if invoice.subtotal is not None and invoice.total is not None:
            expected = cents(invoice.subtotal) + added
            if abs(expected - cents(invoice.total)) > 1:
                return review(
                    self,
                    f"Subtotal, tax and charges add up to {money(expected)}, "
                    f"but the total says {invoice.total:,.2f}.",
                )
        return passed(self, "The invoice arithmetic adds up.")


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
            return review(self, "The invoice has no total to compare with the PO.")
        if po_total is None:
            return review(self, "The PO has no total to compare with the invoice.")

        earlier = sum(
            cents(run.verification.invoice.total)
            for run in context.earlier_runs
            if run.decision is not Decision.REJECT
            and run.purchase_order_id == context.order.id
            and run.verification is not None
            and run.verification.invoice.total is not None
        )
        limit = cents(po_total)
        billed = earlier + cents(invoice_total)
        over = billed - limit
        billed_text = (
            f"{money(billed)} billed in total, including {money(earlier)} earlier"
            if earlier
            else f"Invoice total {money(billed)}"
        )
        comparison = f"{billed_text}, against a PO of {money(limit)}"

        # Whole cents, so that exactly 2% or 10% lands on the right side.
        if over * 100 > self._tolerance.reject_percent * limit:
            return reject(self, f"{comparison}: over by more than {self._tolerance.reject_percent:g}%.")
        if over * 100 > self._tolerance.accept_percent * limit:
            return review(self, f"{comparison}: over by more than {self._tolerance.accept_percent:g}%.")
        if over < 0:
            return passed(self, f"{comparison}: {money(-over)} still open on the PO.")
        return passed(self, f"{comparison}: within tolerance.")


class CurrencyCheck:
    """Reads the invoice text as well as the LLM's answer, because a missed
    currency would otherwise look like there was nothing to compare."""

    name = "currency"

    def run(self, context: CheckContext) -> CheckResult:
        po = _po_currency(context)
        if not po:
            return passed(self, "The PO doesn't set a currency.")

        printed = set(_CURRENCY_CODE.findall(context.invoice_text))
        reported = context.verification.invoice.currency
        if reported:
            printed.add(normalise(reported))
        others = sorted(printed - {po})
        if others:
            return review(self, f"The invoice is in {', '.join(others)} but the PO is in {po}.")
        return passed(self, "No currency conflict.")


def _po_currency(context: CheckContext) -> str:
    field = context.order.fields.get("currency")
    reported = context.verification.purchase_order.currency
    value = field if isinstance(field, str) else reported
    return normalise(value or "")


_TAX_RATE = re.compile(
    r"\b([CSIU]?GST|VAT)\b[^%\n]{0,12}?(\d{1,2}(?:\.\d{1,2})?)\s*%", re.IGNORECASE
)


class TaxRateCheck:
    """The tax charged must be the printed rate applied to the taxable value.
    A wrong rate can hide inside the tolerance on the total."""

    name = "tax_rate"

    def run(self, context: CheckContext) -> CheckResult:
        invoice = context.verification.invoice
        rate = printed_tax_rate(context.invoice_text)
        if rate is None or invoice.subtotal is None or invoice.tax is None:
            return passed(self, "No single tax rate is printed, so the tax wasn't recomputed.")

        expected = invoice.subtotal * rate / 100
        allowed = max(100, abs(cents(expected)) // 200)
        if abs(cents(invoice.tax) - cents(expected)) > allowed:
            return review(
                self,
                f"Tax at the printed {rate:g}% of {invoice.subtotal:,.2f} is {expected:,.2f}, "
                f"but the invoice charges {invoice.tax:,.2f}.",
            )
        return passed(self, f"The tax matches the printed {rate:g}% rate.")


def printed_tax_rate(text: str) -> float | None:
    """The total GST rate printed on the invoice: IGST, or CGST plus SGST, or a
    plain GST rate. None when no rate, or more than one rate per kind, is printed."""
    rates: dict[str, set[float]] = {}
    for kind, value in _TAX_RATE.findall(text):
        rates.setdefault(kind.upper(), set()).add(float(value))
    if any(len(values) > 1 for values in rates.values()):
        return None

    def single(kind: str) -> float | None:
        return next(iter(rates[kind])) if kind in rates else None

    if (igst := single("IGST")) is not None:
        return igst
    cgst, sgst = single("CGST"), single("SGST") or single("UGST")
    if cgst is not None and sgst is not None:
        return cgst + sgst
    return single("GST") or single("VAT")
