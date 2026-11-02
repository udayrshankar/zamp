from app.domain.ports import LlmClient
from app.domain.runs import PoCandidate, PoDetectionOutput
from app.workflow.prompts import PO_DETECTION_SYSTEM, wrap_untrusted


class PoDetector:
    """Asks the LLM for PO references, keeping only those it can back up."""

    def __init__(self, llm: LlmClient) -> None:
        self._llm = llm

    async def detect(self, invoice_text: str) -> list[PoCandidate]:
        output = await self._llm.complete_json(
            PO_DETECTION_SYSTEM,
            wrap_untrusted("invoice", invoice_text),
            PoDetectionOutput,
        )
        source = _squeeze(invoice_text)
        return [
            candidate
            for candidate in output.candidates
            if _squeeze(candidate.value) in source and _squeeze(candidate.evidence) in source
        ]


def _squeeze(text: str) -> str:
    return "".join(text.split()).casefold()
