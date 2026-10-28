import enum
import uuid
from datetime import datetime
from sqlalchemy import DateTime, Enum, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

class Role(str, enum.Enum):
    admin='admin'; developer='developer'; viewer='viewer'
class RunState(str, enum.Enum):
    SUBMITTED='SUBMITTED'; CLONING='CLONING'; ANALYZING='ANALYZING'; MIGRATING='MIGRATING'; TESTING='TESTING'; BUILDING='BUILDING'; ASSESSING_RISK='ASSESSING_RISK'; GENERATING_REPORT='GENERATING_REPORT'; AWAITING_APPROVAL='AWAITING_APPROVAL'; FAILED='FAILED'; INCONCLUSIVE='INCONCLUSIVE'; ACCEPTED='ACCEPTED'; REJECTED='REJECTED'

class StageStatus(str, enum.Enum):
    PENDING='PENDING'; RUNNING='RUNNING'; PASSED='PASSED'; FAILED='FAILED'; SKIPPED='SKIPPED'

class StageName(str, enum.Enum):
    ANALYSIS='analysis'; MIGRATING='migrating'; TEST_INTEGRITY='test_integrity'; BUILD_AND_TEST='build_and_test'; RISK_ASSESSMENT='risk_assessment'; REPORT='report'; VERDICT='verdict'

REQUIRED_STAGES = tuple(StageName)

def idcol(): return mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
class User(Base):
    __tablename__='users'; id: Mapped[str]=idcol(); email: Mapped[str]=mapped_column(String(320), unique=True, index=True); password_hash: Mapped[str]=mapped_column(String(255)); role: Mapped[Role]=mapped_column(Enum(Role), default=Role.developer); created_at: Mapped[datetime]=mapped_column(DateTime, server_default=func.now())
class Project(Base):
    __tablename__='projects'; id: Mapped[str]=idcol(); owner_id: Mapped[str]=mapped_column(ForeignKey('users.id')); name: Mapped[str]=mapped_column(String(255)); repository_url: Mapped[str|None]=mapped_column(String(500)); created_at: Mapped[datetime]=mapped_column(DateTime, server_default=func.now())
class RepoSnapshot(Base):
    __tablename__='repo_snapshots'; id: Mapped[str]=idcol(); project_id: Mapped[str]=mapped_column(ForeignKey('projects.id')); run_id: Mapped[str]=mapped_column(ForeignKey('migration_runs.id')); commit_sha: Mapped[str]=mapped_column(String(100)); content_hash: Mapped[str]=mapped_column(String(64)); snapshot_path: Mapped[str]=mapped_column(String(1000)); snapshot_metadata: Mapped[dict] = mapped_column('metadata', JSON, default=dict)
class MigrationRun(Base):
    __tablename__='migration_runs'; id: Mapped[str]=idcol(); project_id: Mapped[str]=mapped_column(ForeignKey('projects.id')); state: Mapped[RunState]=mapped_column(Enum(RunState), default=RunState.SUBMITTED); verdict: Mapped[str|None]=mapped_column(String(40), nullable=True); created_by: Mapped[str]=mapped_column(ForeignKey('users.id')); created_at: Mapped[datetime]=mapped_column(DateTime, server_default=func.now())
class MigrationChange(Base):
    __tablename__='migration_changes'; id: Mapped[str]=idcol(); run_id: Mapped[str]=mapped_column(ForeignKey('migration_runs.id')); path: Mapped[str]=mapped_column(String(500)); diff: Mapped[str]=mapped_column(Text); source: Mapped[str]=mapped_column(String(30), default='rule'); rule_id: Mapped[str|None]=mapped_column(String(120)); status: Mapped[str]=mapped_column(String(30), default='proposed'); code: Mapped[str|None]=mapped_column(String(80)); title: Mapped[str|None]=mapped_column(String(255)); rationale: Mapped[str|None]=mapped_column(Text); before_content: Mapped[str|None]=mapped_column(Text); after_content: Mapped[str|None]=mapped_column(Text); reversible: Mapped[bool]=mapped_column(default=True); advisory: Mapped[bool]=mapped_column(default=True); applied: Mapped[bool]=mapped_column(default=False); protected: Mapped[bool]=mapped_column(default=False); unnecessary_change: Mapped[bool]=mapped_column(default=False); changed_lines_ratio: Mapped[float|None]=mapped_column()
class AnalysisFinding(Base):
    __tablename__='analysis_findings'; id: Mapped[str]=idcol(); run_id: Mapped[str]=mapped_column(ForeignKey('migration_runs.id')); severity: Mapped[str]=mapped_column(String(30)); code: Mapped[str]=mapped_column(String(100), default='ANALYSIS'); message: Mapped[str]=mapped_column(Text); path: Mapped[str|None]=mapped_column(String(1000)); line_number: Mapped[int|None]=mapped_column(); provenance: Mapped[str|None]=mapped_column(String(500)); confidence: Mapped[str|None]=mapped_column(String(30)); evidence: Mapped[str|None]=mapped_column(Text); note: Mapped[str|None]=mapped_column(Text)
class TestCase(Base):
    __tablename__='test_cases'; id: Mapped[str]=idcol(); project_id: Mapped[str]=mapped_column(ForeignKey('projects.id')); name: Mapped[str]=mapped_column(String(255)); definition: Mapped[dict]=mapped_column(JSON, default=dict)
