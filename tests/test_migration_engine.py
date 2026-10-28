from pathlib import Path
import shutil

import pytest

from backend.migration_engine import (
    _hunk,
    apply_rule_migrations,
    migrate_snapshot,
    snapshot_hash,
)


ROOT = Path(__file__).parents[1]


def test_clean_fixture_gets_compiler_rule_without_touching_snapshot(tmp_path):
    source = tmp_path / "snapshot"
    shutil.copytree(ROOT / "examples" / "clean-java8", source)
    expected = snapshot_hash(source)
    working, changes, _ = migrate_snapshot(source, expected, openrewrite_runner=lambda *args, **kwargs: "")
    assert snapshot_hash(source) == expected
    assert "<maven.compiler.source>17</maven.compiler.source>" in (working / "pom.xml").read_text()
    assert any(item.rule_id == "MAVEN_COMPILER_TARGET_17" for item in changes)


def test_jaxb_rule_is_deterministic(tmp_path):
    working = tmp_path / "working"
    shutil.copytree(ROOT / "examples" / "javax-xml-bind", working)
    changes = apply_rule_migrations(working)
    assert any(item.rule_id == "ADD_JAKARTA_JAXB" for item in changes)
    assert "jakarta.xml.bind-api" in (working / "pom.xml").read_text()


def test_hostile_test_deletion_is_protected():
    result = _hunk(
        Path("src/test/java/example/AppTest.java"),
        Path("."),
        "class AppTest { void testA() {} }\n",
        "",
        "openrewrite",
        "HOSTILE_DELETE_TEST",
        "hostile recipe output",
    )
    assert result is not None
    assert result.protected is True
    assert result.diff == ""


def test_snapshot_hash_mismatch_is_rejected(tmp_path):
    source = tmp_path / "snapshot"
    shutil.copytree(ROOT / "examples" / "clean-java8", source)
    with pytest.raises(ValueError, match="hash mismatch"):
        migrate_snapshot(source, "bad-hash", openrewrite_runner=lambda *args, **kwargs: "")


def test_hostile_recipe_output_cannot_delete_test(tmp_path):
    source = tmp_path / "snapshot"
    shutil.copytree(ROOT / "examples" / "clean-java8", source)
    expected = snapshot_hash(source)

    def hostile(working, **_):
        test = Path(working) / "src/test/java/example/AppTest.java"
        test.unlink()
        return "hostile"

    working, changes, _ = migrate_snapshot(source, expected, openrewrite_runner=hostile)
    assert (working / "src/test/java/example/AppTest.java").exists()
    assert any(item.protected and item.source == "openrewrite" for item in changes)
