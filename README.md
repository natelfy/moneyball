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
| `features.py`    | Feature engineering sabermétrique partagé (OBP, K%, BB/K…) — parité train/inférence. |
| `scoring.py`     | Moteur de scoring : convertit les stats en grades 20-80 par outil + note globale. |
| `report.py`      | Tableau de scouting : fusionne les sources, score et classe les prospects. |
| `train.py`       | Silver → ML : JOIN quantitatif/qualitatif, entraîne XGBoost, pousse le modèle. |
| `api.py`         | API FastAPI : inférence du modèle (`/predict`) et classement statistique (`/rank`). |
| `mock_pdf.py`    | Utilitaire : génère un rapport de scout PDF de démo et l'envoie en Bronze.  |

### Features sabermétriques

`features.py` dérive des ratios à partir des comptages bruts, utilisés à
l'identique par l'entraînement et l'API : `batting_avg`, `obp`, `bb_rate`,
`k_rate`, `bb_per_k`, `hr_rate` (divisions protégées contre `AB=0`).

### Tableau de scouting (`report.py`)

Traduit les stats en **grades 20-80 façon scout** (`scoring.py`), puis classe
les prospects. Chaque outil (contact, puissance, discipline, on-base) n'est
gradé que si la donnée existe — les sources amateurs sont souvent partielles
(leaders de HR sans AB, leaders d'OBP sans HR). Un `home_runs=0` est traité
comme *stat absente*, pas comme « aucune puissance ». La note globale est une
moyenne pondérée *moneyball* (on-base + puissance d'abord) renormalisée sur les
outils présents.

```bash
# Démo directe sur les fichiers JSONL (sans infrastructure)
PYTHONPATH=src python src/report.py --source local --dir local_data --top 10
# En production : lit le Data Warehouse
PYTHONPATH=src python src/report.py --source postgres
```

Exemple — la section « profils complets » isole les prospects *dual-threat*
(puissance **et** on-base **et** discipline mesurés), la vraie valeur ajoutée :

```
PROFILS COMPLETS / DUAL-THREAT (5 joueurs)
 #  PROSPECT               ÉQUIPE            FV  HIT PWR EYE OBP  DATA
 1  Blake Primrose         Saint Joseph's    75   75  70  80  80  100%
 2  Landon Hairston        Arizona St.       75   80  70  70  80  100%
 3  Chris Katz             Mercer            75   75  60  80  80  100%
```

C'est la fusion des sources (UPSERT `GREATEST`) qui reconstitue ces profils
complets à partir de fichiers partiels.

## Démarrage rapide

```bash
# 0. Configurer les secrets (copie du modèle, à ajuster)
cp .env.example .env

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

# 6. Servir le modèle via l'API d'inférence
docker compose up -d api
```

### Interroger l'API

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"games_played":57,"at_bats":200,"hits":70,"home_runs":34,
       "walks":25,"strikeouts":60,"hit_grade":55,"power_grade":70,
       "run_grade":40,"arm_grade":55,"field_grade":50}'
# → {"predicted_fv": 58.4, "rounded_fv": 60, "scale": "20-80"}

# Classement statistique (sans modèle entraîné requis)
curl -X POST http://localhost:8000/rank \
  -H "Content-Type: application/json" \
  -d '{"prospects":[
        {"player_name":"Davis","team":"Louisville","games_played":57,"home_runs":34},
        {"player_name":"Rodriguez","team":"BCU","games_played":54,"at_bats":154,"hits":64,"walks":40}
      ]}'
```

- API : http://localhost:8000 (`/health`, `/predict`, `/rank`, docs auto sur `/docs`)
- Console MinIO : http://localhost:9001
- PostgreSQL : `localhost:5432`, base `scouting_db`

> ⚠️ Les identifiants sont lus depuis `.env` (ignoré par git). Les valeurs par
> défaut ne servent qu'au développement local ; ne commitez jamais de vrais
> secrets. Voir `.env.example`.

## Variables d'environnement

| Variable            | Défaut                   | Utilisé par            |
|---------------------|--------------------------|------------------------|
| `TARGET_URL`        | *(requis)*               | `main.py`              |
| `FILE_NAME`         | `raw_extract.jsonl`      | `main`/`loader`/`nlp`  |
| `S3_ENDPOINT`       | `http://minio:9000`      | tous les jobs S3       |
| `S3_BUCKET`         | `bronze-amateur-stats`   | `main`/`loader`        |
| `S3_MODEL_BUCKET`   | `ml-models`              | `train.py`/`api.py`    |
| `MODEL_NAME`        | `draft_fv_predictor_v1.joblib` | `train.py`/`api.py` |
| `MODEL_LOCAL_PATH`  | *(optionnel)*            | `api.py` (bypass S3)   |
| `PG_HOST`/`PG_PORT` | `postgres` / `5432`      | `loader`/`nlp`/`train` |

Les identifiants (`MINIO_ROOT_*`, `POSTGRES_*`, `S3_ACCESS_KEY`,
`S3_SECRET_KEY`) sont définis dans `.env` — voir `.env.example`.

## Tests & lint

Les tests couvrent la logique pure (parsing, features, validation, API avec
modèle injecté), sans dépendance à S3 ni PostgreSQL :

```bash
pip install -r requirements-dev.txt
ruff check .   # lint
pytest         # tests
```

La CI (`.github/workflows/ci.yml`) exécute, à chaque push / pull request :
le lint `ruff`, la suite `pytest`, et le build de l'image Docker.
