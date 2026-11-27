"""Multi-project isolated workspace service running on Azure Container Apps.
Each project gets its own isolated directory inside /workspace/projects/{project_id}.
Includes reverse proxy for application dev servers (Next.js, Vite, Python) to enable live preview.
"""
import asyncio
import os
import secrets
import shlex
import shutil
import signal
import socket
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

BASE_DIR = Path('/workspace/projects')
BASE_DIR.mkdir(parents=True, exist_ok=True)

# Compatibility root for legacy calls
LEGACY_ROOT = Path('/workspace/repository')

jobs = {}
directories = {}
tasks = set()


def authenticate(authorization: str = Header(default='')):
    expected = os.environ.get('WORKSPACE_TOKEN')
    if not expected or not secrets.compare_digest(authorization, 'Bearer ' + expected):
        raise HTTPException(401, 'Unauthorized workspace request')


app = FastAPI()
api_auth = [Depends(authenticate)]


def get_root(project_id: str | None = None) -> Path:
    if not project_id or project_id in ('default', ''):
        if LEGACY_ROOT.is_dir():
            return LEGACY_ROOT
        safe_id = 'default'
    else:
        safe_id = "".join(c for c in project_id if c.isalnum() or c in "-_") or "default"
    p = BASE_DIR / safe_id
    return p


class ImportRequest(BaseModel):
    repository_url: str
    branch: str = 'main'
    github_token: str | None = None
    project_id: str = 'default'


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=4000)
    terminal_id: str = 'term-1'
    project_id: str = 'default'
    cwd: str = '.'


@app.get('/status', dependencies=api_auth)
def workspace_status(project_id: str = 'default'):
    root = get_root(project_id)
    return {'initialized': root.is_dir(), 'project_id': project_id}


def confined(path: Path, root: Path) -> Path:
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
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


@app.post('/import', dependencies=api_auth)
async def import_repository(body: ImportRequest):
    parsed = urlparse(body.repository_url)
    if parsed.scheme != 'https' or parsed.hostname != 'github.com' or parsed.username or parsed.password:
        raise HTTPException(422, 'Only credential-free HTTPS GitHub repository URLs are accepted')
    
    root = get_root(body.project_id)
    
    # If project already exists, wipe it cleanly for fresh import
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    
    root.mkdir(parents=True, exist_ok=True)
    
    # Clear any old jobs for this project
    to_delete = [jid for jid, j in jobs.items() if j.get('project_id') == body.project_id]
    for jid in to_delete:
        jobs.pop(jid, None)

    environment = dict(os.environ)
    environment.pop('WORKSPACE_TOKEN', None)
    if body.github_token:
        import base64
        encoded = base64.b64encode(('x-access-token:' + body.github_token).encode()).decode()
        environment.update(GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='http.https://github.com/.extraheader', GIT_CONFIG_VALUE_0='Authorization: Basic ' + encoded)
    environment['GIT_TERMINAL_PROMPT'] = '0'

    await run('git', 'clone', '--depth', '1', '--branch', body.branch, '--', body.repository_url, str(root), env=environment)
    # Python virtualenv on container
    await run('python', '-m', 'venv', str(root / '.venv'))
    return {'status': 'ready', 'cwd': str(root), 'platform': 'linux', 'project_id': body.project_id, 'virtualenv': str(root / '.venv')}


@app.get('/files', dependencies=api_auth)
def files(project_id: str = 'default'):
    root = get_root(project_id)
    if not root.is_dir():
        return []
    excluded = {'.git', '.venv', 'node_modules', '__pycache__'}
    return [{'path': str(path.relative_to(root)), 'size_bytes': path.stat().st_size} for path in root.rglob('*') if path.is_file() and not any(part in excluded for part in path.relative_to(root).parts)]


@app.get('/file', dependencies=api_auth)
def file(path: str, project_id: str = 'default'):
    root = get_root(project_id)
    target = confined(root / path, root)
    if not target.is_file():
        raise HTTPException(404, 'File not found')
    if target.stat().st_size > 1_000_000:
        raise HTTPException(413, 'File exceeds viewer limit')
    return {'path': path, 'content': target.read_text(errors='replace'), 'size_bytes': target.stat().st_size, 'is_binary': False}


