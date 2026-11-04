"""Rules about individual invoice lines.

A wrong line can hide inside a total that still fits the PO, so every line is
checked on its own: its arithmetic, which PO line it is, and whether it bills
more, or at a higher price, than that PO line allows. All of it is computed
here; what the LLM says about discrepancies is never trusted to decide.

Quantities and prices are compared in the PO line's unit of measure, so 2,000
kg billed against 2 tonnes ordered is the same amount.
"""

import re
from dataclasses import dataclass

from app.domain.runs import Decision, LineItem, Run
from app.workflow import units
from app.workflow.checks.base import (
    CheckContext,
    CheckResult,
    cents,
    is_itemised,
    passed,
    review,
)

# Words that describe billing rather than the item, so they don't count when
# comparing an invoice line with a PO line.
_FILLER = {
    "and",
    "for",
    "the",
    "with",
    "per",
    "set",
    "pack",
    "box",
    "item",
    "unit",
    "nos",
    "month",
    "months",
    "monthly",
    "day",
    "days",
    "service",
    "charges",
    "inclusive",
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
    "january",
    "february",
    "march",
    "april",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "contd",
} | units.UNIT_WORDS
# Words that announce a different product standing in for the one ordered.
_SUBSTITUTES = {
    "equivalent",
    "substitute",
    "alternative",
    "alternate",
    "compatible",
    "replacement",
    "similar",
}
_QUANTITY_KEYS = ("qty", "quantity", "qnty", "units")
_PRICE_KEYS = ("unit_price", "unit_rate", "price", "rate")
_DESCRIPTION_KEYS = ("description", "item", "name", "product", "particulars")
_UNIT_KEYS = ("unit", "uom", "unit_of_measure", "units_of_measure", "measure", "units")
# The share of a PO line's words an invoice line must repeat to be the same item.
_COVERAGE = 0.6
# Rounding allowed between quantity x rate and the printed amount.
_LINE_TOLERANCE_CENTS = 100
_PRICE_TOLERANCE = 0.005


@dataclass(frozen=True, slots=True)
class PoLine:
    description: str
    quantity: float | None
    unit_price: float | None
    unit: units.Unit | None = None


@dataclass(frozen=True, slots=True)
class _InPoUnits:
    """An invoice line's quantity and net unit price, in its PO line's unit."""

    quantity: float | None
    price: float | None


class LineArithmeticCheck:
    """Lines adding up to the subtotal isn't enough: a wrong line amount is
    carried straight into it."""

    name = "line_arithmetic"

    def run(self, context: CheckContext) -> CheckResult:
        lines = context.verification.invoice.line_items
        wrong = [line for line in lines if is_miscalculated(line)]
        if wrong:
            details = "; ".join(
                f"{line.description}: {line.quantity:g} × {line.unit_price:,.2f} "
                f"is not {line.amount:,.2f}"
                for line in wrong
            )
            return review(self, f"A line's amount is wrong. {details}.")
        return passed(self, "Every line's amount is its quantity times its rate.")


class PoLineCheck:
    """Each invoice line must be a PO line, within the quantity still open on
    it and at no more than the PO's price."""

    name = "po_lines"

    def run(self, context: CheckContext) -> CheckResult:
        if not is_itemised(context.order):
            return passed(self, "The PO lists no line items to compare.")

        po_lines = po_lines_of(context.order.fields)
        problems: list[str] = []
        billed: dict[int, float] = _earlier_quantities(context, po_lines)
        for line in context.verification.invoice.line_items:
            index = match_line(line.description, po_lines)
            if index is None:
                problems.append(f"Not on the PO: {line.description}.")
                continue
            po_line = po_lines[index]
            converted = in_po_units(line, po_line)
            if isinstance(converted, str):
                problems.append(converted)
                continue
            if converted.quantity is not None:
                billed[index] = billed.get(index, 0) + converted.quantity
            if (
                converted.price is not None
                and po_line.unit_price
                and converted.price > po_line.unit_price * (1 + _PRICE_TOLERANCE)
            ):
                per = po_line.unit.label if po_line.unit else "unit"
                problems.append(
                    f"{line.description} is billed at {converted.price:,.2f} a {per}; "
                    f"the PO price is {po_line.unit_price:,.2f}."
                )

        for index, quantity in billed.items():
            po_line = po_lines[index]
            if po_line.quantity is not None and quantity > po_line.quantity + 1e-9:
                unit = f" {po_line.unit.label}" if po_line.unit else ""
                problems.append(
                    f"{po_line.description}: {quantity:g}{unit} billed in total, "
                    f"but the PO orders {po_line.quantity:g}{unit}."
                )

        if problems:
            return review(self, " ".join(problems))
        return passed(self, "Every line is on the PO, within the quantity and price ordered.")


