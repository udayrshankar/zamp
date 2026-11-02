from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.models import (
    DocumentError,
    DocumentStatus,
    ExtractionSummary,
    ExtractionWarning,
    PageResult,
    PurchaseOrder,
)


class UploadAccepted(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: DocumentStatus


class DocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    sha256: str
    size_bytes: int
    status: DocumentStatus
    page_count: int | None
    summary: ExtractionSummary | None
    warnings: list[ExtractionWarning]
    error: DocumentError | None
    created_at: datetime
    updated_at: datetime


class DocumentDetail(DocumentListItem):
    pages: list[PageResult]


class DocumentPage(BaseModel):
    items: list[DocumentListItem]
    total: int
    limit: int
    offset: int


class PurchaseOrderPage(BaseModel):
    items: list[PurchaseOrder]
    total: int
    limit: int
    offset: int
