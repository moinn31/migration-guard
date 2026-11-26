import pytest
import asyncio
from pathlib import Path
from backend.build_executor import compare_test_results, parse_surefire_reports, run_maven_build

@pytest.mark.asyncio
async def test_execution_is_disabled_by_default(tmp_path):
    result = await run_maven_build(tmp_path)
    assert result.status == "SKIPPED"
    assert result.exit_code == 0
    assert result.artifacts == {}


def test_parses_junit_results_and_compares_regressions(tmp_path):
    reports = tmp_path / "surefire-reports"
    reports.mkdir()
    (reports / "TEST-example.AppTest.xml").write_text(
        '<testsuite><testcase classname="example.AppTest" name="works" time="0.12"/>'
        '<testcase classname="example.AppTest" name="fails" time="0.2"><failure message="bad">trace</failure></testcase>'
        '</testsuite>',
        encoding="utf-8",
    )
    baseline = parse_surefire_reports(reports)
    migrated = [baseline[0], type(baseline[1])("example.AppTest#new", "skipped", 0.1, "skip")]
    assert baseline[0].status == "pass"
    assert baseline[1].status == "fail"
    assert compare_test_results(baseline, migrated)[0]["code"] == "TEST_MISSING"


def test_output_before_failure_does_not_hide_test_failure(tmp_path):
    (tmp_path / 'TEST-result.xml').write_text('<testsuite><testcase classname="Order" name="total"><system-out>log</system-out><failure message="wrong total"/></testcase></testsuite>')
    assert parse_surefire_reports(tmp_path)[0].status == 'fail'

@pytest.mark.asyncio
async def test_timeout_removes_container_and_preserves_log(tmp_path, monkeypatch):
    from backend import build_executor
    from backend.config import settings
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'pom.xml').write_text('<project/>')
    monkeypatch.setattr(settings, 'workspace_root', str(tmp_path / 'artifacts'))
    monkeypatch.setattr(build_executor, 'docker_executable', lambda: 'docker-test')
    calls = []
    class Process:
        returncode = None
        def kill(self):
            self.returncode = -9
        async def wait(self):
            return self.returncode
        async def communicate(self):
            await asyncio.sleep(10)
            return b'', None
    async def launch(*command, **kwargs):
        calls.append(command)
        process = Process()
        if command[1] == 'rm':
            process.returncode = 0
        return process
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', launch)
    result = await run_maven_build(source, docker_enabled=True, timeout_seconds=.01)
    assert result.status == 'TIMEOUT' and result.exit_code == 124
    name = calls[0][calls[0].index('--name') + 1]
    assert ('docker-test', 'rm', '-f', name) in calls
    assert (Path(result.artifacts['directory']) / 'build.log').is_file()
