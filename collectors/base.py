"""情報源アダプタの共通部分。

各サイトごとに Collector を1つ作る。取得は「コードで決まった手順」で行い、LLMにブラウザ操作はさせない。
- ページ取得は fetch_html()（httpx → 失敗時は Playwright）
- 取得したHTMLは data/snapshots/_raw/<source>/ に保存し、パーサ修正時に再取得せず検証できるようにする
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
SNAP_DIR = ROOT / "data" / "snapshots" / "current"
RAW_DIR = ROOT / "data" / "snapshots" / "_raw"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36 PokemonBattleAssistant/0.1 (personal use)")
MIN_INTERVAL = 1.5  # 同一サイトへの最小アクセス間隔（秒）

_last_access: dict[str, float] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _throttle(host: str) -> None:
    t = _last_access.get(host, 0)
    wait = MIN_INTERVAL - (time.time() - t)
    if wait > 0:
        time.sleep(wait)
    _last_access[host] = time.time()


def fetch_html(url: str, source: str, *, use_browser: Optional[bool] = None, save_raw: bool = True,
               timeout: float = 20.0) -> str:
    """URLのHTMLを返す。use_browser=None なら標準ライブラリ(urllib)で取り、だめなら Playwright。"""
    from urllib.parse import urlparse

    host = urlparse(url).netloc
    html: Optional[str] = None
    err: Optional[Exception] = None
    if use_browser is not True:
        try:
            import gzip
            import urllib.error
            import urllib.request

            _throttle(host)
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.8",
                                                       "Accept-Encoding": "gzip"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    body = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    charset = r.headers.get_content_charset() or "utf-8"
                    html = body.decode(charset, errors="replace")
            except urllib.error.HTTPError as he:
                raise RuntimeError(f"HTTP {he.code} server={he.headers.get('server')} "
                                   f"body={he.read()[:200]!r}") from he
        except Exception as e:  # noqa: BLE001
            err = e
    if html is None and use_browser is not False:
        try:
            from playwright.sync_api import sync_playwright

            _throttle(host)
            with sync_playwright() as p:
                b = p.chromium.launch()
                pg = b.new_page(user_agent=UA, locale="ja-JP")
                pg.goto(url, wait_until="networkidle", timeout=timeout * 1000)
                html = pg.content()
                b.close()
        except Exception as e:  # noqa: BLE001
            err = err or e
    if html is None:
        raise RuntimeError(f"取得失敗: {url}: {err}")
    if save_raw:
        d = RAW_DIR / source
        d.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha1(url.encode()).hexdigest()[:10]
        (d / f"{name}.html").write_text(html, encoding="utf-8")
        idx = d / "index.json"
        m = json.loads(idx.read_text(encoding="utf-8")) if idx.exists() else {}
        m[name] = {"url": url, "fetched_at": now_iso()}
        idx.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return html


def write_snapshot(name: str, data: dict) -> Path:
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    p = SNAP_DIR / f"{name}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    return p


def read_snapshot(name: str) -> Optional[dict]:
    p = SNAP_DIR / f"{name}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))
