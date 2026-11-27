import asyncio
import pytest
from backend.coverage import collect_coverage, coverage_changes

def test_measured_counters_scope_and_no_double_count(tmp_path):
    working = tmp_path / 'repository'
    report = working / 'target/site/jacoco/jacoco.xml'
    report.parent.mkdir(parents=True)
    report.write_text('<report><sessioninfo id="observed"/><package name="example"><class name="example/Order"/><counter type="LINE" covered="8" missed="2"/></package><counter type="INSTRUCTION" covered="20" missed="5"/><counter type="LINE" covered="8" missed="2"/><counter type="BRANCH" covered="0" missed="0"/></report>')
    measured = collect_coverage(working.resolve(), tmp_path / 'artifacts', {'.': {'example/Order', 'example/Missing'}, 'another': {'Other'}})
    assert measured['counters']['line']['covered'] == 8
    assert measured['counters']['line']['ratio'] == .8
    assert measured['counters']['branch']['ratio'] is None
    assert measured['missing_modules'] == ['another']
    assert measured['modules']['.']['missing_classes'] == ['example/Missing']
    assert (tmp_path / 'artifacts/coverage/jacoco.xml').exists()
    report.write_text('<report><counter type="INSTRUCTION" covered="100" missed="0"/></report>')
    assert collect_coverage(working.resolve(), tmp_path / 'artifacts', {}) is None

def test_coverage_drop_and_missing_module_remain_visible():
    def coverage(ratio):
        return {'modules': {'.': {'counters': {'line': {'ratio': ratio}}}}}
    assert not coverage_changes(None, coverage(1))
    assert not coverage_changes(coverage(.5), coverage(.6))
    assert coverage_changes(coverage(.8), coverage(.7))[0]['metric'] == 'line'
    assert coverage_changes(coverage(.8), {'modules': {}})[0]['metric'] == 'scope'

@pytest.mark.asyncio
async def test_local_queue_stays_on_api_event_loop(monkeypatch):
    from backend.config import settings
    from workers import queue, runner
    monkeypatch.setattr(settings, 'app_env', 'test')
    observed = []
    async def advance(run_id, zip_path):
        observed.append(asyncio.get_running_loop())
    monkeypatch.setattr(runner, 'advance_run', advance)
    queue.enqueue_run('run')
    await asyncio.gather(*queue.tasks)
    assert observed == [asyncio.get_running_loop()]
