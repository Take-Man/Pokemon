"""逆算ダメ計: 対戦中の被ダメ・与ダメ記録から、相手の性格・能力ポイント・持ち物・特性を絞り込む。

記録の種類
- taken: 相手の技を自分が受けた。自分の型は既知。受けたダメージ（HP実数）から相手の攻撃側を推定
- dealt: 自分の技を相手に当てた。与えた割合（%）から相手の耐久側を推定
- reveal: 対戦中に判明した持ち物・技・特性（確定情報）

条件（天候・ランク・やけど等）は未入力(None)なら「なし」とみなし、結果に未確定として記す。
推定は次の順で行う。
1. 記録ごとに、関係する変数（性格補正・該当ステータスの能力ポイント・持ち物・特性）の組み合わせを全列挙し、
   観測値と矛盾しないものを残す
2. 同じ相手の記録をまとめ、25性格 × 持ち物 × 特性 ごとに各記録の条件を同時に満たすか調べる
   （HPは耐久側の記録で共有、能力ポイント合計66以内）
3. 残った候補を環境データの採用率で重み付けし、最有力の型を出す
"""
from __future__ import annotations

import json
import threading
from bisect import bisect_left, bisect_right
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Optional

from .damage import SPECIAL_PHYSICAL_DEF, Field, Options, Result, Side, calc
from .data import STATS, dex, to_id
from .sets import MonSet, load_snapshot
from .stats import SP_MAX, SP_TOTAL, calc_stat

# ダメージに影響する持ち物（それ以外は「影響なし」にまとめる）
TYPE_ITEM = {
    "Fighting": "blackbelt", "Dark": "blackglasses", "Fire": "charcoal", "Dragon": "dragonfang",
    "Fairy": "fairyfeather", "Rock": "hardstone", "Electric": "magnet", "Steel": "metalcoat", "Grass": "miracleseed",
    "Water": "mysticwater", "Ice": "nevermeltice", "Poison": "poisonbarb", "Flying": "sharpbeak",
    "Normal": "silkscarf", "Bug": "silverpowder", "Ground": "softsand", "Ghost": "spelltag", "Psychic": "twistedspoon",
}
RESIST_BERRY = {
    "Fire": "occaberry", "Water": "passhoberry", "Electric": "wacanberry", "Grass": "rindoberry", "Ice": "yacheberry",
    "Fighting": "chopleberry", "Poison": "kebiaberry", "Ground": "shucaberry", "Flying": "cobaberry",
    "Psychic": "payapaberry", "Bug": "tangaberry", "Rock": "chartiberry", "Ghost": "kasibberry", "Dragon": "habanberry",
    "Dark": "colburberry", "Steel": "babiriberry", "Fairy": "roseliberry", "Normal": "chilanberry",
}
OFFENSE_ITEMS = {"lifeorb", "expertbelt", "muscleband", "wiseglasses", "choiceband", "choicespecs", "normalgem",
                 "punchingglove", "lightball", *TYPE_ITEM.values()}
DEFENSE_ITEMS = {"assaultvest", "eviolite", *RESIST_BERRY.values()}
OTHER = "other"  # ダメージに影響しない持ち物

PLUS_NATURE = {"atk": "adamant", "def": "bold", "spa": "modest", "spd": "calm", "spe": "timid"}
MINUS_NATURE = {"atk": "modest", "def": "lonely", "spa": "adamant", "spd": "naughty", "spe": "brave"}
CLASSES = (1.1, 1.0, 0.9)


def _nature_for(stat: str, cls: float) -> str:
    return PLUS_NATURE[stat] if cls == 1.1 else MINUS_NATURE[stat] if cls == 0.9 else "hardy"


def nature_class(nature_id: str, stat: str) -> float:
    n = dex().natures[nature_id]
    if n["plus"] == stat:
        return 1.1
    if n["minus"] == stat:
        return 0.9
    return 1.0


