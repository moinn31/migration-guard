from backend.migration_assistance import build_java17_plan, explain_proposal


def test_java17_plan_is_reviewable_and_reversible():
    proposals = build_java17_plan({"language": "java", "build_system": "maven"})
    assert [proposal.code for proposal in proposals] == ["JAVA_TARGET_17", "JUNIT5_COMPATIBILITY_REVIEW"]
    assert all(proposal.advisory and proposal.reversible for proposal in proposals)
    assert "advisory" in explain_proposal(proposals[0])


def test_non_java_project_has_no_migration_plan():
    assert build_java17_plan({"language": "python", "build_system": "unknown"}) == []
