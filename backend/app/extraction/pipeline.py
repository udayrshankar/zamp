from app.domain.errors import ExtractionError, TooManyPagesError
from app.domain.models import (
    ExtractionResult,
    ExtractionSummary,
    ExtractionWarning,
    PageMethod,
    PageResult,
    RoutingReason,
    WarningCode,
)
from app.domain.ports import PageExtractor, PdfPage, PdfReader
from app.extraction.classifier import PageClassifier


class ExtractionPipeline:
    """Turns PDF bytes into text, choosing how to read each page independently."""

    def __init__(
        self,
        reader: PdfReader,
        classifier: PageClassifier,
        native_extractor: PageExtractor,
        image_extractor: PageExtractor,
        max_pages: int,
        low_confidence: float,
    ) -> None:
        self._reader = reader
        self._classifier = classifier
        self._native_extractor = native_extractor
        self._image_extractor = image_extractor
        self._max_pages = max_pages
        self._low_confidence = low_confidence

    def run(self, data: bytes) -> ExtractionResult:
        with self._reader.open(data) as document:
            if document.page_count > self._max_pages:
                raise TooManyPagesError(
                    f"The PDF has {document.page_count} pages; the limit is {self._max_pages}."
                )
            pages = [self._read_page(page) for page in document.pages()]
        return ExtractionResult(
            page_count=len(pages),
            pages=pages,
            summary=_summarise(pages),
            warnings=self._collect_warnings(pages),
        )

    def _read_page(self, page: PdfPage) -> PageResult:
        reason = RoutingReason.TEXT_LAYER_OK
        try:
            reason = self._classifier.classify(page)
            extractor = (
                self._native_extractor
                if reason is RoutingReason.TEXT_LAYER_OK
                else self._image_extractor
            )
            return extractor.extract(page, reason)
        except ExtractionError:
            # One unreadable page must not cost us the rest of the invoice.
            return PageResult(
                number=page.number, method=PageMethod.FAILED, routing_reason=reason
            )

    def _collect_warnings(self, pages: list[PageResult]) -> list[ExtractionWarning]:
        warnings = [warning for page in pages for warning in self._page_warnings(page)]
        if all(page.method is PageMethod.BLANK for page in pages):
            warnings.append(
                ExtractionWarning(
                    code=WarningCode.NO_TEXT_FOUND,
                    message="No text was found anywhere in the document.",
                )
            )
        return warnings

    def _page_warnings(self, page: PageResult) -> list[ExtractionWarning]:
        warnings = []
        if page.fallback_reason:
            warnings.append(
                ExtractionWarning(
                    code=WarningCode.PARSE_FALLBACK,
                    page=page.number,
                    message=f"Page {page.number} used the backup OCR: {page.fallback_reason}",
                )
            )
        if page.method is PageMethod.BLANK:
            warnings.append(
                ExtractionWarning(
                    code=WarningCode.BLANK_PAGE,
                    page=page.number,
                    message=f"Page {page.number} appears to be blank.",
                )
            )
        elif page.method is PageMethod.FAILED:
            warnings.append(
                ExtractionWarning(
                    code=WarningCode.PAGE_FAILED,
                    page=page.number,
                    message=f"Page {page.number} could not be read.",
                )
            )
        elif page.confidence is not None and page.confidence < self._low_confidence:
            warnings.append(
                ExtractionWarning(
                    code=WarningCode.LOW_OCR_CONFIDENCE,
                    page=page.number,
                    message=f"OCR confidence on page {page.number} is {page.confidence:.0%}.",
                )
            )
        return warnings


def _summarise(pages: list[PageResult]) -> ExtractionSummary:
    counts = {method: 0 for method in PageMethod}
    for page in pages:
        counts[page.method] += 1
    confidences = [page.confidence for page in pages if page.confidence is not None]
    return ExtractionSummary(
        native_pages=counts[PageMethod.NATIVE],
        ocr_pages=counts[PageMethod.OCR],
        parse_pages=counts[PageMethod.PARSE],
        blank_pages=counts[PageMethod.BLANK],
        failed_pages=counts[PageMethod.FAILED],
        mean_ocr_confidence=sum(confidences) / len(confidences) if confidences else None,
    )
