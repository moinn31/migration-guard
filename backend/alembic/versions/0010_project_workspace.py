"""Bring imported-project workspace schema in line with the models."""
from alembic import op
import sqlalchemy as sa

revision = '0010_project_workspace'
down_revision = '0009_migration_engine'
branch_labels = None
depends_on = None

COLUMNS = {
    'repository_id': sa.String(100), 'repository_owner': sa.String(100),
    'repository_name': sa.String(255), 'default_branch': sa.String(100),
    'requested_branch': sa.String(100), 'azure_execution_id': sa.String(255),
    'status_message': sa.String(500), 'error_message': sa.Text(), 'node_analysis': sa.JSON(),
}

def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column['name'] for column in inspector.get_columns('migration_runs')}
    for name, column_type in COLUMNS.items():
        if name not in existing:
            op.add_column('migration_runs', sa.Column(name, column_type, nullable=True))
    if bind.dialect.name == 'postgresql' and any(item['name'] == 'runstate' for item in inspector.get_enums()):
        # Existing deployments use a native PostgreSQL enum.
        with op.get_context().autocommit_block():
            for value in ('QUEUED', 'STARTING', 'CLONING', 'COMPLETED', 'MIGRATING'):
                op.execute(sa.text(f"ALTER TYPE runstate ADD VALUE IF NOT EXISTS '{value}'"))
    if 'project_files' not in inspector.get_table_names():
        op.create_table('project_files',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False),
            sa.Column('run_id', sa.String(36), sa.ForeignKey('migration_runs.id')),
            sa.Column('path', sa.String(1000), nullable=False),
            sa.Column('content', sa.Text()),
            sa.Column('size_bytes', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('is_binary', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False))
    indexes = {item['name'] for item in sa.inspect(bind).get_indexes('project_files')}
    for name in ('project_id', 'run_id', 'path'):
        index = 'ix_project_files_' + name
        if index not in indexes:
            op.create_index(index, 'project_files', [name])
    # Older auth provisioned every Clerk identity as admin, including forged identities.
    op.execute(sa.text("UPDATE users SET role = 'developer' WHERE role = 'admin' AND password_hash = 'clerk_managed'"))

def downgrade():
    op.drop_table('project_files')
    for name in reversed(COLUMNS):
        op.drop_column('migration_runs', name)
    # PostgreSQL enum labels are retained to avoid rewriting existing rows.
