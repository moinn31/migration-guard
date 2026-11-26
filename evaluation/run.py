from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random

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
    import yaml
    from concurrent.futures import ThreadPoolExecutor
    from .evidence import report_row
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    reports = config.get("reports", [])
    if not reports:
        parser.error("Configure reports: [path/to/exported-report.json]. Dataset system adapters are not implemented; no fabricated metrics will be written.")
    output = Path(config.get("outputs", "results/"))
    output.mkdir(parents=True, exist_ok=True)
    def evaluate(path):
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        return report_row(report.get("content", report))
    with ThreadPoolExecutor(max_workers=args.max_workers or config.get("max_workers", 2)) as pool:
        rows = list(pool.map(evaluate, reports))
    with (output / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys() if rows else ["repo", "system"])
        writer.writeheader(); writer.writerows(rows)
    (output / "summary.md").write_text(f"# MigrationGuard evaluation\n\nDataset: `{DATASET}`\n\nPersisted reports evaluated: {len(rows)}. No dataset comparison was executed.\n\n## Metrics\n\n```json\n{json.dumps(summarize_rows(rows), indent=2)}\n```\n\n## Limitations\n\nSample size, dataset selection bias, uncontrolled build environments, and best-effort checks limit generalization. Risk remains heuristic, not a probability.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
