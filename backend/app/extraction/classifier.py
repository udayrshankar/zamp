from dataclasses import dataclass

from app.domain.models import RoutingReason
from app.domain.ports import PdfPage

REPLACEMENT_CHAR = "�"


@dataclass(frozen=True, slots=True)
class RoutingThresholds:
    min_text_chars: int = 50
    min_alnum_ratio: float = 0.5
    image_coverage: float = 0.5
    sparse_text_chars: int = 200


class PageClassifier:
    """Decides whether a page's embedded text can be trusted."""

    def __init__(self, thresholds: RoutingThresholds) -> None:
        self._thresholds = thresholds

    def classify(self, page: PdfPage) -> RoutingReason:
        text = "".join(fragment.text for fragment in page.fragments())
        chars = "".join(text.split())

        if len(chars) < self._thresholds.min_text_chars:
            return RoutingReason.NO_TEXT_LAYER
        if self._is_garbled(chars):
            return RoutingReason.GARBLED_TEXT_LAYER
        if (
            len(chars) < self._thresholds.sparse_text_chars
            and page.image_coverage() >= self._thresholds.image_coverage
        ):
            return RoutingReason.SPARSE_TEXT_OVER_IMAGE
        return RoutingReason.TEXT_LAYER_OK

    def _is_garbled(self, chars: str) -> bool:
        if REPLACEMENT_CHAR in chars:
            return True
        alnum = sum(char.isalnum() for char in chars)
        return alnum / len(chars) < self._thresholds.min_alnum_ratio
