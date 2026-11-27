import asyncio
import json
import sys

import pytest

from backend import camber_service, observability
from backend.camber_service import RecoveryCommand, RecoveryPlan, parse_plan
from backend.config import settings
from backend.terminal_jobs import TerminalManager, safe_cwd, validate_agent_command


def python_command(source):
    # subprocess shell on Windows requires double-quoted Python source.
    return f'"{sys.executable}" -c "{source}"'


@pytest.fixture(autouse=True)
def no_remote_telemetry(monkeypatch):
    monkeypatch.setattr(observability, 'record_failure', lambda *args: 'test-event')
    monkeypatch.setattr(observability, 'record_output', lambda *args: None)


@pytest.mark.parametrize('command', [
    'npm install', 'npm ci', 'npm run build', 'pnpm install',
    'python -m pip install -r requirements.txt', 'python --version', 'mvn test',
])
def test_project_setup_commands_are_accepted(command):
    assert validate_agent_command(command) == command


@pytest.mark.parametrize('command', [
    'npm install && del package.json', 'python -c "print(1)"',
    'pip install --user foo', 'npm install -g foo', 'npm run deploy',
    'curl https://example.com', 'npm install > stolen.txt', 'pip install ../outside',
])
def test_remote_agent_cannot_escape_command_policy(command):
    with pytest.raises(ValueError):
        validate_agent_command(command)


def test_directory_traversal_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        safe_cwd(tmp_path, '..')


def test_wrapped_json_plan_is_validated():
    plan = parse_plan(json.dumps({'response': '```json\n{"summary":"fix","commands":[{"command":"npm ci"}]}\n```'}))
    assert plan.commands[0].command == 'npm ci'
    assert plan.keep_running is True


def test_service_credentials_are_redacted(monkeypatch):
    monkeypatch.setattr(settings, 'camber_api_key', 'real-test-secret-value')
    assert 'real-test-secret-value' not in observability.redact('value real-test-secret-value')
    assert 'abc123' not in observability.redact('authorization=Bearer abc123')
    monkeypatch.setattr(settings, 'azure_workspaces', {'project': {'url': 'https://workspace.example', 'token': 'nested-workspace-secret'}})
    assert 'nested-workspace-secret' not in observability.redact('credential: nested-workspace-secret')


@pytest.mark.asyncio
async def test_live_job_outputs_before_process_finishes_and_cancels(tmp_path):
    manager = TerminalManager()
    job = manager.start('p1', python_command("import time; print('ready', flush=True); time.sleep(30)"), tmp_path, 'term-1', auto_repair=False)
    try:
        async with asyncio.timeout(5):
            while 'ready' not in job.output:
                await asyncio.sleep(.05)
        assert job.public()['process_running']
        with pytest.raises(ValueError, match='busy'):
            manager.start('p1', 'echo second', tmp_path, 'term-1')
        await manager.cancel(job)
        assert job.status == 'cancelled'
        assert not job.public()['process_running']
    finally:
        await manager.cancel(job)


@pytest.mark.asyncio
async def test_failure_goes_to_fixer_and_original_command_is_verified(tmp_path, monkeypatch):
    calls = []
    async def diagnose(*args):
        calls.append(args)
        return RecoveryPlan(summary='Retry after environment check', commands=[RecoveryCommand(command='python --version')])
    monkeypatch.setattr(camber_service, 'diagnose', diagnose)
    source = "from pathlib import Path; import sys; p=Path('attempt'); first=not p.exists(); p.write_text('seen'); print('first attempt fails' if first else 'verified'); sys.exit(1 if first else 0)"
    manager = TerminalManager()
    job = manager.start('p1', python_command(source), tmp_path, 'term-1')
    await asyncio.wait_for(job.task, 10)
    assert job.status == 'recovered'
    assert len(calls) == 1
    children = [item for item in manager.jobs.values() if item.parent_id == job.id]
    assert len(children) == 2
    assert all(item.terminal_name == 'Terminal (AI-2)' for item in children)
    assert children[-1].command == job.command
    assert children[-1].exit_code == 0
    assert calls[0][-1] == 'test-event'


