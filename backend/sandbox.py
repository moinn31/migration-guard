"""Resolve an executable Docker client, rejecting empty PATH shims."""
import os
from pathlib import Path
import shutil
from .config import settings

def docker_executable() -> str:
    candidates = [settings.docker_executable, shutil.which('docker')]
    if os.name == 'nt':
        candidates.append(str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Docker/Docker/resources/bin/docker.exe'))
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and Path(candidate).stat().st_size:
            return str(candidate)
    raise RuntimeError('A working Docker CLI is required. Configure DOCKER_EXECUTABLE or install Docker Desktop.')
