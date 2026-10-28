import httpx
import pytest
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
