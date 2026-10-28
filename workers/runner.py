from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import select

from backend.db import SessionLocal
from backend.build_executor import compare_test_results, rerun_failed_tests, run_maven_build
from backend.config import settings
from backend.ingestion import copy_for_work, create_snapshot_and_findings
from backend.migration_engine import migrate_snapshot
from backend.models import AnalysisFinding, BuildRun, MigrationChange, MigrationRun, Project, Report, RepoSnapshot, RiskAssessment, RunStage, RunState, StageName, StageStatus, TestIntegrityResult, TestResult
from backend.risk_assessment import assess_run
from backend.test_integrity import compare_snapshot_trees
from backend.verdict import compute_verdict
from backend.reporting import build_evidence_report
from .state_machine import can_enter_approval

MAX_RETRIES = 3
STAGE_STATES = {
    StageName.ANALYSIS: RunState.ANALYZING,
    StageName.MIGRATING: RunState.MIGRATING,
    StageName.TEST_INTEGRITY: RunState.TESTING,
    StageName.BUILD_AND_TEST: RunState.BUILDING,
    StageName.RISK_ASSESSMENT: RunState.ASSESSING_RISK,
    StageName.REPORT: RunState.GENERATING_REPORT,
    StageName.VERDICT: RunState.GENERATING_REPORT,
}

def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

async def get_or_create_stage(db, run_id: str, name: StageName) -> RunStage:
    stage = await db.scalar(select(RunStage).where(RunStage.run_id == run_id, RunStage.stage_name == name))
    if stage is None:
        stage = RunStage(run_id=run_id, stage_name=name, status=StageStatus.PENDING)
        db.add(stage)
        await db.flush()
    return stage

