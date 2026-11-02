from app.domain.models import PageMethod, PageResult, RoutingReason, TextLine
from app.domain.ports import OcrEngine, PdfPage
from app.extraction.line_grouping import group_into_lines, weighted_confidence


class OcrTextExtractor:
    """Renders a page to an image and reads it with an OCR engine."""

    def __init__(self, engine: OcrEngine, dpi: int) -> None:
        self._engine = engine
        self._dpi = dpi

    def extract(self, page: PdfPage, reason: RoutingReason) -> PageResult:
        image = page.render(self._dpi)
        fragments = self._engine.recognize(image)
        lines = group_into_lines(
            to_points(fragment, image.pixels_per_point) for fragment in fragments
        )
        return PageResult(
            number=page.number,
            method=PageMethod.OCR if lines else PageMethod.BLANK,
            routing_reason=reason,
            text="\n".join(line.text for line in lines),
            confidence=weighted_confidence(lines),
            lines=lines,
        )


def to_points(fragment: TextLine, pixels_per_point: float) -> TextLine:
    """Moves OCR boxes into PDF points, the same space native text uses."""
    x0, y0, x1, y1 = fragment.bbox
    return fragment.model_copy(
        update={
            "bbox": (
                x0 / pixels_per_point,
                y0 / pixels_per_point,
                x1 / pixels_per_point,
                y1 / pixels_per_point,
            )
        }
    )