@app.post('/commands', status_code=202, dependencies=api_auth)
async def start_command(body: CommandRequest):
    root = get_root(body.project_id)
    if not root.is_dir():
        raise HTTPException(409, 'Repository is not initialized for this project')
    
    dir_key = f"{body.project_id}:{body.terminal_id}"
    base_target = directories.get(dir_key, root)
    cwd = confined(base_target / body.cwd, root)
    if not cwd.is_dir():
        cwd = root
        
    identifier = uuid.uuid4().hex
    job = {
        'id': identifier,
        'project_id': body.project_id,
        'terminal_id': body.terminal_id,
        'command': body.command,
        'cwd': str(cwd),
        'status': 'running',
        'output': '',
        'exit_code': None
    }
    jobs[identifier] = job

    # Handle cd directly
    arguments = shlex.split(body.command)
    if arguments and arguments[0] == 'cd' and not any(char in body.command for char in ';&|<>\n'):
        target_path_str = arguments[1] if len(arguments) > 1 else str(root)
        target = (cwd / target_path_str).resolve()
        
        # Case-insensitive fallback if not found
        if not target.is_dir() and cwd.is_dir():
            arg_lower = target_path_str.lower()
            for item in cwd.iterdir():
                if item.is_dir() and item.name.lower() == arg_lower:
                    target = item
                    break
        
        if not target.is_dir():
            job.update(status='failed', exit_code=1, output=f'Directory does not exist: {target_path_str}')
        else:
            try:
                target = confined(target, root)
                directories[dir_key] = target
                job.update(status='succeeded', exit_code=0, cwd=str(target))
            except HTTPException:
                job.update(status='failed', exit_code=1, output='Path escapes repository')
        return public_job(job)

    async def execute():
        environment = {key: value for key, value in os.environ.items() if key not in {'WORKSPACE_TOKEN'}}
        environment['PATH'] = str(root / '.venv/bin') + ':' + str(root / 'node_modules/.bin') + ':' + environment.get('PATH', '')
        environment['VIRTUAL_ENV'] = str(root / '.venv')
        process = None
        try:
            process = await asyncio.create_subprocess_exec(
                '/bin/bash', '-c', body.command,
                cwd=str(cwd),
                env=environment,
                start_new_session=True,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            job['_process'] = process
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
    job['_task'] = task
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    
    # Wait up to 300ms for fast commands to finish synchronously
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=0.3)
    except (asyncio.TimeoutError, Exception):
        pass
        
    return public_job(job)


@app.get('/commands', dependencies=api_auth)
def list_commands(project_id: str | None = None):
    if project_id:
        return [public_job(j) for j in jobs.values() if j.get('project_id') == project_id]
    return [public_job(job) for job in jobs.values()]


def public_job(job):
    return {key: value for key, value in job.items() if not key.startswith('_')}


@app.delete('/commands/{job_id}', dependencies=api_auth)
async def cancel_command(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, 'Command not found')
    task = job.get('_task')
    if task and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        job['status'] = 'cancelled'
    return public_job(job)


@app.delete('/projects/{project_id}/commands', dependencies=api_auth)
def clear_project_commands(project_id: str, terminal_id: str | None = None):
    to_delete = [
        jid for jid, j in jobs.items()
        if j.get('project_id') == project_id and (not terminal_id or j.get('terminal_id') == terminal_id)
    ]
    for jid in to_delete:
        task = jobs[jid].get('_task')
        if task and not task.done():
            task.cancel()
        jobs.pop(jid, None)
    return {'status': 'cleared', 'count': len(to_delete)}


@app.delete('/projects/{project_id}', dependencies=api_auth)
def delete_project_workspace(project_id: str):
    root = get_root(project_id)
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    to_delete = [jid for jid, j in jobs.items() if j.get('project_id') == project_id]
    for jid in to_delete:
        jobs.pop(jid, None)
    return {'status': 'deleted', 'project_id': project_id}


def find_active_dev_port() -> int | None:
    for port in [3000, 5173, 8000, 5000, 8081, 4000]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.1)
            if s.connect_ex(('127.0.0.1', port)) == 0:
                return port
    return None


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def proxy_preview(request: Request, path: str = ""):
    port = find_active_dev_port()
    if not port:
        return HTMLResponse(
            """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Dev Server</title></head>
            <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="text-align:center;padding:2.5rem;background:#161b22;border-radius:12px;border:1px solid #30363d;max-width:480px;box-shadow:0 8px 24px rgba(0,0,0,0.5);">
              <div style="font-size:2.2rem;margin-bottom:1rem;">🚀</div>
              <h2 style="color:#58a6ff;margin:0 0 0.5rem 0;font-size:1.3rem;">Application Starting...</h2>
              <p style="color:#8b949e;font-size:0.95rem;line-height:1.5;margin-bottom:1.5rem;">Dev server (port 3000/5173/8000) is launching. This preview updates automatically once ready.</p>
              <button onclick="location.reload()" style="background:#238636;color:white;border:none;padding:8px 18px;border-radius:6px;font-weight:600;cursor:pointer;font-size:0.9rem;">Refresh Preview</button>
            </div>
            <script>setTimeout(function(){ location.reload(); }, 3000);</script>
            </body></html>""",
            status_code=503
        )

    target_url = f"http://127.0.0.1:{port}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers["host"] = f"127.0.0.1:{port}"

    body = await request.body()
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            proxy_res = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                follow_redirects=True
            )
            
            # Strip headers that block iframe embedding
            excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection", "x-frame-options", "content-security-policy"}
            res_headers = {k: v for k, v in proxy_res.headers.items() if k.lower() not in excluded_headers}
            
            return Response(
                content=proxy_res.content,
                status_code=proxy_res.status_code,
                headers=res_headers,
                media_type=proxy_res.headers.get("content-type")
            )
        except Exception as exc:
            return HTMLResponse(
                f"<html><body><h3>Connecting to port {port}...</h3><p>{exc}</p><script>setTimeout(()=>location.reload(), 2000)</script></body></html>",
                status_code=502
            )
