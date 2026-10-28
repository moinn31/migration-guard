from backend.models import REQUIRED_STAGES, RunState, StageStatus

ORDER = [
    RunState.SUBMITTED,
    RunState.CLONING,
    RunState.ANALYZING,
    RunState.MIGRATING,
    RunState.TESTING,
    RunState.BUILDING,
    RunState.ASSESSING_RISK,
    RunState.GENERATING_REPORT,
    RunState.AWAITING_APPROVAL,
]

def can_enter_approval(stages) -> bool:
    by_name = {getattr(stage.stage_name, "value", stage.stage_name): stage for stage in stages}
    return all(
        (stage := by_name.get(getattr(required, "value", required))) is not None
        and getattr(stage.status, "value", stage.status) == StageStatus.PASSED.value
        and bool(stage.evidence_reference)
        for required in REQUIRED_STAGES
    )

def next_state(state: RunState, stages=None) -> RunState:
    if state == RunState.GENERATING_REPORT:
        if stages is None or not can_enter_approval(stages):
            return RunState.INCONCLUSIVE
        return RunState.AWAITING_APPROVAL
    if state in {RunState.AWAITING_APPROVAL, RunState.FAILED, RunState.INCONCLUSIVE}:
        return state
    i = ORDER.index(state)
    return ORDER[min(i + 1, len(ORDER) - 1)]
