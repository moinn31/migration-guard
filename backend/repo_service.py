import json
import asyncio
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .git_client import clone_shallow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import SessionLocal
from .models import MigrationRun, Project, ProjectFile, RunState
from .ingestion import validate_github_url, MAX_FILES, MAX_BYTES
from .observability import redact
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Extensions to read as text and save in Neon Postgres
TEXT_EXTENSIONS = {
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".json", ".json5", ".yaml", ".yml",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".md", ".mdx", ".txt", ".svg",
    ".env", ".example", ".gitignore", ".gitattributes",
    ".dockerignore", "Dockerfile", "Makefile"
}

IGNORE_DIRS = {
    ".git", "node_modules", ".next", "dist", "build",
    ".turbo", ".cache", "coverage", ".pytest_cache", ".venv", "venv"
}

MAX_FILE_SIZE = 1024 * 1024  # 1 MB max per individual file for database storage


def detect_node_configuration(repo_root: Path) -> Dict[str, Any]:
    analysis: Dict[str, Any] = {
        "node_version": "Unknown (Defaults to >=18.0.0)",
        "package_manager": "npm",
        "lockfile": None,
        "frameworks": [],
        "dependencies": {},
        "devDependencies": {},
        "scripts": {},
    }

    # 1. Detect package manager from lockfiles
    if (repo_root / "pnpm-lock.yaml").exists():
        analysis["package_manager"] = "pnpm"
        analysis["lockfile"] = "pnpm-lock.yaml"
    elif (repo_root / "yarn.lock").exists():
        analysis["package_manager"] = "yarn"
        analysis["lockfile"] = "yarn.lock"
    elif (repo_root / "bun.lockb").exists():
        analysis["package_manager"] = "bun"
        analysis["lockfile"] = "bun.lockb"
    elif (repo_root / "package-lock.json").exists():
        analysis["package_manager"] = "npm"
        analysis["lockfile"] = "package-lock.json"

    # 2. Detect Node.js versions
    if (repo_root / ".nvmrc").exists():
        try:
            analysis["node_version"] = (repo_root / ".nvmrc").read_text(encoding="utf-8").strip()
        except Exception:
            pass
    elif (repo_root / ".node-version").exists():
        try:
            analysis["node_version"] = (repo_root / ".node-version").read_text(encoding="utf-8").strip()
        except Exception:
            pass

    # 3. Parse package.json
    pkg_path = repo_root / "package.json"
    if pkg_path.exists():
        try:
            pkg_data = json.loads(pkg_path.read_text(encoding="utf-8", errors="replace"))
            analysis["name"] = pkg_data.get("name", "app")
            analysis["version"] = pkg_data.get("version", "1.0.0")

            # Check engines.node
            engines = pkg_data.get("engines", {})
            if "node" in engines:
                analysis["node_version"] = engines["node"]

            analysis["scripts"] = pkg_data.get("scripts", {})
            deps = pkg_data.get("dependencies", {})
            dev_deps = pkg_data.get("devDependencies", {})
            analysis["dependencies"] = deps
            analysis["devDependencies"] = dev_deps

            # Framework detection
            all_deps = {**deps, **dev_deps}
            frameworks = []
            if "next" in all_deps:
                frameworks.append(f"Next.js ({all_deps['next']})")
            if "react" in all_deps and "next" not in all_deps:
                frameworks.append(f"React ({all_deps['react']})")
            if "express" in all_deps:
                frameworks.append(f"Express ({all_deps['express']})")
            if "fastify" in all_deps:
                frameworks.append(f"Fastify ({all_deps['fastify']})")
            if "@nestjs/core" in all_deps:
                frameworks.append(f"NestJS ({all_deps['@nestjs/core']})")
            if "vite" in all_deps:
                frameworks.append(f"Vite ({all_deps['vite']})")
            if "vue" in all_deps:
                frameworks.append(f"Vue ({all_deps['vue']})")
            if "tailwindcss" in all_deps:
                frameworks.append(f"Tailwind CSS ({all_deps['tailwindcss']})")
            if "typescript" in all_deps:
                frameworks.append("TypeScript")

            analysis["frameworks"] = frameworks
        except Exception as e:
            logger.warning(f"Error reading package.json: {e}")

    return analysis


