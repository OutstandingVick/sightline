"""The Desktop backend routes (dashboard/plugin_api.py) over a real FastAPI app."""

import importlib.util
import json
import pathlib

import pytest
from fakes import FakeClient

import sightline.state
import sightline.wallet

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_api():
    spec = importlib.util.spec_from_file_location("sightline_plugin_api_test", ROOT / "dashboard" / "plugin_api.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def api(monkeypatch, keypair):
    c = FakeClient(lamports=1_000_000_000)
    monkeypatch.setattr(sightline.wallet, "Client", lambda *a, **k: c)
    mod = _load_api()
    monkeypatch.setattr(mod, "_state_module", lambda: sightline.state)
    app = fastapi.FastAPI()
    app.include_router(mod.router, prefix="/api/plugins/sightline")
    return TestClient(app)


def test_routes_are_read_only_plus_revoke():
    routes = {(m, r.path) for r in _load_api().router.routes for m in r.methods}
    assert routes == {("GET", "/state"), ("POST", "/revoke")}


def test_state_route_shape(api, keypair, grant_any):
    body = api.get("/api/plugins/sightline/state").json()
    assert body["pubkey"] == str(keypair.pubkey())
    assert body["balances"]["sol"] == "1"
    assert body["grants"][0]["id"] == grant_any.id
    assert body["recent_audit"][0]["event"] == "grant_created"


def test_revoke_route(api, grant_any):
    from sightline import audit, grants

    r = api.post("/api/plugins/sightline/revoke", json={"id": grant_any.id})
    assert r.status_code == 200 and r.json()["grant"]["status"] == "revoked"
    assert grants.get(grant_any.id).status() == "revoked"
    last = audit.entries()[-1]
    assert last["event"] == "grant_revoked" and last["data"]["id"] == grant_any.id


def test_revoke_rejects_bad_and_unknown_ids(api):
    assert api.post("/api/plugins/sightline/revoke", json={"id": "../x"}).status_code == 400
    assert api.post("/api/plugins/sightline/revoke", json={"id": "g_ffff"}).status_code == 404
    assert api.post("/api/plugins/sightline/revoke", json={}).status_code == 422


def test_no_route_can_create_or_widen(api):
    for path in ("/grant", "/grants", "/create", "/policy", "/state"):
        assert api.post(f"/api/plugins/sightline{path}", json={"cap": "1000"}).status_code in (404, 405)


def test_responses_never_contain_the_secret(api, keypair, grant_any):
    secret_b58 = str(keypair)
    secret_bytes = json.dumps(list(bytes(keypair)))[1:-1]
    seed_hex = bytes(keypair)[:32].hex()
    texts = [api.get("/api/plugins/sightline/state").text,
             api.post("/api/plugins/sightline/revoke", json={"id": grant_any.id}).text]
    for text in texts:
        assert secret_b58 not in text
        assert secret_bytes not in text
        assert seed_hex not in text
        assert "secret" not in text.lower()


def test_real_loader_finds_the_package(monkeypatch):
    """Without the test shim, plugin_api loads the sightline package from the folder above."""
    monkeypatch.delenv("SIGHTLINE_SECRET_KEY", raising=False)
    mod = _load_api()
    app = fastapi.FastAPI()
    app.include_router(mod.router)
    body = TestClient(app).get("/state").json()
    assert body["pubkey"] is None and body["network"] == "devnet"


def test_state_limit_is_clamped(api):
    from sightline import audit

    for _ in range(5):
        audit.append("decision", {"verdict": "BLOCK", "intent": {}})
    assert len(api.get("/api/plugins/sightline/state?limit=2").json()["recent_audit"]) == 2
    assert len(api.get("/api/plugins/sightline/state?limit=0").json()["recent_audit"]) == 1
