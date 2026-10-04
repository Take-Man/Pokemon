"""対面評価と選出予想（ルールベース）。

考え方:
- 1対1の対面を「確定数（50%以上で倒せる発数）」と素早さで評価し、0〜1のスコアにする
- 相手の選出予想 = 使用率（環境データがある場合）× 自分のパーティへの通りの良さ
- 自分の推奨選出 = 予想された相手の選出に対して、各相手に「勝てる駒」がいる組み合わせ
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional

from .damage import Field, Options, Result, Side, calc
from .data import dex, to_id
from .sets import MonSet, likely_set, load_snapshot
from .stats import effective_speed


def battle_species(s: MonSet) -> str:
    """メガストーンを持っていればメガシンカ後の姿で計算する。"""
    D = dex()
    p = D.pokemon[s.species]
    if s.item and not p["isMega"]:
        it = D.items.get(s.item)
        ms = it.get("megaStone") if it else None
        target = None
        if isinstance(ms, dict):
            target = ms.get(p["en"]) or ms.get(p["baseSpecies"])
        elif ms and to_id(it.get("megaEvolves") or "") == to_id(p["en"]):
            target = ms
        mega = D.pokemon.get(target) if target else None
        if mega:
            return mega["id"]
    return p["id"]


def as_side(s: MonSet, mega: bool = True) -> Side:
    b = s.build()
    if mega:
        sid = battle_species(s)
        if sid != dex().pokemon[s.species]["id"]:
            b.species = sid
            b.ability = dex().pokemon[sid]["abilities"][0]
    return Side(b)


@dataclass
class Hit:
    move: str
    result: Result

    def to_dict(self) -> dict:
        d = self.result.to_dict()
        return d


def best_hit(att: MonSet, dfd: MonSet, fld: Optional[Field] = None, att_boosts: Optional[dict] = None,
             dfd_boosts: Optional[dict] = None) -> Optional[Hit]:
    a, d = as_side(att), as_side(dfd)
    a.boosts = dict(att_boosts or {})
    d.boosts = dict(dfd_boosts or {})
    best: Optional[Hit] = None
    for m in att.moves:
        mv = dex().moves.get(m)
        if not mv or mv["category"] == "Status":
            continue
        r = calc(a, d, mv["id"], fld, Options())
        if best is None or sum(r.rolls) > sum(best.result.rolls):
            best = Hit(mv["id"], r)
    return best


def hits_to_ko(h: Optional[Hit]) -> int:
    if h is None or h.result.max == 0:
        return 99
    for n in range(1, 8):
        if h.result.ko_chance(n) >= 0.5:
            return n
    return 99


def speed_of(s: MonSet, stage: int = 0) -> int:
    b = as_side(s).build
    return effective_speed(b.stats()["spe"], stage, scarf=to_id(s.item or "") == "choicescarf")


def duel(a: MonSet, b: MonSet, b_boosts: Optional[dict] = None) -> dict:
    """aから見たbとの対面。score: 1=有利, 0.5=五分, 0=不利。b_boosts はbが積んだ後のランク。"""
    ha, hb = best_hit(a, b, dfd_boosts=b_boosts), best_hit(b, a, att_boosts=b_boosts)
    na, nb = hits_to_ko(ha), hits_to_ko(hb)
    sa, sb = speed_of(a), speed_of(b, (b_boosts or {}).get("spe", 0))
    faster = sa > sb
    if na == nb == 99:  # どちらも倒せない
        score = 0.5
    elif na < nb or (na == nb and faster):
        score = 1.0
    elif na == nb and sa == sb:
        score = 0.5
    else:
        score = 0.0
    # 確定数が大きく離れていない不利は少し救う
    if score == 0.0 and na <= nb + 1 and na < 99:
        score = 0.25
    # 後攻で、確定数の差が1しかない有利（先に殴られて削られる）は少し割り引く
    if score == 1.0 and not faster and nb <= na + 1:
        score = 0.75
    return {
        "score": score, "a_hits": na, "b_hits": nb, "a_speed": sa, "b_speed": sb,
        "a_best": ha.to_dict() if ha else None, "b_best": hb.to_dict() if hb else None,
    }


def _usage_score(species_id: str, snap: Optional[dict]) -> Optional[float]:
    if not snap:
        return None
    for r in snap.get("ranking", []):
        if r.get("id") == species_id:
            return max(0.05, 1 - (r["rank"] - 1) / 60)  # 60位以下はほぼ同じ扱い
    return 0.05


SPECIAL_BOOSTS = {"bellydrum": {"atk": 6}, "tidyup": {"atk": 1, "spe": 1}, "curse": {"atk": 1, "def": 1, "spe": -1},
                  "filletaway": {"atk": 2, "spa": 2, "spe": 2}, "victorydance": {"atk": 1, "def": 1, "spe": 1}}
SETUP_RATE = 30.0


def setup_moves(o: MonSet, snap: Optional[dict]) -> list[tuple[str, dict]]:
    """相手が採用率30%以上で持つ積み技（環境データが無ければ型の技から）。[(move_id, boosts)]"""
    D = dex()
    rows = ((snap or {}).get("pokemon", {}).get(o.species) or {}).get("moves")
    cands = [r["id"] for r in rows if (r.get("rate") or 0) >= SETUP_RATE] if rows else list(o.moves)
    out = []
    for mid in cands:
        mv = D.moves.get(mid)
        if not mv or mv["category"] != "Status":
            continue
        b = SPECIAL_BOOSTS.get(mv["id"]) or (mv.get("boosts") if mv.get("target") == "self" else None)
        if b and any(v > 0 for k, v in b.items() if k in ("atk", "spa", "spe")):
            out.append((mv["id"], {k: v for k, v in b.items() if k in ("atk", "def", "spa", "spd", "spe")}))
    return out


def _evidence(me: MonSet, o: MonSet, snap: Optional[dict]) -> tuple[float, str]:
    """実戦データ（相手の「倒されたポケモン」「倒したポケモン」上位10）による補正。"""
    d = (snap or {}).get("pokemon", {}).get(o.species) or {}
    D = dex()
    mine = {me.species, to_id(D.pokemon[me.species]["baseSpecies"])}
    koed_by = [r["id"] for r in d.get("koed_by_pokemon", [])]
    kos = [r["id"] for r in d.get("ko_pokemon", [])]
    adj, notes = 0.0, []
    # 使用率の高いポケモンは両方の欄に出やすいので、順位の差で打ち消し合うように重み付けする
    for i, x in enumerate(koed_by):
        if x in mine:
            adj += 0.15 * (10 - i) / 10
            notes.append(f"相手を倒した{i + 1}位")
    for i, x in enumerate(kos):
        if x in mine:
            adj -= 0.15 * (10 - i) / 10
            notes.append(f"相手に倒された{i + 1}位")
    return round(adj, 3), "・".join(notes)


def predict(my: list[MonSet], opp_species: list[str], opp_sets: Optional[dict[str, MonSet]] = None) -> dict:
    """相手の選出予想と自分の推奨選出。opp_sets で相手の型を個別に上書きできる。"""
    snap = load_snapshot()
    D = dex()
    opp = [opp_sets.get(s) if opp_sets and s in opp_sets else likely_set(s, snap) for s in opp_species]

    table = [[duel(m, o) for o in opp] for m in my]  # table[i][j] = 自分i vs 相手j
    # 実戦データで対面評価を補正
    for i, m in enumerate(my):
        for j, o in enumerate(opp):
            adj, note = _evidence(m, o, snap)
            x = table[i][j]
            x["calc_score"] = x["score"]
            x["score"] = max(0.0, min(1.0, x["score"] + adj))
            x["evidence"] = note

    opp_rows = []
    for j, o in enumerate(opp):
        vs_me = [1 - table[i][j]["score"] for i in range(len(my))]
        matchup = sum(vs_me) / max(len(my), 1)
        usage = _usage_score(o.species, snap)
        score = matchup if usage is None else 0.5 * matchup + 0.5 * usage
        opp_rows.append({
            "species": o.species, "ja": D.pokemon[o.species]["ja"], "set": o.to_dict(), "set_label": o.label(),
            "matchup": round(matchup, 3), "usage": None if usage is None else round(usage, 3),
            "score": round(score, 3),
            "threatens": [D.pokemon[my[i].species]["ja"] for i in range(len(my)) if vs_me[i] >= 0.75],
            "switch_ins": [D.pokemon[my[i].species]["ja"] for i in range(len(my))
                           if table[i][j]["b_best"] and table[i][j]["b_best"]["max_pct"] < 50],
            "setup": [],
        })
        for mid, boosts in setup_moves(o, snap):
            lost = []
            for i, m in enumerate(my):
                if table[i][j]["score"] >= 0.75 and duel(m, o, boosts)["score"] <= 0.25:
                    lost.append(D.pokemon[m.species]["ja"])
            opp_rows[-1]["setup"].append({"move": D.moves[mid]["ja"], "boosts": boosts, "flips": lost})
    ranked = sorted(range(len(opp)), key=lambda j: opp_rows[j]["score"], reverse=True)
    total = sum(opp_rows[j]["score"] for j in ranked) or 1
    weights = {j: opp_rows[j]["score"] / total for j in ranked}

    combos = []
    for c in combinations(range(len(my)), min(3, len(my))):
        s = 0.0
        answers = {}
        for j in range(len(opp)):
            vals = sorted(((table[i][j]["score"], i) for i in c), reverse=True)
            s += weights[j] * (vals[0][0] + 0.3 * (vals[1][0] if len(vals) > 1 else 0))
            answers[opp_rows[j]["ja"]] = [D.pokemon[my[i].species]["ja"] for sc, i in vals if sc >= 0.75]
        megas = sum(1 for i in c if battle_species(my[i]) != D.pokemon[my[i].species]["id"])
        if megas > 1:
            s -= 0.1
        combos.append({"members": [D.pokemon[my[i].species]["ja"] for i in c], "index": list(c),
                       "score": round(s, 3), "answers": answers, "mega_conflict": megas > 1})
    combos.sort(key=lambda x: x["score"], reverse=True)

    return {
        "data_source": (snap or {}).get("source") and f"{snap.get('source')} {snap.get('season_label', '')}" or "推定のみ（環境データなし）",
        "opponent": [opp_rows[j] | {"rank": k + 1} for k, j in enumerate(ranked)],
        "recommend": combos[:3],
        "matrix": [[{"score": x["score"], "a_hits": x["a_hits"], "b_hits": x["b_hits"],
                     "a_move": x["a_best"]["move"] if x["a_best"] else None,
                     "a_pct": [x["a_best"]["min_pct"], x["a_best"]["max_pct"]] if x["a_best"] else None,
                     "b_move": x["b_best"]["move"] if x["b_best"] else None,
                     "b_pct": [x["b_best"]["min_pct"], x["b_best"]["max_pct"]] if x["b_best"] else None,
                     "a_speed": x["a_speed"], "b_speed": x["b_speed"], "calc_score": x["calc_score"],
                     "evidence": x["evidence"]}
                    for x in row] for row in table],
        "my": [D.pokemon[m.species]["ja"] for m in my],
        "opp": [D.pokemon[o.species]["ja"] for o in opp],
    }
