# migration-guard

MigrationGuard is an evidence-led Java 8 to Java 17 migration verification system.

## Development

- Backend: `make install`, `make api`
- Frontend: `npm install`, `npm run dev`
- Tests: `make test`
- Evaluation: `make eval`
- Controlled real Java acceptance: `python -m evaluation.java_acceptance --prepare-images` ([instructions and limits](docs/JAVA_ACCEPTANCE.md))

Create a project virtual environment before installing backend dependencies (`python -m venv .venv`, then activate it). Copy `.env.example` to an untracked `.env` and configure your own credentials. Apply Alembic migrations to a tested database branch before starting the API; do not rely on runtime table creation. Use a direct PostgreSQL connection for migrations.

Workspace commands are disabled until `WORKSPACE_EXECUTION_ENABLED=true` on an isolated worker host. Docker migration execution has a separate `MIGRATIONGUARD_ENABLE_EXECUTION` switch. Configure Clerk, CORS, and optional Camber/Azure settings using `.env.example`. See [the remediation record](docs/REMEDIATION_2026-11-26.md) for verification, credential rotation and remaining integration work.