async def execute_stage(db, run: MigrationRun, stage: RunStage, zip_path: str | None = None) -> None:
    if stage.status == StageStatus.PASSED and stage.evidence_reference:
        return
    stage.status = StageStatus.RUNNING
    stage.started_at = stage.started_at or utcnow()
    stage.finished_at = None
    stage.error = None
    await db.flush()
    if stage.stage_name == StageName.ANALYSIS:
        project = await db.scalar(select(Project).where(Project.id == run.project_id))
        if project is None:
            raise RuntimeError("Run project is missing.")
        snapshot = await create_snapshot_and_findings(db, run.project_id, run.id, project.repository_url, zip_path)
        stage.evidence_reference = f"repo_snapshot:{snapshot.id}"
    elif stage.stage_name == StageName.MIGRATING:
        snapshot = await db.scalar(select(RepoSnapshot).where(RepoSnapshot.run_id == run.id))
        if snapshot is None:
            raise RuntimeError("Snapshot evidence is missing.")
        if snapshot.snapshot_metadata.get("migrated_path"):
            stage.evidence_reference = f"migration:{run.id}"
        else:
            working, hunks, rewrite_output = migrate_snapshot(
                snapshot.snapshot_path,
                snapshot.content_hash,
                dry_run=settings.migration_dry_run,
            )
            snapshot.snapshot_metadata = {
                **snapshot.snapshot_metadata,
                "migrated_path": str(working),
                "openrewrite_output": rewrite_output[-4000:],
                "migration_dry_run": settings.migration_dry_run,
            }
            for hunk in hunks:
                existing = await db.scalar(select(MigrationChange).where(
                    MigrationChange.run_id == run.id,
                    MigrationChange.path == hunk.path,
                    MigrationChange.rule_id == hunk.rule_id,
                ))
                if existing:
                    continue
                db.add(MigrationChange(
                    run_id=run.id, path=hunk.path, diff=hunk.diff, source=hunk.source,
                    rule_id=hunk.rule_id, title=hunk.rule_id, rationale=hunk.reason,
                    before_content=hunk.before, after_content=hunk.after,
                    status="proposed" if hunk.protected else ("proposed" if settings.migration_dry_run else "applied"),
                    applied=not hunk.protected and not settings.migration_dry_run,
                    protected=hunk.protected, unnecessary_change=hunk.unnecessary_change,
                    changed_lines_ratio=hunk.changed_lines_ratio,
                ))
            stage.evidence_reference = f"migration:{run.id}"
    elif stage.stage_name == StageName.TEST_INTEGRITY:
        snapshot = await db.scalar(select(RepoSnapshot).where(RepoSnapshot.run_id == run.id))
        if snapshot is None:
            raise RuntimeError("Snapshot evidence is missing.")
        migrated = snapshot.snapshot_metadata.get("migrated_path") or copy_for_work(snapshot.snapshot_path)
        findings = compare_snapshot_trees(snapshot.snapshot_path, migrated)
        for finding in findings:
            db.add(TestIntegrityResult(
                run_id=run.id, code=finding.code, severity=finding.severity, path=finding.path,
                message=finding.message, confidence=finding.confidence, evidence=finding.evidence, note=finding.note,
            ))
        stage.evidence_reference = f"test_integrity:{run.id}"
    elif stage.stage_name == StageName.BUILD_AND_TEST:
        snapshot = await db.scalar(select(RepoSnapshot).where(RepoSnapshot.run_id == run.id))
        if snapshot is None:
            raise RuntimeError("Snapshot evidence is missing.")
        migrated = snapshot.snapshot_metadata.get("migrated_path") or copy_for_work(snapshot.snapshot_path)
        baseline = await run_maven_build(
            snapshot.snapshot_path, java_version=8,
            docker_enabled=settings.migrationguard_enable_execution,
            maven_mirror=settings.maven_mirror,
        )
        migrated_result = await run_maven_build(
            migrated, java_version=17,
            docker_enabled=settings.migrationguard_enable_execution,
            maven_mirror=settings.maven_mirror,
        )
        if baseline.status == "SKIPPED" or migrated_result.status == "SKIPPED":
            stage.status = StageStatus.SKIPPED
            stage.error = "Docker build execution is disabled."
        else:
            baseline_flaky = await rerun_failed_tests(
                snapshot.snapshot_path, list(baseline.tests), java_version=8,
                docker_enabled=settings.migrationguard_enable_execution, maven_mirror=settings.maven_mirror,
            )
            migrated_flaky = await rerun_failed_tests(
                migrated, list(migrated_result.tests), java_version=17,
                docker_enabled=settings.migrationguard_enable_execution, maven_mirror=settings.maven_mirror,
            )
            for variant, result in (("baseline", baseline), ("migrated", migrated_result)):
                db.add(BuildRun(run_id=run.id, variant=variant, status=result.status, exit_code=result.exit_code, logs=result.logs, artifacts=result.artifacts))
                for test in result.tests:
                    db.add(TestResult(
                        run_id=run.id, variant=variant, test_name=test.name, status=test.status,
                        duration_seconds=test.duration_seconds, message=test.message,
                        flaky=test.name in (baseline_flaky | migrated_flaky),
                    ))
            differences = compare_test_results(list(baseline.tests), list(migrated_result.tests))
            stage.evidence_reference = f"build_runs:{run.id}"
            baseline_versions = baseline.artifacts.get("class_major_versions", {})
            migrated_versions = migrated_result.artifacts.get("class_major_versions", {})
            db.add(TestIntegrityResult(
                run_id=run.id, code="CLASS_MAJOR_VERSION", severity="info", path="target/classes",
                message=f"Baseline class major versions: {baseline_versions}; migrated class major versions: {migrated_versions}.",
                confidence="high", evidence=f"baseline={baseline_versions}; migrated={migrated_versions}",
            ))
            db.add(TestIntegrityResult(
                run_id=run.id, code="TEST_COUNT_PRESERVED", severity="info", path="target/surefire-reports",
                message=f"Baseline test count {len(baseline.tests)}; migrated test count {len(migrated_result.tests)}.",
                confidence="high", evidence=f"baseline={len(baseline.tests)}; migrated={len(migrated_result.tests)}",
            ))
            db.add(TestIntegrityResult(
                run_id=run.id, code="TEST_METHOD_PRESERVATION", severity="info", path="target/surefire-reports",
                message=f"Compared {len(set(item.name for item in baseline.tests) & set(item.name for item in migrated_result.tests))} common test methods.",
                confidence="high", evidence=str(differences),
            ))
            if baseline.status != "PASSED" or migrated_result.status != "PASSED" or differences:
                stage.status = StageStatus.FAILED
                stage.error = str(differences or "Baseline or migrated Maven build failed.")
    elif stage.stage_name == StageName.RISK_ASSESSMENT:
        score, rationale = await assess_run(db, run.id)
        record = RiskAssessment(run_id=run.id, score=score, rationale=rationale)
        db.add(record)
        await db.flush()
        stage.evidence_reference = f"risk_assessment:{record.id}"
    elif stage.stage_name == StageName.REPORT:
        assessment = await db.scalar(select(RiskAssessment).where(RiskAssessment.run_id == run.id).order_by(RiskAssessment.id.desc()))
        if assessment is None:
            raise RuntimeError("Risk assessment evidence is missing.")
        report = Report(run_id=run.id, content={"risk_score": assessment.score, "rationale": assessment.rationale, "status": "INCONCLUSIVE"})
        db.add(report)
        await db.flush()
        stage.evidence_reference = f"report:{report.id}"
    elif stage.stage_name == StageName.VERDICT:
        stages = list((await db.scalars(select(RunStage).where(RunStage.run_id == run.id))).all())
        findings = list((await db.scalars(select(AnalysisFinding).where(AnalysisFinding.run_id == run.id))).all())
        builds = list((await db.scalars(select(BuildRun).where(BuildRun.run_id == run.id))).all())
        results = list((await db.scalars(select(TestResult).where(TestResult.run_id == run.id))).all())
        integrity = list((await db.scalars(select(TestIntegrityResult).where(TestIntegrityResult.run_id == run.id))).all())
        changes = list((await db.scalars(select(MigrationChange).where(MigrationChange.run_id == run.id))).all())
        result = compute_verdict(
            stages, findings, builds, results, integrity, changes,
            docker_execution_enabled=settings.migrationguard_enable_execution,
        )
        run.verdict = result.verdict
        stage.evidence_reference = f"verdict:{run.id}"
        report = await db.scalar(select(Report).where(Report.run_id == run.id).order_by(Report.id.desc()))
        content = await build_evidence_report(db, run, result)
        if report is None:
            report = Report(run_id=run.id, content=content)
            db.add(report)
        else:
            report.content = content
        await db.flush()
        if result.verdict in {"UNSAFE", "INCONCLUSIVE"}:
            run.state = RunState.INCONCLUSIVE
    if stage.status == StageStatus.RUNNING:
        stage.status = StageStatus.PASSED
    stage.finished_at = utcnow()

