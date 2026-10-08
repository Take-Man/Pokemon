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
    "c": [  # 小さめ 1200x675（webp）。▲▼のアイコンが小さく、JPEG にすると色がにじんで読めない
        ("リザードン", "bold", (32, 0, 32, 1, 1, 0), "Blaze", "Charizardite Y", ["weatherball", "rocktomb", "solarbeam", "dragonpulse"]),
        ("カバルドン", "impish", (32, 0, 32, 0, 2, 0), "Sand Stream", "Leftovers", ["protect", "yawn", "earthquake", "slackoff"]),
        ("イダイトウ", "adamant", (8, 32, 18, 0, 5, 3), "Adaptability", "Spell Tag", ["lastrespects", "aquajet", "agility", "substitute"]),
        ("ガルーラ", "adamant", (27, 32, 1, 0, 6, 0), "Scrappy", "Kangaskhanite", ["bodyslam", "earthquake", "icepunch", "circlethrow"]),
        ("ブリムオン", "bold", (32, 0, 32, 0, 2, 0), "Magic Bounce", "Sitrus Berry", ["trickroom", "drainingkiss", "psychicnoise", "healingwish"]),
        ("サザンドラ", "modest", (2, 0, 0, 32, 0, 32), "Levitate", "Choice Scarf", ["darkpulse", "dracometeor", "flamethrower", "focusblast"]),
    ],
}
FILES = {"a": ("team_screen_abilities.png", "team_screen_stats.png"), "b": ("team_screen_b_abilities.png", "team_screen_b_stats.png"),
         "c": ("team_screen_c_abilities.webp", "team_screen_c_stats.webp")}


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


def _jpeg(im, quality=90):
    """サービス版の画面は送る前に JPEG（品質0.9）にする。"""
    import io

    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def _check(res, key):
    for m, (ja, nature, sp, ability, item, moves) in zip(res["members"], EXPECT[key]):
        assert m["species_ja"] == ja
        assert m["nature"] == nature
        assert tuple(m["sp"][k] for k in ("hp", "atk", "def", "spa", "spd", "spe")) == sp
        assert (m["ability"], m["item"]) == (ability, item)
        if moves:
            assert m["moves"] == moves
        assert m["flags"] == []


def test_solve_stats_without_arrows_uses_all_natures():
    """▲▼が1つも読めなくても「補正なし」に決め打ちせず、実数値から性格を決める（ずぶとい リザードン）。"""
    r = solve_stats("charizard", {"atk": None, "def": None, "spa": None, "spd": None, "spe": None},
                    {"hp": 185, "atk": 93, "def": 143, "spa": 130, "spd": 106, "spe": 120},
                    {"hp": 32, "atk": 0, "def": 32, "spa": 1, "spd": 1, "spe": 0})
    assert r["nature"] == "bold" and r["notes"] == []


@pytest.mark.parametrize("key", ["a", "b", "c"])
def test_parse_jpeg_screens(key):
    """サービス版と同じく JPEG にしても、同じ結果になる。"""
    _check(parse_team_screens(_load(key, _jpeg)), key)


@pytest.mark.parametrize("key", ["a", "b", "c"])
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


# ---- Google Cloud Vision（サービス版）: 応答の形を真似た偽物で、まとめて読む仕組みを確かめる ----

def _fake_google():
    """macOS Vision で読んだ結果を、Google の DOCUMENT_TEXT_DETECTION の応答の形にして返す（語は3文字ずつに分ける）。"""
    import base64
    import io

    from screenreader.ocr import VisionOCR

    v = VisionOCR()
    calls = []

    def post(body):
        req = body["requests"][0]
        img = Image.open(io.BytesIO(base64.b64decode(req["image"]["content"])))
        hints = req["imageContext"]["languageHints"]
        calls.append((img.size, hints))
        words = []
        for ln in v._run(img, ("ja-JP", "en-US") if "ja" in hints else ("en-US",)):
            n = max(1, -(-len(ln.text) // 3))
            for k in range(n):
                part = ln.text[k * 3:(k + 1) * 3]
                x0 = ln.x + ln.w * k // n
                x1 = ln.x + ln.w * (k + 1) // n
                vs = [{"x": x0, "y": ln.y}, {"x": x1, "y": ln.y}, {"x": x1, "y": ln.y + ln.h}, {"x": x0, "y": ln.y + ln.h}]
                words.append({"boundingBox": {"vertices": vs}, "confidence": ln.conf, "symbols": [{"text": c} for c in part]})
        return {"responses": [{"fullTextAnnotation": {"pages": [{"blocks": [{"paragraphs": [{"words": words}]}]}]}}]}

    return post, calls


@pytest.mark.parametrize("key", ["a", "b", "c"])
def test_google_backend_reads_real_screens_in_few_calls(key):
    import sys

    from screenreader.ocr import GoogleVisionOCR

    if sys.platform != "darwin":
        pytest.skip("偽の Google 応答に macOS Vision を使う")
    post, calls = _fake_google()
    g = GoogleVisionOCR(key="test", post=post)
    res = parse_team_screens(_load(key, _jpeg), g)  # サービス版と同じ: JPEG にして Google で読む
    assert res["warnings"] == [] and res["backend"] == "google-vision"
    for m, (ja, nature, sp, ability, item, moves) in zip(res["members"], EXPECT[key]):
        assert m["species_ja"] == ja
        assert m["nature"] == nature
        assert tuple(m["sp"][k] for k in ("hp", "atk", "def", "spa", "spd", "spe")) == sp
        assert (m["ability"], m["item"]) == (ability, item)
        if moves:
            assert m["moves"] == moves
    assert g.calls <= 5  # 1枚ずつ読むと約177回