@dataclass
class Cond:
    weather: Optional[str] = None
    terrain: Optional[str] = None
    crit: Optional[bool] = None
    atk_boost: Optional[int] = None  # 攻撃側のランク（技に対応するA/C）
    def_boost: Optional[int] = None  # 防御側のランク（B/D）
    burn: Optional[bool] = None  # 攻撃側のやけど（旧形式。atk_status を優先）
    atk_status: Optional[str] = None  # 攻撃側の状態異常 brn/par/psn/tox/slp/frz/none
    def_status: Optional[str] = None  # 防御側の状態異常
    screen: Optional[bool] = None  # 防御側の壁
    opp_mega: Optional[bool] = None  # 相手がメガシンカ後か
    hits: Optional[int] = None
    ko: Optional[bool] = None  # この攻撃で倒れた

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Cond":
        d = d or {}
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})

    def unknowns(self) -> list[str]:
        labels = {"weather": "天候", "terrain": "フィールド", "atk_boost": "攻撃側ランク", "def_boost": "防御側ランク",
                  "screen": "壁"}
        out = [v for k, v in labels.items() if getattr(self, k) is None]
        if self.atk_status is None and self.burn is None:
            out.append("攻撃側の状態異常")
        return out

    def a_status(self) -> Optional[str]:
        if self.atk_status and self.atk_status != "none":
            return self.atk_status
        return "brn" if self.burn else None

    def d_status(self) -> Optional[str]:
        return self.def_status if self.def_status and self.def_status != "none" else None


@dataclass
class Record:
    id: str
    kind: str  # taken / dealt / reveal
    opp: str
    my: Optional[dict] = None  # 自分の型（MonSetのdict）
    move: Optional[str] = None
    before: Optional[float] = None  # taken: 受ける前HP / dealt: 当てる前%
    after: Optional[float] = None  # taken: 受けた後HP / dealt: 当てた後%
    cond: dict = field(default_factory=dict)
    reveal_type: Optional[str] = None  # item / move / ability
    reveal_value: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "Record":
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})


# ---------------------------------------------------------------------------
# 候補
# ---------------------------------------------------------------------------

def _opp_species(opp: str, mega: bool) -> str:
    """メガシンカ後の姿。複数ある場合（X/Y・Z）は、判明した持ち物か採用率の高いメガストーンに合わせる。"""
    D = dex()
    p = D.pokemon[opp]
    if mega:
        megas = D.mega_of(p["id"])
        if not megas:
            return p["id"]
        pref = _MEGA_PREF.get(p["id"])
        if pref is None:
            items = (((load_snapshot() or {}).get("pokemon") or {}).get(p["id"]) or {}).get("items", [])
            order = [r["id"] for r in items]
            ranked = sorted(megas, key=lambda m: order.index(to_id(m["requiredItem"]))
                            if to_id(m["requiredItem"]) in order else 99)
            pref = ranked[0]["id"]
        return pref
    return p["id"]


_MEGA_PREF: dict[str, str] = {}  # 判明したメガストーンによる指定（infer 実行中だけ使う）


def _known(records: list[Record], kind: str) -> list[str]:
    return [r.reveal_value for r in records if r.kind == "reveal" and r.reveal_type == kind and r.reveal_value]


def item_candidates(opp: str, records: list[Record], snap: Optional[dict]) -> list[str]:
    D = dex()
    known = _known(records, "item")
    if known:
        it = D.items.get(known[-1])
        return [it["id"] if it and it["id"] in OFFENSE_ITEMS | DEFENSE_ITEMS else OTHER] if it else [OTHER]
    usage = [r["id"] for r in (((snap or {}).get("pokemon") or {}).get(opp) or {}).get("items", [])]
    cands = [OTHER]
    for i in usage + ["lifeorb", "expertbelt"]:
        if i in OFFENSE_ITEMS | DEFENSE_ITEMS and i not in cands:
            cands.append(i)
    for r in records:
        mv = D.moves.get(r.move or "")
        if not mv:
            continue
        if r.kind == "taken" and TYPE_ITEM.get(mv["type"]) not in cands:
            cands.append(TYPE_ITEM[mv["type"]])
        if r.kind == "dealt" and RESIST_BERRY.get(mv["type"]) not in cands:
            cands.append(RESIST_BERRY[mv["type"]])
    legal = {i["id"] for i in D.items.rows}
    return [c for c in cands if c == OTHER or c in legal]


