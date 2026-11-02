from dataclasses import dataclass

from app.domain.errors import PageReadError
from app.domain.models import PageMethod, PageResult, RoutingReason, TextLine
from app.extraction.gap_filling_extractor import GapFillingExtractor
from tests.fakes import FakePage

REASON = RoutingReason.NO_TEXT_LAYER


def line(text: str) -> TextLine:
    return TextLine(text=text, bbox=(0, 0, 1, 1))


def parsed(*texts: str, method: PageMethod = PageMethod.PARSE) -> PageResult:
    lines = [line(text) for text in texts]
    return PageResult(
        number=1,
        method=method,
        routing_reason=REASON,
        text="\n".join(texts),
        lines=lines,
    )


@dataclass
class Stub:
    result: PageResult | None = None
    error: Exception | None = None
    calls: int = 0

    def extract(self, page, reason) -> PageResult:
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


TABLE_ROW = "1 | Workstation | 6 | 1,48,000.00 | 8,88,000.00"
OCR_RESULT = parsed(
    "1 Workstation 6 1,48,000.00 8,88,000.00",
    "Taxable Value 8,88,000.00",
    "CGST @ 9% 79,920.00",
    "Total Amount (INR) 10,47,840.00",
    method=PageMethod.OCR,
)


def run(primary: PageResult, backup: Stub) -> PageResult:
    return GapFillingExtractor(Stub(primary), backup).extract(FakePage(), REASON)


def test_a_page_with_a_total_is_not_read_twice():
    backup = Stub(OCR_RESULT)

    result = run(parsed("Total Amount 10.00"), backup)

    assert backup.calls == 0
    assert result.gap_filled is False


def test_only_pages_read_by_parse_are_rechecked():
    backup = Stub(OCR_RESULT)

    run(parsed("No totals here", method=PageMethod.OCR), backup)

    assert backup.calls == 0


def test_adds_only_lines_with_amounts_the_first_read_missed():
    result = run(parsed(TABLE_ROW), Stub(OCR_RESULT))

    assert result.gap_filled is True
    assert result.method is PageMethod.PARSE
    assert result.text.splitlines() == [
        TABLE_ROW,
        "CGST @ 9% 79,920.00",
        "Total Amount (INR) 10,47,840.00",
    ]
    assert len(result.lines) == 3


def test_nothing_new_leaves_the_page_alone():
    result = run(parsed(TABLE_ROW), Stub(parsed(TABLE_ROW, method=PageMethod.OCR)))

    assert result.gap_filled is False
    assert result.text == TABLE_ROW


def test_a_failed_second_read_keeps_the_first():
    result = run(parsed(TABLE_ROW), Stub(error=PageReadError("ocr failed")))

    assert result.text == TABLE_ROW
    assert result.gap_filled is False
