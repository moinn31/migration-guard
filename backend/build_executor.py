from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import asyncio
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class TestResultRecord:
    name: str
    status: str
    duration_seconds: float | None
    message: str | None


@dataclass(frozen=True)
class BuildResult:
    status: str
    exit_code: int
    logs: str
    artifacts: dict[str, object]
    tests: tuple[TestResultRecord, ...] = ()


def parse_surefire_reports(report_root: str | Path) -> list[TestResultRecord]:
    records: list[TestResultRecord] = []
    for report in sorted(Path(report_root).glob("*.xml")):
        try:
            root = ET.parse(report).getroot()
        except ET.ParseError:
            continue
        for case in root.findall(".//testcase"):
            name = f"{case.attrib.get('classname', '')}#{case.attrib.get('name', 'unknown')}"
            duration = float(case.attrib["time"]) if case.attrib.get("time") else None
            child = next(iter(case), None)
            if child is None:
                status = "pass"
                message = None
            elif child.tag in {"skipped"}:
                status = "skipped"
                message = child.attrib.get("message") or child.text
            elif child.tag in {"failure", "error"}:
                status = "fail" if child.tag == "failure" else "error"
                message = child.attrib.get("message") or child.text
            else:
                status = "pass"
                message = None
            records.append(TestResultRecord(name, status, duration, message))
    return records


def class_major_versions(classes_root: str | Path) -> dict[str, int]:
    result: dict[str, int] = {}
    for class_file in Path(classes_root).rglob("*.class"):
        try:
            raw = class_file.read_bytes()
            if raw[:4] != b"\xca\xfe\xba\xbe":
                continue
            major = int.from_bytes(raw[6:8], "big")
            result[class_file.relative_to(classes_root).as_posix()] = major
        except OSError:
            continue
    return result


async def run_maven_build(
    snapshot_path: str | Path,
    *,
    java_version: int = 17,
    timeout_seconds: int = 300,
    docker_enabled: bool = False,
    maven_mirror: str | None = None,
    test_filter: str | None = None,
) -> BuildResult:
    if not docker_enabled:
        return BuildResult("SKIPPED", 0, "Sandbox execution is disabled by default.", {})
    source = Path(snapshot_path).resolve()
    if not source.is_dir():
        return BuildResult("FAILED", 2, f"Snapshot path does not exist: {source}", {})
    target = Path(tempfile.mkdtemp(prefix="migrationguard-target-"))
    image = f"maven:3.9-eclipse-temurin-{java_version}"
    command = [
        "docker", "run", "--rm", "--user", "1000:1000",
        "--cpus", "1", "--memory", "1g",
        "--network", "bridge" if maven_mirror else "none",
        "-v", f"{source}:/workspace:ro",
        "-v", f"{target}:/workspace/target",
        "-w", "/workspace", image, "mvn", "-B", "test",
    ]
    if maven_mirror:
        command.extend(["-Dmaven.repo.local=/tmp/m2", f"-Dmirror.url={maven_mirror}"])
    if test_filter:
        command.extend(["-Dtest=" + test_filter])
    try:
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        code = process.returncode or 0
        tests = parse_surefire_reports(target / "surefire-reports")
        artifacts = {
            "surefire_reports": str(target / "surefire-reports"),
            "class_major_versions": class_major_versions(target / "classes"),
            "test_count": len(tests),
        }
        return BuildResult("PASSED" if code == 0 else "FAILED", code, output.decode(errors="replace"), artifacts, tuple(tests))
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return BuildResult("TIMEOUT", 124, "Build exceeded the configured timeout.", {})
    finally:
        shutil.rmtree(target, ignore_errors=True)


def compare_test_results(baseline: list[TestResultRecord], migrated: list[TestResultRecord]) -> list[dict[str, str]]:
    before = {item.name: item for item in baseline}
    after = {item.name: item for item in migrated}
    differences: list[dict[str, str]] = []
    for name, result in before.items():
        if name not in after:
            differences.append({"code": "TEST_MISSING", "test": name, "message": "Test is missing from migrated results."})
        elif result.status == "pass" and after[name].status == "fail":
            differences.append({"code": "TEST_PASS_TO_FAIL", "test": name, "message": "Test passed in baseline and failed in migrated result."})
        elif result.status != "skipped" and after[name].status == "skipped":
            differences.append({"code": "TEST_NEWLY_SKIPPED", "test": name, "message": "Test became skipped in migrated result."})
    return differences


async def rerun_failed_tests(
    snapshot_path: str | Path,
    tests: list[TestResultRecord],
    *,
    java_version: int,
    docker_enabled: bool,
    maven_mirror: str | None = None,
    retries: int = 2,
) -> set[str]:
    flaky: set[str] = set()
    for test in tests:
        if test.status not in {"fail", "error"} or "#" not in test.name:
            continue
        class_name, method = test.name.split("#", 1)
        for _ in range(retries):
            rerun = await run_maven_build(
                snapshot_path,
                java_version=java_version,
                docker_enabled=docker_enabled,
                maven_mirror=maven_mirror,
                test_filter=f"{class_name}#{method}",
            )
            if any(item.name == test.name and item.status == "pass" for item in rerun.tests):
                flaky.add(test.name)
                break
    return flaky
