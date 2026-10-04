"""役割タグの自動付与と構築診断（ルールベース）。

役割の定義は knowledge/battle_concepts.md の「役割タグ」と対応させる。
判定は型（技・持ち物・特性・能力ポイント）と実数値から行い、種族だけでは決めない。
"""
from __future__ import annotations

from typing import Optional

from .data import dex, to_id
from .matchup import as_side, battle_species, duel
from .sets import MonSet, likely_set, load_snapshot

ROLE_JA = {
    "ace": "エース", "breaker": "崩し", "faceoff": "対面駒", "cushion": "クッション",
    "wall_phys": "物理受け", "wall_spec": "特殊受け", "setter": "起点作り", "stopper": "ストッパー",
    "pivot": "サイクル要員", "weather": "天候・フィールド始動",
}

SETUP_MOVES = {
    "swordsdance", "dragondance", "nastyplot", "calmmind", "bulkup", "quiverdance", "shellsmash", "shiftgear",
    "bellydrum", "agility", "rockpolish", "coil", "curse", "tailglow", "victorydance", "filletaway",
    "clangoroussoul", "noretreat", "workup", "growth", "geomancy", "irondefense", "cosmicpower", "amnesia",
    "tidyup", "trailblaze", "flamecharge", "poweruppunch", "meteorbeam",
}
SETTER_MOVES = {
    "stealthrock", "spikes", "toxicspikes", "stickyweb", "reflect", "lightscreen", "auroraveil", "yawn",
    "trickroom", "tailwind", "memento", "healingwish", "lunardance", "spore", "sleeppowder", "hypnosis",
    "thunderwave", "willowisp", "encore", "taunt", "partingshot", "shedtail",
}
PIVOT_MOVES = {"uturn", "voltswitch", "flipturn", "partingshot", "teleport", "chillyreception", "shedtail"}
RECOVERY_MOVES = {
    "recover", "roost", "slackoff", "softboiled", "moonlight", "morningsun", "synthesis", "shoreup",
    "strengthsap", "milkdrink", "wish", "rest", "painsplit", "junglehealing", "lifedew", "leechseed",
}
WEATHER_ABILITIES = {"drought", "drizzle", "sandstream", "snowwarning", "electricsurge", "grassysurge",
                     "psychicsurge", "mistysurge", "megasol"}
WEATHER_MOVES = {"sunnyday", "raindance", "sandstorm", "snowscape", "electricterrain", "grassyterrain",
                 "psychicterrain", "mistyterrain"}
POWER_ITEMS = {"lifeorb", "expertbelt", "choiceband", "choicespecs"}
SASH_LIKE_ABILITIES = {"sturdy", "multiscale", "shadowshield", "disguise"}


def tag_roles(m: MonSet) -> list[dict]:
    """1体の役割タグ。[{tag, ja, reason}]。"""
    D = dex()
    side = as_side(m)
    sp = D.pokemon[side.build.species]
    st = side.build.stats()
    moves = [D.moves.get(x) for x in m.moves]
    moves = [x for x in moves if x]
    ids = {x["id"] for x in moves}
    item = to_id(m.item or "")
    ability = to_id(side.build.ability or "")
    alloc = m.sp or {}
    tags: list[dict] = []

    def add(tag, reason):
        if not any(t["tag"] == tag for t in tags):
            tags.append({"tag": tag, "ja": ROLE_JA[tag], "reason": reason})

    setup = ids & SETUP_MOVES
    if setup:
        add("ace", "積み技: " + "・".join(D.ja("moves", x) for x in setup))
    setter = ids & SETTER_MOVES
    if setter or item == "lightclay":
        add("setter", "起点作り技: " + "・".join(D.ja("moves", x) for x in setter) if setter else "ひかりのねんど")
    pivot = ids & PIVOT_MOVES
    if pivot or ability == "regenerator":
        add("pivot", "・".join(D.ja("moves", x) for x in pivot) if pivot else "さいせいりょく")
    prio = [x for x in moves if x["priority"] > 0 and x["category"] != "Status"]
    if prio or item == "choicescarf":
        add("stopper", "先制技: " + "・".join(x["ja"] for x in prio) if prio else "こだわりスカーフ")
    if item == "focussash" or ability in SASH_LIKE_ABILITIES:
        add("faceoff", "きあいのタスキ" if item == "focussash" else f"特性 {D.ja('abilities', side.build.ability)}")
    if ability in WEATHER_ABILITIES or ids & WEATHER_MOVES:
        add("weather", f"特性 {D.ja('abilities', side.build.ability)}" if ability in WEATHER_ABILITIES else "天候・フィールド技")

    phys_bulk = st["hp"] * st["def"]
    spec_bulk = st["hp"] * st["spd"]
    offense = max(st["atk"], st["spa"])
    recovery = bool(ids & RECOVERY_MOVES) or item in {"leftovers", "sitrusberry"} or ability == "regenerator"
    invest_b = alloc.get("hp", 0) + alloc.get("def", 0)
    invest_d = alloc.get("hp", 0) + alloc.get("spd", 0)
    if recovery and (phys_bulk >= 26000 or invest_b >= 50):
        add("wall_phys", f"物理耐久指数 {phys_bulk}・回復手段あり")
    if recovery and (spec_bulk >= 26000 or invest_d >= 50):
        add("wall_spec", f"特殊耐久指数 {spec_bulk}・回復手段あり")
    if not any(t["tag"].startswith("wall") for t in tags) and (invest_b >= 40 or invest_d >= 40 or
                                                              min(phys_bulk, spec_bulk) >= 24000):
        add("cushion", f"耐久指数 H×B {phys_bulk} / H×D {spec_bulk}")
    atk_invest = max(alloc.get("atk", 0), alloc.get("spa", 0))
    if not setup and (item in POWER_ITEMS or side.build.species != D.pokemon[m.species]["id"]) and atk_invest >= 28:
        add("breaker", f"火力 {offense}（{D.ja('items', m.item) or ''}）")
    if not tags or (atk_invest >= 28 and not setup and not any(t["tag"] in ("breaker", "faceoff") for t in tags)
                    and alloc.get("spe", 0) >= 28):
        add("faceoff", f"攻撃・素早さ特化（{sp['ja']}）")
    return tags


