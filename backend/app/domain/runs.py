from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_PO = "awaiting_po"
    COMPLETED = "completed"
    FAILED = "failed"


class StageName(StrEnum):
    EXTRACTION = "extraction"
    PO_DETECTION = "po_detection"
    PO_CONFIRMATION = "po_confirmation"
    VERIFICATION = "verification"
    CHECKS = "checks"
    DECISION = "decision"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Decision(StrEnum):
    ACCEPT = "accept"
    REVIEW = "review"
    REJECT = "reject"


class CheckOutcome(StrEnum):
    PASS = "pass"
    REVIEW = "review"
    REJECT = "reject"


class PoSource(StrEnum):
    DETECTED = "detected"
    USER_SUPPLIED = "user_supplied"


_PLACEHOLDERS = {"", "null", "none", "n/a", "na", "not available", "unknown"}


class LlmOutput(BaseModel):
    """Base for what the LLM returns. Unknown keys fail validation."""

    model_config = ConfigDict(extra="forbid")


class ExtractedFacts(LlmOutput):
    """Models sometimes write "null" as text, which would otherwise pass as a
    real value: an invoice with no number would seem to have one."""

    @field_validator("*", mode="before")
    @classmethod
    def _placeholder_means_missing(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().casefold() in _PLACEHOLDERS:
            return None
        return value


class PoCandidate(LlmOutput):
    value: str
    evidence: str


class PoDetectionOutput(LlmOutput):
    candidates: list[PoCandidate]


class LineItem(LlmOutput):
    description: str
    quantity: float | None
    # The unit of measure printed for the quantity, such as kg or nos. Optional
    # so runs saved before units were read still load.
    unit: str | None = None
    unit_price: float | None
    # Optional so runs saved before discounts were read still load.
    discount_percent: float | None = None
    amount: float | None


class Charge(LlmOutput):
    label: str
    amount: float


class InvoiceFacts(ExtractedFacts):
    invoice_number: str | None
    invoice_date: str | None
    vendor: str | None
    currency: str | None
    line_items: list[LineItem]
    subtotal: float | None
    tax: float | None
    charges: list[Charge]
    total: float | None


class PoFacts(ExtractedFacts):
    """Values from a free-form PO, each with the field it came from, so that
    code can confirm the field really holds that value."""

    vendor_field: str | None
    vendor: str | None
    total_field: str | None
    total: float | None
    currency_field: str | None
    currency: str | None


class Discrepancy(LlmOutput):
    kind: Literal["item_not_on_po", "quantity_over_po", "price_differs"]
    description: str
    evidence: str
    invoice_value: float | None
    po_value: float | None


class VerificationOutput(LlmOutput):
    invoice: InvoiceFacts
    purchase_order: PoFacts
    vendor_match: Literal["yes", "no", "unclear"]
    discrepancies: list[Discrepancy]


class CheckResult(BaseModel):
    name: str
    outcome: CheckOutcome
    message: str


class Stage(BaseModel):
    name: StageName
    status: StageStatus = StageStatus.PENDING
    summary: str | None = None
    detail: dict[str, JsonValue] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ModelVote(BaseModel):
    """What one model read, and what the rules would decide from its reading
    alone. Shown beside the final decision; it never changes it."""

    model: str
    status: Literal["answered", "failed"]
    seconds: float
    chosen: bool = False
    decision: Decision | None = None
    reasons: list[str] = Field(default_factory=list)
    invoice_number: str | None = None
    total: float | None = None
    vendor_match: Literal["yes", "no", "unclear"] | None = None
    error: str | None = None


class RunError(BaseModel):
    code: str
    message: str


def _utcnow() -> datetime:
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _new_stages() -> list[Stage]:
    return [Stage(name=name) for name in StageName]


class Run(BaseModel):
    """One invoice's journey to a decision, with everything that happened."""

    id: str = Field(default_factory=lambda: uuid4().hex)
    document_id: str
    filename: str
    sha256: str
    status: RunStatus = RunStatus.QUEUED
    stages: list[Stage] = Field(default_factory=_new_stages)
    po_prompt: str | None = None
    po_suggestions: list[str] = Field(default_factory=list)
    purchase_order_id: str | None = None
    po_number: str | None = None
    po_source: PoSource | None = None
    verification: VerificationOutput | None = None
    checks: list[CheckResult] = Field(default_factory=list)
    model_votes: list[ModelVote] = Field(default_factory=list)
    decision: Decision | None = None
    reasons: list[str] = Field(default_factory=list)
    error: RunError | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    def stage(self, name: StageName) -> Stage:
        return next(stage for stage in self.stages if stage.name is name)

    def begin_stage(self, name: StageName) -> None:
        stage = self.stage(name)
        stage.status = StageStatus.RUNNING
        stage.started_at = _utcnow()

    def end_stage(
        self,
        name: StageName,
        status: StageStatus,
        summary: str,
        detail: dict[str, JsonValue] | None = None,
    ) -> None:
        stage = self.stage(name)
        stage.status = status
        stage.summary = summary
        stage.detail = detail or {}
        stage.finished_at = _utcnow()

    def conclude(self, decision: Decision, reasons: list[str]) -> None:
        self.end_stage(StageName.DECISION, StageStatus.COMPLETED, decision.value.title())
        for stage in self.stages:
            if stage.status is StageStatus.PENDING:
                stage.status = StageStatus.SKIPPED
        self.decision = decision
        self.reasons = reasons
        self.status = RunStatus.COMPLETED
