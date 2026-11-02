import json

import httpx
import pytest

from app.domain.errors import LlmError
from app.domain.runs import PoDetectionOutput
from app.infrastructure.nvidia_llm import NvidiaLlmClient

GOOD = json.dumps({"candidates": [{"value": "PO-1", "evidence": "PO-1"}]})


def reply(content=GOOD, finish_reason="stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]},
    )


def client_with(handler) -> NvidiaLlmClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return NvidiaLlmClient(
        http, "https://llm.test/chat", "secret-key", "test-model", retry_delay_seconds=0
    )


async def ask(client: NvidiaLlmClient) -> PoDetectionOutput:
    return await client.complete_json("system", "user", PoDetectionOutput)


async def test_sends_the_schema_and_returns_a_validated_answer():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return reply()

    answer = await ask(client_with(handler))

    assert answer.candidates[0].value == "PO-1"
    assert seen["auth"] == "Bearer secret-key"
    assert seen["body"]["model"] == "test-model"
    assert seen["body"]["temperature"] == 0
    assert "candidates" in json.dumps(seen["body"]["response_format"])


async def test_retries_once_and_recovers():
    answers = [httpx.Response(500), reply()]

    answer = await ask(client_with(lambda _: answers.pop(0)))

    assert len(answer.candidates) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429),
        httpx.Response(500),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"unexpected": True}),
        reply(content="not json"),
        reply(content='{"wrong": "shape"}'),
        reply(finish_reason="length"),
    ],
)
async def test_bad_answers_raise_after_retrying(response):
    calls = []

    def handler(_: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(response.status_code, content=response.content)

    with pytest.raises(LlmError):
        await ask(client_with(handler))

    assert len(calls) == 3


@pytest.mark.parametrize("failure", [httpx.ReadTimeout("slow"), httpx.ConnectError("down")])
async def test_network_failures_raise_llm_error(failure):
    def handler(_: httpx.Request) -> httpx.Response:
        raise failure

    with pytest.raises(LlmError):
        await ask(client_with(handler))


async def test_errors_never_contain_the_api_key():
    with pytest.raises(LlmError) as failure:
        await ask(client_with(lambda _: httpx.Response(403)))

    assert "secret-key" not in str(failure.value)
