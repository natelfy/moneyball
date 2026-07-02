"""Convertit les exports de tableaux stats.ncaa.org au format JSONL du pipeline.

Accepte les trois formes d'export du site : bouton Excel (.xlsx), CSV, ou
copier-coller du tableau dans un fichier texte (tabulations). Le convertisseur :

- trouve la ligne d'en-têtes même si des lignes de titre la précèdent ;
- mappe les colonnes par alias (PLAYER/NAME, TEAM/SCHOOL, G/GP, AB, H, HR,
  BB, K/SO) et ignore les colonnes inutiles (Rank, Cl, BA, OBP…) ;
- remet les noms « Last, First » au format « First Last » (indispensable pour
  les jointures avec FanGraphs / l'API draft) ;
- retire un éventuel bilan « (45-12) » collé au nom d'équipe, sans toucher aux
  distinctions réelles comme « Miami (OH) » ;
- valide chaque ligne via le schéma Pydantic `HitterStat`.

Usage :
    python src/convert_ncaa.py export_ba.xlsx export_hr.csv --outdir data_ncaa/2024
"""
import argparse
import logging
import os
import re

import pandas as pd
from pydantic import ValidationError

from models import HitterStat

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ncaa-converter")

ALIASES = {
    "player_name": ("PLAYER", "NAME"),
    "team": ("TEAM", "SCHOOL", "INSTITUTION"),
    "games_played": ("G", "GP", "GAMES"),
    "at_bats": ("AB",),
    "hits": ("H", "HITS"),
    "home_runs": ("HR", "HOME RUNS"),
    "walks": ("BB", "WALKS", "BASE ON BALLS"),
    "strikeouts": ("K", "SO", "STRIKEOUTS"),
}

# Bilan sportif accolé à l'équipe, ex: "Louisville (45-12)". On ne retire QUE
# ce motif chiffré : "Miami (OH)" / "Miami (FL)" sont des équipes distinctes.
_RECORD_SUFFIX = re.compile(r"\s*\(\d+-\d+\)\s*$")


def normalize_name(name: str) -> str:
    """« Doe, John » → « John Doe » (format stats.ncaa.org → format pipeline)."""
    name = " ".join(name.split())
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{first.strip()} {last.strip()}"
    return name


def clean_team(team: str) -> str:
    return _RECORD_SUFFIX.sub("", " ".join(team.split()))


def _to_int(value: str) -> int:
    value = value.strip().replace(",", "")
    try:
        return int(float(value))
    except ValueError:
        return 0


def read_rows(path: str) -> list:
    """Lit un export (.xlsx, .csv ou texte tabulé) en lignes de chaînes."""
    if path.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(path, header=None, dtype=str)
    else:
        # sep=None + engine python : détecte virgule, point-virgule ou tab.
        df = pd.read_csv(path, header=None, dtype=str, sep=None,
                         engine="python", skip_blank_lines=True)
    return df.fillna("").astype(str).values.tolist()


def find_header(rows: list) -> tuple:
    """Repère la ligne d'en-têtes (les exports ont parfois des lignes de titre)."""
    for i, row in enumerate(rows):
        upper = [c.strip().upper() for c in row]
        has_player = any(a in upper for a in ALIASES["player_name"])
        has_team = any(a in upper for a in ALIASES["team"])
        if has_player and has_team:
            return i, upper
    raise ValueError(
        "Ligne d'en-têtes introuvable : il faut au moins une colonne joueur "
        f"({'/'.join(ALIASES['player_name'])}) et une colonne équipe "
        f"({'/'.join(ALIASES['team'])})."
    )


def convert_rows(rows: list) -> list[HitterStat]:
    """Convertit les lignes brutes en objets HitterStat validés."""
    header_idx, headers = find_header(rows)
    col = {}
    for field, aliases in ALIASES.items():
        for alias in aliases:
            if alias in headers:
                col[field] = headers.index(alias)
                break

    stats = []
    for row in rows[header_idx + 1:]:
        raw_name = row[col["player_name"]].strip()
        # Ignore lignes vides et en-têtes répétés en cours de tableau.
        if not raw_name or raw_name.upper() in ALIASES["player_name"]:
            continue
        try:
            stats.append(HitterStat(
                player_name=normalize_name(raw_name),
                team=clean_team(row[col["team"]]),
                games_played=_to_int(row[col["games_played"]]) if "games_played" in col else 0,
                at_bats=_to_int(row[col["at_bats"]]) if "at_bats" in col else 0,
                hits=_to_int(row[col["hits"]]) if "hits" in col else 0,
                home_runs=_to_int(row[col["home_runs"]]) if "home_runs" in col else 0,
                walks=_to_int(row[col["walks"]]) if "walks" in col else 0,
                strikeouts=_to_int(row[col["strikeouts"]]) if "strikeouts" in col else 0,
            ))
        except ValidationError as e:
            logger.warning(f"Ligne ignorée ({raw_name}) : {e}")
    return stats


def convert_file(path: str, outdir: str) -> str:
    """Convertit un export en JSONL. Retourne le chemin du fichier écrit."""
    stats = convert_rows(read_rows(path))
    if not stats:
        raise ValueError(f"{path} : aucune ligne exploitable.")

    stem = os.path.splitext(os.path.basename(path))[0]
    out_path = os.path.join(outdir, f"{stem}.jsonl")
    os.makedirs(outdir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        for stat in stats:
            fh.write(stat.model_dump_json() + "\n")
    logger.info(f"{path} → {out_path} ({len(stats)} joueurs)")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="Convertit des exports stats.ncaa.org (xlsx/csv/tsv) en JSONL"
    )
    parser.add_argument("files", nargs="+", help="Exports à convertir")
    parser.add_argument("--outdir", default="data_ncaa", help="Dossier de sortie")
    args = parser.parse_args()

    for path in args.files:
        convert_file(path, args.outdir)


if __name__ == "__main__":
    main()
