import time

from conftest import make_movie, mark_ready, seed_items

from decide import db


def _cookie(resp) -> dict[str, str]:
    raw = resp.headers.get("set-cookie")
    assert raw, "expected a Set-Cookie header"
    return {"Cookie": raw.split(";")[0]}


def _setup_session(test_client, app, deck_size=20, movie_count=40):
    mark_ready()
    seed_items([make_movie(i) for i in range(1, movie_count + 1)])
    resp = test_client.post(
        "/api/sessions",
        json={"display_name": "Harry", "deck_size": deck_size},
    )
    assert resp.status_code == 201, resp.text
    host_headers = _cookie(resp)
    test_client.cookies.clear()
    return resp.json(), host_headers


def test_full_two_person_flow(client):
    test_client, app = client
    created, host = _setup_session(test_client, app)
    sid, code = created["id"], created["join_code"]
    assert len(code) == 6
    assert created["deck_size"] == 20

    # Lookup by code — case-insensitive, confusables forgiven.
    looked_up = test_client.get(f"/api/sessions/{code.lower()}")
    assert looked_up.status_code == 200
    assert looked_up.json()["id"] == sid
    assert len(looked_up.json()["participants"]) == 1

    # Second person joins.
    join = test_client.post(f"/api/sessions/{sid}/join", json={"display_name": "Dee"})
    assert join.status_code == 200
    guest = _cookie(join)
    test_client.cookies.clear()

    # Deck: same frozen order for both, full metadata.
    deck_host = test_client.get(f"/api/sessions/{sid}/deck", headers=host).json()
    deck_guest = test_client.get(f"/api/sessions/{sid}/deck", headers=guest).json()
    assert [i["id"] for i in deck_host["items"]] == [i["id"] for i in deck_guest["items"]]
    assert len(deck_host["items"]) == 20
    first = deck_host["items"][0]
    assert first["title"] and first["has_poster"]

    # Both swipe right on the first film; the second response reports a match.
    target = first["id"]
    one = test_client.post(
        f"/api/sessions/{sid}/swipes",
        json={"swipes": [{"item_id": target, "direction": 1}]},
        headers=host,
    )
    assert one.status_code == 200 and one.json()["new_matches"] == []
    two = test_client.post(
        f"/api/sessions/{sid}/swipes",
        json={"swipes": [{"item_id": target, "direction": 1}]},
        headers=guest,
    )
    assert two.json()["new_matches"] == [target]

    matches = test_client.get(f"/api/sessions/{sid}/matches", headers=host).json()
    assert len(matches["matches"]) == 1
    entry = matches["matches"][0]
    assert entry["item"]["id"] == target
    assert entry["right_count"] == 2 and entry["participant_count"] == 2

    # Undo by the guest retracts the match.
    undone = test_client.delete(
        f"/api/sessions/{sid}/swipes/{target}", headers=guest
    ).json()
    assert undone["removed_matches"] == [target]
    assert (
        test_client.get(f"/api/sessions/{sid}/matches", headers=host).json()["matches"]
        == []
    )

    # Progress reflects both people.
    progress = test_client.get(f"/api/sessions/{sid}/progress", headers=host).json()
    swiped = {p["display_name"]: p["swiped"] for p in progress["participants"]}
    assert swiped == {"Harry": 1, "Dee": 0}
    assert progress["all_complete"] is False


def test_thirty_swipe_replay_lands_once(client):
    test_client, app = client
    created, host = _setup_session(test_client, app, deck_size=30)
    sid = created["id"]
    deck = test_client.get(f"/api/sessions/{sid}/deck", headers=host).json()["items"]
    batch = {
        "swipes": [
            {"item_id": item["id"], "direction": 1 if i % 2 else 0}
            for i, item in enumerate(deck)
        ]
    }
    for _ in range(2):  # the offline queue replaying after reconnect
        resp = test_client.post(f"/api/sessions/{sid}/swipes", json=batch, headers=host)
        assert resp.status_code == 200

    (count,) = db.connect().execute(
        "SELECT COUNT(*) FROM swipes WHERE session_id = ?", (sid,)
    ).fetchone()
    assert count == 30


def test_swipe_outside_deck_rejected(client):
    test_client, app = client
    created, host = _setup_session(test_client, app)
    sid = created["id"]
    resp = test_client.post(
        f"/api/sessions/{sid}/swipes",
        json={"swipes": [{"item_id": "999999", "direction": 1}]},
        headers=host,
    )
    assert resp.status_code == 400
    assert "aren't in this session's deck" in resp.json()["detail"]


def test_deck_requires_participation(client):
    test_client, app = client
    created, _host = _setup_session(test_client, app)
    resp = test_client.get(f"/api/sessions/{created['id']}/deck")
    assert resp.status_code == 401
    assert "Join this session" in resp.json()["detail"]


def test_unknown_session_and_code(client):
    test_client, app = client
    mark_ready()
    assert test_client.get("/api/sessions/NOPE99").status_code == 404
    assert (
        test_client.get("/api/sessions/deadbeef/deck").status_code == 404
    )


def test_lookup_rate_limited_to_ten_per_minute(client):
    test_client, app = client
    for i in range(10):
        resp = test_client.get("/api/sessions/AAAAA1")
        assert resp.status_code == 404, f"attempt {i}"
    eleventh = test_client.get("/api/sessions/AAAAA1")
    assert eleventh.status_code == 429
    assert eleventh.headers.get("retry-after") == "60"


def test_expired_session_is_410(client):
    test_client, app = client
    created, host = _setup_session(test_client, app)
    sid = created["id"]
    conn = db.connect()
    conn.execute(
        "UPDATE sessions SET expires_at = ? WHERE id = ?", (int(time.time()) - 10, sid)
    )
    conn.commit()
    resp = test_client.get(f"/api/sessions/{sid}/deck", headers=host)
    assert resp.status_code == 410
    assert resp.json()["detail"] == "This session has closed."


def test_fifth_participant_rejected(client):
    test_client, app = client
    created, _host = _setup_session(test_client, app)
    sid = created["id"]
    for name in ("Two", "Three", "Four"):
        resp = test_client.post(f"/api/sessions/{sid}/join", json={"display_name": name})
        assert resp.status_code == 200
        test_client.cookies.clear()
    fifth = test_client.post(f"/api/sessions/{sid}/join", json={"display_name": "Five"})
    assert fifth.status_code == 409
    assert "four people" in fifth.json()["detail"]


def test_create_session_names_culprit_when_too_few(client):
    test_client, app = client
    mark_ready()
    seed_items([make_movie(i, runtime_min=150) for i in range(1, 31)])
    resp = test_client.post(
        "/api/sessions",
        json={
            "display_name": "Harry",
            "filters": {"max_runtime": 90},
        },
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "too_few_films"
    assert detail["culprit"] == "max_runtime"
    assert detail["would_yield"] == 30
    assert "runtime limit" in detail["message"]
