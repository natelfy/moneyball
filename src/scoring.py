"""Moteur de scoring de prospects : convertit des statistiques offensives en
grades 20-80 façon scout, puis en une note globale (« Future Value » data-driven).

Philosophie *moneyball* : on privilégie la capacité à se mettre en base (OBP)
et la puissance efficace plutôt que la moyenne au bâton brute. Chaque outil est
gradé **uniquement si la donnée existe** (les sources amateurs sont souvent
partielles : leaders de HR sans AB, leaders d'OBP sans HR), et la note globale
est une moyenne pondérée renormalisée sur les outils réellement disponibles.
"""
import numpy as np

from features import compute_sabermetrics

# Ancrages 20/50/80 par métrique (interpolation linéaire par morceaux).
# Calibrés pour du hitting amateur (NCAA / summer leagues).
BENCHMARKS = {
    "power":   (0.10, 0.28, 0.55),   # HR par match (robuste même sans AB)
    "on_base": (0.320, 0.390, 0.470),  # OBP
    "contact": (0.270, 0.330, 0.400),  # moyenne au bâton
    "eye":     (0.060, 0.110, 0.180),  # taux de buts-sur-balles (BB / PA)
}

# Poids moneyball de la note globale (renormalisés sur les outils présents).
OVERALL_WEIGHTS = {
    "on_base": 0.35,
    "power": 0.30,
    "eye": 0.20,
    "contact": 0.15,
}


def _piecewise_grade(value: float, p20: float, p50: float, p80: float) -> float:
    """Mappe une valeur vers l'échelle 20-80 via deux segments linéaires."""
    if value <= p50:
        grade = 20 + (value - p20) * (30.0 / (p50 - p20))
    else:
        grade = 50 + (value - p50) * (30.0 / (p80 - p50))
    return max(20.0, min(80.0, grade))


def to_scout_scale(value: float) -> int:
    """Arrondit au multiple de 5 le plus proche, borné à 20-80."""
    clamped = min(80.0, max(20.0, value))
    return int(round(clamped / 5.0) * 5)


def grade_prospect(
    games_played: int = 0,
    at_bats: int = 0,
    hits: int = 0,
    home_runs: int = 0,
    walks: int = 0,
    strikeouts: int = 0,
    benchmarks: dict = BENCHMARKS,
    **_ignored: object,
) -> dict[str, object]:
    """Produit les grades 20-80 par outil + une note globale.

    `benchmarks` : ancrages 20/50/80 par métrique. Par défaut les valeurs
    calibrées à la main ; passer le résultat de `calibrate_benchmarks()` pour
    des seuils ajustés à une population réelle.

    Retourne un dict avec les grades disponibles, la note `overall` (float,
    pour le tri), `overall_fv` (arrondie à l'échelle 20-80) et la complétude
    des données (fraction d'outils réellement gradés).
    """
    sm = compute_sabermetrics(
        at_bats=at_bats, hits=hits, home_runs=home_runs,
        walks=walks, strikeouts=strikeouts,
    )

    grades: dict[str, int] = {}

    # Puissance : HR par match. On exige une évidence positive (home_runs > 0) :
    # dans les sources amateurs, HR=0 signifie presque toujours « stat absente »
    # (ex: un fichier de leaders d'OBP ne renseigne pas les HR), pas « aucune
    # puissance ». On laisse donc l'outil non gradé plutôt que d'attribuer un 20
    # trompeur.
    if games_played > 0 and home_runs > 0:
        hr_per_game = home_runs / games_played
        grades["power"] = to_scout_scale(_piecewise_grade(hr_per_game, *benchmarks["power"]))

    # On-base / contact / discipline nécessitent des passages au bâton.
    if at_bats > 0:
        grades["on_base"] = to_scout_scale(_piecewise_grade(sm["obp"], *benchmarks["on_base"]))
        grades["contact"] = to_scout_scale(_piecewise_grade(sm["batting_avg"], *benchmarks["contact"]))
        grades["eye"] = to_scout_scale(_piecewise_grade(sm["bb_rate"], *benchmarks["eye"]))

    # Note globale : moyenne pondérée renormalisée sur les outils présents.
    if grades:
        total_weight = sum(OVERALL_WEIGHTS[tool] for tool in grades)
        overall = sum(grades[tool] * OVERALL_WEIGHTS[tool] for tool in grades) / total_weight
    else:
        overall = 20.0

    return {
        "grades": grades,
        "overall": round(overall, 2),
        "overall_fv": to_scout_scale(overall),
        "graded_tools": sorted(grades),
        "data_completeness": round(len(grades) / len(OVERALL_WEIGHTS), 2),
    }


def rank_prospects(records):
    """Score une liste d'enregistrements et les trie par note globale décroissante.

    Chaque enregistrement (dict) doit contenir au moins `player_name`/`team` et
    les comptages. Retourne une nouvelle liste enrichie de la clé `scouting`.
    """
    scored = []
    for rec in records:
        result = grade_prospect(**rec)
        scored.append({**rec, "scouting": result})
    scored.sort(key=lambda r: r["scouting"]["overall"], reverse=True)
    return scored


def _metric_values(records):
    """Extrait, par métrique, les valeurs observées dans une population."""
    values = {"power": [], "on_base": [], "contact": [], "eye": []}
    for rec in records:
        gp = rec.get("games_played", 0) or 0
        ab = rec.get("at_bats", 0) or 0
        hr = rec.get("home_runs", 0) or 0
        sm = compute_sabermetrics(
            at_bats=ab, hits=rec.get("hits", 0) or 0, home_runs=hr,
            walks=rec.get("walks", 0) or 0, strikeouts=rec.get("strikeouts", 0) or 0,
        )
        if gp > 0 and hr > 0:
            values["power"].append(hr / gp)
        if ab > 0:
            values["on_base"].append(sm["obp"])
            values["contact"].append(sm["batting_avg"])
            values["eye"].append(sm["bb_rate"])
    return values


def calibrate_benchmarks(records, percentiles=(20, 50, 80), min_samples=8):
    """Calcule des ancrages 20/50/80 à partir des percentiles d'une population.

    Rend les grades relatifs au vivier réel plutôt qu'à des seuils fixes. Pour
    chaque métrique, on retombe sur `BENCHMARKS` si l'échantillon est trop
    petit ou dégénéré (percentiles non strictement croissants).

    ⚠️ À calibrer sur un échantillon *représentatif* : sur un fichier de
    « leaders » (haut de distribution), les seuils seront biaisés vers le haut.
    """
    observed = _metric_values(records)
    calibrated = {}
    for metric, default in BENCHMARKS.items():
        vals = observed[metric]
        if len(vals) < min_samples:
            calibrated[metric] = default
            continue
        p20, p50, p80 = (float(np.percentile(vals, p)) for p in percentiles)
        # Garantit des segments strictement croissants (sinon division par 0).
        calibrated[metric] = (p20, p50, p80) if p20 < p50 < p80 else default
    return calibrated
