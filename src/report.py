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
from valuation import find_market_inefficiencies

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


def _query_postgres(sql):
    """Exécute une requête sur le Data Warehouse, retourne des dicts."""
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
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
    finally:
        conn.close()


def load_from_postgres():
    """Charge les stats depuis le Data Warehouse."""
    return _query_postgres(
        "SELECT player_name, team, games_played, at_bats, hits, "
        "home_runs, walks, strikeouts FROM ncaa_hitting_stats"
    )


def load_scouts_postgres():
    """Charge les grades de scouts depuis la table scout_grades."""
    return _query_postgres(
        "SELECT player_name, scout_name, hit_grade, power_grade FROM scout_grades"
    )


def load_scouts_local(path):
    """Charge des grades de scouts depuis un fichier JSONL local."""
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def scouts_by_key(stat_records, scout_records):
    """Indexe les rapports de scouts par la clé (joueur, équipe) des stats.

    Les rapports de scouts ne portent pas l'équipe : on matche par nom de
    joueur, puis on reprend la clé complète des stats pour le croisement
    attendu par `find_market_inefficiencies`.
    """
    by_name = {s["player_name"]: s for s in scout_records}
    return {
        (rec["player_name"], rec["team"]): by_name[rec["player_name"]]
        for rec in stat_records
        if rec["player_name"] in by_name
    }


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


def format_gems_board(inefficiencies, top_n=10):
    """Rend le croisement stats × scouts (écart = production - réputation)."""
    lines = [
        "═" * 78,
        f"{'#':>2}  {'PROSPECT':<22} {'ÉQUIPE':<16} {'ÉCART':>6}  "
        f"{'STAT/SCOUT (HIT)':>16}  {'STAT/SCOUT (PWR)':>16}",
        "─" * 78,
    ]
    for i, rec in enumerate(inefficiencies[:top_n], 1):
        v = rec["valuation"]
        scout = rec.get("scout", {})
        hit = (f"{v['stats_hit']}/{scout.get('hit_grade', '·')}"
               if v["stats_hit"] is not None else "·")
        pwr = (f"{v['stats_power']}/{scout.get('power_grade', '·')}"
               if v["stats_power"] is not None else "·")
        gap = f"{v['gap']:+.1f}"
        lines.append(
            f"{i:>2}  {rec['player_name']:<22.22} {rec['team']:<16.16} "
            f"{gap:>6}  {hit:>16}  {pwr:>16}  {v['label']}"
        )
    lines.append("═" * 78)
    return "\n".join(lines)


def build_gems(scored, scout_records):
    """Croise le board scoré avec les rapports de scouts → inefficiences triées.

    Attache aussi le rapport de scout à chaque résultat pour l'affichage."""
    mapping = scouts_by_key(scored, scout_records)
    gems = find_market_inefficiencies(scored, mapping)
    for rec in gems:
        rec["scout"] = mapping[(rec["player_name"], rec["team"])]
    return gems


def _html_rows(scored, top_n):
    tools = [("contact", "HIT"), ("power", "PWR"), ("eye", "EYE"), ("on_base", "OBP")]
    rows = []
    for i, rec in enumerate(scored[:top_n], 1):
        s = rec["scouting"]
        cells = "".join(
            f'<td class="g">{s["grades"].get(key, "·")}</td>' for key, _ in tools
        )
        rows.append(
            f'<tr><td class="r">{i}</td><td class="name">{rec["player_name"]}</td>'
            f'<td>{rec["team"]}</td><td class="fv">{s["overall_fv"]}</td>{cells}'
            f'<td class="d">{int(s["data_completeness"] * 100)}%</td></tr>'
        )
    return "\n".join(rows)


def _html_gems_rows(gems, top_n):
    rows = []
    for i, rec in enumerate(gems[:top_n], 1):
        v = rec["valuation"]
        scout = rec.get("scout", {})
        hit = (f'{v["stats_hit"]} / {scout.get("hit_grade", "·")}'
               if v["stats_hit"] is not None else "·")
        pwr = (f'{v["stats_power"]} / {scout.get("power_grade", "·")}'
               if v["stats_power"] is not None else "·")
        css = v["label"].lower()
        rows.append(
            f'<tr><td class="r">{i}</td><td class="name">{rec["player_name"]}</td>'
            f'<td>{rec["team"]}</td><td class="gap">{v["gap"]:+.1f}</td>'
            f'<td>{hit}</td><td>{pwr}</td>'
            f'<td><span class="tag {css}">{v["label"]}</span></td></tr>'
        )
    return "\n".join(rows)


