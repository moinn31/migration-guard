from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

try:
    from tree_sitter import Language, Parser
    import tree_sitter_java
except ImportError:
    Language = Parser = tree_sitter_java = None


@dataclass(frozen=True)
class IntegrityFinding:
    code: str
    severity: str
    path: str
    message: str
    confidence: str = "medium"
    evidence: str = ""
    note: str = "This may be legitimate because a test framework or package refactor can change equivalent syntax."


_TEST_RE = re.compile(r"@(?:Test|ParameterizedTest)\b")
_DISABLED_RE = re.compile(r"@(?:Disabled|Ignore)\b")
_ASSERT_RE = re.compile(r"\b(?:assert|verify|fail)\w*\s*\(")
_EXPECTED_RE = re.compile(r"@Test\s*\(\s*expected\s*=")


def _is_java_test(path: str) -> bool:
    p = PurePosixPath(path)
    return p.suffix == ".java" and ("/test/" in f"/{p}" or p.name.endswith("Test.java"))


def _parse_java(content: str) -> None:
    if Parser is not None and tree_sitter_java is not None:
        Parser(Language(tree_sitter_java.language())).parse(content.encode("utf-8"))


def parse_test_tree(files: dict[str, str]) -> dict[str, dict[str, int | bool]]:
    result: dict[str, dict[str, int | bool]] = {}
    for path, content in files.items():
        if _is_java_test(path):
            _parse_java(content)
            result[path] = {
                "tests": len(_TEST_RE.findall(content)),
                "assertions": len(_ASSERT_RE.findall(content)),
                "disabled": bool(_DISABLED_RE.search(content)),
                "expected": len(_EXPECTED_RE.findall(content)),
                "verifies": len(re.findall(r"\bverify\s*\(", content)),
            }
    return result


def compare_test_trees(baseline: dict[str, str], migrated: dict[str, str]) -> list[IntegrityFinding]:
    before, after = parse_test_tree(baseline), parse_test_tree(migrated)
    findings: list[IntegrityFinding] = []
    for path in sorted(set(before) - set(after)):
        findings.append(IntegrityFinding("TEST_FILE_DELETED", "high", path, "A baseline test file is missing from the migrated tree.", "high", "File exists in baseline but not migrated."))
    for path in sorted(set(before) & set(after)):
        old, new = before[path], after[path]
        if int(new["tests"]) < int(old["tests"]):
            findings.append(IntegrityFinding("TESTS_DELETED", "high", path, f"Test count decreased from {old['tests']} to {new['tests']}.", "high", f"baseline={old['tests']}; migrated={new['tests']}"))
        if not bool(old["disabled"]) and bool(new["disabled"]):
            findings.append(IntegrityFinding("TEST_DISABLED", "high", path, "A previously active test file is now disabled.", "high", "@Disabled/@Ignore detected only in migrated file."))
        if int(old["expected"]) > int(new["expected"]):
            findings.append(IntegrityFinding("EXPECTED_EXCEPTION_REMOVED", "high", path, "Expected-exception test metadata was removed.", "high", f"baseline={old['expected']}; migrated={new['expected']}"))
        if int(old["verifies"]) > int(new["verifies"]):
            findings.append(IntegrityFinding("MOCKITO_VERIFY_REMOVED", "medium", path, "Mockito verify calls were removed.", "high", f"baseline={old['verifies']}; migrated={new['verifies']}"))
        if int(old["assertions"]) > 0 and int(new["assertions"]) < int(old["assertions"]):
            findings.append(IntegrityFinding("ASSERTIONS_WEAKENED", "medium", path, f"Assertion count decreased from {old['assertions']} to {new['assertions']}.", "high", f"baseline={old['assertions']}; migrated={new['assertions']}"))
        if re.search(r"assertTrue\s*\(\s*true\s*\)", migrated.get(path, "")):
            findings.append(IntegrityFinding("ASSERTION_ALWAYS_TRUE", "high", path, "Migrated test contains assertTrue(true).", "high", "assertTrue(true)", "This may be legitimate only during a temporary diagnostic test; review before acceptance."))
        if re.search(r"assertNotNull\s*\(", migrated.get(path, "")) and "assertEquals" in baseline.get(path, "") and "assertEquals" not in migrated.get(path, ""):
            findings.append(IntegrityFinding("ASSERTION_WEAKENED", "medium", path, "An equality assertion was replaced with a nullness assertion.", "medium", "assertEquals -> assertNotNull"))
    old_total = sum(int(v["tests"]) for v in before.values())
    new_total = sum(int(v["tests"]) for v in after.values())
    if old_total and new_total / old_total < 0.8:
        findings.append(IntegrityFinding("COVERAGE_REGRESSION_SUSPECTED", "medium", "", f"Test count fell below 80% of baseline ({old_total} to {new_total}).", "high", f"baseline={old_total}; migrated={new_total}"))
    return findings


def compare_snapshot_trees(baseline_root: str | Path, migrated_root: str | Path) -> list[IntegrityFinding]:
    def files(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): path.read_text(encoding="utf-8", errors="replace")
            for path in root.rglob("*.java")
            if ".git" not in path.parts and "target" not in path.parts
        }
    return compare_test_trees(files(Path(baseline_root)), files(Path(migrated_root)))
