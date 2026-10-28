from backend.models import RunState, StageName, StageStatus
from workers.state_machine import can_enter_approval
from workers.state_machine import next_state

class Stage:
    def __init__(self, name, status, evidence=None):
        self.stage_name = name
        self.status = status
        self.evidence_reference = evidence

def test_pipeline_advances_in_order():
    state=RunState.SUBMITTED
    states=[]
    stages = [Stage(name, StageStatus.PASSED, f"evidence:{name.value}") for name in StageName]
    while state != RunState.AWAITING_APPROVAL:
        states.append(state); state=next_state(state, stages)
    assert states == [
        RunState.SUBMITTED,
        RunState.CLONING,
        RunState.ANALYZING,
        RunState.MIGRATING,
        RunState.TESTING,
        RunState.BUILDING,
        RunState.ASSESSING_RISK,
        RunState.GENERATING_REPORT,
    ]

def test_skipped_required_stage_cannot_reach_approval():
    stages = [
        Stage(name, StageStatus.SKIPPED if name == StageName.BUILD_AND_TEST else StageStatus.PASSED, f"evidence:{name.value}")
        for name in StageName
    ]
    assert not can_enter_approval(stages)
    assert next_state(RunState.GENERATING_REPORT, stages) == RunState.INCONCLUSIVE

def test_missing_required_stage_cannot_reach_approval():
    stages = [Stage(name, StageStatus.PASSED, f"evidence:{name.value}") for name in StageName if name != StageName.REPORT]
    assert not can_enter_approval(stages)
    assert next_state(RunState.GENERATING_REPORT, stages) == RunState.INCONCLUSIVE
