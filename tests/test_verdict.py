from types import SimpleNamespace

import pytest

from backend.verdict import compute_verdict
from backend.models import StageName, StageStatus


def stage(name=StageName.ANALYSIS, status=StageStatus.PASSED, evidence="evidence"):
    return SimpleNamespace(stage_name=name, status=status, evidence_reference=evidence)


def complete_stages():
    return [stage(name) for name in StageName]

def healthy_builds():
    return [SimpleNamespace(variant=variant, status='PASSED', artifacts={'class_major_versions': {'Order.class': major}})
            for variant, major in [('baseline', 52), ('migrated', 61)]]

def healthy_results(name='A'):
    return [SimpleNamespace(variant=variant, test_name=name, status='pass') for variant in ('baseline', 'migrated')]


def test_verified_requires_applied_migration():
    result = compute_verdict(complete_stages(), [], [], [], [], [])
    assert result.verdict == "INCONCLUSIVE"
    assert any(reason.rule_id == 'NO_MIGRATION_APPLIED' for reason in result.reasons)


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
        healthy_builds(),
        healthy_results('A.test'),
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
            {"results": [SimpleNamespace(variant="baseline", test_name="A", status="pass", flaky=True), SimpleNamespace(variant='migrated', test_name='A', status='pass')],
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
            {"coverage_available": False, "results": healthy_results(),
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
        "build_runs": kwargs.pop("builds", healthy_builds()),
        "test_results": kwargs.pop(
            "results",
            healthy_results(),
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


def test_passing_build_alone_cannot_verify_a_migration():
    result = compute_verdict(complete_stages(), [], [], healthy_results(), [], [SimpleNamespace(applied=True)])
    assert result.verdict == 'INCONCLUSIVE'
    assert any(reason.rule_id == 'BUILD_EVIDENCE_MISSING' for reason in result.reasons)

@pytest.mark.parametrize('status,evidence', [(StageStatus.RUNNING, 'evidence'), (StageStatus.PASSED, None)])
def test_incomplete_stage_cannot_verify(status, evidence):
    stages = complete_stages()
    stages[0] = stage(StageName.ANALYSIS, status, evidence)
    assert compute_verdict(stages, [], healthy_builds(), healthy_results(), [], [SimpleNamespace(applied=True)]).verdict == 'INCONCLUSIVE'

def test_mixed_bytecode_versions_cannot_pass_by_containing_61():
    builds = healthy_builds()
    builds[1].artifacts['class_major_versions']['Legacy.class'] = 52
    assert compute_verdict(complete_stages(), [], builds, healthy_results(), [], [SimpleNamespace(applied=True)]).verdict == 'UNSAFE'

def test_full_evidence_can_be_verified_and_missing_coverage_is_disclosed():
    args = (complete_stages(), [], healthy_builds(), healthy_results(), [], [SimpleNamespace(applied=True)])
    assert compute_verdict(*args, coverage_available=True).verdict == 'VERIFIED_BY_CHECKS'
    result = compute_verdict(*args)
    assert result.verdict == 'NEEDS_REVIEW'
    assert any(reason.rule_id == 'COVERAGE_UNAVAILABLE' for reason in result.reasons)
