import asyncio
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.domain.errors import LlmError

T = TypeVar("T", bound=BaseModel)

MAX_OUTPUT_TOKENS = 4000
COMPLETE = "stop"
CUT_SHORT = "length"
ATTEMPTS = 2


class _CutShort(LlmError):
    """The answer hit the token limit, so a retry gets a bigger budget."""


class _TimedOut(LlmError):
    """Not retried: a model this slow is better replaced by the next one."""


class NvidiaLlmClient:
    """Chat completions from one model, with schema-constrained JSON output."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        url: str,
        api_key: str,
        model: str,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self._client = client
        self._url = url
        self._api_key = api_key
        self._model = model
        self._retry_delay_seconds = retry_delay_seconds

    @property
    def model(self) -> str:
        return self._model

    async def complete_json(self, system: str, user: str, output: type[T]) -> T:
        failure = LlmError("The LLM was not called.")
        budget = MAX_OUTPUT_TOKENS
        for attempt in range(ATTEMPTS):
            if attempt:
                await asyncio.sleep(self._retry_delay_seconds * attempt)
            try:
                return await self._attempt(system, user, output, budget)
            except _TimedOut:
                raise
            except _CutShort as error:
                failure = error
                budget *= 2
            except LlmError as error:
                failure = error
        raise failure

    async def _attempt(self, system: str, user: str, output: type[T], budget: int) -> T:
        try:
            response = await self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0,
                    "max_tokens": budget,
                    # Reasoning models otherwise spend the whole budget thinking.
                    "chat_template_kwargs": {"enable_thinking": False},
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": output.__name__,
                            "schema": output.model_json_schema(),
                            "strict": True,
                        },
                    },
                },
            )
        except httpx.TimeoutException as error:
            raise _TimedOut("The LLM timed out.") from error
        except httpx.HTTPError as error:
            raise LlmError("The LLM could not be reached.") from error

        if response.status_code != httpx.codes.OK:
            raise LlmError(f"The LLM returned HTTP {response.status_code}.")
        try:
            choice = response.json()["choices"][0]
            content, finish_reason = choice["message"]["content"], choice["finish_reason"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise LlmError("The LLM returned an unexpected response.") from error

        if finish_reason == CUT_SHORT:
            raise _CutShort("The LLM stopped before finishing its answer.")
        if finish_reason != COMPLETE or content is None:
            raise LlmError("The LLM returned no answer.")
        try:
            return output.model_validate_json(content)
        except ValidationError as error:
            raise LlmError("The LLM answer did not match the expected format.") from error
