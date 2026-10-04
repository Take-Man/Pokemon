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
    # 正解値は1発目（おやこあいの2発目はShowdown側で測っていない）
    assert sorted(r.hit_rolls[0] if r.hit_rolls else r.rolls) == c["expected"]


# ---- Showdown との突き合わせ（tools/verify_with_showdown.js）では測れない部分 -----------------

def _side(species, nature=None, sp=None, ability=None, item=None, **kw):
    return Side(Build(species, nature, sp or {}, ability, item), **kw)


def test_multihit_rolls_are_independent():
    # 2発の連続技: 確定数は 16×16 の組み合わせで出す（同じ乱数どうしの合計だけではない）
    a = _side("kangaskhan", "jolly", {"atk": 32}, "Scrappy")
    d = _side("garchomp", "jolly", {"hp": 2}, "Rough Skin")
    r = calc(a, d, "doublehit")
    one = r.hit_rolls[0]
    assert r.hits == 2 and r.min == 2 * one[0] and r.max == 2 * one[-1]
    totals = r.outcomes()
    assert one[0] + one[-1] in totals and abs(sum(totals.values()) - 1) < 1e-9
    single = calc(a, d, "doublehit", opt=Options(hits=1))
    assert r.ko_chance(1) == 0 or r.ko_chance(1) >= single.ko_chance(2) - 1e-9


def test_parental_bond_second_hit_quarter():
    a = _side("kangaskhanmega", "adamant", {"atk": 32}, "Parental Bond")
    d = _side("hippowdon", "impish", {"hp": 32, "def": 32}, "Sand Stream")
    r = calc(a, d, "doubleedge")
    first, second = r.hit_rolls
    assert all(s < f for f, s in zip(first, second)) and r.max == first[-1] + second[-1]


def test_merciless_crits_poisoned_target():
    a = _side("toxapex", "bold", {}, "Merciless")
    plain = calc(a, _side("garchomp"), "liquidation")
    psn = calc(a, _side("garchomp", status="psn"), "liquidation")
    assert psn.max > plain.max and any("ひとでなし" in n for n in psn.notes)


def test_cloud_nine_cancels_weather():
    a = _side("charizard", "modest", {"spa": 32}, "Blaze")
    sun = calc(a, _side("altaria", ability="Natural Cure"), "flamethrower", Field(weather="sun"))
    c9 = calc(a, _side("altaria", ability="Cloud Nine"), "flamethrower", Field(weather="sun"))
    none = calc(a, _side("altaria", ability="Natural Cure"), "flamethrower")
    assert c9.rolls == none.rolls and sun.max > c9.max


def test_battle_speed_modifiers():
    from engine.damage import battle_speed
    base = _side("jolteon", "timid", {"spe": 32}).build.stats()["spe"]
    assert battle_speed(_side("jolteon", "timid", {"spe": 32}, "Volt Absorb", status="par")) == base // 2
    # はやあし: 状態異常で1.5倍、まひの半減なし
    assert battle_speed(_side("jolteon", "timid", {"spe": 32}, "Quick Feet", status="par")) == base * 3 // 2
    assert battle_speed(_side("jolteon", "timid", {"spe": 32}, "Volt Absorb", item="Iron Ball")) == base // 2
    swim = _side("swampert", "jolly", {"spe": 32}, "Swift Swim")
    rain = Field(weather="rain")
    assert battle_speed(swim, rain) == 2 * battle_speed(swim)
    assert battle_speed(swim, rain, _side("altaria", ability="Cloud Nine")) == battle_speed(swim)


def test_psychic_terrain_blocks_priority_on_grounded():
    a = _side("kingambit", "adamant", {"atk": 32}, "Supreme Overlord")
    grounded = calc(a, _side("garchomp"), "suckerpunch", Field(terrain="psychic"))
    flying = calc(a, _side("dragonite", ability="Inner Focus"), "suckerpunch", Field(terrain="psychic"))
    assert grounded.max == 0 and flying.max > 0


def test_klutz_ignores_own_item():
    d = _side("garchomp")
    lo = calc(_side("lopunny", "jolly", {"atk": 32}, "Limber", "Life Orb"), d, "doubleedge")
    klutz = calc(_side("lopunny", "jolly", {"atk": 32}, "Klutz", "Life Orb"), d, "doubleedge")
    plain = calc(_side("lopunny", "jolly", {"atk": 32}, "Klutz"), d, "doubleedge")
    assert klutz.rolls == plain.rolls and lo.max > klutz.max
