"""サービス版（service/main.py）を、Supabase の振る舞いを真似た偽物につないで通しで確かめる。

偽物は PostgREST（select・eq・order・upsert・delete・rpc）と Auth（/auth/v1/user・管理用の削除）だけを真似る。
RLS（本人の行だけ）・パーティの上限・対戦履歴の上限は、supabase/migrations の定義と同じ動きにしている。
"""
import json
import os
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient

URL = "https://fake.supabase.test"
SERVICE_KEY = "sb_secret_test"
USERS = {"tok-a": {"id": "uid-a", "email": "a@example.com"}, "tok-b": {"id": "uid-b", "email": "b@example.com"}}
LIMITS = {"plan": "free", "max_teams": 2, "max_matches": 3, "max_imports_per_day": 2, "features": {}}


class FakeSupabase:
    def __init__(self):
        self.rows = {"teams": [], "matches": [], "user_state": [], "usage_log": []}
        self.calls = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(f"{req.method} {req.url.path}")
        path, q = req.url.path, {k: v[0] for k, v in parse_qs(req.url.query.decode()).items()}
        auth = req.headers.get("authorization", "").removeprefix("Bearer ")
        if path == "/auth/v1/user":
            u = USERS.get(auth)
            return httpx.Response(200, json=u) if u else httpx.Response(401, json={"msg": "invalid"})
        if path.startswith("/auth/v1/admin/users/"):
            if req.headers.get("apikey") != SERVICE_KEY or ("authorization" in req.headers and SERVICE_KEY.startswith("sb_")):
                return httpx.Response(403)  # 新形式のキーは apikey だけで送る
            uid = path.rsplit("/", 1)[1]
            for t in self.rows.values():
                t[:] = [r for r in t if r["user_id"] != uid]
            return httpx.Response(200, json={})
        user = USERS.get(auth)
        if not user:
            return httpx.Response(401, json={"message": "JWT"})
        uid = user["id"]
        table = path.removeprefix("/rest/v1/")
        if table == "rpc/my_limits":
            return httpx.Response(200, json=[LIMITS])
        if table == "rpc/use_quota":  # 直近24時間の回数を数え、上限内なら記録する
            kind = json.loads(req.content)["kind"]
            n = sum(1 for r in self.rows["usage_log"] if r["user_id"] == uid and r["kind"] == kind)
            if n >= LIMITS["max_imports_per_day"]:
                return httpx.Response(400, json={"code": "P0001", "message": f"LIMIT:imports:{LIMITS['max_imports_per_day']}"})
            self.rows["usage_log"].append({"user_id": uid, "kind": kind, "created_at": "2026-10-08T00:00:00Z"})
            return httpx.Response(204)
        mine = [r for r in self.rows[table] if r["user_id"] == uid]  # RLS
        if "id" in q:
            mine = [r for r in mine if r["id"] == q["id"].removeprefix("eq.")]
        if "kind" in q:
            mine = [r for r in mine if r["kind"] == q["kind"].removeprefix("eq.")]
        if req.method == "GET":
            if q.get("order") == "created_at.desc":
                mine.sort(key=lambda r: r.get("created_at") or "", reverse=True)
            cols = q.get("select", "*").split(",")
            return httpx.Response(200, json=[{c: r.get(c) for c in cols} for r in mine])
        if req.method == "DELETE":
            self.rows[table] = [r for r in self.rows[table] if r not in mine]
            return httpx.Response(204)
        if req.method == "POST":
            body = json.loads(req.content)
            assert body["user_id"] == uid  # with check
            keys = q["on_conflict"].split(",")
            hit = next((r for r in self.rows[table] if all(r.get(k) == body.get(k) for k in keys)), None)
            if hit:
                hit.update(body)
                return httpx.Response(201)
            if table == "teams" and len(mine) >= LIMITS["max_teams"]:
                return httpx.Response(400, json={"code": "P0001", "message": f"LIMIT:teams:{LIMITS['max_teams']}"})
            self.rows[table].append(dict(body))
            if table == "matches":
                keep = sorted([r for r in self.rows["matches"] if r["user_id"] == uid],
                              key=lambda r: r.get("created_at") or "", reverse=True)[:LIMITS["max_matches"]]
                self.rows["matches"] = [r for r in self.rows["matches"] if r["user_id"] != uid or r in keep]
            return httpx.Response(201)
        return httpx.Response(405)


