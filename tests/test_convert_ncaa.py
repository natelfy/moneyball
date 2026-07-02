import pandas as pd
import pytest

from convert_ncaa import (
    clean_team,
    convert_file,
    convert_rows,
    normalize_name,
    read_rows,
)

CSV_CONTENT = """Rank,Player,Team,Cl,G,AB,H,BA
1,"Rodriguez, Michael",Bethune-Cookman (34-21),Jr,54,154,64,.416
2,"Mally, Tanner",Western Mich.,Sr,50,195,87,.446
"""

TSV_CONTENT = "Rank\tName\tTeam\tG\tHR\n1\tDavis, Tague\tLouisville\t57\t34\n"


def test_normalize_name_flips_last_first():
    assert normalize_name("Rodriguez, Michael") == "Michael Rodriguez"
    assert normalize_name("Doe Jr., John") == "John Doe Jr."
    assert normalize_name("John Doe") == "John Doe"  # déjà au bon format


def test_clean_team_strips_record_but_keeps_state():
    assert clean_team("Louisville (45-12)") == "Louisville"
    # (OH)/(FL) distinguent de vraies équipes : à préserver absolument.
    assert clean_team("Miami (OH)") == "Miami (OH)"


def test_convert_csv_export(tmp_path):
    p = tmp_path / "ba.csv"
    p.write_text(CSV_CONTENT, encoding="utf-8")
    out = convert_file(str(p), str(tmp_path))
    lines = [line for line in open(out, encoding="utf-8")]
    assert len(lines) == 2
    assert '"player_name":"Michael Rodriguez"' in lines[0]
    assert '"team":"Bethune-Cookman"' in lines[0]
    assert '"at_bats":154' in lines[0]


def test_convert_pasted_tsv(tmp_path):
    p = tmp_path / "hr.txt"
    p.write_text(TSV_CONTENT, encoding="utf-8")
    stats = convert_rows(read_rows(str(p)))
    assert len(stats) == 1
    assert stats[0].player_name == "Tague Davis"
    assert stats[0].home_runs == 34
    assert stats[0].at_bats == 0  # colonne absente -> 0


def test_convert_xlsx_with_title_row(tmp_path):
    p = tmp_path / "walks.xlsx"
    df = pd.DataFrame([
        ["2024 NCAA Division I — Base on Balls", "", "", ""],   # ligne de titre
        ["Player", "Team", "G", "BB"],
        ["Katz, Chris", "Mercer", "55", "48"],
    ])
    df.to_excel(p, index=False, header=False)
    stats = convert_rows(read_rows(str(p)))
    assert len(stats) == 1
    assert stats[0].player_name == "Chris Katz"
    assert stats[0].walks == 48


def test_missing_header_raises(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="en-têtes introuvable"):
        convert_rows(read_rows(str(p)))
