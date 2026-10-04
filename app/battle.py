"""対戦モードの画面データ（選出した3体どうしの対面・素早さ・相手の型の確定/推定）。"""
from __future__ import annotations

from typing import Optional

from engine.data import STAT_JA, dex
from engine.infer import Record, opponent_build
from engine.matchup import as_side, duel
from engine.sets import MonSet, load_snapshot
from engine.stats import speed_variants

from . import matches, state

KIND_JA = {"taken": "被ダメ", "dealt": "与ダメ", "reveal": "判明"}
KIND_SHORT = {"taken": "被", "dealt": "与", "item": "もち", "move": "技", "ability": "特性"}
REVEAL_JA = {"item": "持ち物", "move": "技", "ability": "特性"}
WEATHER_JA = {"sun": "晴れ", "rain": "雨", "sand": "砂嵐", "snow": "雪"}
TERRAIN_JA = {"electric": "エレキ", "grassy": "グラス", "psychic": "サイコ", "misty": "ミスト"}


def _cond_text(c: dict) -> str:
    parts = []
    if c.get("weather") and c["weather"] != "none":
        parts.append(WEATHER_JA.get(c["weather"], c["weather"]))
    if c.get("terrain") and c["terrain"] != "none":
        parts.append(TERRAIN_JA.get(c["terrain"], c["terrain"]) + "F")
    if c.get("crit"):
        parts.append("急所")
    if c.get("atk_boost"):
        parts.append(f"攻撃側{c['atk_boost']:+d}")
    if c.get("def_boost"):
        parts.append(f"防御側{c['def_boost']:+d}")
    stj = {"brn": "やけど", "par": "まひ", "psn": "どく", "tox": "もうどく", "slp": "ねむり", "frz": "こおり"}
    if c.get("atk_status") and c["atk_status"] != "none":
        parts.append("攻撃側" + stj.get(c["atk_status"], c["atk_status"]))
    elif c.get("burn"):
        parts.append("やけど")
    if c.get("def_status") and c["def_status"] != "none":
        parts.append("防御側" + stj.get(c["def_status"], c["def_status"]))
    if c.get("screen"):
        parts.append("壁")
    if c.get("opp_mega"):
        parts.append("相手メガ後")
    if c.get("hits"):
        parts.append(f"{c['hits']}回")
    if c.get("ko"):
        parts.append("倒れた")
    return "・".join(parts)


def record_summary(r: dict) -> str:
    D = dex()
    opp = D.pokemon[r["opp"]]["ja"] if D.pokemon.get(r.get("opp") or "") else r.get("opp")
    if r["kind"] == "reveal":
        kind = r.get("reveal_type")
        table = {"item": "items", "move": "moves", "ability": "abilities"}.get(kind, "moves")
        return f"{opp}の{REVEAL_JA.get(kind, kind)}: {D.ja(table, r.get('reveal_value'))}"
    my = D.pokemon[r["my"]["species"]]["ja"] if r.get("my") else "?"
    mv = D.ja("moves", r.get("move"))
    c = _cond_text(r.get("cond") or {})
    if r["kind"] == "taken":
        b, a = r.get("before"), r.get("after")
        val = f"HP {b}→{a}（{(b or 0) - (a or 0)}ダメージ）" if b is not None else f"残りHP {a}"
        text = f"{opp}の{mv} → {my}: {val}"
    else:
        b = r.get("before") if r.get("before") is not None else 100
        val = f"{b:g}%→{r.get('after'):g}%（{b - r.get('after'):g}%）"
        text = f"{my}の{mv} → {opp}: {val}"
    return text + (f"［{c}］" if c else "")


