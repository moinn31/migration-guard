from evaluation.metrics import confusion_matrix, summarize_rows


def test_confusion_metrics():
    counts = confusion_matrix([True, True, False, False], [True, False, True, False])
    assert counts.true_positive == 1
    assert counts.false_positive == 1
    assert counts.false_negative == 1
    assert round(counts.f1, 3) == 0.5


def test_summary_metrics():
    summary = summarize_rows([{"build_success": True, "tests_preserved": True, "regression_detected": False, "false_positive": False, "unnecessary_change": True}])
    assert summary["build_success_rate"] == 1.0
    assert summary["unnecessary_change_rate"] == 1.0
