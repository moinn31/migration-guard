# MigrationGuard evaluation

The reproducible evaluation module is intentionally isolated from the Next.js preview. It will load the MigrationBench Java/Maven subset, create labeled Mutation Lab variants, run four systems, and write CSV/PNG/Markdown artifacts under `results/`.

Runner contract: `python -m evaluation.run --config evaluation/config.yaml --max_workers 2`. Run with `--inspect-dataset` first to record the dataset schema and license in `evaluation/DATASET.md`.

Ground truth is created only for controlled mutations (deleted/disabled/weakened tests and injected regressions). Benchmark repositories without those labels must not be treated as negative examples. Risk scores are explainable heuristics, not calibrated probabilities.
