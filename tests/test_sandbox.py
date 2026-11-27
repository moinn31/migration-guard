import pytest
from backend import sandbox
from backend.config import settings

def test_empty_docker_shim_is_not_accepted(tmp_path, monkeypatch):
    shim = tmp_path / 'docker'
    shim.touch()
    monkeypatch.setattr(settings, 'docker_executable', None)
    monkeypatch.setattr(sandbox.shutil, 'which', lambda _: str(shim))
    monkeypatch.setenv('ProgramFiles', str(tmp_path))
    with pytest.raises(RuntimeError, match='working Docker CLI'):
        sandbox.docker_executable()

def test_explicit_client_takes_precedence(tmp_path, monkeypatch):
    executable = tmp_path / 'docker.exe'
    executable.write_bytes(b'fixture')
    monkeypatch.setattr(settings, 'docker_executable', str(executable))
    assert sandbox.docker_executable() == str(executable)
