from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


VERIFIED_CAVEAT = "Passing checks do not prove behavioral equivalence."


@dataclass(frozen=True)
class VerdictReason:
    rule_id: str
    severity: str
    evidence_reference: str
    message: str


@dataclass(frozen=True)
class VerdictResult:
    verdict: str
    reasons: tuple[VerdictReason, ...]
    caveat: str = VERIFIED_CAVEAT


def _reason(rule_id: str, severity: str, reference: str, message: str) -> VerdictReason:
    return VerdictReason(rule_id, severity, reference, message)

def _value(value: object) -> str:
    return str(getattr(value, "value", value))


def compute_verdict(
    run_stages: Iterable[object],
    analysis_findings: Iterable[object],
    build_runs: Iterable[object],
    test_results: Iterable[object],
    test_integrity_results: Iterable[object],
    migration_changes: Iterable[object],
    dependency_data: object = None,
    *,
    target_major: int = 61,
    docker_execution_enabled: bool = True,
    baseline_test_count: int | None = None,
    migrated_test_count: int | None = None,
    migration_applied: bool | None = None,
    coverage_available: bool = True,
) -> VerdictResult:
    stages = list(run_stages)
    findings = list(analysis_findings)
    builds = list(build_runs)
    results = list(test_results)
    integrity = list(test_integrity_results)
    changes = list(migration_changes)
    reasons: list[VerdictReason] = []

    def add(rule: str, severity: str, ref: str, message: str) -> None:
        reasons.append(_reason(rule, severity, ref, message))

    if any(_value(getattr(stage, "status", "")).upper() == "FAILED" for stage in stages):
        add("REQUIRED_STAGE_FAILED", "critical", "run_stages", "A required stage failed.")
    if any(
        _value(getattr(build, "variant", "migrated")) == "migrated"
        and _value(getattr(build, "status", "")).upper() in {"FAILED", "ERROR", "TIMEOUT"}
        for build in builds
    ):
        add("MIGRATED_BUILD_FAILED", "critical", "build_runs", "The migrated build failed, errored, or timed out.")
    baseline = {getattr(item, "test_name", ""): item for item in results if _value(getattr(item, "variant", "migrated")) == "baseline"}
    migrated = {getattr(item, "test_name", ""): item for item in results if _value(getattr(item, "variant", "migrated")) == "migrated"}
    for name, old in baseline.items():
        new = migrated.get(name)
        if new and _value(getattr(old, "status", "")).lower() == "pass" and _value(getattr(new, "status", "")).lower() in {"fail", "error"}:
            add("BASELINE_PASS_MIGRATED_FAIL", "critical", f"test_result:{name}", f"Test {name} passed in baseline and failed in migrated.")
    for item in integrity:
        code = _value(getattr(item, "code", "")).upper()
        if code in {"TEST_FILE_DELETED", "TESTS_DELETED", "TEST_DISABLED"}:
            add(code, "critical", f"test_integrity:{getattr(item, 'id', getattr(item, 'path', 'unknown'))}", getattr(item, "message", code))
        if code in {"ASSERTIONS_WEAKENED", "ASSERTION_ALWAYS_TRUE"} and _value(getattr(item, "confidence", "")).lower() == "high":
            add(code, "critical", f"test_integrity:{getattr(item, 'id', getattr(item, 'path', 'unknown'))}", getattr(item, "message", code))
    for item in integrity:
        if _value(getattr(item, "code", "")).upper() == "CLASS_MAJOR_VERSION":
            evidence = str(getattr(item, "evidence", ""))
            migrated_evidence = evidence.split("migrated=", 1)[-1]
            if "61" not in migrated_evidence:
                add("CLASS_MAJOR_VERSION_NOT_61", "critical", f"test_integrity:{getattr(item, 'id', 'class-major')}", "Java 17 output did not have class major version 61.")
    if baseline_test_count is not None and migrated_test_count is not None and migrated_test_count < baseline_test_count:
        add("TEST_COUNT_DECREASED", "critical", "test_count", "Migrated test count decreased.")

    if any(_value(getattr(stage, "status", "")).upper() == "SKIPPED" for stage in stages):
        add("REQUIRED_STAGE_SKIPPED", "high", "run_stages", "A required stage was skipped.")
    required_names = {"analysis", "test_integrity", "build_and_test", "risk_assessment", "report", "verdict"}
    if not required_names.issubset({_value(getattr(stage, "stage_name", "")) for stage in stages}):
        add("REQUIRED_STAGE_MISSING", "high", "run_stages", "A required stage is missing.")
    if not docker_execution_enabled:
        add("DOCKER_EXECUTION_DISABLED", "high", "settings:migrationguard_enable_execution", "Docker execution is disabled.")
    if migration_applied is False or (migration_applied is None and not any(bool(getattr(change, "applied", False)) for change in changes)):
        add("NO_MIGRATION_APPLIED", "high", "migration_changes", "No migration change was applied; original and migrated trees are not distinguishable.")
    if not baseline:
        add("BASELINE_ZERO_TESTS", "high", "test_results", "No baseline tests were recorded.")
    if any(_value(getattr(build, "variant", "migrated")) == "baseline" and _value(getattr(build, "status", "")).upper() in {"FAILED", "ERROR", "TIMEOUT"} for build in builds):
        add("BASELINE_BUILD_FAILED", "high", "build_runs", "The baseline build failed.")

    for item in integrity:
        code = _value(getattr(item, "code", "")).upper()
        confidence = str(getattr(item, "confidence", "")).lower()
        if confidence in {"medium", "low"}:
            add("INTEGRITY_NEEDS_REVIEW", "medium", f"test_integrity:{getattr(item, 'id', 'unknown')}", getattr(item, "message", code))
    if any(bool(getattr(item, "flaky", False)) for item in results):
        add("FLAKY_TEST", "medium", "test_results", "A test was marked flaky after reruns.")
    if any(_value(getattr(item, "code", "")).upper() in {"REMOVED_JDK_API", "INTERNAL_JDK_API"} for item in findings):
        add("REMAINING_REMOVED_JDK_API", "medium", "analysis_findings", "Removed or internal JDK API findings remain.")
    if isinstance(dependency_data, dict) and dependency_data.get("unresolved_conflicts"):
        add("UNRESOLVED_DEPENDENCY_CONFLICT", "medium", "dependencies", "Dependency conflicts remain unresolved.")
    if not coverage_available:
        add("COVERAGE_UNAVAILABLE", "low", "coverage", "Coverage evidence is unavailable.")

    if any(reason.severity == "critical" or reason.rule_id in {
        "REQUIRED_STAGE_FAILED", "MIGRATED_BUILD_FAILED", "BASELINE_PASS_MIGRATED_FAIL",
        "TEST_FILE_DELETED", "TESTS_DELETED", "TEST_DISABLED", "ASSERTIONS_WEAKENED",
        "ASSERTION_ALWAYS_TRUE", "CLASS_MAJOR_VERSION_NOT_61", "TEST_COUNT_DECREASED",
    } for reason in reasons):
        verdict = "UNSAFE"
    elif any(reason.rule_id in {
        "REQUIRED_STAGE_SKIPPED", "REQUIRED_STAGE_MISSING", "DOCKER_EXECUTION_DISABLED",
        "NO_MIGRATION_APPLIED", "BASELINE_ZERO_TESTS", "BASELINE_BUILD_FAILED",
    } for reason in reasons):
        verdict = "INCONCLUSIVE"
    elif reasons:
        verdict = "NEEDS_REVIEW"
    else:
        verdict = "VERIFIED_BY_CHECKS"
    return VerdictResult(verdict, tuple(reasons))
