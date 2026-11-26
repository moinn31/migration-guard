# Real Java migration acceptance

This milestone proves the core workflow using a small controlled Java/Maven project. It does not establish general migration safety or benchmark accuracy.

## Run

Activate the project Python environment and start Docker Desktop/Engine, then:

```text
python -m evaluation.java_acceptance --prepare-images
```

Subsequent runs can omit `--prepare-images`. The first command downloads official Maven/Temurin images and JUnit/Maven dependencies while building trusted fixture images. Actual verification runs use `--network none`, non-root users, resource limits and no host credential mounts. The helper detects empty Docker PATH shims on Windows and falls back to Docker Desktop's executable; DOCKER_EXECUTABLE can explicitly select the client.

Every run creates fresh evidence under `results/java-acceptance/<run>/`: summary, per-scenario JSON reports, build logs and Surefire XML. Tests use an isolated temporary SQLite database and do not modify application projects or the live database. Dispatch is captured so the test can await the real worker; build/test execution, migration rules, policy, report persistence and approvals are real.

## Scenarios

| Scenario | Expected result | Evidence |
| --- | --- | --- |
| Clean Java 8 to 17 migration | NEEDS_REVIEW | Both tests pass, bytecode 52 becomes 61; missing coverage is disclosed; approval requires justification |
| Equality replaced by nullness assertion | NEEDS_REVIEW | Builds still pass, but test-integrity evidence flags ASSERTION_WEAKENED |
| Deleted test method | UNSAFE | Missing method and lower test count; ordinary approval denied |
| Incorrect production calculation | UNSAFE | A baseline passing test fails after migration; ordinary approval denied |
| Execution disabled | INCONCLUSIVE | Skipped build evidence and a persisted report; ordinary approval denied |

Negative variants are injected only by this test harness into disposable migration copies. Normal migration rules never perform those test modifications. Every scenario verifies the original snapshot hash is unchanged. Reports must already be persisted by the worker before the test requests the report API.

The clean case intentionally does not claim VERIFIED_BY_CHECKS while coverage is unavailable. An administrator override remains a separate audited product capability; these acceptance cases test ordinary developer approval.

## Pipeline changes

- Build source is copied into a disposable writable workspace. Multi-module test results and class versions are collected before cleanup.
- Build logs and Surefire reports are preserved under the configured workspace artifact directory.
- Maven mirrors are configured through settings XML, not an ineffective JVM property. Offline/cache/image configuration is explicit.
- A configured mirror enables bridge networking; it is repository configuration, not a network egress allowlist. The acceptance suite uses prewarmed images and no network during verification.
- Timeout cleanup removes the named container as well as stopping its Docker client.
- Missing build variants, incomplete stages, missing class versions, mixed bytecode versions, lost tests and newly skipped tests cannot yield a verified verdict.
- Failed and skipped build stages continue through risk/report/verdict generation. ZIP uploads use the same asynchronous dispatch path as repository runs.
- OpenRewrite is separately opt-in through OPENREWRITE_ENABLED; the fixture demonstrates deterministic compiler migration rules, not an OpenRewrite recipe run. Enabled recipe failures raise errors instead of silently succeeding.

The CI `java-acceptance` job prepares images, runs the five scenarios and uploads the generated evidence. The ordinary unit job skips these Docker tests unless explicitly enabled.

## Limitations and next step

The fixture has two JUnit tests and a simple compiler-target migration. It is not a MigrationBench evaluation, full AST-semantic analysis, coverage measurement, or proof of equivalence. Production worker recovery, artifact retention/access policies, and broader repository/build combinations need further validation. Next, measure coverage and run the same acceptance process on a small pinned public-repository subset.
