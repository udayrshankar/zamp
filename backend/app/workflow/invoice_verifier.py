import re

from app.domain.llm import ModelAnswer
from app.domain.models import PurchaseOrder
from app.domain.ports import LlmPanel
from app.domain.runs import VerificationOutput
from app.workflow.prompts import VERIFICATION_SYSTEM, wrap_untrusted

_TABLE_ROW = re.compile(r"^\s*\d+\s*\|", re.MULTILINE)

Answers = list[ModelAnswer[VerificationOutput]]


class InvoiceVerifier:
    """Has a panel of models read both documents side by side."""

    def __init__(self, panel: LlmPanel) -> None:
        self._panel = panel

    async def verify(self, invoice_text: str, order: PurchaseOrder) -> Answers:
        po_json = order.model_dump_json(include={"po_number", "fields"})
        documents = (
            wrap_untrusted("invoice", invoice_text)
            + "\n"
            + wrap_untrusted("purchase_order", po_json)
        )
        answers = await self._ask(documents)

        # Models sometimes stop after the first row. Numbered table rows show
        # how many to expect, so short answers get one more try with that count.
        rows = len(_TABLE_ROW.findall(invoice_text))
        if any(_lines(answer) < rows for answer in answers if answer.answered):
            reminder = f"\nThe item table has {rows} rows. Return all {rows} in line_items."
            answers = _fuller(answers, await self._ask(documents + reminder))
        return answers

    async def _ask(self, user: str) -> Answers:
        return await self._panel.ask_all(VERIFICATION_SYSTEM, user, VerificationOutput)


def _lines(answer: ModelAnswer[VerificationOutput]) -> int:
    return len(answer.output.invoice.line_items) if answer.answered else -1


def _fuller(first: Answers, second: Answers) -> Answers:
    """Per model, the answer that read more line items."""
    best = {answer.model: answer for answer in first}
    for answer in second:
        if answer.model not in best or _lines(answer) > _lines(best[answer.model]):
            best[answer.model] = answer
    return list(best.values())
