"""Bounded Git cloning on Windows and Unix without GitPython's Unix-only timeout."""
import os
from pathlib import Path
import signal
import subprocess

def clone_shallow(repository_url: str, target: str | Path, *, branch: str | None = None, timeout: int = 120) -> None:
    command = ['git', 'clone', '--depth', '1']
    if branch:
        if branch.startswith('-') or any(character in branch for character in '\r\n\x00'):
            raise ValueError('Invalid repository branch')
        command.extend(['--branch', branch])
    command.extend(['--', repository_url, str(target)])
    environment = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', env=environment, **options)
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.communicate()
        raise TimeoutError(f'Repository clone exceeded {timeout} seconds') from None
    if process.returncode:
        # Do not include the command: clone URLs can contain scoped credentials.
        raise RuntimeError('Repository clone failed: ' + output[-2000:])
