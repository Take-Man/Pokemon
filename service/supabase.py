"""サービス版の保存先（Supabase）と、ログインの確認。

- 読み書きは利用者のアクセストークンで PostgREST を呼ぶ。RLS が効くので、本人の行しか触れない
- 管理用キー（service role）はアカウント削除だけで使う
- 1リクエストの中で同じ行を何度も読むので、読んだ結果を Store に覚えておく（書いたら置き換える）
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

from app.storage import Store


def _env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"環境変数 {name} が未設定")
    return v


def url() -> str:
    return _env("SUPABASE_URL").rstrip("/")


def anon_key() -> str:
    return _env("SUPABASE_ANON_KEY")


_client: Optional[httpx.Client] = None


def client() -> httpx.Client:
    """接続を使い回す（関数の実体が続けて使われる間）。"""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=10.0)
    return _client


class StoreError(RuntimeError):
    """Supabase との通信に失敗した。"""


class LimitExceeded(RuntimeError):
    """プランの上限に達した。kind: teams / matches、limit: 上限の数。"""

    def __init__(self, kind: str, limit: int):
        super().__init__(f"{kind}:{limit}")
        self.kind, self.limit = kind, limit


# ---------------------------------------------------------------------------
# ログインの確認
# ---------------------------------------------------------------------------

@dataclass
class User:
    id: str
    email: str
    token: str


_user_cache: dict[str, tuple[float, User]] = {}
_user_lock = threading.Lock()
USER_CACHE_SECONDS = 60


def verify(token: str) -> Optional[User]:
    """アクセストークンを Supabase Auth に確かめる。結果は60秒覚える（毎回の往復を省く）。"""
    now = time.time()
    with _user_lock:
        hit = _user_cache.get(token)
        if hit and hit[0] > now:
            return hit[1]
    try:
        r = client().get(f"{url()}/auth/v1/user", headers={"apikey": anon_key(), "Authorization": f"Bearer {token}"})
    except httpx.HTTPError as e:
        raise StoreError(f"Supabase Auth に接続できない: {e}") from e
    if r.status_code != 200:
        return None
    d = r.json()
    u = User(id=d["id"], email=d.get("email") or "", token=token)
    with _user_lock:
        if len(_user_cache) > 1000:
            _user_cache.clear()
        _user_cache[token] = (now + USER_CACHE_SECONDS, u)
    return u


def delete_user(user_id: str) -> None:
    """アカウントを消す（データは on delete cascade で消える）。管理用キーを使う。"""
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    r = client().delete(f"{url()}/auth/v1/admin/users/{user_id}", headers={"apikey": key, "Authorization": f"Bearer {key}"})
    if r.status_code not in (200, 204):
        raise StoreError(f"アカウントを削除できない: HTTP {r.status_code} {r.text[:200]}")


# ---------------------------------------------------------------------------
# 保存先
# ---------------------------------------------------------------------------

def _copy(x: Any) -> Any:
    return None if x is None else json.loads(json.dumps(x))


class SupabaseStore(Store):
    local = False

    def __init__(self, user: User):
        self.user = user
        self._cache: dict[tuple, Any] = {}

    # ---- PostgREST
    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {"apikey": anon_key(), "Authorization": f"Bearer {self.user.token}"}
        h.update(extra or {})
        return h

    def _req(self, method: str, table: str, *, params: Optional[dict] = None, body: Any = None,
             prefer: Optional[str] = None) -> Any:
        try:
            r = client().request(method, f"{url()}/rest/v1/{table}", params=params, json=body,
                                 headers=self._headers({"Prefer": prefer} if prefer else None))
        except httpx.HTTPError as e:
            raise StoreError(f"Supabase に接続できない: {e}") from e
        if r.status_code >= 400:
            msg = r.text
            try:
                msg = r.json().get("message") or msg
            except ValueError:
                pass
            if isinstance(msg, str) and msg.startswith("LIMIT:"):
                _, kind, lim = msg.split(":", 2)
                raise LimitExceeded(kind, int(lim))
            raise StoreError(f"Supabase {method} {table}: HTTP {r.status_code} {str(msg)[:200]}")
        return r.json() if r.content else None

    def _upsert(self, table: str, row: dict, on_conflict: str) -> None:
        self._req("POST", table, params={"on_conflict": on_conflict}, body=dict(row, user_id=self.user.id),
                  prefer="resolution=merge-duplicates,return=minimal")

    def _cached(self, key: tuple, load):
        if key not in self._cache:
            self._cache[key] = load()
        return _copy(self._cache[key])

    # ---- パーティ
    def list_teams(self) -> list[dict]:
        rows = self._cached(("teams",), lambda: self._req("GET", "teams", params={"select": "doc"}))
        return [r["doc"] for r in rows]

    def get_team(self, tid: str) -> Optional[dict]:
        def load():
            rows = self._req("GET", "teams", params={"select": "doc", "id": f"eq.{tid}"})
            return rows[0]["doc"] if rows else None
        return self._cached(("team", tid), load)

    def put_team(self, team: dict) -> None:
        self._upsert("teams", {"id": team["id"], "doc": team}, "user_id,id")
        self._cache[("team", team["id"])] = _copy(team)
        self._cache.pop(("teams",), None)

    def delete_team(self, tid: str) -> None:
        self._req("DELETE", "teams", params={"id": f"eq.{tid}"})
        self._cache[("team", tid)] = None
        self._cache.pop(("teams",), None)

    # ---- 設定・相手・予想（user_state の1行）
    def _state_row(self) -> dict:
        def load():
            rows = self._req("GET", "user_state", params={"select": "settings,opponent,opponent_updated_at,prediction"})
            return rows[0] if rows else {"settings": {}, "opponent": None, "opponent_updated_at": None, "prediction": None}
        return self._cached(("state",), load)

    def _put_state(self, **cols) -> None:
        self._upsert("user_state", cols, "user_id")
        row = self._state_row()
        row.update({k: v for k, v in cols.items() if k in row})
        self._cache[("state",)] = row

    def get_settings(self) -> dict:
        return self._state_row().get("settings") or {}

    def put_settings(self, s: dict) -> None:
        self._put_state(settings=s)

    def get_doc(self, name: str) -> Optional[dict]:
        return self._state_row().get(name)

    def put_doc(self, name: str, doc: dict) -> None:
        if name == "opponent":
            self._put_state(opponent=doc, opponent_updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        else:
            self._put_state(**{name: doc})

    def doc_mtime(self, name: str) -> float:
        t = self._state_row().get(f"{name}_updated_at")
        if not t:
            return 0.0
        from datetime import datetime

        return datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()

    # ---- 対戦
    def list_matches(self) -> list[dict]:
        rows = self._cached(("matches",), lambda: self._req("GET", "matches", params={"select": "doc", "order": "created_at.desc"}))
        return [r["doc"] for r in rows]

    def get_match(self, mid: str) -> Optional[dict]:
        def load():
            rows = self._req("GET", "matches", params={"select": "doc", "id": f"eq.{mid}"})
            return rows[0]["doc"] if rows else None
        return self._cached(("match", mid), load)

    def put_match(self, m: dict) -> None:
        row = {"id": m["id"], "doc": m}
        if m.get("created_at"):
            row["created_at"] = m["created_at"]
        self._upsert("matches", row, "user_id,id")
        self._cache[("match", m["id"])] = _copy(m)
        self._cache.pop(("matches",), None)

    def delete_match(self, mid: str) -> None:
        self._req("DELETE", "matches", params={"id": f"eq.{mid}"})
        self._cache[("match", mid)] = None
        self._cache.pop(("matches",), None)

    # ---- アカウント
    def limits(self) -> dict:
        rows = self._req("POST", "rpc/my_limits", body={})
        return rows[0] if rows else {"plan": "free", "max_teams": None, "max_matches": None, "features": {}}
