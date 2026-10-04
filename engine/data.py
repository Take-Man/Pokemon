"""固定データ(data/static)の読み込みと名前検索。"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "data" / "static"

STATS = ("hp", "atk", "def", "spa", "spd", "spe")
STAT_JA = {"hp": "H", "atk": "A", "def": "B", "spa": "C", "spd": "D", "spe": "S"}


def to_id(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def norm_kana(s: str) -> str:
    """検索用の正規化: 全角半角統一・カタカナ→ひらがな・記号除去・小文字化。"""
    s = unicodedata.normalize("NFKC", s).lower()
    s = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)
    return re.sub(r"[\s・()（）\-_.’'!]", "", s)


def _load(name: str):
    return json.loads((STATIC / f"{name}.json").read_text(encoding="utf-8"))


class Table:
    """id / 英名 / 日本語名 のどれでも引ける表。"""

    def __init__(self, rows: list[dict]):
        self.rows = rows
        self.by_id: dict[str, dict] = {}
        self._keys: list[tuple[str, dict]] = []
        for r in rows:
            self.by_id[r["id"]] = r
            for k in {r["id"], to_id(r.get("en", "")), norm_kana(r.get("ja", ""))}:
                if k:
                    self.by_id.setdefault(k, r)
            self._keys.append((norm_kana(r.get("ja", "")) + "|" + to_id(r.get("en", "")), r))

    def get(self, key: str | None) -> dict | None:
        if not key:
            return None
        return self.by_id.get(key) or self.by_id.get(to_id(key)) or self.by_id.get(norm_kana(key))

    def __getitem__(self, key: str) -> dict:
        r = self.get(key)
        if r is None:
            raise KeyError(key)
        return r

    def search(self, q: str, limit: int = 20, pred=None) -> list[dict]:
        q = norm_kana(q)
        if not q:
            return []
        head, part = [], []
        for k, r in self._keys:
            if pred and not pred(r):
                continue
            if k.startswith(q) or k.split("|")[1].startswith(q):
                head.append(r)
            elif q in k:
                part.append(r)
        return (head + part)[:limit]


class Dex:
    def __init__(self):
        self.pokemon = Table(_load("pokemon"))
        self.moves = Table(_load("moves"))
        self.abilities = Table(_load("abilities"))
        self.items = Table(_load("items"))
        self.natures = Table(_load("natures"))
        t = _load("types")
        self.type_chart: dict[str, dict[str, float]] = t["chart"]
        self.type_ja: dict[str, str] = {x["id"]: x["ja"] for x in t["types"]}
        self.meta = _load("meta")

    def mega_of(self, species_id: str) -> list[dict]:
        """そのフォルムからメガシンカできる姿（メガストーンの対応表から引く）。"""
        base = self.pokemon[species_id]
        out = []
        for it in self.items.rows:
            ms = it.get("megaStone")
            if isinstance(ms, dict) and base["en"] in ms:
                m = self.pokemon.get(ms[base["en"]])
                if m and m not in out:
                    out.append(m)
        return out

    def ja(self, kind: str, key: str | None) -> str:
        if not key:
            return ""
        r = getattr(self, kind).get(key)
        return r["ja"] if r else key


@lru_cache(maxsize=1)
def dex() -> Dex:
    return Dex()
