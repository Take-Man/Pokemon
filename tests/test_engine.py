"""計算エンジンのテスト。showdown_damage.json は Pokémon Showdown（champions mod）で出した16乱数の正解値。"""
import json
from pathlib import Path

import pytest

from engine.damage import Field, Options, Side, calc
from engine.data import dex, to_id
from engine.stats import Build, calc_stat, validate_sp

FIX = json.loads((Path(__file__).parent / "fixtures" / "showdown_damage.json").read_text(encoding="utf-8"))


def test_stat_formula():
    # ガブリアス A130 ようき 能力ポイント32 → 182、S102 ようき32 → 169、H108 SP2 → 185
    assert calc_stat(130, 32, "atk", "jolly") == 182
    assert calc_stat(102, 32, "spe", "jolly") == 169
    assert calc_stat(108, 2, "hp") == 185


def test_sp_validation():
    assert validate_sp({"atk": 32, "spe": 32, "hp": 2}) == []
    assert validate_sp({"atk": 33}) != []
    assert validate_sp({"atk": 32, "spe": 32, "hp": 32}) != []


def test_type_chart_size():
    assert len(dex().type_chart) == 18


def test_name_lookup():
    assert dex().pokemon["ガブリアス"]["id"] == "garchomp"
    assert dex().pokemon.search("がぶ")[0]["id"] == "garchomp"
    assert dex().moves["じしん"]["id"] == "earthquake"


@pytest.mark.parametrize("c", FIX, ids=[c["name"] for c in FIX])
def test_damage_matches_showdown(c):
    A, D = c["attacker"], c["defender"]
    a = Side(Build(A["species"], to_id(A["nature"]), A["sp"], A["ability"], A["item"] or None),
             boosts=c.get("atkBoosts", {}), status=A.get("status"))
    d = Side(Build(D["species"], to_id(D["nature"]), D["sp"], D["ability"], D["item"] or None),
             boosts=c.get("defBoosts", {}), reflect=D.get("reflect", False), light_screen=D.get("light_screen", False))
    r = calc(a, d, c["move"], Field(**c.get("field", {})), Options(crit=c.get("crit", False), hits=1))
    assert r.rolls == c["expected"]
