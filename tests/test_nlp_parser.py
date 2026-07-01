from nlp_parser import parse_scout_text

REPORT = """MLB AMATEUR SCOUTING REPORT
Player: Charlie Condon
Scout: Billy Beane
Date: 2024-05-10
Notes: Generational raw power. Struggles slightly with inside breaking balls.
Hit: 55
Power: 70
Run: 40
Arm: 55
Field: 50
Overall FV: 60"""


def test_names_do_not_leak_across_lines():
    # Régression : la regex avalait le saut de ligne et produisait
    # "Charlie Condon\nScout", cassant le JOIN avec les stats NCAA.
    report = parse_scout_text(REPORT)
    assert report.player_name == "Charlie Condon"
    assert report.scout_name == "Billy Beane"


def test_grades_are_parsed():
    report = parse_scout_text(REPORT)
    assert report.hit_grade == 55
    assert report.power_grade == 70
    assert report.run_grade == 40
    assert report.arm_grade == 55
    assert report.field_grade == 50
    assert report.overall_fv == 60


def test_alternate_grade_format():
    report = parse_scout_text("Player: Test\nScout: X\nHit Grade - 60\nOverall FV: 45")
    assert report.hit_grade == 60
    assert report.overall_fv == 45


def test_missing_grade_defaults_to_40():
    report = parse_scout_text("Player: Test\nScout: X\nOverall FV: 50")
    assert report.power_grade == 40  # absent → défaut
    assert report.overall_fv == 50


def test_missing_names_fall_back_to_unknown():
    report = parse_scout_text("Hit: 50\nOverall FV: 50")
    assert report.player_name == "Unknown Player"
    assert report.scout_name == "Unknown Scout"
