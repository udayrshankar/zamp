from app.domain.runs import CheckOutcome, CheckResult, Decision


def decide(checks: list[CheckResult]) -> tuple[Decision, list[str]]:
    """The strictest check wins, and every reason comes from a check result."""
    rejected = [check.message for check in checks if check.outcome is CheckOutcome.REJECT]
    flagged = [check.message for check in checks if check.outcome is CheckOutcome.REVIEW]
    if rejected:
        return Decision.REJECT, rejected + flagged
    if flagged:
        return Decision.REVIEW, flagged
    return Decision.ACCEPT, ["Every check passed."]