class TestResult(Base):
    __tablename__='test_results'; id: Mapped[str]=idcol(); run_id: Mapped[str]=mapped_column(ForeignKey('migration_runs.id')); test_case_id: Mapped[str|None]=mapped_column(ForeignKey('test_cases.id')); variant: Mapped[str]=mapped_column(String(30), default='migrated'); test_name: Mapped[str]=mapped_column(String(500), default='unknown'); status: Mapped[str]=mapped_column(String(30)); duration_seconds: Mapped[float|None]=mapped_column(); message: Mapped[str|None]=mapped_column(Text); output: Mapped[str|None]=mapped_column(Text); attempt: Mapped[int]=mapped_column(default=1); flaky: Mapped[bool]=mapped_column(default=False)
class BuildRun(Base):
    __tablename__='build_runs'; id: Mapped[str]=idcol(); run_id: Mapped[str]=mapped_column(ForeignKey('migration_runs.id')); variant: Mapped[str]=mapped_column(String(30), default='migrated'); status: Mapped[str]=mapped_column(String(30)); exit_code: Mapped[int|None]=mapped_column(); logs: Mapped[str|None]=mapped_column(Text); artifacts: Mapped[dict]=mapped_column(JSON, default=dict)
class RiskAssessment(Base):
    __tablename__='risk_assessments'; id: Mapped[str]=idcol(); run_id: Mapped[str]=mapped_column(ForeignKey('migration_runs.id')); score: Mapped[str]=mapped_column(String(30)); rationale: Mapped[str]=mapped_column(Text); breakdown: Mapped[list]=mapped_column(JSON, default=list)
class Report(Base):
    __tablename__='reports'; id: Mapped[str]=idcol(); run_id: Mapped[str]=mapped_column(ForeignKey('migration_runs.id')); content: Mapped[dict]=mapped_column(JSON, default=dict)
class Approval(Base):
    __tablename__='approvals'; __table_args__=(UniqueConstraint('run_id', name='uq_approvals_run_id'),); id: Mapped[str]=idcol(); run_id: Mapped[str]=mapped_column(ForeignKey('migration_runs.id')); user_id: Mapped[str]=mapped_column(ForeignKey('users.id')); decision: Mapped[str]=mapped_column(String(30)); justification: Mapped[str|None]=mapped_column(Text); created_at: Mapped[datetime]=mapped_column(DateTime, server_default=func.now())
class TestIntegrityResult(Base):
    __tablename__='test_integrity_results'; id: Mapped[str]=idcol(); run_id: Mapped[str]=mapped_column(ForeignKey('migration_runs.id')); code: Mapped[str]=mapped_column(String(80)); severity: Mapped[str]=mapped_column(String(30)); path: Mapped[str]=mapped_column(String(500)); message: Mapped[str]=mapped_column(Text); confidence: Mapped[str]=mapped_column(String(30), default='medium'); evidence: Mapped[str|None]=mapped_column(Text); note: Mapped[str|None]=mapped_column(Text); created_at: Mapped[datetime]=mapped_column(DateTime, server_default=func.now())

class AuditLog(Base):
    __tablename__='audit_log'; id: Mapped[str]=idcol(); user_id: Mapped[str|None]=mapped_column(ForeignKey('users.id')); action: Mapped[str]=mapped_column(String(255)); entity_id: Mapped[str|None]=mapped_column(String(36)); details: Mapped[dict]=mapped_column(JSON, default=dict); created_at: Mapped[datetime]=mapped_column(DateTime, server_default=func.now())

class RunStage(Base):
    __tablename__='run_stages'
    __table_args__=(UniqueConstraint('run_id', 'stage_name', name='uq_run_stages_run_stage'),)
    id: Mapped[str]=idcol()
    run_id: Mapped[str]=mapped_column(ForeignKey('migration_runs.id'))
    stage_name: Mapped[StageName]=mapped_column(Enum(StageName))
    status: Mapped[StageStatus]=mapped_column(Enum(StageStatus), default=StageStatus.PENDING)
    started_at: Mapped[datetime|None]=mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime|None]=mapped_column(DateTime, nullable=True)
    error: Mapped[str|None]=mapped_column(Text, nullable=True)
    evidence_reference: Mapped[str|None]=mapped_column(String(500), nullable=True)
    retry_count: Mapped[int]=mapped_column(default=0)

class LLMInteraction(Base):
    __tablename__='llm_interactions'
    id: Mapped[str]=idcol()
    run_id: Mapped[str|None]=mapped_column(ForeignKey('migration_runs.id'), nullable=True)
    provider: Mapped[str]=mapped_column(String(40))
    model: Mapped[str]=mapped_column(String(120))
    prompt_hash: Mapped[str]=mapped_column(String(64))
    redacted_prompt: Mapped[str]=mapped_column(Text)
    response: Mapped[dict]=mapped_column(JSON, default=dict)
    tokens: Mapped[int|None]=mapped_column(nullable=True)
    latency_ms: Mapped[int|None]=mapped_column(nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime, server_default=func.now())

class ReportShare(Base):
    __tablename__='report_shares'
    id: Mapped[str]=idcol()
    run_id: Mapped[str]=mapped_column(ForeignKey('migration_runs.id'))
    token_hash: Mapped[str]=mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]=mapped_column(DateTime)
    created_at: Mapped[datetime]=mapped_column(DateTime, server_default=func.now())
