# Camber and Sentry terminal integration

Two personal Camber agents have been created under the signed-in account:

- `@jayjaiswal10776773.migrationguard-reader`
- `@jayjaiswal10776773.migrationguard-fixer`

Their tags are saved in the Git-ignored `.env.development.local` override. Existing account credentials in `.env` were preserved.

## Current connection status

Camber's public MCP endpoint is `https://camber-mcp.cambercloud.com/mcp`.
Its current authorization server is `https://clerk.cambercloud.com`.
The API key from the account settings was tested and the MCP endpoint returned HTTP 401 `invalid_token`.
Camber's current documentation specifies OAuth for agent calls; the API-key instructions in the older public repository are no longer sufficient for this endpoint.

A production MigrationGuard integration needs its own Camber-approved OAuth client and redirect URI. The authorization server does not advertise dynamic client registration. Camber's published client IDs are for specific applications (Claude, Cursor, Antigravity, ChatGPT); they are not MigrationGuard application credentials. The documented ChatGPT client also rejects device authorization.

Once Camber supplies application OAuth credentials, obtain an access token with that approved flow and supply it as `CAMBER_MCP_ACCESS_TOKEN` in the ignored local environment file. The current adapter does not refresh OAuth tokens, so an expired token requires reconnection. Agent creation is complete; live agent invocation remains blocked on this OAuth authorization. No successful live agent call is claimed.

Official references:

- https://docs.cambercloud.com/docs/camber-mcp/
- https://docs.cambercloud.com/docs/camber-cli/login/

## Runtime flow

1. Start the API with `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000` and the frontend with `npm run dev`.
2. Open a project workspace and choose **Start Reading Agent**. Camber returns a validated setup plan; the browser runs its commands in Terminal (AI-1).
3. The backend captures stdout/stderr continuously, redacts configured service credentials, and submits terminal logs to Sentry. Nonzero exits and recognized live error lines create correlated Sentry events.
4. The Fixer Agent receives the redacted context, failed command, recent output, previous fixes, and Sentry event ID. It returns a structured recovery plan.
5. Each recovery attempt gets a separate **Terminal (AI-2)**. A useful running process is preserved when the plan requests it. A process requiring restart is stopped as a process tree first.
6. Successful repair commands are followed by the original failed command. Recovery is reported as verified only when that original command exits successfully. Failures go back to the fixer up to the configured retry limit (default three).
7. Agent Communication reports progress, verified completion, or the action still needed. The Stop button cancels a command and its active recovery commands.

## Execution boundaries

- Jobs run on the API host; this feature does not provision Azure sandboxes.
- API service credentials are excluded from the child process environment. Python package commands create and use a project-local `.venv`. Repository commands can still execute repository code on the host; use a trusted project and an isolated API host.
- Agent-generated commands are restricted to supported package setup/build/test/start operations, bounded working directories, and no shell chaining. This is command validation, not an OS sandbox.
- Jobs and their output are kept in bounded API-process memory. Browser refresh reconnects to that state. An API restart loses the job history; multiple API worker processes need a shared job store before deployment.
- A long-running process stays visible as running, not completed. The configured command deadline defaults to 30 minutes.
- Sentry records telemetry. The local failure detector triggers Camber directly; a Sentry DSN alone does not enable Sentry AI diagnosis or a signed inbound issue webhook.

## Verification

The automated tests exercise live output, cancellation, busy terminals, path containment, credential redaction, recovery command validation, preserving useful processes, retrying the original command, and Camber failure reporting. Recovery tests stub the external Camber response and run real short-lived local processes. They do not establish live Camber connectivity.
