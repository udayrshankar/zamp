import re

from app.domain.errors import ExtractionError
from app.domain.models import PageMethod, PageResult, RoutingReason, TextLine
from app.domain.ports import PageExtractor, PdfPage

_AMOUNT = re.compile(r"\d[\d,]*\.\d{2}")
_TOTAL_WORD = "total"


class GapFillingExtractor:
    """Recovers amounts a parsing model skipped.

    Nemotron Parse can silently drop a whole block, and on invoices that has
    been the totals beneath a table. It reports success when this happens, so a
    page with no "total" gets a second read. Only lines holding amounts the
    first read missed are added, which keeps its table structure and order.
    """

    def __init__(self, primary: PageExtractor, backup: PageExtractor) -> None:
        self._primary = primary
        self._backup = backup

    def extract(self, page: PdfPage, reason: RoutingReason) -> PageResult:
        result = self._primary.extract(page, reason)
        if result.method is not PageMethod.PARSE or _TOTAL_WORD in result.text.casefold():
            return result

        try:
            second_read = self._backup.extract(page, reason)
        except ExtractionError:
            return result

        missing = _lines_with_new_amounts(result.text, second_read.lines)
        if not missing:
            return result
        return result.model_copy(
            update={
                "text": "\n".join([result.text, *(line.text for line in missing)]),
                "lines": [*result.lines, *missing],
                "gap_filled": True,
            }
        )


def _lines_with_new_amounts(text: str, lines: list[TextLine]) -> list[TextLine]:
    known = set(_AMOUNT.findall(text))
    return [line for line in lines if set(_AMOUNT.findall(line.text)) - known]
