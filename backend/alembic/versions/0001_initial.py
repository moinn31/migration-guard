"""Create the complete baseline schema."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

role = sa.Enum("admin", "developer", "viewer", name="role", native_enum=False)
run_state = sa.Enum(
    "SUBMITTED", "CLONING", "ANALYZING", "MIGRATING", "TESTING", "BUILDING",
    "ASSESSING_RISK", "GENERATING_REPORT", "AWAITING_APPROVAL",
    "FAILED", "INCONCLUSIVE", "ACCEPTED", "REJECTED", name="runstate", native_enum=False,
)
stage_name = sa.Enum("analysis", "test_integrity", "build_and_test", "risk_assessment", "report", "verdict", name="stagename", native_enum=False)
stage_status = sa.Enum("PENDING", "RUNNING", "PASSED", "FAILED", "SKIPPED", name="stagestatus", native_enum=False)

def id_column():
    return sa.Column("id", sa.String(36), primary_key=True)

def upgrade() -> None:
    op.create_table(
        "users",
        id_column(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", role, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "projects",
        id_column(),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("repository_url", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "migration_runs",
        id_column(),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("state", run_state, nullable=False),
        sa.Column("verdict", sa.String(40)),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "repo_snapshots",
        id_column(),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("commit_sha", sa.String(100), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_path", sa.String(1000), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_repo_snapshots_project_id", "repo_snapshots", ["project_id"])
    op.create_index("ix_repo_snapshots_run_id", "repo_snapshots", ["run_id"], unique=True)
    op.create_table(
        "migration_changes",
        id_column(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("diff", sa.Text(), nullable=False),
        sa.Column("source", sa.String(30), nullable=False, server_default="rule"),
        sa.Column("rule_id", sa.String(120)),
        sa.Column("status", sa.String(30), nullable=False, server_default="proposed"),
        sa.Column("code", sa.String(80)),
        sa.Column("title", sa.String(255)),
        sa.Column("rationale", sa.Text()),
        sa.Column("before_content", sa.Text()),
        sa.Column("after_content", sa.Text()),
        sa.Column("reversible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("advisory", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("protected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("unnecessary_change", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("changed_lines_ratio", sa.Float()),
    )
    op.create_table(
        "analysis_findings",
        id_column(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("path", sa.String(1000)),
        sa.Column("line_number", sa.Integer()),
        sa.Column("provenance", sa.String(500)),
        sa.Column("confidence", sa.String(30)),
        sa.Column("evidence", sa.Text()),
        sa.Column("note", sa.Text()),
    )
    op.create_index("ix_analysis_findings_run_id", "analysis_findings", ["run_id"])
    op.create_table(
        "test_cases",
        id_column(),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
    )
    op.create_table(
        "test_results",
        id_column(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("test_case_id", sa.String(36), sa.ForeignKey("test_cases.id")),
        sa.Column("variant", sa.String(30), nullable=False, server_default="migrated"),
        sa.Column("test_name", sa.String(500), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("message", sa.Text()),
        sa.Column("output", sa.Text()),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("flaky", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "build_runs",
        id_column(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("variant", sa.String(30), nullable=False, server_default="migrated"),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("exit_code", sa.Integer()),
        sa.Column("logs", sa.Text()),
        sa.Column("artifacts", sa.JSON(), nullable=False),
    )
    op.create_table(
        "risk_assessments",
        id_column(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("score", sa.String(30), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("breakdown", sa.JSON(), nullable=False),
    )
    op.create_table(
        "reports",
        id_column(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
    )
    op.create_table(
        "approvals",
        id_column(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("justification", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", name="uq_approvals_run_id"),
    )
    op.create_table(
        "test_integrity_results",
        id_column(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("path", sa.String(500), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(30), nullable=False),
        sa.Column("evidence", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "audit_log",
        id_column(),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(255), nullable=False),
        sa.Column("entity_id", sa.String(36)),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "run_stages",
        id_column(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("stage_name", stage_name, nullable=False),
        sa.Column("status", stage_status, nullable=False),
        sa.Column("started_at", sa.DateTime()),
        sa.Column("finished_at", sa.DateTime()),
        sa.Column("error", sa.Text()),
        sa.Column("evidence_reference", sa.String(500)),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("run_id", "stage_name", name="uq_run_stages_run_stage"),
    )
    op.create_index("ix_run_stages_run_id", "run_stages", ["run_id"])
    op.create_table(
        "llm_interactions",
        id_column(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id")),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("redacted_prompt", sa.Text(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("tokens", sa.Integer()),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "report_shares",
        id_column(),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

def downgrade() -> None:
    op.drop_table("run_stages")
    op.drop_table("llm_interactions")
    op.drop_table("report_shares")
    op.drop_table("audit_log")
    op.drop_table("test_integrity_results")
    op.drop_table("approvals")
    op.drop_table("reports")
    op.drop_table("risk_assessments")
    op.drop_table("build_runs")
    op.drop_table("test_results")
    op.drop_table("test_cases")
    op.drop_table("analysis_findings")
    op.drop_table("migration_changes")
    op.drop_table("repo_snapshots")
    op.drop_table("migration_runs")
    op.drop_table("projects")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
