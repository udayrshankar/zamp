"""What each model, on its own reading, would have the rules decide. Shown to
the user beside the final decision so disagreements are visible."""

from dataclasses import replace

from app.domain.llm import ModelAnswer
from app.domain.runs import ModelVote, VerificationOutput
from app.workflow.checks import Check, CheckContext
from app.workflow.consensus import Consensus
from app.workflow.decision_policy import decide


def predict(
    answers: list[ModelAnswer[VerificationOutput]],
    consensus: Consensus,
    context: CheckContext,
    checks: list[Check],
) -> list[ModelVote]:
    readings = {reading.model: reading.output for reading in consensus.readings}
    votes = []
    for answer in answers:
        reading = readings.get(answer.model)
        if reading is None:
            votes.append(
                ModelVote(
                    model=answer.model, status="failed", seconds=answer.seconds, error=answer.error
                )
            )
            continue
        alone = replace(context, verification=reading, readings_agree=True)
        decision, reasons = decide([check.run(alone) for check in checks])
        votes.append(
            ModelVote(
                model=answer.model,
                status="answered",
                seconds=answer.seconds,
                chosen=answer.model == consensus.chosen.model,
                decision=decision,
                reasons=reasons,
                invoice_number=reading.invoice.invoice_number,
                total=reading.invoice.total,
                vendor_match=reading.vendor_match,
            )
        )
    return votes