@pytest.mark.asyncio
async def test_invalid_agent_response_does_not_run_commands(tmp_path, monkeypatch):
    async def diagnose(*args):
        return RecoveryPlan(summary='invalid', commands=[RecoveryCommand(command='npm install && echo nope')])
    monkeypatch.setattr(camber_service, 'diagnose', diagnose)
    manager = TerminalManager()
    job = manager.start('p1', python_command('import sys; sys.exit(1)'), tmp_path, 'term-1')
    await asyncio.wait_for(job.task, 10)
    assert job.status == 'failed'
    assert len(manager.jobs) == 1


@pytest.mark.asyncio
async def test_useful_process_is_preserved_while_fixer_runs_in_another_terminal(tmp_path, monkeypatch):
    async def diagnose(*args):
        assert args[3] is True
        return RecoveryPlan(summary='Keep server alive', keep_running=True, commands=[RecoveryCommand(command='python --version')])
    monkeypatch.setattr(camber_service, 'diagnose', diagnose)
    manager = TerminalManager()
    job = manager.start('p1', python_command("import time; print('ERROR: missing optional dependency', flush=True); time.sleep(30)"), tmp_path, 'term-1')
    try:
        async with asyncio.timeout(10):
            while not any('original process remains running' in item['text'] for item in job.notices):
                await asyncio.sleep(.05)
        assert job.process.returncode is None
        child = next(item for item in manager.jobs.values() if item.parent_id == job.id)
        assert child.terminal_id != job.terminal_id
        assert child.status == 'succeeded'
    finally:
        await manager.cancel(job)


@pytest.mark.asyncio
async def test_unavailable_camber_reports_action_needed_without_claiming_success(tmp_path, monkeypatch):
    async def diagnose(*args):
        raise camber_service.AgentUnavailable('Camber token needs attention')
    monkeypatch.setattr(camber_service, 'diagnose', diagnose)
    manager = TerminalManager()
    job = manager.start('p1', python_command('import sys; sys.exit(1)'), tmp_path, 'term-1')
    await asyncio.wait_for(job.task, 10)
    assert job.status == 'failed'
    assert any('token needs attention' in item['text'] for item in job.notices)
    assert not any('verified' in item['text'] for item in job.notices)


@pytest.mark.asyncio
async def test_failing_process_is_stopped_before_repair_and_verified_once(tmp_path, monkeypatch):
    calls = []
    async def diagnose(*args):
        calls.append(args)
        return RecoveryPlan(summary='Restart is needed', keep_running=False, commands=[RecoveryCommand(command='python --version')])
    monkeypatch.setattr(camber_service, 'diagnose', diagnose)
    source = "from pathlib import Path; import time; p=Path('attempt'); first=not p.exists(); p.write_text('seen'); print('ERROR: restart required' if first else 'verified',flush=True); time.sleep(30 if first else 0)"
    manager = TerminalManager()
    job = manager.start('p1', python_command(source), tmp_path, 'term-1')
    await asyncio.wait_for(job.task, 10)
    assert job.status == 'recovered'
    assert len(calls) == 1
    assert not job.public()['process_running']
    assert len([item for item in manager.jobs.values() if item.parent_id == job.id and item.command == job.command]) == 1


@pytest.mark.asyncio
async def test_timeout_is_sent_to_sentry_and_fixer(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(settings, 'terminal_timeout_seconds', 1)
    async def diagnose(*args):
        calls.append(args)
        return RecoveryPlan(summary='Human action needed', commands=[])
    monkeypatch.setattr(camber_service, 'diagnose', diagnose)
    manager = TerminalManager()
    job = manager.start('p1', python_command('import time; time.sleep(30)'), tmp_path, 'term-1')
    await asyncio.wait_for(job.task, 5)
    assert job.exit_code == 124
    assert job.status == 'failed'
    assert calls[0][-1] == 'test-event'


@pytest.mark.asyncio
async def test_python_package_commands_use_a_project_virtualenv(tmp_path):
    manager = TerminalManager()
    job = manager.start('p1', 'python -m pip --version', tmp_path, 'term-1', auto_repair=False)
    await asyncio.wait_for(job.task, 90)
    assert job.exit_code == 0
    assert (tmp_path / '.venv').is_dir()
    assert '.venv' in job.output
