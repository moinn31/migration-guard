from pathlib import Path

from backend.analyzer import analyze_repository

ROOT = Path(__file__).parents[1]


def test_detects_java8_from_real_pom():
    metadata, findings = analyze_repository(ROOT / "examples" / "clean-java8")
    assert metadata["build_system"] == "maven"
    assert metadata["compiler"]["maven.compiler.source"] == "8"
    assert metadata["compiler"]["maven.compiler.target"] == "8"
    assert not findings


def test_detects_removed_javax_api_with_provenance():
    metadata, findings = analyze_repository(ROOT / "examples" / "javax-xml-bind")
    finding = next(item for item in findings if item.code == "REMOVED_JDK_API")
    assert metadata["language"] == "java"
    assert finding.path.endswith("LegacyXml.java")
    assert finding.line_number == 3
    assert finding.provenance


def test_non_maven_snapshot_is_explicit():
    metadata, findings = analyze_repository(ROOT / "examples" / "integrity-deleted")
    assert metadata["build_system"] == "unknown"
    assert findings[0].code == "NOT_MAVEN_PROJECT"
