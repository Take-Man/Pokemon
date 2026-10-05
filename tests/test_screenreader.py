"""パーティ確認画面のスクショ読み取り（実機のスクショで回帰）。OCRが使えない環境ではスキップする。"""
from pathlib import Path

import pytest
from PIL import Image

from screenreader.layout import find_cards
from screenreader.match import best, fold
from screenreader.ocr import OCRUnavailable, get_backend
from screenreader.team_screen import detect_tab, parse_team_screens, solve_stats

FIX = Path(__file__).parent / "fixtures"
# 画面の種類ごと（端末・プラットフォームが違うスクショ）の期待値: 種族, 性格, 能力ポイント(H,A,B,C,D,S), 特性, 持ち物, 技(Noneは4つ読めればよい)
EXPECT = {
    "a": [  # スマホ 2532x1170
        ("イダイトウ", "adamant", (0, 32, 32, 0, 0, 2), "Adaptability", "Life Orb", ["wavecrash", "lastrespects", "aquajet", "outrage"]),
        ("ジジーロン", "modest", (32, 0, 2, 32, 0, 0), "Berserk", "Drampanite", None),
        ("サーフゴー", "timid", (2, 0, 0, 32, 0, 32), "Good as Gold", "Choice Scarf", None),
        ("ボーマンダ", "brave", (0, 32, 2, 0, 32, 0), "Moxie", "Salamencite", None),
        ("マリルリ", "adamant", (29, 32, 3, 0, 2, 0), "Huge Power", "Sitrus Berry", None),
        ("ガブリアス", "jolly", (2, 32, 0, 0, 0, 32), "Rough Skin", "Focus Sash", None),
    ],
    "b": [  # 別プラットフォーム 1920x1080（カードの位置・大きさ・余白が違う）
        ("ガブリアス", "adamant", (32, 0, 22, 0, 7, 5), "Rough Skin", "Sitrus Berry", ["earthquake", "dragontail", "stealthrock", "swordsdance"]),
        ("ゲンガー", "timid", (14, 0, 0, 20, 0, 32), "Cursed Body", "Gengarite", None),
        ("アーマーガア", "impish", (32, 0, 25, 0, 7, 2), "Pressure", "Leftovers", None),
        ("マスカーニャ", "adamant", (0, 32, 2, 0, 0, 32), "Overgrow", "Focus Sash", None),
        ("アシレーヌ", "modest", (32, 0, 24, 0, 0, 10), "Torrent", "Chesto Berry", None),
        ("カエンジシ", "modest", (10, 0, 0, 32, 0, 24), "Unnerve", "Pyroarite", None),
    ],
}
FILES = {"a": ("team_screen_abilities.png", "team_screen_stats.png"), "b": ("team_screen_b_abilities.png", "team_screen_b_stats.png")}


def _load(key, tf=None):
    imgs = [Image.open(FIX / n).convert("RGB") for n in FILES[key]]
    return [tf(i) for i in imgs] if tf else imgs


@pytest.fixture(scope="module", autouse=True)
def _ocr():
    try:
        get_backend()
    except OCRUnavailable as e:
        pytest.skip(str(e))


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


@pytest.mark.parametrize("key", ["a", "b"])
def test_parse_real_screens(key):
    imgs = _load(key)
    assert [detect_tab(i) for i in imgs] == ["abilities", "stats"]
    assert find_cards(imgs[0]) is not None
    res = parse_team_screens(imgs)
    assert res["warnings"] == []
    for m, (ja, nature, sp, ability, item, moves) in zip(res["members"], EXPECT[key]):
        assert m["species_ja"] == ja
        assert m["nature"] == nature
        assert tuple(m["sp"][k] for k in ("hp", "atk", "def", "spa", "spd", "spe")) == sp
        assert (m["ability"], m["item"]) == (ability, item)
        assert len(m["moves"]) == 4
        if moves:
            assert m["moves"] == moves
        assert m["flags"] == []


@pytest.mark.parametrize("key,w,h", [("a", 0.6, 0.6), ("b", 1.25, 1.0), ("b", 0.8, 1.0)])
def test_parse_resized_screens(key, w, h):
    """縦横比・解像度が変わっても（引き伸ばし・縮小を含む）、同じ結果になる。カードの位置は画像から検出する。"""
    base = parse_team_screens(_load(key))

    def tf(im):
        return im.resize((round(im.width * w), round(im.height * h)), Image.LANCZOS)

    res = parse_team_screens(_load(key, tf))
    keyf = lambda r: [(m["species"], m["nature"], m["sp"], m["moves"]) for m in r["members"]]  # noqa: E731
    assert keyf(res) == keyf(base)


def test_find_cards_none_on_blank():
    assert find_cards(Image.new("RGB", (800, 600), (240, 220, 180))) is None
