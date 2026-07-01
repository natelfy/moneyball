"""API d'inférence : score la Future Value (20-80) d'un prospect.

Charge le pipeline entraîné depuis le Model Registry (S3/MinIO) et l'expose
via un endpoint HTTP. Les features sont calculées avec `features.py`, donc
identiques à celles de l'entraînement.
"""
import logging
import os
from functools import lru_cache

import boto3
import joblib
import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from features import MODEL_FEATURE_COLUMNS, compute_sabermetrics
from scoring import rank_prospects, to_scout_scale
from valuation import compare_to_scout

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("inference-api")


class ProspectStats(BaseModel):
    """Entrée : comptages bruts + notes de scout (mêmes champs qu'à l'entraînement)."""
    games_played: int = Field(default=0, ge=0)
    at_bats: int = Field(ge=0)
    hits: int = Field(default=0, ge=0)
    home_runs: int = Field(default=0, ge=0)
    walks: int = Field(default=0, ge=0)
    strikeouts: int = Field(default=0, ge=0)
    hit_grade: int = Field(default=40, ge=20, le=80)
    power_grade: int = Field(default=40, ge=20, le=80)
    run_grade: int = Field(default=40, ge=20, le=80)
    arm_grade: int = Field(default=40, ge=20, le=80)
    field_grade: int = Field(default=40, ge=20, le=80)


class ProspectCounts(BaseModel):
    """Comptages bruts pour le scoring statistique (sans notes de scout requises)."""
    player_name: str = "Unknown"
    team: str = "Unknown"
    games_played: int = Field(default=0, ge=0)
    at_bats: int = Field(default=0, ge=0)
    hits: int = Field(default=0, ge=0)
    home_runs: int = Field(default=0, ge=0)
    walks: int = Field(default=0, ge=0)
    strikeouts: int = Field(default=0, ge=0)


class RankRequest(BaseModel):
    prospects: list[ProspectCounts]


class ValuationRequest(BaseModel):
    """Comptages du joueur + grades du scout, pour détecter une sous-évaluation."""
    games_played: int = Field(default=0, ge=0)
    at_bats: int = Field(default=0, ge=0)
    hits: int = Field(default=0, ge=0)
    home_runs: int = Field(default=0, ge=0)
    walks: int = Field(default=0, ge=0)
    strikeouts: int = Field(default=0, ge=0)
    scout_hit_grade: int = Field(ge=20, le=80)
    scout_power_grade: int = Field(ge=20, le=80)


def _download_model_from_s3(local_path: str) -> None:
    bucket = os.getenv("S3_MODEL_BUCKET", "ml-models")
    key = os.getenv("MODEL_NAME", "draft_fv_predictor_v1.joblib")
    s3 = boto3.client(
        's3',
        endpoint_url=os.getenv('S3_ENDPOINT', 'http://minio:9000'),
        aws_access_key_id=os.getenv('S3_ACCESS_KEY', 'admin'),
        aws_secret_access_key=os.getenv('S3_SECRET_KEY', 'password123'),
        region_name='us-east-1',
    )
    logger.info(f"Téléchargement du modèle s3://{bucket}/{key}")
    s3.download_file(bucket, key, local_path)


@lru_cache(maxsize=1)
def get_model():
    """Charge le modèle une seule fois (cache). Surchargée dans les tests.

    Si MODEL_LOCAL_PATH pointe vers un fichier existant, il est utilisé
    directement ; sinon le modèle est récupéré depuis le registry S3.
    """
    local_path = os.getenv("MODEL_LOCAL_PATH", "/tmp/model.joblib")
    if not (os.getenv("MODEL_LOCAL_PATH") and os.path.exists(local_path)):
        _download_model_from_s3(local_path)
    return joblib.load(local_path)


def build_feature_frame(stats: ProspectStats) -> pd.DataFrame:
    """Assemble le vecteur de features dans l'ordre attendu par le modèle."""
    record = stats.model_dump()
    record.update(compute_sabermetrics(**record))
    return pd.DataFrame([[record[c] for c in MODEL_FEATURE_COLUMNS]], columns=MODEL_FEATURE_COLUMNS)


app = FastAPI(title="Moneyball FV Predictor", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/predict")
def predict(stats: ProspectStats, model=Depends(get_model)) -> dict:
    try:
        features = build_feature_frame(stats)
        raw_fv = float(model.predict(features)[0])
    except Exception as e:  # noqa: BLE001 - on renvoie une 500 explicite
        logger.error(f"Échec de la prédiction : {e}")
        raise HTTPException(status_code=500, detail="Prediction failed") from e

    return {
        "predicted_fv": round(raw_fv, 2),
        "rounded_fv": to_scout_scale(raw_fv),
        "scale": "20-80",
    }


@app.post("/rank")
def rank(request: RankRequest) -> dict:
    """Classe des prospects par note globale à partir de leurs stats seules.

    Ne nécessite pas de modèle entraîné : le scoring 20-80 est transparent et
    dérivé directement des sabermétriques (utile pour un tableau de scouting).
    """
    ranked = rank_prospects([p.model_dump() for p in request.prospects])
    return {
        "count": len(ranked),
        "ranking": [
            {
                "player_name": r["player_name"],
                "team": r["team"],
                "overall_fv": r["scouting"]["overall_fv"],
                "grades": r["scouting"]["grades"],
                "data_completeness": r["scouting"]["data_completeness"],
            }
            for r in ranked
        ],
    }


@app.post("/valuation")
def valuation(request: ValuationRequest) -> dict:
    """Détecte une inefficience de marché : grade statistique vs grade du scout.

    `gap` positif = la production dépasse la réputation (potentielle pépite).
    """
    stats = request.model_dump()
    scout = {
        "hit_grade": stats.pop("scout_hit_grade"),
        "power_grade": stats.pop("scout_power_grade"),
    }
    return compare_to_scout(stats, scout)
