"""Terminal telemetry with credential redaction before it leaves the server."""
import logging
import os
import re

from .config import settings

logger = logging.getLogger("migrationguard.terminal")


def redact(text: str) -> str:
    text = str(text)
    # Include dotenv values (not just os.environ) and credentials inherited by workers.
    values = {**settings.model_dump(), **os.environ}
    def secrets(value):
        if not isinstance(value, dict):
            return
        for name, item in value.items():
            if isinstance(item, dict):
                yield from secrets(item)
            elif any(part in name.lower() for part in ("secret", "token", "password", "api_key", "database_url", "dsn")):
                if isinstance(item, str) and len(item) >= 8:
                    yield item
    for value in secrets(values):
        text = text.replace(value, "[REDACTED]")
    text = re.sub(r"(?i)(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    return re.sub(r"(?i)((?:api[_-]?key|token|password|secret|authorization)\s*[:=]\s*)(?:Bearer\s+)?[^\s,;]+", r"\1[REDACTED]", text)


def _scrub(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: "[REDACTED]" if any(part in str(key).lower() for part in ("authorization", "cookie", "password", "secret", "api_key", "token")) else _scrub(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def initialize_monitoring() -> None:
    if not settings.sentry_dsn:
        return
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        send_default_pii=False,
        enable_logs=True,
        before_send=lambda event, hint: _scrub(event),
        before_send_log=lambda event, hint: _scrub(event),
        integrations=[LoggingIntegration(level=logging.INFO, event_level=None)],
    )
    logger.setLevel(logging.INFO)


def record_output(project_id: str, job_id: str, text: str) -> None:
    logger.info("project=%s job=%s %s", project_id, job_id, redact(text))


def record_failure(project_id: str, job_id: str, command: str, output: str) -> str | None:
    if not settings.sentry_dsn:
        return None
    import sentry_sdk
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("project_id", project_id)
        scope.set_tag("terminal_job_id", job_id)
        scope.set_tag("command", command)
        scope.set_context("terminal", {"command": redact(command), "output": redact(output[-12000:])})
        msg = f"Workspace Command Failed: '{command}'"
        first_line = output.strip().split('\n')[0] if output.strip() else ''
        if first_line:
            msg += f" ({first_line[:100]})"
        return sentry_sdk.capture_message(msg, level="error")
