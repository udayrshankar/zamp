import pytest

from app.domain.models import RoutingReason
from app.extraction.classifier import PageClassifier, RoutingThresholds
from tests.fakes import GOOD_TEXT, FakePage

classifier = PageClassifier(RoutingThresholds())


def test_good_text_layer_is_trusted():
    assert classifier.classify(FakePage(text=GOOD_TEXT)) is RoutingReason.TEXT_LAYER_OK


def test_page_without_text_needs_ocr():
    assert classifier.classify(FakePage()) is RoutingReason.NO_TEXT_LAYER


def test_short_text_is_not_trusted():
    assert classifier.classify(FakePage(text="Page 2 of 2")) is RoutingReason.NO_TEXT_LAYER


@pytest.mark.parametrize("text", ["#%&@!?*~^=+" * 10, GOOD_TEXT + "�"])
def test_garbled_text_layer_needs_ocr(text):
    assert classifier.classify(FakePage(text=text)) is RoutingReason.GARBLED_TEXT_LAYER


def test_scan_with_a_stamped_header_needs_ocr():
    page = FakePage(text=GOOD_TEXT, coverage=0.95)

    assert classifier.classify(page) is RoutingReason.SPARSE_TEXT_OVER_IMAGE


def test_long_text_over_an_image_is_trusted():
    page = FakePage(text=GOOD_TEXT * 4, coverage=0.95)

    assert classifier.classify(page) is RoutingReason.TEXT_LAYER_OK


def test_text_beside_a_small_logo_is_trusted():
    page = FakePage(text=GOOD_TEXT, coverage=0.1)

    assert classifier.classify(page) is RoutingReason.TEXT_LAYER_OK
