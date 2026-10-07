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
    if c.get("miss"):
        parts.append("不発・効果なし")
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
    if (r.get("cond") or {}).get("miss"):
        return f"{opp}の{mv} → {my}" if r["kind"] == "taken" else f"{my}の{mv} → {opp}"
    if r["kind"] == "taken":
        b, a = r.get("before"), r.get("after")
        val = f"HP {b}→{a}（{(b or 0) - (a or 0)}ダメージ）" if b is not None else f"残りHP {a}"
        text = f"{opp}の{mv} → {my}: {val}"
    else:
        b = r.get("before") if r.get("before") is not None else 100
        val = f"{b:g}%→{r.get('after'):g}%（{b - r.get('after'):g}%）"
        text = f"{my}の{mv} → {opp}: {val}"
    return text + (f"［{c}］" if c else "")


STATUS_JA = {"none": "なし", "brn": "やけど", "par": "まひ", "psn": "どく", "tox": "もうどく", "slp": "ねむり", "frz": "こおり"}
SCREEN_JA = {"none": "なし", "reflect": "リフレクター", "lightscreen": "ひかりのかべ", "both": "両方・オーロラベール"}
MEGA_JA = {"auto": "未確定", "yes": "した", "no": "しなかった"}
RANK_JA = {"atk": "A", "def": "B", "spa": "C", "spd": "D", "spe": "S"}
HAZARD_DEFAULT = {"rocks": False, "spikes": 0, "tspikes": 0, "web": False}


def _hazard_text(h: dict) -> str:
    h = {**HAZARD_DEFAULT, **(h or {})}
    parts = (["ステルスロック"] if h["rocks"] else []) + ([f"まきびし{h['spikes']}層"] if h["spikes"] else []) + \
        ([f"どくびし{h['tspikes']}層"] if h["tspikes"] else []) + (["ねばねばネット"] if h["web"] else [])
    return "・".join(parts) or "なし"


def diff_live(m: dict, before: dict, after: dict) -> list[dict]:
    """現在の対面の変化を {who, item, before, after} の一覧にする。"""
    D = dex()
    team = (m.get("detail") or {}).get("my_team", [])
    out = []

    def add(who, item, b, a):
        if b != a:
            out.append({"who": who, "item": item, "before": b, "after": a})

    for side in ("my", "opp"):
        for key, a in after[side].items():
            b = before[side].get(key)
            if b is None:
                continue
            if side == "my":
                sp = team[int(key)]
                who = "自分 " + D.pokemon[sp["species"]]["ja"]
                mx = MonSet.from_dict(sp).build().stats()["hp"]
                hp = lambda v: str(mx if v is None else v)
            else:
                who = "相手 " + D.pokemon[key]["ja"]
                hp = lambda v: f"{(100 if v is None else v):g}%"
            add(who, "HP", hp(b.get("hp")), hp(a.get("hp")))
            add(who, "状態異常", STATUS_JA.get(b.get("status"), b.get("status")), STATUS_JA.get(a.get("status"), a.get("status")))
            for k, ja in RANK_JA.items():
                x, y = (b.get("boosts") or {}).get(k, 0), (a.get("boosts") or {}).get(k, 0)
                add(who, f"{ja}ランク", f"{x:+d}" if x else "0", f"{y:+d}" if y else "0")
            if side == "opp":
                add(who, "メガシンカ", MEGA_JA.get(b.get("mega_state"), "未確定"), MEGA_JA.get(a.get("mega_state"), "未確定"))
    fb, fa = before["field"], after["field"]
    for k, ja, tab in (("weather", "天候", WEATHER_JA), ("terrain", "フィールド", TERRAIN_JA)):
        add("場", ja, tab.get(fb.get(k), "なし"), tab.get(fa.get(k), "なし"))
    for k, ja in (("my_screen", "自分側の壁"), ("opp_screen", "相手側の壁")):
        add("場", ja, SCREEN_JA.get(fb.get(k), "なし"), SCREEN_JA.get(fa.get(k), "なし"))
    for k, ja in (("my_hazards", "自分側の設置"), ("opp_hazards", "相手側の設置")):
        add("場", ja, _hazard_text(fb.get(k)), _hazard_text(fa.get(k)))
    ab, aa = before["active"], after["active"]
    if ab["my"] != aa["my"] and aa["my"] is not None:
        nm = lambda i: D.pokemon[team[int(i)]["species"]]["ja"] if i is not None else "なし"
        add("対面", "自分の場", nm(ab["my"]), nm(aa["my"]))
    if ab["opp"] != aa["opp"] and aa["opp"] is not None:
        nm = lambda s: D.pokemon[s]["ja"] if s else "なし"
        add("対面", "相手の場", nm(ab["opp"]), nm(aa["opp"]))
    return out


