import os
import subprocess
import tempfile
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import ProjectFile, Project

logger = logging.getLogger(__name__)

WORKSPACES_ROOT = Path(tempfile.gettempdir()) / "migrationguard_workspaces"
WORKSPACES_ROOT.mkdir(parents=True, exist_ok=True)


def get_project_dir(project_id: str) -> Path:
    proj_dir = WORKSPACES_ROOT / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    return proj_dir


async def hydrate_project_files_if_needed(project_id: str, db: AsyncSession) -> Path:
    """
    Ensures the workspace folder on disk contains all files stored in
    Neon PostgreSQL so that commands like 'ls', 'npm install', or 'pip install'
    operate directly on the latest project files.
    """
    proj_dir = get_project_dir(project_id)
    files = list((await db.scalars(
        select(ProjectFile).where(ProjectFile.project_id == project_id)
    )).all())

    for f in files:
        file_path = (proj_dir / f.path).resolve()
        if not file_path.is_relative_to(proj_dir.resolve()):
            raise ValueError("Stored file path escapes the project workspace.")
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            if f.content is not None:
                file_path.write_text(f.content, encoding="utf-8", errors="replace")
            else:
                # If binary or empty, create file if not exists
                if not file_path.exists():
                    file_path.touch()

    return proj_dir


def execute_shell_command(
    command: str,
    cwd: Path,
    timeout_seconds: int = 45
) -> Tuple[str, int]:
    """
    Executes a command inside the project directory using powershell / cmd.
    Captures stdout and stderr, returns (output, exit_code).
    """
    cmd = command.strip()
    if not cmd:
        return ("", 0)

    # Shell execution on Windows
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=True,
            text=True,
            errors="replace"
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            exit_code = process.returncode
            combined = ""
            if stdout:
                combined += stdout
            if stderr:
                if combined:
                    combined += "\n"
                combined += stderr
            return (combined or "(Command completed with no output)", exit_code)
        except subprocess.TimeoutExpired:
            process.kill()
            return (f"Command timed out after {timeout_seconds}s.", 124)
    except Exception as exc:
        return (f"Failed to execute command: {exc}", 1)


async def analyze_project_context(project_id: str, db: AsyncSession) -> Dict[str, Any]:
    """
    Reading Agent: Reads all configuration and source files from Neon PostgreSQL,
    detects languages, package managers, frameworks, and docker services,
    and returns a structured context plan with required install commands.
    """
    files = list((await db.scalars(
        select(ProjectFile).where(ProjectFile.project_id == project_id)
    )).all())

    file_paths = [f.path for f in files]
    file_map = {f.path: f.content for f in files if f.content is not None}

    detected_stack: List[str] = []
    manifests_found: List[str] = []
    recommended_commands: List[str] = []
    details: Dict[str, Any] = {}

    if 'pom.xml' in file_map:
        manifests_found.append('pom.xml')
        detected_stack.extend(['Java', 'Maven'])
        recommended_commands.append('mvn test')
        try:
            pom = ET.fromstring(file_map['pom.xml'])
            def value(name):
                return next((node.text.strip() for node in pom.iter() if node.tag.rsplit('}', 1)[-1] == name and node.text), None)
            details['java_target'] = value('maven.compiler.release') or value('maven.compiler.target') or value('maven.compiler.source')
            details['artifact'] = value('artifactId')
            details['package_manager'] = 'maven'
            details['java_files'] = [path for path in file_paths if path.endswith('.java')]
            details['test_files'] = [path for path in details['java_files'] if '/test/' in path]
            import re
            details['route_hints'] = sorted({match for path, source in file_map.items() if path.startswith('src/main/') and path.endswith('.java') for match in re.findall(r'"(/[A-Za-z0-9_/-]*)"', source)})
        except ET.ParseError:
            details['manifest_error'] = 'pom.xml could not be parsed'

    # 1. Node.js Ecosystem
    if "package.json" in file_map:
        manifests_found.append("package.json")
        detected_stack.append("Node.js / JavaScript")
        try:
            pkg = json.loads(file_map["package.json"])
            deps = pkg.get("dependencies", {})
            dev_deps = pkg.get("devDependencies", {})
            details["dependencies"] = deps
            details["devDependencies"] = dev_deps
            details["scripts"] = pkg.get("scripts", {})

            if "next" in deps or "next" in dev_deps:
                detected_stack.append("Next.js")
            if "react" in deps or "react" in dev_deps:
                detected_stack.append("React")
            if "express" in deps:
                detected_stack.append("Express.js")

            # Determine package manager
            if "pnpm-lock.yaml" in file_paths:
                recommended_commands.append("pnpm install")
                details["package_manager"] = "pnpm"
            elif "yarn.lock" in file_paths:
                recommended_commands.append("yarn install")
                details["package_manager"] = "yarn"
            elif "bun.lockb" in file_paths:
                recommended_commands.append("bun install")
                details["package_manager"] = "bun"
            else:
                recommended_commands.append("npm install")
                details["package_manager"] = "npm"
        except Exception:
            recommended_commands.append("npm install")

    # 2. Python Ecosystem
    if "requirements.txt" in file_paths:
        manifests_found.append("requirements.txt")
        detected_stack.append("Python")
        recommended_commands.append("pip install -r requirements.txt")
        req_content = file_map.get("requirements.txt", "")
        details["python_requirements"] = [
            line.strip() for line in req_content.splitlines() if line.strip() and not line.startswith("#")
        ][:25]

    if "pyproject.toml" in file_paths:
        manifests_found.append("pyproject.toml")
        detected_stack.append("Python (pyproject.toml)")
        if not any("pip install" in cmd for cmd in recommended_commands):
            recommended_commands.append("pip install .")

    if "Pipfile" in file_paths:
        manifests_found.append("Pipfile")
        recommended_commands.append("pipenv install")

    # 3. Docker & Containers
    if "docker-compose.yml" in file_paths or "docker-compose.yaml" in file_paths:
        manifests_found.append("docker-compose.yml")
        detected_stack.append("Docker Compose")
    if "Dockerfile" in file_paths:
        manifests_found.append("Dockerfile")
        detected_stack.append("Docker Container")

    # 4. Environment
    if ".env.example" in file_paths and ".env" not in file_paths:
        manifests_found.append(".env.example")
        recommended_commands.insert(0, "copy .env.example .env" if os.name == "nt" else "cp .env.example .env")

    # Summary
    stack_label = ", ".join(detected_stack) if detected_stack else "Generic Codebase"
    summary = (
        f"Project analysis inspected {len(files)} stored files. "
        f"Detected environment: {stack_label}. "
        f"Found configuration manifests: {', '.join(manifests_found) or 'None'}. "
        f"Generated {len(recommended_commands)} dependency setup command(s)."
    )

    return {
        "project_id": project_id,
        "detected_stack": detected_stack,
        "manifest_files": manifests_found,
        "recommended_commands": recommended_commands,
        "context_summary": summary,
        "details": details,
    }
