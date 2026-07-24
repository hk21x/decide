from conftest import make_movie, mark_ready, seed_items
from starlette.websockets import WebSocketDisconnect


def _cookie(resp) -> dict[str, str]:
    return {"Cookie": resp.headers["set-cookie"].split(";")[0]}


def _make_session(test_client, app):
    mark_ready()
    seed_items([make_movie(i) for i in range(1, 31)])
    created = test_client.post(
        "/api/sessions", json={"display_name": "Harry", "deck_size": 20}
    )
    host = _cookie(created)
    test_client.cookies.clear()
    return created.json(), host


def test_ws_rejects_without_cookie(client):
    test_client, app = client
    created, _ = _make_session(test_client, app)
    with test_client.websocket_connect(f"/api/sessions/{created['id']}/live") as ws:
        try:
            ws.receive_json()
            raise AssertionError("expected close")
        except WebSocketDisconnect as closed:
            assert closed.code == 4401


def test_joined_progress_match_and_unmatch_events(client):
    test_client, app = client
    created, host = _make_session(test_client, app)
    sid = created["id"]

    with test_client.websocket_connect(
        f"/api/sessions/{sid}/live", headers=host
    ) as host_ws:
        # Guest joins -> joined event reaches the host's socket.
        join = test_client.post(f"/api/sessions/{sid}/join", json={"display_name": "Dee"})
        guest = _cookie(join)
        test_client.cookies.clear()
        event = host_ws.receive_json()
        assert event["type"] == "joined"
        assert event["display_name"] == "Dee"

        deck = test_client.get(f"/api/sessions/{sid}/deck", headers=host).json()
        target = deck["items"][0]["id"]

        # Host swipes right -> progress only (no match yet).
        test_client.post(
            f"/api/sessions/{sid}/swipes",
            json={"swipes": [{"item_id": target, "direction": 1}]},
            headers=host,
        )
        event = host_ws.receive_json()
        assert event["type"] == "progress"
        assert event["display_name"] == "Harry"
        assert event["swiped"] == 1 and event["total"] == 20

        # Guest swipes right -> progress, then the match lands live.
        test_client.post(
            f"/api/sessions/{sid}/swipes",
            json={"swipes": [{"item_id": target, "direction": 1}]},
            headers=guest,
        )
        assert host_ws.receive_json()["type"] == "progress"
        event = host_ws.receive_json()
        assert event["type"] == "match"
        assert event["item_id"] == target
        assert len(event["participant_ids"]) == 2

        # Guest undoes -> progress, then unmatch.
        test_client.delete(f"/api/sessions/{sid}/swipes/{target}", headers=guest)
        assert host_ws.receive_json()["type"] == "progress"
        event = host_ws.receive_json()
        assert event["type"] == "unmatch"
        assert event["item_id"] == target


def test_complete_event_when_everyone_finishes(client):
    test_client, app = client
    created, host = _make_session(test_client, app)
    sid = created["id"]
    deck = test_client.get(f"/api/sessions/{sid}/deck", headers=host).json()
    batch = {
        "swipes": [{"item_id": item["id"], "direction": 0} for item in deck["items"]]
    }

    with test_client.websocket_connect(
        f"/api/sessions/{sid}/live", headers=host
    ) as ws:
        test_client.post(f"/api/sessions/{sid}/swipes", json=batch, headers=host)
        assert ws.receive_json()["type"] == "progress"
        assert ws.receive_json()["type"] == "complete"  # solo session, all done


def test_matches_include_right_names(client):
    test_client, app = client
    created, host = _make_session(test_client, app)
    sid = created["id"]
    deck = test_client.get(f"/api/sessions/{sid}/deck", headers=host).json()
    target = deck["items"][0]["id"]
    test_client.post(
        f"/api/sessions/{sid}/swipes",
        json={"swipes": [{"item_id": target, "direction": 1}]},
        headers=host,
    )
    matches = test_client.get(f"/api/sessions/{sid}/matches", headers=host).json()
    assert matches["matches"][0]["right_names"] == ["Harry"]


def test_summary_by_id_requires_participation(client):
    test_client, app = client
    created, host = _make_session(test_client, app)
    sid = created["id"]
    assert test_client.get(f"/api/sessions/{sid}/summary").status_code == 401
    summary = test_client.get(f"/api/sessions/{sid}/summary", headers=host)
    assert summary.status_code == 200
    assert summary.json()["join_code"] == created["join_code"]
    assert summary.json()["filters"]["unwatched_only"] is True