"""Picks the best of several models' readings of the same invoice.

"Best" is decided by evidence, then by agreement: a reading the document itself
supports (its total is printed, its arithmetic closes, its invoice number is on
the page) beats one that only has more models behind it. Ties go to the model
listed first.
"""

from collections import Counter
from dataclasses import dataclass

from app.domain.llm import ModelAnswer
from app.domain.runs import InvoiceFacts, VerificationOutput
from app.workflow.checks.base import NUMBER, cents, squeeze
from app.workflow.checks.lines import is_miscalculated
from app.workflow.facts import normalise_verification
from app.workflow.po_matcher import normalise

# Rounding allowed when checking that a reading's arithmetic closes.
_ROUNDING_CENTS = 100


@dataclass(frozen=True, slots=True)
class Reading:
    model: str
    output: VerificationOutput


@dataclass(frozen=True, slots=True)
class Consensus:
    chosen: Reading
    readings: list[Reading]
    # False when the readings disagree on the total and the document can't
    # tell which one is right.
    readings_agree: bool


def choose(
    answers: list[ModelAnswer[VerificationOutput]], invoice_text: str, po_number: str
) -> Consensus | None:
    readings = [
        Reading(answer.model, normalise_verification(answer.output, po_number))
        for answer in answers
        if answer.answered
    ]
    if not readings:
        return None

    printed = _printed_amounts(invoice_text)
    source = squeeze(invoice_text)
    ranked = sorted(
        enumerate(readings),
        key=lambda item: (
            -evidence(item[1].output.invoice, printed, source),
            -agreement(item[1].output.invoice, [other.output.invoice for other in readings]),
            item[0],
        ),
    )
    return Consensus(
        chosen=ranked[0][1],
        readings=readings,
        readings_agree=_totals_settled(readings, printed),
    )


def evidence(facts: InvoiceFacts, printed: set[int], source: str) -> int:
    """How many of the reading's key claims the document confirms."""
    return sum(
        (
            facts.total is not None and cents(facts.total) in printed,
            _closes(facts),
            _lines_add_up(facts),
            # A misread rate shows up as a line that contradicts itself.
            not any(is_miscalculated(line) for line in facts.line_items),
            facts.invoice_number is not None and squeeze(facts.invoice_number) in source,
        )
    )


def agreement(facts: InvoiceFacts, everyone: list[InvoiceFacts]) -> int:
    """How many field values this reading shares with the other readings."""
    mine = _key_values(facts)
    return sum(
        mine[field] == theirs[field]
        for other in everyone
        if other is not facts
        for theirs in (_key_values(other),)
        for field in mine
    )


def _totals_settled(readings: list[Reading], printed: set[int]) -> bool:
    totals = [reading.output.invoice.total for reading in readings]
    if len(readings) == 1 or Counter(totals).most_common(1)[0][1] >= 2:
        return True
    supported = {total for total in totals if total is not None and cents(total) in printed}
    return len(supported) == 1


def _key_values(facts: InvoiceFacts) -> dict[str, object]:
    return {
        "invoice_number": normalise(facts.invoice_number or ""),
        "invoice_date": facts.invoice_date,
        "currency": (facts.currency or "").upper(),
        "total": facts.total,
        "subtotal": facts.subtotal,
        "tax": facts.tax,
        "lines": len(facts.line_items),
    }


def _closes(facts: InvoiceFacts) -> bool:
    if facts.subtotal is None or facts.total is None:
        return False
    added = (
        cents(facts.subtotal) + cents(facts.tax or 0) + sum(cents(c.amount) for c in facts.charges)
    )
    return abs(added - cents(facts.total)) <= _ROUNDING_CENTS


def _lines_add_up(facts: InvoiceFacts) -> bool:
    amounts = [line.amount for line in facts.line_items]
    if not amounts or None in amounts or facts.subtotal is None:
        return False
    return abs(sum(cents(amount) for amount in amounts) - cents(facts.subtotal)) <= _ROUNDING_CENTS


def _printed_amounts(text: str) -> set[int]:
    return {cents(float(number.replace(",", ""))) for number in NUMBER.findall(text)}
