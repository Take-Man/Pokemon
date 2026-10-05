"""OCR結果を図鑑の辞書に寄せる（誤認識に強い曖昧一致）。"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_SMALL = str.maketrans("ぁぃぅぇぉっゃゅょゎ", "あいうえおつやゆよわ")
_DAKU = {}
for base, dk in (("かきくけこさしすせそたちつてとはひふへほ", "がぎぐげござじずぜぞだぢづでどばびぶべぼ"), ("はひふへほ", "ぱぴぷぺぽ")):
    for b, d in zip(base, dk):
        _DAKU[d] = b


def fold(s: str) -> str:
    """比較用: カタカナ→ひらがな、小書き→通常、濁点・半濁点を落とし、長音記号を統一。"""
    s = unicodedata.normalize("NFKC", s)
    s = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)
    s = s.translate(_SMALL)
    s = "".join(_DAKU.get(c, c) for c in s)
    s = re.sub(r"[ー一－―\-]", "ー", s)
    return re.sub(r"[^ぁ-ん0-9a-zー]", "", s.lower())


def best(query: str, cands: list[tuple[str, object]], min_score: float = 0.6):
    """query に最も近い候補 (obj, score)。先頭・末尾の1文字（アイコンの誤認識）は外した形も試す。"""
    q0 = fold(query)
    if not q0:
        return None, 0.0
    variants = {q0, q0[1:], q0[:-1]} - {""}
    top, ts = None, 0.0
    for name, obj in cands:
        k = fold(name)
        if not k:
            continue
        sc = 0.0
        for v in variants:
            r = SequenceMatcher(None, v, k).ratio()
            if v is not q0:
                r -= 0.04  # 削った形は少し割り引く
            sc = max(sc, r)
        if sc > ts:
            top, ts = obj, sc
    return (top, ts) if ts >= min_score else (None, ts)