def ability_candidates(species: str, records: list[Record]) -> list[str]:
    D = dex()
    known = _known(records, "ability")
    if known and D.abilities.get(known[-1]):
        return [D.abilities[known[-1]]["en"]]
    return list(D.pokemon[species]["abilities"])


# ---------------------------------------------------------------------------
# 記録ごとの可能集合
# ---------------------------------------------------------------------------

def _field(c: Cond) -> Field:
    return Field(c.weather or None, c.terrain or None)


def _totals(att: Side, dfd: Side, move_id: str, c: Cond) -> tuple[list[int], int]:
    """記録の条件で計算し、1回で出うる合計ダメージの一覧（連続技は1発ごとに乱数が独立）と受けた側の最大HPを返す。

    連続技の回数が未入力なら、ありうる回数をすべて含める。
    """
    mh = dex().moves[move_id].get("multihit")
    counts = [c.hits] if c.hits else (list(range(mh[0], mh[1] + 1)) if isinstance(mh, list) else [None])
    results: list[Result] = [calc(att, dfd, move_id, _field(c), Options(crit=bool(c.crit), hits=n)) for n in counts]
    totals = {x for res in results for x in (res.outcomes() if res.hit_rolls else res.rolls)}
    return sorted(totals), results[0].defender_hp


def _observed_ok(totals: list[int], hp: int, r: Record, c: Cond, as_percent: bool) -> bool:
    """観測したダメージが totals（_totals の結果）のどれかで出るか。hp は受けた側の最大HP。"""
    if not totals or totals[-1] == 0:
        return False
    if r.after is not None and float(r.after) <= 0:
        c = Cond(**{**c.__dict__, "ko": True})  # 残り0は倒れた扱い（ダメージは残りHP以上）
    if as_percent:
        before = 100.0 if r.before is None else float(r.before)
        after = float(r.after or 0)
        tol = 1.0 if before >= 100 else 2.0
        if c.ko:
            return totals[-1] / hp * 100 >= before - tol
        target = before - after
        # totals は昇順。条件を満たしうる範囲（前後に1の余裕）だけを、同じ式で確かめる
        lo = bisect_left(totals, (target - tol) * hp / 100 - 1)
        hi = bisect_right(totals, (target + tol) * hp / 100 + 1)
        return any(abs(x / hp * 100 - target) <= tol for x in totals[lo:hi])
    before = int(r.before) if r.before is not None else hp  # 受ける前のHPの既定は最大HP
    after = int(r.after or 0)
    if c.ko:
        return totals[-1] >= before
    return before - after in totals


# 記録ごとの可能集合は、記録の内容・候補・相手の姿が同じなら変わらない。HP・ランクの変更や
# 他の相手の記録の追加では再計算しないよう、結果を覚えておく（全列挙は1記録0.1〜0.5秒かかる）
_FEASIBLE_CACHE: "OrderedDict[str, tuple[str, frozenset]]" = OrderedDict()
_FEASIBLE_MAX = 1024
_FEASIBLE_LOCK = threading.Lock()


def _memo_feasible(fn: Callable) -> Callable:
    def wrapper(r: Record, items: list[str], abilities: list[str], mega: bool) -> tuple[str, frozenset]:
        key = json.dumps([fn.__name__, r.kind, r.opp, r.my, r.move, r.before, r.after, r.cond, items, abilities,
                          mega, _opp_species(r.opp, mega)], sort_keys=True, default=str)
        with _FEASIBLE_LOCK:
            hit = _FEASIBLE_CACHE.get(key)
            if hit is not None:
                _FEASIBLE_CACHE.move_to_end(key)
                return hit
        stat, F = fn(r, items, abilities, mega)
        hit = (stat, frozenset(F))
        with _FEASIBLE_LOCK:
            _FEASIBLE_CACHE[key] = hit
            if len(_FEASIBLE_CACHE) > _FEASIBLE_MAX:
                _FEASIBLE_CACHE.popitem(last=False)
        return hit
    wrapper.__name__, wrapper.__doc__, wrapper.__wrapped__ = fn.__name__, fn.__doc__, fn
    return wrapper


