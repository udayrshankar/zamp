import asyncio
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel

from app.domain.llm import ModelAnswer
from app.domain.ports import NamedLlmClient
from app.infrastructure.llm_chain import ask_one
from app.infrastructure.model_health import ModelHealth

T = TypeVar("T", bound=BaseModel)


class ParallelLlmPanel:
    """Puts the same question to several models at once. When one fails, the
    next healthy model in the chain takes its place, so the panel degrades from
    three answers to two, to one, and only then to none. No new round starts
    after `deadline_seconds`, so a run never waits on round after round."""

    def __init__(
        self,
        clients: list[NamedLlmClient],
        health: ModelHealth,
        size: int,
        deadline_seconds: float = 45,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clients = {client.model: client for client in clients}
        self._health = health
        self._size = size
        self._deadline_seconds = deadline_seconds
        self._clock = clock

    async def ask_all(self, system: str, user: str, output: type[T]) -> list[ModelAnswer[T]]:
        waiting = self._health.preferred()
        answers: list[ModelAnswer[T]] = []
        started = self._clock()
        while waiting and sum(answer.answered for answer in answers) < self._size:
            if answers and self._clock() - started >= self._deadline_seconds:
                break
            missing = self._size - sum(answer.answered for answer in answers)
            batch, waiting = waiting[:missing], waiting[missing:]
            answers += await asyncio.gather(
                *(
                    ask_one(self._clients[model], self._health, system, user, output)
                    for model in batch
                )
            )
        return answers
