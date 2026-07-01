from scraper import CCBLScraper

# Deux en-têtes réalistes : l'un utilise "K" pour les retraits au bâton,
# l'autre "SO", et "NAME" au lieu de "PLAYER" — les variantes que le mapping
# dynamique doit tolérer.
HTML_WITH_K = """
<table>
  <thead><tr>
    <th>PLAYER</th><th>TEAM</th><th>G</th><th>AB</th><th>H</th>
    <th>HR</th><th>BB</th><th>K</th>
  </tr></thead>
  <tbody>
    <tr><td>Tague Davis</td><td>Louisville</td><td>57</td><td>200</td>
        <td>70</td><td>34</td><td>25</td><td>60</td></tr>
  </tbody>
</table>
"""

HTML_WITH_SO_AND_NAME = """
<table>
  <thead><tr>
    <th>NAME</th><th>TEAM</th><th>G</th><th>AB</th><th>H</th>
    <th>HR</th><th>BB</th><th>SO</th>
  </tr></thead>
  <tbody>
    <tr><td> Daniel Jackson </td><td>Georgia</td><td>67</td><td>210</td>
        <td>80</td><td>32</td><td>18</td><td>45</td></tr>
  </tbody>
</table>
"""


def test_extract_stats_maps_k_column():
    players = CCBLScraper("http://example.com").extract_stats(HTML_WITH_K)
    assert len(players) == 1
    p = players[0]
    assert p.player_name == "Tague Davis"
    assert p.team == "Louisville"
    assert p.home_runs == 34
    assert p.strikeouts == 60  # la colonne "K" doit être lue


def test_extract_stats_maps_so_and_name_aliases():
    players = CCBLScraper("http://example.com").extract_stats(HTML_WITH_SO_AND_NAME)
    assert len(players) == 1
    p = players[0]
    # "NAME" doit être reconnu comme joueur, et espaces retirés
    assert p.player_name == "Daniel Jackson"
    # "SO" doit alimenter strikeouts (auparavant ignoré → 0)
    assert p.strikeouts == 45
    assert p.walks == 18


def test_extract_stats_returns_empty_without_table():
    assert CCBLScraper("http://example.com").extract_stats("<html>no table</html>") == []
