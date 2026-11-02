from functools import cached_property

import numpy as np
from rapidocr import RapidOCR

from app.domain.errors import PageReadError
from app.domain.models import RenderedImage, TextLine


class RapidOcrEngine:
    @cached_property
    def _model(self) -> RapidOCR:
        # Loading takes seconds, so it waits until the first scanned page.
        return RapidOCR()

    def recognize(self, image: RenderedImage) -> list[TextLine]:
        pixels = np.frombuffer(image.samples, dtype=np.uint8).reshape(
            image.height, image.width, image.channels
        )
        try:
            # RapidOCR expects BGR, the OpenCV convention.
            output = self._model(pixels[:, :, ::-1])
        except Exception as error:
            raise PageReadError("The OCR engine failed on this page.") from error

        if output.boxes is None:
            return []
        return [
            TextLine(text=text, bbox=_bounding_box(box), confidence=float(score))
            for box, text, score in zip(output.boxes, output.txts, output.scores)
        ]


def _bounding_box(quad: np.ndarray) -> tuple[float, float, float, float]:
    xs, ys = quad[:, 0], quad[:, 1]
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
