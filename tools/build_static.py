"""Showdown書き出し(_src/showdown_*.json)とPokeAPI CSVを結合し、日本語名付きの固定データを生成する。

使い方: python tools/build_static.py <PokeAPI csvディレクトリ>
出力: data/static/{types,natures,pokemon,moves,abilities,items}.json と knowledge/*.md の一部
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "static" / "_src"
OUT = ROOT / "data" / "static"
JA, JA_KANA, EN = "11", "1", "9"

STAT_JA = {"hp": "H", "atk": "A", "def": "B", "spa": "C", "spd": "D", "spe": "S"}
TYPE_JA_FALLBACK = {"Stellar": "ステラ"}
ZEN2HAN = str.maketrans("ＸＹＺ", "XYZ")
MANUAL_JA = {
    "Tauros-Paldea-Combat": "ケンタロス(パルデア格闘)",
    "Tauros-Paldea-Blaze": "ケンタロス(パルデア炎)",
    "Tauros-Paldea-Aqua": "ケンタロス(パルデア水)",
}
REGION_JA = {"Alola": "アローラ", "Galar": "ガラル", "Hisui": "ヒスイ", "Paldea": "パルデア"}


def sid(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def load_csv(d: Path, name: str):
    with open(d / f"{name}.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def names_by(d: Path, name: str, key: str, col: str = "name") -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = defaultdict(dict)
    for r in load_csv(d, name):
        out[r[key]][r["local_language_id"]] = r[col]
    return out


def pick(n: dict[str, str]) -> str | None:
    return n.get(JA) or n.get(JA_KANA)


def sd(name: str):
    return json.loads((SRC / f"showdown_{name}.json").read_text(encoding="utf-8"))


def main(csv_dir: Path) -> None:
    # ---- types -------------------------------------------------------------
    t_rows = {r["identifier"]: r["id"] for r in load_csv(csv_dir, "types")}
    t_names = names_by(csv_dir, "type_names", "type_id")
    sd_types = sd("types")
    type_ja = {}
    for t in sd_types:
        tid = t_rows.get(t["id"])
        type_ja[t["name"]] = (pick(t_names[tid]) if tid else None) or TYPE_JA_FALLBACK.get(t["name"], t["name"])
    battle_types = [t["name"] for t in sd_types if t["name"] != "Stellar"]
    # damageTaken: 0=等倍 1=弱点 2=半減 3=無効
    code = {0: 1.0, 1: 2.0, 2: 0.5, 3: 0.0}
    chart = {atk: {} for atk in battle_types}
    for t in sd_types:
        if t["name"] == "Stellar":
            continue
        for atk in battle_types:
            chart[atk][t["name"]] = code[t["damageTaken"].get(atk, 0)]
    (OUT / "types.json").write_text(json.dumps({
        "types": [{"id": n, "ja": type_ja[n]} for n in battle_types],
        "chart": chart,
        "_note": "chart[攻撃タイプ][防御タイプ] = 倍率",
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- natures -----------------------------------------------------------
    n_rows = {r["identifier"]: r["id"] for r in load_csv(csv_dir, "natures")}
    n_names = names_by(csv_dir, "nature_names", "nature_id")
    natures = []
    for n in sd("natures"):
        ja = pick(n_names[n_rows[n["id"]]])
        natures.append({"id": n["id"], "en": n["name"], "ja": ja, "plus": n["plus"], "minus": n["minus"],
                        "label": (f"{STAT_JA[n['plus']]}↑{STAT_JA[n['minus']]}↓" if n["plus"] else "無補正")})
    (OUT / "natures.json").write_text(json.dumps(natures, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- abilities ---------------------------------------------------------
    a_rows = {sid(r["identifier"]): r["id"] for r in load_csv(csv_dir, "abilities")}
    a_names = names_by(csv_dir, "ability_names", "ability_id")
    abilities = []
    ab_ja = {}
    for a in sd("abilities"):
        pid = a_rows.get(a["id"])
        ja = pick(a_names[pid]) if pid else None
        ab_ja[a["name"]] = ja or a["name"]
        abilities.append({"id": a["id"], "en": a["name"], "ja": ja or a["name"], "desc_en": a.get("shortDesc"), "ja_missing": ja is None})
    (OUT / "abilities.json").write_text(json.dumps(abilities, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- items -------------------------------------------------------------
    i_rows = {sid(r["identifier"]): r["id"] for r in load_csv(csv_dir, "items")}
    i_names = names_by(csv_dir, "item_names", "item_id")
    items = []
    for it in sd("items"):
        pid = i_rows.get(it["id"])
        ja = pick(i_names[pid]) if pid else None
        items.append({"id": it["id"], "en": it["name"], "ja": ja or it["name"], "megaStone": it["megaStone"],
                      "megaEvolves": it["megaEvolves"], "isBerry": it["isBerry"], "desc_en": it.get("shortDesc"), "ja_missing": ja is None})
    (OUT / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- moves -------------------------------------------------------------
    m_rows = {sid(r["identifier"]): r["id"] for r in load_csv(csv_dir, "moves")}
    m_names = names_by(csv_dir, "move_names", "move_id")
    moves = []
    for m in sd("moves"):
        pid = m_rows.get(m["id"])
        ja = pick(m_names[pid]) if pid else None
        m2 = dict(m)
        m2["en"] = m2.pop("name")
        m2["ja"] = ja or m2["en"]
        m2["ja_missing"] = ja is None
        moves.append(m2)
    (OUT / "moves.json").write_text(json.dumps(moves, ensure_ascii=False), encoding="utf-8")

    # ---- pokemon -----------------------------------------------------------
    sp_names = names_by(csv_dir, "pokemon_species_names", "pokemon_species_id")
    forms = {sid(r["identifier"]): r for r in load_csv(csv_dir, "pokemon_forms")}
    f_names = names_by(csv_dir, "pokemon_form_names", "pokemon_form_id", "pokemon_name")
    f_forms = names_by(csv_dir, "pokemon_form_names", "pokemon_form_id", "form_name")
    pokemon = []
    for s in sd("species"):
        base_ja = pick(sp_names[str(s["num"])]) or s["baseSpecies"]
        ja = None
        fr = forms.get(s["id"])
        if s["en" if False else "name"] in MANUAL_JA:
            ja = MANUAL_JA[s["name"]]
        elif s["forme"] and fr:
            ja = pick(f_names[fr["id"]]) or None
            if not ja:
                fn = pick(f_forms[fr["id"]])
                if fn and s["isMega"] and fn.startswith("メガ"):
                    ja = fn.translate(ZEN2HAN)
                elif fn and fn.endswith(base_ja):
                    ja = fn
                elif fn:
                    ja = f"{base_ja}({fn.replace('のすがた', '')})"
        if not ja:
            if not s["forme"]:
                ja = base_ja
            elif s["isMega"]:
                suffix = s["forme"].replace("Mega", "").strip("-")
                ja = f"メガ{base_ja}{suffix}"
            else:
                parts = [REGION_JA.get(p, p) for p in s["forme"].split("-")]
                ja = f"{base_ja}({'・'.join(parts)})"
        pokemon.append({
            "id": s["id"], "en": s["name"], "ja": ja, "num": s["num"], "baseSpecies": s["baseSpecies"],
            "forme": s["forme"], "isMega": s["isMega"], "requiredItem": s["requiredItem"],
            "types": s["types"], "types_ja": [type_ja[t] for t in s["types"]],
            "baseStats": s["baseStats"], "bst": sum(s["baseStats"].values()),
            "abilities": list(dict.fromkeys(s["abilities"].values())),
            "abilities_ja": [ab_ja.get(a, a) for a in dict.fromkeys(s["abilities"].values())],
            "weightkg": s["weightkg"], "otherFormes": s["otherFormes"], "battleOnly": s.get("battleOnly"),
            "moves": s["moves"],
        })
    # 見た目違い・バトル中のみのフォルムは検索対象から外す
    by_name = {p["en"]: p for p in pokemon}
    for p in pokemon:
        base = by_name.get(p["baseSpecies"])
        cosmetic = (p["forme"] and base is not None and base is not p and not p["isMega"]
                    and base["types"] == p["types"] and base["baseStats"] == p["baseStats"]
                    and base["abilities"] == p["abilities"])
        p["searchable"] = not (cosmetic or (p["battleOnly"] and not p["isMega"]))
    (OUT / "pokemon.json").write_text(json.dumps(pokemon, ensure_ascii=False), encoding="utf-8")

    # 手動の日本語名で上書き
    ov = json.loads((OUT / "overrides_ja.json").read_text(encoding="utf-8"))
    for key, rows in (("items", items), ("abilities", abilities), ("moves", moves), ("pokemon", pokemon)):
        for r in rows:
            if r["en"] in ov.get(key, {}):
                r["ja"] = ov[key][r["en"]]
                r["ja_missing"] = False
    for name, rows in (("items", items), ("abilities", abilities), ("pokemon", pokemon)):
        (OUT / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=None if name == "pokemon" else 1), encoding="utf-8")
    (OUT / "moves.json").write_text(json.dumps(moves, ensure_ascii=False), encoding="utf-8")
    ab_ja2 = {a["en"]: a["ja"] for a in abilities}
    for p in pokemon:
        p["abilities_ja"] = [ab_ja2.get(a, a) for a in p["abilities"]]
    (OUT / "pokemon.json").write_text(json.dumps(pokemon, ensure_ascii=False), encoding="utf-8")

    meta = sd("meta")
    missing = {
        "abilities": [a["en"] for a in abilities if a.get("ja_missing")],
        "items": [i["en"] for i in items if i.get("ja_missing")],
        "moves": [m["en"] for m in moves if m.get("ja_missing")],
    }
    meta["ja_missing"] = missing
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: len(v) for k, v in missing.items()}), "missing ja")
    print(missing)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
