from __future__ import annotations

from dataclasses import dataclass
import difflib
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from .config import settings
from .ingestion import _content_hash, copy_for_work


@dataclass(frozen=True)
class MigrationHunk:
    path: str
    diff: str
    source: str
    rule_id: str
    reason: str
    protected: bool
    unnecessary_change: bool
    changed_lines_ratio: float
    before: str
    after: str


RULE_LOOKUP = {
    "lombok": {"minimum": "1.18.30"},
    "mockito-core": {"minimum": "5.12.0"},
    "byte-buddy": {"minimum": "1.14.18"},
    "jacoco-maven-plugin": {"minimum": "0.8.12"},
    "maven-surefire-plugin": {"minimum": "3.2.5"},
}
MANUAL_REVIEW_ARTIFACTS = {"powermock-api-mockito2", "powermock-module-junit4", "powermock-core"}
TEST_IMPORT_WHITELIST = {"JUNIT4_TO_JUNIT5_IMPORTS", "JUNIT4_TO_JUNIT5_ANNOTATIONS"}


def snapshot_hash(path: str | Path) -> str:
    return _content_hash(Path(path))[0]


def verify_snapshot(path: str | Path, expected_hash: str) -> None:
    actual = snapshot_hash(path)
    if actual != expected_hash:
        raise ValueError(f"Immutable snapshot hash mismatch: expected {expected_hash}, got {actual}")


def _ratio(before: str, after: str) -> float:
    old = before.splitlines()
    new = after.splitlines()
    changed = sum(1 for line in difflib.ndiff(old, new) if line[:2] in {"+ ", "- "})
    return changed / max(len(old), 1)


def _hunk(path: Path, root: Path, before: str, after: str, source: str, rule_id: str, reason: str) -> MigrationHunk | None:
    if before == after:
        return None
    relative = path.relative_to(root).as_posix()
    protected = relative.startswith("src/test/") or "/src/test/" in relative
    if protected and rule_id not in TEST_IMPORT_WHITELIST:
        return MigrationHunk(relative, "", source, rule_id, reason, True, False, _ratio(before, after), before, after)
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile=f"a/{relative}", tofile=f"b/{relative}",
    ))
    formatting_only = bool(re.fullmatch(r"[\s{}\(\);,]*", "".join(
        line[1:] for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )))
    return MigrationHunk(relative, diff, source, rule_id, reason, False, formatting_only, _ratio(before, after), before, after)


def _replace_file(path: Path, root: Path, transform, source: str, rule_id: str, reason: str) -> MigrationHunk | None:
    before = path.read_text(encoding="utf-8")
    after = transform(before)
    result = _hunk(path, root, before, after, source, rule_id, reason)
    if result and not result.protected:
        path.write_text(after, encoding="utf-8")
    return result


def _compiler_fix(pom: Path, root: Path) -> MigrationHunk | None:
    def transform(text: str) -> str:
        for tag in ("maven.compiler.release", "maven.compiler.source", "maven.compiler.target"):
            text = re.sub(rf"(<{re.escape(tag)}>)[^<]*(</{re.escape(tag)}>)", r"\g<1>17\2", text)
        if "maven.compiler.release" not in text and "<properties>" in text:
            text = text.replace("<properties>", "<properties><maven.compiler.release>17</maven.compiler.release>", 1)
        return text
    return _replace_file(pom, root, transform, "rule", "MAVEN_COMPILER_TARGET_17", "Set Maven compiler source, target, or release to Java 17.")


def _jaxb_fix(root: Path, pom: Path) -> MigrationHunk | None:
    source_files = list(root.rglob("*.java"))
    if not any("javax.xml.bind" in path.read_text(encoding="utf-8", errors="ignore") for path in source_files):
        return None

    def transform(text: str) -> str:
        if "jakarta.xml.bind-api" in text:
            return text
        dependency = (
            "<dependency><groupId>jakarta.xml.bind</groupId>"
            "<artifactId>jakarta.xml.bind-api</artifactId><version>4.0.2</version></dependency>"
        )
        if "</dependencies>" in text:
            return text.replace("</dependencies>", dependency + "</dependencies>", 1)
        return text.replace("</project>", f"<dependencies>{dependency}</dependencies></project>", 1)
    return _replace_file(pom, root, transform, "rule", "ADD_JAKARTA_JAXB", "Add Jakarta JAXB API compatibility for javax.xml.bind usage.")


def _version_fix(pom: Path, root: Path) -> list[MigrationHunk]:
    text = pom.read_text(encoding="utf-8")
    results: list[MigrationHunk] = []
    for artifact, entry in RULE_LOOKUP.items():
        pattern = rf"(<artifactId>{re.escape(artifact)}</artifactId>\s*<version>)[^<]+(</version>)"
        match = re.search(pattern, text)
        if not match:
            continue
        before = text
        text = re.sub(pattern, rf"\g<1>{entry['minimum']}\2", text, count=1)
        if text != before:
            result = _hunk(pom, root, before, text, "rule", f"BUMP_{artifact.upper().replace('-', '_')}", f"Use the pinned compatible {artifact} version.")
            if result:
                results.append(result)
    if text != pom.read_text(encoding="utf-8"):
        pom.write_text(text, encoding="utf-8")
    return results


