"""保存先の差し替え口。ローカル版はファイル（data/user・state/）、サービス版は利用者ごとの Supabase。

state.py・matches.py は保存先を直接触らず、current() が返す Store を通す。
サービス版はリクエストごとに use() で利用者の Store を入れる（contextvars なので同時のリクエストで混ざらない）。
"""
from __future__ import annotations

import contextvars
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


class Store:
    """保存先の共通の形。文書（dict）をそのまま出し入れする。"""

    local = False  # True なら Claude 向けの state/ 書き出し・計算履歴・外部取得を行う

    # パーティ
    def list_teams(self) -> list[dict]: raise NotImplementedError
    def get_team(self, tid: str) -> Optional[dict]: raise NotImplementedError
    def put_team(self, team: dict) -> None: raise NotImplementedError
    def delete_team(self, tid: str) -> None: raise NotImplementedError

    # 設定（選択中のパーティ active・現在の対戦 current_match）
    def get_settings(self) -> dict: raise NotImplementedError
    def put_settings(self, s: dict) -> None: raise NotImplementedError

    # 相手の6体（opponent）・選出予想（prediction）
    def get_doc(self, name: str) -> Optional[dict]: raise NotImplementedError
    def put_doc(self, name: str, doc: dict) -> None: raise NotImplementedError
    def doc_mtime(self, name: str) -> float: raise NotImplementedError

    # 対戦
    def list_matches(self) -> list[dict]: raise NotImplementedError
    def get_match(self, mid: str) -> Optional[dict]: raise NotImplementedError
    def put_match(self, m: dict) -> None: raise NotImplementedError
    def delete_match(self, mid: str) -> None: raise NotImplementedError

    # 回数に上限のある機能（画像の取り込み）を1回使う。上限なら例外。ローカル版は数えない
    def use_quota(self, kind: str) -> None:
        return None


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


class FileStore(Store):
    """ローカル版: これまでどおり data/user と state/ のファイル。場所は state・matches の定数を毎回見る（テストで差し替えられる）。"""

    local = True

    @staticmethod
    def _state():
        from . import state

        return state

    def _team_path(self, tid: str) -> Path:
        return self._state().TEAMS_DIR / f"{tid}.json"

    def list_teams(self) -> list[dict]:
        d = self._state().TEAMS_DIR
        return [t for t in (_read(p, None) for p in sorted(d.glob("*.json"))) if t] if d.exists() else []

    def get_team(self, tid: str) -> Optional[dict]:
        return _read(self._team_path(tid), None)

    def put_team(self, team: dict) -> None:
        _write(self._team_path(team["id"]), team)

    def delete_team(self, tid: str) -> None:
        p = self._team_path(tid)
        if p.exists():
            p.unlink()

    def get_settings(self) -> dict:
        return _read(self._state().SETTINGS_FILE, {})

    def put_settings(self, s: dict) -> None:
        _write(self._state().SETTINGS_FILE, s)

    def _doc_path(self, name: str) -> Path:
        st = self._state()
        return {"opponent": st.OPP_FILE, "prediction": st.PRED_FILE}[name]

    def get_doc(self, name: str) -> Optional[dict]:
        return _read(self._doc_path(name), None)

    def put_doc(self, name: str, doc: dict) -> None:
        _write(self._doc_path(name), doc)

    def doc_mtime(self, name: str) -> float:
        p = self._doc_path(name)
        return p.stat().st_mtime if p.exists() else 0.0

    @staticmethod
    def _match_dir() -> Path:
        from . import matches

        return matches.MATCH_DIR

    def list_matches(self) -> list[dict]:
        d = self._match_dir()
        if not d.exists():
            return []
        return [m for m in (_read(p, None) for p in d.glob("*.json")) if m]

    def get_match(self, mid: str) -> Optional[dict]:
        p = self._match_dir() / f"{mid}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put_match(self, m: dict) -> None:
        _write(self._match_dir() / f"{m['id']}.json", m)

    def delete_match(self, mid: str) -> None:
        p = self._match_dir() / f"{mid}.json"
        if p.exists():
            p.unlink()


_DEFAULT = FileStore()
_current: contextvars.ContextVar[Store] = contextvars.ContextVar("store", default=_DEFAULT)


def current() -> Store:
    return _current.get()


@contextmanager
def use(store: Store) -> Iterator[Store]:
    """このブロックの中だけ保存先を差し替える。"""
    token = _current.set(store)
    try:
        yield store
    finally:
        _current.reset(token)
