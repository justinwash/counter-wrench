"""Judge-calibration math, checked against hand-computed values."""

import json

import pytest

from evals.calibration.agreement import SET_FILE, cohen_kappa, metrics


def test_kappa_matches_hand_computation():
    a = ["pass", "pass", "fail", "fail", "pass", "fail"]
    b = ["pass", "fail", "fail", "fail", "pass", "pass"]
    # observed 4/6; chance: both "pass" 0.5*0.5 + both "fail" 0.5*0.5 = 0.5 -> (0.667-0.5)/0.5
    assert cohen_kappa(a, b) == pytest.approx(1 / 3)
    assert cohen_kappa(a, a) == pytest.approx(1.0)
    assert cohen_kappa(["pass", "pass"], ["pass", "pass"]) is None  # chance agreement is total


def test_metrics_split_errors_by_direction():
    pairs = [("pass", "pass"), ("pass", "fail"), ("fail", "fail"), ("fail", "fail")]
    m = metrics(pairs)
    assert (m["n"], m["accuracy"], m["tpr"], m["tnr"]) == (4, 0.75, 0.5, 1.0)


def test_calibration_set_is_balanced_and_blind_ready():
    items = json.loads(SET_FILE.read_text("utf-8"))["items"]
    assert len(items) == 40 and len({i["id"] for i in items}) == 40
    for judge in ("diagnosis_reasonable", "explanation_quality"):
        for verdict in ("pass", "fail"):
            group = [i for i in items if i["judge"] == judge and i["judge_verdict"] == verdict]
            assert [i["split"] for i in group].count("dev") == 6 and len(group) == 10