@pytest.fixture
def svc(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", URL)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "sb_publishable_test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SERVICE_KEY)
    had = "PBA_USAGE_DATA" in os.environ
    from service import main, supabase as sb

    if not had:  # service.main は読み込み時に既定で使用率データを切る。他のテストに影響させない
        os.environ.pop("PBA_USAGE_DATA", None)
    fake = FakeSupabase()
    monkeypatch.setattr(sb, "_client", httpx.Client(transport=httpx.MockTransport(fake)))
    monkeypatch.setattr(sb, "_user_cache", {})
    return TestClient(main.app), fake


H_A = {"Authorization": "Bearer tok-a"}
H_B = {"Authorization": "Bearer tok-b"}
MEMBERS = [{"species": "garchomp", "nature": "jolly", "sp": {"atk": 32, "spe": 32, "hp": 2}, "ability": "Rough Skin",
            "item": "Life Orb", "moves": ["earthquake", "dragonclaw", "stoneedge", "swordsdance"]},
           {"species": "corviknight", "nature": "impish", "sp": {"hp": 32, "def": 32, "spd": 2}, "ability": "Pressure",
            "item": "Leftovers", "moves": ["bravebird", "roost", "uturn", "bodypress"]},
           {"species": "rotomwash", "nature": "bold", "sp": {"hp": 32, "def": 32, "spa": 2}, "ability": "Levitate",
            "item": "Sitrus Berry", "moves": ["hydropump", "voltswitch", "willowisp", "painsplit"]}]


