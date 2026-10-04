"""ポケモンバトルデータベース チャンピオンズ（champs.pokedb.tokyo）アダプタ。

取得するもの（シングル・最新シーズンのみ）:
- 使用率ランキング（一覧ページ1回）
- 各ポケモンの 技・特性・性格・持ち物・能力ポイント・同じチーム・倒した/倒されたポケモンと技（詳細ページ1体1回）
- 上位構築の公開データ（/opendata、完了したシーズンのみ。サイトが公式に配布しているもの）

利用規約（2026/6/11版）で「過度な連続アクセス」「大量のデータ取得を目的とした継続的・断続的なアクセス」が
禁止されているため、次を守る:
- 同一サイトへのアクセス間隔は3秒以上
- 詳細ページは既定で上位30体まで。取得済みのものは24時間以内は再取得しない
- 対戦中の追加取得は、環境データに無い相手の分だけ
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

from . import base
from .base import RAW_DIR, SNAP_DIR, fetch_html, now_iso, read_snapshot, write_snapshot

BASE = "https://champs.pokedb.tokyo/"
SOURCE = "pokedb"
RULE_SINGLE = 0
DEFAULT_TOP = 30
REFRESH_HOURS = 24
base.MIN_INTERVAL = 3.0

# pokedbのキー（図鑑番号-フォルム番号）→ このアプリのid。-00 と地方フォルムは自動で解決し、残りをここで指定
KEY_OVERRIDES = {
    "0128-01": "taurospaldeacombat", "0128-02": "taurospaldeablaze", "0128-03": "taurospaldeaaqua",
    "0670-05": "floetteeternal", "0678-01": "meowsticf", "0711-01": "gourgeistsmall", "0711-02": "gourgeistlarge",
    "0711-03": "gourgeistsuper", "0745-01": "lycanrocmidnight", "0745-02": "lycanrocdusk",
    "0849-01": "toxtricitylowkey", "0876-01": "indeedeef", "0902-01": "basculegionf",
    "0931-01": "squawkabillyblue", "0931-02": "squawkabillyyellow", "0931-03": "squawkabillywhite",
}
SECTIONS = {
    "技": "moves", "特性": "abilities", "能力補正": "natures", "持ち物": "items", "同じチーム": "teammates",
    "倒したポケモン": "ko_pokemon", "倒した技": "ko_moves", "倒されたポケモン": "koed_by_pokemon",
    "倒された技": "koed_by_moves",
}
SECTION_TABLE = {
    "moves": "moves", "abilities": "abilities", "natures": "natures", "items": "items", "teammates": "pokemon",
    "ko_pokemon": "pokemon", "ko_moves": "moves", "koed_by_pokemon": "pokemon", "koed_by_moves": "moves",
}
STAT_LETTER = {"H": "hp", "A": "atk", "B": "def", "C": "spa", "D": "spd", "S": "spe"}
RATE_RE = re.compile(r"([\d.]+)\s*%")


def _soup(html: str):
    from bs4 import BeautifulSoup

    return BeautifulSoup(html, "html.parser")


# ---------------------------------------------------------------------------
# 名前・キーの解決
# ---------------------------------------------------------------------------

def _key_to_id(key: str, name: str = "") -> Optional[str]:
    from engine.data import dex

    D = dex()
    if key in KEY_OVERRIDES:
        return KEY_OVERRIDES[key]
    num, form = key.split("-")
    num = int(num)
    if form == "00":
        cands = [p for p in D.pokemon.rows if p["num"] == num and not p["forme"]]
        if cands:
            return cands[0]["id"]
    if name:
        p = D.pokemon.get(name)
        if p:
            return p["id"]
    return None


def _name_index() -> dict[str, str]:
    """表示名 → id（同じチーム欄など名前だけの箇所で使う）。検索APIの一覧を1日1回だけ取る。"""
    cache = SNAP_DIR / "pokedb_names.json"
    if cache.exists():
        d = json.loads(cache.read_text(encoding="utf-8"))
        if datetime.fromisoformat(d["fetched_at"]) > datetime.now().astimezone() - timedelta(days=7):
            return d["names"]
    raw = fetch_html(BASE + "api/pokemon/search?rule=0", SOURCE, save_raw=False)
    names = {}
    for p in json.loads(raw)["pokemons"]:
        pid = _key_to_id(p["pokemon_key"], p["display_name"])
        if pid:
            names[p["display_name"]] = pid
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"fetched_at": now_iso(), "names": names}, ensure_ascii=False), encoding="utf-8")
    return names


def _resolve(kind: str, name: str, names: dict[str, str]) -> Optional[dict]:
    from engine.data import dex

    D = dex()
    name = re.sub(r"\s*\(\s*[A-Z]↑\s*[A-Z]↓\s*\)\s*$", "", name).strip()  # 性格の「(S↑ C↓)」を除く
    if kind == "pokemon":
        pid = names.get(name)
        r = D.pokemon.get(pid) if pid else D.pokemon.get(name)
    else:
        r = getattr(D, kind).get(name)
    return r


# ---------------------------------------------------------------------------
# パーサ
# ---------------------------------------------------------------------------

def parse_list(html: str, base_url: str = BASE) -> dict:
    """一覧ページ → {season, updated, ranking:[{rank,key,name,url}]}"""
    soup = _soup(html)
    seasons = [int(x) for x in re.findall(r"season=(\d+)&(?:amp;)?rule=", html)]
    upd = None
    for tag in soup.select(".season-action-tags .tag"):
        t = tag.get_text(strip=True)
        if re.match(r"\d{4}/\d+/\d+", t):
            upd = t
    ranking = []
    for a in soup.select("a.list-pokemon"):
        m = re.search(r"/pokemon/show/([\d]+-[\d]+)", a["href"])
        if not m:
            continue
        rank_el, name_el = a.select_one(".pokemon-rank"), a.select_one(".pokemon-name")
        ranking.append({
            "rank": int(rank_el.get_text(strip=True)) if rank_el else len(ranking) + 1,
            "key": m.group(1), "name": name_el.get_text(" ", strip=True) if name_el else "",
            "url": urljoin(base_url, a["href"]),
        })
    return {"season": max(seasons) if seasons else None, "updated": upd, "ranking": ranking}


def _section_items(container) -> list[tuple[str, Optional[float]]]:
    out = []
    for li in container.select("li.usage-list-item") or container.select("li"):
        name_el = li.select_one(".usage-name")
        rate_el = li.select_one(".usage-rate")
        if name_el:
            name = name_el.get_text(" ", strip=True)
        else:
            name = re.sub(r"^\d+\s+", "", RATE_RE.split(li.get_text(" ", strip=True))[0]).strip()
        m = RATE_RE.search(rate_el.get_text(strip=True) if rate_el else li.get_text(" ", strip=True))
        if name:
            out.append((name, float(m.group(1)) if m else None))
    return out


def parse_detail(html: str, names: Optional[dict[str, str]] = None) -> dict:
    """詳細ページ → 各項目 [{id, ja, rate}]（rateは%。同じチーム等はrate無しで順位順）。"""
    names = names or {}
    soup = _soup(html)
    res: dict[str, list] = {v: [] for v in SECTIONS.values()}
    res["sp"] = []

    # 技（data-move-detail にJSONで入っている）
    for el in soup.select("[data-move-detail]"):
        try:
            d = json.loads(el["data-move-detail"])
        except Exception:  # noqa: BLE001
            continue
        r = _resolve("moves", d.get("name", ""), names)
        if r and not any(x["id"] == r["id"] for x in res["moves"]):
            res["moves"].append({"id": r["id"], "ja": r["ja"], "rate": d.get("rate")})

    # 見出しごとのカード
    for title in soup.find_all(["h3", "div"]):
        cls = title.get("class") or []
        if title.name == "div" and "title" not in cls:
            continue
        text = title.get_text(" ", strip=True)
        key = SECTIONS.get(text)
        if not key or key == "moves" or res[key]:
            continue
        container = title.find_parent(class_="card-content") or title.find_parent(class_="card")
        if container is None:
            continue
        for name, rate in _section_items(container):
            r = _resolve(SECTION_TABLE[key], name, names)
            if r and not any(x["id"] == r["id"] for x in res[key]):
                row = {"id": r["id"], "ja": r["ja"]}
                if rate is not None:
                    row["rate"] = rate
                res[key].append(row)
            elif not r:
                res.setdefault("_unresolved", []).append(f"{key}:{name}")

    # 能力ポイント（「個別」表示の方を使う）
    raw = soup.select_one("[x-show=\"statViewMode === 'raw'\"]")
    if raw is not None:
        for li in raw.select("li.usage-list-item"):
            spread = {s: 0 for s in STAT_LETTER.values()}
            for chip in li.select(".pokemon-stat-spread__chip"):
                lab = chip.select_one(".pokemon-stat-spread__label")
                val = chip.select_one(".pokemon-stat-spread__value")
                if lab and val and lab.get_text(strip=True) in STAT_LETTER and val.get_text(strip=True).isdigit():
                    spread[STAT_LETTER[lab.get_text(strip=True)]] = int(val.get_text(strip=True))
            rate_el = li.select_one(".usage-rate")
            m = RATE_RE.search(rate_el.get_text(strip=True)) if rate_el else None
            name_el = li.select_one(".usage-name")
            res["sp"].append({"spread": spread, "rate": float(m.group(1)) if m else None,
                              "label": name_el.get_text(" ", strip=True) if name_el else ""})
    return res


# ---------------------------------------------------------------------------
# 取得
# ---------------------------------------------------------------------------

def _fresh(entry: Optional[dict], hours: float = REFRESH_HOURS) -> bool:
    if not entry or not entry.get("fetched_at"):
        return False
    return datetime.fromisoformat(entry["fetched_at"]) > datetime.now().astimezone() - timedelta(hours=hours)


def collect(season: Optional[int] = None, top: int = DEFAULT_TOP, rule: int = RULE_SINGLE,
            only: Optional[list[str]] = None, force: bool = False, **_: object) -> dict:
    """一覧と、上位top体（またはonlyの種族）の詳細を取得して usage.json を更新する。"""
    from engine.data import dex

    D = dex()
    prev = read_snapshot("usage") or {}
    lurl = f"{BASE}pokemon/list?rule={rule}" + (f"&season={season}" if season else "")
    if (not force and only and prev.get("ranking") and _fresh({"fetched_at": prev.get("list_fetched_at")})
            and (season is None or prev.get("season") == season)):
        lst = {"season": prev["season"], "updated": prev.get("source_updated"), "ranking": prev["ranking"]}
        list_fetched = prev.get("list_fetched_at")
    else:
        lst = parse_list(fetch_html(lurl, SOURCE), lurl)
        list_fetched = now_iso()
    season = lst["season"] or season
    ranking = []
    for r in lst["ranking"]:
        pid = r.get("id") or _key_to_id(r["key"], r["name"])
        ranking.append({"rank": r["rank"], "id": pid, "ja": D.pokemon[pid]["ja"] if pid else r["name"],
                        "key": r["key"], "name": r["name"]})
    if prev.get("season") != season:
        prev = {}
    pokemon = dict(prev.get("pokemon", {}))
    names = _name_index()

    by_id = {r["id"]: r for r in ranking if r["id"]}
    if only:
        targets = [by_id[i] for i in only if i in by_id]
    else:
        targets = [r for r in ranking if r["id"]][:top]
    errors, fetched = [], 0
    for r in targets:
        if not force and _fresh(pokemon.get(r["id"])):
            continue
        url = f"{BASE}pokemon/show/{r['key']}?season={season}&rule={rule}"
        try:
            det = parse_detail(fetch_html(url, SOURCE), names)
            det.update(fetched_at=now_iso(), url=url, key=r["key"])
            pokemon[r["id"]] = det
            fetched += 1
        except Exception as e:  # noqa: BLE001
            errors.append({"id": r["id"], "error": str(e)[:200]})
    snap = {
        "source": "ポケモンバトルデータベース", "source_url": BASE, "season": season,
        "season_label": f"シーズンM-{season}", "rule": "single", "source_updated": lst.get("updated"),
        "list_fetched_at": list_fetched, "fetched_at": now_iso(),
        "ranking": ranking, "pokemon": pokemon, "errors": errors,
        "unresolved_ranking": [r["name"] for r in ranking if not r["id"]],
    }
    write_snapshot("usage", snap)
    snap["_fetched_now"] = fetched
    return snap


def collect_opendata(season: Optional[int] = None) -> dict:
    """公開データ（上位構築。完了したシーズンのみ）を取得して top_teams.json に書く。"""
    from engine.data import dex

    D = dex()
    if season is None:
        cur = (read_snapshot("usage") or {}).get("season")
        season = (cur - 1) if cur else None
    if not season:
        raise RuntimeError("シーズン番号が不明。先に update を実行する")
    url = f"{BASE}opendata/s{season}_single_ranked_teams.json"
    data = json.loads(fetch_html(url, SOURCE, save_raw=False))
    teams = []
    for t in data.get("teams", []):
        mons = []
        for m in t.get("team", []):
            form = (m.get("form") or "").replace("のすがた", "")
            pid = (_key_to_id(m["id"], m.get("pokemon", "") if not form or form == m.get("pokemon") else "")
                   or _key_to_id(m["id"], form) or _key_to_id(m["id"], f"{m.get('pokemon', '')}({form})"))
            it = D.items.get(m.get("item", "")) if m.get("item") else None
            mons.append({"id": pid, "ja": D.pokemon[pid]["ja"] if pid else m.get("form"), "key": m["id"],
                         "item": it["en"] if it else m.get("item")})
        teams.append({"rank": t["rank"], "rating": t["rating_value"], "team": mons})
    out = {"source": "ポケモンバトルデータベース 公開データ", "url": url, "season": season,
           "season_label": data.get("season"), "updated_at": data.get("updated_at"), "fetched_at": now_iso(),
           "teams": teams}
    write_snapshot("top_teams", out)
    return out


def probe() -> None:
    """保存済みの生HTMLでパーサを試す（ネットワークに出ない）。"""
    idx = json.loads((RAW_DIR / SOURCE / "index.json").read_text(encoding="utf-8"))
    for name, meta in idx.items():
        path = RAW_DIR / SOURCE / f"{name}.html"
        html = path.read_text(encoding="utf-8")
        if "/pokemon/list" in meta["url"]:
            r = parse_list(html)
            print(meta["url"], "season", r["season"], "件数", len(r["ranking"]), r["ranking"][:3])
        elif "/pokemon/show/" in meta["url"]:
            d = parse_detail(html)
            print(meta["url"], json.dumps({k: v[:3] for k, v in d.items()}, ensure_ascii=False)[:1500])


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="ポケモンバトルデータベースから環境データを取得")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe", help="保存済みHTMLでパーサを確認（通信なし）")
    u = sub.add_parser("update", help="一覧と上位の詳細を取得")
    u.add_argument("--top", type=int, default=DEFAULT_TOP)
    u.add_argument("--season", type=int)
    u.add_argument("--only", nargs="*", help="このアプリのid（例: garchomp）")
    u.add_argument("--force", action="store_true", help="24時間以内に取得済みでも取り直す")
    o = sub.add_parser("opendata", help="上位構築の公開データ（前シーズン）を取得")
    o.add_argument("--season", type=int)
    a = ap.parse_args(argv)
    if a.cmd == "probe":
        probe()
    elif a.cmd == "update":
        s = collect(a.season, a.top, only=a.only, force=a.force)
        print(f"{s['season_label']}（サイト更新 {s.get('source_updated')}）: ランキング{len(s['ranking'])}件 / "
              f"詳細 保持{len(s['pokemon'])}件・今回取得{s['_fetched_now']}件 / エラー{len(s['errors'])}件")
        if s["unresolved_ranking"]:
            print("名前を解決できなかったポケモン:", "、".join(s["unresolved_ranking"]))
    else:
        s = collect_opendata(a.season)
        print(f"{s['season_label']} 上位構築 {len(s['teams'])}件（更新 {s['updated_at']}）")


if __name__ == "__main__":
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    main()
