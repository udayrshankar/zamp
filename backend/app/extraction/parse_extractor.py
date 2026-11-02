from app.domain.errors import NothingToParseError
from app.domain.models import PageMethod, PageResult, RoutingReason
from app.domain.ports import PageParser, PdfPage
from app.extraction.ink import ink_ratio
from app.extraction.ocr_extractor import to_points


class ParseTextExtractor:
    """Reads a page with a document parsing model."""

    def __init__(
        self,
        parser: PageParser,
        max_width: int,
        max_height: int,
        min_ink_ratio: float,
    ) -> None:
        self._parser = parser
        self._max_width = max_width
        self._max_height = max_height
        self._min_ink_ratio = min_ink_ratio

    def extract(self, page: PdfPage, reason: RoutingReason) -> PageResult:
        image = page.render_to_fit(self._max_width, self._max_height)
        # Given a near-empty page the model invents plausible text, with no
        # confidence score to give it away. On an invoice that is the worst
        # possible failure, so these pages never reach it.
        if ink_ratio(image) < self._min_ink_ratio:
            raise NothingToParseError("The page has too little content to parse safely.")

        # The model already returns reading order, which holds up on rotated
        # and multi-column pages where sorting by position would not.
        lines = [
            to_points(line, image.pixels_per_point) for line in self._parser.parse(image)
        ]
        return PageResult(
            number=page.number,
            method=PageMethod.PARSE if lines else PageMethod.BLANK,
            routing_reason=reason,
            text="\n".join(line.text for line in lines),
            lines=lines,
        )