def test_login_required_and_local_only_routes(svc):
    c, _ = svc
    assert c.get("/api/team").status_code == 401
    assert c.get("/api/team", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/api/types").status_code == 200  # 固定データは未ログインでも
    assert c.get("/api/config").json()["mode"] == "service"
    assert c.post("/api/collect", headers=H_A).status_code == 404  # 外部取得はサービス版に無い
    assert c.get("/api/env", headers=H_A).status_code == 404


def test_full_flow_is_isolated_per_user(svc):
    c, fake = svc
    t = c.get("/api/team", headers=H_A).json()  # 初回はパーティが1つ作られる
    assert c.put("/api/team", headers=H_A, json={"id": t["id"], "name": "本命", "members": MEMBERS}).status_code == 200
    c.put("/api/opponent", headers=H_A, json={"species": ["dragonite", "kingambit", "gholdengo", "toxapex", "archaludon", "rillaboom"]})
    pred = c.post("/api/predict", headers=H_A).json()
    assert pred["opponent"] and pred["job"] is None  # 外部へは取りに行かない
    assert not any("pokedb" in x for x in fake.calls)
    assert c.put("/api/battle", headers=H_A, json={"my_picks": [0, 1], "opp_picks": ["dragonite"]}).status_code == 200
    c.put("/api/battle/live", headers=H_A, json={"field": {"weather": "rain"}})
    r = c.post("/api/battle/records", headers=H_A, json={"kind": "taken", "opp": "dragonite", "my_index": 0, "move": "extremespeed",
                                                         "before": 183, "after": 140, "cond": {}})
    assert r.status_code == 200, r.text
    b = c.get("/api/battle", headers=H_A).json()
    assert b["live"]["field"]["weather"] == "rain" and len([x for x in b["records"] if x["kind"] != "log"]) == 1
    assert b["opp_builds"][0]["inference"]["records"] == 1

    # 別の利用者からは何も見えない
    assert c.get("/api/matches", headers=H_B).json() == []
    assert c.get("/api/battle", headers=H_B).json()["match"] is None
    assert c.get("/api/team", headers=H_B).json()["members"] == []
    assert c.get(f"/api/teams/{t['id']}", headers=H_B).status_code == 404
    assert all(x["id"] != t["id"] for x in c.get("/api/teams", headers=H_B).json())

    acc = c.get("/api/account", headers=H_A).json()
    assert acc["email"] == "a@example.com" and acc["usage"] == {"teams": 1, "matches": 1, "imports_today": 0}


def test_team_limit_and_match_trim(svc):
    c, fake = svc
    c.get("/api/team", headers=H_A)
    assert c.post("/api/teams", headers=H_A, json={"name": "2つ目"}).status_code == 200
    r = c.post("/api/teams", headers=H_A, json={"name": "3つ目"})
    assert r.status_code == 403 and "2件まで" in r.json()["detail"]
    t = c.get("/api/team", headers=H_A).json()
    c.put("/api/team", headers=H_A, json={"id": t["id"], "name": "x", "members": MEMBERS})  # 上書きは上限に数えない
    opps = [["dragonite", "kingambit", "gholdengo", "toxapex", "archaludon", s] for s in
            ("rillaboom", "garchomp", "primarina", "hippowdon", "lucario")]
    for o in opps:
        c.put("/api/opponent", headers=H_A, json={"species": o})
        c.post("/api/predict", headers=H_A)
    assert len(c.get("/api/matches", headers=H_A).json()) == LIMITS["max_matches"]


def test_export_and_delete_account(svc):
    c, fake = svc
    c.get("/api/team", headers=H_A)
    ex = c.get("/api/account/export", headers=H_A).json()
    assert len(ex["teams"]) == 1
    assert c.delete("/api/account", headers=H_A).json() == {"ok": True}
    assert not any(r["user_id"] == "uid-a" for t in fake.rows.values() for r in t)


def test_image_import_has_daily_quota(svc, monkeypatch):
    """画像からの取り込みはサービス版でも使える。外部OCRの費用の歯止めとして、24時間の回数に上限がある。"""
    import base64
    import io

    from PIL import Image

    import screenreader
    from screenreader import ocr

    c, fake = svc
    monkeypatch.setattr(ocr, "get_backend", lambda prefer=None: object())
    monkeypatch.setattr(screenreader, "parse_team_screens", lambda imgs, o=None: {"members": [], "warnings": [], "backend": "fake"})
    buf = io.BytesIO()
    Image.new("RGB", (20, 10)).save(buf, "JPEG")
    body = {"images": ["data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()]}
    assert c.post("/api/team/import-image", headers=H_A, json={"images": ["not-an-image"]}).status_code == 400  # 数えない
    for _ in range(LIMITS["max_imports_per_day"]):
        assert c.post("/api/team/import-image", headers=H_A, json=body).status_code == 200
    r = c.post("/api/team/import-image", headers=H_A, json=body)
    assert r.status_code == 403 and "24時間で2回まで" in r.json()["detail"]
    assert c.post("/api/team/import-image", headers=H_B, json=body).status_code == 200  # 利用者ごと
    assert c.get("/api/account", headers=H_A).json()["usage"]["imports_today"] == 2


def test_image_import_not_counted_when_ocr_service_fails(svc, monkeypatch):
    """OCR サービスの設定・障害で読めなかったときは、取り込みの回数に数えない。"""
    import base64
    import io

    from PIL import Image

    import screenreader
    from screenreader import ocr

    c, fake = svc

    def broken(imgs, o=None):
        raise ocr.OCRUnavailable("Google Cloud Vision: HTTP 403 blocked")

    monkeypatch.setattr(ocr, "get_backend", lambda prefer=None: object())
    monkeypatch.setattr(screenreader, "parse_team_screens", broken)
    buf = io.BytesIO()
    Image.new("RGB", (20, 10)).save(buf, "JPEG")
    body = {"images": ["data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()]}
    for _ in range(LIMITS["max_imports_per_day"] + 1):
        r = c.post("/api/team/import-image", headers=H_A, json=body)
        assert r.status_code == 503 and "読み取りサービス" in r.json()["detail"]
    assert c.get("/api/account", headers=H_A).json()["usage"]["imports_today"] == 0
