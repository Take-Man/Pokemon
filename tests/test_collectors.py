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
