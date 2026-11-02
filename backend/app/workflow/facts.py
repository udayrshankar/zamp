"""Puts what the LLM read into one consistent shape before any rule looks at it.

Models report the same invoice in different ways: GST as `tax`, as charges, or
half in each. Rules written against one consistent shape stay simple, and every
model's reading can be judged by the same rules.
"""

import re

from app.domain.runs import Charge, InvoiceFacts, VerificationOutput
from app.workflow.po_matcher import normalise

_TAX_LABEL = re.compile(r"\b(?:[CSIU]GST|GST|VAT|CESS)\b", re.IGNORECASE)


def normalise_verification(output: VerificationOutput, po_number: str) -> VerificationOutput:
    return output.model_copy(update={"invoice": normalise_invoice(output.invoice, po_number)})


def normalise_invoice(facts: InvoiceFacts, po_number: str) -> InvoiceFacts:
    tax, charges = _combine_tax(facts.tax, facts.charges)
    return facts.model_copy(
        update={
            "tax": tax,
            "charges": charges,
            "invoice_number": _real_invoice_number(facts.invoice_number, po_number),
        }
    )


def _combine_tax(tax: float | None, charges: list[Charge]) -> tuple[float | None, list[Charge]]:
    """All GST parts become one `tax` figure, counted once."""
    tax_charges = [charge for charge in charges if _TAX_LABEL.search(charge.label)]
    if not tax_charges:
        return tax, charges

    others = [charge for charge in charges if charge not in tax_charges]
    parts = round(sum(charge.amount for charge in tax_charges), 2)
    if tax is None or _repeats(tax, tax_charges, parts):
        return parts, others
    return round(tax + parts, 2), others


def _repeats(tax: float, tax_charges: list[Charge], parts: float) -> bool:
    """Whether `tax` is a copy of what the charges already hold, rather than a
    part they are missing. With only one half of a CGST/SGST pair among the
    charges, `tax` is the other half, even when the two amounts are equal."""
    halves = {_half(charge.label) for charge in tax_charges} - {None}
    if len(halves) == 1:
        return _same(tax, parts) and len(tax_charges) > 1
    return any(_same(tax, amount) for amount in (parts, *(c.amount for c in tax_charges)))


def _half(label: str) -> str | None:
    """Which half of an intra-state GST pair a label names, if any."""
    match = re.search(r"\b([CSU])GST\b", label, re.IGNORECASE)
    if match is None:
        return None
    return "central" if match.group(1).upper() == "C" else "state"


def _real_invoice_number(number: str | None, po_number: str) -> str | None:
    """A model with nothing better sometimes offers the PO number instead."""
    if number is not None and normalise(number) == normalise(po_number):
        return None
    return number


def _same(a: float, b: float) -> bool:
    return abs(a - b) < 0.01
