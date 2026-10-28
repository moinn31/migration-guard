"""Persist verdict, approval justification, risk evidence, and applied changes."""

from alembic import op
import sqlalchemy as sa

revision = "0008_verdict_approval"
down_revision = "0007_real_ingestion_and_execution"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    additions = {
        "migration_runs": [sa.Column("verdict", sa.String(40), nullable=True)],
        "migration_changes": [sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.false())],
        "build_runs": [sa.Column("variant", sa.String(30), nullable=False, server_default="migrated")],
        "test_results": [sa.Column("variant", sa.String(30), nullable=False, server_default="migrated")],
        "risk_assessments": [sa.Column("breakdown", sa.JSON(), nullable=True)],
        "approvals": [sa.Column("justification", sa.Text(), nullable=True)],
    }
    for table, columns in additions.items():
        existing = {column["name"] for column in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    constraints = {item["name"] for item in inspector.get_unique_constraints("approvals")}
    if "uq_approvals_run_id" not in constraints:
        op.create_unique_constraint("uq_approvals_run_id", "approvals", ["run_id"])

def downgrade() -> None:
    pass
