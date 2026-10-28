import asyncio, json
import tempfile
import time
import hashlib
import secrets
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .db import SessionLocal, get_db
from .config import settings
from .models import User, Project, MigrationRun, MigrationChange, RunState, RepoSnapshot, AnalysisFinding, BuildRun, RunStage, StageName, StageStatus
from .build_executor import run_maven_build
from .phase3_schemas import BuildResultOut
from .phase4_schemas import IntegrityCheckRequest, IntegrityCheckOut, IntegrityFindingOut
from .test_integrity import compare_test_trees, parse_test_tree
from .migration_assistance import build_java17_plan, explain_proposal
from .phase5_schemas import MigrationPlanOut, MigrationProposalOut
from .phase6_schemas import RiskAssessmentOut, ReportOut, ApprovalRequest, ApprovalOut
from .risk_assessment import assess_run_breakdown
from .models import Approval, AuditLog, Report, ReportShare, RiskAssessment, Role, MigrationChange, TestResult, TestIntegrityResult
from .schemas import UserCreate, Token, ProjectCreate, ProjectOut, RunOut
from .phase2_schemas import SnapshotOut, FindingOut, RunDetailOut
from .auth import hash_password, verify_password, create_token, current_user, oauth2, require_roles
from .ingestion import create_snapshot_and_findings
from .migration_engine import verify_snapshot
from workers.queue import enqueue_run
from .reporting import build_evidence_report, render_markdown
from .verdict import compute_verdict
from .llm.service import LLMService
from .llm.providers import FakeProvider

_llm_requests: dict[str, list[float]] = {}

