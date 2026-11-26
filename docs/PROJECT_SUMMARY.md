# MigrationGuard / Codexa AI status

Reviewed 2026-11-26 against local commit `8cd2186` (2026-11-03). This replaces the outdated October audit. Source implementation is distinguished from runtime verification; no completion percentage is claimed.

## Purpose

This application helps verify Java 8 to Java 17 migrations. Its intended flow is: create project, ingest GitHub repository or ZIP, analyze Java/Maven compatibility, generate migration edits, check test integrity, compare Java 8/17 builds and tests, calculate risk, produce a deterministic verdict and evidence report, then request human approval and export changes.

Stack: Next.js 16, React 19, TypeScript, Clerk, TanStack Query, FastAPI, async SQLAlchemy, Alembic, PostgreSQL/SQLite, Celery/Redis and Docker/Maven. AI assistance explains evidence and proposes fixes separately from deterministic verdicts.

## New updates

Recent commits add Clerk authentication, dashboard/repository cards, public/private repository discovery, database configuration, AI/report runtime fixes, and reproducible OpenAPI client generation.

Current code also contains features missing from the old audit:

| Area | Implemented in source | Evidence |
| --- | --- | --- |
| Frontend | Dashboard, projects, migration wizard, analysis, changes, builds, tests, verdict, reports, settings and benchmarks routes | `app/` |
| Ingestion | Real cloning, ZIP validation, content hashes and run-scoped snapshots | `backend/ingestion.py` |
| Analysis | Filesystem Java/Maven analysis | `backend/analyzer.py` |
| Migration | Rule edits, optional OpenRewrite, before/after diffs, protected test changes, dry runs | `backend/migration_engine.py` |
| Workers | Persisted stages, retries, evidence references, Celery dispatch and development threads | `workers/` |
| Builds | Java 8/17 Maven commands, Surefire parsing, class versions, test comparisons, flaky reruns | `backend/build_executor.py` |
| Verdict | VERIFIED_BY_CHECKS, NEEDS_REVIEW, UNSAFE, INCONCLUSIVE | `backend/verdict.py` |
| Reports | Evidence aggregation, Markdown/HTML/PDF, expiring sharing and patch export | `backend/reporting.py`, `backend/main.py` |
| Approval | Role checks, justification/override rules, accepted/rejected states, audit records | `backend/main.py` |
| AI | Explain, suggest-fix, summary, redaction, response validation, interaction persistence | `backend/llm/` |
| Integrations | Repository listing, PR endpoint, Python CLI and example action | `app/api/github/repos/route.ts`, `migrationguard/`, `docs/migrationguard-action.yml` |
| Schema/CI | Base migration creates tables; CI declares pytest, OpenAPI/client generation checks and frontend build | `backend/alembic/`, `.github/workflows/ci.yml` |

## Pending work, by priority

### P0: Authentication defect

`backend/auth.py:current_user` falls back from failed local JWT verification to decoding with `verify_signature=False`. It accepts subjects beginning with `user_` or issuers containing `clerk`, then provisions missing users as administrators. This permits forged identity claims and administrative access. Verify Clerk signatures using trusted keys, validate issuer/audience/expiry, reject invalid tokens, provision least-privilege users, and add adversarial tests. This is a source-confirmed flaw; no exploit was executed.

### P1: Complete the real migration workflow

1. **Private repository ingestion:** repository listing uses OAuth/PAT, but `clone_repository` receives only a URL and calls `Repo.clone_from` without those credentials. Private listing does not establish private cloning support.
2. **Wizard wiring:** `app/projects/[id]/new/page.tsx` collects a URL and minimal/maximal mode but sends neither. ZIP selection has no upload handler. Submit always starts a run against the existing project's repository.
3. **Sandbox execution:** execution defaults to disabled. Skipped/failed build stages stop orchestration with INCONCLUSIVE before report/verdict stages; report GET can compute evidence separately. Persist terminal reasons and verify the resulting UI.
4. **Docker/Maven reliability:** validate dependency cache/mirror setup, non-root write permissions, nested modules and timeout cleanup. Default execution has no network and no populated cache. Passing `-Dmirror.url` alone does not configure a Maven mirror. Artifact paths point to a temporary directory deleted after execution.
5. **OpenRewrite outcomes:** execution uses `check=False` and returns stdout without checking return code or preserving stderr. A recipe failure can appear as a completed migration stage. Persist and enforce command outcomes.
6. **Verdict completeness:** required stage names are checked without requiring every stage to pass with evidence. Optional count/dependency/coverage inputs are not passed by the worker; class-version validation searches text for `61`. Require structured, current evidence before granting verification, including report recomputation outside orchestration.
7. **Evidence freshness:** verify that apply/revert invalidates old builds, verdicts and approvals. Approval reuses a stored verdict when present; current evidence must be enforced.
8. **PR publishing:** the endpoint creates a GitHub PR but does not create/push its head branch or commit migrated files. Implement publishing or explicitly require a pre-existing branch.

### P2: Evaluation and operational work

- **Benchmarks are still a scaffold:** `evaluation/run.py` downloads a subset but writes fixed false metric fields for all four systems without executing them. Parsed config/worker arguments are unused. Benchmark API returns an empty status/404. Implement actual experiments and persisted results before reporting metrics.
- **Worker recovery:** test duplicate delivery, restart recovery, partial writes and database errors. Retries reuse the database session without explicit rollback. ZIP dispatch passes a local temporary filename, requiring shared storage across separate API/worker hosts.
- **Filesystem lifecycle:** validate writable migration copies after copying read-only snapshots, and add snapshot/workspace retention and cleanup.
- **AI configuration:** Settings and provider discovery use different environment names; discovery reads `MIGRATIONGUARD_LLM_*` directly. Align configuration and dotenv handling. Ollama defaults to native `/api/chat` while sending/parsing an OpenAI-style envelope; use a matching protocol. Validate real provider failures and responses.
- **Approval UI:** blocked verdicts hide the justification textarea while still showing Approve, preventing entry of the required admin override reason. Add role-aware controls and error feedback.
- **Deployment:** Compose starts only PostgreSQL/Redis. Document API/frontend/worker startup, fresh and incremental migrations, production CORS, shared storage and health checks; validate them in a clean environment.
- **Documentation/branding:** reconcile phase docs and minimal root README with current code, standardize MigrationGuard/Codexa AI naming, and define release acceptance criteria.

## Verification

- `npx tsc --noEmit`: passed, exit code 0.
- Backend tests could not execute: `python` is unavailable and `py` reports no installed interpreter.
- Source, routes, worker pipeline, CI and recent local history were reviewed. Production build, backend runtime, Docker, database migrations, live AI and GitHub operations were not tested.
- Existing `.env` modification was left untouched; secret values were not read. This review changes documentation only.

## Recommended next delivery

Fix authentication, then demonstrate one reproducible public repository run through migration, Java 8/17 execution, test preservation, verdict, report and approval. Include disabled execution and failure cases. Follow with private credentials, ZIP/mode UI integration and branch/commit publishing. Complete benchmark experiments once the pipeline is reproducible.
