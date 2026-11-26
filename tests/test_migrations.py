import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


EXPECTED_TABLES = {
    "users", "projects", "migration_runs", "repo_snapshots", "migration_changes",
    "analysis_findings", "test_cases", "test_results", "build_runs",
    "risk_assessments", "reports", "approvals", "test_integrity_results",
    "audit_log", "run_stages", "llm_interactions", "report_shares",
    "project_files",
}


def run_upgrade(url: str) -> set[str]:
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, "head")
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_alembic_upgrade_fresh_sqlite(tmp_path):
    url = f"sqlite:///{tmp_path / 'migrationguard.db'}"
    tables = run_upgrade(url)
    assert EXPECTED_TABLES <= tables
    engine = create_engine(url)
    try:
        columns = {item['name'] for item in inspect(engine).get_columns('migration_runs')}
        assert {'repository_id', 'azure_execution_id', 'status_message', 'node_analysis'} <= columns
    finally:
        engine.dispose()


@pytest.mark.integration
def test_alembic_upgrade_fresh_postgresql():
    url = os.getenv("MIGRATIONGUARD_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set MIGRATIONGUARD_TEST_POSTGRES_URL to run the PostgreSQL migration check.")
    tables = run_upgrade(url)
    assert EXPECTED_TABLES <= tables
