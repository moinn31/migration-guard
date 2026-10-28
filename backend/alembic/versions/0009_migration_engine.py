"""Persist migration engine metadata and migrating stage."""

from alembic import op
import sqlalchemy as sa

revision = "0009_migration_engine"
down_revision = "0008_verdict_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {
        "migration_runs": [
            sa.Column("verdict", sa.String(40), nullable=True),
        ],
        "migration_changes": [
            sa.Column("source", sa.String(30), nullable=False, server_default="rule"),
            sa.Column("rule_id", sa.String(120), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="proposed"),
            sa.Column("protected", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("unnecessary_change", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("changed_lines_ratio", sa.Float(), nullable=True),
            sa.Column("before_content", sa.Text(), nullable=True),
            sa.Column("after_content", sa.Text(), nullable=True),
        ],
    }
    for table, additions in columns.items():
        existing = {item["name"] for item in inspector.get_columns(table)}
        for column in additions:
            if column.name not in existing:
                op.add_column(table, column)
    if "llm_interactions" not in inspector.get_table_names():
        op.create_table(
            "llm_interactions",
            sa.Column("id", sa.String(36), primary_key=True),
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
    if "report_shares" not in inspector.get_table_names():
        op.create_table(
            "report_shares",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("run_id", sa.String(36), sa.ForeignKey("migration_runs.id"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        )


def downgrade() -> None:
    pass
