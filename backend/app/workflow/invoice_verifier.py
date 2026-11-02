import re

from app.domain.models import PurchaseOrder
from app.domain.ports import LlmClient
from app.domain.runs import VerificationOutput
from app.workflow.prompts import VERIFICATION_SYSTEM, wrap_untrusted

_TABLE_ROW = re.compile(r"^\s*\d+\s*\|", re.MULTILINE)


class InvoiceVerifier:
    """Has the LLM read both documents side by side."""

    def __init__(self, llm: LlmClient) -> None:
        self._llm = llm

    async def verify(self, invoice_text: str, order: PurchaseOrder) -> VerificationOutput:
        po_json = order.model_dump_json(include={"po_number", "fields"})
        documents = (
            wrap_untrusted("invoice", invoice_text)
            + "\n"
            + wrap_untrusted("purchase_order", po_json)
        )
        output = await self._ask(documents)

        # The LLM sometimes stops after the first row. Numbered table rows show
        # how many to expect, so it gets one more try with that count.
        rows = len(_TABLE_ROW.findall(invoice_text))
        if rows > len(output.invoice.line_items):
            reminder = f"\nThe item table has {rows} rows. Return all {rows} in line_items."
            second = await self._ask(documents + reminder)
            if len(second.invoice.line_items) > len(output.invoice.line_items):
                return second
        return output

    async def _ask(self, user: str) -> VerificationOutput:
        return await self._llm.complete_json(VERIFICATION_SYSTEM, user, VerificationOutput)
