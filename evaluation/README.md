# MigrationGuard evaluation

The runner evaluates exported verification reports and writes CSV/Markdown artifacts under `results/`. It does not run a four-system MigrationBench experiment. Missing build/test evidence and unlabeled outcomes remain unavailable, rather than being counted as failures or negatives.

Export JSON from `/runs/{id}/report`, then set `reports: [path/to/report.json]` in a copy of `evaluation/config.yaml`. Run `python -m evaluation.run --config path/to/config.yaml --max_workers 2`. Empty reports configuration fails explicitly without writing synthetic results. Both raw report objects and API objects containing `content` are accepted.

`--inspect-dataset` remains an optional dataset metadata inspection command and requires `datasets`. The benchmark API/UI summarize only the authenticated owner's persisted reports. Regression observations are not labeled detection accuracy; false-positive and unnecessary-change rates remain unavailable without independent labels. Real dataset adapters and controlled four-system experiments remain future work.

Ground truth is created only for controlled mutations (deleted/disabled/weakened tests and injected regressions). Benchmark repositories without those labels must not be treated as negative examples. Risk scores are explainable heuristics, not calibrated probabilities.
