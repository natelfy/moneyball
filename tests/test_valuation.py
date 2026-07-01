from valuation import compare_to_scout, find_market_inefficiencies

# Profil : grosse production offensive (34 HR/57 G, OBP élevée).
STRONG_STATS = {
    "player_name": "Gem", "team": "X", "games_played": 57,
    "at_bats": 200, "hits": 78, "home_runs": 34, "walks": 40, "strikeouts": 30,
}


def test_undervalued_when_stats_beat_scout():
    # Le scout sous-note largement (hit 40, power 40) vs des stats élites.
    val = compare_to_scout(STRONG_STATS, {"hit_grade": 40, "power_grade": 40})
    assert val["gap"] > 0
    assert val["label"] == "UNDERVALUED"
    assert set(val["components"]) == {"hit", "power"}


def test_overvalued_when_scout_beats_stats():
    weak_stats = {"games_played": 57, "at_bats": 200, "hits": 45,
                  "home_runs": 3, "walks": 8, "strikeouts": 70}
    val = compare_to_scout(weak_stats, {"hit_grade": 70, "power_grade": 70})
    assert val["gap"] < 0
    assert val["label"] == "OVERVALUED"


def test_fair_when_close():
    val = compare_to_scout(STRONG_STATS, {"hit_grade": 78, "power_grade": 78})
    assert val["label"] == "FAIR"


def test_unknown_when_no_comparable_tool():
    # Aucune donnée offensive comparable -> pas de composant.
    val = compare_to_scout({"games_played": 0}, {"hit_grade": 50, "power_grade": 50})
    assert val["gap"] is None
    assert val["label"] == "UNKNOWN"


def test_find_market_inefficiencies_ranks_by_gap():
    stats = [
        {"player_name": "Gem", "team": "X", "games_played": 57, "at_bats": 200,
         "hits": 78, "home_runs": 34, "walks": 40, "strikeouts": 30},
        {"player_name": "Fair", "team": "Y", "games_played": 57, "at_bats": 200,
         "hits": 60, "home_runs": 12, "walks": 20, "strikeouts": 40},
        {"player_name": "NoScout", "team": "Z", "games_played": 57, "home_runs": 20},
    ]
    scouts = {
        ("Gem", "X"): {"hit_grade": 40, "power_grade": 40},
        ("Fair", "Y"): {"hit_grade": 55, "power_grade": 55},
    }
    ranked = find_market_inefficiencies(stats, scouts)
    assert [r["player_name"] for r in ranked] == ["Gem", "Fair"]  # NoScout exclu
    assert ranked[0]["valuation"]["gap"] >= ranked[1]["valuation"]["gap"]
