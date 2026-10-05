"""パーティ確認画面のスクショに、読み取りの領域（カード・名前・特性・持ち物・技・数値・▲▼）を描いて保存する。

新しい端末・画面で読み取りがずれるときに、どこを見ているかを確認して screenreader/layout.py を調整するためのもの。
  python tools/debug_screen.py 画像.png [出力.png]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from screenreader import layout as L  # noqa: E402


def main(src: str, dst: str | None = None) -> None:
    img = Image.open(src).convert("RGB")
    cards = L.find_cards(img)
    print("カード検出:", "成功" if cards else "失敗（基準レイアウトで代用）", img.size)
    cards = cards or L.Frame(*img.size).cards()
    d = ImageDraw.Draw(img, "RGBA")

    def box(r, color, w=2):
        d.rectangle(r, outline=color, width=w)

    for c in cards:
        box((c.x0, c.y0, c.x1, c.y1), (255, 0, 0, 255), 4)
        box(c.rel(L.NAME), (0, 160, 255, 255))
        box(c.rel(L.ABILITY), (0, 200, 0, 255))
        box(c.rel(L.ITEM), (0, 200, 0, 255))
        for k in range(4):
            y0 = L.MOVE_Y0 + L.MOVE_PITCH * k
            box(c.rel((L.MOVE_X[0], y0, L.MOVE_X[1], y0 + L.MOVE_PITCH)), (255, 140, 0, 255))
        for col in L.STAT_COLS:
            for r in range(3):
                top = L.STAT_ROW_TOP + L.STAT_ROW_PITCH * r
                bot = top + L.STAT_ROW_H
                box(c.rel((col["value"][0], top, col["value"][1], bot)), (255, 255, 0, 255))
                box(c.rel((col["sp"][0], top, col["sp"][1], bot)), (255, 0, 255, 255))
                box(c.rel((col["label"] + L.ARROW_DX[0], top, col["label"] + L.ARROW_DX[1], bot)), (255, 255, 255, 255))
    out = dst or str(Path(src).with_suffix("")) + "_debug.png"
    img.save(out)
    print("保存:", out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(*sys.argv[1:3])
