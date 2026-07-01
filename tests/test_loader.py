from loader import parse_records


def test_parse_records_maps_fields_in_order():
    line = (
        '{"player_name":"Tague Davis","team":"Louisville","games_played":57,'
        '"at_bats":200,"hits":70,"home_runs":34,"walks":25,"strikeouts":60}'
    )
    records = parse_records([line])
    assert records == [
        ("Tague Davis", "Louisville", 57, 200, 70, 34, 25, 60),
    ]


def test_parse_records_defaults_missing_numeric_to_zero():
    records = parse_records(['{"player_name":"X","team":"Y"}'])
    assert records == [("X", "Y", 0, 0, 0, 0, 0, 0)]


def test_parse_records_skips_blank_lines():
    lines = ['{"player_name":"X","team":"Y"}', "", "   ", "\n"]
    assert len(parse_records(lines)) == 1
