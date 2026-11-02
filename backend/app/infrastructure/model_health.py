import time
from collections.abc import Callable
from dataclasses import dataclass

from app.domain.llm import ModelState, ModelStatus


@dataclass(slots=True)
class _Record:
    failures_in_a_row: int = 0
    cooling_until: float = 0.0
    last_seconds: float | None = None
    last_error: str | None = None
    seen: bool = False


class ModelHealth:
    """Remembers which models have been failing, so a model that is down is
    skipped for a while instead of making every invoice wait for its timeout."""

    def __init__(
        self,
        models: list[str],
        failures_to_trip: int = 2,
        cooldown_seconds: float = 300,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._order = list(models)
        self._records = {model: _Record() for model in models}
        self._failures_to_trip = failures_to_trip
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock

    def preferred(self) -> list[str]:
        """Healthy models in configured order. If every model is cooling down,
        all of them, because trying is better than giving up."""
        healthy = [model for model in self._order if self._is_healthy(model)]
        return healthy or list(self._order)

    def record_success(self, model: str, seconds: float) -> None:
        record = self._records[model]
        record.failures_in_a_row = 0
        record.cooling_until = 0.0
        record.last_seconds = round(seconds, 2)
        record.last_error = None
        record.seen = True

    def record_failure(self, model: str, seconds: float, error: str) -> None:
        record = self._records[model]
        record.failures_in_a_row += 1
        record.last_seconds = round(seconds, 2)
        record.last_error = error
        record.seen = True
        if record.failures_in_a_row >= self._failures_to_trip:
            record.cooling_until = self._clock() + self._cooldown_seconds

    def status(self) -> list[ModelStatus]:
        return [self._status_of(model) for model in self._order]

    def _is_healthy(self, model: str) -> bool:
        return self._clock() >= self._records[model].cooling_until

    def _status_of(self, model: str) -> ModelStatus:
        record = self._records[model]
        if not record.seen:
            state = ModelState.UNKNOWN
        elif self._is_healthy(model) and record.failures_in_a_row == 0:
            state = ModelState.OK
        elif self._is_healthy(model):
            state = ModelState.UNKNOWN
        else:
            state = ModelState.COOLING_DOWN
        return ModelStatus(
            name=model,
            state=state,
            last_seconds=record.last_seconds,
            last_error=record.last_error,
        )
