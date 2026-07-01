"""Feature engineering sabermétrique partagé entre l'entraînement et l'API.

Centraliser le calcul ici garantit la *parité train/inférence* : le modèle est
entraîné et interrogé avec exactement les mêmes colonnes, dans le même ordre.
"""

import pandas as pd

# Colonnes de comptage brutes issues des stats de frappeurs.
RAW_COUNT_COLUMNS = [
    "games_played", "at_bats", "hits", "home_runs", "walks", "strikeouts",
]

# Ratios sabermétriques dérivés des comptages ci-dessus.
SABERMETRIC_COLUMNS = [
    "batting_avg",  # H / AB
    "obp",          # (H + BB) / (AB + BB) — approx. sans HBP/SF
    "bb_rate",      # BB / PA
    "k_rate",       # SO / PA
    "bb_per_k",     # BB / SO (discipline au bâton)
    "hr_rate",      # HR / AB (proxy de puissance ; ISO indisponible sans XBH)
]

# Notes de scout (échelle 20-80) utilisées comme features qualitatives.
SCOUT_GRADE_COLUMNS = [
    "hit_grade", "power_grade", "run_grade", "arm_grade", "field_grade",
]

# Vecteur de features complet attendu par le modèle, dans l'ordre.
MODEL_FEATURE_COLUMNS = (
    RAW_COUNT_COLUMNS + SABERMETRIC_COLUMNS + SCOUT_GRADE_COLUMNS
)


def _safe_div(numerator: float, denominator: float) -> float:
    """Division protégée : retourne 0.0 si le dénominateur est nul.

    Indispensable car certaines sources fournissent AB=0 (ex: leaders de HR)."""
    return numerator / denominator if denominator else 0.0


def compute_sabermetrics(
    at_bats: int,
    hits: int,
    home_runs: int,
    walks: int,
    strikeouts: int,
    **_ignored: object,
) -> dict[str, float]:
    """Calcule les ratios sabermétriques à partir des comptages bruts.

    Accepte des kwargs supplémentaires (ex: games_played) qui sont ignorés,
    pour pouvoir déballer un enregistrement complet sans filtrage préalable.
    """
    plate_appearances = at_bats + walks
    return {
        "batting_avg": round(_safe_div(hits, at_bats), 4),
        "obp": round(_safe_div(hits + walks, plate_appearances), 4),
        "bb_rate": round(_safe_div(walks, plate_appearances), 4),
        "k_rate": round(_safe_div(strikeouts, plate_appearances), 4),
        "bb_per_k": round(_safe_div(walks, strikeouts), 4),
        "hr_rate": round(_safe_div(home_runs, at_bats), 4),
    }


def add_sabermetric_features(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les colonnes sabermétriques à un DataFrame de comptages.

    Le calcul est fait ligne à ligne via `compute_sabermetrics`, garantissant
    une logique strictement identique à celle de l'inférence unitaire.
    """
    if df.empty:
        for col in SABERMETRIC_COLUMNS:
            df[col] = pd.Series(dtype="float64")
        return df

    metrics = df.apply(
        lambda row: compute_sabermetrics(
            at_bats=row["at_bats"],
            hits=row["hits"],
            home_runs=row["home_runs"],
            walks=row["walks"],
            strikeouts=row["strikeouts"],
        ),
        axis=1,
        result_type="expand",
    )
    return pd.concat([df, metrics], axis=1)
