from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class MigrationProposal:
    code: str
    path: str
    title: str
    rationale: str
    diff: str
    reversible: bool = True
    advisory: bool = True


def build_java17_plan(metadata: dict, findings: Iterable[object] = ()) -> list[MigrationProposal]:
    """Create deterministic, reviewable Java 8 -> 17 proposals without editing files."""
    if metadata.get("language") != "java" or metadata.get("build_system") != "maven":
        return []

    proposals = [
        MigrationProposal(
            code="JAVA_TARGET_17",
            path="pom.xml",
            title="Set Maven compiler release to Java 17",
            rationale="The migration target is Java 17; using release keeps source and bytecode compatibility explicit.",
            diff="@@ pom.xml\n+ <maven.compiler.release>17</maven.compiler.release>",
        ),
        MigrationProposal(
            code="JUNIT5_COMPATIBILITY_REVIEW",
            path="pom.xml",
            title="Review test dependencies for Java 17 compatibility",
            rationale="Test plugins and dependencies should be checked before any source change is accepted.",
            diff="@@ pom.xml\n~ Review surefire and test dependency versions for Java 17 support.",
        ),
    ]
    for finding in findings:
        code = getattr(finding, "code", "")
        if code == "MAVEN_NOT_DETECTED":
            proposals.clear()
    return proposals


def explain_proposal(proposal: MigrationProposal) -> str:
    """Provider-neutral explanation boundary; deterministic by design in Phase 5."""
    reversibility = "reversible" if proposal.reversible else "requires manual rollback"
    return f"{proposal.rationale} This is advisory and {reversibility}; review the diff before approval."
