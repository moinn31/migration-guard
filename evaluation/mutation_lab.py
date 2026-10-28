from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil


@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    label: str
    path: str
    description: str
    negative_control: bool = False


def mutate_repository(source: str | Path, destination: str | Path) -> list[Mutation]:
    source, destination = Path(source), Path(destination)
    shutil.copytree(source, destination, dirs_exist_ok=True)
    mutations: list[Mutation] = []
    for path in destination.rglob("*.java"):
        if "src/test" not in path.as_posix():
            continue
        original = path.read_text(encoding="utf-8")
        if "@Test" in original:
            path.write_text(re.sub(r"(?s)@Test.*?(?=\n\s*})", "", original, count=1), encoding="utf-8")
            mutations.append(Mutation("deleted-test", "deleted_test", path.relative_to(destination).as_posix(), "Removed one test method."))
            break
    return mutations
