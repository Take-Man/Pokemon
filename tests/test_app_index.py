"""python -m app が配信する画面。"""
from fastapi.testclient import TestClient

from app.server import app


def test_index_serves_ui():
    c = TestClient(app)
    r = c.get("/")
    assert "/static/js/main.js" in r.text and "no-cache" in r.headers["cache-control"]
    assert c.get("/static/js/main.js").status_code == 200
    assert c.get("/api/meta").status_code == 200