def _item_groups(items: list[str], same_effect: set) -> dict[str, list[str]]:
    """同じダメージになる持ち物をまとめる: {計算に使う持ち物: [同じ結果になる持ち物]}。

    攻撃側の防御用の持ち物・防御側の攻撃用の持ち物は、「何か持っている」こと（はたきおとす・アクロバット）
    以外はダメージに関係しないので、1つだけ計算して残りに写す。"""
    groups: dict[str, list[str]] = {}
    rep = None
    for it in items:
        if it in same_effect:
            rep = rep or it
            groups.setdefault(rep, []).append(it)
        else:
            groups.setdefault(it, []).append(it)
    return groups


@_memo_feasible
def feasible_taken(r: Record, items: list[str], abilities: list[str], mega: bool) -> tuple[str, set]:
    """相手→自分。返り値: (関係するステータス, {(補正, 持ち物, 特性, SP)})"""
    D = dex()
    c = Cond.from_dict(r.cond)
    mv = D.moves[r.move]
    if mv["id"] == "foulplay" or mv["category"] == "Status":
        return "", set()
    stat = "def" if mv["id"] == "bodypress" else ("atk" if mv["category"] == "Physical" else "spa")
    me = MonSet.from_dict(r.my)
    from .matchup import as_side

    dfd = as_side(me)
    dfd.boosts = {("def" if mv["category"] == "Physical" or mv["id"] in SPECIAL_PHYSICAL_DEF else "spd"): c.def_boost or 0}
    dfd.reflect = dfd.light_screen = bool(c.screen)
    dfd.status = c.d_status()
    if r.before is not None:
        dfd.hp_percent = float(r.before) / dfd.build.stats()["hp"] * 100
    sp_species = _opp_species(r.opp, mega)
    out = set()
    for cls in CLASSES:
        for item, same in _item_groups(items, DEFENSE_ITEMS).items():
            for ab in abilities:
                for sp in range(SP_MAX + 1):
                    b = MonSet(sp_species, _nature_for(stat, cls), {stat: sp}, ab, None if item == OTHER else item)
                    att = Side(b.build(), boosts={stat: c.atk_boost or 0}, status=c.a_status())
                    totals, my_hp = _totals(att, dfd, mv["id"], c)
                    if _observed_ok(totals, my_hp, r, c, as_percent=False):
                        out.update((cls, it, ab, sp) for it in same)
    return stat, out


@_memo_feasible
def feasible_dealt(r: Record, items: list[str], abilities: list[str], mega: bool) -> tuple[str, set]:
    """自分→相手。返り値: (防御ステータス, {(補正, 持ち物, 特性, HPのSP, 防御のSP)})"""
    D = dex()
    c = Cond.from_dict(r.cond)
    mv = D.moves[r.move]
    if mv["category"] == "Status":
        return "", set()
    stat = "def" if mv["category"] == "Physical" or mv["id"] in SPECIAL_PHYSICAL_DEF else "spd"
    me = MonSet.from_dict(r.my)
    from .matchup import as_side

    att = as_side(me)
    atk_key = "def" if mv["id"] == "bodypress" else ("atk" if mv["category"] == "Physical" else "spa")
    att.boosts = {atk_key: c.atk_boost or 0}
    att.status = c.a_status()
    sp_species = _opp_species(r.opp, mega)
    base = D.pokemon[sp_species]["baseStats"]
    out = set()
    for cls in CLASSES:
        for item, same in _item_groups(items, OFFENSE_ITEMS).items():
            for ab in abilities:
                for dsp in range(SP_MAX + 1):
                    # ダメージはHPの能力ポイントに依存しない（マルチスケイル等は満タン前提）ので、防御側ごとに1回計算
                    b = MonSet(sp_species, _nature_for(stat, cls), {stat: dsp}, ab, None if item == OTHER else item)
                    d = Side(b.build(), boosts={stat: c.def_boost or 0}, reflect=bool(c.screen), status=c.d_status(),
                             light_screen=bool(c.screen), hp_percent=100.0 if (r.before is None or r.before >= 100) else 99.0)
                    totals, _ = _totals(att, d, mv["id"], c)
                    for hsp in range(SP_MAX + 1):
                        hp = calc_stat(base["hp"], hsp, "hp")
                        if _observed_ok(totals, hp, r, c, as_percent=True):
                            out.update((cls, it, ab, hsp, dsp) for it in same)
    return stat, out


