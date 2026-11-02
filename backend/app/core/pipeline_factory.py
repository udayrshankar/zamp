import httpx

from app.core.config import Settings
from app.domain.ports import PageExtractor
from app.extraction.classifier import PageClassifier, RoutingThresholds
from app.extraction.fallback_extractor import FallbackPageExtractor
from app.extraction.gap_filling_extractor import GapFillingExtractor
from app.extraction.native_extractor import NativeTextExtractor
from app.extraction.ocr_extractor import OcrTextExtractor
from app.extraction.parse_extractor import ParseTextExtractor
from app.extraction.pipeline import ExtractionPipeline
from app.infrastructure.nemotron_parser import NemotronParser
from app.infrastructure.pymupdf_reader import PyMuPdfReader
from app.infrastructure.rapidocr_engine import RapidOcrEngine


def build_image_extractor(settings: Settings) -> PageExtractor:
    """Pages that need reading from their image: Nemotron Parse, backed by local OCR."""
    ocr = OcrTextExtractor(RapidOcrEngine(), settings.OCR_DPI)
    if not settings.NVIDIA_KEY:
        return ocr

    parser = NemotronParser(
        client=httpx.Client(timeout=settings.NEMOTRON_PARSE_TIMEOUT_SECONDS),
        url=settings.NEMOTRON_PARSE_URL,
        api_key=settings.NVIDIA_KEY,
    )
    parse = ParseTextExtractor(
        parser=parser,
        max_width=settings.NEMOTRON_PARSE_MAX_WIDTH,
        max_height=settings.NEMOTRON_PARSE_MAX_HEIGHT,
        min_ink_ratio=settings.PARSE_MIN_INK_RATIO,
    )
    return FallbackPageExtractor(
        primary=GapFillingExtractor(primary=parse, backup=ocr), fallback=ocr
    )


def build_pipeline(settings: Settings) -> ExtractionPipeline:
    """Wires the concrete PDF reader and text extractors. Swap engines here."""
    thresholds = RoutingThresholds(
        min_text_chars=settings.MIN_TEXT_CHARS,
        min_alnum_ratio=settings.MIN_ALNUM_RATIO,
        image_coverage=settings.IMAGE_COVERAGE_THRESHOLD,
        sparse_text_chars=settings.SPARSE_TEXT_CHARS,
    )
    return ExtractionPipeline(
        reader=PyMuPdfReader(),
        classifier=PageClassifier(thresholds),
        native_extractor=NativeTextExtractor(),
        image_extractor=build_image_extractor(settings),
        max_pages=settings.MAX_PAGES,
        low_confidence=settings.LOW_OCR_CONFIDENCE,
    )
