# ⚾ Moneyball — Pipeline MLOps de scouting amateur

Pipeline de données et de machine learning qui agrège des statistiques de
frappeurs amateurs (NCAA / summer leagues) et des rapports de scouts, puis
entraîne un modèle pour prédire la **Future Value (FV)** d'un prospect sur
l'échelle scouting standard **20–80**.

## Architecture

Le projet suit une architecture *medallion* (Bronze / Silver) :

```
                 ┌─────────────┐        ┌──────────────┐        ┌───────────┐
  Sources  ───▶  │   BRONZE    │  ───▶  │    SILVER    │  ───▶  │    ML     │
 (web/PDF)       │  MinIO (S3) │        │  PostgreSQL  │        │  XGBoost  │
                 │  data brute │        │ data validée │        │ Model Reg │
                 └─────────────┘        └──────────────┘        └───────────┘
```

| Couche  | Service         | Rôle                                                    |
|---------|-----------------|---------------------------------------------------------|
| Bronze  | MinIO (S3)      | Datalake : dépôt brut (JSONL de stats, PDF de scouts)   |
| Silver  | PostgreSQL      | Data Warehouse : données validées et dédupliquées       |
| ML      | MinIO (S3)      | Model Registry : modèles `.joblib` versionnés           |

## Composants (`src/`)

| Fichier          | Étape du pipeline                                                            |
|------------------|-----------------------------------------------------------------------------|
| `models.py`      | Schéma Pydantic `HitterStat` (validation des stats).                        |
| `scraper.py`     | Scrape les tableaux de stats NCAA (retry + mapping dynamique des colonnes). |
| `main.py`        | Orchestration : scrape → cache local JSONL → upload Bronze (S3).           |
| `loader.py`      | Bronze → Silver : charge le JSONL S3 dans PostgreSQL (UPSERT).             |
| `nlp_parser.py`  | Parse les PDF de scouts (regex + Pydantic) → table `scout_grades`.         |
| `train.py`       | Silver → ML : JOIN quantitatif/qualitatif, entraîne XGBoost, pousse le modèle. |
| `mock_pdf.py`    | Utilitaire : génère un rapport de scout PDF de démo et l'envoie en Bronze.  |

## Démarrage rapide

```bash
# 1. Lancer l'infrastructure (Datalake + Warehouse)
docker compose up -d minio postgres

# 2. Ingestion des stats (Bronze) — TARGET_URL = page de stats NCAA
TARGET_URL="https://exemple.com/ncaa/hitting" FILE_NAME="hitters.jsonl" \
  docker compose run --rm worker python src/main.py

# 3. Chargement Bronze → Silver
FILE_NAME="hitters.jsonl" \
  docker compose run --rm worker python src/loader.py

# 4. (Démo) Rapport de scout + parsing NLP
docker compose run --rm worker python src/mock_pdf.py
FILE_NAME="condon_report.pdf" S3_BUCKET="bronze-scout-reports" \
  docker compose run --rm worker python src/nlp_parser.py

# 5. Entraînement du modèle de FV
docker compose run --rm worker python src/train.py
```

- Console MinIO : http://localhost:9001 (`admin` / `password123`)
- PostgreSQL : `localhost:5432`, base `scouting_db` (`mlops` / `moneyball_password`)

> ⚠️ Les identifiants par défaut sont destinés au développement local
> uniquement. En dehors de la machine locale, fournissez-les via des
> variables d'environnement / secrets et ne les commitez jamais.

## Variables d'environnement

| Variable            | Défaut                   | Utilisé par            |
|---------------------|--------------------------|------------------------|
| `TARGET_URL`        | *(requis)*               | `main.py`              |
| `FILE_NAME`         | `raw_extract.jsonl`      | `main`/`loader`/`nlp`  |
| `S3_ENDPOINT`       | `http://minio:9000`      | tous les jobs S3       |
| `S3_BUCKET`         | `bronze-amateur-stats`   | `main`/`loader`        |
| `S3_MODEL_BUCKET`   | `ml-models`              | `train.py`             |
| `PG_HOST`/`PG_PORT` | `postgres` / `5432`      | `loader`/`nlp`/`train` |

## Tests

Les tests unitaires couvrent la logique pure (parsing, validation), sans
dépendance à S3 ni PostgreSQL :

```bash
pip install -r requirements-dev.txt
pytest
```

La CI (`.github/workflows/ci.yml`) exécute la suite de tests et vérifie que
l'image Docker du worker se construit à chaque push / pull request.
