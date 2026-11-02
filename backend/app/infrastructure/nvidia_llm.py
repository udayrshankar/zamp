import asyncio
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.domain.errors import LlmError

T = TypeVar("T", bound=BaseModel)

MAX_OUTPUT_TOKENS = 4000
COMPLETE = "stop"
ATTEMPTS = 3


class NvidiaLlmClient:
    """Chat completions with schema-constrained JSON output."""

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

    async def complete_json(self, system: str, user: str, output: type[T]) -> T:
        failure = LlmError("The LLM was not called.")
        for attempt in range(ATTEMPTS):
            if attempt:
                await asyncio.sleep(self._retry_delay_seconds * attempt)
            try:
                return await self._attempt(system, user, output)
            except LlmError as error:
                failure = error
        raise failure

    async def _attempt(self, system: str, user: str, output: type[T]) -> T:
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
                    "max_tokens": MAX_OUTPUT_TOKENS,
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
            raise LlmError("The LLM timed out.") from error
        except httpx.HTTPError as error:
            raise LlmError("The LLM could not be reached.") from error

        if response.status_code != httpx.codes.OK:
            raise LlmError(f"The LLM returned HTTP {response.status_code}.")
        try:
            choice = response.json()["choices"][0]
            content, finish_reason = choice["message"]["content"], choice["finish_reason"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise LlmError("The LLM returned an unexpected response.") from error

        if finish_reason != COMPLETE:
            raise LlmError("The LLM stopped before finishing its answer.")
        try:
            return output.model_validate_json(content)
        except ValidationError as error:
            raise LlmError("The LLM answer did not match the expected format.") from error
