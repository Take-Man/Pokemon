"""逆算ダメ計と対戦記録のテスト。"""
from engine.damage import calc
from engine.infer import Record, infer, opponent_build
from engine.matchup import as_side
from engine.sets import MonSet

SNAP = {"pokemon": {"garchomp": {
    "natures": [{"id": "jolly", "rate": 40}, {"id": "adamant", "rate": 30}],
    "items": [{"id": "lifeorb", "rate": 20}, {"id": "focussash", "rate": 30}],
    "abilities": [{"id": "roughskin", "rate": 99}],
    "moves": [{"id": "earthquake", "rate": 80}, {"id": "dragonclaw", "rate": 50}],
    "sp": [{"spread": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}, "rate": 50}]}}}
ME = MonSet("hippowdon", "impish", {"hp": 32, "def": 2, "spd": 32}, "Sand Stream", "Sitrus Berry", ["earthquake"])
TRUTH = MonSet("garchomp", "jolly", {"atk": 32, "spe": 32, "hp": 2}, "Rough Skin", "Life Orb", ["earthquake"])


def _taken(roll_index=8):
    r = calc(as_side(TRUTH), as_side(ME), "earthquake")
    hp = r.defender_hp
    return Record("t1", "taken", "garchomp", ME.to_dict(), "earthquake", hp, hp - r.rolls[roll_index], {})


def test_taken_identifies_life_orb():
    res = infer("garchomp", [_taken()], SNAP)
    assert res["feasible"] and res["items"][0]["id"] == "lifeorb"
    jolly = next(n for n in res["by_nature"] if n["id"] == "jolly")
    lo, hi = jolly["ranges"]["atk"]
    assert lo <= 32 <= hi


def test_truth_is_always_feasible_for_dealt():
    r = calc(as_side(ME), as_side(TRUTH), "earthquake")
    pct = round(r.rolls[5] / r.defender_hp * 100)
    rec = Record("d1", "dealt", "garchomp", ME.to_dict(), "earthquake", 100, 100 - pct, {})
    res = infer("garchomp", [_taken(), rec], SNAP)
    assert res["feasible"]
    assert res["sp_ranges"]["hp"][0] <= 2 <= res["sp_ranges"]["hp"][1]


def test_impossible_record_is_flagged():
    rec = Record("x", "taken", "garchomp", ME.to_dict(), "earthquake", 215, 1, {})
    res = infer("garchomp", [rec], SNAP)
    assert not res["feasible"] and any("再現できない" in n for n in res["notes"])


def test_build_marks_confirmed():
    recs = [_taken(), Record("r", "reveal", "garchomp", reveal_type="move", reveal_value="swordsdance")]
    b = opponent_build("garchomp", recs, SNAP)
    srcs = {m["id"]: m["src"] for m in b["moves"]}
    assert srcs["swordsdance"] == "confirmed" and srcs["earthquake"] == "confirmed"
    assert b["item"]["src"] == "inferred" and b["item"]["id"] == "Life Orb"


