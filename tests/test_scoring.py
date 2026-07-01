from scoring import (
    BENCHMARKS,
    calibrate_benchmarks,
    grade_prospect,
    rank_prospects,
    to_scout_scale,
)


def test_to_scout_scale_rounds_and_clamps():
    assert to_scout_scale(57.3) == 55
    assert to_scout_scale(58.0) == 60
    assert to_scout_scale(-5) == 20
    assert to_scout_scale(200) == 80


def test_grade_prospect_complete_profile():
    # Joueur avec tous les outils renseignés -> complétude 100%.
    res = grade_prospect(games_played=55, at_bats=200, hits=75,
                         home_runs=15, walks=35, strikeouts=30)
    assert set(res["grades"]) == {"power", "on_base", "contact", "eye"}
    assert res["data_completeness"] == 1.0
    assert 20 <= res["overall_fv"] <= 80
    # Toutes les notes sur l'échelle 20-80, multiples de 5.
    for grade in res["grades"].values():
        assert 20 <= grade <= 80 and grade % 5 == 0


def test_grade_prospect_power_only_when_no_at_bats():
    # Cas "leader de HR" : AB=0 -> seule la puissance est gradable.
    res = grade_prospect(games_played=57, at_bats=0, home_runs=34)
    assert set(res["grades"]) == {"power"}
    assert res["data_completeness"] == 0.25
    assert res["overall_fv"] == res["grades"]["power"]  # overall = power seul


def test_grade_prospect_power_scales_with_hr_rate():
    low = grade_prospect(games_played=57, home_runs=10)["grades"]["power"]
    high = grade_prospect(games_played=57, home_runs=34)["grades"]["power"]
    assert high > low


def test_grade_prospect_no_data_defaults_low():
    res = grade_prospect()
    assert res["grades"] == {}
    assert res["overall_fv"] == 20


def test_calibrate_benchmarks_computes_percentiles():
    # Population avec de l'AB partout -> on_base/contact/eye calibrables.
    records = [
        {"games_played": 55, "at_bats": 150 + i, "hits": 40 + i,
         "home_runs": (i % 15) + 1, "walks": 10 + i, "strikeouts": 30}
        for i in range(20)
    ]
    bm = calibrate_benchmarks(records)
    for metric in ("power", "on_base", "contact", "eye"):
        p20, p50, p80 = bm[metric]
        assert p20 < p50 < p80  # segments strictement croissants


def test_calibrate_benchmarks_falls_back_when_too_few_samples():
    bm = calibrate_benchmarks([{"games_played": 55, "home_runs": 10}], min_samples=8)
    # Pas assez de données -> on garde les seuils par défaut.
    assert bm["power"] == BENCHMARKS["power"]
    assert bm["on_base"] == BENCHMARKS["on_base"]


def test_grade_prospect_respects_custom_benchmarks():
    stats = {"at_bats": 200, "hits": 60, "walks": 20, "home_runs": 0}
    # Benchmarks très exigeants -> contact plus faible que par défaut.
    strict = {**BENCHMARKS, "contact": (0.350, 0.420, 0.500)}
    default_grade = grade_prospect(**stats)["grades"]["contact"]
    strict_grade = grade_prospect(**stats, benchmarks=strict)["grades"]["contact"]
    assert strict_grade < default_grade


def test_rank_prospects_orders_by_overall_desc():
    recs = [
        {"player_name": "Slugger", "team": "A", "games_played": 57, "home_runs": 34},
        {"player_name": "Weak", "team": "B", "games_played": 57, "home_runs": 5},
        {"player_name": "OnBase", "team": "C", "games_played": 55,
         "at_bats": 190, "hits": 80, "walks": 40, "home_runs": 8},
    ]
    ranked = rank_prospects(recs)
    overalls = [r["scouting"]["overall"] for r in ranked]
    assert overalls == sorted(overalls, reverse=True)
    assert "scouting" in ranked[0]
