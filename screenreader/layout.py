"""ゲームの「パーティ確認」画面のレイアウト（基準: 2532x1170）。

画面は高さに合わせて拡大され、左右中央に置かれる前提で、解像度・縦横比が変わっても座標を写せる。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

REF_W, REF_H = 2532, 1170
CARD_W, CARD_H = 810, 204
# 1〜6体目の左上（左列→右列、上→下の順）
CARD_ORIGINS = [(424, 286), (1294, 286), (424, 522), (1294, 522), (424, 757), (1294, 757)]

# カード左上からの相対矩形 (x0, y0, x1, y1)
NAME = (55, 0, 340, 52)
ABILITY = (65, 58, 480, 104)
ITEM = (65, 108, 480, 156)
MOVE_X = (490, 810)
MOVE_Y0, MOVE_PITCH = 20, 49.5
# ステータス画面: 行の上端と、列ごとの (ラベルx, 実数値x範囲, 能力ポイントx範囲)
STAT_ROW_TOP, STAT_ROW_PITCH, STAT_ROW_H = 58, 48.5, 44
STAT_COLS = [
    {"label": 95, "value": (228, 312), "sp": (330, 410), "stats": ["hp", "atk", "def"]},
    {"label": 478, "value": (610, 705), "sp": (712, 795), "stats": ["spa", "spd", "spe"]},
]
ARROW_DX = (100, 128)  # ラベル左端からの、▲▼アイコンのx範囲
# 上部のタブ（能力 / ステータス）の帯
TAB_BAND = (680, 205, 1850, 262)


@dataclass
class Frame:
    """基準レイアウトを、高さ基準の拡縮＋左右中央として写す（カードを検出できなかったときの代替）。"""
    w: int
    h: int

    @property
    def s(self) -> float:
        return self.h / REF_H

    @property
    def ox(self) -> float:
        return (self.w - REF_W * self.s) / 2

    def rect(self, x0, y0, x1, y1) -> tuple[int, int, int, int]:
        s, ox = self.s, self.ox
        return (max(0, round(ox + x0 * s)), max(0, round(y0 * s)), min(self.w, round(ox + x1 * s)), min(self.h, round(y1 * s)))

    def cards(self) -> list["Card"]:
        return [Card(*self.rect(cx, cy, cx + CARD_W, cy + CARD_H)) for cx, cy in CARD_ORIGINS]


@dataclass
class Card:
    """画面上の1体分のカード。内側の座標は、基準サイズ（CARD_W x CARD_H）の相対値を、このカードの大きさに合わせて写す。"""
    x0: int
    y0: int
    x1: int
    y1: int

    def rel(self, r) -> tuple[int, int, int, int]:
        sx, sy = (self.x1 - self.x0) / CARD_W, (self.y1 - self.y0) / CARD_H
        return (round(self.x0 + r[0] * sx), round(self.y0 + r[1] * sy), round(self.x0 + r[2] * sx), round(self.y0 + r[3] * sy))


def _runs(v, thr, min_len):
    out, s = [], None
    for i, x in enumerate(v):
        if x > thr and s is None:
            s = i
        elif x <= thr and s is not None:
            if i - s >= min_len:
                out.append((s, i))
            s = None
    if s is not None and len(v) - s >= min_len:
        out.append((s, len(v)))
    return out


def find_cards(img) -> Optional[list[Card]]:
    """カード（紫の角丸パネル）を画像から探す。2列x3行が見つからなければ None。

    端末ごとに画面の縦横比・余白・カードの大きさが違っても、カード自体を基準にして内側を読む。
    """
    import numpy as np
    W, H = img.size
    k = 1.0
    a = np.asarray(img.convert("RGB")).astype(int)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    m = (B > 160) & (B - G > 40) & (R > 90) & (R < 200) & (B - R > 20)
    h, w = m.shape
    cols = _runs(m.sum(0), h * 0.12, int(w * 0.15))
    if len(cols) < 2:
        return None
    cols = sorted(sorted(cols, key=lambda c: c[1] - c[0], reverse=True)[:2])
    grid = []
    for x0, x1 in cols:
        rows = _runs(m[:, x0:x1].sum(1), (x1 - x0) * 0.3, int(h * 0.12))
        if len(rows) != 3:
            return None
        grid.append([(x0, y0, x1, y1) for y0, y1 in rows])
    out = []
    for r in range(3):
        for c in range(2):
            x0, y0, x1, y1 = grid[c][r]
            out.append(Card(round(x0 / k), round(y0 / k), round(x1 / k), round(y1 / k)))
    return out