async def clone_and_persist_repository(
    project_id: str,
    run_id: str,
    repository_url: str,
    branch: Optional[str] = None,
    github_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Clones the repository and stores all its source files directly into
    Neon PostgreSQL (project_files table) so that the user can browse
    the files in the workspace and resume work anytime.
    """
    temp_dir = tempfile.mkdtemp(prefix=f"migrationguard-{run_id}-")
    target_path = Path(temp_dir)

    async with SessionLocal() as db:
        run = await db.get(MigrationRun, run_id)
        if run:
            run.state = RunState.CLONING
            run.error_message = None
            run.status_message = "Connecting to GitHub & cloning repository..."
            await db.commit()

    try:
        clone_url = await asyncio.to_thread(validate_github_url, repository_url)
        if github_token:
            clean_url = clone_url.replace("https://", "").replace("http://", "")
            clone_url = f"https://x-access-token:{quote(github_token, safe='')}@{clean_url}"

        logger.info(f"Cloning {repository_url} into {temp_dir}")
        await asyncio.to_thread(clone_shallow, clone_url, target_path, branch=branch, timeout=120)

        # Update status to ANALYZING
        async with SessionLocal() as db:
            run = await db.get(MigrationRun, run_id)
            if run:
                run.state = RunState.ANALYZING
                run.status_message = "Detecting Node.js configuration & saving files to database..."
                await db.commit()

        # Detect Node.js structure
        node_analysis = detect_node_configuration(target_path)

        # Traverse and collect files
        files_to_store: List[ProjectFile] = []
        total_bytes = 0
        for root, dirs, files in os.walk(target_path):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for file_name in files:
                file_full = Path(root) / file_name
                if file_full.is_symlink() or not file_full.resolve().is_relative_to(target_path.resolve()):
                    continue
                rel_path = file_full.relative_to(target_path).as_posix()

                try:
                    file_size = file_full.stat().st_size
                except OSError:
                    file_size = 0
                total_bytes += file_size
                if len(files_to_store) >= MAX_FILES or total_bytes > MAX_BYTES:
                    raise ValueError('Repository exceeds import size limits')

                content: Optional[str] = None
                is_binary = True

                if file_size <= MAX_FILE_SIZE:
                    try:
                        with open(file_full, "rb") as bf:
                            chunk = bf.read(8192)
                            if b"\x00" not in chunk:
                                content = file_full.read_text(encoding="utf-8", errors="replace")
                                is_binary = False
                    except Exception:
                        content = None
                        is_binary = True

                files_to_store.append(
                    ProjectFile(
                        project_id=project_id,
                        run_id=run_id,
                        path=rel_path,
                        content=content,
                        size_bytes=file_size,
                        is_binary=is_binary,
                    )
                )

        # Batch insert files into Neon PostgreSQL
        async with SessionLocal() as db:
            from sqlalchemy import delete
            await db.execute(delete(ProjectFile).where(ProjectFile.project_id == project_id))
            db.add_all(files_to_store)

            # Update MigrationRun to COMPLETED
            run = await db.get(MigrationRun, run_id)
            if run:
                run.state = RunState.COMPLETED
                run.error_message = None
                run.status_message = f"Successfully imported {len(files_to_store)} files to Neon database"
                run.node_analysis = node_analysis
            await db.commit()

        logger.info(f"Persisted {len(files_to_store)} files to Neon database for project {project_id}")
        return node_analysis

    except Exception as e:
        message = redact(str(e).replace(github_token, '[REDACTED]') if github_token else str(e))
        logger.error("Error cloning repository: %s", message)
        async with SessionLocal() as db:
            run = await db.get(MigrationRun, run_id)
            if run:
                run.state = RunState.FAILED
                run.status_message = f"Cloning failed: {message}"[:500]
                run.error_message = message
                await db.commit()
        raise RuntimeError('Repository import failed; inspect the redacted run error') from None

    finally:
        # Cleanup temporary clone files from host memory/disk
        if target_path.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
