import httpx
import pytest

from app.domain.errors import PageReadError
from app.domain.models import RenderedImage
from app.infrastructure.nemotron_parser import NemotronParser

IMAGE = RenderedImage(
    width=100, height=200, channels=3, samples=b"\xff" * 60000, pixels_per_point=1.0
)
GOOD_CONTENT = "<x_0.1><y_0.1>**Total**10.00<x_0.5><y_0.2><class_Text>"


def parser_returning(handler) -> NemotronParser:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return NemotronParser(client, "https://nvidia.test/parse", "secret-key")


def respond_with(status=200, **body):
    return lambda _: httpx.Response(status, json=body)


def test_sends_the_page_as_an_authorised_multipart_jpeg():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["type"] = request.headers["content-type"]
        seen["body"] = request.read()
        return httpx.Response(200, json={"content": GOOD_CONTENT, "finish_reason": "stop"})

    parser_returning(handler).parse(IMAGE)

    assert seen["auth"] == "Bearer secret-key"
    assert seen["type"].startswith("multipart/form-data")
    assert b'name="document"' in seen["body"]
    assert b"image/jpeg" in seen["body"]


def test_returns_lines_in_image_pixels():
    parser = parser_returning(respond_with(content=GOOD_CONTENT, finish_reason="stop"))

    line = parser.parse(IMAGE)[0]

    assert line.text == "Total 10.00"
    assert line.bbox == pytest.approx((10, 20, 50, 40))
    assert line.confidence is None


@pytest.mark.parametrize(
    "handler",
    [
        respond_with(status=403, detail="Authorization failed"),
        respond_with(status=429),
        respond_with(status=500),
        respond_with(content=GOOD_CONTENT, finish_reason="length"),
        respond_with(content="<x_0.0><y_0.0>runaway text", finish_reason="stop"),
        respond_with(content="", finish_reason="stop"),
        respond_with(unexpected="shape"),
        lambda _: httpx.Response(200, text="not json"),
    ],
)
def test_bad_responses_raise_page_read_error(handler):
    with pytest.raises(PageReadError):
        parser_returning(handler).parse(IMAGE)


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), httpx.ConnectError("down")])
def test_network_failures_raise_page_read_error(failure):
    def handler(_: httpx.Request) -> httpx.Response:
        raise failure

    with pytest.raises(PageReadError):
        parser_returning(handler).parse(IMAGE)


def test_errors_never_contain_the_api_key():
    with pytest.raises(PageReadError) as failure:
        parser_returning(respond_with(status=403)).parse(IMAGE)

    assert "secret-key" not in str(failure.value)
