"""バックグラウンド取得ジョブ。選出予想は即時にルールベースで返し、追加データ取得はここで並列に走らせる。"""
from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .base import now_iso

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="collector")
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def submit(kind: str, fn: Callable[[Callable[[int, int], None]], object],
           on_done: Callable[[object], None] | None = None) -> str:
    """fn(report) をバックグラウンドで実行する。report(済んだ件数, 全件数) で進捗を残せる。

    同じ kind のジョブが実行中なら、新しく走らせずにそのジョブの id を返す（同じ取得を重ねない）。
    """
    with _lock:
        for j in _jobs.values():
            if j["kind"] == kind and j["status"] == "running":
                return j["id"]
        jid = uuid.uuid4().hex[:8]
        _jobs[jid] = {"id": jid, "kind": kind, "status": "running", "started_at": now_iso()}

    def report(done: int, total: int) -> None:
        with _lock:
            _jobs[jid].update(done=done, total=total)

    def run():
        try:
            res = fn(report)
            with _lock:
                _jobs[jid].update(status="done", finished_at=now_iso())
                if isinstance(res, dict) and res.get("blocked"):
                    _jobs[jid]["warning"] = res["blocked"]
            if on_done:
                on_done(res)
        except Exception as e:  # noqa: BLE001
            with _lock:
                _jobs[jid].update(status="error", error=str(e)[:300], trace=traceback.format_exc()[-800:],
                                  finished_at=now_iso())

    _pool.submit(run)
    return jid


def list_jobs(limit: int = 20) -> list[dict]:
    with _lock:
        return [dict(j) for j in list(_jobs.values())[-limit:]]
