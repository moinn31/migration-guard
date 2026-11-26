"""Metrics from observed run evidence. Unknown labels stay unknown."""

def report_row(report: dict) -> dict:
    builds = report.get('builds', [])
    baseline = {item['name']: item for item in report.get('tests', {}).get('baseline', [])}
    migrated = {item['name']: item for item in report.get('tests', {}).get('migrated', [])}
    build_success = None
    if builds and all(item.get('status') in {'PASSED', 'FAILED', 'ERROR', 'TIMEOUT'} for item in builds):
        build_success = all(item['status'] == 'PASSED' for item in builds)
    return {
        'run_id': report['run_id'], 'system': 'migrationguard',
        'build_success': build_success,
        'tests_preserved': set(baseline).issubset(migrated) and all(migrated[name]['status'] != 'skipped' for name, test in baseline.items() if test['status'] != 'skipped') if baseline and migrated else None,
        'regression_detected': any(test['status'] == 'pass' and migrated.get(name, {}).get('status') in {'fail', 'error'} for name, test in baseline.items()) if baseline and migrated else None,
        # Ground-truth labels and independently reviewed change necessity are unavailable.
        'false_positive': None, 'unnecessary_change': None,
        'runtime_seconds': sum(stage.get('duration_seconds') or 0 for stage in report.get('stages', [])),
    }