# ---------------------------------------------------------------------------
# 相手1体の推定
# ---------------------------------------------------------------------------

def _usage(opp: str, snap: Optional[dict]) -> dict:
    return (((snap or {}).get("pokemon") or {}).get(opp) or {})


def infer(opp: str, records: list[Record], snap: Optional[dict] = None, mega_hint: bool = False) -> dict:
    D = dex()
    snap = snap if snap is not None else load_snapshot()
    recs = [r for r in records if r.opp == opp]
    dmg_recs = [r for r in recs if r.kind in ("taken", "dealt") and r.move and D.moves.get(r.move)
                and not (r.cond or {}).get("miss")]  # 不発・効果なしの技は、ダメージの逆算に使わない
    mega = mega_hint or any(Cond.from_dict(r.cond).opp_mega for r in recs)
    known_item = _known(recs, "item")
    _MEGA_PREF.pop(D.pokemon[opp]["id"], None)
    if known_item and D.items.get(known_item[-1]) and D.items[known_item[-1]].get("megaStone"):
        mega = True
        ms = D.items[known_item[-1]]["megaStone"]
        target = ms.get(D.pokemon[opp]["en"]) if isinstance(ms, dict) else None
        if target and D.pokemon.get(target):
            _MEGA_PREF[D.pokemon[opp]["id"]] = D.pokemon[target]["id"]
    species = _opp_species(opp, mega)
    items = item_candidates(opp, recs, snap)
    abilities = ability_candidates(species, recs)
    per = []
    notes = []
    for r in dmg_recs:
        if r.kind == "taken":
            stat, F = feasible_taken(r, items, abilities, mega)
        else:
            stat, F = feasible_dealt(r, items, abilities, mega)
        unk = Cond.from_dict(r.cond).unknowns()
        per.append({"record": r, "stat": stat, "F": F, "idx": _index(r.kind, F)})
        if not stat:
            notes.append(f"{D.ja('moves', r.move)}: 逆算に使えない技")
        elif not F:
            notes.append(f"{D.ja('moves', r.move)}: どの候補でも観測値を再現できない（入力値・条件の確認が必要）")
        if unk and stat:
            notes.append(f"{D.ja('moves', r.move)}: 未入力の条件（{'・'.join(unk)}）は「なし」として計算")
    per = [p for p in per if p["stat"]]

    u = _usage(opp, snap)
    rate = {k: {x["id"]: x.get("rate") or 0 for x in u.get(k, [])} for k in ("natures", "items", "abilities")}

    combos = []
    for n in D.natures.rows:
        for item in items:
            for ab in abilities:
                ranges = _joint(per, n["id"], item, ab)
                if ranges is None:
                    continue
                w = (rate["natures"].get(n["id"], 0.5) + 0.1) * (_item_rate(item, rate["items"]) + 0.1) * \
                    (rate["abilities"].get(to_id(ab), 1.0) + 0.1)
                combos.append({"nature": n["id"], "item": item, "ability": ab, "ranges": ranges, "weight": w})
    total_w = sum(c["weight"] for c in combos) or 1
    for c in combos:
        c["p"] = c["weight"] / total_w
    combos.sort(key=lambda c: c["weight"], reverse=True)

    def agg(key):
        acc: dict[str, float] = {}
        for c in combos:
            acc[c[key]] = acc.get(c[key], 0) + c["p"]
        return sorted(acc.items(), key=lambda x: -x[1])

    constrained = sorted({s for p in per for s in ([p["stat"]] if p["record"].kind == "taken" else ["hp", p["stat"]])})
    sp_ranges = {}
    for s in constrained:
        lo = min((c["ranges"][s][0] for c in combos if s in c["ranges"]), default=None)
        hi = max((c["ranges"][s][1] for c in combos if s in c["ranges"]), default=None)
        if lo is not None:
            sp_ranges[s] = [lo, hi]
    # 性格ごとの範囲（同じ観測でも性格で必要な振り方が変わるため）
    by_nature = []
    for nid, pn in agg("nature")[:6]:
        rg: dict[str, list[int]] = {}
        for c in combos:
            if c["nature"] != nid:
                continue
            for k, (lo, hi) in c["ranges"].items():
                cur = rg.get(k)
                rg[k] = [lo, hi] if cur is None else [min(cur[0], lo), max(cur[1], hi)]
        by_nature.append({"id": nid, "ja": D.ja("natures", nid), "p": round(pn, 3), "ranges": rg})
    return {
        "species": species, "base_species": opp, "mega": mega, "records": len(dmg_recs), "by_nature": by_nature,
        "feasible": bool(combos) or not per, "constrained": constrained, "sp_ranges": sp_ranges,
        "natures": [{"id": k, "ja": D.ja("natures", k), "p": round(v, 3)} for k, v in agg("nature")][:8],
        "items": [{"id": k, "ja": "影響なし（その他）" if k == OTHER else D.ja("items", k), "p": round(v, 3)}
                  for k, v in agg("item")],
        "abilities": [{"id": to_id(k), "en": k, "ja": D.ja("abilities", k), "p": round(v, 3)} for k, v in agg("ability")],
        "best": combos[0] if combos else None, "candidates": len(combos), "notes": notes,
        "per_record": [{"id": p["record"].id, "stat": p["stat"], "count": len(p["F"])} for p in per],
    }


