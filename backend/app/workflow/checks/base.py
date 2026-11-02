"""What every rule shares: its input, its result, and small helpers for both."""

import re
from dataclasses import dataclass
from typing import Protocol

from app.domain.models import Document, PurchaseOrder
from app.domain.runs import CheckOutcome, CheckResult, Run, VerificationOutput

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


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
    # False when the models read the invoice differently and code couldn't tell
    # which reading is right.
    readings_agree: bool = True


class Check(Protocol):
    name: str

    def run(self, context: CheckContext) -> CheckResult: ...


def passed(check: Check, message: str) -> CheckResult:
    return CheckResult(name=check.name, outcome=CheckOutcome.PASS, message=message)


def review(check: Check, message: str) -> CheckResult:
    return CheckResult(name=check.name, outcome=CheckOutcome.REVIEW, message=message)


def reject(check: Check, message: str) -> CheckResult:
    return CheckResult(name=check.name, outcome=CheckOutcome.REJECT, message=message)


def cents(amount: float) -> int:
    return round(amount * 100)


def money(cents_value: int) -> str:
    return f"{cents_value / 100:,.2f}"


def squeeze(text: str) -> str:
    return "".join(text.split()).casefold()


def is_itemised(order: PurchaseOrder) -> bool:
    return any(isinstance(value, list) and value for value in order.fields.values())