def in_po_units(line: LineItem, po_line: PoLine) -> _InPoUnits | str:
    """The line's quantity and price in the PO line's unit, or why they can't be
    compared. A line or PO line that names no unit is taken to use the other's."""
    quantity, price = line.quantity, _net_unit_price(line)
    billed_in = units.parse(line.unit) or units.in_text(line.description)
    ordered_in = po_line.unit
    if billed_in is None or ordered_in is None:
        return _InPoUnits(quantity, price)
    factor = units.ratio(billed_in, ordered_in)
    if factor is None:
        return (
            f"{line.description} is billed in {billed_in.label}, but the PO orders it in "
            f"{ordered_in.label}, which doesn't convert."
        )
    return _InPoUnits(
        None if quantity is None else quantity * factor,
        None if price is None else price / factor,
    )


def po_lines_of(fields: dict) -> list[PoLine]:
    """Reads the line items of a free-form PO, whatever its keys are called."""
    rows = next((value for value in fields.values() if isinstance(value, list) and value), [])
    return [
        PoLine(
            description=_first_text(row),
            quantity=_first_number(row, _QUANTITY_KEYS),
            unit_price=_first_number(row, _PRICE_KEYS),
            unit=_first_unit(row),
        )
        for row in rows
        if isinstance(row, dict)
    ]


def match_line(description: str, po_lines: list[PoLine]) -> int | None:
    """The PO line this invoice line bills for, or None if it isn't on the PO."""
    words = _words(description)
    if words & _SUBSTITUTES:
        return None
    scored = [
        (_coverage(words, _words(po_line.description)), index)
        for index, po_line in enumerate(po_lines)
        if _same_specification(words, _words(po_line.description))
    ]
    best = max(scored, default=(0.0, None))
    return best[1] if best[0] >= _COVERAGE else None


def _earlier_quantities(context: CheckContext, po_lines: list[PoLine]) -> dict[int, float]:
    """Quantities already billed on this PO by invoices that weren't rejected."""
    billed: dict[int, float] = {}
    for run in context.earlier_runs:
        if not _counts_towards(run, context):
            continue
        for line in run.verification.invoice.line_items:
            index = match_line(line.description, po_lines)
            if index is None:
                continue
            converted = in_po_units(line, po_lines[index])
            if not isinstance(converted, str) and converted.quantity is not None:
                billed[index] = billed.get(index, 0) + converted.quantity
    return billed


def _counts_towards(run: Run, context: CheckContext) -> bool:
    return (
        run.decision is not Decision.REJECT
        and run.purchase_order_id == context.order.id
        and run.verification is not None
    )


def is_miscalculated(line: LineItem) -> bool:
    if line.quantity is None or line.unit_price is None or line.amount is None:
        return False
    gross = line.quantity * line.unit_price
    net = gross * (1 - (line.discount_percent or 0) / 100)
    allowed = max(_LINE_TOLERANCE_CENTS, abs(cents(line.amount)) // 2000)
    return all(abs(cents(expected) - cents(line.amount)) > allowed for expected in (gross, net))


def _net_unit_price(line: LineItem) -> float | None:
    if line.amount is not None and line.quantity:
        return line.amount / line.quantity
    if line.unit_price is not None:
        return line.unit_price * (1 - (line.discount_percent or 0) / 100)
    return None


def _words(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+(?:[x./-][a-z0-9]+)*", text.lower())
    return {
        token
        for token in tokens
        if token not in _FILLER and (len(token) >= 3 or any(char.isdigit() for char in token))
    }


def _coverage(invoice_words: set[str], po_words: set[str]) -> float:
    if not po_words:
        return 0.0
    return sum(any(_same_word(word, other) for other in invoice_words) for word in po_words) / len(
        po_words
    )


def _same_specification(invoice_words: set[str], po_words: set[str]) -> bool:
    """Every number-bearing word on the PO line (sizes, models, "4g") must be
    on the invoice line, allowing for a description cut short."""
    specs = {word for word in po_words if any(char.isdigit() for char in word)}
    return all(any(_same_word(spec, word) for word in invoice_words) for spec in specs)


def _same_word(a: str, b: str) -> bool:
    """Equal, or one is the other cut short (at least 4 characters kept)."""
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    return len(shorter) >= 4 and longer.startswith(shorter)


def _first_text(row: dict) -> str:
    for key in _DESCRIPTION_KEYS:
        for name, value in row.items():
            if key in name.lower() and isinstance(value, str):
                return value
    return next((value for value in row.values() if isinstance(value, str)), "")


def _first_number(row: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = row.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return None


def _first_unit(row: dict) -> units.Unit | None:
    """The PO line's unit: a text field such as "unit" or "uom", or else one the
    description names, like "Copper cable (metre)"."""
    for key in _UNIT_KEYS:
        for name, value in row.items():
            if name.strip().casefold() == key and isinstance(value, str):
                return units.parse(value)
    return units.in_text(_first_text(row))
