import pytest
from backend.build_executor import compare_test_results, parse_surefire_reports, run_maven_build

@pytest.mark.asyncio
async def test_execution_is_disabled_by_default(tmp_path):
    result = await run_maven_build(tmp_path)
    assert result.status == "SKIPPED"
    assert result.exit_code == 0
    assert result.artifacts == {}


def test_parses_junit_results_and_compares_regressions(tmp_path):
    reports = tmp_path / "surefire-reports"
    reports.mkdir()
    (reports / "TEST-example.AppTest.xml").write_text(
        '<testsuite><testcase classname="example.AppTest" name="works" time="0.12"/>'
        '<testcase classname="example.AppTest" name="fails" time="0.2"><failure message="bad">trace</failure></testcase>'
        '</testsuite>',
        encoding="utf-8",
    )
    baseline = parse_surefire_reports(reports)
    migrated = [baseline[0], type(baseline[1])("example.AppTest#new", "skipped", 0.1, "skip")]
    assert baseline[0].status == "pass"
    assert baseline[1].status == "fail"
    assert compare_test_results(baseline, migrated)[0]["code"] == "TEST_MISSING"
