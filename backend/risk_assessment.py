from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import AnalysisFinding, BuildRun, TestIntegrityResult

async def assess_run_breakdown(db: AsyncSession, run_id: str) -> tuple[str, str, list[dict[str, object]]]:
    findings = list((await db.scalars(select(AnalysisFinding).where(AnalysisFinding.run_id == run_id))).all())
    integrity = list((await db.scalars(select(TestIntegrityResult).where(TestIntegrityResult.run_id == run_id))).all())
    builds = list((await db.scalars(select(BuildRun).where(BuildRun.run_id == run_id))).all())
    breakdown: list[dict[str, object]] = []
    high_findings = sum(1 for item in findings if item.severity.lower() in {"critical", "high"})
    high_integrity = sum(1 for item in integrity if item.severity.lower() in {"critical", "high"})
    if high_findings:
        breakdown.append({"category": "analysis_findings", "weight": high_findings, "evidence_refs": [f"analysis:{item.id}" for item in findings if item.severity.lower() in {"critical", "high"}]})
    if high_integrity:
        breakdown.append({"category": "test_integrity", "weight": high_integrity, "evidence_refs": [f"integrity:{item.id}" for item in integrity if item.severity.lower() in {"critical", "high"}]})
    if any(item.status.lower() not in {"passed", "stubbed"} for item in builds):
        breakdown.append({"category": "build", "weight": 3, "evidence_refs": [f"build:{item.id}" for item in builds]})
    if high_findings or high_integrity or any(item.status.lower() not in {"passed", "stubbed"} for item in builds):
        return "HIGH", "Heuristic: high-severity findings or unsuccessful build evidence.", breakdown
    if findings or integrity:
        return "MEDIUM", "Heuristic: reviewable findings were detected.", breakdown
    return "LOW", "Heuristic: no high-severity findings were detected; approval is still required.", breakdown

async def assess_run(db: AsyncSession, run_id: str) -> tuple[str, str]:
    score, rationale, _ = await assess_run_breakdown(db, run_id)
    return score, rationale
