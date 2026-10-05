"""APP_UI による画面の切替（現行UI / simple UI）。"""
import importlib

from fastapi.testclient import TestClient


def _client(monkeypatch, ui):
    if ui is None:
        monkeypatch.delenv("APP_UI", raising=False)
    else:
        monkeypatch.setenv("APP_UI", ui)
    import app.server as server
    importlib.reload(server)
    return TestClient(server.app)


def test_default_is_classic(monkeypatch):
    html = _client(monkeypatch, None).get("/").text
    assert "/static/app.js?v=" in html


def test_simple_ui(monkeypatch):
    c = _client(monkeypatch, "simple")
    assert "/static/js/main.js" in c.get("/").text
    assert c.get("/api/meta").status_code == 200  # APIは共通
    monkeypatch.delenv("APP_UI")
    importlib.reload(importlib.import_module("app.server"))
