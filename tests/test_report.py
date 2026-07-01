from report import build_board, merge_records, render_html


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
