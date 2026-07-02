from report import (
    build_board,
    build_gems,
    format_gems_board,
    merge_records,
    render_html,
    scouts_by_key,
)


def test_merge_records_takes_max_per_field():
    # Le même joueur dans deux sources (HR-only puis OBP-only) doit fusionner
    # en un profil complet (sémantique GREATEST du warehouse).
    records = [
        {"player_name": "Dual", "team": "X", "games_played": 57,
         "at_bats": 0, "hits": 0, "home_runs": 34, "walks": 0, "strikeouts": 0},
        {"player_name": "Dual", "team": "X", "games_played": 57,
         "at_bats": 200, "hits": 75, "home_runs": 0, "walks": 35, "strikeouts": 30},
    ]
    merged = merge_records(records)
    assert len(merged) == 1
    m = merged[0]
    assert m["home_runs"] == 34   # gardé de la source HR
    assert m["at_bats"] == 200    # gardé de la source OBP
    assert m["walks"] == 35


def test_merge_records_distinct_keys_kept_separate():
    records = [
        {"player_name": "A", "team": "X", "home_runs": 10},
        {"player_name": "A", "team": "Y", "home_runs": 20},  # même nom, autre équipe
    ]
    assert len(merge_records(records)) == 2


def test_build_board_ranks_complete_profile_and_renders():
    records = [
        {"player_name": "Slugger", "team": "A", "games_played": 57, "home_runs": 34},
        {"player_name": "Complete", "team": "B", "games_played": 55,
         "at_bats": 200, "hits": 78, "home_runs": 20, "walks": 40, "strikeouts": 25},
    ]
    scored, board = build_board(records, top_n=10)
    assert len(scored) == 2
    assert "PROSPECT" in board
    # Le tableau contient bien les deux joueurs.
    assert "Slugger" in board and "Complete" in board


def test_render_html_produces_valid_document():
    records = [
        {"player_name": "Slugger", "team": "A", "games_played": 57, "home_runs": 34},
        {"player_name": "Complete", "team": "B", "games_played": 55,
         "at_bats": 200, "hits": 78, "home_runs": 20, "walks": 40, "strikeouts": 25},
    ]
    scored, _ = build_board(records, top_n=10)
    html = render_html(scored, top_n=10)
    assert html.startswith("<!doctype html>")
    assert "<table>" in html and "Slugger" in html and "Complete" in html
    # Sans rapports de scouts, pas de section inefficiences.
    assert "Inefficiences" not in html


_STATS = [
    {"player_name": "Gem", "team": "X", "games_played": 57,
     "at_bats": 200, "hits": 78, "home_runs": 34, "walks": 40, "strikeouts": 30},
    {"player_name": "NoScout", "team": "Z", "games_played": 57, "home_runs": 20},
]
_SCOUTS = [
    {"player_name": "Gem", "scout_name": "S", "hit_grade": 40, "power_grade": 40},
]


def test_scouts_by_key_matches_by_name_and_reuses_stats_team():
    mapping = scouts_by_key(_STATS, _SCOUTS)
    # Le rapport de scout ne porte pas l'équipe : la clé vient des stats.
    assert list(mapping) == [("Gem", "X")]
    assert mapping[("Gem", "X")]["hit_grade"] == 40


def test_build_gems_crosses_and_attaches_scout():
    scored, _ = build_board(_STATS, top_n=10)
    gems = build_gems(scored, _SCOUTS)
    assert len(gems) == 1  # NoScout exclu (pas de rapport)
    assert gems[0]["valuation"]["label"] == "UNDERVALUED"
    assert gems[0]["scout"]["scout_name"] == "S"


def test_format_gems_board_and_html_render_gems():
    scored, _ = build_board(_STATS, top_n=10)
    gems = build_gems(scored, _SCOUTS)
    text = format_gems_board(gems)
    assert "UNDERVALUED" in text and "Gem" in text
    html = render_html(scored, top_n=10, gems=gems)
    assert "Inefficiences" in html and "UNDERVALUED" in html
