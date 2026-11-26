"""Run the controlled Java migration acceptance suite, without touching app data."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from backend.sandbox import docker_executable

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ('clean', 'weakened_assertion', 'deleted_test', 'regression', 'execution_disabled')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-images', action='store_true', help='Build the trusted fixture images with dependency downloads before offline verification.')
    args = parser.parse_args()
    docker = docker_executable()
    engine = subprocess.run([docker, 'info', '--format', '{{.ServerVersion}}'], capture_output=True, text=True, timeout=20)
    if engine.returncode or not engine.stdout.strip():
        parser.error('Docker engine is unavailable; start Docker Desktop first.')
    for version in (8, 17):
        image = f'migrationguard-fixture-java{version}:local'
        if args.prepare_images:
            subprocess.run([docker, 'build', '--build-arg', f'JAVA_VERSION={version}', '-t', image, 'tests/fixtures/java8-orders'], cwd=ROOT, check=True)
        else:
            exists = subprocess.run([docker, 'image', 'inspect', image], capture_output=True)
            if exists.returncode:
                parser.error('Fixture images are missing; rerun with --prepare-images.')
    output = ROOT / 'results/java-acceptance' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    environment = {**os.environ, 'APP_ENV': 'test', 'DATABASE_URL': 'sqlite+aiosqlite:///:memory:',
                   'AZURE_ENABLED': 'false', 'SENTRY_DSN': '', 'JWT_SECRET': uuid.uuid4().hex * 2,
                   'MIGRATIONGUARD_TEST_JAVA_PIPELINE': '1', 'MIGRATIONGUARD_ACCEPTANCE_OUTPUT': str(output)}
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-s', 'tests/test_java_pipeline.py', '--tb=short'], cwd=ROOT, env=environment)
    if result.returncode:
        return result.returncode
    lines = ['# Java migration acceptance evidence', '',
             'Controlled fixture, real Java 8/17 Docker builds, offline verification, isolated SQLite data.', '',
             '| Scenario | Verdict | Baseline tests | Migrated tests |', '| --- | --- | ---: | ---: |']
    for scenario in SCENARIOS:
        report = json.loads((output / f'{scenario}.json').read_text(encoding='utf-8'))
        lines.append(f"| {scenario} | {report['verdict']['value']} | {len(report['tests']['baseline'])} | {len(report['tests']['migrated'])} |")
    lines.extend(['', 'All original snapshots were verified unchanged. Unsafe/inconclusive approvals were rejected.',
                  'Clean and weakened cases require written human review. Coverage is unavailable; no behavioral-equivalence claim is made.',
                  'This is a controlled acceptance fixture, not a public-repository benchmark or a live cloud deployment.'])
    (output / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'\nEvidence: {output / "summary.md"}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
