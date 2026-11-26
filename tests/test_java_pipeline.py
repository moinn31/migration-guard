"""Opt-in acceptance test: actual Java 8/17 Docker builds, real API and worker.

Only dispatch is captured so the test can await the real worker deterministically.
No build results, integrity checks, risk policy, reports or approvals are mocked.
"""
import io
import json
import os
from pathlib import Path
import zipfile

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend import main, migration_engine
from backend.config import settings
from backend.db import Base
from backend.models import Report, RepoSnapshot
from workers import runner

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.getenv('MIGRATIONGUARD_TEST_JAVA_PIPELINE') != '1',
    reason='Opt in with MIGRATIONGUARD_TEST_JAVA_PIPELINE=1 after preparing fixture images.')]
FIXTURE = Path(__file__).parent / 'fixtures/java8-orders'

@pytest.mark.asyncio
@pytest.mark.parametrize('scenario,expected', [
    ('clean', 'NEEDS_REVIEW'), ('weakened_assertion', 'NEEDS_REVIEW'),
    ('deleted_test', 'UNSAFE'), ('regression', 'UNSAFE'), ('execution_disabled', 'INCONCLUSIVE'),
])
async def test_java_migration_acceptance(tmp_path, monkeypatch, scenario, expected):
    output = Path(os.getenv('MIGRATIONGUARD_ACCEPTANCE_OUTPUT', 'results/java-acceptance')).resolve()
    output.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, 'workspace_root', str(output / 'builds'))
    monkeypatch.setattr(settings, 'maven_image_template', 'migrationguard-fixture-java{java_version}:local')
    monkeypatch.setattr(settings, 'maven_repository_path', '/opt/maven-repository')
    monkeypatch.setattr(settings, 'maven_offline', True)
    monkeypatch.setattr(settings, 'maven_mirror', None)
    monkeypatch.setattr(settings, 'openrewrite_enabled', False)
    monkeypatch.setattr(settings, 'migrationguard_enable_execution', scenario != 'execution_disabled')
    monkeypatch.setattr(settings, 'migration_dry_run', False)
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "acceptance.db"}')
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(runner, 'SessionLocal', sessions)
    queued = []
    monkeypatch.setattr(main, 'enqueue_run', lambda run_id, zip_path=None: queued.append((run_id, zip_path)))
    async def database():
        async with sessions() as session:
            yield session
    main.app.dependency_overrides[main.get_db] = database
    original_migrate = migration_engine.migrate_snapshot
    def controlled_variant(*args, **kwargs):
        working, changes, rewrite = original_migrate(*args, **kwargs)
        test = working / 'src/test/java/example/OrderTest.java'
        if scenario == 'weakened_assertion':
            test.write_text(test.read_text().replace('assertEquals(100, Order.total(25, 4));', 'assertNotNull(Order.total(25, 4));'))
        elif scenario == 'deleted_test':
            test.write_text(test.read_text().replace('@Test(expected = IllegalArgumentException.class) public void rejectsNegativeQuantity() {\n        Order.total(25, -1);\n    }', ''))
        elif scenario == 'regression':
            source = working / 'src/main/java/example/Order.java'
            source.write_text(source.read_text().replace('unitPrice * quantity', 'unitPrice + quantity'))
        return working, changes, rewrite
    monkeypatch.setattr(runner, 'migrate_snapshot', controlled_variant)
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as zipped:
        for path in FIXTURE.rglob('*'):
            if path.is_file() and path.name != 'Dockerfile':
                zipped.write(path, path.relative_to(FIXTURE).as_posix())
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://acceptance') as client:
            registered = await client.post('/auth/register', json={'email': f'{scenario}@example.com', 'password': 'fixture-password-for-testing'})
            assert registered.status_code == 200, registered.text
            client.headers['Authorization'] = 'Bearer ' + registered.json()['access_token']
            created = await client.post('/projects', json={'name': scenario})
            assert created.status_code == 200, created.text
            submitted = await client.post(f'/projects/{created.json()["id"]}/runs/upload', files={'upload': ('orders.zip', archive.getvalue(), 'application/zip')})
            assert submitted.status_code == 202, submitted.text
            run_id = submitted.json()['id']
            assert len(queued) == 1 and queued[0][0] == run_id
            await runner.advance_run(*queued[0])
            async with sessions() as db:
                persisted = await db.scalar(select(Report).where(Report.run_id == run_id))
                assert persisted is not None, 'Worker must persist a report even for failed/skipped builds'
                snapshot = await db.scalar(select(RepoSnapshot).where(RepoSnapshot.run_id == run_id))
                migration_engine.verify_snapshot(snapshot.snapshot_path, snapshot.content_hash)
            response = await client.get(f'/runs/{run_id}/report')
            assert response.status_code == 200, response.text
            report = response.json()['content']
            assert report['verdict']['value'] == expected, report
            if scenario != 'execution_disabled':
                assert {build['variant'] for build in report['builds']} == {'baseline', 'migrated'}
                migrated = next(build for build in report['builds'] if build['variant'] == 'migrated')
                baseline = next(build for build in report['builds'] if build['variant'] == 'baseline')
                assert set(baseline['artifacts']['class_major_versions'].values()) == {52}
                assert set(migrated['artifacts']['class_major_versions'].values()) == {61}
                for build in report['builds']:
                    assert build['artifacts']['network'] == 'none'
                    assert (Path(build['artifacts']['directory']) / 'build.log').is_file()
                    assert list(Path(build['artifacts']['surefire_reports']).rglob('*.xml'))
            else:
                assert all(build['status'] == 'SKIPPED' for build in report['builds'])
            if scenario == 'weakened_assertion':
                assert any(item['code'] == 'ASSERTION_WEAKENED' for item in report['integrity_findings'])
            if scenario == 'deleted_test':
                assert any(item['code'] == 'TESTS_DELETED' for item in report['integrity_findings'])
            approval = await client.post(f'/runs/{run_id}/approval', json={'decision': 'approved'})
            assert approval.status_code == (422 if expected == 'NEEDS_REVIEW' else 409), approval.text
            if scenario == 'clean':
                approved = await client.post(f'/runs/{run_id}/approval', json={'decision': 'approved', 'justification': 'Reviewed passing build/test evidence and missing coverage limitation.'})
                assert approved.status_code == 200, approved.text
                assert (await client.get(f'/runs/{run_id}')).json()['state'] == 'ACCEPTED'
            (output / f'{scenario}.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(f'\n{scenario}: {expected}; original snapshot preserved; approval guard enforced')
    finally:
        main.app.dependency_overrides.pop(main.get_db, None)
        for _, path in queued:
            if path:
                Path(path).unlink(missing_ok=True)
        await engine.dispose()
