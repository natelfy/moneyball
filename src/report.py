"""Génère le tableau de scouting : fusionne les sources, score chaque prospect
et affiche le classement.

Utilisable sur le Data Warehouse (PostgreSQL) en production, ou directement sur
les fichiers JSONL locaux pour une démonstration hors infrastructure.
"""
import argparse
import glob
import json
import logging
import os

from scoring import rank_prospects

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scouting-report")

_NUMERIC_FIELDS = ("games_played", "at_bats", "hits", "home_runs", "walks", "strikeouts")


def merge_records(records):
    """Fusionne les enregistrements par (joueur, équipe) en prenant le max de
    chaque compteur — réplique la sémantique GREATEST de l'UPSERT warehouse,
    afin qu'un joueur présent dans plusieurs sources (HR + OBP) obtienne un
    profil complet.
    """
    merged = {}
    for rec in records:
        key = (rec.get("player_name"), rec.get("team"))
        if key not in merged:
            merged[key] = {"player_name": key[0], "team": key[1],
                           **{f: 0 for f in _NUMERIC_FIELDS}}
        for f in _NUMERIC_FIELDS:
            merged[key][f] = max(merged[key][f], int(rec.get(f, 0) or 0))
    return list(merged.values())


def load_local(data_dir):
    """Charge tous les fichiers *.jsonl d'un répertoire."""
    records = []
    for path in sorted(glob.glob(os.path.join(data_dir, "*.jsonl"))):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def load_from_postgres():
    """Charge les stats depuis le Data Warehouse."""
    import psycopg2  # import local : non requis en mode démo local
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST", "postgres"),
        port=os.getenv("PG_PORT", "5432"),
        user=os.getenv("PG_USER", "mlops"),
        password=os.getenv("PG_PASSWORD", "moneyball_password"),
        dbname=os.getenv("PG_DB", "scouting_db"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT player_name, team, games_played, at_bats, hits, "
                "home_runs, walks, strikeouts FROM ncaa_hitting_stats"
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        conn.close()


def format_board(scored, top_n=15):
    """Rend le classement sous forme de tableau texte."""
    lines = [
        "═" * 78,
        f"{'#':>2}  {'PROSPECT':<22} {'ÉQUIPE':<16} {'FV':>3}  "
        f"{'HIT':>3} {'PWR':>3} {'EYE':>3} {'OBP':>3}  {'DATA':>4}",
        "─" * 78,
    ]
    for i, rec in enumerate(scored[:top_n], 1):
        s = rec["scouting"]
        g = s["grades"]
        lines.append(
            f"{i:>2}  {rec['player_name']:<22.22} {rec['team']:<16.16} "
            f"{s['overall_fv']:>3}  "
            f"{g.get('contact', '·'):>3} {g.get('power', '·'):>3} "
            f"{g.get('eye', '·'):>3} {g.get('on_base', '·'):>3}  "
            f"{int(s['data_completeness'] * 100):>3}%"
        )
    lines.append("═" * 78)
    return "\n".join(lines)


def build_board(records, top_n=15):
    """Pipeline complet : fusion → scoring → classement → rendu texte."""
    merged = merge_records(records)
    scored = rank_prospects(merged)
    return scored, format_board(scored, top_n)


def main():
    parser = argparse.ArgumentParser(description="Tableau de scouting Moneyball")
    parser.add_argument("--source", choices=["local", "postgres"], default="local")
    parser.add_argument("--dir", default="local_data", help="Répertoire JSONL (mode local)")
    parser.add_argument("--top", type=int, default=15, help="Nombre de prospects affichés")
    args = parser.parse_args()

    records = load_local(args.dir) if args.source == "local" else load_from_postgres()
    logger.info(f"{len(records)} lignes chargées depuis {args.source}.")

    scored, board = build_board(records, args.top)
    logger.info(f"{len(scored)} prospects distincts après fusion des sources.")

    print("\nCLASSEMENT GLOBAL (tous prospects)")
    print(board)

    # Profils complets : la vraie valeur moneyball — joueurs gradés sur tous
    # les outils (puissance + on-base + discipline + contact), donc les plus
    # fiables et les plus recherchés.
    complete = [r for r in scored if r["scouting"]["data_completeness"] == 1.0]
    print(f"\nPROFILS COMPLETS / DUAL-THREAT ({len(complete)} joueurs)")
    print(format_board(complete, args.top))


if __name__ == "__main__":
    main()
