"""Live command jobs and bounded Camber recovery, owned by the API process.

Jobs survive browser refresh, but not an API restart. No database schema changes.
"""
import asyncio
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import uuid

from . import camber_service, observability
from .config import settings

ERROR_LINE = re.compile(r"(?i)(?:\berror\b\s*[:\[]|\bnpm (?:err!|error)\b|traceback \(most recent|\bexception\b:|\bfailed to\b)")
ACTIVE = {"queued", "running", "recovering"}
MAX_OUTPUT = 100_000


def safe_cwd(root: Path, relative: str | None) -> Path:
    target = (root / (relative or ".")).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_dir():
        raise ValueError("Command directory must be an existing folder inside this project.")
    return target


def validate_agent_command(command: str) -> str:
    """Restrict remote agent output to explicit project setup/build operations."""
    if re.search(r"[\r\n;&|<>`$%]", command):
        raise ValueError("Agent commands cannot contain shell chains, expansion, or redirection.")
    args = shlex.split(command)
    allowed = {
        "npm": {"install", "ci", "run", "test", "start", "--version"},
        "pnpm": {"install", "run", "build", "test", "dev", "start", "--version"},
        "yarn": {"install", "run", "build", "test", "dev", "start", "--version"},
        "bun": {"install", "run", "test", "--version"},
        "pip": {"install", "check", "--version"},
        "mvn": {"test", "compile", "package", "verify", "--version"},
        "node": {"--version", "-v"},
        "python": {"--version"},
    }
    if len(args) < 2 or args[0] not in allowed:
        raise ValueError("Agent command is outside the supported project setup/build tools.")
    if args[:3] == ["python", "-m", "pip"]:
        args = ["pip", *args[3:]]
    if len(args) < 2 or args[1] not in allowed[args[0]]:
        raise ValueError("Unsupported agent command operation.")
    if args[1] == "run" and (len(args) < 3 or args[2] not in {"build", "test", "dev", "start", "lint", "typecheck"}):
        raise ValueError("Only project build/test/dev/start/lint/typecheck scripts are allowed.")
    if any(arg in {"-g", "--global", "--user", "--prefix", "--directory", "--cwd", "-C"} or arg.startswith(("--prefix=", "--cwd=", "--directory=", "--cache=", "--userconfig=")) for arg in args):
        raise ValueError("Agent commands must operate inside the project.")
    if any(".." in Path(arg).parts or Path(arg).is_absolute() for arg in args[2:]):
        raise ValueError("Agent commands cannot address paths outside the project.")
    return command


def command_environment() -> dict[str, str]:
    # Do not hand the API's database, Clerk, Azure, or Camber credentials to repositories.
    allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "JAVA_HOME", "LANG"}
    return {**{key: value for key, value in os.environ.items() if key.upper() in allowed}, "PYTHONUNBUFFERED": "1", "NO_COLOR": "1", "CI": "1"}


async def project_environment(job) -> dict[str, str]:
    environment = command_environment()
    virtualenv = job.root / ".venv"
    scripts = virtualenv / ("Scripts" if os.name == "nt" else "bin")
    if re.match(r"^(?:pip\s|python\s+-m\s+pip\s)", job.command.strip()) and not scripts.is_dir():
        job.notice("Preparing a project-local Python virtual environment.")
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "venv", str(virtualenv), env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), 90)
        except BaseException:
            process.kill()
            await process.wait()
            raise
        if process.returncode != 0:
            raise RuntimeError("Could not create the project Python environment: " + observability.redact(output.decode(errors="replace")[-2000:]))
    if scripts.is_dir():
        environment["VIRTUAL_ENV"] = str(virtualenv)
        environment["PATH"] = str(scripts) + os.pathsep + environment.get("PATH", "")
    return environment


