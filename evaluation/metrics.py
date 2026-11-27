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


def summarize_rows(rows: list[dict]) -> dict[str, float | None]:
    fields = {'build_success_rate': 'build_success', 'test_preservation_rate': 'tests_preserved',
              'regression_detection_rate': 'regression_detected', 'false_positive_rate': 'false_positive',
              'unnecessary_change_rate': 'unnecessary_change'}
    summary = {}
    for name, field in fields.items():
        observed = [row[field] for row in rows if isinstance(row.get(field), bool)]
        summary[name] = sum(observed) / len(observed) if observed else None
    return summary
