import httpx
import pytest

@pytest.mark.asyncio
async def test_workspace_commands_require_explicit_execution_and_ownership(approval_client, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, 'workspace_execution_enabled', False)
    client, _, _, _ = approval_client
    projects = (await client.get('/projects')).json()
    project_id = projects[0]['id']
    disabled = await client.post(f'/api/projects/{project_id}/terminal/jobs', json={'command': 'echo test'})
    assert disabled.status_code == 503
    unauthorized = await client.post('/api/projects/other/terminal/jobs', json={'command': 'echo test'})
    assert unauthorized.status_code == 404
    assert (await client.get(f'/api/projects/{project_id}/terminal/jobs')).json() == []

@pytest.mark.asyncio
async def test_workspace_chat_returns_actual_agent_response(approval_client, monkeypatch):
    from backend import camber_service
    from backend.config import settings
    monkeypatch.setattr(settings, 'camber_chat_agent', 'test-agent')
    monkeypatch.setattr(settings, 'camber_mcp_access_token', 'test-token')
    async def ask(tag, message):
        assert 'Explain this project' in message
        return 'Response from the configured agent'
    monkeypatch.setattr(camber_service, 'ask_agent', ask)
    client, _, _, _ = approval_client
    project_id = (await client.get('/projects')).json()[0]['id']
    response = await client.post(f'/api/projects/{project_id}/chat', json={'message': 'Explain this project'})
    assert response.status_code == 200
    assert response.json()['reply'] == 'Response from the configured agent'

@pytest.mark.asyncio
async def test_local_assistant_and_workspace_capabilities(approval_client, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, 'camber_chat_agent', None)
    monkeypatch.setattr(settings, 'workspace_execution_enabled', False)
    client, _, _, _ = approval_client
    project_id = (await client.get('/projects')).json()[0]['id']
    monkeypatch.setattr(settings, 'project_previews', {project_id: 'http://127.0.0.1:8080'})
    workspace = (await client.get(f'/api/projects/{project_id}/workspace')).json()
    assert workspace['preview_url'] == 'http://127.0.0.1:8080'
    assert workspace['terminal_enabled'] is False
    response = await client.post(f'/api/projects/{project_id}/chat', json={'message': 'Summarize verification coverage'})
    assert response.status_code == 200
    assert response.json()['mode'] == 'local_analysis'
    assert 'No verification report' in response.json()['reply']
    assert (await client.get('/api/projects/other/workspace')).status_code == 404

@pytest.mark.asyncio
async def test_benchmarks_do_not_invent_measurements(approval_client):
    client, _, _, _ = approval_client
    response = await client.get('/benchmarks')
    assert response.status_code == 200
    assert response.json()['items'] == []
    assert response.json()['metrics']['build_success_rate'] is None

@pytest.mark.asyncio
async def test_configured_azure_workspace_is_used_instead_of_host(approval_client, monkeypatch):
    from backend import main
    from backend.config import settings
    client, _, _, _ = approval_client
    project_id = (await client.get('/projects')).json()[0]['id']
    monkeypatch.setattr(settings, 'workspace_execution_enabled', True)
    monkeypatch.setattr(settings, 'azure_workspaces', {project_id: {'url': 'https://workspace.example', 'token': 'test'}})
    calls = []
    async def remote(project, method, path, body=None):
        calls.append((method, path))
        assert project == project_id
        if path == '/status':
            return {'initialized': True}
        job = {'id': 'remote-job', 'command': 'npm test', 'status': 'running', 'output': '', 'terminal_id': 'test'}
        return [job] if method == 'GET' else job
    monkeypatch.setattr(main, 'remote_workspace', remote)
    started = await client.post(f'/api/projects/{project_id}/terminal/jobs', json={'command': 'npm test'})
    assert started.status_code == 202
    assert started.json()['id'] == 'remote-job'
    assert (await client.get(f'/api/projects/{project_id}/terminal/jobs')).json()[0]['id'] == 'remote-job'
    assert (await client.delete(f'/api/projects/{project_id}/terminal/jobs/remote-job')).status_code == 200
    assert ('DELETE', '/commands/remote-job') in calls
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend import auth
from backend.db import Base
from backend.main import app
from backend.models import MigrationRun, Project, Role, RunState, User


@pytest.fixture
async def approval_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async with sessions() as db:
        user = User(email="developer@example.com", password_hash="hash", role=Role.developer)
        db.add(user)
        await db.flush()
        project = Project(owner_id=user.id, name="fixture", repository_url=None)
        db.add(project)
        await db.flush()
        run = MigrationRun(
            project_id=project.id,
            created_by=user.id,
            state=RunState.AWAITING_APPROVAL,
            verdict="NEEDS_REVIEW",
        )
        db.add(run)
        await db.commit()
        run_id = run.id

    async def override_db():
        async with sessions() as db:
            yield db

    selected_role = {"value": Role.developer}

    async def override_user():
        async with sessions() as db:
            current = await db.get(User, user.id)
            current.role = selected_role["value"]
            return current

    app.dependency_overrides[auth.get_db] = override_db
    app.dependency_overrides[auth.current_user] = override_user
    # main imported the same dependency function object as auth.get_db.
    from backend import main
    app.dependency_overrides[main.get_db] = override_db
    app.dependency_overrides[main.current_user] = override_user
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, run_id, user.id, selected_role
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_needs_review_requires_justification_and_double_approval_is_idempotent(approval_client):
    client, run_id, _, _ = approval_client
    missing = await client.post(f"/runs/{run_id}/approval", json={"decision": "approved"})
    assert missing.status_code == 422

    approved = await client.post(
        f"/runs/{run_id}/approval",
        json={"decision": "approved", "justification": "Reviewed the evidence."},
    )
    assert approved.status_code == 200
    repeated = await client.post(
        f"/runs/{run_id}/approval",
        json={"decision": "approved", "justification": "Same decision."},
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == approved.json()["id"]

    conflict = await client.post(
        f"/runs/{run_id}/approval", json={"decision": "rejected"}
    )
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_viewer_cannot_approve(approval_client):
    client, run_id, _, selected_role = approval_client
    selected_role["value"] = Role.viewer
    response = await client.post(
        f"/runs/{run_id}/approval", json={"decision": "rejected"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_report_export_and_share_paths(approval_client):
    client, run_id, _, _ = approval_client
    html = await client.get(f"/runs/{run_id}/report.html")
    assert html.status_code == 200
    assert "<html>" in html.text
    patch = await client.get(f"/runs/{run_id}/export/patch")
    assert patch.status_code == 200
    share = await client.post(f"/runs/{run_id}/report/share")
    assert share.status_code == 200
    shared = await client.get(share.json()["url"])
    assert shared.status_code == 200
    pdf = await client.get(f"/runs/{run_id}/report.pdf")
    assert pdf.status_code in {200, 503}
