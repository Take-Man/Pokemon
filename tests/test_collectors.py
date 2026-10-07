"""pokedbパーサのテスト（実サイトの構造を縮めたHTML）。"""
from collectors.pokedb import _key_to_id, parse_detail, parse_list

LIST = """<div class="season-action-tags"><span class="tag">更新日</span><span class="tag">2026/9/28 16:07</span></div>
<a href="?season=6&rule=0">シングル</a>
<a href="/pokemon/show/0445-00?season=6&rule=0" class="list-pokemon"><div class="pokemon-rank">1</div><div class="pokemon-name">ガブリアス</div></a>
<a href="/pokemon/show/0128-02?season=6&rule=0" class="list-pokemon"><div class="pokemon-rank">2</div><div class="pokemon-name">ケンタロス:炎</div></a>
<a href="/pokemon/show/0479-02?season=6&rule=0" class="list-pokemon"><div class="pokemon-rank">3</div><div class="pokemon-name">ウォッシュロトム</div></a>"""

DETAIL = """
<span class="pokemon-trend__move-name" data-move-detail='{"rank":1,"name":"じしん","rate":67.6}'>じしん</span>
<div class="card"><div class="card-content"><h3>特性</h3><ul>
 <li class="usage-list-item"><span class="usage-name">さめはだ</span><span class="usage-rate">99.0%</span></li></ul></div></div>
<div class="card"><div class="card-content"><h3>能力補正</h3><ul>
 <li class="usage-list-item"><span class="usage-name">ようき ( S↑ C↓ )</span><span class="usage-rate">25.4%</span></li></ul></div></div>
<div class="card"><div class="card-content"><h3>持ち物</h3><ul>
 <li class="usage-list-item"><span class="usage-name">ガブリアスナイトＺ</span><span class="usage-rate">34.6%</span></li></ul></div></div>
<div class="card"><div class="card-content"><h3>能力ポイント</h3>
 <div x-show="statViewMode === 'raw'"><ul><li class="usage-list-item"><span class="usage-name">AS + h</span><span class="usage-rate">26.9%</span>
  <span class="pokemon-stat-spread__chip"><span class="pokemon-stat-spread__label">H</span><span class="pokemon-stat-spread__value">2</span></span>
  <span class="pokemon-stat-spread__chip"><span class="pokemon-stat-spread__label">A</span><span class="pokemon-stat-spread__value">32</span></span>
  <span class="pokemon-stat-spread__chip"><span class="pokemon-stat-spread__label">S</span><span class="pokemon-stat-spread__value">32</span></span>
 </li></ul></div></div></div>
<div class="card"><div class="card-content"><h3>同じチーム</h3><ul><li class="usage-list-item"><span class="usage-name">アシレーヌ</span></li></ul></div></div>
<div class="card"><div class="card-content"><div class="title is-flex">倒された技</div><ul><li>1 りゅうせいぐん 7.9% 7.9%</li></ul></div></div>
"""


def test_parse_list():
    r = parse_list(LIST)
    assert r["season"] == 6 and r["updated"] == "2026/9/28 16:07"
    assert [_key_to_id(x["key"], x["name"]) for x in r["ranking"]] == ["garchomp", "taurospaldeablaze", "rotomwash"]


def test_parse_detail():
    d = parse_detail(DETAIL)
    assert d["moves"] == [{"id": "earthquake", "ja": "じしん", "rate": 67.6}]
    assert d["abilities"][0]["id"] == "roughskin"
    assert d["natures"][0]["id"] == "jolly"
    assert d["items"][0]["id"] == "garchompitez"
    assert d["sp"][0]["spread"] == {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}
    assert d["teammates"][0]["id"] == "primarina"
    assert d["koed_by_moves"][0] == {"id": "dracometeor", "ja": "りゅうせいぐん", "rate": 7.9}


# ---- 取得の決まり（通信は差し替え、実サイトには出ない） ----
import io
import urllib.error
from datetime import datetime, timedelta

import pytest

from collectors import base, pokedb


