# MigrationGuard Phase 1

Run `make install`, `make up`, `make api`, then open `/docs`. Create a user via `/auth/register`, use the bearer token, create a project, and start a run. `make test` runs pytest; `make openapi` exports `docs/openapi.json`.

Phase 1 intentionally contains no analysis, sandbox, or migration implementation. Phase 2 adds repository snapshot metadata and deterministic Java/Maven analysis findings. Phase 3 adds a bounded Docker Maven worker interface and a disabled-by-default build recording stub via `POST /runs/{id}/build`. Phase 4 adds deterministic Java test-integrity comparison via `POST /runs/{id}/test-integrity`, detecting deleted, disabled, weakened, and suspiciously reduced tests. Phase 5 adds deterministic Java 8-to-17 migration proposals via `GET /runs/{id}/migration-plan`; proposals are advisory, reversible, traceable, and never applied automatically. Real sandbox execution, automatic migration edits, and LLM calls remain opt-in/not implemented.
