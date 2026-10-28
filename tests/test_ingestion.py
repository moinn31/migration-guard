from pathlib import Path
import zipfile

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db import Base
from backend.ingestion import IngestionError, create_snapshot_and_findings, extract_zip, validate_github_url

ROOT = Path(__file__).parents[1]


def test_rejects_ssrf_urls():
    for url in (
        "http://github.com/acme/repo",
        "https://localhost/acme/repo",
        "https://127.0.0.1/acme/repo",
        "file:///C:/repo",
        "ssh://git@github.com/acme/repo",
        "https://user:password@github.com/acme/repo",
    ):
        with pytest.raises(IngestionError):
            validate_github_url(url)


def test_rejects_zip_slip(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../../escaped.txt", "no")
    with pytest.raises(IngestionError):
        extract_zip(archive, tmp_path / "workspace")


@pytest.mark.asyncio
async def test_snapshot_persists_real_hash_and_path(tmp_path):
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as output:
        for path in (ROOT / "examples" / "clean-java8").rglob("*"):
            if path.is_file():
                output.write(path, path.relative_to(ROOT / "examples" / "clean-java8").as_posix())
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        snapshot = await create_snapshot_and_findings(db, "project-1", "run-1", None, archive)
        assert snapshot.commit_sha.startswith("zip:")
        assert len(snapshot.content_hash) == 64
        assert Path(snapshot.snapshot_path).is_dir()
        assert snapshot.snapshot_metadata["build_system"] == "maven"
    await engine.dispose()
