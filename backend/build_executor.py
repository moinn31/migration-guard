from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import asyncio
import shutil
import tempfile
import uuid
import os
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
from .config import settings, VerificationProfile
from .coverage import collect_coverage
from .sandbox import docker_executable


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
    for report in sorted(Path(report_root).rglob("*.xml")):
        if not report.resolve().is_relative_to(Path(report_root).resolve()):
            continue
        try:
            root = ET.parse(report).getroot()
        except ET.ParseError:
            continue
        for case in root.findall(".//testcase"):
            name = f"{case.attrib.get('classname', '')}#{case.attrib.get('name', 'unknown')}"
            duration = float(case.attrib["time"]) if case.attrib.get("time") else None
            child = next((item for item in case if item.tag in {'failure', 'error', 'skipped'}), None)
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
        if not class_file.resolve().is_relative_to(Path(classes_root).resolve()):
            continue
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
    profile: VerificationProfile | None = None,
) -> BuildResult:
    if not docker_enabled:
        return BuildResult("SKIPPED", 0, "Sandbox execution is disabled by default.", {})
    source = Path(snapshot_path).resolve()
    if not source.is_dir():
        return BuildResult("FAILED", 2, f"Snapshot path does not exist: {source}", {})
    temporary = Path(tempfile.mkdtemp(prefix='migrationguard-build-'))
    working = temporary / 'repository'
    shutil.copytree(source, working, ignore=shutil.ignore_patterns('.git', 'target'), symlinks=True)
    for path in [working, *working.rglob('*')]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | 0o200)
    artifact_root = Path(settings.workspace_root).resolve() / 'artifacts' / uuid.uuid4().hex
    if artifact_root.is_relative_to(source):
        shutil.rmtree(temporary)
        return BuildResult('ERROR', 2, 'Build artifacts must be stored outside the original snapshot.', {})
    artifact_root.mkdir(parents=True)
    name = 'migrationguard-build-' + uuid.uuid4().hex
    try:
        executable = docker_executable()
    except RuntimeError as exc:
        shutil.rmtree(temporary)
        return BuildResult('ERROR', 127, str(exc), {})
    image = (profile.image_template if profile else settings.maven_image_template).format(java_version=java_version)
    repository_path = profile.repository_path if profile else settings.maven_repository_path
    offline = profile.offline if profile else settings.maven_offline
    measure_coverage = profile.collect_coverage if profile else settings.maven_collect_coverage
    uid = os.getuid() if hasattr(os, 'getuid') and os.getuid() != 0 else 1000
    gid = os.getgid() if hasattr(os, 'getgid') and os.getuid() != 0 else 1000
    command = [
        executable, "run", "--rm", '--name', name, "--user", f'{uid}:{gid}',
        "--cpus", "1", "--memory", "1g", '--pids-limit', '256',
        '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
        "--network", "bridge" if maven_mirror else "none",
        '--env', 'HOME=/tmp', '--env', 'MAVEN_CONFIG=/tmp/maven-config',
        "-v", f"{working}:/workspace:rw",
    ]
    if maven_mirror:
        parsed = urlparse(maven_mirror)
        if parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
            shutil.rmtree(temporary)
            return BuildResult('ERROR', 2, 'Maven mirror must be a credential-free HTTP(S) URL.', {})
        document = ET.Element('settings', xmlns='http://maven.apache.org/SETTINGS/1.2.0')
        mirror = ET.SubElement(ET.SubElement(document, 'mirrors'), 'mirror')
        for key, value in {'id': 'migrationguard', 'mirrorOf': '*', 'url': maven_mirror}.items():
            ET.SubElement(mirror, key).text = value
        settings_file = temporary / 'settings.xml'
        ET.ElementTree(document).write(settings_file, encoding='utf-8', xml_declaration=True)
        command.extend(['-v', f'{settings_file}:/maven-settings.xml:ro'])
    goals = ['org.jacoco:jacoco-maven-plugin:0.8.12:prepare-agent', 'test', 'org.jacoco:jacoco-maven-plugin:0.8.12:report'] if measure_coverage else ['test']
    command.extend(['-w', '/workspace', image, 'mvn', '-B', f'-Dmaven.repo.local={repository_path}', *goals])
    if offline:
        command.append('--offline')
    if maven_mirror:
        command.extend(['--settings', '/maven-settings.xml'])
    if test_filter:
        command.extend(["-Dtest=" + test_filter, '-Dsurefire.failIfNoSpecifiedTests=false'])
    process = None
    output = b''
    code = 127
    status = 'ERROR'
    try:
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        output, _ = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
        code = process.returncode or 0
        status = 'PASSED' if code == 0 else 'FAILED'
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        code, status = 124, 'TIMEOUT'
        output = b'Build exceeded the configured timeout.'
    except OSError as exc:
        output = str(exc).encode()
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        # Killing the Docker client alone leaves the container running.
        try:
            cleanup = await asyncio.create_subprocess_exec(executable, 'rm', '-f', name, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await asyncio.wait_for(cleanup.wait(), 15)
        except (OSError, TimeoutError):
            pass
    tests = []
    versions = {}
    expected_classes = {}
    try:
        for report_dir in sorted(working.rglob('surefire-reports')):
            if not report_dir.resolve().is_relative_to(working) or report_dir.parent.name != 'target':
                continue
            module = report_dir.parent.parent.relative_to(working).as_posix()
            records = parse_surefire_reports(report_dir)
            tests.extend(TestResultRecord(f'{module}:{item.name}' if module != '.' else item.name, item.status, item.duration_seconds, item.message) for item in records)
            destination = artifact_root / module / 'surefire-reports'
            destination.mkdir(parents=True, exist_ok=True)
            for report in report_dir.glob('*.xml'):
                if report.resolve().is_relative_to(working):
                    shutil.copyfile(report, destination / report.name)
        for classes in working.rglob('classes'):
            if classes.parent.name == 'target' and classes.resolve().is_relative_to(working):
                collected = class_major_versions(classes)
                expected_classes[classes.parent.parent.relative_to(working).as_posix()] = {path[:-6] for path in collected}
                for path, version in collected.items():
                    versions[(classes.relative_to(working) / path).as_posix()] = version
        logs = output.decode(errors='replace')
        (artifact_root / 'build.log').write_text(logs, encoding='utf-8')
        artifacts = {'directory': str(artifact_root), 'surefire_reports': str(artifact_root),
                     'class_major_versions': versions, 'test_count': len(tests),
                     'java_version': java_version, 'image': image, 'command': command,
                     'execution_enabled': True, 'coverage': collect_coverage(working, artifact_root, expected_classes),
                     'network': 'bridge' if maven_mirror else 'none'}
        return BuildResult(status, code, logs, artifacts, tuple(tests))
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def compare_test_results(baseline: list[TestResultRecord], migrated: list[TestResultRecord]) -> list[dict[str, str]]:
    before = {item.name: item for item in baseline}
    after = {item.name: item for item in migrated}
    differences: list[dict[str, str]] = []
    for name, result in before.items():
        if name not in after:
            differences.append({"code": "TEST_MISSING", "test": name, "message": "Test is missing from migrated results."})
        elif result.status == "pass" and after[name].status in {"fail", 'error'}:
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
    profile: VerificationProfile | None = None,
) -> set[str]:
    flaky: set[str] = set()
    for test in tests:
        if test.status not in {"fail", "error"} or "#" not in test.name:
            continue
        class_name, method = test.name.split(':', 1)[-1].split("#", 1)
        for _ in range(retries):
            rerun = await run_maven_build(
                snapshot_path,
                java_version=java_version,
                docker_enabled=docker_enabled,
                maven_mirror=maven_mirror,
                test_filter=f"{class_name}#{method}",
                profile=profile,
            )
            if any(item.name == test.name and item.status == "pass" for item in rerun.tests):
                flaky.add(test.name)
                break
    return flaky