def test_match_storage(tmp_path, monkeypatch):
    from app import matches, state

    monkeypatch.setattr(state, "USER", tmp_path)
    monkeypatch.setattr(state, "TEAMS_DIR", tmp_path / "teams")
    monkeypatch.setattr(state, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(state, "TEAM_FILE", tmp_path / "team.json")
    monkeypatch.setattr(state, "render_current", lambda: "")
    monkeypatch.setattr(matches, "MATCH_DIR", tmp_path / "matches")
    state.save_team({"members": [ME.to_dict()]})
    m = matches.create_or_reuse(["garchomp", "salamence"])
    assert matches.create_or_reuse(["salamence", "garchomp"])["id"] == m["id"]
    assert matches.get(m["id"])["detail"] is None
    rec = matches.add_record(m["id"], {"kind": "reveal", "opp": "garchomp", "reveal_type": "item",
                                       "reveal_value": "lifeorb"})
    got = matches.get(m["id"])
    assert got["detail"]["my_team"][0]["species"] == "hippowdon" and len(got["detail"]["records"]) == 1
    matches.update_record(m["id"], rec["id"], dict(rec, reveal_value="focussash"))
    assert matches.get(m["id"])["detail"]["records"][0]["reveal_value"] == "focussash"
    matches.delete_record(m["id"], rec["id"])
    assert matches.get(m["id"])["detail"]["records"] == []
    assert len(matches.list_matches()) == 1


def test_live_state_and_effects(tmp_path, monkeypatch):
    from app import matches, state

    monkeypatch.setattr(state, "USER", tmp_path)
    monkeypatch.setattr(state, "TEAMS_DIR", tmp_path / "teams")
    monkeypatch.setattr(state, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(state, "TEAM_FILE", tmp_path / "team.json")
    monkeypatch.setattr(state, "render_current", lambda: "")
    monkeypatch.setattr(matches, "MATCH_DIR", tmp_path / "matches")
    state.save_team({"members": [ME.to_dict()]})
    m = matches.create_or_reuse(["garchomp"])
    matches.update_detail(m["id"], my_picks=[0], opp_picks=["garchomp"])
    matches.update_live(m["id"], {"opp": {"garchomp": {"boosts": {"atk": 2}}}, "field": {"weather": "sand"}})
    lv = matches.live_state(matches.get(m["id"]))
    assert lv["opp"]["garchomp"]["boosts"]["atk"] == 2 and lv["field"]["weather"] == "sand"
    assert lv["active"] == {"my": 0, "opp": "garchomp"}
    matches.apply_record_effect(m["id"], {"kind": "taken", "my_index": 0, "opp": "garchomp", "move": "thunderwave",
                                          "after": 150, "cond": {}})
    matches.apply_record_effect(m["id"], {"kind": "dealt", "my_index": 0, "opp": "garchomp", "move": "earthquake",
                                          "after": 40, "cond": {}})
    lv = matches.live_state(matches.get(m["id"]))
    assert lv["my"]["0"]["hp"] == 150 and lv["my"]["0"]["status"] == "par"
    assert lv["opp"]["garchomp"]["hp"] == 40


def test_status_condition_changes_damage():
    from engine.infer import Cond

    c = Cond.from_dict({"atk_status": "brn"})
    assert c.a_status() == "brn" and Cond.from_dict({"burn": True}).a_status() == "brn"
    assert Cond.from_dict({"def_status": "none"}).d_status() is None


def test_no_mega_build_drops_stone():
    snap = {"pokemon": {"garchomp": {"items": [{"id": "garchompitez", "rate": 40}, {"id": "choicescarf", "rate": 20}],
                                     "natures": [{"id": "jolly"}], "abilities": [{"id": "roughskin"}],
                                     "moves": [{"id": "earthquake", "rate": 70}], "sp": []}}}
    auto = opponent_build("garchomp", [], snap, None)
    assert auto["battle_species"] == "garchompmegaz"
    no = opponent_build("garchomp", [], snap, False)
    assert no["battle_species"] == "garchomp" and no["item"]["id"] == "Choice Scarf"
    yes = opponent_build("garchomp", [], snap, True)
    assert yes["battle_species"] != "garchomp"


def test_duel_endpoint():
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/calc/duel", json={"me": {"species": "hippowdon", "nature": "impish", "sp": {"hp": 32, "def": 32}},
                                        "opp": {"species": "garchomp", "nature": "jolly", "sp": {"atk": 32, "spe": 32}},
                                        "my_moves": ["earthquake"], "opp_moves": ["earthquake", "dragonclaw"], "log": False}).json()
    assert len(r["to_opp"]) == 1 and len(r["to_me"]) == 2 and r["me"]["speed"] < r["opp"]["speed"]


def test_zero_after_is_ko_and_spread_total():
    # 残り0%は倒れた扱い（オーバーキルでも矛盾にならない）
    rec = Record("k", "taken", "garchomp", ME.to_dict(), "earthquake", 30, 0, {})
    res = infer("garchomp", [rec], SNAP)
    assert res["feasible"]
    b = opponent_build("garchomp", [rec], SNAP)
    assert sum(b["sp"].values()) <= 66


def test_index_has_cache_busting():
    from fastapi.testclient import TestClient

    from app.server import API_VERSION, app

    c = TestClient(app)
    r = c.get("/")
    assert "/static/app.js?v=" in r.text and "no-cache" in r.headers["cache-control"]
    assert c.get("/api/meta").json()["api_version"] == API_VERSION
    js = c.get("/static/app.js").text
    assert f"APP_API_VERSION = {API_VERSION}" in js


def test_every_status_move_has_effect_text():
    import json
    from pathlib import Path

    from engine.damage import Field, Side
    from engine.move_effects import EFFECT_JA, describe
    from engine.stats import Build

    moves = json.loads((Path(__file__).resolve().parents[1] / "data/static/moves.json").read_text())
    status = [m["id"] for m in moves if m["category"] == "Status"]
    assert set(status) <= set(EFFECT_JA)
    a = Side(Build("garchomp", "jolly", {"atk": 32, "spe": 32}, "Rough Skin", "Leftovers"), hp_percent=60)
    d = Side(Build("rotomwash", "bold", {"hp": 32, "def": 32}, "Levitate", "Leftovers"))
    for mid in status:
        for x, y in ((a, d), (d, a)):
            r = describe(x, y, mid, Field("sun", "misty"))
            assert r["text"] and isinstance(r["notes"], list)
    # 対面による補足
    assert "でんき" in describe(a, d, "thunderwave")["fails"]
    assert describe(d, a, "thunderwave")["fails"]  # ガブリアスはじめん
    assert "HP" in describe(a, d, "recover")["notes"][-1]
    assert describe(a, d, "auroraveil")["fails"] and not describe(a, d, "auroraveil", Field("snow"))["fails"]
    assert "地面にいない" in describe(a, d, "spikes")["notes"][-1]


