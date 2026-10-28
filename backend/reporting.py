from __future__ import annotations

from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AnalysisFinding, BuildRun, MigrationChange, MigrationRun, RepoSnapshot, RunStage, TestIntegrityResult, TestResult, RiskAssessment
from .verdict import VerdictResult

REPORT_VERSION = "1.0"

async def build_evidence_report(db: AsyncSession, run: MigrationRun, verdict: VerdictResult) -> dict:
    snapshot = await db.scalar(select(RepoSnapshot).where(RepoSnapshot.run_id == run.id))
    stages = list((await db.scalars(select(RunStage).where(RunStage.run_id == run.id))).all())
    findings = list((await db.scalars(select(AnalysisFinding).where(AnalysisFinding.run_id == run.id))).all())
    builds = list((await db.scalars(select(BuildRun).where(BuildRun.run_id == run.id))).all())
    results = list((await db.scalars(select(TestResult).where(TestResult.run_id == run.id))).all())
    integrity = list((await db.scalars(select(TestIntegrityResult).where(TestIntegrityResult.run_id == run.id))).all())
    changes = list((await db.scalars(select(MigrationChange).where(MigrationChange.run_id == run.id))).all())
    risk = await db.scalar(select(RiskAssessment).where(RiskAssessment.run_id == run.id).order_by(RiskAssessment.id.desc()))

    def duration(stage: RunStage) -> float | None:
        if not stage.started_at or not stage.finished_at:
            return None
        return (stage.finished_at - stage.started_at).total_seconds()

    return {
        "schema_version": REPORT_VERSION,
        "run_id": run.id,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "verdict": {"value": verdict.verdict, "caveat": verdict.caveat, "reasons": [reason.__dict__ for reason in verdict.reasons]},
        "risk": {"score": risk.score if risk else None, "label": "heuristic", "rationale": risk.rationale if risk else None, "breakdown": risk.breakdown if risk else []},
        "snapshot": {"commit_sha": snapshot.commit_sha, "content_hash": snapshot.content_hash, "path": snapshot.snapshot_path} if snapshot else None,
        "stages": [{"name": stage.stage_name.value, "status": stage.status.value, "started_at": stage.started_at.isoformat() if stage.started_at else None, "finished_at": stage.finished_at.isoformat() if stage.finished_at else None, "duration_seconds": duration(stage), "evidence_reference": stage.evidence_reference, "error": stage.error} for stage in stages],
        "tests": {
            "baseline": [{"name": item.test_name, "status": item.status, "duration_seconds": item.duration_seconds, "message": item.message, "flaky": item.flaky} for item in results if item.variant == "baseline"],
            "migrated": [{"name": item.test_name, "status": item.status, "duration_seconds": item.duration_seconds, "message": item.message, "flaky": item.flaky} for item in results if item.variant == "migrated"],
        },
        "integrity_findings": [{"code": item.code, "severity": item.severity, "path": item.path, "message": item.message, "confidence": item.confidence, "evidence": item.evidence, "note": item.note} for item in integrity],
        "builds": [{"status": item.status, "exit_code": item.exit_code, "log_excerpt": (item.logs or "")[-2000:], "artifacts": item.artifacts} for item in builds],
        "analysis_findings": [{"code": item.code, "severity": item.severity, "path": item.path, "line_number": item.line_number, "message": item.message, "evidence": item.evidence} for item in findings],
        "dependency_changes": [{"id": change.id, "code": change.code, "path": change.path, "title": change.title, "applied": change.applied} for change in changes],
        "migration_diff": [{"path": change.path, "code": change.code, "diff": change.diff, "applied": change.applied} for change in changes],
        "tool_versions": {"report_schema": REPORT_VERSION},
        "executed_commands": [],
        "evidence_ledger": [{"reference": stage.evidence_reference, "timestamp": stage.finished_at.isoformat() if stage.finished_at else None} for stage in stages if stage.evidence_reference],
        "limitations": [
            "The report is generated only from persisted database evidence.",
            "Passing checks do not prove behavioral equivalence.",
            "Risk is heuristic, not a probability.",
        ],
    }

def render_markdown(report: dict) -> str:
    lines = [f"# MigrationGuard verification report", "", f"Schema version: `{report['schema_version']}`", f"Verdict: **{report['verdict']['value']}**", "", report["verdict"]["caveat"], "", "## Reasons"]
    lines.extend(f"- `{reason['rule_id']}` ({reason['severity']}): {reason['message']} [{reason['evidence_reference']}]" for reason in report["verdict"]["reasons"])
    lines.extend(["", "## Risk", f"- Score: `{report['risk']['score']}`", "- Label: `heuristic`", f"- Rationale: {report['risk']['rationale']}", "", "## Limitations"])
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"
