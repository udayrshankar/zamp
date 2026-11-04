"""What the rest of the app knows about the LLMs: each model's answer and its health.
Kept separate from any provider, so the workflow never imports infrastructure."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ModelAnswer(Generic[T]):
    """One model's reply to a question put to the panel."""

    model: str
    status: AnswerStatus
    seconds: float
    output: T | None = None
    error: str | None = None

    @property
    def answered(self) -> bool:
        return self.status is AnswerStatus.ANSWERED and self.output is not None


class ModelState(StrEnum):
    OK = "ok"
    # Its last call failed, but not often enough yet to be skipped.
    FAILING = "failing"
    # Failed repeatedly, so it is skipped until its cooldown ends.
    COOLING_DOWN = "cooling_down"
    # Not called since the server started.
    UNKNOWN = "unknown"


class ModelStatus(BaseModel):
    name: str
    state: ModelState
    last_seconds: float | None = None
    last_error: str | None = None
