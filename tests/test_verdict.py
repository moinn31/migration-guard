from types import SimpleNamespace

import pytest

from backend.verdict import compute_verdict
from backend.models import StageName, StageStatus


def stage(name=StageName.ANALYSIS, status=StageStatus.PASSED, evidence="evidence"):
    return SimpleNamespace(stage_name=name, status=status, evidence_reference=evidence)


def complete_stages():
    return [stage(name) for name in StageName]


def test_verified_requires_applied_migration():
    result = compute_verdict(complete_stages(), [], [], [], [], [])
    assert result.verdict == "INCONCLUSIVE"
    assert result.reasons[0].rule_id == "NO_MIGRATION_APPLIED"


@pytest.mark.parametrize(
    ("builds", "integrity", "changes", "expected"),
    [
        ([SimpleNamespace(variant="migrated", status="FAILED")], [], [SimpleNamespace(applied=True)], "UNSAFE"),
        (
            [],
            [SimpleNamespace(code="TEST_FILE_DELETED", confidence="high", message="deleted")],
            [SimpleNamespace(applied=True)],
            "UNSAFE",
        ),
        (
            [],
            [SimpleNamespace(code="ASSERTIONS_WEAKENED", confidence="high", message="weakened")],
            [SimpleNamespace(applied=True)],
            "UNSAFE",
        ),
        (
            [],
            [],
            [SimpleNamespace(applied=True)],
            "INCONCLUSIVE",
        ),
    ],
)
def test_verdict_rule_paths(builds, integrity, changes, expected):
    result = compute_verdict(
        complete_stages(),
        [],
        builds,
        [],
        integrity,
        changes,
        baseline_test_count=1,
        migrated_test_count=1,
    )
    assert result.verdict == expected


def test_baseline_pass_to_migrated_fail_is_unsafe():
    results = [
        SimpleNamespace(variant="baseline", test_name="A.test", status="pass"),
        SimpleNamespace(variant="migrated", test_name="A.test", status="fail"),
    ]
    result = compute_verdict(
        complete_stages(), [], [], results, [], [SimpleNamespace(applied=True)]
    )
    assert result.verdict == "UNSAFE"
    assert any(reason.rule_id == "BASELINE_PASS_MIGRATED_FAIL" for reason in result.reasons)


def test_skipped_stage_is_inconclusive_not_verified():
    stages = complete_stages()
    stages[2] = stage(StageName.BUILD_AND_TEST, StageStatus.SKIPPED, "skipped")
    result = compute_verdict(stages, [], [], [], [], [SimpleNamespace(applied=True)])
    assert result.verdict == "INCONCLUSIVE"


def test_medium_integrity_finding_needs_review():
    result = compute_verdict(
        complete_stages(),
        [],
        [],
        [SimpleNamespace(variant="baseline", test_name="A.test", status="pass")],
        [SimpleNamespace(code="REVIEW", confidence="medium", message="review")],
        [SimpleNamespace(applied=True)],
    )
    assert result.verdict == "NEEDS_REVIEW"


def test_unsafe_precedes_inconclusive_and_review():
    result = compute_verdict(
        complete_stages(),
        [],
        [SimpleNamespace(variant="migrated", status="FAILED")],
        [],
        [SimpleNamespace(code="REVIEW", confidence="medium", message="review")],
        [],
    )
    assert result.verdict == "UNSAFE"


@pytest.mark.parametrize(
    ("kwargs", "expected", "rule"),
    [
        ({"migrated_test_count": 0, "baseline_test_count": 1}, "UNSAFE", "TEST_COUNT_DECREASED"),
        (
            {"integrity": [SimpleNamespace(code="CLASS_MAJOR_VERSION", evidence="migrated={52}")],
             "changes": [SimpleNamespace(applied=True)]},
            "UNSAFE",
            "CLASS_MAJOR_VERSION_NOT_61",
        ),
        (
            {"builds": [SimpleNamespace(variant="baseline", status="FAILED")],
             "changes": [SimpleNamespace(applied=True)]},
            "INCONCLUSIVE",
            "BASELINE_BUILD_FAILED",
        ),
        (
            {"docker_execution_enabled": False, "changes": [SimpleNamespace(applied=True)]},
            "INCONCLUSIVE",
            "DOCKER_EXECUTION_DISABLED",
        ),
        (
            {"results": [], "changes": [SimpleNamespace(applied=True)]},
            "INCONCLUSIVE",
            "BASELINE_ZERO_TESTS",
        ),
        (
            {"integrity": [SimpleNamespace(code="REVIEW", confidence="low", message="review")],
             "changes": [SimpleNamespace(applied=True)]},
            "NEEDS_REVIEW",
            "INTEGRITY_NEEDS_REVIEW",
        ),
        (
            {"results": [SimpleNamespace(variant="baseline", test_name="A", status="pass", flaky=True)],
             "changes": [SimpleNamespace(applied=True)]},
            "NEEDS_REVIEW",
            "FLAKY_TEST",
        ),
        (
            {"findings": [SimpleNamespace(code="REMOVED_JDK_API")],
             "changes": [SimpleNamespace(applied=True)]},
            "NEEDS_REVIEW",
            "REMAINING_REMOVED_JDK_API",
        ),
        (
            {"dependency_data": {"unresolved_conflicts": ["x"]},
             "changes": [SimpleNamespace(applied=True)]},
            "NEEDS_REVIEW",
            "UNRESOLVED_DEPENDENCY_CONFLICT",
        ),
        (
            {"coverage_available": False, "results": [SimpleNamespace(variant="baseline", test_name="A", status="pass")],
             "changes": [SimpleNamespace(applied=True)]},
            "NEEDS_REVIEW",
            "COVERAGE_UNAVAILABLE",
        ),
    ],
)
def test_remaining_verdict_rules(kwargs, expected, rule):
    kwargs = {
        "run_stages": complete_stages(),
        "analysis_findings": kwargs.pop("findings", []),
        "build_runs": kwargs.pop("builds", []),
        "test_results": kwargs.pop(
            "results",
            [SimpleNamespace(variant="baseline", test_name="A", status="pass")],
        ),
        "test_integrity_results": kwargs.pop("integrity", []),
        "migration_changes": kwargs.pop("changes", []),
        **kwargs,
    }
    result = compute_verdict(**kwargs)
    assert result.verdict == expected
    assert any(reason.rule_id == rule for reason in result.reasons)


def test_required_stage_failed_is_unsafe_and_missing_is_inconclusive():
    failed = complete_stages()
    failed[0] = stage(StageName.ANALYSIS, StageStatus.FAILED, "error")
    result = compute_verdict(failed, [], [], [], [], [SimpleNamespace(applied=True)])
    assert result.verdict == "UNSAFE"

    missing = complete_stages()[:-1]
    result = compute_verdict(missing, [], [], [], [], [SimpleNamespace(applied=True)])
    assert result.verdict == "INCONCLUSIVE"
