"""ゲームの「パーティ確認」画面のレイアウト（基準: 2532x1170）。

画面は高さに合わせて拡大され、左右中央に置かれる前提で、解像度・縦横比が変わっても座標を写せる。
"""
from __future__ import annotations

from dataclasses import dataclass

REF_W, REF_H = 2532, 1170
CARD_W, CARD_H = 810, 210
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

    def card_rect(self, i: int, rel) -> tuple[int, int, int, int]:
        cx, cy = CARD_ORIGINS[i]
        x0, y0, x1, y1 = rel
        return self.rect(cx + x0, cy + y0, cx + x1, cy + y1)
