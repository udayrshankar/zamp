"""Rules about history: has this invoice been seen before?"""

from app.domain.runs import Decision
from app.workflow.checks.base import CheckContext, CheckResult, passed, reject
from app.workflow.checks.vendor import company_words
from app.workflow.po_matcher import normalise


class DuplicateCheck:
    name = "duplicate"

    def run(self, context: CheckContext) -> CheckResult:
        invoice = context.verification.invoice
        number = normalise(invoice.invoice_number or "")
        for run in context.earlier_runs:
            if run.decision is Decision.REJECT:
                continue
            if run.sha256 == context.document.sha256:
                return reject(self, f"This exact file was already processed as {run.filename}.")
            earlier = run.verification.invoice if run.verification else None
            if earlier is None or not number or normalise(earlier.invoice_number or "") != number:
                continue
            same_vendor = company_words(earlier.vendor) == company_words(invoice.vendor)
            same_total = earlier.total is not None and earlier.total == invoice.total
            if same_vendor or same_total:
                return reject(
                    self,
                    f"Invoice {invoice.invoice_number} was already processed as {run.filename}.",
                )
        return passed(self, "No earlier invoice matches this one.")
