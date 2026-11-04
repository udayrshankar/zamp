"""The model chain and panel: graceful degradation from three models to none."""

import asyncio

import pytest
from pydantic import BaseModel

from app.domain.errors import LlmError
from app.domain.llm import AnswerStatus, ModelState
from app.infrastructure.llm_chain import FallbackLlmClient
from app.infrastructure.llm_panel import ParallelLlmPanel
from app.infrastructure.model_health import ModelHealth
from app.infrastructure.model_probe import ModelProber


class Answer(BaseModel):
    text: str


class ScriptedModel:
    """A model that answers with its own name, or fails, as scripted."""

    def __init__(self, model: str, fails: bool = False) -> None:
        self.model = model
        self.fails = fails
        self.calls = 0

    async def complete_json(self, system: str, user: str, output: type) -> Answer:
        self.calls += 1
        if self.fails:
            raise LlmError("The LLM timed out.")
        return Answer(text=self.model)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def models(*specs: tuple[str, bool]) -> list[ScriptedModel]:
    return [ScriptedModel(name, fails) for name, fails in specs]


def health_for(clients, clock=None) -> ModelHealth:
    return ModelHealth([c.model for c in clients], cooldown_seconds=60, clock=clock or Clock())


class TestModelHealth:
    def test_two_failures_in_a_row_cool_a_model_down_until_the_cooldown_ends(self):
        clock = Clock()
        health = ModelHealth(["a", "b"], cooldown_seconds=60, clock=clock)

        health.record_failure("a", 1.0, "timed out")
        assert health.preferred() == ["b", "a"]
        health.record_failure("a", 1.0, "timed out")
        assert health.preferred() == ["b"]

        clock.now = 61
        # Back in use, but behind healthy models until it answers again.
        assert health.preferred() == ["b", "a"]

    def test_a_success_resets_the_count(self):
        health = ModelHealth(["a"])

        health.record_failure("a", 1.0, "x")
        health.record_success("a", 0.5)
        health.record_failure("a", 1.0, "x")

        assert health.preferred() == ["a"]

    def test_when_every_model_is_cooling_down_all_are_still_tried(self):
        health = ModelHealth(["a", "b"])
        for model in ("a", "b"):
            health.record_failure(model, 1.0, "x")
            health.record_failure(model, 1.0, "x")

        assert health.preferred() == ["a", "b"]

    def test_status_reports_each_model(self):
        health = ModelHealth(["a", "b", "c"])
        health.record_success("a", 0.4)
        health.record_failure("b", 9.0, "timed out")
        health.record_failure("b", 9.0, "timed out")

        states = {status.name: status.state for status in health.status()}

        assert states == {"a": ModelState.OK, "b": ModelState.COOLING_DOWN, "c": ModelState.UNKNOWN}


class TestFallbackChain:
    async def test_the_first_healthy_model_answers(self):
        clients = models(("a", False), ("b", False))

        chain = FallbackLlmClient(clients, health_for(clients))

        answer = await chain.complete_json("s", "u", Answer)

        assert answer.text == "a"
        assert clients[1].calls == 0

    async def test_a_failing_model_hands_over_to_the_next(self):
        clients = models(("down", True), ("up", False))

        chain = FallbackLlmClient(clients, health_for(clients))

        answer = await chain.complete_json("s", "u", Answer)

        assert answer.text == "up"

    async def test_a_model_that_failed_is_not_tried_first_again(self):
        clients = models(("down", True), ("up", False))
        chain = FallbackLlmClient(clients, health_for(clients))

        for _ in range(3):
            await chain.complete_json("s", "u", Answer)

        assert clients[0].calls == 1

    async def test_every_model_failing_raises_one_error_naming_them(self):
        clients = models(("a", True), ("b", True))

        with pytest.raises(LlmError) as failure:
            await FallbackLlmClient(clients, health_for(clients)).complete_json("s", "u", Answer)

        assert "a:" in failure.value.message and "b:" in failure.value.message


