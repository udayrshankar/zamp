from app.domain.models import PageMethod, PageResult, RoutingReason
from app.domain.ports import PdfPage
from app.extraction.line_grouping import group_into_lines


class NativeTextExtractor:
    """Reads the text layer embedded in the PDF."""

    def extract(self, page: PdfPage, reason: RoutingReason) -> PageResult:
        lines = group_into_lines(page.fragments())
        return PageResult(
            number=page.number,
            method=PageMethod.NATIVE,
            routing_reason=reason,
            text="\n".join(line.text for line in lines),
            lines=lines,
        )
