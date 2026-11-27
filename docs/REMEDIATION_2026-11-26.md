# Remediation record: 2026-11-26

Based on main `39b3829` and the Next.js security upgrade `3458640`. Prepared for pull request #1; Git history records publication status.

## Verified locally

- Clean project `.venv`: 92 backend tests passed, 2 integration checks skipped; `pip check` reports no broken requirements. Skipped checks require external Docker/PostgreSQL setup. Monitoring emits nonblocking SDK deprecation warnings.
- Next.js 16.4.6 production build and TypeScript checking passed, including a separate build with a nonfunctional CI public key and no Clerk secret.
- Production server started successfully; `/sign-in` returned 200 and unauthenticated `/dashboard` redirected with 307.
- Backend production startup passed with a temporary signing secret and telemetry disabled; `/health` returned 200 and unauthenticated `/projects` returned 401. Monitoring initialization also passed with a no-network test transport. Sentry is constrained below version 3 because version 3 rejects existing configuration options.
- OpenAPI/client regenerated. Live credential rotation, cloud deployment, authenticated live Clerk/Camber sessions, and live PostgreSQL migration are not claimed.

## Implemented

- Clerk tokens require RS256 signature verification using keys from the configured issuer, plus expiry/issuer checks and optional audience/authorized-party validation. The existing trusted Clerk publishable key can supply the issuer hostname when CLERK_ISSUER is absent. Invalid local JWTs no longer provision users; new Clerk users are developers.
- Migration 0010 adds workspace files/import fields and demotes legacy automatically provisioned Clerk administrators to developers. Review legitimate administrators and explicitly regrant access through an audited administration process after migration. Existing forged/unknown accounts should be reviewed.
- `.env` is removed from the Git index and ignored. Its local contents are preserved. This does not remove historical credentials or rotate them.
- Restored owner-scoped project deletion, including run evidence and project-scoped test cases, with active-import protection and terminal cancellation.
- Added missing terminal/Camber/Sentry settings and SDK dependencies, corrected the MCP transport tuple handling, and connected authenticated chat/job/list/cancel endpoints to the workspace UI. Chat explains context; terminal execution is a separate explicit action. Worker jobs are process-local, not durable across restart.
- Per-project AZURE_WORKSPACES configuration routes terminal initialization, commands, listing and cancellation to the existing Azure workspace service over authenticated HTTPS. The remote service now exposes initialization status and cancellation, and accepts confined working directories. Without a project mapping, the explicit host-execution gate applies. Remote automatic Camber recovery remains unavailable and is labeled in job notices.
- Execution is opt-in: WORKSPACE_EXECUTION_ENABLED for host commands and MIGRATIONGUARD_ENABLE_EXECUTION for Docker migrations. Disabled builds persist an INCONCLUSIVE verdict and status explanation. Use an isolated host before enabling terminal execution; project scripts execute arbitrary repository code.
- Azure defaults off and accepts only a configured HTTPS callback, rejecting local IPs/localhost. Import records remote dispatch failure and continues local import. A deployed authenticated callback/worker protocol still needs integration testing.
- Repository imports validate the GitHub host, bound clone time and stored size, skip symlinks, move cloning off the event loop, and redact credentials in persisted failures.
- Applying/reverting changes validates paths and invalidates previous build/test/risk/report/approval evidence and the stored verdict.
- Evaluation uses actual exported/stored reports. Unknown outcomes remain null. The CLI consumes config and worker count, and refuses to fabricate dataset comparisons. UI/API display observed metrics with limitations.
- Applied the already-approved Next.js 16.4.6 security branch changes to this checkout, regenerated OpenAPI/client, and enabled Clerk route protection in development and production.

## Required configuration and external work

1. Rotate exposed database passwords, Clerk secret keys, GitHub tokens, Azure credentials and any other credentials that were committed. Replace the local JWT signing secret to invalidate old local tokens. Revoke sessions when appropriate. Removing `.env` from future commits does not fix Git history.
2. Configure Clerk with CLERK_ISSUER (or the trusted publishable key), matching frontend keys, CLERK_AUTHORIZED_PARTIES and optional CLERK_AUDIENCE. Use APP_ENV=production, a unique JWT_SECRET, and explicit CORS_ORIGINS in production.
3. Test migration 0010 on an isolated Neon branch with a direct connection before production. The local SQLite migration check passes; a live PostgreSQL migration was not executed.
4. Configure CAMBER_MCP_ACCESS_TOKEN and @owner.alias chat/fixer tags. Live Camber OAuth/agent calls were not exercised. Use the per-project Azure workspace service for remote terminals. The separate legacy `azure_worker/worker.py` entrypoint remains a demonstration and its `/internal/jobs/.../progress` callback is not implemented; leave AZURE_ENABLED=false until that job protocol is completed. BACKEND_PUBLIC_URL validation alone does not make this legacy pipeline functional.
5. Docker/Maven dependency caching/mirror, real migration execution, and controlled dataset experiments still require integration work. No claim of behavioral equivalence or benchmark accuracy is made.

See `.env.example` and the evaluation README for the configuration contract. The existing project audit was preserved from the earlier review; this record supersedes its descriptions of the items fixed here.