@dataclass
class TerminalJob:
    project_id: str
    command: str
    cwd: Path
    root: Path
    terminal_id: str
    terminal_name: str
    context: dict
    auto_repair: bool = True
    parent_id: str | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "queued"
    output: str = ""
    exit_code: int | None = None
    sentry_event_id: str | None = None
    notices: list[dict] = field(default_factory=list)
    repair_attempts: int = 0
    process: asyncio.subprocess.Process | None = None
    task: asyncio.Task | None = None
    cancelled: bool = False

    def notice(self, text: str):
        self.notices.append({"id": f"{self.id}:{len(self.notices)}", "text": observability.redact(text)})

    def public(self):
        return {"id": self.id, "parent_id": self.parent_id, "command": observability.redact(self.command),
                "terminal_id": self.terminal_id, "terminal_name": self.terminal_name,
                "status": self.status, "output": self.output, "exit_code": self.exit_code,
                "sentry_event_id": self.sentry_event_id, "notices": self.notices,
                "repair_attempts": self.repair_attempts,
                "process_running": self.process is not None and self.process.returncode is None}


class TerminalManager:
    def __init__(self):
        self.jobs: dict[str, TerminalJob] = {}

    def start(self, project_id: str, command: str, root: Path, terminal_id: str, *, cwd: str = ".", terminal_name: str = "Terminal", context: dict | None = None, auto_repair: bool = True, parent_id: str | None = None) -> TerminalJob:
        if not command.strip() or len(command) > 4000:
            raise ValueError("A command of at most 4000 characters is required.")
        if any(j.project_id == project_id and j.terminal_id == terminal_id and j.status in ACTIVE for j in self.jobs.values()):
            raise ValueError("This terminal is busy. Open a new terminal for another command.")
        if sum(j.status in ACTIVE for j in self.jobs.values() if j.project_id == project_id) >= 8:
            raise ValueError("This project already has eight active commands.")
        # Keep bounded process-local history, without ever evicting running jobs.
        completed = [key for key, value in self.jobs.items() if value.status not in ACTIVE]
        for key in completed[:max(0, len(self.jobs) - 199)]:
            self.jobs.pop(key, None)
        job = TerminalJob(project_id, command, safe_cwd(root, cwd), root, terminal_id, terminal_name, context or {}, auto_repair, parent_id)
        self.jobs[job.id] = job
        job.task = asyncio.create_task(self._run(job))
        return job

    async def stop(self, job: TerminalJob):
        process = job.process
        if process is None or process.returncode is not None:
            return
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec("taskkill", "/PID", str(process.pid), "/T", "/F", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await killer.wait()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await process.wait()

    async def cancel(self, job: TerminalJob):
        job.cancelled = True
        for child in list(self.jobs.values()):
            if child.parent_id == job.id and child.status in ACTIVE:
                await self.cancel(child)
        await self.stop(job)
        if job.task:
            job.task.cancel()
            await asyncio.gather(job.task, return_exceptions=True)
        job.status = "cancelled"
        job.notice("Command stopped by the user.")

    async def _run(self, job: TerminalJob):
        reader = None
        waiter = None
        error_waiter = None
        try:
            job.status = "running"
            kwargs = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
            environment = await project_environment(job)
            job.process = await asyncio.create_subprocess_shell(job.command, cwd=str(job.cwd), env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, **kwargs)
            error_seen = asyncio.Event()

            async def consume():
                pending = ""
                while chunk := await job.process.stdout.read(4096):
                    text = observability.redact(chunk.decode(errors="replace"))
                    job.output = (job.output + text)[-MAX_OUTPUT:]
                    observability.record_output(job.project_id, job.id, text)
                    pending = (pending + text)[-8192:]
                    if ERROR_LINE.search(pending):
                        error_seen.set()
                    if "\n" in pending:
                        pending = pending.rsplit("\n", 1)[-1]

            reader = asyncio.create_task(consume())
            waiter = asyncio.create_task(job.process.wait())
            error_waiter = asyncio.create_task(error_seen.wait())
            async with asyncio.timeout(settings.terminal_timeout_seconds):
                if job.auto_repair:
                    await asyncio.wait({waiter, error_waiter}, return_when=asyncio.FIRST_COMPLETED)
                    if error_seen.is_set() and not waiter.done():
                        # Let a failing installer finish printing its diagnostic before asking Camber.
                        await asyncio.wait({waiter}, timeout=1)
                        if not waiter.done():
                            job.sentry_event_id = observability.record_failure(job.project_id, job.id, job.command, job.output)
                            repaired = await self._repair(job, running=True)
                            if job.process.returncode is not None and repaired:
                                await reader
                                job.exit_code = job.process.returncode
                                job.status = "recovered"
                                return
                            job.status = "running"
                await waiter
                await reader
            job.exit_code = job.process.returncode
            if job.cancelled:
                job.status = "cancelled"
            elif job.exit_code == 0:
                job.status = "succeeded"
                job.notice("Command completed successfully.")
            elif job.auto_repair:
                job.sentry_event_id = observability.record_failure(job.project_id, job.id, job.command, job.output)
                repaired = await self._repair(job, running=False)
                job.status = "recovered" if repaired else "failed"
            else:
                job.status = "failed"
                job.sentry_event_id = observability.record_failure(job.project_id, job.id, job.command, job.output)
        except asyncio.CancelledError:
            await self.stop(job)
            job.status = "cancelled"
            raise
        except TimeoutError:
            await self.stop(job)
            job.exit_code = 124
            job.output += "\nCommand timed out.\n"
            job.notice("Command reached the configured time limit and its process tree was stopped.")
            job.sentry_event_id = observability.record_failure(job.project_id, job.id, job.command, job.output)
            repaired = await self._repair(job, running=False) if job.auto_repair else False
            job.status = "recovered" if repaired else "failed"
        except Exception as exc:
            await self.stop(job)
            job.status = "failed"
            job.notice(f"Command could not run: {observability.redact(str(exc))}")
        finally:
            for task in (reader, waiter, error_waiter):
                if task and not task.done():
                    task.cancel()
            await asyncio.gather(*(t for t in (reader, waiter, error_waiter) if t), return_exceptions=True)

    async def _repair(self, job: TerminalJob, *, running: bool) -> bool:
        attempts = []
        last_command, last_output = job.command, job.output
        while job.repair_attempts < settings.agent_max_retries and not job.cancelled:
            job.status = "recovering"
            job.repair_attempts += 1
            job.notice(f"Error captured{' in Sentry (' + job.sentry_event_id + ')' if job.sentry_event_id else ''}. Asking Camber Fixer Agent (attempt {job.repair_attempts}/{settings.agent_max_retries}).")
            try:
                plan = await camber_service.diagnose(job.context, last_command, last_output, running, attempts, job.sentry_event_id)
                if not plan.commands:
                    job.notice(f"Human action required: {plan.summary}")
                    return False
                # Validate the complete plan before any command can run.
                for item in plan.commands:
                    validate_agent_command(item.command)
                    safe_cwd(job.root, item.cwd)
                job.notice(f"Fixer Agent: {plan.summary}")
                if running and not plan.keep_running:
                    await self.stop(job)
                    running = False
                    job.notice("Stopped the failing process before applying the recovery plan.")
                elif running:
                    job.notice("Keeping the existing process running; recovery uses a separate Terminal (AI-2).")
                terminal_id = f"ai-2-{job.id}-{job.repair_attempts}"
                failed = False
                for item in plan.commands:
                    if item.command in attempts:
                        raise ValueError("Camber repeated an earlier recovery command; stopping the loop.")
                    attempts.append(item.command)
                    child = self.start(job.project_id, item.command, job.root, terminal_id, cwd=item.cwd, terminal_name="Terminal (AI-2)", auto_repair=False, parent_id=job.id)
                    await child.task
                    if child.exit_code != 0:
                        last_command, last_output = item.command, child.output
                        failed = True
                        break
                if failed:
                    continue
                if running and job.process.returncode is None:
                    job.status = "running"
                    job.notice("Recovery commands completed. The original process remains running; final verification is pending.")
                    return True
                # A successful diagnostic is not a successful fix. Verify the original command.
                verification = self.start(job.project_id, job.command, job.root, terminal_id, cwd=str(job.cwd.relative_to(job.root.resolve())), terminal_name="Terminal (AI-2)", auto_repair=False, parent_id=job.id)
                await verification.task
                if verification.exit_code == 0:
                    job.notice("Recovery verified: the original command now succeeds. Setup can continue.")
                    return True
                last_command, last_output = job.command, verification.output
            except (camber_service.AgentUnavailable, ValueError) as exc:
                job.notice(str(exc))
                return False
        job.notice("Automatic recovery stopped after the retry limit. Human action is required.")
        return False


terminal_manager = TerminalManager()