class TestPanel:
    async def ask(self, clients, size=3):
        return await ParallelLlmPanel(clients, health_for(clients), size).ask_all("s", "u", Answer)

    async def test_three_healthy_models_all_answer(self):
        answers = await self.ask(models(("a", False), ("b", False), ("c", False), ("d", False)))

        assert [a.model for a in answers if a.answered] == ["a", "b", "c"]

    async def test_a_failed_model_is_replaced_from_the_rest_of_the_chain(self):
        answers = await self.ask(models(("a", False), ("down", True), ("c", False), ("d", False)))

        assert [a.model for a in answers if a.answered] == ["a", "c", "d"]
        assert [a.model for a in answers if a.status is AnswerStatus.FAILED] == ["down"]

    async def test_with_only_two_models_up_the_panel_still_answers(self):
        answers = await self.ask(models(("a", False), ("b", True), ("c", False)))

        assert sum(a.answered for a in answers) == 2

    async def test_with_every_model_down_it_reports_failures_and_never_raises(self):
        answers = await self.ask(models(("a", True), ("b", True)))

        assert answers and not any(a.answered for a in answers)
        assert all(a.error == "The LLM timed out." for a in answers)

    async def test_no_new_round_starts_after_the_deadline(self):
        clock = Clock()

        class SlowFailure(ScriptedModel):
            async def complete_json(self, system, user, output):
                clock.now += 50
                return await super().complete_json(system, user, output)

        clients = [SlowFailure("a", False), SlowFailure("b", True), ScriptedModel("c")]
        panel = ParallelLlmPanel(
            clients, health_for(clients), size=2, deadline_seconds=45, clock=clock
        )

        answers = await panel.ask_all("s", "u", Answer)

        assert [a.model for a in answers] == ["a", "b"]
        assert clients[2].calls == 0


class TestProber:
    async def test_checks_every_model_and_reports_each_state(self):
        clients = models(("up", False), ("down", True))
        health = health_for(clients)

        statuses = await ModelProber(clients, health).check()

        states = {status.name: status.state for status in statuses}
        assert states == {"up": ModelState.OK, "down": ModelState.COOLING_DOWN}
        assert all(client.calls == 1 for client in clients)

    async def test_a_model_that_fails_the_check_is_skipped_by_the_next_invoice(self):
        clients = models(("up", False), ("down", True))
        health = health_for(clients)

        await ModelProber(clients, health).check()

        assert health.preferred() == ["up"]

    async def test_a_model_that_answers_a_later_check_is_back_in_use(self):
        clock = Clock()
        clients = models(("a", True))
        health = health_for(clients, clock)
        prober = ModelProber(clients, health, min_interval_seconds=60, clock=clock)
        await prober.check()

        clients[0].fails = False
        clock.now = 61
        [status] = await prober.check()

        assert status.state is ModelState.OK

    async def test_a_model_that_hangs_is_reported_after_the_timeout(self):
        class Hanging(ScriptedModel):
            async def complete_json(self, system, user, output):
                await asyncio.sleep(5)

        clients = [Hanging("slow")]

        [status] = await ModelProber(clients, health_for(clients), timeout_seconds=0.05).check()

        assert status.state is ModelState.COOLING_DOWN
        assert "No answer within" in status.last_error

    async def test_checks_close_together_reuse_the_last_result(self):
        clock = Clock()
        clients = models(("a", False))
        prober = ModelProber(clients, health_for(clients), min_interval_seconds=60, clock=clock)

        await prober.check()
        await prober.check()
        clock.now = 61
        await prober.check()

        assert clients[0].calls == 2

    def test_a_model_whose_last_call_failed_is_tried_after_the_healthy_ones(self):
        health = ModelHealth(["a", "b", "c"])
        health.record_failure("a", 1.0, "timed out")

        assert health.preferred() == ["b", "c", "a"]
