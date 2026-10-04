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


def submit(kind: str, fn: Callable[[], object], on_done: Callable[[object], None] | None = None) -> str:
    jid = uuid.uuid4().hex[:8]
    with _lock:
        _jobs[jid] = {"id": jid, "kind": kind, "status": "running", "started_at": now_iso()}

    def run():
        try:
            res = fn()
            with _lock:
                _jobs[jid].update(status="done", finished_at=now_iso())
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
        return list(_jobs.values())[-limit:]
