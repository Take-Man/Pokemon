"""役割判定・調整の逆算・パーティ保存のテスト。"""
from engine.matchup import battle_species
from engine.roles import tag_roles, type_overlap
from engine.sets import MonSet
from engine.tuning import ko, survive


def test_mega_species_from_dict_stone():
    assert battle_species(MonSet("garchomp", item="Garchompite Z")) == "garchompmegaz"
    assert battle_species(MonSet("charizard", item="Charizardite Y")) == "charizardmegay"


def test_roles():
    m = MonSet("dragonite", "adamant", {"atk": 32, "spe": 32, "hp": 2}, "Multiscale", None,
               ["dragondance", "extremespeed", "earthquake", "roost"])
    tags = {t["tag"] for t in tag_roles(m)}
    assert "ace" in tags and "stopper" in tags and "faceoff" in tags
    w = MonSet("corviknight", "impish", {"hp": 32, "def": 32, "spd": 2}, "Pressure", "Leftovers",
               ["roost", "uturn", "bodypress", "defog"])
    tags = {t["tag"] for t in tag_roles(w)}
    assert "wall_phys" in tags and "pivot" in tags


def test_type_overlap_levitate():
    rows = {r["type"]: r for r in type_overlap([MonSet("gengar", ability="Levitate")])}
    assert rows["Ground"]["weak"] == 0


def test_survive_and_ko():
    hippo = MonSet("hippowdon", "impish", {"hp": 32, "def": 2, "spd": 32}, "Sand Stream", None, ["earthquake"])
    atk = MonSet("garchomp", "adamant", {"atk": 32, "spe": 32}, "Rough Skin", None, ["earthquake"])
    r = survive(hippo, atk, "earthquake", hits=2, threshold=0.0)
    assert r["feasible"] and r["options"][0]["ko_chance"] == 0
    r = ko(atk, MonSet("gengar", "timid", {"spa": 32, "spe": 32}, "Cursed Body"), "earthquake", 1, 1.0)
    assert r["feasible"] and r["option"]["ko_chance"] == 1.0


def test_team_storage(tmp_path, monkeypatch):
    from app import state

    monkeypatch.setattr(state, "USER", tmp_path)
    monkeypatch.setattr(state, "TEAMS_DIR", tmp_path / "teams")
    monkeypatch.setattr(state, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(state, "TEAM_FILE", tmp_path / "team.json")
    monkeypatch.setattr(state, "render_current", lambda: "")
    a = state.create_team("A")
    b = state.create_team("B")
    assert state.active_team_id() == b["id"]
    state.set_active_team(a["id"])
    state.save_team({"id": a["id"], "name": "A2", "members": [{"species": "garchomp"}]})
    assert state.load_team()["name"] == "A2"
    assert len(state.list_teams()) == 2
    state.delete_team(a["id"])
    assert state.active_team_id() == b["id"]


def test_mega_of_uses_stone_table():
    from engine.data import dex

    D = dex()
    assert [m["id"] for m in D.mega_of("charizard")] == ["charizardmegax", "charizardmegay"]
    assert [m["id"] for m in D.mega_of("meowsticf")] == ["meowsticfmega"]


def test_autofill_only_fills_empty():
    from engine.sets import autofill

    snap = {"pokemon": {"garchomp": {
        "natures": [{"id": "jolly"}, {"id": "modest"}], "abilities": [{"id": "roughskin"}],
        "items": [{"id": "garchompitez"}, {"id": "choicescarf"}],
        "moves": [{"id": "earthquake", "rate": 70}, {"id": "dracometeor", "rate": 30}, {"id": "stoneedge", "rate": 20}],
        "sp": [{"spread": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}},
               {"spread": {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32}}]}}}
    r = autofill({"species": "garchomp", "nature": "modest"}, snap)
    m = r["member"]
    assert m["nature"] == "modest" and m["sp"]["spa"] == 32 and "stoneedge" not in m["moves"]
    assert m["item"] == "Choice Scarf"  # メガストーンは自動入力しない
    assert autofill({"species": "garchomp", "moves": ["surf"]}, snap)["filled"] == []  # 合致する型が無い
    assert autofill({"species": "pikachu"}, snap)["filled"] == []  # 型データが無い
