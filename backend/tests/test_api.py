import time

from conftest import FakeSource, make_movie, mark_ready

import decide.main as main_module
from decide.config import Settings
from decide.main import create_app
from fastapi.testclient import TestClient


def _wait_for_idle(test_client, timeout_s: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        status = test_client.get("/api/library/status").json()
        if status["state"] == "idle" and status["item_count"] > 0:
            return status
        time.sleep(0.05)
    raise AssertionError(f"sync never finished: {status}")


def test_healthz(client):
    test_client, _ = client
    response = test_client.get("/api/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_setup_status_starts_unconfigured(client):
    test_client, _ = client
    body = test_client.get("/api/setup/status").json()
    assert body["stage"] == "unconfigured"
    assert body["server_name"] is None


def test_sync_requires_configuration(client):
    test_client, _ = client
    response = test_client.post("/api/library/sync", json={})
    assert response.status_code == 409


def test_sync_endpoint_populates_library(client):
    test_client, app = client
    mark_ready()
    movies = [make_movie(i) for i in range(1, 6)]
    app.state.sync.source_factory = lambda: FakeSource(movies)

    response = test_client.post("/api/library/sync", json={"full": True})
    assert response.status_code == 202
    assert response.json() == {"started": True}

    status = _wait_for_idle(test_client)
    assert status["item_count"] == 5
    assert status["unusable_count"] == 0
    assert status["stage"] == "ready"
    assert status["last_synced_at"] is not None


def test_second_sync_while_running_conflicts(client):
    test_client, app = client
    mark_ready()

    class SlowSource(FakeSource):
        def fetch_movies(self, section_keys, updated_since, progress=None):
            time.sleep(0.4)
            yield from super().fetch_movies(section_keys, updated_since, progress)

    app.state.sync.source_factory = lambda: SlowSource([make_movie(1)])
    assert test_client.post("/api/library/sync", json={}).status_code == 202
    assert test_client.post("/api/library/sync", json={}).status_code == 409
    _wait_for_idle(test_client)


def test_env_config_skips_wizard_and_boot_syncs(tmp_path, monkeypatch):
    movies = [make_movie(i) for i in range(1, 4)]
    monkeypatch.setattr(main_module, "_make_source", lambda: FakeSource(movies))
    settings = Settings(
        data_dir=tmp_path / "data",
        enable_jobs=False,
        env_plex_token="env-token-abcdef123456",
        env_plex_url="http://192.0.2.1:32400",
        env_plex_sections=["1"],
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        assert test_client.get("/api/setup/status").json()["stage"] == "ready"
        status = _wait_for_idle(test_client)
        assert status["item_count"] == 3


def test_token_never_appears_in_responses(client):
    test_client, app = client
    token = "PLEXTOKENxyzzy987654321"
    mark_ready(token=token)
    app.state.sync.source_factory = lambda: FakeSource([make_movie(1)])
    test_client.post("/api/library/sync", json={"full": True})
    _wait_for_idle(test_client)

    for path in ("/api/setup/status", "/api/library/status", "/api/healthz"):
        assert token not in test_client.get(path).text


def test_poll_unknown_pin_is_404(client):
    test_client, _ = client
    response = test_client.get("/api/setup/pin/doesnotexist")
    assert response.status_code == 404
    assert "Start the sign-in again" in response.json()["detail"]


def test_choose_server_without_token_is_400(client):
    test_client, _ = client
    response = test_client.post("/api/setup/server", json={})
    assert response.status_code == 400
    assert "Sign in with Plex" in response.json()["detail"]


def test_choose_server_unreachable_is_502_with_guidance(client):
    test_client, _ = client
    response = test_client.post(
        "/api/setup/server",
        json={"url": "http://127.0.0.1:9", "token": "pasted-token-123456"},
    )
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Can't reach Plex at http://127.0.0.1:9" in detail
    assert "Check the server is running" in detail


def test_settings_cache_and_signout(client):
    test_client, app = client
    mark_ready()
    stats = test_client.get("/api/settings/cache").json()
    assert stats["entries"] == 0 and stats["cap_bytes"] > 0

    assert test_client.post("/api/settings/cache/clear").json()["freed_bytes"] == 0

    signout = test_client.post("/api/settings/signout")
    assert signout.json()["stage"] == "unconfigured"
    assert test_client.get("/api/setup/status").json()["stage"] == "unconfigured"
