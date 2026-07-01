import pandas as pd
import pytest
from sklearn.pipeline import Pipeline

from features import MODEL_FEATURE_COLUMNS, add_sabermetric_features
from train import train_model


def _sample_rows(n):
    rows = []
    for i in range(n):
        rows.append({
            "games_played": 50 + i, "at_bats": 180 + i, "hits": 60 + i,
            "home_runs": 10 + i, "walks": 20 + i, "strikeouts": 40 + i,
            "hit_grade": 50, "power_grade": 55, "run_grade": 45,
            "arm_grade": 50, "field_grade": 50, "overall_fv": 50 + (i % 3) * 5,
        })
    return pd.DataFrame(rows)


def _feature_frame(df):
    return add_sabermetric_features(df.copy())[MODEL_FEATURE_COLUMNS]


def test_train_model_poc_branch_returns_fitted_pipeline():
    # < 5 lignes : branche Proof-of-Concept (pas de split train/test).
    df = _sample_rows(3)
    model = train_model(df)
    assert isinstance(model, Pipeline)
    preds = model.predict(_feature_frame(df))
    assert len(preds) == 3


def test_train_model_standard_branch():
    model = train_model(_sample_rows(8))
    assert isinstance(model, Pipeline)


def test_train_model_empty_raises():
    with pytest.raises(ValueError):
        train_model(pd.DataFrame())
