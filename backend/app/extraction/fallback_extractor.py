from app.domain.errors import ExtractionError, NothingToParseError
from app.domain.models import PageResult, RoutingReason
from app.domain.ports import PageExtractor, PdfPage


class FallbackPageExtractor:
    """Tries one extractor and turns to another if it can't read the page."""

    def __init__(self, primary: PageExtractor, fallback: PageExtractor) -> None:
        self._primary = primary
        self._fallback = fallback

    def extract(self, page: PdfPage, reason: RoutingReason) -> PageResult:
        try:
            return self._primary.extract(page, reason)
        except NothingToParseError:
            # A deliberate choice rather than a fault, so nothing to warn about.
            return self._fallback.extract(page, reason)
        except ExtractionError as error:
            result = self._fallback.extract(page, reason)
            return result.model_copy(update={"fallback_reason": error.message})