def render_html(scored, top_n=25, title="Moneyball — Tableau de scouting", gems=None):
    """Rend un board HTML autonome (classement global + profils complets,
    et inefficiences de marché si des rapports de scouts sont fournis)."""
    header = (
        "<tr><th>#</th><th>Prospect</th><th>Équipe</th><th>FV</th>"
        "<th>HIT</th><th>PWR</th><th>EYE</th><th>OBP</th><th>Data</th></tr>"
    )
    complete = [r for r in scored if r["scouting"]["data_completeness"] == 1.0]
    gems_section = ""
    if gems:
        gems_header = (
            "<tr><th>#</th><th>Prospect</th><th>Équipe</th><th>Écart</th>"
            "<th>Stat / Scout (hit)</th><th>Stat / Scout (pwr)</th><th>Verdict</th></tr>"
        )
        gems_section = f"""
<h2>Inefficiences de marché — production vs réputation ({len(gems)} joueurs croisés)</h2>
<p class="note">Écart positif = les stats disent plus que le scout (pépite potentielle).</p>
<table>{gems_header}
{_html_gems_rows(gems, top_n)}
</table>"""
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><title>{title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#0f1117; color:#e6e6e6; margin:2rem; }}
  h1 {{ font-size:1.4rem; }} h2 {{ font-size:1.05rem; color:#9ecbff; margin-top:2rem; }}
  table {{ border-collapse:collapse; width:100%; margin-top:.5rem; font-size:.9rem; }}
  th, td {{ padding:.35rem .6rem; text-align:center; border-bottom:1px solid #262b36; }}
  th {{ color:#8a93a5; text-transform:uppercase; font-size:.72rem; letter-spacing:.04em; }}
  td.name {{ text-align:left; font-weight:600; }} td:nth-child(3) {{ text-align:left; color:#aab; }}
  td.fv {{ font-weight:700; color:#7ee787; }} td.g {{ color:#d8dee9; }}
  td.r {{ color:#6b7280; }} td.d {{ color:#8a93a5; }} td.gap {{ font-weight:700; }}
  tr:hover td {{ background:#161a22; }}
  .note {{ color:#8a93a5; font-size:.82rem; margin-top:.4rem; }}
  .tag {{ padding:.1rem .5rem; border-radius:.6rem; font-size:.72rem; font-weight:700; }}
  .tag.undervalued {{ background:#123822; color:#7ee787; }}
  .tag.overvalued {{ background:#3d1a1a; color:#ff9e9e; }}
  .tag.fair {{ background:#22262f; color:#aab; }}
</style></head><body>
<h1>⚾ {title}</h1>
<p class="note">Grades sur l'échelle scouting 20-80. « · » = outil non mesuré (donnée absente).</p>
<h2>Classement global ({len(scored)} prospects)</h2>
<table>{header}
{_html_rows(scored, top_n)}
</table>
<h2>Profils complets / dual-threat ({len(complete)} joueurs)</h2>
<table>{header}
{_html_rows(complete, top_n)}
</table>{gems_section}
</body></html>"""


def main():
    parser = argparse.ArgumentParser(description="Tableau de scouting Moneyball")
    parser.add_argument("--source", choices=["local", "postgres"], default="local")
    parser.add_argument("--dir", default="local_data", help="Répertoire JSONL (mode local)")
    parser.add_argument("--top", type=int, default=15, help="Nombre de prospects affichés")
    parser.add_argument("--html", metavar="PATH", help="Écrit aussi le board en HTML")
    parser.add_argument("--scouts", metavar="PATH",
                        help="JSONL de grades scouts (mode local) ; en mode "
                             "postgres la table scout_grades est lue d'office")
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

    # Croisement stats × scouts : où la production contredit la réputation.
    scout_records = []
    if args.scouts:
        scout_records = load_scouts_local(args.scouts)
    elif args.source == "postgres":
        scout_records = load_scouts_postgres()

    gems = build_gems(scored, scout_records) if scout_records else []
    if gems:
        print(f"\nINEFFICIENCES DE MARCHÉ — production vs réputation ({len(gems)} joueurs croisés)")
        print(format_gems_board(gems, args.top))
    elif scout_records:
        logger.info("Aucun joueur croisable entre stats et rapports de scouts.")

    if args.html:
        with open(args.html, "w", encoding="utf-8") as fh:
            fh.write(render_html(scored, top_n=max(args.top, 25), gems=gems))
        logger.info(f"Board HTML écrit dans {args.html}")


if __name__ == "__main__":
    main()
