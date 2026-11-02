from dataclasses import dataclass, field

import pytest

from app.domain.errors import NothingToParseError, PageReadError
from app.domain.models import (
    PageMethod,
    PageResult,
    RenderedImage,
    RoutingReason,
    TextLine,
    WarningCode,
)
from app.extraction.classifier import PageClassifier, RoutingThresholds
from app.extraction.fallback_extractor import FallbackPageExtractor
from app.extraction.ink import ink_ratio
from app.extraction.native_extractor import NativeTextExtractor
from app.extraction.parse_extractor import ParseTextExtractor
from app.extraction.pipeline import ExtractionPipeline
from tests.fakes import GOOD_TEXT, FakePage, FakePdf, FakeReader

REASON = RoutingReason.NO_TEXT_LAYER
INKED_PAGE = b"\xff" * 900 + b"\x00" * 100
EMPTY_PAGE = b"\xff" * 100_000


def image_of(samples: bytes) -> RenderedImage:
    return RenderedImage(width=1, height=1, channels=3, samples=samples, pixels_per_point=1.0)


@dataclass
class FakeParser:
    lines: list[TextLine] = field(default_factory=list)
    error: Exception | None = None
    calls: int = 0

    def parse(self, image: RenderedImage) -> list[TextLine]:
        self.calls += 1
        if self.error:
            raise self.error
        return self.lines


@dataclass
class StubExtractor:
    result: PageResult | None = None
    error: Exception | None = None

    def extract(self, page, reason: RoutingReason) -> PageResult:
        if self.error:
            raise self.error
        return self.result


OCR_RESULT = PageResult(
    number=1, method=PageMethod.OCR, routing_reason=REASON, text="from ocr", confidence=0.9
)


def parse_extractor(parser: FakeParser) -> ParseTextExtractor:
    return ParseTextExtractor(parser, max_width=800, max_height=1000, min_ink_ratio=0.001)


class TestInkRatio:
    def test_blank_page_has_no_ink(self):
        assert ink_ratio(image_of(b"\xff" * 1000)) == 0

    def test_counts_pixels_that_stand_out(self):
        assert ink_ratio(image_of(INKED_PAGE)) == pytest.approx(0.1)

    def test_faint_text_on_a_pale_page_still_counts(self):
        assert ink_ratio(image_of(b"\xff" * 900 + b"\xb2" * 100)) == pytest.approx(0.1)

    def test_scanner_noise_is_not_ink(self):
        assert ink_ratio(image_of(bytes([245, 235, 255, 240]) * 250)) == 0

    def test_grey_background_is_measured_from_itself(self):
        assert ink_ratio(image_of(b"\x80" * 1000)) == 0

    def test_empty_image(self):
        assert ink_ratio(image_of(b"")) == 0


class TestParseExtractor:
    def test_reads_a_page_and_converts_boxes_to_points(self):
        parser = FakeParser([TextLine(text="Total 10.00", bbox=(20, 40, 200, 80))])

        result = parse_extractor(parser).extract(FakePage(pixels=INKED_PAGE), REASON)

        assert result.method is PageMethod.PARSE
        assert result.text == "Total 10.00"
        assert result.confidence is None
        assert result.lines[0].bbox == (10, 20, 100, 40)

    def test_keeps_the_reading_order_of_the_model(self):
        # Sideways text gives tall boxes at the same height, which sorting by
        # position would wrongly merge into one row.
        parser = FakeParser(
            [
                TextLine(text="first", bbox=(100, 0, 120, 200)),
                TextLine(text="second", bbox=(50, 0, 70, 200)),
            ]
        )

        result = parse_extractor(parser).extract(FakePage(pixels=INKED_PAGE), REASON)

        assert result.text == "first\nsecond"

    def test_near_empty_page_never_reaches_the_model(self):
        parser = FakeParser([TextLine(text="invented", bbox=(0, 0, 1, 1))])

        with pytest.raises(NothingToParseError):
            parse_extractor(parser).extract(FakePage(pixels=EMPTY_PAGE), REASON)

        assert parser.calls == 0


class TestFallback:
    def test_uses_the_primary_when_it_works(self):
        primary = PageResult(number=1, method=PageMethod.PARSE, routing_reason=REASON)
        extractor = FallbackPageExtractor(StubExtractor(primary), StubExtractor(OCR_RESULT))

        assert extractor.extract(FakePage(), REASON) is primary

    def test_records_why_the_fallback_was_needed(self):
        extractor = FallbackPageExtractor(
            StubExtractor(error=PageReadError("Nemotron Parse timed out.")),
            StubExtractor(OCR_RESULT),
        )

        result = extractor.extract(FakePage(), REASON)

        assert result.method is PageMethod.OCR
        assert result.fallback_reason == "Nemotron Parse timed out."

    def test_skipping_a_near_empty_page_is_not_reported_as_a_fault(self):
        extractor = FallbackPageExtractor(
            StubExtractor(error=NothingToParseError()), StubExtractor(OCR_RESULT)
        )

        assert extractor.extract(FakePage(), REASON).fallback_reason is None

    def test_a_failing_fallback_still_fails(self):
        extractor = FallbackPageExtractor(
            StubExtractor(error=PageReadError()), StubExtractor(error=PageReadError("ocr"))
        )

        with pytest.raises(PageReadError, match="ocr"):
            extractor.extract(FakePage(), REASON)


class TestPipelineWithParse:
    def run(self, parser: FakeParser, pages: list[FakePage]):
        image_extractor = FallbackPageExtractor(
            parse_extractor(parser), StubExtractor(OCR_RESULT)
        )
        pipeline = ExtractionPipeline(
            reader=FakeReader(FakePdf(pages)),
            classifier=PageClassifier(RoutingThresholds()),
            native_extractor=NativeTextExtractor(),
            image_extractor=image_extractor,
            max_pages=50,
            low_confidence=0.7,
        )
        return pipeline.run(b"pdf")

    def test_good_text_layers_stay_native_and_never_call_the_model(self):
        parser = FakeParser()

        result = self.run(parser, [FakePage(text=GOOD_TEXT)])

        assert result.pages[0].method is PageMethod.NATIVE
        assert parser.calls == 0

    def test_summary_counts_parsed_pages(self):
        parser = FakeParser([TextLine(text="scanned", bbox=(0, 0, 10, 10))])

        result = self.run(parser, [FakePage(pixels=INKED_PAGE)])

        assert result.summary.parse_pages == 1
        assert result.summary.mean_ocr_confidence is None
        assert result.warnings == []

    def test_fallback_is_visible_as_a_warning(self):
        parser = FakeParser(error=PageReadError("Nemotron Parse returned HTTP 429."))

        result = self.run(parser, [FakePage(pixels=INKED_PAGE)])

        assert result.summary.ocr_pages == 1
        assert [warning.code for warning in result.warnings] == [WarningCode.PARSE_FALLBACK]
        assert "HTTP 429" in result.warnings[0].message
