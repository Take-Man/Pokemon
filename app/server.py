"""ローカルWebアプリ（FastAPI）。起動: python -m app  →  http://127.0.0.1:8765"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
import hashlib

from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from collectors import jobs
from engine.move_effects import describe as describe_effect
from engine.damage import Field, Options, Side, calc
from engine.data import STATS, dex, to_id
from engine.matchup import battle_species, predict
from engine.sets import MonSet, estimate_set, likely_set, load_snapshot, usage_set
from engine.stats import Build, speed_variants, validate_sp

from . import state

STATIC = Path(__file__).parent / "static"
# 画面(app.js)とサーバのAPIの世代。app.js の APP_API_VERSION と一致しなければ画面に再起動を促す表示を出す
API_VERSION = 10
app = FastAPI(title="Pokemon Battle Assistant")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_pred_lock = threading.Lock()
NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def _file_hash(name: str) -> str:
    return hashlib.sha1((STATIC / name).read_bytes()).hexdigest()[:10]


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    """ブラウザが古い app.js / style.css を使い続けないようにする。"""
    resp = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        for k, v in NO_CACHE.items():
            resp.headers[k] = v
    return resp


@app.get("/", response_class=HTMLResponse)
def index():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = html.replace("/static/app.js", f"/static/app.js?v={_file_hash('app.js')}")
    html = html.replace("/static/style.css", f"/static/style.css?v={_file_hash('style.css')}")
    return HTMLResponse(html, headers=NO_CACHE)


# ---- 参照系 -----------------------------------------------------------------

@app.get("/api/meta")
def meta():
    D = dex()
    snap = load_snapshot()
    return {
        "api_version": API_VERSION,
        "format": D.meta.get("format"), "static_exported_at": D.meta.get("exportedAt"),
        "counts": D.meta.get("counts"),
        "snapshot": None if not snap else {k: snap.get(k) for k in ("source", "season_label", "fetched_at")}
        | {"ranking": len(snap.get("ranking", [])), "detail": len(snap.get("pokemon", {}))},
        "types": [{"id": k, "ja": v} for k, v in D.type_ja.items()],
        "natures": D.natures.rows,
    }


TYPE_ORDER = ["Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting", "Poison", "Ground", "Flying",
              "Psychic", "Bug", "Rock", "Ghost", "Dragon", "Dark", "Steel", "Fairy"]


@app.get("/api/types")
def types():
    """タイプ相性タブ用: タイプ一覧・相性表・使用可能ポケモンのタイプ。"""
    D = dex()
    return {
        "types": [{"id": t, "ja": D.type_ja[t]} for t in TYPE_ORDER if t in D.type_chart],
        "chart": D.type_chart,
        "pokemon": [{"id": p["id"], "ja": p["ja"], "types": p["types"], "isMega": p["isMega"],
                     "abilities": [to_id(a) for a in p["abilities"] if a],
                     "searchable": p.get("searchable", True)} for p in D.pokemon.rows],
        "moves": {m["id"]: [m["type"], m["ja"], m["category"]] for m in D.moves.rows},
    }


@app.get("/api/search")
def search(kind: str, q: str, species: Optional[str] = None, limit: int = 15, include_mega: bool = False):
    """名前検索。メガシンカ後の姿とメガストーンは既定で除く（メガはパーティ側のチェックで指定する）。"""
    D = dex()
    table = {"pokemon": D.pokemon, "moves": D.moves, "items": D.items, "abilities": D.abilities,
             "natures": D.natures}.get(kind)
    if table is None:
        raise HTTPException(400, "kind")
    pred = None
    if kind == "pokemon":
        pred = lambda r: r.get("searchable", True) and (include_mega or not r["isMega"])  # noqa: E731
    elif kind == "items" and not include_mega:
        pred = lambda r: not r.get("megaStone")  # noqa: E731
    elif kind == "moves" and species:
        pool = set(D.pokemon[species]["moves"])
        pred = lambda r: r["id"] in pool  # noqa: E731
    elif kind == "abilities" and species:
        ab = set(D.pokemon[species]["abilities"])
        pred = lambda r: r["en"] in ab  # noqa: E731
    rows = table.search(q, limit, pred)
    return [{"id": r["id"], "ja": r["ja"], "en": r["en"],
             **({"types_ja": r["types_ja"], "isMega": r["isMega"]} if kind == "pokemon" else {}),
             **({"type": r["type"], "category": r["category"], "basePower": r["basePower"]} if kind == "moves" else {})}
            for r in rows]


@app.get("/api/pokemon/{pid}")
def pokemon(pid: str):
    D = dex()
    p = D.pokemon.get(pid)
    if not p:
        raise HTTPException(404)
    snap = load_snapshot()
    usage = (snap or {}).get("pokemon", {}).get(p["id"])
    rank = next((r["rank"] for r in (snap or {}).get("ranking", []) if r.get("id") == p["id"]), None)
    megas = [{"id": m["id"], "ja": m["ja"], "item": m["requiredItem"], "item_ja": D.ja("items", m["requiredItem"])}
             for m in D.mega_of(p["id"])] if not p["isMega"] else []
    weak = {}
    for t in D.type_chart:
        e = 1.0
        for dt in p["types"]:
            e *= D.type_chart[t][dt]
        if e != 1:
            weak.setdefault(str(e), []).append(D.type_ja[t])
    return {
        "id": p["id"], "ja": p["ja"], "en": p["en"], "types": p["types"], "types_ja": p["types_ja"],
        "baseStats": p["baseStats"], "bst": p["bst"], "abilities": [{"id": to_id(a), "en": a, "ja": j} for a, j in
                                                                     zip(p["abilities"], p["abilities_ja"])],
        "weightkg": p["weightkg"], "megas": megas, "speed": speed_variants(p["baseStats"]["spe"]),
        "weakness": weak, "usage": usage, "usage_rank": rank,
        "likely_set": (ls := likely_set(p["id"], snap)).to_dict(), "likely_set_label": ls.label(),
    }


# ---- パーティ・相手 -------------------------------------------------------------

class TeamIn(BaseModel):
    id: Optional[str] = None
    name: str = ""
    archetype: str = "スタンダード"
    members: list[dict]


@app.get("/api/team")
def get_team():
    t = state.load_team()
    D = dex()
    for m in t.get("members", []):
        if m.get("species") and D.pokemon.get(m["species"]):
            b = MonSet.from_dict(m).build()
            m["_stats"] = b.stats()
            m["_errors"] = validate_sp(m.get("sp", {}))
            m["_ja"] = D.pokemon[m["species"]]["ja"]
    t["archetypes"] = state.ARCHETYPES
    return t


@app.put("/api/team")
def put_team(t: TeamIn):
    members = [{k: v for k, v in m.items() if not k.startswith("_")} for m in t.members][:6]
    return state.save_team({"id": t.id, "name": t.name, "archetype": t.archetype, "members": members})


@app.get("/api/teams")
def get_teams():
    D = dex()
    active = state.active_team_id()
    return [{"id": t["id"], "name": t.get("name", ""), "archetype": t.get("archetype"), "active": t["id"] == active,
             "updated_at": t.get("updated_at"),
             "members": [D.pokemon[m["species"]]["ja"] for m in t.get("members", [])
                         if m.get("species") and D.pokemon.get(m["species"])]}
            for t in state.list_teams()]


class NewTeamIn(BaseModel):
    name: str = ""
    copy_from: Optional[str] = None


@app.post("/api/teams")
def post_team(n: NewTeamIn):
    members, arch = [], "スタンダード"
    if n.copy_from:
        src = state.load_team(n.copy_from)
        members, arch = src.get("members", []), src.get("archetype", arch)
        n.name = n.name or f"{src.get('name', '')}のコピー"
    return state.create_team(n.name, members, arch)


@app.put("/api/teams/active/{tid}")
def put_active(tid: str):
    try:
        return state.set_active_team(tid)
    except KeyError:
        raise HTTPException(404)


@app.delete("/api/teams/{tid}")
def delete_team(tid: str):
    state.delete_team(tid)
    return {"ok": True, "active": state.active_team_id()}


class AutofillIn(BaseModel):
    member: dict


@app.post("/api/autofill")
def post_autofill(a: AutofillIn):
    from engine.sets import autofill

    return autofill(a.member)


# ---- 構築診断・調整 --------------------------------------------------------------

@app.get("/api/diagnose")
def get_diagnose(top: int = 30):
    from engine.roles import diagnose

    t = state.load_team()
    sets = state.team_sets()
    if not sets:
        return {"members": [], "findings": [], "archetype": t.get("archetype")}
    return diagnose(sets, t.get("archetype", "スタンダード"), top)


@app.get("/api/threats")
def get_threats(top: int = 30):
    """調整の仮想敵候補: 使用率上位と、その想定型の攻撃技。"""
    D = dex()
    snap = load_snapshot() or {}
    out = []
    for r in snap.get("ranking", [])[:top]:
        if not r.get("id"):
            continue
        ls = likely_set(r["id"], snap)
        out.append({"rank": r["rank"], "id": r["id"], "ja": D.pokemon[r["id"]]["ja"], "set": ls.to_dict(),
                    "set_label": ls.label(),
                    "moves": [{"id": m, "ja": D.moves[m]["ja"], "category": D.moves[m]["category"]}
                              for m in ls.moves if D.moves.get(m) and D.moves[m]["category"] != "Status"]})
    return out


class TuneIn(BaseModel):
    index: int  # 自分のパーティの何体目か
    mode: str  # survive / ko
    opponent: str
    move: str  # survive: 相手の技、ko: 自分の技
    hits: int = 1
    threshold: Optional[float] = None
    worst_case: bool = False
    opponent_set: Optional[dict] = None


@app.post("/api/tune")
def post_tune(t: TuneIn):
    from engine.tuning import ko, survive, worst_case

    members = state.load_team().get("members", [])
    if t.index >= len(members) or not members[t.index].get("species"):
        raise HTTPException(400, "対象のポケモンが未入力")
    me = MonSet.from_dict(members[t.index])
    opp = MonSet.from_dict(t.opponent_set) if t.opponent_set else likely_set(dex().pokemon[t.opponent]["id"])
    if t.worst_case:
        opp = worst_case(opp)
    if t.mode == "survive":
        return survive(me, opp, t.move, t.hits, 0.0 if t.threshold is None else t.threshold)
    return ko(me, opp, t.move, t.hits, 1.0 if t.threshold is None else t.threshold)


class OppIn(BaseModel):
    species: list[str]
    sets: dict = {}
    source: str = "manual"


@app.get("/api/opponent")
def get_opp():
    o = state.load_opponent()
    D = dex()
    o["ja"] = [D.pokemon[s]["ja"] for s in o.get("species", []) if D.pokemon.get(s)]
    o["mtime"] = state.opponent_mtime()
    return o


@app.put("/api/opponent")
def put_opp(o: OppIn):
    return state.save_opponent(o.model_dump())


# ---- 選出予想 -----------------------------------------------------------------

def _run_prediction() -> dict:  # noqa: C901
    my = state.team_sets()
    opp = state.load_opponent()
    if not my or not opp.get("species"):
        raise HTTPException(400, "自分のパーティと相手の6体を入力してください")
    sets = {k: MonSet.from_dict(v) for k, v in (opp.get("sets") or {}).items()}
    with _pred_lock:
        pred = predict(my, opp["species"], sets)
        state.save_prediction(pred)
    return pred


@app.post("/api/predict")
def post_predict(fetch: bool = True):
    """ルールベースの予想を即時に返し、環境データに無い相手がいれば並列で取得→再計算する。"""
    pred = _run_prediction()
    from . import matches

    match = matches.create_or_reuse(state.load_opponent()["species"])
    job = None
    if fetch:
        snap = load_snapshot() or {}
        have = set(snap.get("pokemon", {}).keys())
        missing = [s for s in state.load_opponent()["species"] if s not in have]
        if missing:
            from collectors import pokedb

            def work():
                return pokedb.collect(season=snap.get("season"), only=missing, merge=True)

            job = jobs.submit(f"pokedb:{','.join(missing)}", work, on_done=lambda _: _run_prediction())
    pred = dict(pred, job=job, match_id=match["id"])
    return pred


@app.get("/api/predict")
def get_predict():
    return state.load_prediction() or {}


@app.get("/api/jobs")
def get_jobs():
    return jobs.list_jobs()


@app.post("/api/collect")
def post_collect(top: int = 30):
    from collectors import pokedb

    jid = jobs.submit(f"pokedb:top{top}", lambda: pokedb.collect(top=top), on_done=lambda _: state.render_current())
    return {"job": jid}


# ---- ダメージ計算 ---------------------------------------------------------------

class SideIn(BaseModel):
    species: str
    moves: list[str] = []
    nature: Optional[str] = None
    sp: dict[str, int] = {}
    ability: Optional[str] = None
    item: Optional[str] = None
    boosts: dict[str, int] = {}
    status: Optional[str] = None
    hp_percent: float = 100
    hp: Optional[int] = None  # 残りHPの実数（指定時は hp_percent より優先）
    reflect: bool = False
    light_screen: bool = False
    aurora_veil: bool = False
    mega: bool = False
    supreme_overlord: int = 0


class CalcIn(BaseModel):
    attacker: SideIn
    defender: SideIn
    moves: list[str]
    weather: Optional[str] = None
    terrain: Optional[str] = None
    crit: bool = False
    hits: Optional[int] = None
    bp_override: Optional[int] = None
    log: bool = True


def _side(s: SideIn) -> Side:
    D = dex()
    species = D.pokemon[s.species]["id"]
    ability = s.ability
    if s.mega:
        ms = MonSet(species, s.nature, s.sp, s.ability, s.item)
        mid = battle_species(ms)
        if mid == species:
            megas = D.mega_of(species)
            if megas:
                mid = megas[0]["id"]
        if mid != species:
            species = mid
            ability = D.pokemon[mid]["abilities"][0]
    b = Build(species, s.nature, s.sp, ability, s.item)
    pct = s.hp_percent
    if s.hp is not None:
        mx = b.stats()["hp"]
        pct = 100.0 if s.hp >= mx else max(0.0, s.hp * 100 / mx)
    return Side(b, boosts=s.boosts, status=s.status or None, hp_percent=pct, reflect=s.reflect,
                light_screen=s.light_screen, aurora_veil=s.aurora_veil, supreme_overlord=s.supreme_overlord)


@app.post("/api/calc")
def post_calc(c: CalcIn):
    D = dex()
    a, d = _side(c.attacker), _side(c.defender)
    fld = Field(c.weather or None, c.terrain or None)
    cur_hp = int(d.build.stats()["hp"] * d.hp_percent / 100)
    out = []
    for m in c.moves:
        if not m or not D.moves.get(m):
            continue
        r = calc(a, d, m, fld, Options(crit=c.crit, hits=c.hits, bp_override=c.bp_override))
        out.append(r.to_dict(cur_hp))
    res = {
        "attacker": {"ja": D.pokemon[a.build.species]["ja"], "stats": a.build.stats()},
        "defender": {"ja": D.pokemon[d.build.species]["ja"], "stats": d.build.stats(), "current_hp": cur_hp},
        "results": out,
    }
    if c.log and out:
        best = max(out, key=lambda x: x["max"])
        state.log_calc({"summary": f"{res['attacker']['ja']}の{best['move']} → {res['defender']['ja']}: "
                                   f"{best['min_pct']}〜{best['max_pct']}%（{best['ko']}）",
                        "request": c.model_dump(), "results": out})
    return res


class DuelIn(BaseModel):
    me: SideIn
    opp: SideIn
    my_moves: list[str] = []
    opp_moves: Optional[list[str]] = None  # 省略時は相手の採用率1%以上の技すべて（＋型の技）
    weather: Optional[str] = None
    terrain: Optional[str] = None
    crit: bool = False
    log: bool = True


MIN_MOVE_RATE = 1.0  # 相手の技として出す採用率の下限（%）


def opp_move_list(species: str, set_moves: Optional[list[str]] = None, min_rate: float = MIN_MOVE_RATE) -> list[dict]:
    """相手の技: 採用率 min_rate% 以上の技すべて（変化技を含む、採用率順）。

    環境データ（pokedbの上位10技）に無い型の技は後ろに付ける。環境データが無いポケモンは推定型の技。
    """
    D = dex()
    base = D.pokemon[species]
    sid = to_id(base["baseSpecies"]) if base["isMega"] else base["id"]
    rows = ((load_snapshot() or {}).get("pokemon", {}).get(sid) or {}).get("moves", [])
    out = []
    for r in sorted(rows, key=lambda r: -(r.get("rate") or 0)):
        mv = D.moves.get(r["id"])
        if mv and (r.get("rate") or 0) >= min_rate and all(x["id"] != mv["id"] for x in out):
            out.append({"id": mv["id"], "ja": mv["ja"], "rate": r.get("rate"), "src": "usage"})
    extra = list(set_moves or [])
    if not rows:
        extra += likely_set(sid).moves
    for m in extra:
        mv = D.moves.get(m)
        if mv and all(x["id"] != mv["id"] for x in out):
            out.append({"id": mv["id"], "ja": mv["ja"], "rate": None, "src": "set"})
    return out


@app.post("/api/calc/duel")
def post_duel(c: DuelIn):
    """自分→相手（自分の技4つ）と、相手→自分（相手の採用率上位の技）を同時に計算する。"""
    from engine.stats import effective_speed

    D = dex()
    me, op = _side(c.me), _side(c.opp)
    fld = Field(c.weather or None, c.terrain or None)

    def cur_hp(side: Side, sin: SideIn) -> int:
        mx = side.build.stats()["hp"]
        return max(0, min(mx, sin.hp)) if sin.hp is not None else int(mx * side.hp_percent / 100)

    def run(att, dfd, moves, dfd_in):
        cur = cur_hp(dfd, dfd_in)
        out = []
        for m in moves:
            if m and D.moves.get(m):
                r = calc(att, dfd, m, fld, Options(crit=c.crit)).to_dict(cur)
                if r["category"] == "Status":
                    r["effect"] = describe_effect(att, dfd, m, fld)
                out.append(r)
        return out, cur

    to_opp, opp_hp = run(me, op, c.my_moves, c.opp)
    omoves = opp_move_list(op.build.species, c.opp.moves if hasattr(c.opp, "moves") else None) \
        if c.opp_moves is None else [{"id": m, "ja": D.ja("moves", m), "rate": None, "src": "set"} for m in c.opp_moves]
    to_me, my_hp = run(op, me, [m["id"] for m in omoves], c.me)
    for r, m in zip(to_me, omoves):
        r["rate"], r["src"] = m["rate"], m["src"]

    def spd(side: Side, item):
        return effective_speed(side.build.stats()["spe"], side.boosts.get("spe", 0),
                               scarf=to_id(item or "") == "choicescarf", paralysis=side.status == "par")

    res = {
        "me": {"ja": D.pokemon[me.build.species]["ja"], "stats": me.build.stats(), "current_hp": my_hp,
               "speed": spd(me, c.me.item)},
        "opp": {"ja": D.pokemon[op.build.species]["ja"], "stats": op.build.stats(), "current_hp": opp_hp,
                "speed": spd(op, c.opp.item)},
        "to_opp": to_opp, "to_me": to_me,
    }
    if c.log and (to_opp or to_me):
        parts = []
        if to_opp:
            b = max(to_opp, key=lambda x: x["max"])
            parts.append(f"{res['me']['ja']}の{b['move']}→{res['opp']['ja']} {b['min_pct']}〜{b['max_pct']}%（{b['ko']}）")
        if to_me:
            b = max(to_me, key=lambda x: x["max"])  # 変化技は0なので攻撃技が選ばれる
            parts.append(f"{res['opp']['ja']}の{b['move']}→{res['me']['ja']} {b['min_pct']}〜{b['max_pct']}%（{b['ko']}）")
        state.log_calc({"summary": " ／ ".join(parts), "request": c.model_dump()})
    return res


@app.get("/api/speed")
def speed(ids: str):
    """相手候補の素早さ帯と、自分のパーティの実数値を並べる。"""
    D = dex()
    rows = []
    for m in state.team_sets():
        b = m.build()
        rows.append({"side": "me", "ja": D.pokemon[m.species]["ja"], "label": "自分", "speed": b.stats()["spe"],
                     "scarf": to_id(m.item or "") == "choicescarf"})
        ms = battle_species(m)
        if ms != D.pokemon[m.species]["id"]:
            b2 = Build(ms, m.nature, m.sp)
            rows.append({"side": "me", "ja": D.pokemon[ms]["ja"], "label": "自分(メガ)", "speed": b2.stats()["spe"]})
    for pid in [x for x in ids.split(",") if x]:
        p = D.pokemon.get(pid)
        if not p:
            continue
        for label, v in speed_variants(p["baseStats"]["spe"]).items():
            if label in ("最速", "準速"):
                rows.append({"side": "opp", "ja": p["ja"], "label": label, "speed": v})
        rows.append({"side": "opp", "ja": p["ja"], "label": "最速スカーフ",
                     "speed": speed_variants(p["baseStats"]["spe"])["最速"] * 3 // 2})
        for mg in D.mega_of(p["id"]):
            rows.append({"side": "opp", "ja": mg["ja"], "label": "最速",
                         "speed": speed_variants(mg["baseStats"]["spe"])["最速"]})
    rows.sort(key=lambda r: r["speed"], reverse=True)
    return rows


# ---- 対戦記録（6体の組み合わせ）と対戦モード ---------------------------------------------

@app.get("/api/matches")
def get_matches(limit: int = 200):
    from . import matches

    D = dex()
    cur = matches.current_id()
    out = []
    for m in matches.list_matches()[:limit]:
        d = m.get("detail") or {}
        out.append({"id": m["id"], "created_at": m["created_at"], "opp": m["opp"],
                    "opp_ja": [D.pokemon[s]["ja"] for s in m["opp"] if D.pokemon.get(s)],
                    "team_name": m.get("team_name"), "current": m["id"] == cur, "has_detail": bool(d),
                    "records": len(d.get("records", [])), "result": d.get("result"),
                    "opp_picks_ja": [D.pokemon[s]["ja"] for s in d.get("opp_picks", []) if D.pokemon.get(s)]})
    return out


@app.post("/api/matches/{mid}/load")
def load_match(mid: str):
    """過去の6体を呼び出す: 相手の6体に入れ、この対戦を現在の対戦にする。"""
    from . import matches

    m = matches.get(mid)
    if not m:
        raise HTTPException(404)
    matches.set_current(mid)
    state.save_opponent({"species": m["opp"], "source": "history"})
    return {"ok": True}


@app.delete("/api/matches/{mid}")
def delete_match(mid: str):
    from . import matches

    matches.delete(mid)
    return {"ok": True}


def _bv() -> dict:
    from . import battle

    v = battle.view()
    try:
        battle.write_state(v)
    except Exception:  # noqa: BLE001
        pass
    return v


@app.get("/api/battle")
def get_battle():
    return _bv()


class PicksIn(BaseModel):
    my_picks: Optional[list[int]] = None
    opp_picks: Optional[list[str]] = None
    result: Optional[str] = None
    memo: Optional[str] = None


def _current_match_id() -> str:
    from . import matches

    mid = matches.current_id()
    if not mid:
        raise HTTPException(400, "対戦がない（選出タブで相手の6体を入れて選出予想を押す）")
    return mid


@app.put("/api/battle")
def put_battle(p: PicksIn):
    from . import matches

    mid = _current_match_id()
    matches.update_detail(mid, my_picks=(p.my_picks or [])[:3] if p.my_picks is not None else None,
                          opp_picks=(p.opp_picks or [])[:3] if p.opp_picks is not None else None,
                          result=p.result, memo=p.memo)
    return _bv()


@app.post("/api/battle/resnapshot")
def battle_resnapshot():
    from . import matches

    matches.resnapshot_team(_current_match_id())
    return _bv()


class LiveIn(BaseModel):
    my: dict = {}
    opp: dict = {}
    field: dict = {}
    active: dict = {}


@app.put("/api/battle/live")
def put_live(p: LiveIn):
    from . import matches

    matches.update_live(_current_match_id(), p.model_dump())
    return _bv()


class RecordIn(BaseModel):
    kind: str
    opp: str
    my_index: Optional[int] = None
    move: Optional[str] = None
    before: Optional[float] = None
    after: Optional[float] = None
    cond: dict = {}
    reveal_type: Optional[str] = None
    reveal_value: Optional[str] = None


def _record_dict(r: RecordIn, mid: str) -> dict:
    from . import matches

    D = dex()
    m = matches.ensure_detail(matches.get(mid))
    if r.kind not in ("taken", "dealt", "reveal"):
        raise HTTPException(400, "kind")
    if not D.pokemon.get(r.opp):
        raise HTTPException(400, "相手のポケモン")
    d = r.model_dump()
    d["opp"] = D.pokemon[r.opp]["id"]
    if r.kind in ("taken", "dealt"):
        team = m["detail"]["my_team"]
        if r.my_index is None or r.my_index >= len(team):
            raise HTTPException(400, "自分のポケモン")
        if not r.move or not D.moves.get(r.move):
            raise HTTPException(400, "技")
        if r.after is None:
            raise HTTPException(400, "受けた後のHP／当てた後の%")
        d["move"] = D.moves[r.move]["id"]
        d["my"] = team[r.my_index]
        if r.kind == "taken":
            d["before"] = int(r.before) if r.before is not None else None
            d["after"] = int(r.after)
        d["cond"] = {k: v for k, v in (r.cond or {}).items() if v not in ("", None)}
    else:
        if r.reveal_type not in ("item", "move", "ability") or not r.reveal_value:
            raise HTTPException(400, "判明した内容")
    return d


@app.post("/api/battle/records")
def add_battle_record(r: RecordIn):
    from . import matches

    mid = _current_match_id()
    rec = _record_dict(r, mid)
    matches.add_record(mid, rec)
    matches.apply_record_effect(mid, rec)
    return _bv()


@app.put("/api/battle/records/{rid}")
def edit_battle_record(rid: str, r: RecordIn):
    from . import matches

    mid = _current_match_id()
    try:
        matches.update_record(mid, rid, _record_dict(r, mid))
    except KeyError:
        raise HTTPException(404)
    return _bv()


@app.delete("/api/battle/records/{rid}")
def delete_battle_record(rid: str):
    from . import matches

    matches.delete_record(_current_match_id(), rid)
    return _bv()


@app.get("/api/current.md", response_class=PlainTextResponse)
def current_md():
    return state.render_current()
