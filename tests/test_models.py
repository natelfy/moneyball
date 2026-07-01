import pytest
from pydantic import ValidationError

from models import HitterStat


def test_strips_whitespace_on_name_and_team():
    stat = HitterStat(player_name="  Tague Davis  ", team="  Louisville ")
    assert stat.player_name == "Tague Davis"
    assert stat.team == "Louisville"


def test_defaults_are_zero():
    stat = HitterStat(player_name="X", team="Y")
    assert (stat.games_played, stat.at_bats, stat.hits) == (0, 0, 0)
    assert (stat.home_runs, stat.walks, stat.strikeouts) == (0, 0, 0)


def test_negative_stats_are_rejected():
    with pytest.raises(ValidationError):
        HitterStat(player_name="X", team="Y", home_runs=-1)