def log_summary(entry: dict) -> str:
    text = "、".join(f"{c['who']} {c['item']} {c['before']}→{c['after']}" for c in entry.get("changes", []))
    return (f"［{entry['reason']}］" if entry.get("reason") else "") + text


def hazard_effect(side: str, key: str, mid: Optional[str] = None) -> dict:
    """設置技（ステルスロック・まきびし・どくびし・ねばねばネット）がある場に、ポケモンが出てきたときの変化。"""
    from engine.damage import type_effectiveness
    from engine.data import to_id

    D = dex()
    v = view(mid)
    out = {"lines": [], "hp": None, "status": None, "boosts": {}, "field": {}, "name": ""}
    if not v.get("match") or not v.get("live"):
        return out
    lv = v["live"]
    hz = {**HAZARD_DEFAULT, **(lv["field"].get(f"{side}_hazards") or {})}
    if side == "my":
        x = next((q for q in v["mine"] if str(q["index"]) == str(key)), None)
        if not x:
            return out
        types = D.pokemon[x["set"]["species"]]["types"]
        item, ability, name = to_id(x["set"].get("item") or ""), to_id(x["set"].get("ability") or x["ability_id"]), x["ja"]
        mx = x["stats"]["hp"]
        cur = lv["my"][str(key)].get("hp")
        cur = mx if cur is None else cur
    else:
        o = next((q for q in v["opp_builds"] if q["base_species"] == key), None)
        if not o:
            return out
        types = D.pokemon[o["battle_species"]]["types"]
        item = to_id(o["item"].get("id") or "") if o["item"].get("src") == "confirmed" else ""
        ab = o["ability"]
        abs_ = [to_id(a) for a in D.pokemon[o["battle_species"]]["abilities"] if a]
        ability = to_id(ab.get("id") or "") if ab.get("src") == "confirmed" else (abs_[0] if len(abs_) == 1 else "")
        name, mx = o.get("battle_ja") or o["ja"], o["stats"]["hp"]
        pc = lv["opp"][key].get("hp")
        cur = 100 if pc is None else pc
    out["name"] = name
    if (cur <= 0) or not (hz["rocks"] or hz["spikes"] or hz["tspikes"] or hz["web"]):
        return out
    if item == "heavydutyboots":
        out["lines"].append("あつぞこブーツで受けない")
        return out
    grounded = "Flying" not in types and ability != "levitate" and item != "airballoon"
    hits = []  # (理由, ダメージ)
    if ability != "magicguard":
        if hz["rocks"]:
            hits.append(("ステルスロック", max(1, int(mx * type_effectiveness("Rock", types) / 8))))
        if hz["spikes"] and grounded:
            hits.append((f"まきびし{hz['spikes']}層", max(1, mx // {1: 8, 2: 6, 3: 4}[hz["spikes"]])))
    dmg = sum(d for _, d in hits)
    for label, d in hits:
        out["lines"].append(f"{label} -{d}" if side == "my" else f"{label} -{round(d / mx * 100, 1):g}%")
    if hz["tspikes"] and grounded:
        if "Poison" in types:
            out["field"][f"{side}_hazards"] = {**hz, "tspikes": 0}
            out["lines"].append("どくびしを取り除く")
        elif "Steel" not in types and ability not in ("immunity", "pastelveil"):
            out["status"] = "tox" if hz["tspikes"] >= 2 else "psn"
            out["lines"].append("もうどく" if hz["tspikes"] >= 2 else "どく")
    if hz["web"] and grounded and ability not in ("clearbody", "whitesmoke", "fullmetalbody"):
        out["boosts"] = {"spe": -1}
        out["lines"].append("すばやさ -1")
    if dmg:
        out["hp"] = max(0, cur - dmg) if side == "my" else max(0, round(cur - dmg / mx * 100, 1))
    return out


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
    for r in sorted(detail.get("records", []) + detail.get("logs", []), key=lambda r: r.get("at") or ""):
        if r.get("kind") == "log":
            recs_out.append(dict(r, summary=log_summary(r), kind_ja="ログ", kind_short="ログ", feasible=None, chip_move=None))
            continue
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
    """state/battle.md: 対戦モードの現在（Claudeがチャットから読む用。ローカル版だけ）。"""
    from . import storage

    if not storage.current().local:
        return
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
