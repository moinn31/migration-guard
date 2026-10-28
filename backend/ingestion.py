from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import ipaddress
import os
import shutil
import socket
import stat
import tempfile
import asyncio
from urllib.parse import urlparse
import zipfile

from git import Repo
from sqlalchemy.ext.asyncio import AsyncSession

from .analyzer import Finding, analyze_repository
from .models import AnalysisFinding, RepoSnapshot

MAX_FILES = 20_000
MAX_BYTES = 500 * 1024 * 1024
MAX_CLONE_SECONDS = 120
MAX_COMPRESSION_RATIO = 100


class IngestionError(ValueError):
    pass


def validate_github_url(repository_url: str) -> str:
    parsed = urlparse(repository_url or "")
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        raise IngestionError("Only https://github.com repository URLs are accepted.")
    if parsed.username or parsed.password or not parsed.path.strip("/"):
        raise IngestionError("Repository URL must not contain credentials and must name a repository.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise IngestionError("Repository host could not be resolved.") from exc
    if any(ipaddress.ip_address(address).is_private or ipaddress.ip_address(address).is_loopback or ipaddress.ip_address(address).is_link_local for address in addresses):
        raise IngestionError("Repository host resolves to a private or local address.")
    return repository_url


def _content_hash(root: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    total = 0
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        count += 1
        total += path.stat().st_size
        if count > MAX_FILES or total > MAX_BYTES:
            raise IngestionError("Repository exceeds file-count or content-size limits.")
        digest.update(path.relative_to(root).as_posix().encode())
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest(), count, total


def _make_read_only(root: Path) -> None:
    for path in root.rglob("*"):
        try:
            mode = path.stat().st_mode
            path.chmod(mode & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
        except OSError:
            continue


def copy_for_work(snapshot_path: str | Path, destination: str | Path | None = None) -> Path:
    source = Path(snapshot_path).resolve()
    target = Path(destination or tempfile.mkdtemp(prefix="migrationguard-work-")) / "working"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, dirs_exist_ok=False)
    return target


def clone_repository(repository_url: str, workspace: str | Path | None = None) -> tuple[Path, str, dict]:
    validate_github_url(repository_url)
    base = Path(workspace or tempfile.mkdtemp(prefix="migrationguard-"))
    base.mkdir(parents=True, exist_ok=True)
    target = base / "original"
    try:
        repo = Repo.clone_from(repository_url, target, depth=1, no_single_branch=False)
        commit_sha = repo.head.commit.hexsha
        content_hash, files, bytes_count = _content_hash(target)
        shutil.rmtree(target / ".git", ignore_errors=True)
        _make_read_only(target)
        return target, commit_sha, {"content_hash": content_hash, "file_count": files, "byte_count": bytes_count, "immutable": True}
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise


def extract_zip(upload_path: str | Path, workspace: str | Path | None = None) -> tuple[Path, str, dict]:
    base = Path(workspace or tempfile.mkdtemp(prefix="migrationguard-"))
    target = base / "original"
    target.mkdir(parents=True, exist_ok=True)
    total = 0
    count = 0
    with zipfile.ZipFile(upload_path) as archive:
        for member in archive.infolist():
            name = Path(member.filename)
            if name.is_absolute() or ".." in name.parts or member.filename.startswith(("\\", "/")):
                raise IngestionError("Zip archive contains a path traversal entry.")
            if member.is_dir():
                continue
            if member.compress_size and member.file_size / member.compress_size > MAX_COMPRESSION_RATIO:
                raise IngestionError("Zip archive contains an excessive compression ratio.")
            mode = (member.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise IngestionError("Zip archive contains a symbolic link.")
            count += 1
            total += member.file_size
            if count > MAX_FILES or total > MAX_BYTES:
                raise IngestionError("Zip archive exceeds file-count or uncompressed-size limits.")
            destination = (target / name).resolve()
            if target.resolve() not in destination.parents:
                raise IngestionError("Zip archive entry escapes the extraction directory.")
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as sink:
                shutil.copyfileobj(source, sink, 1024 * 1024)
    content_hash, files, bytes_count = _content_hash(target)
    _make_read_only(target)
    return target, f"zip:{content_hash}", {"content_hash": content_hash, "file_count": files, "byte_count": bytes_count, "immutable": True}


async def create_snapshot_and_findings(db: AsyncSession, project_id: str, run_id: str, repository_url: str | None, zip_path: str | Path | None = None) -> RepoSnapshot:
    if zip_path:
        snapshot_path, commit_sha, ingestion_metadata = extract_zip(zip_path)
    elif repository_url:
        try:
            snapshot_path, commit_sha, ingestion_metadata = await asyncio.wait_for(
                asyncio.to_thread(clone_repository, repository_url),
                timeout=MAX_CLONE_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise IngestionError("Repository clone exceeded the configured time limit.") from exc
    else:
        raise IngestionError("A Git URL or zip upload is required.")
    metadata, findings = analyze_repository(snapshot_path)
    metadata.update(ingestion_metadata)
    snapshot = RepoSnapshot(
        project_id=project_id, run_id=run_id, commit_sha=commit_sha,
        content_hash=ingestion_metadata["content_hash"], snapshot_path=str(snapshot_path),
        snapshot_metadata=metadata,
    )
    db.add(snapshot)
    for finding in findings:
        db.add(AnalysisFinding(
            run_id=run_id, severity=finding.severity, code=finding.code, message=finding.message,
            path=finding.path, line_number=finding.line_number, provenance=finding.provenance,
            confidence=finding.confidence, evidence=finding.evidence, note=finding.note,
        ))
    await db.flush()
    return snapshot
