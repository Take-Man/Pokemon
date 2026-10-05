"""パーティ確認画面のスクショ読み取り（実機のスクショで回帰）。OCRが使えない環境ではスキップする。"""
from pathlib import Path

import pytest
from PIL import Image

from screenreader.match import best, fold
from screenreader.ocr import OCRUnavailable, get_backend
from screenreader.team_screen import detect_tab, parse_team_screens, solve_stats

FIX = Path(__file__).parent / "fixtures"
EXPECT = [  # 種族, 性格, 能力ポイント(H,A,B,C,D,S), 特性, 持ち物, 技
    ("イダイトウ", "adamant", (0, 32, 32, 0, 0, 2), "Adaptability", "Life Orb", ["wavecrash", "lastrespects", "aquajet", "outrage"]),
    ("ジジーロン", "modest", (32, 0, 2, 32, 0, 0), "Berserk", "Drampanite", None),
    ("サーフゴー", "timid", (2, 0, 0, 32, 0, 32), "Good as Gold", "Choice Scarf", None),
    ("ボーマンダ", "brave", (0, 32, 2, 0, 32, 0), "Moxie", "Salamencite", None),
    ("マリルリ", "adamant", (29, 32, 3, 0, 2, 0), "Huge Power", "Sitrus Berry", None),
    ("ガブリアス", "jolly", (2, 32, 0, 0, 0, 32), "Rough Skin", "Focus Sash", None),
]


def test_fold_absorbs_ocr_noise():
    assert fold("ボーマンダ") == fold("ポーマンタ")
    obj, sc = best("てきおうりよく", [("てきおうりょく", "ok"), ("かたやぶり", "ng")])
    assert obj == "ok" and sc > 0.8


def test_solve_stats_recovers_nature_and_sp():
    # ガブリアス ようき（S↑A... 実数値は画面の読み取りどおり）
    r = solve_stats("garchomp", {"spe": "up", "spa": "down"},
                    {"hp": 185, "atk": 182, "def": 115, "spa": 90, "spd": 105, "spe": 169},
                    {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32})
    assert r["nature"] == "jolly" and r["sp"] == {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}


@pytest.fixture(scope="module")
def parsed():
    try:
        get_backend()
    except OCRUnavailable as e:
        pytest.skip(str(e))
    imgs = [Image.open(FIX / "team_screen_abilities.png"), Image.open(FIX / "team_screen_stats.png")]
    assert [detect_tab(i) for i in imgs] == ["abilities", "stats"]
    return parse_team_screens(imgs)


def test_parse_real_screens(parsed):
    assert parsed["warnings"] == []
    for m, (ja, nature, sp, ability, item, moves) in zip(parsed["members"], EXPECT):
        assert m["species_ja"] == ja
        assert m["nature"] == nature
        assert tuple(m["sp"][k] for k in ("hp", "atk", "def", "spa", "spd", "spe")) == sp
        assert (m["ability"], m["item"]) == (ability, item)
        assert len(m["moves"]) == 4
        if moves:
            assert m["moves"] == moves
        assert m["flags"] == []


def test_parse_scaled_screen(parsed):
    """解像度・縦横比が変わっても同じ結果になる（高さ基準で拡縮し、左右中央に置かれる前提）。"""
    out = []
    for name in ("team_screen_abilities.png", "team_screen_stats.png"):
        im = Image.open(FIX / name).convert("RGB")
        h = 590
        im = im.resize((round(im.width * h / im.height), h), Image.LANCZOS)
        canvas = Image.new("RGB", (1400, h), (250, 230, 200))
        canvas.paste(im, ((1400 - im.width) // 2, 0))
        out.append(canvas)
    r = parse_team_screens(out)
    assert [(m["species"], m["nature"], m["sp"], m["moves"]) for m in r["members"]] == \
           [(m["species"], m["nature"], m["sp"], m["moves"]) for m in parsed["members"]]
