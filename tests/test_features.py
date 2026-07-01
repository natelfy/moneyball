import pandas as pd

from features import (
    MODEL_FEATURE_COLUMNS,
    add_sabermetric_features,
    compute_sabermetrics,
)


def test_compute_sabermetrics_basic():
    m = compute_sabermetrics(at_bats=200, hits=70, home_runs=34, walks=25, strikeouts=60)
    assert m["batting_avg"] == 0.35              # 70/200
    assert m["obp"] == round(95 / 225, 4)        # (70+25)/(200+25)
    assert m["bb_rate"] == round(25 / 225, 4)
    assert m["k_rate"] == round(60 / 225, 4)
    assert m["bb_per_k"] == round(25 / 60, 4)
    assert m["hr_rate"] == round(34 / 200, 4)


def test_compute_sabermetrics_handles_zero_at_bats():
    # Cas réel : les fichiers "leaders de HR" ont at_bats=0.
    m = compute_sabermetrics(at_bats=0, hits=0, home_runs=34, walks=0, strikeouts=0)
    assert m["batting_avg"] == 0.0
    assert m["obp"] == 0.0
    assert m["bb_per_k"] == 0.0
    assert m["hr_rate"] == 0.0


def test_compute_sabermetrics_ignores_extra_kwargs():
    # On peut déballer un enregistrement complet sans filtrer les champs.
    record = {
        "games_played": 57, "at_bats": 100, "hits": 30, "home_runs": 5,
        "walks": 10, "strikeouts": 20, "player_name": "X",
    }
    m = compute_sabermetrics(**record)
    assert m["batting_avg"] == 0.30


def test_add_sabermetric_features_adds_all_columns():
    df = pd.DataFrame([
        {"games_played": 57, "at_bats": 200, "hits": 70,
         "home_runs": 34, "walks": 25, "strikeouts": 60},
    ])
    out = add_sabermetric_features(df)
    for col in MODEL_FEATURE_COLUMNS:
        if col in ("hit_grade", "power_grade", "run_grade", "arm_grade", "field_grade"):
            continue  # notes de scout, absentes de ce df de comptages
        assert col in out.columns
    assert out.loc[0, "batting_avg"] == 0.35


def test_add_sabermetric_features_empty_df():
    df = pd.DataFrame(columns=["games_played", "at_bats", "hits",
                               "home_runs", "walks", "strikeouts"])
    out = add_sabermetric_features(df)
    assert "obp" in out.columns
    assert len(out) == 0
