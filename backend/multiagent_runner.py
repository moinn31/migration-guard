"""Multi-Agent System for MigrationGuard
Coordinates 3 specialized agents:
- Agent 1: Codebase & Dependency Analyzer (reads manifests, package.json, requirements.txt, languages, versions)
- Agent 2: Dependency Installer (creates non-interactive AI Terminal, runs npm install / pip install in Azure sandbox)
- Agent 3: Project Runner (starts app, connects preview window)
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from pathlib import Path
from sqlalchemy import select
from .db import SessionLocal
from .models import Project, ProjectFile, MigrationRun
from .config import settings

logger = logging.getLogger("migrationguard.multiagent")


def analyze_codebase_stack(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Inspects all project files and detects primary/secondary languages, versions, manifests, and install/run commands."""
    paths = [f["path"] for f in files]
    file_map = {f["path"]: f.get("content") for f in files}

    # Counts by extension
    ext_counts: Dict[str, int] = {}
    for p in paths:
        ext = os.path.splitext(p)[1].lower()
        if ext:
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

    has_package_json = any(p.endswith("package.json") for p in paths)
    has_requirements_txt = any(p.endswith("requirements.txt") for p in paths)
    has_pipfile = any(p.endswith("Pipfile") for p in paths)
    has_pyproject = any(p.endswith("pyproject.toml") for p in paths)
    has_pom = any(p.endswith("pom.xml") for p in paths)
    has_gradle = any(p.endswith("build.gradle") for p in paths)
    has_python_files = ext_counts.get(".py", 0) > 0
    has_js_ts_files = (ext_counts.get(".js", 0) + ext_counts.get(".ts", 0) + ext_counts.get(".tsx", 0) + ext_counts.get(".jsx", 0)) > 0
    has_java_files = ext_counts.get(".java", 0) > 0
    has_html = ext_counts.get(".html", 0) > 0
    has_css = (ext_counts.get(".css", 0) + ext_counts.get(".scss", 0)) > 0

    primary_language = "Generic Codebase"
    primary_version = "Unknown"
    frontend_stack = "None"
    frontend_version = "N/A"
    backend_stack = "None"
    backend_version = "N/A"
    other_languages = []
    install_commands: List[str] = []
    run_command: Optional[str] = None
    manifests_found: List[str] = []

    # 1. Python Stack Detection
    if has_requirements_txt or has_pipfile or has_pyproject or has_python_files:
        if ext_counts.get(".py", 0) >= ext_counts.get(".js", 0):
            primary_language = "Python"
            primary_version = "3.11+"

        backend_stack = "Python"
        backend_version = "3.11"

        req_path = next((p for p in paths if p.endswith("requirements.txt")), None)
        if req_path:
            manifests_found.append(req_path)
            install_commands.append(f"pip install -r {req_path}")
            content = file_map.get(req_path) or ""
            if "fastapi" in content.lower():
                backend_stack = "FastAPI (Python)"
            elif "flask" in content.lower():
                backend_stack = "Flask (Python)"
            elif "django" in content.lower():
                backend_stack = "Django (Python)"

        # Check for main run script
        for p in paths:
            base = os.path.basename(p)
            if base in ("main.py", "app.py", "server.py", "run.py"):
                run_command = f"python {p}"
                break
        if not run_command and has_python_files:
            run_command = "python app.py"

    # 2. Node.js / JavaScript / TypeScript Detection
    pkg_path = next((p for p in paths if p.endswith("package.json")), None)
    if has_package_json or has_js_ts_files:
        pkg_data = {}
        if pkg_path and file_map.get(pkg_path):
            try:
                pkg_data = json.loads(file_map[pkg_path])
                manifests_found.append(pkg_path)
            except Exception:
                pass

        if not primary_language or primary_language == "Generic Codebase":
            primary_language = "Node.js (TypeScript/JavaScript)"
            primary_version = pkg_data.get("engines", {}).get("node", ">=18.0.0")

        # Frontend frameworks
        deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
        if "next" in deps:
            frontend_stack = "Next.js"
            frontend_version = deps["next"]
        elif "react" in deps:
            frontend_stack = "React"
            frontend_version = deps["react"]
        elif "vue" in deps:
            frontend_stack = "Vue.js"
            frontend_version = deps["vue"]
        elif "vite" in deps:
            frontend_stack = "Vite"
            frontend_version = deps["vite"]

        # Package manager & install command
        if any(p.endswith("pnpm-lock.yaml") for p in paths):
            install_commands.append("pnpm install --no-frozen-lockfile || npm install")
        elif any(p.endswith("yarn.lock") for p in paths):
            install_commands.append("yarn install || npm install")
        elif any(p.endswith("bun.lockb") for p in paths):
            install_commands.append("bun install || npm install")
        elif has_package_json:
            install_commands.append("npm install")

        # Run command from scripts
        scripts = pkg_data.get("scripts", {})
        if any(p.endswith("pnpm-lock.yaml") for p in paths):
            if "dev" in scripts:
                run_command = "pnpm run dev || npm run dev"
            elif "start" in scripts:
                run_command = "pnpm start || npm start"
        else:
            if "dev" in scripts:
                run_command = "npm run dev"
            elif "start" in scripts:
                run_command = "npm start"

    # Compute target subfolder if manifests live in a subdirectory
    target_cwd = "."
    if pkg_path:
        d = os.path.dirname(pkg_path).replace("\\", "/")
        if d and d != ".":
            target_cwd = d
    elif req_path:
        d = os.path.dirname(req_path).replace("\\", "/")
        if d and d != ".":
            target_cwd = d

    if target_cwd != ".":
        install_commands = [f"cd {target_cwd} && {cmd}" for cmd in install_commands]
        if run_command:
            run_command = f"cd {target_cwd} && {run_command}"

    # 3. Java / Maven Detection
    if has_pom or has_gradle or has_java_files:
        if ext_counts.get(".java", 0) > ext_counts.get(".py", 0):
            primary_language = "Java"
            primary_version = "Java 8 / Java 17"
            backend_stack = "Java Swing / MySQL / Maven"

        if has_pom:
            manifests_found.append("pom.xml")
            install_commands.append("mvn clean compile")
            run_command = "mvn exec:java"

    # Secondary languages
    if has_html:
        other_languages.append(f"HTML ({ext_counts.get('.html', 0)} files)")
    if has_css:
        other_languages.append(f"CSS ({ext_counts.get('.css', 0) + ext_counts.get('.scss', 0)} files)")
    if ext_counts.get(".json", 0) > 0:
        other_languages.append("JSON")
    if ext_counts.get(".yaml", 0) + ext_counts.get(".yml", 0) > 0:
        other_languages.append("YAML")

    return {
        "primary_language": primary_language,
        "primary_version": primary_version,
        "frontend_stack": frontend_stack,
        "frontend_version": frontend_version,
        "backend_stack": backend_stack,
        "backend_version": backend_version,
        "other_languages": other_languages,
        "manifests_found": manifests_found,
        "install_commands": install_commands,
        "run_command": run_command,
        "files_count": len(files),
    }


