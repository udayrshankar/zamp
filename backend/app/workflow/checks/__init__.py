"""The rules that decide an invoice. Each one is small and independent, so a new
rule is a new class added to `build_checks`.

These are code rather than LLM judgement because they have to be right, and
repeatable, every time. The LLM reads the documents; these confirm what it read.
"""

from app.workflow.checks.amounts import ArithmeticCheck, CurrencyCheck, PoAmountCheck, TaxRateCheck
from app.workflow.checks.base import Check, CheckContext, Tolerance
from app.workflow.checks.documents import (
    ExtractionQualityCheck,
    ReadingAccuracyCheck,
    ReadingAgreementCheck,
    RequiredFieldsCheck,
)
from app.workflow.checks.duplicates import DuplicateCheck
from app.workflow.checks.fraud import BankDetailsCheck, InvoiceDateCheck
from app.workflow.checks.lines import LineArithmeticCheck, PoLineCheck
from app.workflow.checks.vendor import VendorCheck

__all__ = [
    "ArithmeticCheck",
    "BankDetailsCheck",
    "Check",
    "CheckContext",
    "CurrencyCheck",
    "DuplicateCheck",
    "ExtractionQualityCheck",
    "InvoiceDateCheck",
    "LineArithmeticCheck",
    "PoAmountCheck",
    "PoLineCheck",
    "ReadingAccuracyCheck",
    "ReadingAgreementCheck",
    "RequiredFieldsCheck",
    "TaxRateCheck",
    "Tolerance",
    "VendorCheck",
    "build_checks",
]


def build_checks(tolerance: Tolerance) -> list[Check]:
    return [
        RequiredFieldsCheck(),
        ReadingAccuracyCheck(),
        ReadingAgreementCheck(),
        ArithmeticCheck(),
        LineArithmeticCheck(),
        TaxRateCheck(),
        DuplicateCheck(),
        VendorCheck(),
        CurrencyCheck(),
        PoAmountCheck(tolerance),
        PoLineCheck(),
        InvoiceDateCheck(),
        BankDetailsCheck(),
        ExtractionQualityCheck(),
    ]
