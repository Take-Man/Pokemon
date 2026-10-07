"""型（セット）の表現と、環境データ/推定からの型生成。"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

from .data import ROOT, dex
from .stats import Build

SNAPSHOT = ROOT / "data" / "snapshots" / "current" / "usage.json"

# 推定型で候補から外す技（反動で動けない・溜め・条件付き・自滅・命中難）
EXCLUDE_ESTIMATE = {
    "hyperbeam", "gigaimpact", "blastburn", "frenzyplant", "hydrocannon", "rockwrecker", "meteorassault",
    "explosion", "selfdestruct", "mistyexplosion", "finalgambit", "solarbeam", "solarblade", "skyattack",
    "electroshot", "meteorbeam", "focuspunch", "futuresight", "doomdesire", "lastresort", "belch", "beakblast",
    "shelltrap", "dreameater", "burnup", "doubleshock", "steelroller", "zapcannon", "dynamicpunch", "inferno",
    "fling", "naturalgift", "synchronoise", "firstimpression", "fakeout", "upperhand", "suckerpunch",
    "thrash", "petaldance", "outrage", "ragingfury", "headlongrush", "highjumpkick", "megakick", "irontail",
    "rollout", "iceball", "furycutter", "echoedvoice", "round", "uproar", "bide", "counter", "mirrorcoat",
    "metalburst", "endeavor", "superfang", "seismictoss", "nightshade", "lowkick", "grassknot", "heavyslam",
    "heatcrash", "gyroball", "electroball", "reversal", "flail", "eruption", "waterspout", "storedpower",
    "powertrip", "payback", "assurance", "avalanche", "revenge", "retaliate", "lashout", "hex", "facade",
    "acrobatics", "brine", "weatherball", "terrainpulse", "expandingforce", "risingvoltage", "boltbeak",
    "fishiousrend", "crushgrip", "wringout", "hardpress", "present", "magnitude", "beatup", "spitup",
    "trumpcard", "punishment", "ficklebeam", "lastrespects", "ragefist", "populationbomb", "tripleaxel",
    "triplekick", "dragondarts", "steelbeam", "mindblown", "chloroblast", "healingwish", "memento",
}


@dataclass
class MonSet:
    """1体の型。source は 'user' / 'usage' / 'estimate'。"""
    species: str
    nature: Optional[str] = None
    sp: dict[str, int] = field(default_factory=dict)
    ability: Optional[str] = None
    item: Optional[str] = None
    moves: list[str] = field(default_factory=list)
    source: str = "user"
    note: str = ""

    def build(self) -> Build:
        return Build(self.species, self.nature, dict(self.sp), self.ability, self.item, list(self.moves))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MonSet":
        return cls(**{k: d.get(k) for k in ("species", "nature", "sp", "ability", "item", "moves", "source", "note")
                      if k in d})

    def label(self) -> str:
        D = dex()
        p = D.pokemon[self.species]
        nat = D.ja("natures", self.nature)
        from .data import STAT_JA
        sp = "".join(f"{STAT_JA[k]}{v}" for k, v in self.sp.items() if v)
        item = D.ja('items', self.item) or "持ち物不明"
        moves = "/".join(D.ja("moves", m) for m in self.moves)
        return f"{p['ja']} {nat} {sp} {D.ja('abilities', self.ability)} @{item}｜{moves}"


def is_physical(species: dict) -> bool:
    b = species["baseStats"]
    atk = b["atk"] * (2 if set(species["abilities"]) & {"Huge Power", "Pure Power"} else 1)
    return atk >= b["spa"]


def estimate_set(species_id: str) -> MonSet:
    """環境データが無いときの推定型（種族値からの機械的な推定）。"""
    D = dex()
    p = D.pokemon[species_id]
    b = p["baseStats"]
    phys = is_physical(p)
    fast = b["spe"] >= 80
    atk_key = "atk" if phys else "spa"
    if phys:
        nature = "jolly" if fast else "adamant"
    else:
        nature = "timid" if fast else "modest"
    sp = {atk_key: 32, "spe": 32, "hp": 2} if fast else {atk_key: 32, "hp": 32, "spe": 2}
    cat = "Physical" if phys else "Special"
    pool = [D.moves[m] for m in p["moves"]]
    pool = [m for m in pool if m["category"] == cat and m["basePower"] >= 50 and m["id"] not in EXCLUDE_ESTIMATE
            and not m.get("multihit") and not m["flags"].get("charge") and not m["flags"].get("recharge")
            and m["id"] not in {"foulplay", "bodypress"}]
    stab, cover = {}, {}
    for m in sorted(pool, key=lambda m: (m["basePower"] * (m["accuracy"] if m["accuracy"] is not True else 100)),
                    reverse=True):
        (stab if m["type"] in p["types"] else cover).setdefault(m["type"], m["id"])
    moves = list(stab.values())[:2] + list(cover.values())
    moves = moves[:4]
    item = p["requiredItem"] if p["isMega"] else None
    ability = p["abilities"][0]
    for a in ("Huge Power", "Pure Power"):
        if a in p["abilities"]:
            ability = a
    return MonSet(species_id, nature, sp, ability, item, moves, "estimate",
                  "環境データなし: 種族値からの推定")


_snap_cache: tuple = (None, None)  # (ファイルの更新時刻・サイズ, 読み込んだ内容)


def load_snapshot() -> Optional[dict]:
    """環境データ。ファイルが変わるまでは読み込んだ内容を使い回す（読み取り専用として扱う）。

    環境変数 PBA_USAGE_DATA=off なら使わない（相手の型は種族値からの推定になる）。サービス版で、
    取得先の利用許可が出るまで使用率データを載せないためのスイッチ。"""
    global _snap_cache
    if os.environ.get("PBA_USAGE_DATA") == "off":
        return None
    try:
        st = SNAPSHOT.stat()
    except OSError:
        return None
    key = (str(SNAPSHOT), st.st_mtime_ns, st.st_size)
    if _snap_cache[0] != key:
        try:
            _snap_cache = (key, json.loads(SNAPSHOT.read_text(encoding="utf-8")))
        except Exception:
            return None
    return _snap_cache[1]


def usage_set(species_id: str, snap: Optional[dict] = None) -> Optional[MonSet]:
    """環境データの採用率上位から、互いに矛盾しない型を組む。

    性格の最多を起点に、物理/特殊を決め、それに合う能力ポイント・攻撃技を選ぶ。
    """
    snap = snap if snap is not None else load_snapshot()
    if not snap:
        return None
    d = snap.get("pokemon", {}).get(species_id)
    if not d:
        return None
    D = dex()
    base = estimate_set(species_id)

    def first(key):
        rows = d.get(key) or []
        return rows[0]["id"] if rows else None

    nature = first("natures") or base.nature
    n = D.natures.get(nature) if nature else None
    if n and n.get("minus") == "spa":
        physical = True
    elif n and n.get("minus") == "atk":
        physical = False
    else:
        physical = is_physical(D.pokemon[species_id])
    atk_key = "atk" if physical else "spa"

    sp = None
    for row in d.get("sp") or []:
        spread = row.get("spread") or {}
        other = "spa" if physical else "atk"
        if spread.get(atk_key, 0) >= spread.get(other, 0):
            sp = {k: v for k, v in spread.items() if v}
            break
    if sp is None and d.get("sp"):
        sp = {k: v for k, v in d["sp"][0]["spread"].items() if v}

    wrong_cat = "Special" if physical else "Physical"
    moves = []
    for row in d.get("moves") or []:
        mv = D.moves.get(row["id"])
        if not mv:
            continue
        if mv["category"] == wrong_cat and (row.get("rate") or 0) < 50:
            continue
        moves.append(mv["id"])
        if len(moves) == 4:
            break
    ability = first("abilities") or base.ability
    ab = D.abilities.get(ability)
    item = first("items")
    it = D.items.get(item) if item else None
    return MonSet(species_id, nature, sp or base.sp, ab["en"] if ab else ability, it["en"] if it else base.item,
                  moves or base.moves, "usage", f"{snap.get('source', '')} {snap.get('season_label', '')} の採用率上位")


def likely_set(species_id: str, snap: Optional[dict] = None) -> MonSet:
    return usage_set(species_id, snap) or estimate_set(species_id)


# ---------------------------------------------------------------------------
# 型の自動補完（入力済みの項目は変えず、未入力だけを環境データで埋める）
# ---------------------------------------------------------------------------

def _orientation(member: dict) -> tuple[Optional[bool], str]:
    """入力済みの内容から物理(True)/特殊(False)を推定する。決め手が無ければ None。"""
    from .data import to_id

    D = dex()
    sp = member.get("sp") or {}
    if sp.get("atk", 0) != sp.get("spa", 0) and max(sp.get("atk", 0), sp.get("spa", 0)) >= 16:
        return sp.get("atk", 0) > sp.get("spa", 0), "能力ポイント"
    n = D.natures.get(member.get("nature") or "")
    if n and n.get("minus") == "spa":
        return True, "性格"
    if n and n.get("minus") == "atk":
        return False, "性格"
    cats = [D.moves[m]["category"] for m in member.get("moves") or [] if D.moves.get(m)]
    ph, spc = cats.count("Physical"), cats.count("Special")
    if ph != spc:
        return ph > spc, "技"
    item = D.items.get(member.get("item") or "")
    ms = item.get("megaStone") if item else None
    if isinstance(ms, dict):
        mega = D.pokemon.get(next(iter(ms.values())))
        if mega and member.get("species") and to_id(D.pokemon[member["species"]]["en"]) in {to_id(k) for k in ms}:
            b = mega["baseStats"]
            return b["atk"] >= b["spa"], "メガシンカ後の種族値"
    return None, ""


def autofill(member: dict, snap: Optional[dict] = None) -> dict:
    """未入力の項目（性格・特性・持ち物・能力ポイント・技の空き枠）を環境データの採用率上位で埋める。

    返り値: {member, filled: [項目], message}。
    - 環境データにそのポケモンが無い → 埋めない
    - 入力済みの性格・特性・持ち物・技のどれも環境データの上位に無い → 合致する型が無いとして埋めない
    """
    D = dex()
    member = {k: v for k, v in member.items() if not k.startswith("_")}
    sid = member.get("species")
    if not sid or not D.pokemon.get(sid):
        return {"member": member, "filled": [], "message": "ポケモンが未入力"}
    snap = snap if snap is not None else load_snapshot()
    d = ((snap or {}).get("pokemon") or {}).get(D.pokemon[sid]["id"])
    name = D.pokemon[sid]["ja"]
    if not d:
        return {"member": member, "filled": [], "message": f"{name}の型データが無い（環境データの取得範囲外）"}

    ids = {k: [r["id"] for r in d.get(k) or []] for k in ("natures", "abilities", "items", "moves")}
    ab_ids = {D.abilities[a]["id"] for a in ids["abilities"] if D.abilities.get(a)}
    checks = []
    if member.get("nature"):
        checks.append(member["nature"] in ids["natures"])
    if member.get("ability") and D.abilities.get(member["ability"]):
        checks.append(D.abilities[member["ability"]]["id"] in ab_ids)
    if member.get("item") and D.items.get(member["item"]):
        checks.append(D.items[member["item"]]["id"] in ids["items"])
    for m in member.get("moves") or []:
        checks.append(m in ids["moves"])
    if checks and not any(checks):
        return {"member": member, "filled": [], "message": f"入力内容と合致する{name}の型が環境データに無い"}

    physical, why = _orientation(member)
    filled = []

    def fits_nature(nid: str) -> bool:
        n = D.natures.get(nid)
        if physical is None or not n or not n.get("plus"):
            return True
        return n["minus"] != ("atk" if physical else "spa") and n["plus"] != ("spa" if physical else "atk")

    if not member.get("nature"):
        cand = [n for n in ids["natures"] if fits_nature(n)]
        if cand:
            member["nature"] = cand[0]
            filled.append("性格")
            if physical is None:
                n = D.natures[cand[0]]
                physical = True if n.get("minus") == "spa" else False if n.get("minus") == "atk" else None
    if not member.get("ability") and ids["abilities"]:
        a = D.abilities.get(ids["abilities"][0])
        if a:
            member["ability"] = a["en"]
            filled.append("特性")
    if not member.get("item"):
        for it_id in ids["items"]:
            it = D.items.get(it_id)
            if it and not it.get("megaStone"):
                member["item"] = it["en"]
                filled.append("持ち物")
                break
    sp = member.get("sp") or {}
    if sum(sp.values()) == 0 and d.get("sp"):
        for row in d["sp"]:
            s = row.get("spread") or {}
            if physical is None or (s.get("atk", 0) >= s.get("spa", 0)) == physical:
                member["sp"] = {k: v for k, v in s.items() if v}
                filled.append("能力ポイント")
                break
    moves = list(member.get("moves") or [])
    if len(moves) < 4:
        wrong = None if physical is None else ("Special" if physical else "Physical")
        for r in d.get("moves") or []:
            mv = D.moves.get(r["id"])
            if not mv or mv["id"] in moves:
                continue
            if wrong and mv["category"] == wrong and (r.get("rate") or 0) < 50:
                continue
            if mv["id"] not in set(D.pokemon[sid]["moves"]):
                continue
            moves.append(mv["id"])
            if len(moves) == 4:
                break
        if len(moves) > len(member.get("moves") or []):
            member["moves"] = moves
            filled.append("技")
    basis = f"（{why}から{'物理' if physical else '特殊'}型と判断）" if why and physical is not None else ""
    msg = (f"{name}: {'・'.join(filled)}を埋めた{basis}" if filled else f"{name}: 埋める項目が無い")
    return {"member": member, "filled": filled, "message": msg}
