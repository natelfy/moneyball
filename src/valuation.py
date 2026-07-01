"""Moteur de sous-évaluation : le cœur de l'approche *moneyball*.

Compare le grade **statistique** d'un joueur (ce que disent les chiffres, via
`scoring.py`) au grade **subjectif du scout** (via les rapports parsés). Un
écart positif marqué signale un joueur dont la production dépasse la réputation
— la « pépite » que le marché sous-évalue.

Nuance assumée : le grade statistique ne couvre que l'offensive (contact,
puissance, on-base). On compare donc outil à outil (bat vs bat), pas la Future
Value globale du scout qui inclut aussi la défense/course.
"""
from scoring import grade_prospect

# Seuil (en points d'échelle 20-80) au-delà duquel on parle d'inefficience.
# ~1.5 cran de 5 points : suffisamment net pour être actionnable.
INEFFICIENCY_THRESHOLD = 7.5


def _stats_hit_grade(grades: dict) -> int | None:
    """Note « hit tool » statistique = moyenne des grades on-base et contact."""
    present = [grades[k] for k in ("on_base", "contact") if k in grades]
    return round(sum(present) / len(present)) if present else None


def compare_to_scout(stats: dict, scout: dict) -> dict:
    """Compare les grades statistiques d'un joueur aux grades d'un scout.

    `stats` : comptages bruts. `scout` : dict pouvant contenir `hit_grade`,
    `power_grade`. Retourne l'écart moyen (positif = sous-évalué) et un label.
    """
    stat_grades = grade_prospect(**stats)["grades"]
    stats_hit = _stats_hit_grade(stat_grades)
    stats_power = stat_grades.get("power")

    components: dict[str, int] = {}
    if stats_hit is not None and scout.get("hit_grade") is not None:
        components["hit"] = stats_hit - scout["hit_grade"]
    if stats_power is not None and scout.get("power_grade") is not None:
        components["power"] = stats_power - scout["power_grade"]

    if not components:
        return {"gap": None, "label": "UNKNOWN", "components": {},
                "stats_hit": stats_hit, "stats_power": stats_power}

    gap = round(sum(components.values()) / len(components), 1)
    if gap >= INEFFICIENCY_THRESHOLD:
        label = "UNDERVALUED"
    elif gap <= -INEFFICIENCY_THRESHOLD:
        label = "OVERVALUED"
    else:
        label = "FAIR"

    return {"gap": gap, "label": label, "components": components,
            "stats_hit": stats_hit, "stats_power": stats_power}


def find_market_inefficiencies(stat_records, scouts_by_key):
    """Croise stats et rapports de scouts, classe par sous-évaluation décroissante.

    `stat_records` : liste de dicts de comptages (avec player_name/team).
    `scouts_by_key` : dict {(player_name, team): scout_dict}. Seuls les joueurs
    disposant d'un rapport de scout comparable sont retournés.
    """
    results = []
    for rec in stat_records:
        key = (rec.get("player_name"), rec.get("team"))
        scout = scouts_by_key.get(key)
        if not scout:
            continue
        valuation = compare_to_scout(rec, scout)
        if valuation["gap"] is None:
            continue
        results.append({**rec, "valuation": valuation})

    results.sort(key=lambda r: r["valuation"]["gap"], reverse=True)
    return results
