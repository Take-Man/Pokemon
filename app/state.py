"""アプリの状態（自分のパーティ・相手の6体・計算履歴）の保存と、Claude向けの state/ 出力。"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from collectors.base import now_iso
from engine.data import ROOT, STAT_JA, dex
from engine.sets import MonSet, load_snapshot

USER = ROOT / "data" / "user"
STATE = ROOT / "state"
TEAM_FILE = USER / "team.json"
OPP_FILE = STATE / "opponent.json"
PRED_FILE = STATE / "prediction.json"
CALC_LOG = STATE / "calc_log.jsonl"
CURRENT_MD = STATE / "current.md"
_lock = threading.Lock()


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


# ---- 自分のパーティ（複数保存） ---------------------------------------------------
# data/user/teams/<id>.json に1パーティ1ファイル。どれを使うかは data/user/settings.json の active。

TEAMS_DIR = USER / "teams"
SETTINGS_FILE = USER / "settings.json"
ARCHETYPES = ["対面", "サイクル", "展開", "スタンダード", "受けループ"]


def _new_id() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


def _migrate_legacy() -> None:
    """旧形式（data/user/team.json 1ファイル）を移す。"""
    if TEAM_FILE.exists() and not TEAMS_DIR.exists():
        t = _read(TEAM_FILE, {"name": "", "members": []})
        tid = _new_id()
        t.update(id=tid, name=t.get("name") or "パーティ1")
        _write(TEAMS_DIR / f"{tid}.json", t)
        _write(SETTINGS_FILE, {"active": tid})
        TEAM_FILE.rename(TEAM_FILE.with_suffix(".json.migrated"))


def list_teams() -> list[dict]:
    _migrate_legacy()
    out = []
    for p in sorted(TEAMS_DIR.glob("*.json")) if TEAMS_DIR.exists() else []:
        t = _read(p, None)
        if t:
            out.append(t)
    out.sort(key=lambda t: t.get("updated_at") or "", reverse=True)
    return out


def active_team_id() -> Optional[str]:
    _migrate_legacy()
    tid = _read(SETTINGS_FILE, {}).get("active")
    if tid and (TEAMS_DIR / f"{tid}.json").exists():
        return tid
    teams = list_teams()
    return teams[0]["id"] if teams else None


def set_active_team(tid: str) -> dict:
    if not (TEAMS_DIR / f"{tid}.json").exists():
        raise KeyError(tid)
    s = _read(SETTINGS_FILE, {})
    s["active"] = tid
    _write(SETTINGS_FILE, s)
    render_current()
    return load_team()


def create_team(name: str = "", members: Optional[list] = None, archetype: str = "スタンダード") -> dict:
    tid = _new_id()
    n = len(list_teams()) + 1
    t = {"id": tid, "name": name or f"パーティ{n}", "archetype": archetype, "members": members or [],
         "created_at": now_iso(), "updated_at": now_iso()}
    _write(TEAMS_DIR / f"{tid}.json", t)
    set_active_team(tid)
    return t


def delete_team(tid: str) -> None:
    p = TEAMS_DIR / f"{tid}.json"
    if p.exists():
        p.unlink()
    s = _read(SETTINGS_FILE, {})
    if s.get("active") == tid:
        s["active"] = None
        _write(SETTINGS_FILE, s)
    render_current()


def load_team(tid: Optional[str] = None) -> dict:
    tid = tid or active_team_id()
    if not tid:
        return create_team()
    t = _read(TEAMS_DIR / f"{tid}.json", None)
    if t is None:
        return create_team()
    t.setdefault("archetype", "スタンダード")
    return t


def save_team(team: dict) -> dict:
    tid = team.get("id") or active_team_id()
    cur = load_team(tid) if tid else {}
    cur.update({k: v for k, v in team.items() if k in ("name", "members", "archetype")})
    cur["id"] = cur.get("id") or _new_id()
    cur["updated_at"] = now_iso()
    _write(TEAMS_DIR / f"{cur['id']}.json", cur)
    render_current()
    return cur


def team_sets(tid: Optional[str] = None) -> list[MonSet]:
    return [MonSet.from_dict(m) for m in load_team(tid).get("members", []) if m.get("species")]


# ---- 相手の6体 --------------------------------------------------------------
# 手入力はUIから、スクショ判定はClaudeのチャットから、どちらも state/opponent.json に書く。

def load_opponent() -> dict:
    return _read(OPP_FILE, {"species": [], "sets": {}, "source": "manual", "updated_at": None})


def save_opponent(opp: dict) -> dict:
    D = dex()
    ids = []
    for s in opp.get("species", []):
        p = D.pokemon.get(s)
        if p:
            ids.append(p["id"])
    opp = {"species": ids[:6], "sets": opp.get("sets", {}), "source": opp.get("source", "manual"),
           "updated_at": now_iso()}
    _write(OPP_FILE, opp)
    return opp


def opponent_mtime() -> float:
    return OPP_FILE.stat().st_mtime if OPP_FILE.exists() else 0.0


# ---- 予想・計算履歴 ----------------------------------------------------------

def save_prediction(pred: dict) -> None:
    pred = dict(pred, updated_at=now_iso())
    _write(PRED_FILE, pred)
    render_current()


def load_prediction() -> Optional[dict]:
    return _read(PRED_FILE, None)


def log_calc(entry: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    with _lock:
        lines = CALC_LOG.read_text(encoding="utf-8").splitlines() if CALC_LOG.exists() else []
        lines.append(json.dumps(dict(entry, at=now_iso()), ensure_ascii=False))
        CALC_LOG.write_text("\n".join(lines[-30:]) + "\n", encoding="utf-8")
    render_current()


def recent_calcs(n: int = 10) -> list[dict]:
    if not CALC_LOG.exists():
        return []
    return [json.loads(x) for x in CALC_LOG.read_text(encoding="utf-8").splitlines()[-n:] if x.strip()]


# ---- Claude向けの現在状況 -----------------------------------------------------

def _set_line(m: MonSet) -> str:
    D = dex()
    sp = " ".join(f"{STAT_JA[k]}{v}" for k, v in m.sp.items() if v)
    moves = "／".join(D.ja("moves", x) for x in m.moves)
    return (f"{D.pokemon[m.species]['ja']}｜{D.ja('natures', m.nature)}｜{sp}｜"
            f"{D.ja('abilities', m.ability)}｜{D.ja('items', m.item) or 'なし'}｜{moves}")


def render_current() -> str:
    """state/current.md を書き直す。Claudeはここを起点に周辺ファイルを読む。"""
    D = dex()
    snap = load_snapshot()
    team = load_team()
    opp = load_opponent()
    pred = load_prediction()
    L = ["# 現在の状況", "", f"更新: {now_iso()}", ""]
    L += ["## 環境データ", ""]
    if snap:
        L.append(f"- {snap.get('source')} {snap.get('season_label')}（取得 {snap.get('fetched_at')}）"
                 f" ランキング{len(snap.get('ranking', []))}件・詳細{len(snap.get('pokemon', {}))}件")
        L.append("- 詳細: data/snapshots/current/usage.json")
    else:
        L.append("- なし（型は種族値からの推定）")
    L += ["", f"## 自分のパーティ: {team.get('name', '')}（構築の型: {team.get('archetype', '')}）", "",
          "- 保存済みパーティ: " + "、".join(t.get("name", "") for t in list_teams()), ""]
    for m in team.get("members", []):
        if m.get("species"):
            L.append("- " + _set_line(MonSet.from_dict(m)))
    L += ["", "## 相手の6体", ""]
    if opp.get("species"):
        L.append(f"- 入力元: {opp.get('source')}（{opp.get('updated_at')}）")
        L.append("- " + "、".join(D.pokemon[s]["ja"] for s in opp["species"] if D.pokemon.get(s)))
    else:
        L.append("- 未入力")
    if pred:
        L += ["", "## 選出予想（ルールベース）", "", f"- データ: {pred.get('data_source')}（{pred.get('updated_at')}）"]
        for o in pred.get("opponent", []):
            thr = "、".join(o.get("threatens", [])) or "なし"
            L.append(f"- {o['rank']}. {o['ja']}（スコア{o['score']}）想定型: {o['set_label']} ／ 重い相手: {thr}"
                     f" ／ 受け出し先: {'、'.join(o.get('switch_ins') or []) or 'なし'}")
            for su in o.get("setup") or []:
                if su.get("flips"):
                    L.append(f"  - {su['move']}を積まれると起点にされる: {'、'.join(su['flips'])}")
        if pred.get("recommend"):
            L += ["", "推奨選出:"]
            for c in pred["recommend"]:
                L.append(f"- {'・'.join(c['members'])}（{c['score']}）")
    calcs = recent_calcs(8)
    if calcs:
        L += ["", "## 直近のダメージ計算", ""]
        for c in calcs:
            L.append(f"- {c.get('summary', '')}")
    L += ["", "## 参照先", "",
          "- 固定データ: data/static/（types.json, natures.json, pokemon.json, moves.json, items.json, abilities.json）",
          "- 用語・役割・構築の型: knowledge/",
          "- 予想の詳細（対面表）: state/prediction.json", ""]
    text = "\n".join(L)
    STATE.mkdir(parents=True, exist_ok=True)
    CURRENT_MD.write_text(text, encoding="utf-8")
    return text
