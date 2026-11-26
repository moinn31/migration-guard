import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from backend.db import Base
from backend.models import User, Project, MigrationRun, TestCase as Case, TestResult
from backend.main import delete_project_endpoint


@pytest.mark.asyncio
async def test_deletion_handles_project_scoped_tests_and_preserves_other_projects(monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    @event.listens_for(engine.sync_engine, 'connect')
    def enforce_foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    # This test checks database deletion only, without touching a real workspace.
    import backend.main as main
    monkeypatch.setattr(main, 'get_project_dir', lambda _: (_ for _ in ()).throw(RuntimeError('No filesystem cleanup in this test')))
    async with sessions() as db:
        user = User(email='delete@example.com', password_hash='test')
        db.add(user)
        await db.flush()
        target = Project(owner_id=user.id, name='target')
        other = Project(owner_id=user.id, name='keep')
        db.add_all([target, other])
        await db.flush()
        run = MigrationRun(project_id=target.id, created_by=user.id)
        case = Case(project_id=target.id, name='test')
        keep_case = Case(project_id=other.id, name='keep')
        db.add_all([run, case, keep_case])
        await db.flush()
        db.add(TestResult(run_id=run.id, test_case_id=case.id, status='pass'))
        await db.commit()
        result = await delete_project_endpoint(target.id, user, db)
        assert result['status'] == 'deleted'
        assert await db.scalar(select(Project.id).where(Project.id == target.id)) is None
        assert await db.scalar(select(Case.id).where(Case.id == case.id)) is None
        assert await db.scalar(select(Project.id).where(Project.id == other.id)) == other.id
        assert await db.scalar(select(Case.id).where(Case.id == keep_case.id)) == keep_case.id
    await engine.dispose()