# 構築の型ごとに必要な役割（いずれかのタグを満たす駒の数）
REQUIREMENTS = {
    "対面": [({"faceoff", "stopper"}, 2, "対面駒・ストッパー")],
    "サイクル": [({"pivot"}, 1, "サイクル要員"), ({"cushion", "wall_phys", "wall_spec"}, 2, "クッション・受け")],
    "展開": [({"setter"}, 1, "起点作り"), ({"ace"}, 1, "エース")],
    "スタンダード": [({"ace", "breaker"}, 1, "エース・崩し"), ({"cushion", "wall_phys", "wall_spec", "pivot"}, 1,
                                                        "クッション・受け・サイクル要員"),
                  ({"stopper", "faceoff"}, 1, "ストッパー・対面駒")],
    "受けループ": [({"wall_phys"}, 1, "物理受け"), ({"wall_spec"}, 1, "特殊受け")],
}


def type_overlap(team: list[MonSet]) -> list[dict]:
    """攻撃タイプごとに、弱点・半減以下の数。"""
    D = dex()
    rows = []
    for t in D.type_chart:
        weak, resist, names = 0, 0, []
        for m in team:
            side = as_side(m)
            p = D.pokemon[side.build.species]
            e = 1.0
            for dt in p["types"]:
                e *= D.type_chart[t][dt]
            ab = to_id(side.build.ability or "")
            if (t == "Ground" and (ab in {"levitate", "eelevate"} or to_id(m.item or "") == "airballoon")) or \
                    (t == "Fire" and ab in {"flashfire", "wellbakedbody"}) or \
                    (t == "Water" and ab in {"waterabsorb", "stormdrain", "dryskin"}) or \
                    (t == "Electric" and ab in {"voltabsorb", "lightningrod", "motordrive"}) or \
                    (t == "Grass" and ab == "sapsipper"):
                e = 0
            if e > 1:
                weak += 1
                names.append(p["ja"])
            elif e < 1:
                resist += 1
        rows.append({"type": t, "ja": D.type_ja[t], "weak": weak, "resist": resist, "weak_members": names})
    return rows


def threats(team: list[MonSet], top: int = 30, snap: Optional[dict] = None) -> list[dict]:
    """使用率上位のうち、対面で勝てる駒が0〜1体の相手。"""
    D = dex()
    snap = snap if snap is not None else load_snapshot()
    if not snap:
        return []
    out = []
    for r in snap.get("ranking", [])[:top]:
        if not r.get("id"):
            continue
        o = likely_set(r["id"], snap)
        answers = []
        for m in team:
            d = duel(m, o)
            if d["score"] >= 0.75:
                answers.append(D.pokemon[m.species]["ja"])
        if len(answers) <= 1:
            out.append({"rank": r["rank"], "id": r["id"], "ja": D.pokemon[battle_species(o)]["ja"],
                        "set_label": o.label(), "answers": answers})
    return out


def diagnose(team: list[MonSet], archetype: str = "スタンダード", top: int = 30) -> dict:
    D = dex()
    members = []
    counts: dict[str, int] = {}
    for m in team:
        tags = tag_roles(m)
        for t in tags:
            counts[t["tag"]] = counts.get(t["tag"], 0) + 1
        members.append({"species": m.species, "ja": D.pokemon[m.species]["ja"], "roles": tags})
    findings = []
    for tagset, need, label in REQUIREMENTS.get(archetype, []):
        have = sum(1 for mm in members if any(t["tag"] in tagset for t in mm["roles"]))
        if have < need:
            findings.append({"level": "warn", "kind": "role",
                             "text": f"{archetype}構築に必要な「{label}」が{have}体（目安{need}体以上）"})
    overlap = type_overlap(team)
    for o in overlap:
        if o["weak"] >= 3:
            findings.append({"level": "warn" if o["resist"] == 0 else "info", "kind": "type",
                             "text": f"{o['ja']}弱点が{o['weak']}体（{'・'.join(o['weak_members'])}）、半減以下{o['resist']}体"})
    th = threats(team, top)
    for t in th:
        if not t["answers"]:
            findings.append({"level": "warn", "kind": "threat",
                             "text": f"使用率{t['rank']}位 {t['ja']} に対面で勝てる駒がいない（想定: {t['set_label']}）"})
        else:
            findings.append({"level": "info", "kind": "threat",
                             "text": f"使用率{t['rank']}位 {t['ja']} に勝てるのは {t['answers'][0]} のみ"})
    return {"archetype": archetype, "members": members, "role_counts": counts, "findings": findings,
            "type_overlap": overlap, "threats": th, "top": top}
