import asyncio
import time
from collections.abc import Callable

from pydantic import BaseModel

from app.domain.errors import LlmError
from app.domain.llm import ModelStatus
from app.domain.ports import NamedLlmClient
from app.infrastructure.llm_chain import ask_one
from app.infrastructure.model_health import ModelHealth

PROBE_SYSTEM = "Reply with the JSON object requested."
PROBE_USER = 'Return {"ok": true}.'


class _Probe(BaseModel):
    ok: bool


class _WithDeadline:
    """Gives one model a shorter limit than real invoices get, so a check
    reports a model that is down within seconds rather than a minute."""

    def __init__(self, client: NamedLlmClient, seconds: float) -> None:
        self._client = client
        self._seconds = seconds

    @property
    def model(self) -> str:
        return self._client.model

    async def complete_json(self, system: str, user: str, output: type) -> BaseModel:
        try:
            return await asyncio.wait_for(
                self._client.complete_json(system, user, output), self._seconds
            )
        except TimeoutError as error:
            raise LlmError(f"No answer within {self._seconds:g} s.") from error


class ModelProber:
    """Sends a tiny request to every model at once and records the result in
    ModelHealth. A model that fails is skipped straight away, so no invoice
    waits on it; one that answers is back in use at once. Checks closer
    together than `min_interval_seconds` reuse the last result, so many page
    loads don't spend the API's rate limit."""

    def __init__(
        self,
        clients: list[NamedLlmClient],
        health: ModelHealth,
        timeout_seconds: float = 10,
        min_interval_seconds: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clients = [_WithDeadline(client, timeout_seconds) for client in clients]
        self._health = health
        self._min_interval_seconds = min_interval_seconds
        self._clock = clock
        self._last_check: float | None = None
        self._lock = asyncio.Lock()

    async def check(self) -> list[ModelStatus]:
        async with self._lock:
            if not self._checked_recently():
                answers = await asyncio.gather(
                    *(
                        ask_one(client, self._health, PROBE_SYSTEM, PROBE_USER, _Probe)
                        for client in self._clients
                    )
                )
                for answer in answers:
                    if not answer.answered:
                        self._health.cool_down(answer.model)
                self._last_check = self._clock()
        return self._health.status()

    def _checked_recently(self) -> bool:
        if self._last_check is None:
            return False
        return self._clock() - self._last_check < self._min_interval_seconds
