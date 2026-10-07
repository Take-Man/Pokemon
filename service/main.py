"""サービス版の入口（Vercel の Python 関数）。ローカル版の /api をそのまま使い、ログインと保存先だけを足す。

- /api/* はログイン（Supabase のアクセストークン）が必要。固定データだけを返すものは未ログインでも使える
- リクエストごとに、保存先をその利用者の Supabase に切り替える（app.storage.use）
- 外部サイトへの取得・Claude向けの書き出しなど、ローカル版だけの機能は404
- 画像からの取り込みは Google Cloud Vision で読む（GOOGLE_VISION_API_KEY）。24時間あたりの回数に上限
- 環境データ（使用率）は既定で使わない（PBA_USAGE_DATA=on で使う。取得先の利用許可が出てから）

ローカルで試す: SUPABASE_URL=... SUPABASE_ANON_KEY=... uvicorn service.main:app --port 8770
"""
from __future__ import annotations

import os

os.environ.setdefault("PBA_USAGE_DATA", "off")

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.concurrency import run_in_threadpool  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from app import storage  # noqa: E402
from app.server import STATIC, api  # noqa: E402

from . import supabase as sb  # noqa: E402

# 未ログインでも使える（固定データだけを返す）
PUBLIC = ("/api/config", "/api/meta", "/api/types", "/api/search", "/api/pokemon/")
# ローカル版だけの機能
LOCAL_ONLY = ("/api/collect", "/api/env", "/api/jobs", "/api/current.md")

app = FastAPI(title="Gyakudame Note")


@app.middleware("http")
async def auth_and_store(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    if path.startswith(LOCAL_ONLY):
        return JSONResponse({"detail": "サービス版では使えない機能"}, status_code=404)
    if path.startswith(PUBLIC):
        return await call_next(request)
    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    try:
        user = await run_in_threadpool(sb.verify, token) if token else None
    except sb.StoreError:
        return JSONResponse({"detail": "ログインの確認に失敗した。時間をおいて試してください"}, status_code=503)
    if user is None:
        return JSONResponse({"detail": "ログインが必要"}, status_code=401)
    request.state.user = user
    with storage.use(sb.SupabaseStore(user)):
        return await call_next(request)


@app.exception_handler(sb.LimitExceeded)
async def on_limit(_request: Request, e: sb.LimitExceeded):
    msg = {"teams": f"保存できるパーティは{e.limit}件まで", "matches": f"残せる対戦履歴は{e.limit}件まで",
           "imports": f"画像からの取り込みは24時間で{e.limit}回まで"}.get(e.kind, f"{e.kind}は{e.limit}まで")
    return JSONResponse({"detail": f"{msg}（いまのプランの上限）", "limit": {"kind": e.kind, "max": e.limit}}, status_code=403)


@app.exception_handler(sb.StoreError)
async def on_store_error(_request: Request, e: sb.StoreError):
    return JSONResponse({"detail": f"データの保存先に接続できない: {e}"}, status_code=503)


@app.get("/api/config")
def config():
    """画面がログインに使う公開の設定（公開キーは、RLSがあるので画面に渡してよいもの）。"""
    return {"mode": "service", "supabase_url": sb.url(), "supabase_anon_key": sb.anon_key(),
            "usage_data": os.environ.get("PBA_USAGE_DATA") != "off"}


@app.get("/api/account")
def get_account(request: Request):
    store: sb.SupabaseStore = storage.current()  # type: ignore[assignment]
    return {"email": request.state.user.email, "limits": store.limits(),
            "usage": {"teams": len(store.list_teams()), "matches": len(store.list_matches()),
                      "imports_today": store.used_today("image_import")}}


@app.get("/api/account/export")
def export_account():
    """自分のデータをまとめて書き出す（パーティ・対戦履歴・設定）。"""
    store = storage.current()
    return {"teams": store.list_teams(), "matches": store.list_matches(), "settings": store.get_settings(),
            "opponent": store.get_doc("opponent")}


@app.delete("/api/account")
def delete_account(request: Request):
    sb.delete_user(request.state.user.id)
    return {"ok": True}


app.include_router(api)


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/privacy", response_class=HTMLResponse)
def privacy():
    return HTMLResponse((STATIC / "privacy.html").read_text(encoding="utf-8"))


@app.get("/terms", response_class=HTMLResponse)
def terms():
    return HTMLResponse((STATIC / "terms.html").read_text(encoding="utf-8"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