async def advance_run(run_id: str, zip_path: str | None = None) -> None:
    async with SessionLocal() as db:
        run = await db.scalar(select(MigrationRun).where(MigrationRun.id == run_id))
        if run is None or run.state.value in {"AWAITING_APPROVAL", "FAILED", "INCONCLUSIVE"}:
            return
        for name in StageName:
            stage = await get_or_create_stage(db, run.id, name)
            if stage.status == StageStatus.PASSED and stage.evidence_reference:
                continue
            run.state = STAGE_STATES[name]
            stage.status = StageStatus.RUNNING
            stage.started_at = stage.started_at or utcnow()
            stage.finished_at = None
            stage.error = None
            await db.commit()
            attempts = 0
            while attempts < MAX_RETRIES:
                try:
                    await execute_stage(db, run, stage, zip_path)
                    break
                except Exception as exc:
                    attempts += 1
                    stage.retry_count = attempts
                    stage.error = str(exc)
                    stage.finished_at = utcnow()
                    if attempts >= MAX_RETRIES:
                        stage.status = StageStatus.FAILED
                        run.state = RunState.FAILED
                        await db.commit()
                        return
            if stage.status in {StageStatus.FAILED, StageStatus.SKIPPED}:
                run.state = RunState.INCONCLUSIVE
                await db.commit()
                return
            await db.commit()
        stages = list((await db.scalars(select(RunStage).where(RunStage.run_id == run.id))).all())
        run.state = RunState.AWAITING_APPROVAL if can_enter_approval(stages) and run.verdict not in {"UNSAFE", "INCONCLUSIVE"} else RunState.INCONCLUSIVE
        await db.commit()
