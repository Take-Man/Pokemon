"""能力ポイントの逆算（耐久調整・火力調整）。

- survive: 仮想敵の技を条件付きで耐える H/B（またはH/D）の最小配分
- ko:      仮想敵を条件付きで倒す A（またはC）の最小配分
条件は「n発で倒される確率が threshold 以下」（threshold=0 で確定耐え）、火力側は「n発で倒す確率が threshold 以上」（1.0で確定）。
他のステータスに振っているポイントは固定し、残りの範囲で探す。
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from .damage import Field, Options, calc
from .data import STAT_JA, dex
from .matchup import as_side
from .sets import MonSet
from .stats import SP_MAX, SP_TOTAL


def _move_category(att: MonSet, move: str) -> str:
    mv = dex().moves[move]
    if mv["id"] == "bodypress":
        return "Physical"
    return mv["category"]


def _def_key(move: str) -> str:
    mv = dex().moves[move]
    if mv["category"] == "Physical" or mv["id"] in {"psyshock", "psystrike", "secretsword"}:
        return "def"
    return "spd"


def survive(me: MonSet, threat: MonSet, move: str, hits: int = 1, threshold: float = 0.0,
            fld: Optional[Field] = None, keep: Optional[dict[str, int]] = None, limit: int = 5) -> dict:
    """me が threat の move を hits 回受けて倒される確率を threshold 以下にする最小配分。"""
    D = dex()
    dkey = _def_key(move)
    keep = dict(keep if keep is not None else {k: v for k, v in (me.sp or {}).items() if k not in ("hp", dkey)})
    budget = SP_TOTAL - sum(keep.values())
    att = as_side(threat)
    results = []
    for total in range(0, min(budget, 2 * SP_MAX) + 1):
        for hp in range(max(0, total - SP_MAX), min(SP_MAX, total) + 1):
            d = total - hp
            trial = replace(me, sp={**keep, "hp": hp, dkey: d})
            r = calc(att, as_side(trial), move, fld, Options())
            p = r.ko_chance(hits)
            if p <= threshold + 1e-9:
                results.append({"hp": hp, dkey: d, "total": total, "ko_chance": round(p, 4),
                                "damage_pct": list(r.percent()), "stats": as_side(trial).build.stats()})
        if results:
            break
    best = sorted(results, key=lambda x: (x["total"], -x["hp"]))[:limit]
    base = calc(att, as_side(me), move, fld, Options())
    return {
        "mode": "survive", "stat": dkey, "move": D.moves[move]["ja"], "threat": threat.label(), "hits": hits,
        "threshold": threshold, "budget": budget, "keep": keep, "options": best,
        "current": {"ko_chance": round(base.ko_chance(hits), 4), "damage_pct": list(base.percent())},
        "feasible": bool(best),
        "note": "" if best else f"残り{budget}ポイントでは条件を満たせない（性格・持ち物の変更が必要）",
    }


def ko(me: MonSet, target: MonSet, move: str, hits: int = 1, threshold: float = 1.0,
       fld: Optional[Field] = None, keep: Optional[dict[str, int]] = None) -> dict:
    """me の move で target を hits 発以内に倒す確率を threshold 以上にする最小の攻撃ポイント。"""
    D = dex()
    cat = _move_category(me, move)
    akey = "def" if D.moves[move]["id"] == "bodypress" else ("atk" if cat == "Physical" else "spa")
    keep = dict(keep if keep is not None else {k: v for k, v in (me.sp or {}).items() if k != akey})
    budget = SP_TOTAL - sum(keep.values())
    dfd = as_side(target)
    rows = []
    found = None
    for pts in range(0, min(budget, SP_MAX) + 1):
        trial = replace(me, sp={**keep, akey: pts})
        r = calc(as_side(trial), dfd, move, fld, Options())
        p = r.ko_chance(hits)
        rows.append({akey: pts, "ko_chance": round(p, 4), "damage_pct": list(r.percent())})
        if found is None and p >= threshold - 1e-9:
            found = rows[-1] | {"stats": as_side(trial).build.stats()}
    return {
        "mode": "ko", "stat": akey, "move": D.moves[move]["ja"], "target": target.label(), "hits": hits,
        "threshold": threshold, "budget": budget, "keep": keep, "option": found, "feasible": found is not None,
        "max": rows[-1] if rows else None,
        "note": "" if found else f"{STAT_JA[akey]}{min(budget, SP_MAX)}振りでも届かない（最大 {rows[-1]['ko_chance'] * 100:.1f}%）"
        if rows else "",
    }


def worst_case(threat: MonSet) -> MonSet:
    """仮想敵の最大火力型（攻撃に性格補正・32振り）。"""
    D = dex()
    p = D.pokemon[threat.species]
    moves = [D.moves.get(m) for m in threat.moves]
    phys = sum(1 for m in moves if m and m["category"] == "Physical")
    spec = sum(1 for m in moves if m and m["category"] == "Special")
    physical = phys >= spec if (phys or spec) else p["baseStats"]["atk"] >= p["baseStats"]["spa"]
    return replace(threat, nature="adamant" if physical else "modest",
                   sp={("atk" if physical else "spa"): 32, "hp": 32, "spe": 2}, source="worst")
