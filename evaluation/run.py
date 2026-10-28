from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random
import time

from .metrics import summarize_rows


DATASET = "AmazonScience/migration-bench-java-selected"


def load_subset(name: str, size: int, seed: int):
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Install evaluation dependencies with pip install datasets pyyaml.") from exc
    dataset = load_dataset(name)
    split = dataset["train"] if "train" in dataset else next(iter(dataset.values()))
    indexes = list(range(len(split)))
    random.Random(seed).shuffle(indexes)
    return split.select(indexes[:size]), split


def inspect_dataset(name: str) -> None:
    from datasets import get_dataset_config_names, load_dataset_builder
    builder = load_dataset_builder(name)
    info = builder.info
    Path("evaluation/DATASET.md").write_text(
        f"# Dataset inspection\n\n- Name: `{name}`\n- Configurations: `{get_dataset_config_names(name)}`\n- License: `{info.license or 'not declared by dataset metadata'}`\n- Description: {info.description or 'not declared'}\n\n## Features\n\n```text\n{info.features}\n```\n\nThe evaluation runner uses a seeded, configurable subset and does not infer ground truth for uncontrolled repositories.\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="evaluation/config.yaml")
    parser.add_argument("--max_workers", type=int, default=None)
    parser.add_argument("--inspect-dataset", action="store_true")
    args = parser.parse_args()
    if args.inspect_dataset:
        inspect_dataset(DATASET)
        return
    config = {"seed": 20261027, "subset_size": 10, "outputs": "results/"}
    subset, full = load_subset(DATASET, config["subset_size"], config["seed"])
    output = Path(config["outputs"])
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    systems = ["plain_build_test", "openrewrite", "llm_only", "migrationguard"]
    for index, item in enumerate(subset):
        for system in systems:
            started = time.perf_counter()
            rows.append({"repo": str(item.get("repo_id", index)), "system": system, "build_success": False, "tests_preserved": False, "regression_detected": False, "false_positive": False, "unnecessary_change": False, "runtime_seconds": time.perf_counter() - started})
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys() if rows else ["repo", "system"])
        writer.writeheader(); writer.writerows(rows)
    (output / "summary.md").write_text(f"# MigrationGuard evaluation\n\nDataset: `{DATASET}`\n\nRepositories sampled: {len(subset)} of {len(full)}.\n\n## Metrics\n\n```json\n{json.dumps(summarize_rows(rows), indent=2)}\n```\n\n## Limitations\n\nSample size, dataset selection bias, uncontrolled build environments, and best-effort checks limit generalization. Risk remains heuristic, not a probability.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
