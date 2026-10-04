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

import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from collectors.base import now_iso
from engine.data import ROOT

from . import state

MATCH_DIR = ROOT / "data" / "user" / "matches"
REUSE_MINUTES = 120


def _path(mid: str):
    return MATCH_DIR / f"{mid}.json"


def _read(mid: str) -> Optional[dict]:
    p = _path(mid)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _write(m: dict) -> dict:
    MATCH_DIR.mkdir(parents=True, exist_ok=True)
    m["updated_at"] = now_iso()
    tmp = _path(m["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_path(m["id"]))
    return m


def list_matches() -> list[dict]:
    if not MATCH_DIR.exists():
        return []
    out = []
    for p in MATCH_DIR.glob("*.json"):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    out.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    return out


def current_id() -> Optional[str]:
    mid = state._read(state.SETTINGS_FILE, {}).get("current_match")
    return mid if mid and _path(mid).exists() else None


def set_current(mid: Optional[str]) -> None:
    s = state._read(state.SETTINGS_FILE, {})
    s["current_match"] = mid
    state._write(state.SETTINGS_FILE, s)


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
    p = _path(mid)
    if p.exists():
        p.unlink()
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


def delete_record(mid: str, rid: str) -> None:
    m = ensure_detail(get(mid))
    m["detail"]["records"] = [r for r in m["detail"]["records"] if r["id"] != rid]
    _write(m)


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


def apply_record_effect(mid: str, rec: dict) -> None:
    """記録の結果（受けた後のHP・当てた後の%・状態異常技）を現在の対面に反映する。"""
    from engine.data import dex

    if rec.get("kind") not in ("taken", "dealt"):
        return
    D = dex()
    m = get(mid)
    lv = live_state(ensure_detail(m))
    cond = rec.get("cond") or {}
    mv = D.moves.get(rec.get("move") or "")
    st = mv.get("status") if mv else None
    if rec["kind"] == "taken" and rec.get("my_index") is not None and str(rec["my_index"]) in lv["my"]:
        tgt = lv["my"][str(rec["my_index"])]
        tgt["hp"] = 0 if cond.get("ko") else rec.get("after")
        if st and tgt["status"] == "none":
            tgt["status"] = st
    elif rec["kind"] == "dealt" and rec.get("opp") in lv["opp"]:
        tgt = lv["opp"][rec["opp"]]
        tgt["hp"] = 0 if cond.get("ko") else rec.get("after")
        if st and tgt["status"] == "none":
            tgt["status"] = st
    if cond.get("opp_mega") and rec.get("opp") in lv["opp"]:
        lv["opp"][rec["opp"]]["mega"] = True
        lv["opp"][rec["opp"]]["mega_state"] = "yes"
    m["detail"]["live"] = lv
    _write(m)