def view(mid: Optional[str] = None) -> dict:
    D = dex()
    m = matches.get(mid)
    if not m:
        return {"match": None}
    snap = load_snapshot()
    detail = m.get("detail") or {}
    my_team = detail.get("my_team") or [x for x in state.load_team().get("members", []) if x.get("species")]
    my_picks = [i for i in detail.get("my_picks", []) if i < len(my_team)]
    opp_picks = [s for s in detail.get("opp_picks", []) if s in m["opp"]]
    records = [Record.from_dict(r) for r in detail.get("records", []) if r.get("kind")]

    live = matches.live_state(m) if m.get("detail") else None
    # メガシンカ: した(True)/しなかった(False)/未確定(None)。誰かがメガシンカしたら他はしない
    states = {s: (((live or {}).get("opp") or {}).get(s) or {}).get("mega_state", "auto") for s in m["opp"]}
    someone = any(v == "yes" for v in states.values())
    mega_hint = {s: True if v == "yes" else False if (v == "no" or someone) else None for s, v in states.items()}
    builds = {}
    for s in opp_picks or []:
        builds[s] = opponent_build(s, records, snap, mega_hint.get(s))
    # 選出していない相手でも記録があれば推定する
    for r in records:
        if r.opp not in builds and r.opp in m["opp"]:
            builds[r.opp] = opponent_build(r.opp, records, snap, mega_hint.get(r.opp))

    my_sets = [MonSet.from_dict(x) for x in my_team]
    mine = []
    for i in my_picks:
        s = my_sets[i]
        side = as_side(s)
        mine.append({"index": i, "ja": D.pokemon[s.species]["ja"], "battle_ja": D.pokemon[side.build.species]["ja"],
                     "battle_species": side.build.species,
                     "set": s.to_dict(), "label": s.label(), "stats": side.build.stats(),
                     "item_ja": D.ja("items", s.item) if s.item else "",
                     "ability_ja": D.ja("abilities", side.build.ability) if side.build.ability else "",
                     "ability_id": side.build.ability or "",
                     "nature_ja": D.ja("natures", s.nature) if s.nature else "",
                     "sp": {k: v for k, v in (s.sp or {}).items() if v},
                     "moves": [{"id": mv, "ja": D.ja("moves", mv)} for mv in s.moves]})

    matrix = []
    for i in my_picks:
        row = []
        for sp in opp_picks:
            o = MonSet.from_dict(builds[sp]["set"])
            d = duel(my_sets[i], o)
            ab, bb = d["a_best"], d["b_best"]
            row.append({"score": d["score"], "a_hits": d["a_hits"], "b_hits": d["b_hits"],
                        "a_move_id": ab["move_id"] if ab else None, "b_move_id": bb["move_id"] if bb else None,
                        "a_move": d["a_best"]["move"] if d["a_best"] else None,
                        "a_pct": [d["a_best"]["min_pct"], d["a_best"]["max_pct"]] if d["a_best"] else None,
                        "b_move": d["b_best"]["move"] if d["b_best"] else None,
                        "b_pct": [d["b_best"]["min_pct"], d["b_best"]["max_pct"]] if d["b_best"] else None,
                        "a_speed": d["a_speed"], "b_speed": d["b_speed"]})
        matrix.append(row)

    speed = []
    from engine.matchup import speed_of

    for x, i in zip(mine, my_picks):
        scarf = (my_sets[i].item or "").lower().replace(" ", "") == "choicescarf"
        speed.append({"side": "me", "ja": x["battle_ja"], "label": "自分" + ("（スカーフ込み）" if scarf else ""),
                      "speed": speed_of(my_sets[i])})
    for sp in opp_picks:
        b = builds[sp]
        rng = b["stats_range"].get("spe")
        base_spe = D.pokemon[b["battle_species"]]["baseStats"]["spe"]
        v = speed_variants(base_spe)
        speed.append({"side": "opp", "ja": b["battle_ja"], "label": "推定（" + ("逆算" if rng else "採用率") + "）",
                      "speed": b["stats"]["spe"]})
        speed.append({"side": "opp", "ja": b["battle_ja"], "label": "最速", "speed": v["最速"]})
        if b["item"]["src"] != "confirmed" and b["battle_species"] == b["species"]:
            speed.append({"side": "opp", "ja": b["battle_ja"], "label": "最速スカーフ", "speed": v["最速"] * 3 // 2})
    speed.sort(key=lambda r: r["speed"], reverse=True)

    recs_out = []
    per_count = {}
    for b in builds.values():
        for p in b["inference"].get("per_record", []):
            per_count[p["id"]] = p["count"]
    for r in detail.get("records", []):
        recs_out.append(dict(r, summary=record_summary(r), feasible=per_count.get(r["id"]),
                             kind_ja=KIND_JA.get(r["kind"], r["kind"]),
                             kind_short=KIND_SHORT.get(r.get("reveal_type") if r["kind"] == "reveal" else r["kind"], "判明"),
                             chip_move=r.get("move") if r["kind"] != "reveal" else
                             (r.get("reveal_value") if r.get("reveal_type") == "move" else None)))

    return {
        "match": {k: m.get(k) for k in ("id", "created_at", "opp", "team_name")} |
        {"opp_ja": [D.pokemon[s]["ja"] for s in m["opp"]], "has_detail": bool(m.get("detail"))},
        "my_team": [{"index": i, "ja": D.pokemon[s.species]["ja"], "species": s.species,
                     "moves": [{"id": mv, "ja": D.ja("moves", mv),
                                "category": (D.moves.get(mv) or {}).get("category")} for mv in s.moves],
                     "hp": as_side(s).build.stats()["hp"]} for i, s in enumerate(my_sets)],
        "my_team_name": detail.get("my_team_name") or m.get("team_name"),
        "my_picks": my_picks, "opp_picks": opp_picks, "mine": mine,
        "opp_builds": [builds[s] for s in opp_picks], "other_builds": [b for s, b in builds.items() if s not in opp_picks],
        "matrix": matrix, "speed": speed, "records": recs_out,
        "result": detail.get("result"), "memo": detail.get("memo", ""),
        "live": live,
        "opp_has_mega": {s: bool(D.mega_of(s)) for s in m["opp"]},
        "stat_ja": STAT_JA,
    }


def write_state(v: dict) -> None:
    """state/battle.md: 対戦モードの現在（Claudeがチャットから読む用）。"""
    L = ["# 対戦モード", ""]
    m = v.get("match")
    if not m:
        L.append("- 対戦なし")
    else:
        L += [f"- 対戦: {m['created_at']}（id {m['id']}）", f"- 相手の6体: {'・'.join(m['opp_ja'])}",
              f"- 自分のパーティ: {v.get('my_team_name')}", ""]
        L.append("## 自分の選出")
        for x in v["mine"]:
            L.append(f"- {x['label']}")
        L += ["", "## 相手の選出（[確定]/[逆算]/[採用率]/[推定]）"]
        tag = {"confirmed": "確定", "inferred": "逆算", "usage": "採用率", "estimate": "推定", "battle": "推定"}
        for o in v["opp_builds"] + v.get("other_builds", []):
            sp = " ".join(f"{STAT_JA[k]}{val}" for k, val in o["sp"].items() if val)
            moves = "／".join(f"{mv['ja']}[{tag.get(mv['src'], mv['src'])}]" for mv in o["moves"])
            L.append(f"- {o['battle_ja']}: 持ち物 {o['item']['ja']}[{tag.get(o['item']['src'])}]・特性 {o['ability']['ja']}"
                     f"[{tag.get(o['ability']['src'])}]・性格 {o['nature']['ja']}[{tag.get(o['nature']['src'])}]・{sp}・{moves}")
            inf = o.get("inference") or {}
            if inf.get("records"):
                rng = " ".join(f"{STAT_JA[k]}{a}〜{b}" for k, (a, b) in inf.get("sp_ranges", {}).items())
                L.append(f"  - 逆算: 記録{inf['records']}件、候補{inf['candidates']}通り、能力ポイント範囲 {rng}")
        L += ["", "## 記録"]
        for i, r in enumerate(v["records"], 1):
            L.append(f"{i}. [{r['kind_ja']}] {r['summary']}" + (f"（候補{r['feasible']}）" if r.get("feasible") is not None else ""))
        if v.get("result"):
            L.append(f"\n結果: {'勝ち' if v['result'] == 'win' else '負け'}")
    state.STATE.mkdir(parents=True, exist_ok=True)
    (state.STATE / "battle.md").write_text("\n".join(L) + "\n", encoding="utf-8")