def _item_rate(item: str, rates: dict) -> float:
    if item == OTHER:
        return sum(v for k, v in rates.items() if k not in OFFENSE_ITEMS | DEFENSE_ITEMS) or 30.0
    return rates.get(item, 1.0)


@lru_cache(maxsize=256)
def _index(kind: str, F: frozenset) -> dict:
    """可能集合を (補正, 持ち物, 特性) で引けるようにする。taken: SPの集合 / dealt: {HPのSP: 防御のSPの集合}

    F は _memo_feasible が返す同じオブジェクトなので、結果も覚えておく（呼び出し側は読むだけ）。"""
    idx: dict = {}
    for t in F:
        key = t[:3]
        if kind == "taken":
            idx.setdefault(key, set()).add(t[3])
        else:
            idx.setdefault(key, {}).setdefault(t[3], set()).add(t[4])
    return idx


def _joint(per: list[dict], nature: str, item: str, ab: str) -> Optional[dict]:
    """性格・持ち物・特性を固定したとき、全記録を満たすSPの範囲。満たせなければ None。"""
    atk_allowed: dict[str, set] = {}
    def_pairs: dict[str, list[dict]] = {}
    for p in per:
        cls = nature_class(nature, p["stat"])
        hit = p["idx"].get((cls, item, ab))
        if p["record"].kind == "taken":
            atk_allowed[p["stat"]] = atk_allowed.get(p["stat"], set(range(SP_MAX + 1))) & (hit or set())
            if not atk_allowed[p["stat"]]:
                return None
        else:
            if not hit:
                return None
            def_pairs.setdefault(p["stat"], []).append(hit)
    ranges: dict[str, list[int]] = {}
    for s, v in atk_allowed.items():
        ranges[s] = [min(v), max(v)]
    min_atk = sum(min(v) for v in atk_allowed.values())
    if def_pairs:
        ok_hp = []
        per_stat_vals: dict[str, set] = {}
        for hp in range(SP_MAX + 1):
            mins = 0
            good = True
            vals_here = {}
            for s, lst in def_pairs.items():
                allowed = set(range(SP_MAX + 1))
                for by_hp in lst:
                    allowed &= by_hp.get(hp, set())
                if s in atk_allowed:
                    allowed &= atk_allowed[s]
                if not allowed:
                    good = False
                    break
                vals_here[s] = allowed
                mins += min(allowed)
            if good and hp + mins + sum(min(v) for k, v in atk_allowed.items() if k not in def_pairs) <= SP_TOTAL:
                ok_hp.append(hp)
                for s, v in vals_here.items():
                    per_stat_vals.setdefault(s, set()).update(v)
        if not ok_hp:
            return None
        ranges["hp"] = [min(ok_hp), max(ok_hp)]
        for s, v in per_stat_vals.items():
            ranges[s] = [min(v), max(v)]
    elif min_atk > SP_TOTAL:
        return None
    return ranges