class _Resp(io.BytesIO):
    def __init__(self, body: str):
        super().__init__(body.encode())
        self.headers = type("H", (), {"get": lambda _s, k, d=None: None, "get_content_charset": lambda _s: "utf-8"})()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def net(tmp_path, monkeypatch):
    """urlopen を差し替える。pages[url] が文字列なら本文、数値ならそのHTTPエラー。"""
    monkeypatch.setattr(base, "ACCESS_FILE", tmp_path / "access.json")
    monkeypatch.setattr(base, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base, "SNAP_DIR", tmp_path / "snap")
    monkeypatch.setattr(pokedb, "SNAP_DIR", tmp_path / "snap")
    monkeypatch.setattr(base, "_last_access", {})
    monkeypatch.setattr(base, "HOST_INTERVAL", {})
    monkeypatch.setattr(base, "MIN_INTERVAL", 0)
    calls, pages = [], {"https://example.test/robots.txt": "User-agent: *\nDisallow: /private/\n"}

    def urlopen(req, timeout=0):
        calls.append(req.full_url)
        assert "Mozilla" not in req.get_header("User-agent") and base.UA_TOKEN in req.get_header("User-agent")
        v = pages.get(req.full_url, 404)
        if isinstance(v, int):
            hdrs = type("H", (), {"get": lambda _s, k, d=None: "120" if k == "Retry-After" and v == 429 else d})()
            raise urllib.error.HTTPError(req.full_url, v, "x", hdrs, io.BytesIO(b""))
        return _Resp(v)

    monkeypatch.setattr(base.urllib.request, "urlopen", urlopen)
    return calls, pages


def test_robots_is_respected_and_cached(net):
    calls, pages = net
    pages["https://example.test/a"] = "ok"
    assert base.fetch_html("https://example.test/a", "t") == "ok"
    with pytest.raises(base.FetchBlocked):
        base.fetch_html("https://example.test/private/x", "t")
    assert base.fetch_html("https://example.test/a", "t") == "ok"
    assert calls.count("https://example.test/robots.txt") == 1  # robots.txt は1日1回
    assert "https://example.test/private/x" not in calls


def test_refused_request_stops_further_access(net):
    calls, pages = net
    pages["https://example.test/busy"] = 429
    pages["https://example.test/a"] = "ok"
    with pytest.raises(base.FetchBlocked):
        base.fetch_html("https://example.test/busy", "t")
    n = len(calls)
    with pytest.raises(base.FetchBlocked):  # 停止中は別のページも取りに行かない
        base.fetch_html("https://example.test/a", "t")
    assert len(calls) == n
    st = base.access_status("example.test")
    assert st["cooldown_until"] and st["cooldown_reason"] == "HTTP 429"


def test_daily_limit(net, monkeypatch):
    calls, pages = net
    pages["https://example.test/a"] = "ok"
    monkeypatch.setattr(base, "DAILY_LIMIT", 3)  # robots.txt を含めて3件
    base.fetch_html("https://example.test/a", "t")
    base.fetch_html("https://example.test/a", "t")
    with pytest.raises(base.FetchBlocked):
        base.fetch_html("https://example.test/a", "t")
    assert len(calls) == 3


def test_needs_detail_follows_site_update():
    now = datetime.now().astimezone()
    old = {"fetched_at": (now - timedelta(hours=10)).isoformat()}
    recent = {"fetched_at": (now - timedelta(hours=2)).isoformat()}
    assert pokedb._needs_detail(None, None, None)
    assert pokedb._needs_detail(old, now - timedelta(hours=1), None)  # 取得後にサイトが更新された
    assert not pokedb._needs_detail(old, now - timedelta(hours=20), None)  # 取得後に更新されていない
    assert not pokedb._needs_detail(recent, now - timedelta(hours=1), None)  # 更新されたが6時間以内に取得済み
    assert not pokedb._needs_detail(None, None, (now - timedelta(hours=1)).isoformat())  # 最近失敗した


def _site(pages):
    B = pokedb.BASE
    pages[B + "robots.txt"] = "User-agent: *\nDisallow: /error-pages/\n"
    pages[B + "pokemon/list?rule=0"] = LIST
    pages[B + "api/pokemon/search?rule=0"] = '{"pokemons": []}'
    for key in ("0445-00", "0128-02", "0479-02"):
        pages[f"{B}pokemon/show/{key}?season=6&rule=0"] = DETAIL
    return B


def test_second_check_does_not_access_the_site(net):
    calls, pages = net
    _site(pages)
    s = pokedb.collect(top=3)
    assert s["_fetched_now"] == 3 and not s["blocked"]
    n = len(calls)
    s = pokedb.collect(top=3)  # 一覧は1時間以内、詳細はサイト更新後に取得済み
    assert s["_planned"] == 0 and len(calls) == n
    assert pokedb.status()["stale"] == 0 and not pokedb.status()["can_check"]


def test_collect_stops_when_refused(net):
    calls, pages = net
    B = _site(pages)
    pages[B + "pokemon/show/0128-02?season=6&rule=0"] = 429  # 2体目で断られる
    s = pokedb.collect(top=3)
    assert s["_fetched_now"] == 1 and s["blocked"] and "garchomp" in s["pokemon"]
    assert B + "pokemon/show/0479-02?season=6&rule=0" not in calls  # 断られたら残りは取りに行かない
    assert pokedb.pending(["garchomp", "rotomwash", "pikachu"]) == ["rotomwash"]  # 取得済み・ランキング外は除く