def apply_rule_migrations(working: str | Path) -> list[MigrationHunk]:
    root = Path(working)
    pom = root / "pom.xml"
    if not pom.exists():
        return []
    changes: list[MigrationHunk] = []
    first = _compiler_fix(pom, root)
    if first:
        changes.append(first)
    second = _jaxb_fix(root, pom)
    if second:
        changes.append(second)
    changes.extend(_version_fix(pom, root))
    for java_file in root.rglob("*.java"):
        text = java_file.read_text(encoding="utf-8", errors="ignore")
        for artifact in MANUAL_REVIEW_ARTIFACTS:
            if artifact in text:
                changes.append(MigrationHunk(
                    java_file.relative_to(root).as_posix(), "", "rule", "MANUAL_REVIEW_POWERMOCK",
                    f"PowerMock or similar incompatible library {artifact} requires manual review.",
                    False, False, 0.0, text, text,
                ))
                break
    return changes


def run_openrewrite_docker(
    working: str | Path,
    *,
    dry_run: bool = False,
    docker_enabled: bool | None = None,
    recipes: list[str] | None = None,
) -> str:
    if docker_enabled is None:
        docker_enabled = settings.migrationguard_enable_execution
    if not docker_enabled:
        return ""
    root = Path(working).resolve()
    target = Path(tempfile.mkdtemp(prefix="migrationguard-rewrite-"))
    recipe_list = recipes or [item.strip() for item in settings.openrewrite_recipes.split(",") if item.strip()]
    command = [
        "docker", "run", "--rm", "--user", "1000:1000", "--cpus", "1", "--memory", "1g",
        "--network", "bridge" if settings.maven_mirror else "none",
        "-v", f"{root}:/workspace:rw", "-v", f"{target}:/root/.m2",
        "-w", "/workspace", f"maven:3.9-eclipse-temurin-17", "mvn", "-B",
        f"org.openrewrite.maven:rewrite-maven-plugin:{settings.openrewrite_plugin_version}:run",
        f"-Drewrite.recipeArtifactCoordinates=org.openrewrite.recipe:rewrite-migrate-java:{settings.openrewrite_recipe_version}",
        f"-Drewrite.activeRecipe={','.join(recipe_list)}",
    ]
    if dry_run:
        command.append("-Drewrite.dryRun=true")
    if settings.maven_mirror:
        command.append(f"-Dmirror.url={settings.maven_mirror}")
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=300, check=False).stdout
    finally:
        shutil.rmtree(target, ignore_errors=True)


def migrate_snapshot(
    snapshot_path: str | Path,
    expected_hash: str,
    *,
    dry_run: bool = False,
    openrewrite_runner=run_openrewrite_docker,
) -> tuple[Path, list[MigrationHunk], str]:
    verify_snapshot(snapshot_path, expected_hash)
    working = copy_for_work(snapshot_path)
    original_hash = snapshot_hash(snapshot_path)
    changes = apply_rule_migrations(working)
    rewrite_before = Path(tempfile.mkdtemp(prefix="migrationguard-rewrite-before-"))
    shutil.copytree(working, rewrite_before / "tree")
    rewrite_output = openrewrite_runner(working, dry_run=dry_run)
    before_root = rewrite_before / "tree"
    paths = {path.relative_to(before_root) for path in before_root.rglob("*") if path.is_file()} | {
        path.relative_to(working) for path in working.rglob("*") if path.is_file()
    }
    for relative in paths:
        before_path = before_root / relative
        after_path = working / relative
        before = before_path.read_text(encoding="utf-8", errors="ignore") if before_path.exists() else ""
        after = after_path.read_text(encoding="utf-8", errors="ignore") if after_path.exists() else ""
        item = _hunk(
            working / relative,
            working,
            before,
            after,
            "openrewrite",
            "OPENREWRITE_JAVA17",
            "Applied the configured OpenRewrite Java 8 to 17 recipe.",
        )
        if item:
            changes.append(item)
            if item.protected:
                if before_path.exists():
                    after_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(before_path, after_path)
                elif after_path.exists():
                    after_path.unlink()
    shutil.rmtree(rewrite_before, ignore_errors=True)
    final_hash = snapshot_hash(snapshot_path)
    if final_hash != original_hash:
        raise ValueError("Immutable snapshot changed while migration was running.")
    if dry_run:
        shutil.rmtree(working, ignore_errors=True)
        working = copy_for_work(snapshot_path)
        return working, changes, rewrite_output
    verify_snapshot(snapshot_path, expected_hash)
    return working, changes, rewrite_output


def apply_hunk(working: str | Path, change: MigrationHunk) -> None:
    if change.protected:
        raise ValueError("Protected test hunk requires explicit review and cannot be auto-applied.")
    target = Path(working) / change.path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(change.after, encoding="utf-8")
