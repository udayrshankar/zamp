import time
from typing import TypeVar

from pydantic import BaseModel

from app.domain.errors import LlmError
from app.domain.llm import AnswerStatus, ModelAnswer
from app.domain.ports import NamedLlmClient
from app.infrastructure.model_health import ModelHealth

T = TypeVar("T", bound=BaseModel)


async def ask_one(
    client: NamedLlmClient, health: ModelHealth, system: str, user: str, output: type[T]
) -> ModelAnswer[T]:
    """Asks one model and records how it went, without ever raising."""
    started = time.monotonic()
    try:
        answer = await client.complete_json(system, user, output)
    except LlmError as error:
        seconds = time.monotonic() - started
        health.record_failure(client.model, seconds, error.message)
        return ModelAnswer(
            client.model, AnswerStatus.FAILED, round(seconds, 2), error=error.message
        )
    seconds = time.monotonic() - started
    health.record_success(client.model, seconds)
    return ModelAnswer(client.model, AnswerStatus.ANSWERED, round(seconds, 2), output=answer)


class FallbackLlmClient:
    """An LlmClient that tries each healthy model in order until one answers.
    Callers see a single client, so nothing upstream changes when a model is
    added, removed or down."""

    def __init__(self, clients: list[NamedLlmClient], health: ModelHealth) -> None:
        self._clients = {client.model: client for client in clients}
        self._health = health

    async def complete_json(self, system: str, user: str, output: type[T]) -> T:
        errors = []
        for model in self._health.preferred():
            answer = await ask_one(self._clients[model], self._health, system, user, output)
            if answer.answered:
                return answer.output
            errors.append(f"{model}: {answer.error}")
        raise LlmError("No model could answer. " + " ".join(errors))
