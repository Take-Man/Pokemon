"""対戦記録（相手の6体の組み合わせ）と、その対戦の詳細（選出・逆算ダメ計の記録・判明情報）。

data/user/matches/<id>.json に1対戦1ファイル。
- opp: 相手の6体（選出予想を押した時点で保存）
- detail: 対戦モードで選出や記録を付けたときだけ作る（無い対戦が多い想定）
  - my_team: 対戦開始時点の自分のパーティのコピー（後でパーティを編集しても記録の前提が変わらない）
  - my_picks: 自分の選出（my_team の添字）
  - opp_picks: 相手の選出（種族id）
  - records: 逆算ダメ計・判明情報の記録（engine.infer.Record 形式）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional

from collectors.base import now_iso
from engine.data import ROOT

from . import state, storage

MATCH_DIR = ROOT / "data" / "user" / "matches"
REUSE_MINUTES = 120


def _read(mid: str) -> Optional[dict]:
    return storage.current().get_match(mid)


def _write(m: dict) -> dict:
    m["updated_at"] = now_iso()
    storage.current().put_match(m)
    return m


def list_matches() -> list[dict]:
    out = storage.current().list_matches()
    out.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    return out


def current_id() -> Optional[str]:
    mid = storage.current().get_settings().get("current_match")
    return mid if mid and _read(mid) is not None else None


def set_current(mid: Optional[str]) -> None:
    s = storage.current().get_settings()
    s["current_match"] = mid
    storage.current().put_settings(s)


def get(mid: Optional[str] = None) -> Optional[dict]:
    mid = mid or current_id()
    return _read(mid) if mid else None


def create_or_reuse(opp: list[str]) -> dict:
    """選出予想のたびに呼ぶ。直近の対戦と同じ6体（2時間以内）なら再利用する。"""
    cur = get()
    if cur and sorted(cur.get("opp", [])) == sorted(opp):
        created = datetime.fromisoformat(cur["created_at"])
        if created > datetime.now().astimezone() - timedelta(minutes=REUSE_MINUTES) or cur.get("detail"):
            return cur
    team = state.load_team()
    m = {"id": uuid.uuid4().hex[:10], "created_at": now_iso(), "opp": list(opp),
         "team_id": team.get("id"), "team_name": team.get("name"), "detail": None}
    _write(m)
    set_current(m["id"])
    return m


def delete(mid: str) -> None:
    storage.current().delete_match(mid)
    if current_id() is None:
        set_current(None)


def ensure_detail(m: dict) -> dict:
    if not m.get("detail"):
        team = state.load_team(m.get("team_id")) if m.get("team_id") else state.load_team()
        m["detail"] = {"my_team": [x for x in team.get("members", []) if x.get("species")],
                       "my_team_name": team.get("name"), "my_picks": [], "opp_picks": [], "records": [],
                       "result": None, "memo": ""}
    return m


def update_detail(mid: str, **fields) -> dict:
    m = ensure_detail(get(mid))
    for k, v in fields.items():
        if v is not None:
            m["detail"][k] = v
    return _write(m)


def resnapshot_team(mid: str) -> dict:
    """自分のパーティのコピーを、現在のパーティで取り直す（記録は残す）。"""
    m = ensure_detail(get(mid))
    team = state.load_team()
    m["detail"]["my_team"] = [x for x in team.get("members", []) if x.get("species")]
    m["detail"]["my_team_name"] = team.get("name")
    m["team_id"], m["team_name"] = team.get("id"), team.get("name")
    return _write(m)


def add_record(mid: str, rec: dict) -> dict:
    m = ensure_detail(get(mid))
    rec = dict(rec, id=uuid.uuid4().hex[:8], at=now_iso())
    m["detail"]["records"].append(rec)
    _write(m)
    return rec


def update_record(mid: str, rid: str, rec: dict) -> dict:
    m = ensure_detail(get(mid))
    for i, r in enumerate(m["detail"]["records"]):
        if r["id"] == rid:
            m["detail"]["records"][i] = dict(rec, id=rid, at=r.get("at"), edited_at=now_iso())
            _write(m)
            return m["detail"]["records"][i]
    raise KeyError(rid)


def delete_record(mid: str, rid: str) -> list[str]:
    m = ensure_detail(get(mid))
    reverted: list[str] = []
    for r in m["detail"]["records"]:
        if r["id"] == rid and r.get("effect_ops"):
            reverted = revert_effects(m, r)
    m["detail"]["records"] = [r for r in m["detail"]["records"] if r["id"] != rid]
    m["detail"]["logs"] = [r for r in m["detail"].get("logs", []) if r["id"] != rid]
    _write(m)
    return reverted


def add_log(mid: str, entry: dict) -> dict:
    """現在の対面を手で直したときの変化（項目・変化前・変化後）。逆算には使わず、記録一覧に並べるだけ。"""
    m = ensure_detail(get(mid))
    entry = dict(entry, id=uuid.uuid4().hex[:8], at=now_iso(), kind="log")
    m["detail"].setdefault("logs", []).append(entry)
    _write(m)
    return entry


# ---------------------------------------------------------------------------
# 現在の対面（HP・状態異常・ランク・場の状態）。detail.live に保持し、記録の条件の既定値にする
# ---------------------------------------------------------------------------

RANK_KEYS = ("atk", "def", "spa", "spd", "spe")


def _blank_mon(hp) -> dict:
    return {"hp": hp, "status": "none", "boosts": {k: 0 for k in RANK_KEYS}, "mega": False}


def live_state(m: dict) -> dict:
    """detail.live を既定値で補った形で返す（保存はしない）。"""
    d = m.get("detail") or {}
    lv = d.get("live") or {}
    out = {"my": {}, "opp": {}, "field": {"weather": "none", "terrain": "none", "my_screen": "none",
                                           "opp_screen": "none"},
           "active": {"my": None, "opp": None}}
    out["field"].update(lv.get("field") or {})
    for i in d.get("my_picks", []):
        cur = (lv.get("my") or {}).get(str(i)) or {}
        mon = _blank_mon(None)
        mon.update({k: v for k, v in cur.items() if k != "boosts"})
        mon["boosts"].update(cur.get("boosts") or {})
        out["my"][str(i)] = mon
    for s in d.get("opp_picks", []):
        cur = (lv.get("opp") or {}).get(s) or {}
        mon = _blank_mon(100)
        mon.update({k: v for k, v in cur.items() if k != "boosts"})
        mon["boosts"].update(cur.get("boosts") or {})
        # メガシンカの状態: auto（採用率どおり想定）/ yes（した）/ no（しなかった）
        if mon.get("mega_state") not in ("auto", "yes", "no"):
            mon["mega_state"] = "yes" if mon.get("mega") else "auto"
        mon["mega"] = mon["mega_state"] == "yes"
        out["opp"][s] = mon
    act = lv.get("active") or {}
    my_act = act.get("my")
    out["active"]["my"] = my_act if my_act is not None and str(my_act) in out["my"] else \
        (int(next(iter(out["my"]))) if out["my"] else None)
    opp_act = act.get("opp")
    out["active"]["opp"] = opp_act if opp_act in out["opp"] else (next(iter(out["opp"])) if out["opp"] else None)
    return out


def update_live(mid: str, patch: dict) -> dict:
    """patch は {my: {idx: {...}}, opp: {sid: {...}}, field: {...}, active: {...}} の一部。"""
    m = ensure_detail(get(mid))
    lv = live_state(m)
    for side in ("my", "opp"):
        for k, v in (patch.get(side) or {}).items():
            k = str(k)
            if k not in lv[side]:
                continue
            boosts = v.get("boosts")
            lv[side][k].update({kk: vv for kk, vv in v.items() if kk != "boosts"})
            if side == "opp" and "mega_state" in v:
                lv[side][k]["mega"] = v["mega_state"] == "yes"
            elif side == "opp" and "mega" in v:
                lv[side][k]["mega_state"] = "yes" if v["mega"] else "auto"
            if boosts:
                lv[side][k]["boosts"].update({b: max(-6, min(6, int(x))) for b, x in boosts.items() if b in RANK_KEYS})
    lv["field"].update(patch.get("field") or {})
    lv["active"].update({k: v for k, v in (patch.get("active") or {}).items() if k in ("my", "opp")})
    m["detail"]["live"] = lv
    return _write(m)


_RANK_JA = {"atk": "A", "def": "B", "spa": "C", "spd": "D", "spe": "S"}
_WEATHER_ID = {"raindance": "rain", "primordialsea": "rain", "sunnyday": "sun", "desolateland": "sun", "sandstorm": "sand",
               "hail": "snow", "snowscape": "snow"}
_TERRAIN_ID = {"electricterrain": "electric", "grassyterrain": "grassy", "psychicterrain": "psychic", "mistyterrain": "misty"}
_WEATHER_JA = {"rain": "雨", "sun": "晴れ", "sand": "砂嵐", "snow": "雪"}
_TERRAIN_JA = {"electric": "エレキフィールド", "grassy": "グラスフィールド", "psychic": "サイコフィールド", "misty": "ミストフィールド"}
_STATUS_JA = {"brn": "やけど", "par": "まひ", "psn": "どく", "tox": "もうどく", "slp": "ねむり", "frz": "こおり"}


def _certain_effects(mv: dict) -> dict:
    """技の追加効果のうち、命中すれば必ず起きるもの（ランク変化・状態異常・場の変化）。"""
    sec = mv.get("secondary") or {}
    user_b, target_b = {}, {}
    if mv.get("boosts"):
        (user_b if mv.get("target") == "self" else target_b).update(mv["boosts"])
    user_b.update((mv.get("self") or {}).get("boosts") or {})
    if sec.get("chance") == 100:
        user_b.update((sec.get("self") or {}).get("boosts") or {})
        target_b.update(sec.get("boosts") or {})
    return {"user": user_b, "target": target_b, "status": mv.get("status") if mv.get("target") != "self" else None,
            "side": mv.get("sideCondition"), "weather": mv.get("weather"), "terrain": mv.get("terrain"), "to": mv.get("target")}


def apply_record_effect(mid: str, rec: dict) -> tuple[list[str], list[dict]]:
    """記録の結果（受けた後のHP・当てた後の%・技の確定効果）を現在の対面に反映し、HP以外の反映内容を文にして返す。"""
    from engine.data import dex

    D = dex()
    m = get(mid)
    lv = live_state(ensure_detail(m))
    cond = rec.get("cond") or {}
    team = m["detail"].get("my_team", [])
    notes: list[str] = []
    ops: list[dict] = []   # 反映した変更。記録を削除するとき、矛盾しなければ元に戻す
    mv = D.moves.get(rec.get("move") or (rec.get("reveal_value") if rec.get("reveal_type") == "move" else "") or "")
    kind = rec.get("kind")
    miss = bool(cond.get("miss"))

    def my_name(i):
        return "自分 " + D.pokemon[team[int(i)]["species"]]["ja"]

    def opp_name(s):
        return "相手 " + D.pokemon[s]["ja"]

    # ---- 誰が使い、誰に当たったか
    if kind == "taken":
        user = ("opp", rec.get("opp")); target = ("my", str(rec.get("my_index")))
    elif kind == "dealt":
        user = ("my", str(rec.get("my_index"))); target = ("opp", rec.get("opp"))
    elif kind == "reveal" and rec.get("reveal_type") == "move":
        user = ("opp", rec.get("opp")); target = ("my", str(lv["active"]["my"]) if lv["active"]["my"] is not None else None)
    else:
        user = target = None
    name = lambda t: (my_name(t[1]) if t[0] == "my" else opp_name(t[1])) if t and t[1] is not None else ""
    mon = lambda t: lv[t[0]].get(t[1]) if t and t[1] is not None else None

    if kind in ("taken", "dealt") and not miss:
        tgt = mon(target)
        if tgt is not None:
            tgt["hp"] = 0 if cond.get("ko") else rec.get("after")
    if mv and not miss and user:
        fx = _certain_effects(mv)

        def boost(t, stats):
            x = mon(t)
            if x is None:
                return
            for st, n in stats.items():
                if st in _RANK_JA and n:
                    old = x["boosts"].get(st, 0)
                    new = max(-6, min(6, old + n))
                    if new != old:
                        x["boosts"][st] = new
                        notes.append(f"{name(t)} {_RANK_JA[st]}ランク {new - old:+d}")
                        ops.append({"t": "boost", "side": t[0], "key": t[1], "stat": st, "before": old, "after": new, "label": f"{name(t)} {_RANK_JA[st]}ランク"})
        boost(user, fx["user"])
        if fx["to"] not in ("self", "foeSide", "allySide", "all"):
            boost(target, fx["target"])
            tgt = mon(target)
            if fx["status"] and tgt is not None and tgt["status"] == "none":
                tgt["status"] = fx["status"]
                notes.append(f"{name(target)} {_STATUS_JA.get(fx['status'], fx['status'])}")
                ops.append({"t": "status", "side": target[0], "key": target[1], "before": "none", "after": fx["status"], "label": f"{name(target)} 状態異常"})
        if fx["weather"] and _WEATHER_ID.get(str(fx["weather"]).lower()) and lv["field"].get("weather") != _WEATHER_ID[str(fx["weather"]).lower()]:
            ops.append({"t": "field", "key": "weather", "before": lv["field"].get("weather"), "after": _WEATHER_ID[str(fx["weather"]).lower()], "label": "天候"})
            lv["field"]["weather"] = _WEATHER_ID[str(fx["weather"]).lower()]
            notes.append(f"天候 {_WEATHER_JA[lv['field']['weather']]}")
        if fx["terrain"] and _TERRAIN_ID.get(str(fx["terrain"]).lower()) and lv["field"].get("terrain") != _TERRAIN_ID[str(fx["terrain"]).lower()]:
            ops.append({"t": "field", "key": "terrain", "before": lv["field"].get("terrain"), "after": _TERRAIN_ID[str(fx["terrain"]).lower()], "label": "フィールド"})
            lv["field"]["terrain"] = _TERRAIN_ID[str(fx["terrain"]).lower()]
            notes.append(f"フィールド {_TERRAIN_JA[lv['field']['terrain']]}")
        sc = str(fx["side"] or "").lower()
        if sc in ("stealthrock", "spikes", "toxicspikes", "stickyweb"):
            key = "opp_hazards" if user[0] == "my" else "my_hazards"
            h = {"rocks": False, "spikes": 0, "tspikes": 0, "web": False, **(lv["field"].get(key) or {})}
            h_before = dict(h)
            side_ja = "相手側" if user[0] == "my" else "自分側"
            if sc == "stealthrock" and not h["rocks"]:
                h["rocks"] = True; notes.append(f"{side_ja} ステルスロック")
            elif sc == "spikes" and h["spikes"] < 3:
                h["spikes"] += 1; notes.append(f"{side_ja} まきびし{h['spikes']}層")
            elif sc == "toxicspikes" and h["tspikes"] < 2:
                h["tspikes"] += 1; notes.append(f"{side_ja} どくびし{h['tspikes']}層")
            elif sc == "stickyweb" and not h["web"]:
                h["web"] = True; notes.append(f"{side_ja} ねばねばネット")
            if h != h_before:
                ops.append({"t": "field", "key": key, "before": h_before, "after": dict(h), "label": f"{side_ja} 設置"})
            lv["field"][key] = h
        if sc in ("reflect", "lightscreen", "auroraveil"):
            key = "my_screen" if user[0] == "my" else "opp_screen"
            have = {"reflect": {"reflect"}, "lightscreen": {"lightscreen"}, "both": {"reflect", "lightscreen"}}.get(lv["field"].get(key, "none"), set())
            have = have | ({"reflect", "lightscreen"} if sc == "auroraveil" else {sc})
            after = "both" if have == {"reflect", "lightscreen"} else next(iter(have))
            if after != lv["field"].get(key, "none"):
                ops.append({"t": "field", "key": key, "before": lv["field"].get(key, "none"), "after": after, "label": "壁"})
            lv["field"][key] = after
            notes.append(f"{'自分側' if user[0] == 'my' else '相手側'} {({'reflect': 'リフレクター', 'lightscreen': 'ひかりのかべ', 'auroraveil': 'オーロラベール'})[sc]}")
    if kind in ("taken", "dealt") and cond.get("opp_mega") and rec.get("opp") in lv["opp"]:
        lv["opp"][rec["opp"]]["mega"] = True
        lv["opp"][rec["opp"]]["mega_state"] = "yes"
    m["detail"]["live"] = lv
    _write(m)
    return notes, ops


def set_record_effects(mid: str, rid: str, effects: list[str], ops: list[dict]) -> None:
    m = ensure_detail(get(mid))
    for r in m["detail"]["records"]:
        if r["id"] == rid:
            r["effects"] = effects
            r["effect_ops"] = ops
    _write(m)


def revert_effects(m: dict, rec: dict) -> list[str]:
    """記録で反映した変更を、いまの値が反映直後のままのものだけ元に戻す。食い違うものは何もしない。"""
    lv = live_state(m)
    done: list[str] = []
    for op in rec.get("effect_ops") or []:
        t = op.get("t")
        if t == "boost":
            x = lv[op["side"]].get(op["key"])
            if x is not None and x["boosts"].get(op["stat"], 0) == op["after"]:
                x["boosts"][op["stat"]] = op["before"]
                done.append(f"{op['label']} {op['before'] - op['after']:+d}")
        elif t == "status":
            x = lv[op["side"]].get(op["key"])
            if x is not None and x["status"] == op["after"]:
                x["status"] = op["before"]
                done.append(f"{op['label']} {_STATUS_JA.get(op['after'], op['after'])}を解除")
        elif t == "field" and lv["field"].get(op["key"], "none" if isinstance(op["after"], str) else {}) == op["after"]:
            lv["field"][op["key"]] = op["before"]
            done.append(f"{op['label']} を元に戻した")
    if done:
        m["detail"]["live"] = lv
    return done