def format_agent1_analysis_message(analysis: Dict[str, Any]) -> str:
    """Formats the comprehensive analysis generated by Agent 1 for the communication panel."""
    lines = [
        "🤖 **[Agent 1: Codebase & Dependency Analyzer]**",
        "Project files scanned and architectural stack detected:",
        "",
        f"• **Primary Language**: `{analysis['primary_language']}` (Version: `{analysis['primary_version']}`)",
        f"• **Frontend Stack**: `{analysis['frontend_stack']}` (Version: `{analysis['frontend_version']}`)",
        f"• **Backend Stack**: `{analysis['backend_stack']}` (Version: `{analysis['backend_version']}`)",
    ]

    if analysis.get("other_languages"):
        lines.append(f"• **Other Languages & Assets**: {', '.join(analysis['other_languages'])}")

    if analysis.get("manifests_found"):
        lines.append(f"• **Manifest Files Found**: {', '.join(f'`{m}`' for m in analysis['manifests_found'])}")
    else:
        lines.append("• **Manifest Files Found**: None")

    lines.append("")
    if analysis.get("install_commands"):
        cmd_str = " && ".join(analysis["install_commands"])
        lines.append(f"📦 **Required Dependencies**: Handing off `{cmd_str}` to **Agent 2 (Installer)**.")
    else:
        lines.append("📦 **Required Dependencies**: No package manifest required; dependencies verified.")

    if analysis.get("run_command"):
        lines.append(f"🚀 **Execution Command**: Handing off `{analysis['run_command']}` to **Agent 3 (Runner)**.")

    return "\n".join(lines)
