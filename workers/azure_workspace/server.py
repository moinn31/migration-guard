"""One deployment per repository. Source and processes stay inside Azure."""
import asyncio
import os
import secrets
import shlex
import signal
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel, Field

ROOT = Path('/workspace/repository')
jobs = {}
directories = {}
tasks = set()


def authenticate(authorization: str = Header(default='')):
    expected = os.environ.get('WORKSPACE_TOKEN')
    if not expected or not secrets.compare_digest(authorization, 'Bearer ' + expected):
        raise HTTPException(401, 'Unauthorized workspace request')


app = FastAPI(dependencies=[Depends(authenticate)])


class ImportRequest(BaseModel):
    repository_url: str
    branch: str = 'main'
    github_token: str | None = None


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4000)
    terminal_id: str = 'term-1'


def confined(path: Path) -> Path:
    path = path.resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise HTTPException(422, 'Path escapes the repository')
    return path


async def run(*args, env=None):
    process = await asyncio.create_subprocess_exec(*args, env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        output, _ = await asyncio.wait_for(process.communicate(), 300)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise HTTPException(504, 'Repository initialization timed out')
    if process.returncode:
        raise HTTPException(502, 'Repository initialization failed; check repository access and branch')
    return output.decode(errors='replace')


@app.post('/import')
async def import_repository(body: ImportRequest):
    parsed = urlparse(body.repository_url)
    if parsed.scheme != 'https' or parsed.hostname != 'github.com' or parsed.username or parsed.password:
        raise HTTPException(422, 'Only credential-free HTTPS GitHub repository URLs are accepted')
    if ROOT.exists():
        raise HTTPException(409, 'Repository already initialized')
    environment = dict(os.environ)
    environment.pop('WORKSPACE_TOKEN', None)
    if body.github_token:
        import base64
        encoded = base64.b64encode(('x-access-token:' + body.github_token).encode()).decode()
        environment.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader', GIT_CONFIG_VALUE_0='Authorization: Basic ' + encoded)
    environment['GIT_TERMINAL_PROMPT'] = '0'
    await run('git', 'clone', '--depth', '1', '--branch', body.branch, '--', body.repository_url, str(ROOT), env=environment)
    # Environment creation occurs on the Azure container's filesystem.
    await run('python', '-m', 'venv', str(ROOT / '.venv'))
    return {'status': 'ready', 'cwd': str(ROOT), 'platform': 'linux', 'virtualenv': str(ROOT / '.venv')}


@app.get('/files')
def files():
    excluded = {'.git', '.venv', 'node_modules', '__pycache__'}
    return [{'path': str(path.relative_to(ROOT)), 'size_bytes': path.stat().st_size} for path in ROOT.rglob('*') if path.is_file() and not any(part in excluded for part in path.relative_to(ROOT).parts)]


@app.get('/file')
def file(path: str):
    target = confined(ROOT / path)
    if not target.is_file():
        raise HTTPException(404, 'File not found')
    if target.stat().st_size > 1_000_000:
        raise HTTPException(413, 'File exceeds viewer limit')
    return {'path': path, 'content': target.read_text(errors='replace'), 'size_bytes': target.stat().st_size, 'is_binary': False}


@app.post('/commands', status_code=202)
async def start_command(body: CommandRequest):
    if not ROOT.is_dir():
        raise HTTPException(409, 'Repository is not initialized')
    if any(job['terminal_id'] == body.terminal_id and job['status'] == 'running' for job in jobs.values()):
        raise HTTPException(409, 'Terminal is busy')
    cwd = directories.get(body.terminal_id, ROOT)
    identifier = uuid.uuid4().hex
    job = {'id': identifier, 'terminal_id': body.terminal_id, 'command': body.command, 'cwd': str(cwd), 'status': 'running', 'output': '', 'exit_code': None}
    jobs[identifier] = job
    arguments = shlex.split(body.command)
    if arguments and arguments[0] == 'cd' and not any(char in body.command for char in ';&|<>\n'):
        target = confined(cwd / (arguments[1] if len(arguments) > 1 else str(ROOT)))
        if not target.is_dir():
            job.update(status='failed', exit_code=1, output='Directory does not exist')
        else:
            directories[body.terminal_id] = target
            job.update(status='succeeded', exit_code=0, cwd=str(target))
        return job

    async def execute():
        environment = {key: value for key, value in os.environ.items() if key not in {'WORKSPACE_TOKEN'}}
        environment['PATH'] = str(ROOT / '.venv/bin') + ':' + environment.get('PATH', '')
        environment['VIRTUAL_ENV'] = str(ROOT / '.venv')
        process = None
        try:
            process = await asyncio.create_subprocess_exec('/bin/bash', '-c', body.command, cwd=str(cwd), env=environment, start_new_session=True, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            async with asyncio.timeout(1800):
                while chunk := await process.stdout.read(4096):
                    job['output'] = (job['output'] + chunk.decode(errors='replace'))[-100000:]
                await process.wait()
            job.update(status='succeeded' if process.returncode == 0 else 'failed', exit_code=process.returncode)
        except BaseException:
            if process and process.returncode is None:
                os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
            job.update(status='failed', exit_code=124, output=job['output'] + '\nCommand stopped or timed out')

    task = asyncio.create_task(execute())
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return job


@app.get('/commands')
def list_commands():
    return list(jobs.values())
