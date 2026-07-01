"""Harnais d'évaluation du modèle de Future Value.

Rend la qualité du modèle mesurable et honnête :
- cross-validation K-fold (MAE moyenne ± écart-type) ;
- comparaison à un baseline naïf (prédire la moyenne) → l'amélioration réelle ;
- importances des features (quels outils pilotent la prédiction).

Charge les données depuis le Data Warehouse ou depuis un fichier JSONL
labellisé (`--data`), ce qui permet de brancher un dataset de drafts
historiques dès qu'il est disponible.
"""
import argparse
import json
import logging

import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.model_selection import KFold, cross_val_score

from features import MODEL_FEATURE_COLUMNS, add_sabermetric_features
from train import build_pipeline

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("model-evaluator")

TARGET = "overall_fv"


def _feature_target(df: pd.DataFrame):
    df = add_sabermetric_features(df.copy())
    return df[MODEL_FEATURE_COLUMNS], df[TARGET]


def cross_validate_model(df: pd.DataFrame, k: int = 5) -> dict:
    """Cross-validation MAE + baseline naïf. Retourne un rapport chiffré."""
    if TARGET not in df.columns:
        raise ValueError(f"Colonne cible '{TARGET}' absente du dataset.")
    if len(df) < 2:
        raise ValueError("Au moins 2 échantillons requis pour la cross-validation.")

    X, y = _feature_target(df)
    n_splits = min(k, len(df))
    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)

    mae = -cross_val_score(build_pipeline(), X, y, cv=kf, scoring="neg_mean_absolute_error")
    baseline = -cross_val_score(
        DummyRegressor(strategy="mean"), X, y, cv=kf, scoring="neg_mean_absolute_error"
    )

    base_mean = float(baseline.mean())
    mae_mean = float(mae.mean())
    improvement = (base_mean - mae_mean) / base_mean * 100 if base_mean else 0.0
    return {
        "samples": len(df),
        "folds": n_splits,
        "mae_mean": round(mae_mean, 3),
        "mae_std": round(float(mae.std()), 3),
        "baseline_mae": round(base_mean, 3),
        "improvement_pct": round(improvement, 1),
    }


def feature_importance(df: pd.DataFrame) -> list:
    """Importances XGBoost, triées décroissant : (feature, importance)."""
    X, y = _feature_target(df)
    pipe = build_pipeline()
    pipe.fit(X, y)
    importances = pipe.named_steps["xgb"].feature_importances_
    ranked = sorted(zip(MODEL_FEATURE_COLUMNS, importances, strict=True),
                    key=lambda t: t[1], reverse=True)
    return [(name, round(float(imp), 4)) for name, imp in ranked]


def load_labeled(path: str) -> pd.DataFrame:
    """Charge un dataset labellisé JSONL (comptages + grades scout + overall_fv)."""
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(line) for line in fh if line.strip()]
    return pd.DataFrame(rows)


def format_report(cv: dict, importances: list, top: int = 8) -> str:
    lines = [
        "═" * 60,
        "ÉVALUATION DU MODÈLE DE FUTURE VALUE",
        "─" * 60,
        f"Échantillons        : {cv['samples']}",
        f"Cross-validation    : {cv['folds']}-fold",
        f"MAE modèle          : {cv['mae_mean']} ± {cv['mae_std']} pts de FV",
        f"MAE baseline (moy.) : {cv['baseline_mae']} pts",
        f"Amélioration        : {cv['improvement_pct']}% vs baseline",
        "─" * 60,
        "IMPORTANCE DES FEATURES (top)",
    ]
    for name, imp in importances[:top]:
        bar = "█" * int(round(imp * 40))
        lines.append(f"  {name:<14} {imp:>6.3f} {bar}")
    lines.append("═" * 60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Évaluation du modèle de FV")
    parser.add_argument("--data", metavar="PATH", help="Dataset JSONL labellisé")
    parser.add_argument("--folds", type=int, default=5)
    args = parser.parse_args()

    if args.data:
        df = load_labeled(args.data)
    else:
        from train import extract_features  # import local : nécessite PostgreSQL
        df = extract_features()

    cv = cross_validate_model(df, k=args.folds)
    importances = feature_importance(df)
    print(format_report(cv, importances))


if __name__ == "__main__":
    main()