app=FastAPI(title='MigrationGuard API', version='1.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def _ai_artifacts(run_id: str, db: AsyncSession) -> dict:
    builds = list((await db.scalars(select(BuildRun).where(BuildRun.run_id == run_id))).all())
    report = await db.scalar(select(Report).where(Report.run_id == run_id).order_by(Report.id.desc()))
    return {
        "builds": [{"id": item.id, "status": item.status, "logs": item.logs or ""} for item in builds],
        "report": report.content if report else {},
    }

def _check_llm_rate(user: User) -> None:
    now = time.time()
    values = [value for value in _llm_requests.get(user.id, []) if now - value < 60]
    if len(values) >= settings.llm_rate_limit_per_minute:
        raise HTTPException(429, "AI assistance rate limit exceeded")
    values.append(now)
    _llm_requests[user.id] = values

async def _ai_service_call(run_id: str, user: User, db: AsyncSession, operation: str):
    await _owned_run(run_id, user, db)
    _check_llm_rate(user)
    service = LLMService(FakeProvider() if settings.llm_provider == "fake" else None)
    try:
        artifacts = await _ai_artifacts(run_id, db)
        result = await getattr(service, operation)(db, run_id, artifacts)
        if operation == "suggest_fix":
            await service.store_suggestions(db, run_id, result)
        await db.commit()
        return {"label": "AI-generated - unverified", **result.model_dump()}
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc

@app.get('/health')
async def health(): return {'status':'ok'}

@app.get('/benchmarks')
async def list_benchmarks(user: User = Depends(current_user)):
    return {"items": [], "status": "evaluation_not_run"}

@app.get('/benchmarks/{benchmark_id}')
async def get_benchmark(benchmark_id: str, user: User = Depends(current_user)):
    raise HTTPException(404, "Benchmark result not found")

@app.post('/runs/{run_id}/ai/explain')
async def ai_explain(run_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await _ai_service_call(run_id, user, db, "explain")

@app.post('/runs/{run_id}/ai/suggest-fix')
async def ai_suggest_fix(run_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await _ai_service_call(run_id, user, db, "suggest_fix")

@app.post('/runs/{run_id}/ai/summary')
async def ai_summary(run_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    return await _ai_service_call(run_id, user, db, "summary")
@app.post('/auth/register', response_model=Token)
async def register(data: UserCreate, db: AsyncSession=Depends(get_db)):
    if await db.scalar(select(User).where(User.email == data.email)):
        raise HTTPException(409, 'Email already registered')
    # Public registration may not self-assign privileged roles.
    user = User(email=data.email, password_hash=hash_password(data.password), role='developer')
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return Token(access_token=create_token(user))
@app.post('/auth/login', response_model=Token)
async def login(data: UserCreate, db: AsyncSession=Depends(get_db)):
    user=await db.scalar(select(User).where(User.email==data.email))
    if not user or not verify_password(data.password,user.password_hash): raise HTTPException(401,'Invalid credentials')
    return Token(access_token=create_token(user))
@app.post('/projects', response_model=ProjectOut)
async def create_project(data: ProjectCreate, user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    project=Project(**data.model_dump(),owner_id=user.id); db.add(project); await db.commit(); await db.refresh(project); return project
@app.get('/projects', response_model=list[ProjectOut])
async def list_projects(user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    return list((await db.scalars(select(Project).where(Project.owner_id==user.id))).all())
@app.post('/projects/{project_id}/runs', response_model=RunOut, status_code=202)
async def create_run(project_id: str, user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    project=await db.scalar(select(Project).where(Project.id==project_id,Project.owner_id==user.id))
    if not project: raise HTTPException(404,'Project not found')
    run=MigrationRun(project_id=project_id,created_by=user.id,state=RunState.SUBMITTED)
    db.add(run)
    await db.flush()
    db.add_all([RunStage(run_id=run.id, stage_name=name, status=StageStatus.PENDING) for name in StageName])
    await db.commit()
    await db.refresh(run)
    try:
        enqueue_run(run.id)
    except Exception as exc:
        run.state = RunState.FAILED
        await db.commit()
        raise HTTPException(503, f'Unable to enqueue run: {exc}') from exc
    return run

@app.post('/projects/{project_id}/runs/upload', response_model=RunOut, status_code=202)
async def create_zip_run(project_id: str, upload: UploadFile = File(...), user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    project = await db.scalar(select(Project).where(Project.id == project_id, Project.owner_id == user.id))
    if not project:
        raise HTTPException(404, 'Project not found')
    if not upload.filename or not upload.filename.lower().endswith('.zip'):
        raise HTTPException(422, 'Only zip uploads are supported')
    temporary = tempfile.NamedTemporaryFile(prefix='migrationguard-upload-', suffix='.zip', delete=False)
    try:
        while chunk := await upload.read(1024 * 1024):
            temporary.write(chunk)
        temporary.close()
        run = MigrationRun(project_id=project_id, created_by=user.id, state=RunState.SUBMITTED)
        db.add(run)
        await db.flush()
        db.add_all([RunStage(run_id=run.id, stage_name=name, status=StageStatus.PENDING) for name in StageName])
        await db.commit()
        await db.refresh(run)
        from workers.celery_app import run_pipeline
        run_pipeline.apply_async(args=[run.id, temporary.name])
        return run
    finally:
        await upload.close()
@app.get('/runs/{run_id}', response_model=RunOut)
async def get_run(run_id: str, user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    run=await db.scalar(select(MigrationRun).join(Project,Project.id==MigrationRun.project_id).where(MigrationRun.id==run_id,Project.owner_id==user.id))
    if not run: raise HTTPException(404,'Run not found')
    return run
@app.get('/runs/{run_id}/details', response_model=RunDetailOut)
async def get_run_details(run_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    run = await db.scalar(select(MigrationRun).join(Project, Project.id == MigrationRun.project_id).where(MigrationRun.id == run_id, Project.owner_id == user.id))
    if not run:
        raise HTTPException(404, 'Run not found')
    snapshot = await db.scalar(select(RepoSnapshot).where(RepoSnapshot.run_id == run.id))
    findings = list((await db.scalars(select(AnalysisFinding).where(AnalysisFinding.run_id == run_id))).all())
    return RunDetailOut.model_validate({**run.__dict__, 'snapshot': snapshot, 'findings': findings}, from_attributes=True)

@app.get('/runs/{run_id}/snapshot', response_model=SnapshotOut)
async def get_snapshot(run_id: str, user: User=Depends(current_user), db: AsyncSession=Depends(get_db)): 
    snapshot = await db.scalar(select(RepoSnapshot).join(MigrationRun, MigrationRun.id == RepoSnapshot.run_id).join(Project, Project.id == MigrationRun.project_id).where(MigrationRun.id == run_id, Project.owner_id == user.id))
    if not snapshot: raise HTTPException(404, 'Snapshot not found')
    return snapshot

@app.get('/runs/{run_id}/findings', response_model=list[FindingOut])
async def get_findings(run_id: str, user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    run = await db.scalar(select(MigrationRun).join(Project, Project.id == MigrationRun.project_id).where(MigrationRun.id == run_id, Project.owner_id == user.id))
    if not run: raise HTTPException(404, 'Run not found')
    return list((await db.scalars(select(AnalysisFinding).where(AnalysisFinding.run_id == run_id))).all())

async def _owned_run(run_id: str, user: User, db: AsyncSession) -> MigrationRun:
    run = await db.scalar(select(MigrationRun).join(Project, Project.id == MigrationRun.project_id).where(
        MigrationRun.id == run_id, Project.owner_id == user.id
    ))
    if not run:
        raise HTTPException(404, "Run not found")
    return run

@app.get('/runs/{run_id}/changes')
async def get_changes(run_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _owned_run(run_id, user, db)
    return list((await db.scalars(select(MigrationChange).where(MigrationChange.run_id == run_id).order_by(MigrationChange.id))).all())

async def _change_action(run_id: str, change_id: str, user: User, db: AsyncSession, apply: bool):
    await _owned_run(run_id, user, db)
    change = await db.scalar(select(MigrationChange).where(MigrationChange.id == change_id, MigrationChange.run_id == run_id))
    if not change:
        raise HTTPException(404, "Migration change not found")
    if change.protected and apply:
        raise HTTPException(409, "Protected test changes require review and cannot be auto-applied")
    snapshot = await db.scalar(select(RepoSnapshot).where(RepoSnapshot.run_id == run_id))
    if not snapshot or not snapshot.snapshot_metadata.get("migrated_path"):
        raise HTTPException(409, "Migrated working copy is not available")
    verify_snapshot(snapshot.snapshot_path, snapshot.content_hash)
    target = Path(snapshot.snapshot_metadata["migrated_path"]) / change.path
    target.parent.mkdir(parents=True, exist_ok=True)
    content = change.after_content if apply else change.before_content
    if content is None:
        raise HTTPException(409, "Change does not contain reversible content")
    target.write_text(content, encoding="utf-8")
    change.applied = apply
    change.status = "applied" if apply else "reverted"
    stages = list((await db.scalars(select(RunStage).where(RunStage.run_id == run_id))).all())
    for stage in stages:
        if stage.stage_name in {StageName.MIGRATING, StageName.TEST_INTEGRITY, StageName.BUILD_AND_TEST, StageName.RISK_ASSESSMENT, StageName.REPORT, StageName.VERDICT}:
            stage.status = StageStatus.PENDING
            stage.evidence_reference = None
            stage.error = None
    run = await db.get(MigrationRun, run_id)
    if run:
        run.state = RunState.SUBMITTED
    await db.commit()
    try:
        enqueue_run(run_id)
    except Exception as exc:
        raise HTTPException(503, f"Unable to enqueue migration verification: {exc}") from exc
    return change

@app.post('/runs/{run_id}/changes/{change_id}/apply')
async def apply_change(run_id: str, change_id: str, user: User = Depends(require_roles(Role.developer, Role.admin)), db: AsyncSession = Depends(get_db)):
    return await _change_action(run_id, change_id, user, db, True)

@app.post('/runs/{run_id}/changes/{change_id}/revert')
async def revert_change(run_id: str, change_id: str, user: User = Depends(require_roles(Role.developer, Role.admin)), db: AsyncSession = Depends(get_db)):
    return await _change_action(run_id, change_id, user, db, False)

@app.post('/runs/{run_id}/changes/revert-all')
async def revert_all_changes(run_id: str, user: User = Depends(require_roles(Role.developer, Role.admin)), db: AsyncSession = Depends(get_db)):
    await _owned_run(run_id, user, db)
    changes = list((await db.scalars(select(MigrationChange).where(MigrationChange.run_id == run_id))).all())
    for change in changes:
        if change.applied:
            await _change_action(run_id, change.id, user, db, False)
    return changes

@app.get('/runs/{run_id}/diff', response_class=PlainTextResponse)
async def get_run_diff(run_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _owned_run(run_id, user, db)
    changes = list((await db.scalars(select(MigrationChange).where(
        MigrationChange.run_id == run_id, MigrationChange.applied.is_(True)
    ))).all())
    return "\n".join(change.diff for change in changes if change.diff)

@app.post('/runs/{run_id}/build', response_model=BuildResultOut, status_code=202)
async def build_run(run_id: str, user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    run = await db.scalar(select(MigrationRun).join(Project, Project.id == MigrationRun.project_id).where(MigrationRun.id == run_id, Project.owner_id == user.id))
    if not run: raise HTTPException(404, 'Run not found')
    snapshot = await db.scalar(select(RepoSnapshot).where(RepoSnapshot.run_id == run_id))
    if not snapshot:
        raise HTTPException(409, 'Run snapshot is not available')
    result = await run_maven_build(
        snapshot.snapshot_path,
        java_version=17,
        docker_enabled=settings.migrationguard_enable_execution,
        maven_mirror=settings.maven_mirror,
    )
    record = BuildRun(run_id=run_id, status=result.status, exit_code=result.exit_code, logs=result.logs, artifacts=result.artifacts)
    db.add(record); await db.commit(); await db.refresh(record)
    return record

@app.post('/runs/{run_id}/test-integrity', response_model=IntegrityCheckOut)
async def test_integrity(run_id: str, data: IntegrityCheckRequest, user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    run = await db.scalar(select(MigrationRun).join(Project, Project.id == MigrationRun.project_id).where(MigrationRun.id == run_id, Project.owner_id == user.id))
    if not run: raise HTTPException(404, 'Run not found')
    findings = compare_test_trees(data.baseline_files, data.migrated_files)
    return IntegrityCheckOut(
        findings=[IntegrityFindingOut.model_validate(f, from_attributes=True) for f in findings],
        baseline_test_count=sum(int(v['tests']) for v in parse_test_tree(data.baseline_files).values()),
        migrated_test_count=sum(int(v['tests']) for v in parse_test_tree(data.migrated_files).values()),
    )

@app.get('/runs/{run_id}/migration-plan', response_model=MigrationPlanOut)
async def migration_plan(run_id: str, user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    run = await db.scalar(select(MigrationRun).join(Project, Project.id == MigrationRun.project_id).where(MigrationRun.id == run_id, Project.owner_id == user.id))
    if not run:
        raise HTTPException(404, 'Run not found')
    snapshot = await db.scalar(select(RepoSnapshot).where(RepoSnapshot.run_id == run.id))
    metadata = snapshot.snapshot_metadata if snapshot else {}
    proposals = build_java17_plan(metadata)
    records = []
    for proposal in proposals:
        record = MigrationChange(run_id=run_id, code=proposal.code, path=proposal.path, title=proposal.title, rationale=proposal.rationale, diff=proposal.diff, reversible=proposal.reversible, advisory=proposal.advisory)
        db.add(record)
        records.append(record)
    await db.commit()
    return MigrationPlanOut(run_id=run_id, target='java-17', proposals=[MigrationProposalOut(run_id=run_id, code=p.code, path=p.path, title=p.title, rationale=p.rationale, diff=p.diff, explanation=explain_proposal(p), reversible=p.reversible, advisory=p.advisory) for p in proposals])

@app.post('/runs/{run_id}/assess-risk', response_model=RiskAssessmentOut)
async def assess_risk(run_id: str, user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    run = await db.scalar(select(MigrationRun).join(Project, Project.id == MigrationRun.project_id).where(MigrationRun.id == run_id, Project.owner_id == user.id))
    if not run: raise HTTPException(404, 'Run not found')
    score, rationale, breakdown = await assess_run_breakdown(db, run_id)
    record = RiskAssessment(run_id=run_id, score=score, rationale=rationale, breakdown=breakdown)
    db.add(record); await db.commit(); await db.refresh(record)
    return record

async def _run_verdict(db: AsyncSession, run_id: str):
    stages = list((await db.scalars(select(RunStage).where(RunStage.run_id == run_id))).all())
    findings = list((await db.scalars(select(AnalysisFinding).where(AnalysisFinding.run_id == run_id))).all())
    builds = list((await db.scalars(select(BuildRun).where(BuildRun.run_id == run_id))).all())
    results = list((await db.scalars(select(TestResult).where(TestResult.run_id == run_id))).all())
    integrity = list((await db.scalars(select(TestIntegrityResult).where(TestIntegrityResult.run_id == run_id))).all())
    changes = list((await db.scalars(select(MigrationChange).where(MigrationChange.run_id == run_id))).all())
    return compute_verdict(stages, findings, builds, results, integrity, changes, docker_execution_enabled=settings.migrationguard_enable_execution)

@app.get('/runs/{run_id}/report', response_model=ReportOut)
async def get_report(run_id: str, user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    run = await db.scalar(select(MigrationRun).join(Project, Project.id == MigrationRun.project_id).where(MigrationRun.id == run_id, Project.owner_id == user.id))
    if not run: raise HTTPException(404, 'Run not found')
    result = await _run_verdict(db, run_id)
    report = await db.scalar(select(Report).where(Report.run_id == run_id).order_by(Report.id.desc()))
    content = await build_evidence_report(db, run, result)
    if report:
        report.content = content
    else:
        report = Report(run_id=run_id, content=content)
        db.add(report)
    await db.commit()
    await db.refresh(report)
    return report

@app.get('/runs/{run_id}/report.md', response_class=PlainTextResponse)
async def get_report_markdown(run_id: str, user: User=Depends(current_user), db: AsyncSession=Depends(get_db)):
    run = await db.scalar(select(MigrationRun).join(Project, Project.id == MigrationRun.project_id).where(MigrationRun.id == run_id, Project.owner_id == user.id))
    if not run:
        raise HTTPException(404, 'Run not found')
    return render_markdown(await build_evidence_report(db, run, await _run_verdict(db, run_id)))

@app.get('/runs/{run_id}/report.html', response_class=HTMLResponse)
async def get_report_html(run_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    run = await _owned_run(run_id, user, db)
    report = await build_evidence_report(db, run, await _run_verdict(db, run_id))
    reasons = "".join(f"<li>{escape(item['rule_id'])}: {escape(item['message'])}</li>" for item in report["verdict"]["reasons"])
    limitations = "".join(f"<li>{escape(item)}</li>" for item in report["limitations"])
    return HTMLResponse(f"<html><body><h1>MigrationGuard verification report</h1><h2>{escape(report['verdict']['value'])}</h2><p>{escape(report['verdict']['caveat'])}</p><h2>Reasons</h2><ul>{reasons}</ul><h2>Limitations</h2><ul>{limitations}</ul></body></html>")

@app.get('/runs/{run_id}/report.pdf')
async def get_report_pdf(run_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    html = await get_report_html(run_id, user, db)
    try:
        from weasyprint import HTML
        html_text = html.body.decode("utf-8") if isinstance(html, HTMLResponse) else str(html)
        return Response(HTML(string=html_text).write_pdf(), media_type="application/pdf")
    except (ImportError, OSError) as exc:
        raise HTTPException(503, "PDF export requires the optional WeasyPrint dependency.") from exc

@app.post('/runs/{run_id}/report/share')
async def create_report_share(run_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _owned_run(run_id, user, db)
    token = secrets.token_urlsafe(32)
    db.add(ReportShare(run_id=run_id, token_hash=hashlib.sha256(token.encode()).hexdigest(), expires_at=datetime.utcnow() + timedelta(hours=24)))
    await db.commit()
    return {"token": token, "expires_in_seconds": 86400, "url": f"/shared/reports/{token}"}

@app.get('/shared/reports/{token}', response_class=PlainTextResponse)
async def shared_report(token: str, db: AsyncSession = Depends(get_db)):
    record = await db.scalar(select(ReportShare).where(
        ReportShare.token_hash == hashlib.sha256(token.encode()).hexdigest(),
        ReportShare.expires_at > datetime.utcnow(),
    ))
    if not record:
        raise HTTPException(404, "Share link not found or expired")
    run = await db.get(MigrationRun, record.run_id)
    if not run:
        raise HTTPException(404, "Report not found")
    return render_markdown(await build_evidence_report(db, run, await _run_verdict(db, run.id)))

@app.get('/runs/{run_id}/export/patch', response_class=PlainTextResponse)
async def export_patch(run_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await _owned_run(run_id, user, db)
    changes = list((await db.scalars(select(MigrationChange).where(
        MigrationChange.run_id == run_id, MigrationChange.applied.is_(True)
    ))).all())
    return "\n".join(change.diff for change in changes if change.diff)

@app.post('/runs/{run_id}/pull-request')
async def open_pull_request(run_id: str, data: dict, user: User = Depends(require_roles(Role.developer, Role.admin)), db: AsyncSession = Depends(get_db)):
    run = await _owned_run(run_id, user, db)
    if run.state != RunState.ACCEPTED:
        raise HTTPException(409, "Only ACCEPTED runs may open a pull request")
    if not settings.github_token:
        raise HTTPException(503, "GitHub integration is disabled because no token is configured")
    project = await db.get(Project, run.project_id)
    parsed = urllib.parse.urlparse(project.repository_url or "")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise HTTPException(422, "Project repository is not a GitHub repository")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    report = await build_evidence_report(db, run, await _run_verdict(db, run_id))
    payload = json.dumps({
        "title": data.get("title", f"MigrationGuard Java 17 migration for {project.name}"),
        "head": data.get("head", f"migrationguard/{run_id}"),
        "base": data.get("base", "main"),
        "body": render_markdown(report),
    }).encode()
    request = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo}/pulls",
        data=payload,
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {settings.github_token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise HTTPException(502, "GitHub pull request creation failed") from exc

@app.post('/runs/{run_id}/approval', response_model=ApprovalOut)
async def approve_run(run_id: str, data: ApprovalRequest, user: User=Depends(require_roles(Role.developer, Role.admin)), db: AsyncSession=Depends(get_db)):
    if data.decision not in {'approved', 'rejected'}: raise HTTPException(422, 'Decision must be approved or rejected')
    run = await db.scalar(select(MigrationRun).join(Project, Project.id == MigrationRun.project_id).where(MigrationRun.id == run_id, Project.owner_id == user.id))
    if not run: raise HTTPException(404, 'Run not found')
    if not run.verdict:
        result = await _run_verdict(db, run_id)
        run.verdict = result.verdict
        await db.flush()
    existing = await db.scalar(select(Approval).where(Approval.run_id == run_id))
    if existing:
        if existing.decision == data.decision:
            return existing
        raise HTTPException(409, 'Run already has a different approval decision')
    if data.decision == 'approved':
        if run.verdict in {'UNSAFE', 'INCONCLUSIVE'}:
            if user.role != Role.admin or not data.override_reason:
                raise HTTPException(409, 'Only an admin override with a mandatory reason can approve this verdict')
        elif run.verdict == 'NEEDS_REVIEW' and not data.justification:
            raise HTTPException(422, 'A written justification is required for NEEDS_REVIEW approval')
        elif run.state != RunState.AWAITING_APPROVAL:
            raise HTTPException(409, 'Run is not ready for approval')
        run.state = RunState.ACCEPTED
    else:
        run.state = RunState.REJECTED
    approval = Approval(run_id=run_id, user_id=user.id, decision=data.decision, justification=data.justification or data.override_reason)
    db.add(approval)
    db.add(AuditLog(user_id=user.id, action=f'run.{data.decision}', entity_id=run_id, details={'verdict': run.verdict, 'override_reason': data.override_reason}))
    await db.commit(); await db.refresh(approval)
    return approval

@app.get('/runs/{run_id}/events')
async def run_events(run_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    run = await db.scalar(select(MigrationRun).join(Project, Project.id == MigrationRun.project_id).where(MigrationRun.id == run_id, Project.owner_id == user.id))
    if not run:
        raise HTTPException(404, 'Run not found')

    async def events():
        last_payload = None
        heartbeat_at = asyncio.get_running_loop().time()
        while True:
            async with SessionLocal() as stream_db:
                current = await stream_db.scalar(select(MigrationRun).where(MigrationRun.id == run_id))
                stages = list((await stream_db.scalars(select(RunStage).where(RunStage.run_id == run_id).order_by(RunStage.stage_name))).all())
                payload = {
                    "run_id": run_id,
                    "state": current.state.value if current else "FAILED",
                    "stages": [{"name": s.stage_name.value, "status": s.status.value, "evidence_reference": s.evidence_reference} for s in stages],
                }
            if payload != last_payload:
                yield f'data: {json.dumps(payload)}\n\n'
                last_payload = payload
            now = asyncio.get_running_loop().time()
            if now - heartbeat_at >= 5:
                yield ': heartbeat\n\n'
                heartbeat_at = now
            if payload["state"] in {"AWAITING_APPROVAL", "FAILED", "INCONCLUSIVE"}:
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
