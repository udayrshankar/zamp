import pytest

from app.domain.errors import TooManyPagesError
from app.domain.models import PageMethod, TextLine, WarningCode
from app.extraction.classifier import PageClassifier, RoutingThresholds
from app.extraction.native_extractor import NativeTextExtractor
from app.extraction.ocr_extractor import OcrTextExtractor
from app.extraction.pipeline import ExtractionPipeline
from tests.fakes import GOOD_TEXT, FakeOcrEngine, FakePage, FakePdf, FakeReader

OCR_LINE = TextLine(text="Scanned total 500.00", bbox=(0, 0, 720, 30), confidence=0.9)
LOW_LINE = TextLine(text="sc4nned t0tal", bbox=(0, 0, 720, 30), confidence=0.4)


def run(pages, ocr_lines=(), max_pages=50):
    pipeline = ExtractionPipeline(
        reader=FakeReader(FakePdf(pages)),
        classifier=PageClassifier(RoutingThresholds()),
        native_extractor=NativeTextExtractor(),
        image_extractor=OcrTextExtractor(FakeOcrEngine(list(ocr_lines)), dpi=72),
        max_pages=max_pages,
        low_confidence=0.7,
    )
    return pipeline.run(b"pdf")


def test_each_page_is_routed_on_its_own():
    result = run([FakePage(1, GOOD_TEXT), FakePage(2)], [OCR_LINE])

    assert [page.method for page in result.pages] == [PageMethod.NATIVE, PageMethod.OCR]
    assert result.summary.native_pages == 1
    assert result.summary.ocr_pages == 1
    assert result.summary.mean_ocr_confidence == pytest.approx(0.9)
    assert result.warnings == []


def test_both_paths_produce_text_in_the_same_shape():
    native, ocr = run([FakePage(1, GOOD_TEXT), FakePage(2)], [OCR_LINE]).pages

    assert native.text == GOOD_TEXT
    assert native.confidence is None
    assert ocr.text == OCR_LINE.text
    assert ocr.confidence == pytest.approx(0.9)


def test_ocr_boxes_are_converted_to_pdf_points():
    pipeline_at_144_dpi = ExtractionPipeline(
        reader=FakeReader(FakePdf([FakePage()])),
        classifier=PageClassifier(RoutingThresholds()),
        native_extractor=NativeTextExtractor(),
        image_extractor=OcrTextExtractor(FakeOcrEngine([OCR_LINE]), dpi=144),
        max_pages=50,
        low_confidence=0.7,
    )

    assert pipeline_at_144_dpi.run(b"pdf").pages[0].lines[0].bbox == (0, 0, 360, 15)


def test_page_with_nothing_on_it_is_blank():
    result = run([FakePage(1, GOOD_TEXT), FakePage(2)])

    assert result.pages[1].method is PageMethod.BLANK
    assert [warning.code for warning in result.warnings] == [WarningCode.BLANK_PAGE]


def test_all_blank_pages_also_warn_about_the_document():
    result = run([FakePage()])

    assert [warning.code for warning in result.warnings] == [
        WarningCode.BLANK_PAGE,
        WarningCode.NO_TEXT_FOUND,
    ]


def test_low_confidence_page_is_flagged():
    warning = run([FakePage()], [LOW_LINE]).warnings[0]

    assert warning.code is WarningCode.LOW_OCR_CONFIDENCE
    assert warning.page == 1


def test_failed_page_does_not_lose_the_others():
    result = run([FakePage(1, GOOD_TEXT), FakePage(2, render_error=True)])

    assert result.pages[0].text == GOOD_TEXT
    assert result.pages[1].method is PageMethod.FAILED
    assert result.summary.failed_pages == 1
    assert [warning.code for warning in result.warnings] == [WarningCode.PAGE_FAILED]


def test_all_failed_pages_are_not_reported_as_no_text():
    result = run([FakePage(render_error=True)])

    assert WarningCode.NO_TEXT_FOUND not in [warning.code for warning in result.warnings]


def test_page_limit_is_enforced():
    with pytest.raises(TooManyPagesError, match="3 pages"):
        run([FakePage(), FakePage(), FakePage()], max_pages=2)
