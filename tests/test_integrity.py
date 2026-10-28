from backend.test_integrity import compare_test_trees

BASE = {'src/test/java/OrderTest.java': '@Test void createsOrder(){ assertEquals(1, 1); }'}


def test_detects_deleted_disabled_and_weakened_tests():
    findings = compare_test_trees(BASE, {'src/test/java/OrderTest.java': '@Disabled @Test void createsOrder(){ }'})
    codes = {finding.code for finding in findings}
    assert 'TEST_DISABLED' in codes
    assert 'ASSERTIONS_WEAKENED' in codes


def test_detects_deleted_file():
    findings = compare_test_trees(BASE, {})
    assert findings[0].code == 'TEST_FILE_DELETED'


def test_detects_deleted_test_and_weakened_assertion_from_examples():
    baseline = {
        "src/test/java/example/AppTest.java": (
            "@Test void first(){ assertEquals(1, 1); }\n"
            "@Test void deleted(){ assertEquals(2, 2); }"
        )
    }
    deleted = {
        "src/test/java/example/AppTest.java": "@Test void first(){ assertEquals(1, 1); }"
    }
    weakened = {
        "src/test/java/example/AppTest.java": "@Test void first(){ assertNotNull(new Object()); }"
    }
    assert "TESTS_DELETED" in {item.code for item in compare_test_trees(baseline, deleted)}
    assert "ASSERTION_WEAKENED" in {item.code for item in compare_test_trees(baseline, weakened)}
