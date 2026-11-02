import re
from dataclasses import dataclass

from app.domain.models import PurchaseOrder
from app.domain.runs import PoCandidate

_PREFIX = re.compile(r"^(?:PO|PURCHASEORDER|ORDER)(?=[A-Z0-9])")
_DIGIT_RUN = re.compile(r"\d{4,}")


@dataclass(frozen=True, slots=True)
class PoMatch:
    """A single `order` when the reference is clear, otherwise the `ambiguous`
    orders it could mean, which is empty when nothing matched."""

    order: PurchaseOrder | None
    ambiguous: list[PurchaseOrder]


def normalise(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _core(value: str) -> str:
    return _PREFIX.sub("", normalise(value))


def match_purchase_order(
    candidates: list[PoCandidate], orders: list[PurchaseOrder]
) -> PoMatch:
    """Exact matches win. Otherwise a long digit run may identify the PO, so
    that "88213/ACME" finds PO-88213, but only if it points at one order."""
    exact = _unique(
        order
        for candidate in candidates
        for order in orders
        if _core(candidate.value) == _core(order.po_number)
    )
    if exact:
        return _result(exact)

    # Every number in the reference must appear, because POs often share a year:
    # PUR/2026-27/0417 must not match every 2026 order.
    return _result(
        _unique(
            order
            for candidate in candidates
            for order in orders
            if _shares_numbers(candidate.value, order.po_number)
        )
    )


def _shares_numbers(reference: str, po_number: str) -> bool:
    numbers = set(_DIGIT_RUN.findall(reference))
    return bool(numbers) and numbers <= set(_DIGIT_RUN.findall(po_number))


def find_by_number(po_number: str, orders: list[PurchaseOrder]) -> PurchaseOrder | None:
    return next(
        (order for order in orders if _core(order.po_number) == _core(po_number)), None
    )


def _unique(orders) -> list[PurchaseOrder]:
    return list({order.id: order for order in orders}.values())


def _result(matches: list[PurchaseOrder]) -> PoMatch:
    if len(matches) == 1:
        return PoMatch(order=matches[0], ambiguous=[])
    return PoMatch(order=None, ambiguous=matches)