# ---------------------------------------------------------------------------
# 相手の型（確定と推定）
# ---------------------------------------------------------------------------

def opponent_build(opp: str, records: list[Record], snap: Optional[dict] = None,
                   mega_hint: Optional[bool] = None) -> dict:
    """バトル中の相手1体の型。各項目に confirmed（確定）/ inferred（逆算）/ usage（採用率）/ estimate を付ける。

    mega_hint: True=メガシンカした / False=しなかった（メガストーン以外の型）/ None=未確定（採用率どおり）
    """
    from .sets import likely_set

    D = dex()
    snap = snap if snap is not None else load_snapshot()
    recs = [r for r in records if r.opp == opp]
    inf = infer(opp, recs, snap, bool(mega_hint) and bool(D.mega_of(opp)))
    base = likely_set(opp, snap)
    no_mega = mega_hint is False

    def is_stone(i):
        it = D.items.get(i) if i else None
        return bool(it and it.get("megaStone"))

    if no_mega and is_stone(base.item):
        base.item = next((r["id"] for r in _usage(opp, snap).get("items", []) if not is_stone(r["id"])), None)
    src_default = base.source  # usage / estimate

    # 技: 判明＋記録で使われた技は確定、残りは採用率上位で補う
    used = [r.move for r in recs if r.kind == "taken" and r.move]
    known_moves = []
    for m in _known(recs, "move") + used:
        mv = D.moves.get(m)
        if mv and mv["id"] not in known_moves:
            known_moves.append(mv["id"])
    moves = [{"id": m, "ja": D.ja("moves", m), "src": "confirmed"} for m in known_moves]
    for m in base.moves:
        if len(moves) >= 4:
            break
        if m not in known_moves:
            moves.append({"id": m, "ja": D.ja("moves", m), "src": src_default})

    known_item = _known(recs, "item")
    if known_item:
        item = {"id": D.items[known_item[-1]]["en"] if D.items.get(known_item[-1]) else known_item[-1],
                "ja": D.ja("items", known_item[-1]), "src": "confirmed"}
    elif inf["records"] and inf["best"] and inf["best"]["item"] != OTHER:
        it = D.items[inf["best"]["item"]]
        item = {"id": it["en"], "ja": it["ja"], "src": "inferred", "p": inf["items"][0]["p"] if inf["items"] else None}
    else:
        # 逆算で「影響なし」なら、採用率上位のうちダメージに影響しない持ち物を候補にする
        cand = None
        for r in _usage(opp, snap).get("items", []):
            if no_mega and is_stone(r["id"]):
                continue
            if not inf["records"] or r["id"] not in OFFENSE_ITEMS | DEFENSE_ITEMS:
                cand = r["id"]
                break
        cand = cand or base.item
        item = {"id": D.items[cand]["en"] if cand and D.items.get(cand) else cand, "ja": D.ja("items", cand),
                "src": src_default}
    if inf["mega"]:
        mega = D.pokemon[inf["species"]]
        item = {"id": mega["requiredItem"], "ja": D.ja("items", mega["requiredItem"]), "src": "confirmed"}

    known_ab = _known(recs, "ability")
    if known_ab:
        ability = {"id": D.abilities[known_ab[-1]]["en"], "ja": D.ja("abilities", known_ab[-1]), "src": "confirmed"}
    elif inf["records"] and inf["best"]:
        ability = {"id": inf["best"]["ability"], "ja": D.ja("abilities", inf["best"]["ability"]), "src": "inferred"}
    else:
        ability = {"id": base.ability, "ja": D.ja("abilities", base.ability), "src": src_default}
    if inf["mega"]:
        ab = D.pokemon[inf["species"]]["abilities"][0]
        ability = {"id": ab, "ja": D.ja("abilities", ab), "src": "confirmed"}

    # 性格・能力ポイント: 逆算の最有力に合う採用率上位の配分を探し、無ければ範囲から組み立てる
    nature = {"id": base.nature, "ja": D.ja("natures", base.nature), "src": src_default}
    sp = dict(base.sp)
    sp_src = {s: src_default for s in STATS}
    if inf["records"] and inf["best"]:
        best = inf["best"]
        nature = {"id": best["nature"], "ja": D.ja("natures", best["nature"]), "src": "inferred",
                  "p": inf["natures"][0]["p"] if inf["natures"] else None}
        ranges = best["ranges"]
        chosen = None
        for row in _usage(opp, snap).get("sp") or []:
            s = row.get("spread") or {}
            if all(ranges[k][0] <= s.get(k, 0) <= ranges[k][1] for k in ranges):
                chosen = {k: v for k, v in s.items() if v}
                break
        if chosen is None:
            # 制約のあるステータスは推定型の値に最も近い範囲内の値、残りのポイントは推定型の優先順で配る
            chosen = {k: base.sp.get(k, 0) for k in STATS}
            for k, (lo, hi) in ranges.items():
                chosen[k] = min(max(chosen[k], lo), hi)
            over = sum(chosen.values()) - SP_TOTAL
            for k in sorted(chosen, key=lambda k: (k in ranges, chosen[k])):
                if over <= 0:
                    break
                cut = min(over, chosen[k] - (ranges[k][0] if k in ranges else 0))
                chosen[k] -= cut
                over -= cut
            left = SP_TOTAL - sum(chosen.values())
            order = sorted([k for k in STATS if k not in ranges], key=lambda k: -base.sp.get(k, 0)) + \
                [k for k in ("spe", "hp", "atk", "spa", "def", "spd") if k not in ranges]
            for k in dict.fromkeys(order):
                if left <= 0:
                    break
                add = min(SP_MAX - chosen[k], left)
                chosen[k] += add
                left -= add
        sp = {k: v for k, v in chosen.items() if v}
        for k in ranges:
            sp_src[k] = "inferred"

    stats_range = {}
    if inf["records"] and inf["sp_ranges"]:
        b = D.pokemon[inf["species"]]["baseStats"]
        cls_set = {s: {nature_class(n["id"], s) for n in inf["natures"]} for s in STATS if s != "hp"}
        for s, (lo, hi) in inf["sp_ranges"].items():
            if s == "hp":
                stats_range[s] = [calc_stat(b["hp"], lo, "hp"), calc_stat(b["hp"], hi, "hp")]
            else:
                vals = [calc_stat(b[s], v, s, _nature_for(s, c)) for v in (lo, hi) for c in cls_set.get(s) or {1.0}]
                stats_range[s] = [min(vals), max(vals)]

    guess = MonSet(inf["species"], nature["id"], sp, ability["id"], item["id"], [m["id"] for m in moves],
                   "battle", "対戦中の記録から推定")
    from .matchup import as_side, battle_species

    bsp = battle_species(guess)
    mega_note = ""  # メガシンカ後・想定は名前でわかるので付けない
    if no_mega and D.mega_of(opp):
        mega_note = "（メガシンカなし）"
    if bsp != inf["species"] and not inf["mega"]:
        mab = D.pokemon[bsp]["abilities"][0]
        ability = {"id": mab, "ja": D.ja("abilities", mab) + "（メガ後）", "src": item["src"]}
    return {"species": inf["species"], "ja": D.pokemon[inf["species"]]["ja"], "base_species": opp,
            "battle_species": bsp, "battle_ja": D.pokemon[bsp]["ja"] + mega_note, "mega_hint": mega_hint,
            "item": item, "ability": ability, "nature": nature, "sp": sp, "sp_src": sp_src, "moves": moves,
            "stats": as_side(guess).build.stats(), "stats_range": stats_range, "inference": {k: v for k, v in inf.items()
                                                                                   if k != "best"},
            "set": guess.to_dict()}
