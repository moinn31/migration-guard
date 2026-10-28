from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET

try:
    from tree_sitter import Language, Parser
    import tree_sitter_java
except ImportError:
    Language = Parser = tree_sitter_java = None


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    message: str
    path: str | None = None
    line_number: int | None = None
    provenance: str | None = None
    confidence: str = "high"
    evidence: str | None = None
    note: str | None = None


def _strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _pom_values(root: ET.Element, name: str) -> list[str]:
    return [child.text.strip() for child in root.iter() if _strip_namespace(child.tag) == name and child.text and child.text.strip()]


def _source_line(path: Path, offset: int) -> int:
    return path.read_text(encoding="utf-8", errors="replace")[:offset].count("\n") + 1


def _java_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    patterns = (
        ("INTERNAL_JDK_API", r"\bsun\.[A-Za-z0-9_.]+", "Use of an internal sun.* JDK API."),
        ("REMOVED_JDK_API", r"\bjavax\.xml\.bind\b", "javax.xml.bind was removed from the JDK after Java 8."),
        ("REMOVED_JDK_API", r"\bjavax\.annotation\b", "javax.annotation is not included in modern JDK distributions."),
        ("REMOVED_JDK_API", r"\bNashorn\b|javax\.script\.ScriptEngine", "Nashorn-era scripting APIs require migration review."),
        ("REMOVED_JDK_API", r"\bSecurityManager\b", "SecurityManager is deprecated/disabled in modern Java."),
    )
    for path in sorted(root.rglob("*.java")):
        if any(part in {".git", "target"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(root).as_posix()
        if Parser is not None and tree_sitter_java is not None:
            parser = Parser(Language(tree_sitter_java.language()))
            parser.parse(text.encode("utf-8"))
        for code, pattern, message in patterns:
            for match in re.finditer(pattern, text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(Finding(
                    "high", code, message, relative, line,
                    "Java source scan; tree-sitter-java grammar dependency is used when available.",
                    "high", match.group(0),
                    "This may be legitimate when a compatibility dependency supplies the API; verify the target runtime.",
                ))
    return findings


def analyze_repository(snapshot_path: str | Path) -> tuple[dict, list[Finding]]:
    root = Path(snapshot_path).resolve()
    pom = root / "pom.xml"
    metadata = {
        "repository_name": root.name,
        "source_type": "snapshot",
        "language": "unknown",
        "build_system": "unknown",
        "detected_files": [],
        "supported_target": False,
        "modules": [],
        "parent": None,
        "properties": {},
        "compiler": {},
        "dependencies": [],
        "plugins": [],
    }
    if not pom.is_file():
        return metadata, [Finding(
            "info", "NOT_MAVEN_PROJECT", "No pom.xml was found; this is not a Maven project.",
            None, None, "Filesystem snapshot analysis", "high", None, "A non-Maven repository is not inferred from its URL.",
        )]
    try:
        tree = ET.parse(pom)
    except ET.ParseError as exc:
        return metadata, [Finding("high", "POM_PARSE_ERROR", f"pom.xml could not be parsed: {exc}", "pom.xml", None, "pom.xml", "high")]
    root_element = tree.getroot()
    metadata.update({
        "language": "java",
        "build_system": "maven",
        "detected_files": ["pom.xml"],
        "supported_target": True,
        "modules": _pom_values(root_element, "module"),
        "parent": {child.tag.rsplit("}", 1)[-1]: child.text.strip() for parent in root_element if _strip_namespace(parent.tag) == "parent" for child in parent if child.text},
        "properties": {
            _strip_namespace(child.tag): child.text.strip()
            for properties in root_element
            if _strip_namespace(properties.tag) == "properties"
            for child in properties
            if child.text and child.text.strip()
        },
        "dependencies": [],
        "plugins": [],
    })
    compiler: dict[str, str] = {}
    for key in ("java.version", "maven.compiler.release", "maven.compiler.source", "maven.compiler.target"):
        if key in metadata["properties"]:
            compiler[key] = metadata["properties"][key]
    for plugin in root_element.iter():
        if _strip_namespace(plugin.tag) != "plugin":
            continue
        values = {_strip_namespace(child.tag): child.text.strip() for child in plugin if child.text and child.text.strip()}
        if values.get("artifactId") == "maven-compiler-plugin":
            compiler.update({key: value for key, value in values.items() if key in {"groupId", "artifactId", "version"}})
            for config in plugin:
                if _strip_namespace(config.tag) == "configuration":
                    compiler.update({_strip_namespace(child.tag): child.text.strip() for child in config if child.text and child.text.strip()})
        if values.get("artifactId"):
            metadata["plugins"].append(values)
    metadata["compiler"] = compiler
    metadata["dependencies"] = [
        {_strip_namespace(child.tag): child.text.strip() for child in dependency if child.text and child.text.strip()}
        for dependency in root_element.iter()
        if _strip_namespace(dependency.tag) == "dependency"
    ]
    return metadata, _java_findings(root)
