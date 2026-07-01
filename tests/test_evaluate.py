import json

import pandas as pd
import pytest

from evaluate import (
    cross_validate_model,
    feature_importance,
    format_report,
    load_labeled,
)
from features import MODEL_FEATURE_COLUMNS


def _labeled_df(n=25):
    # Signal net : overall_fv croît avec home_runs -> le modèle doit battre
    # le baseline (prédire la moyenne).
    rows = []
    for i in range(n):
        hr = i % 20
        rows.append({
            "games_played": 55, "at_bats": 190, "hits": 60 + (i % 10),
            "home_runs": hr, "walks": 20 + (i % 8), "strikeouts": 40,
            "hit_grade": 50, "power_grade": 45, "run_grade": 45,
            "arm_grade": 50, "field_grade": 50, "overall_fv": 30 + hr,
        })
    return pd.DataFrame(rows)


def test_cross_validate_reports_metrics_and_beats_baseline():
    cv = cross_validate_model(_labeled_df(30), k=5)
    assert cv["folds"] == 5
    assert cv["samples"] == 30
    assert cv["mae_mean"] >= 0
    # Sur un signal clair, le modèle bat la prédiction moyenne.
    assert cv["mae_mean"] < cv["baseline_mae"]
    assert cv["improvement_pct"] > 0


def test_cross_validate_requires_target():
    with pytest.raises(ValueError):
        cross_validate_model(pd.DataFrame([{"at_bats": 100}]))


def test_cross_validate_requires_min_samples():
    df = _labeled_df(1)
    with pytest.raises(ValueError):
        cross_validate_model(df)


def test_feature_importance_ranked_and_complete():
    imp = feature_importance(_labeled_df(30))
    names = [n for n, _ in imp]
    assert set(names) == set(MODEL_FEATURE_COLUMNS)
    values = [v for _, v in imp]
    assert values == sorted(values, reverse=True)


def test_load_labeled_reads_jsonl(tmp_path):
    p = tmp_path / "data.jsonl"
    p.write_text(
        json.dumps({"at_bats": 100, "overall_fv": 50}) + "\n\n"
        + json.dumps({"at_bats": 120, "overall_fv": 55}) + "\n",
        encoding="utf-8",
    )
    df = load_labeled(str(p))
    assert len(df) == 2
    assert list(df["overall_fv"]) == [50, 55]


def test_format_report_contains_sections():
    cv = cross_validate_model(_labeled_df(20), k=4)
    report = format_report(cv, feature_importance(_labeled_df(20)))
    assert "ÉVALUATION DU MODÈLE" in report
    assert "IMPORTANCE DES FEATURES" in report