def test_duel_endpoint_status_effect():
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    r = c.post("/api/calc/duel", json={"me": {"species": "garchomp", "nature": "jolly", "sp": {"atk": 32, "spe": 32}},
                                        "opp": {"species": "rotomwash", "nature": "bold", "sp": {"hp": 32}},
                                        "my_moves": ["swordsdance", "stealthrock"], "opp_moves": [], "log": False}).json()
    sd, sr = r["to_opp"]
    assert sd["effect"]["text"].startswith("自分の攻撃") and "+2" in sd["effect"]["notes"][0]
    assert "出てくるたび" in sr["effect"]["notes"][-1]


def test_battle_view_panels(tmp_path, monkeypatch):
    from app import battle, matches, state

    monkeypatch.setattr(state, "USER", tmp_path)
    monkeypatch.setattr(state, "TEAMS_DIR", tmp_path / "teams")
    monkeypatch.setattr(state, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(state, "TEAM_FILE", tmp_path / "team.json")
    monkeypatch.setattr(state, "render_current", lambda: "")
    monkeypatch.setattr(matches, "MATCH_DIR", tmp_path / "matches")
    state.save_team({"members": [ME.to_dict()]})
    m = matches.create_or_reuse(["garchomp", "salamence"])
    matches.add_record(m["id"], {"kind": "reveal", "opp": "garchomp", "reveal_type": "move", "reveal_value": "earthquake"})
    matches.update_detail(m["id"], my_picks=[0], opp_picks=["garchomp"])
    v = battle.view(m["id"])
    r = v["records"][0]
    assert r["kind_short"] == "技" and r["chip_move"] == "earthquake"
    x = v["mine"][0]
    assert x["moves"] and x["moves"][0]["ja"] and "battle_species" in x
    cell = v["matrix"][0][0]
    assert cell["a_move_id"] and cell["b_move_id"]


def test_opp_moves_include_status_over_one_percent():
    from app.server import opp_move_list
    from engine.sets import load_snapshot

    rows = ((load_snapshot() or {}).get("pokemon", {}).get("garchomp") or {}).get("moves", [])
    out = opp_move_list("garchompmegaz" if rows else "garchomp")
    if rows:
        want = [r["id"] for r in rows if (r.get("rate") or 0) >= 1.0]
        assert [m["id"] for m in out if m["src"] == "usage"] == want
        assert any(m["id"] == "stealthrock" for m in out)  # 変化技も含む
    else:
        assert out


def test_mega_name_has_no_assumption_note():
    from engine.infer import opponent_build
    from engine.sets import load_snapshot

    b = opponent_build("garchomp", [], load_snapshot(), None)
    assert "（" not in b["battle_ja"]
    b2 = opponent_build("garchomp", [], load_snapshot(), False)
    assert b2["battle_ja"].endswith("（メガシンカなし）")


def test_types_endpoint_has_abilities():
    from fastapi.testclient import TestClient

    from app.server import app

    d = TestClient(app).get("/api/types").json()
    rot = next(p for p in d["pokemon"] if p["id"] == "rotomwash")
    assert rot["abilities"] == ["levitate"]


def test_duel_real_hp_for_me():
    from fastapi.testclient import TestClient

    from app.server import app

    c = TestClient(app)
    body = {"me": {"species": "garchomp", "nature": "jolly", "sp": {"atk": 32, "spe": 32}, "hp": 76},
            "opp": {"species": "gholdengo", "nature": "modest", "sp": {"spa": 32}},
            "my_moves": ["earthquake"], "opp_moves": ["shadowball"], "log": False}
    r = c.post("/api/calc/duel", json=body).json()
    assert r["me"]["current_hp"] == 76
    body["me"]["hp"] = 999
    assert c.post("/api/calc/duel", json=body).json()["me"]["current_hp"] == c.post("/api/calc/duel", json=body).json()["me"]["stats"]["hp"]


def test_taken_without_before_uses_max_hp():
    rec = _taken()
    rec.before = None  # 受ける前のHPを空欄にしたら満タンとして扱う
    res = infer("garchomp", [rec], SNAP)
    assert res["feasible"] and res["items"][0]["id"] == "lifeorb"


def test_duel_walls_are_even():
    from engine.matchup import duel
    a = MonSet("hippowdon", "impish", {"hp": 32, "def": 32}, "Sand Stream", None, ["slackoff"])
    b = MonSet("garchomp", "jolly", {"atk": 32}, "Rough Skin", None, ["swordsdance"])
    assert duel(a, b)["score"] == 0.5
