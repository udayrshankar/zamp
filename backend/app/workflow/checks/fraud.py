"""Rules for common invoice-fraud signals that a careful clerk would stop for."""

import re
from datetime import date, datetime

from app.workflow.checks.base import CheckContext, CheckResult, passed, review

_DATE_FORMATS = (
    "%d %b %Y",
    "%d %B %Y",
    "%d-%b-%Y",
    "%d %b, %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d.%m.%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
)
_NEW_BANK_DETAILS = re.compile(
    r"bank (?:details|account)[^.]{0,30}(?:changed|updated)"
    r"|(?:remit|pay|transfer)[^.]{0,20}\bnew\b[^.]{0,15}(?:account|a/c|bank)"
    r"|\bnew (?:bank )?(?:account|a/c) (?:details|number|no)",
    re.IGNORECASE,
)


class InvoiceDateCheck:
    name = "invoice_date"

    def run(self, context: CheckContext) -> CheckResult:
        invoiced = parse_date(context.verification.invoice.invoice_date)
        ordered = parse_date(_po_date(context.order.fields))
        if invoiced is None or ordered is None:
            return passed(
                self, "The invoice and PO dates could not both be read, so they weren't compared."
            )
        if invoiced < ordered:
            return review(
                self,
                f"The invoice is dated {invoiced:%d %b %Y}, "
                f"before the PO was raised on {ordered:%d %b %Y}.",
            )
        return passed(self, "The invoice is dated on or after the PO.")


class BankDetailsCheck:
    name = "bank_details"

    def run(self, context: CheckContext) -> CheckResult:
        notice = _NEW_BANK_DETAILS.search(context.invoice_text)
        if notice:
            return review(
                self,
                f'The invoice asks for payment to new bank details ("{notice.group(0)}"). '
                "Confirm them with the vendor before paying.",
            )
        return passed(self, "No change of bank details is mentioned.")


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", value.strip())
    for pattern in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, pattern).date()
        except ValueError:
            continue
    return None


def _po_date(fields: dict) -> str | None:
    """The PO's own date: a field named like "po_date" or "order_date"."""
    for name, value in fields.items():
        lowered = name.lower()
        if "date" in lowered and ("po" in lowered or "order" in lowered) and isinstance(value, str):
            return value
    return None
