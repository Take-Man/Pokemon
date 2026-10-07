"""情報源アダプタの共通部分。

各サイトごとに Collector を1つ作る。取得は「コードで決まった手順」で行い、LLMにブラウザ操作はさせない。
- ページ取得は fetch_html()（標準ライブラリの urllib。ブラウザを使った取り直しはしない）
- 取得したHTMLは data/snapshots/_raw/<source>/ に保存し、パーサ修正時に再取得せず検証できるようにする

相手のサイトに迷惑をかけないための決まり（すべての取得がここを通る）:
- 身元を偽らない: User-Agent は個人用ツールであることを名乗る（ブラウザを装わない）
- robots.txt を守る: 取得前に確認し、禁止されたURLは取らない（robots.txt は1日1回だけ取り直す）
- 1件ずつ: 同時に複数のジョブが動いても、同じサイトへは1件ずつ間隔（HOST_INTERVAL、既定 MIN_INTERVAL 秒）を空ける
- 1日の上限: 同じサイトへのリクエストは DAILY_LIMIT 件まで（プログラムの誤りで取り続けないための安全装置）
- 断られたら止める: 403・429・5xx を受けたら、そのサイトへの取得を COOLDOWN 秒（Retry-After があればそれ）止める。
  取り直しや別の手段での回避はしない
"""
from __future__ import annotations

import gzip
import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SNAP_DIR = ROOT / "data" / "snapshots" / "current"
RAW_DIR = ROOT / "data" / "snapshots" / "_raw"
ACCESS_FILE = RAW_DIR / "_access.json"  # サイトごとの1日の件数・停止期限・robots.txt（プロセスをまたいで共有）
UA_TOKEN = "GyakudameNote"
UA = f"{UA_TOKEN}/0.2 (personal, non-commercial local tool)"
MIN_INTERVAL = 1.5  # 同一サイトへの最小アクセス間隔（秒）
HOST_INTERVAL: dict[str, float] = {}  # サイトごとの間隔（各アダプタが設定する）
DAILY_LIMIT = 150  # 同一サイトへの1日のリクエスト上限
COOLDOWN = 3600  # 断られたときに止める秒数（Retry-After が無いとき）
ROBOTS_HOURS = 24

_lock = threading.Lock()
_last_access: dict[str, float] = {}


class FetchBlocked(RuntimeError):
    """サイト側に断られた・上限に達した・robots.txt で禁止されている。続けて取りに行かない。"""


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _load_access() -> dict:
    try:
        return json.loads(ACCESS_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_access(st: dict) -> None:
    ACCESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ACCESS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ACCESS_FILE)


def access_status(host: str) -> dict:
    """画面・CLI向け: 今日の件数・上限・停止中ならその期限。"""
    h = _load_access().get(host, {})
    until = h.get("cooldown_until")
    if until and datetime.fromisoformat(until) <= datetime.now().astimezone():
        until = None
    return {"today": (h.get("days") or {}).get(_today(), 0), "limit": DAILY_LIMIT, "cooldown_until": until,
            "cooldown_reason": h.get("cooldown_reason") if until else None}


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _throttle(host: str) -> None:
    wait = HOST_INTERVAL.get(host, MIN_INTERVAL) - (time.time() - _last_access.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_access[host] = time.time()


def _cooldown_seconds(err: urllib.error.HTTPError) -> int:
    """Retry-After（秒か日時）があればそれに従う（最低1分）。無ければ COOLDOWN。"""
    ra = (err.headers.get("Retry-After") or "").strip() if err.headers else ""
    if ra.isdigit():
        return max(60, int(ra))
    if ra:
        try:
            return max(60, int((parsedate_to_datetime(ra) - datetime.now(timezone.utc)).total_seconds()))
        except Exception:  # noqa: BLE001
            pass
    return COOLDOWN


def _request(host: str, h: dict, st: dict, url: str, timeout: float) -> str:
    """1件取得する（_lock の中で呼ぶ）。間隔・上限・停止を守り、断られたら停止を記録して FetchBlocked。"""
    until = h.get("cooldown_until")
    if until and datetime.fromisoformat(until) > datetime.now().astimezone():
        raise FetchBlocked(f"{host} は {until[11:16]} まで取得を止めている（{h.get('cooldown_reason', '')}）")
    days = {k: v for k, v in (h.get("days") or {}).items() if k >= (datetime.now().date() - timedelta(days=7)).isoformat()}
    if days.get(_today(), 0) >= DAILY_LIMIT:
        raise FetchBlocked(f"{host} への今日の取得が上限（{DAILY_LIMIT}件）に達した。明日以降に取り直す")
    _throttle(host)
    days[_today()] = days.get(_today(), 0) + 1
    h["days"] = days
    _save_access(st)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja,en;q=0.8",
                                               "Accept-Encoding": "gzip"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return body.decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    except urllib.error.HTTPError as he:
        if he.code in (403, 429) or he.code >= 500:
            sec = _cooldown_seconds(he)
            h["cooldown_until"] = (datetime.now().astimezone() + timedelta(seconds=sec)).isoformat(timespec="seconds")
            h["cooldown_reason"] = f"HTTP {he.code}"
            _save_access(st)
            raise FetchBlocked(f"{host} に断られた（HTTP {he.code}）。{sec // 60}分は取得しない") from he
        raise RuntimeError(f"HTTP {he.code}: {url}") from he


def _robots_ok(host: str, h: dict, st: dict, url: str, timeout: float) -> bool:
    rb = h.get("robots") or {}
    fresh = rb.get("fetched_at") and \
        datetime.fromisoformat(rb["fetched_at"]) > datetime.now().astimezone() - timedelta(hours=ROBOTS_HOURS)
    if not fresh:
        p = urlparse(url)
        try:
            text = _request(host, h, st, f"{p.scheme}://{p.netloc}/robots.txt", timeout)
        except RuntimeError as e:
            if isinstance(e, FetchBlocked) or "HTTP 404" not in str(e):
                raise
            text = ""  # robots.txt が無ければ制限なし
        rb = h["robots"] = {"fetched_at": now_iso(), "text": text}
        _save_access(st)
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(rb["text"].splitlines())
    return rp.can_fetch(UA_TOKEN, url)


def fetch_html(url: str, source: str, *, save_raw: bool = True, timeout: float = 20.0) -> str:
    """URLの本文を返す。上の決まりを守れないときは FetchBlocked（取り直さない）。"""
    host = urlparse(url).netloc
    with _lock:  # 同時に複数のジョブが動いても、同じプロセスからは1件ずつ取る
        st = _load_access()
        h = st.setdefault(host, {})
        if not _robots_ok(host, h, st, url, timeout):
            raise FetchBlocked(f"robots.txt で禁止されているため取得しない: {url}")
        html = _request(host, h, st, url, timeout)
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
