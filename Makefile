# Orchestration du pipeline Moneyball.
# Cibles locales (sans infra) : test, lint, board, board-html, evaluate.
# Cibles Docker (infra requise) : infra, ingest, load, nlp, train, api.

.DEFAULT_GOAL := help
PY = PYTHONPATH=src python3

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

test: ## Lance la suite de tests
	$(PY) -m pytest

lint: ## Lint ruff
	python3 -m ruff check .

board: ## Tableau de scouting sur les données locales (avec croisement scouts démo)
	$(PY) src/report.py --source local --dir local_data --top 15 \
		--scouts local_data/scout_grades_demo.jsonl

board-html: ## Board HTML autonome -> board.html
	$(PY) src/report.py --source local --dir local_data --top 25 \
		--scouts local_data/scout_grades_demo.jsonl --html board.html

evaluate: ## Évalue le modèle (DATA=fichier.jsonl labellisé, sinon warehouse)
	$(PY) src/evaluate.py $(if $(DATA),--data $(DATA))

convert: ## Convertit des exports stats.ncaa.org en JSONL (FILES="a.xlsx b.csv" OUTDIR=data_ncaa)
	$(PY) src/convert_ncaa.py $(FILES) --outdir $(or $(OUTDIR),data_ncaa)

infra: ## Démarre MinIO + PostgreSQL
	docker compose up -d minio postgres

ingest: ## Scrape + upload Bronze (TARGET_URL=... FILE_NAME=...)
	docker compose run --rm worker python src/main.py

load: ## Bronze -> Silver (FILE_NAME=...)
	docker compose run --rm worker python src/loader.py

nlp: ## Parse un rapport scout PDF (FILE_NAME=... S3_BUCKET=bronze-scout-reports)
	docker compose run --rm worker python src/nlp_parser.py

train: ## Entraîne le modèle et le pousse au Model Registry
	docker compose run --rm worker python src/train.py

api: ## Démarre l'API d'inférence (port 8000)
	docker compose up -d api

clean: ## Supprime caches et artefacts locaux
	rm -rf .pytest_cache .ruff_cache board.html
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

.PHONY: help test lint board board-html evaluate convert infra ingest load nlp train api clean
