"""「パーティ確認」画面（能力タブ・ステータスタブ）から6体の型を読み取る。

- 能力タブ: ポケモン名・特性・持ち物・技4つ
- ステータスタブ: 実数値と能力ポイント。性格は▲▼アイコンの色と、実数値との整合性から決める
どちらか片方だけでも読める（足りない項目は空のまま返す）。
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from PIL import Image

from engine.data import STATS, dex
from engine.stats import SP_MAX, calc_stat

from . import layout as L
from .match import best
from .ocr import OCR, Line, get_backend

STAT_JA = {"hp": "HP", "atk": "こうげき", "def": "ぼうぎょ", "spa": "とくこう", "spd": "とくぼう", "spe": "すばやさ"}
GOOD = 0.8  # これ未満の一致は「要確認」にする


# ---------------------------------------------------------------------------
# 画面の判定・領域の切り出し
# ---------------------------------------------------------------------------

def _cards(img: Image.Image) -> list[L.Card]:
    """画像からカードの位置を探す。見つからなければ基準レイアウトの拡縮で代用する。"""
    return L.find_cards(img) or L.Frame(*img.size).cards()


def detect_tab(img: Image.Image, cards: Optional[list[L.Card]] = None) -> Optional[str]:
    """カードの上にある黄緑のタブが、左なら能力・右ならステータス。"""
    cards = cards or L.find_cards(img) or L.Frame(*img.size).cards()
    top = cards[0].y0
    a = np.asarray(img.convert("RGB").crop((0, 0, img.width, top))).astype(int)
    m = (a[..., 1] > 205) & (a[..., 0] > 140) & (a[..., 0] < 225) & (a[..., 2] < 110)
    if m.sum() < 200:
        return None
    mid = (cards[0].x1 + cards[1].x0) / 2
    return "abilities" if np.nonzero(m)[1].mean() < mid else "stats"


def _digits_crop(img: Image.Image, rect, thr: int = 185, grow: int = 0) -> Image.Image:
    """白い数字だけを残して拡大する（背景の紫・オレンジのバーを落とす）。"""
    rect = (max(0, rect[0] - grow), rect[1], min(img.width, rect[2] + grow), rect[3])
    c = np.asarray(img.convert("RGB").crop(rect)).astype(int)
    bright = (c.min(axis=2) > thr)
    out = np.where(bright, 0, 255).astype(np.uint8)
    im = Image.fromarray(out).convert("L")
    im = im.resize((im.width * 4, im.height * 4), Image.LANCZOS)
    pad = Image.new("L", (im.width + 60, im.height + 60), 255)
    pad.paste(im, (30, 30))
    return pad


def _arrow(img: Image.Image, rect) -> Optional[str]:
    """ラベルの右の▲（赤）・▼（青）。"""
    c = np.asarray(img.convert("RGB").crop(rect)).astype(int)
    R, G, B = c[..., 0], c[..., 1], c[..., 2]
    red = ((R > 185) & (G < 150) & (B < 175) & (R - G > 70)).sum()
    blue = ((B > 185) & (R < 140) & (G > 80) & (B - R > 80)).sum()
    need = max(3, int(0.0003 * c.shape[0] * c.shape[1]))
    if red >= need and red > blue:
        return "up"
    if blue >= need and blue > red:
        return "down"
    return None


# ---------------------------------------------------------------------------
# 能力タブ
# ---------------------------------------------------------------------------

def _pick(lines: list[Line], rect) -> Optional[Line]:
    x0, y0, x1, y1 = rect
    inside = [l for l in lines if x0 <= l.cx <= x1 and y0 <= l.cy <= y1 and l.text.strip()]
    if not inside:
        return None
    return max(inside, key=lambda l: (l.conf, len(l.text)))


def _read_texts(img: Image.Image, ocr: OCR, lines: list[Line], rects: list) -> list[str]:
    """枠ごとの文字。画面全体の読み取り結果から拾い、見つからない枠だけ切り出してまとめて読み直す。"""
    out: list[str] = []
    missing = []
    for k, rect in enumerate(rects):
        l = _pick(lines, rect)
        out.append(l.text if l else "")
        if not l:
            x0, y0, x1, y1 = rect
            missing.append((k, img.crop((x0, y0, x1, y1)).resize(((x1 - x0) * 2, (y1 - y0) * 2), Image.LANCZOS)))
    if missing:
        for (k, _), got in zip(missing, ocr.lines_many([sub for _, sub in missing])):
            out[k] = max(got, key=lambda g: g.conf).text if got else ""
    return out


def _species_pool():
    D = dex()
    return [(r["ja"], r) for r in D.pokemon.rows if not r["isMega"] and r.get("searchable", True)]


def read_names(img: Image.Image, ocr: OCR, lines: Optional[list[Line]] = None, cards: Optional[list[L.Card]] = None) -> list[dict]:
    cards = cards or _cards(img)
    lines = lines if lines is not None else ocr.lines(img)
    pool = _species_pool()
    out = []
    for raw in _read_texts(img, ocr, lines, [cards[i].rel(L.NAME) for i in range(6)]):
        row, sc = best(raw, pool, 0.5)
        out.append({"raw": raw, "species": row["id"] if row else None, "score": round(sc, 2)})
    return out


def read_abilities_page(img: Image.Image, ocr: OCR, lines: Optional[list[Line]] = None, cards: Optional[list[L.Card]] = None) -> list[dict]:
    D = dex()
    cards = cards or _cards(img)
    lines = lines if lines is not None else ocr.lines(img)
    names = read_names(img, ocr, lines, cards)
    items_pool = [(r["ja"], r) for r in D.items.rows]
    moves_pool = [(r["ja"], r) for r in D.moves.rows]
    abil_pool = [(r["ja"], r) for r in D.abilities.rows]
    # 特性・持ち物・技4つの枠を6体分まとめて読む（1体あたり6枠）
    rects = []
    for i in range(6):
        rects += [cards[i].rel(L.ABILITY), cards[i].rel(L.ITEM)]
        for k in range(4):
            y0 = L.MOVE_Y0 + L.MOVE_PITCH * k
            rects.append(cards[i].rel((L.MOVE_X[0], y0, L.MOVE_X[1], y0 + L.MOVE_PITCH)))
    texts = _read_texts(img, ocr, lines, rects)
    res = []
    for i, nm in enumerate(names):
        t = texts[i * 6:(i + 1) * 6]
        m = {"index": i, "species": nm["species"], "species_raw": nm["raw"], "species_score": nm["score"], "flags": []}
        sp = D.pokemon.get(nm["species"]) if nm["species"] else None
        # 特性: その種族の特性に絞る（絞ってもだめなら全体から）
        raw = t[0]
        pool = [(ja, {"en": en}) for en, ja in zip(sp["abilities"], sp["abilities_ja"])] if sp else []
        hit, sc = best(raw, pool, 0.45) if pool else (None, 0.0)
        if not hit:
            row, sc = best(raw, abil_pool, 0.6)
            hit = {"en": row["en"]} if row else None
        m["ability"], m["ability_raw"], m["ability_score"] = (hit["en"] if hit else None), raw, round(sc, 2)
        # 持ち物
        raw = t[1]
        row, sc = best(raw, items_pool, 0.6)
        m["item"], m["item_raw"], m["item_score"] = (row["en"] if row else None), raw, round(sc, 2)
        # 技: その種族の覚える技に絞る
        learn = set(sp["moves"]) if sp else set()
        lpool = [(r["ja"], r) for r in D.moves.rows if r["id"] in learn]
        moves, mraw, mscore = [], [], []
        for k in range(4):
            raw = t[2 + k]
            row, sc = best(raw, lpool, 0.55) if lpool else (None, 0.0)
            if not row:
                row, sc = best(raw, moves_pool, 0.6)
            moves.append(row["id"] if row else None)
            mraw.append(raw)
            mscore.append(round(sc, 2))
        m["moves"], m["moves_raw"], m["moves_score"] = moves, mraw, mscore
        res.append(m)
    return res


# ---------------------------------------------------------------------------
# ステータスタブ
# ---------------------------------------------------------------------------

# 読み取りの条件を変えて数字を読み直すときの組（しきい値, 切り出しの広げ幅）
_RETRY = [(185, 0), (160, 0), (185, 6), (210, 0), (160, 8), (140, 4)]


def _plausible(base: Optional[int], stat: str) -> tuple[int, int]:
    """その種族の実数値としてありうる範囲（読み取りの検算用）。"""
    if base is None:
        return 0, 999
    if stat == "hp":
        return base + 75, base + 75 + SP_MAX
    return (base + 20) * 90 // 100, (base + 20 + SP_MAX) * 110 // 100


def _read_numbers(img: Image.Image, ocr: OCR, jobs: list[tuple]) -> list[Optional[int]]:
    """jobs = [(rect, lo, hi)]。範囲 lo〜hi に収まる読み取りが得られるまで、条件を変えて読み直す。

    OCR の呼び出しは2回にまとめる: 1回目は全部の枠を最初の条件で、2回目は決まらなかった枠を残りの条件すべてで。
    条件の順に結果を見るので、1つずつ読み直すのと同じ結果になる。"""
    def accept(v, lo, hi):
        if v is not None and lo <= v <= hi:
            return v
        if v is not None and v >= 100 and lo <= int(str(v)[1:] or 0) <= hi:  # 先頭の余計な1文字
            return int(str(v)[1:])
        return None

    thr, grow = _RETRY[0]
    first = ocr.numbers([_digits_crop(img, rect, thr, grow) for rect, _, _ in jobs])
    out = [accept(v, lo, hi) for v, (_, lo, hi) in zip(first, jobs)]
    todo = [k for k, v in enumerate(out) if v is None]
    if todo:
        crops = [_digits_crop(img, jobs[k][0], thr, grow) for k in todo for thr, grow in _RETRY[1:]]
        vals = ocr.numbers(crops)
        n = len(_RETRY) - 1
        for j, k in enumerate(todo):
            _, lo, hi = jobs[k]
            seen = first[k]
            for v in vals[j * n:(j + 1) * n]:
                seen = v if seen is None else seen
                if accept(v, lo, hi) is not None:
                    out[k] = accept(v, lo, hi)
                    break
            else:
                out[k] = None if seen is None or not (lo <= seen <= hi) else seen
    return out


def read_stats_page(img: Image.Image, ocr: OCR, cards: Optional[list[L.Card]] = None,
                    species: Optional[list[Optional[str]]] = None) -> list[dict]:
    cards = cards or _cards(img)
    D = dex()
    res = []
    jobs, slots = [], []  # 6体分の実数値・能力ポイントをまとめて読む
    for i in range(6):
        arrows = {}
        for col in L.STAT_COLS:
            for r, stat in enumerate(col["stats"]):
                top = L.STAT_ROW_TOP + L.STAT_ROW_PITCH * r
                bot = top + L.STAT_ROW_H
                if stat != "hp":
                    ax0, ax1 = col["label"] + L.ARROW_DX[0], col["label"] + L.ARROW_DX[1]
                    arrows[stat] = _arrow(img, cards[i].rel((ax0, top, ax1, bot)))
                base = D.pokemon[species[i]]["baseStats"][stat] if species and species[i] else None
                lo, hi = _plausible(base, stat)
                jobs.append((cards[i].rel((col["value"][0], top, col["value"][1], bot)), lo, hi))
                slots.append((i, "values", stat))
                jobs.append((cards[i].rel((col["sp"][0], top, col["sp"][1], bot)), 0, SP_MAX))
                slots.append((i, "sp_raw", stat))
        res.append({"index": i, "arrows": arrows, "values": {}, "sp_raw": {}})
    for (i, key, stat), v in zip(slots, _read_numbers(img, ocr, jobs)):
        res[i][key][stat] = v
    return res


NEUTRAL = "hardy"


def _sp_for(base: int, stat: str, nature: str, v: Optional[int]) -> list[int]:
    if v is None:
        return []
    return [k for k in range(SP_MAX + 1) if calc_stat(base, k, stat, nature) == v]


def solve_stats(species_id: str, arrows: dict, values: dict, sp_raw: dict) -> dict:
    """実数値と▲▼から、性格と能力ポイントを決める。"""
    D = dex()
    base = D.pokemon[species_id]["baseStats"]
    up = [s for s, a in arrows.items() if a == "up"]
    down = [s for s, a in arrows.items() if a == "down"]
    natures = D.natures.rows

    def candidates():
        exact = [n for n in natures if (n["plus"] is None and not up and not down) or
                 (n["plus"] and up == [n["plus"]] and down == [n["minus"]])]
        if exact:
            return [n for n in exact if n["plus"] or n["id"] == NEUTRAL]
        return natures  # アイコンが読めなかった: 全部から実数値で決める

    def fit(n):
        ok, sps, miss = 0, {}, []
        for s in STATS:
            v, raw = values.get(s), sp_raw.get(s)
            ks = _sp_for(base[s], s, n["id"], v)
            if not ks and v is not None and v >= 100:  # 先頭に余計な1文字を拾ったとき（372→72）
                ks = _sp_for(base[s], s, n["id"], int(str(v)[1:]))
            if ks:
                ok += 1
                sps[s] = min(ks)  # 隣り合う値は実数値が同じになる（端数切り捨て）ので、小さい方に寄せる
            else:
                miss.append(s)
                sps[s] = raw if raw is not None and 0 <= raw <= SP_MAX else 0
        agree = sum(1 for s in STATS if sp_raw.get(s) == sps[s])
        if sum(sps.values()) > 66:  # 合計66を超える組み合わせはありえない
            ok -= 10
        return ok, agree, sps, miss

    scored = [(fit(n), n) for n in candidates()]
    (ok, agree, sps, miss), n = max(scored, key=lambda t: (t[0][0], t[0][1]))
    notes = []
    if miss:
        notes.append("実数値が合わない項目: " + "・".join(STAT_JA[s] for s in miss))
    if sum(sps.values()) > 66:
        notes.append(f"能力ポイントの合計が{sum(sps.values())}（上限66）")
    nat_id = n["id"]
    return {"nature": nat_id, "sp": sps, "notes": notes, "ok_stats": ok}


# ---------------------------------------------------------------------------
# まとめ
# ---------------------------------------------------------------------------

def parse_team_screens(images: list[Image.Image], ocr: Optional[OCR] = None) -> dict:
    """1〜2枚の画像から6体分の型を返す。"""
    ocr = ocr or get_backend()
    D = dex()
    members = [{"index": i, "species": None, "flags": []} for i in range(6)]
    warnings, kinds = [], []
    for img in images:
        img = img.convert("RGB")
        found = L.find_cards(img)
        if found is None:
            warnings.append("カードの位置を検出できなかったので、基準の配置で読んだ（読み取りが外れていないか確認してほしい）")
        cards = found or L.Frame(*img.size).cards()
        kind = detect_tab(img, cards)
        kinds.append(kind)
        if kind is None:
            warnings.append("パーティ確認画面（能力・ステータス）として認識できない画像がある")
            continue
        if kind == "abilities":
            for a in read_abilities_page(img, ocr, cards=cards):
                m = members[a["index"]]
                m.update({k: v for k, v in a.items() if k != "index"})
        else:
            names = read_names(img, ocr, cards=cards)
            for i, st in enumerate(read_stats_page(img, ocr, cards=cards, species=[n["species"] for n in names])):
                m = members[i]
                if not m.get("species") and names[i]["species"]:
                    m["species"], m["species_raw"], m["species_score"] = names[i]["species"], names[i]["raw"], names[i]["score"]
                m["_stats_page"] = st
    for m in members:
        st = m.pop("_stats_page", None)
        if st and m.get("species"):
            sol = solve_stats(m["species"], st["arrows"], st["values"], st["sp_raw"])
            m["nature"], m["sp"] = sol["nature"], sol["sp"]
            m["flags"] += sol["notes"]
        if m.get("species") is None:
            m["flags"].append("ポケモン名を読み取れなかった")
        else:
            m["species_ja"] = D.pokemon[m["species"]]["ja"]
            if m.get("species_score", 1) < GOOD:
                m["flags"].append(f"ポケモン名が曖昧（読み取り: {m.get('species_raw')}）")
        for key, label in (("ability", "特性"), ("item", "持ち物")):
            if key in m and (m[key] is None or m.get(f"{key}_score", 1) < GOOD):
                m["flags"].append(f"{label}が曖昧（読み取り: {m.get(key + '_raw')}）")
        if "moves" in m:
            for k, (mv, sc) in enumerate(zip(m["moves"], m["moves_score"])):
                if mv is None or sc < GOOD:
                    m["flags"].append(f"技{k + 1}が曖昧（読み取り: {m['moves_raw'][k]}）")
            m["moves"] = [x for x in m["moves"] if x]
    if "abilities" not in kinds:
        warnings.append("能力タブの画像が無いので、特性・持ち物・技は読み取っていない")
    if "stats" not in kinds:
        warnings.append("ステータスタブの画像が無いので、性格・能力ポイントは読み取っていない")
    return {"members": members, "warnings": warnings, "backend": ocr.name}
