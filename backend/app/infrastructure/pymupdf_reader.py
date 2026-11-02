from collections.abc import Iterator
from types import TracebackType
from typing import Self

import pymupdf

from app.domain.errors import CorruptPdfError, EncryptedPdfError, PageReadError
from app.domain.models import RenderedImage, TextLine

POINTS_PER_INCH = 72
# Keeps an oversized page from allocating gigabytes when rendered.
MAX_RENDER_SIDE_PX = 6000


class PyMuPdfPage:
    def __init__(self, page: pymupdf.Page) -> None:
        self._page = page

    @property
    def number(self) -> int:
        return self._page.number + 1

    def fragments(self) -> list[TextLine]:
        try:
            words = self._page.get_text("words")
        except Exception as error:
            raise PageReadError(f"Could not read text on page {self.number}.") from error
        return [TextLine(text=word[4], bbox=tuple(word[:4])) for word in words]

    def image_coverage(self) -> float:
        page_area = self._page.rect.get_area()
        if not page_area:
            return 0.0
        covered = 0.0
        for image in self._page.get_image_info():
            visible = pymupdf.Rect(image["bbox"]) & self._page.rect
            covered += visible.get_area()
        # Overlapping images are counted twice, which only matters for pages
        # that are mostly images anyway.
        return min(covered / page_area, 1.0)

    def render(self, dpi: int) -> RenderedImage:
        longest_side = max(self._page.rect.width, self._page.rect.height)
        return self._render_at(min(dpi / POINTS_PER_INCH, MAX_RENDER_SIDE_PX / longest_side))

    def render_to_fit(self, max_width: int, max_height: int) -> RenderedImage:
        return self._render_at(
            min(max_width / self._page.rect.width, max_height / self._page.rect.height)
        )

    def _render_at(self, pixels_per_point: float) -> RenderedImage:
        try:
            pixmap = self._page.get_pixmap(
                matrix=pymupdf.Matrix(pixels_per_point, pixels_per_point),
                colorspace=pymupdf.csRGB,
                alpha=False,
            )
        except Exception as error:
            raise PageReadError(f"Could not render page {self.number}.") from error
        return RenderedImage(
            width=pixmap.width,
            height=pixmap.height,
            channels=pixmap.n,
            samples=pixmap.samples,
            pixels_per_point=pixels_per_point,
        )


class PyMuPdfDocument:
    def __init__(self, document: pymupdf.Document) -> None:
        self._document = document

    @property
    def page_count(self) -> int:
        return self._document.page_count

    def pages(self) -> Iterator[PyMuPdfPage]:
        for page in self._document:
            yield PyMuPdfPage(page)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._document.close()


class PyMuPdfReader:
    def open(self, data: bytes) -> PyMuPdfDocument:
        try:
            document = pymupdf.open(stream=data, filetype="pdf")
        except Exception as error:
            raise CorruptPdfError() from error
        if document.needs_pass:
            document.close()
            raise EncryptedPdfError()
        if document.page_count == 0:
            document.close()
            raise CorruptPdfError("The PDF has no readable pages.")
        return PyMuPdfDocument(document)
