from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Counts:
    true_positive: int
    false_positive: int
    false_negative: int
    true_negative: int

    @property
    def precision(self) -> float:
        return self.true_positive / max(self.true_positive + self.false_positive, 1)

    @property
    def recall(self) -> float:
        return self.true_positive / max(self.true_positive + self.false_negative, 1)

    @property
    def f1(self) -> float:
        return 2 * self.precision * self.recall / max(self.precision + self.recall, 1e-12)


def confusion_matrix(labels: Iterable[bool], predictions: Iterable[bool]) -> Counts:
    values = [(bool(label), bool(prediction)) for label, prediction in zip(labels, predictions)]
    return Counts(
        sum(label and prediction for label, prediction in values),
        sum(not label and prediction for label, prediction in values),
        sum(label and not prediction for label, prediction in values),
        sum(not label and not prediction for label, prediction in values),
    )


def summarize_rows(rows: list[dict]) -> dict[str, float]:
    if not rows:
        return {"build_success_rate": 0.0, "test_preservation_rate": 0.0, "regression_detection_rate": 0.0, "false_positive_rate": 0.0, "unnecessary_change_rate": 0.0}
    total = len(rows)
    return {
        "build_success_rate": sum(row.get("build_success", False) for row in rows) / total,
        "test_preservation_rate": sum(row.get("tests_preserved", False) for row in rows) / total,
        "regression_detection_rate": sum(row.get("regression_detected", False) for row in rows) / total,
        "false_positive_rate": sum(row.get("false_positive", False) for row in rows) / total,
        "unnecessary_change_rate": sum(row.get("unnecessary_change", False) for row in rows) / total,
    }
