from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field, JsonValue, field_validator

BBox = tuple[float, float, float, float]


class DocumentStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PageMethod(StrEnum):
    NATIVE = "native"
    OCR = "ocr"
    PARSE = "parse"
    BLANK = "blank"
    FAILED = "failed"


class RoutingReason(StrEnum):
    TEXT_LAYER_OK = "text_layer_ok"
    NO_TEXT_LAYER = "no_text_layer"
    GARBLED_TEXT_LAYER = "garbled_text_layer"
    SPARSE_TEXT_OVER_IMAGE = "sparse_text_over_image"


class WarningCode(StrEnum):
    LOW_OCR_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    BLANK_PAGE = "BLANK_PAGE"
    PAGE_FAILED = "PAGE_FAILED"
    NO_TEXT_FOUND = "NO_TEXT_FOUND"
    PARSE_FALLBACK = "PARSE_FALLBACK"


class ErrorCode(StrEnum):
    ENCRYPTED_PDF = "ENCRYPTED_PDF"
    CORRUPT_PDF = "CORRUPT_PDF"
    TOO_MANY_PAGES = "TOO_MANY_PAGES"
    PAGE_READ_FAILED = "PAGE_READ_FAILED"
    INTERRUPTED = "INTERRUPTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class RenderedImage:
    """Raw interleaved pixels, so the domain never depends on an image library."""

    width: int
    height: int
    channels: int
    samples: bytes
    pixels_per_point: float


class TextLine(BaseModel):
    """A run of text with its position in PDF points.

    `confidence` is None for native text: there is no recognition step to be
    unsure about, so reporting 1.0 would be misleading.
    """

    text: str
    bbox: BBox
    confidence: float | None = None


class PageResult(BaseModel):
    number: int
    method: PageMethod
    routing_reason: RoutingReason
    text: str = ""
    confidence: float | None = None
    lines: list[TextLine] = Field(default_factory=list)
    fallback_reason: str | None = None
    gap_filled: bool = False


class ExtractionSummary(BaseModel):
    native_pages: int = 0
    ocr_pages: int = 0
    parse_pages: int = 0
    blank_pages: int = 0
    failed_pages: int = 0
    mean_ocr_confidence: float | None = None


class ExtractionWarning(BaseModel):
    code: WarningCode
    message: str
    page: int | None = None


class ExtractionResult(BaseModel):
    page_count: int
    pages: list[PageResult]
    summary: ExtractionSummary
    warnings: list[ExtractionWarning] = Field(default_factory=list)


class DocumentError(BaseModel):
    code: ErrorCode
    message: str


def _utcnow() -> datetime:
    # MongoDB stores milliseconds. Matching that here means a value returned on
    # create is identical to the same value read back later.
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


class Document(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    filename: str
    sha256: str
    size_bytes: int
    file_id: str
    status: DocumentStatus = DocumentStatus.QUEUED
    page_count: int | None = None
    summary: ExtractionSummary | None = None
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    error: DocumentError | None = None
    pages: list[PageResult] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class PurchaseOrderData(BaseModel):
    """The editable part of a purchase order.

    Only `po_number` is required, because a PO must be identifiable. Everything
    else is up to the user: `fields` holds whatever this PO needs, such as
    `handling_charges` or `line_items`, and values can be any JSON.
    """

    po_number: str = Field(min_length=1)
    fields: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("po_number")
    @classmethod
    def _strip_po_number(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("po_number must not be blank")
        return stripped

    @field_validator("fields")
    @classmethod
    def _check_field_names(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        for name in value:
            # MongoDB gives "." and a leading "$" special meaning in field names.
            if not name.strip() or "." in name or name.startswith("$"):
                raise ValueError(
                    f"Invalid field name {name!r}: it must not be blank, "
                    "contain '.', or start with '$'"
                )
        return value


class PurchaseOrder(PurchaseOrderData):
    id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
