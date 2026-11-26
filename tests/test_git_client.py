import subprocess
from types import SimpleNamespace
import pytest
from backend import git_client

def test_clone_uses_portable_timeout_and_explicit_arguments(tmp_path, monkeypatch):
    captured = {}
    class Process:
        returncode = 0
        def communicate(self, timeout=None):
            captured['timeout'] = timeout
            return '', None
    def start(command, **options):
        captured['command'] = command
        captured['options'] = options
        return Process()
    monkeypatch.setattr(subprocess, 'Popen', start)
    git_client.clone_shallow('https://github.com/example/demo.git', tmp_path, branch='main')
    assert captured['timeout'] == 120
    assert captured['command'] == ['git', 'clone', '--depth', '1', '--branch', 'main', '--', 'https://github.com/example/demo.git', str(tmp_path)]
    assert 'kill_after_timeout' not in captured['options']
    assert captured['options']['env']['GIT_TERMINAL_PROMPT'] == '0'

def test_failed_clone_does_not_print_the_credential_url(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, 'Popen', lambda *args, **kwargs: SimpleNamespace(returncode=1, communicate=lambda **kwargs: ('permission denied', None)))
    with pytest.raises(RuntimeError, match='permission denied') as error:
        git_client.clone_shallow('https://private-token@github.com/example/demo.git', tmp_path)
    assert 'private-token' not in str(error.value)
