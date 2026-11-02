import httpx
import pymupdf

from app.domain.errors import PageReadError
from app.domain.models import RenderedImage, TextLine
from app.infrastructure.nemotron_format import parse_blocks, to_lines

JPEG_QUALITY = 90
COMPLETE = "stop"


class NemotronParser:
    """Reads a page image with NVIDIA's hosted Nemotron 3.5 Parse model."""

    def __init__(self, client: httpx.Client, url: str, api_key: str) -> None:
        self._client = client
        self._url = url
        self._api_key = api_key

    def parse(self, image: RenderedImage) -> list[TextLine]:
        content = self._request(image)
        blocks = parse_blocks(content)
        if not blocks:
            raise PageReadError("Nemotron Parse returned no readable blocks.")
        return [
            line
            for block in blocks
            for line in to_lines(block, image.width, image.height)
        ]

    def _request(self, image: RenderedImage) -> str:
        try:
            response = self._client.post(
                self._url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept": "application/json",
                },
                files={"document": ("page.jpg", _to_jpeg(image), "image/jpeg")},
            )
        except httpx.TimeoutException as error:
            raise PageReadError("Nemotron Parse timed out.") from error
        except httpx.HTTPError as error:
            raise PageReadError("Nemotron Parse could not be reached.") from error

        if response.status_code != httpx.codes.OK:
            raise PageReadError(f"Nemotron Parse returned HTTP {response.status_code}.")
        try:
            body = response.json()
            content, finish_reason = body["content"], body["finish_reason"]
        except (ValueError, KeyError, TypeError) as error:
            raise PageReadError("Nemotron Parse returned an unexpected response.") from error

        # Anything else means the page was cut off, and a partial invoice is
        # worse than a slower complete one.
        if finish_reason != COMPLETE:
            raise PageReadError("Nemotron Parse stopped before finishing the page.")
        return content


def _to_jpeg(image: RenderedImage) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, image.width, image.height, image.samples, False)
    return pixmap.tobytes("jpeg", jpg_quality=JPEG_QUALITY)
