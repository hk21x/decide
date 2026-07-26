"""Stats, crown, album, collections and players — the v0.2 feature set."""

import time

from conftest import make_movie, mark_ready, seed_items

from decide import db, migrations
from decide.models import DeckFilters
from decide.services import deck


def _cookie(resp):
    return {"Cookie": resp.headers["set-cookie"].split(";")[0]}


def _session_with_two(test_client, deck_size=20):
    mark_ready()
    seed_items([make_movie(i) for i in range(1, 31)])
    created = test_client.post(
        "/api/sessions", json={"display_name": "Harry", "deck_size": deck_size}
    )
    host = _cookie(created)
    test_client.cookies.clear()
    sid = created.json()["id"]
    join = test_client.post(f"/api/sessions/{sid}/join", json={"display_name": "Dee"})
    guest = _cookie(join)
    test_client.cookies.clear()
    return sid, host, guest


def _swipe(test_client, sid, headers, item_id, direction):
    resp = test_client.post(
        f"/api/sessions/{sid}/swipes",
        json={"swipes": [{"item_id": item_id, "direction": direction}]},
        headers=headers,
    )
    assert resp.status_code == 200
    return resp.json()


def test_migration_v2_applied(dbenv):
    conn = db.connect()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(migrations.MIGRATIONS)
    columns = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    assert "collections_json" in columns
    session_cols = {r[1] for r in conn.execute("PRAGMA table_info(sessions)")}
    assert "crowned_item_id" in session_cols
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "album" in tables


def test_collection_filter_and_listing(dbenv):
    seed_items(
        [
            make_movie(1, collections=["Studio Ghibli"]),
            make_movie(2, collections=["Studio Ghibli"]),
            make_movie(3, collections=["Studio Ghibli", "Favourites"]),
            make_movie(4, collections=["Loner Collection"]),  # only 1 film
            make_movie(5),
        ]
    )
    assert deck.preview_count(DeckFilters(collection="Studio Ghibli")) == 3
    assert deck.preview_count(DeckFilters()) == 5


def test_collection_shortfall_names_culprit(dbenv):
    seed_items(
        [make_movie(1, collections=["Tiny"]), make_movie(2, collections=["Tiny"])]
        + [make_movie(i) for i in range(3, 40)]
    )
    try:
        deck.build_deck("s", DeckFilters(collection="Tiny"), 30)
        raise AssertionError("expected DeckTooSmall")
    except deck.DeckTooSmall as err:
        assert err.culprit == "collection"
        assert "collection filter" in err.message


def test_stats_pairwise_agreement(client):
    test_client, app = client
    sid, host, guest = _session_with_two(test_client)
    deck_items = test_client.get(f"/api/sessions/{sid}/deck", headers=host).json()["items"]
    ids = [item["id"] for item in deck_items]

    # Harry: right on 0,1, left on 2,3.  Dee: right on 0, left on 1,2, right on 3.
    for item, direction in zip(ids[:4], [1, 1, 0, 0]):
        _swipe(test_client, sid, host, item, direction)
    for item, direction in zip(ids[:4], [1, 0, 0, 1]):
        _swipe(test_client, sid, guest, item, direction)

    stats = test_client.get(f"/api/sessions/{sid}/stats", headers=host).json()
    assert len(stats["pairs"]) == 1
    pair = stats["pairs"][0]
    assert pair["both_swiped"] == 4
    assert pair["agreed"] == 2  # item0 both right, item2 both left
    assert pair["both_right"] == 1
    assert pair["pct"] == 50
    assert {pair["a_name"], pair["b_name"]} == {"Harry", "Dee"}


def test_crown_requires_match_and_broadcasts(client):
    test_client, app = client
    sid, host, guest = _session_with_two(test_client)
    deck_items = test_client.get(f"/api/sessions/{sid}/deck", headers=host).json()["items"]
    target = deck_items[0]["id"]

    # Not yet a match -> refused.
    refused = test_client.post(
        f"/api/sessions/{sid}/crown", json={"item_id": target}, headers=host
    )
    assert refused.status_code == 400

    _swipe(test_client, sid, host, target, 1)
    _swipe(test_client, sid, guest, target, 1)

    with test_client.websocket_connect(f"/api/sessions/{sid}/live", headers=guest) as ws:
        crowned = test_client.post(
            f"/api/sessions/{sid}/crown", json={"item_id": target}, headers=host
        )
        assert crowned.status_code == 200
        event = ws.receive_json()
        assert event == {"type": "crowned", "item_id": target}

    summary = test_client.get(f"/api/sessions/{sid}/summary", headers=host).json()
    assert summary["crowned_item_id"] == target


def test_album_save_survives_purge(client):
    test_client, app = client
    sid, host, guest = _session_with_two(test_client)
    deck_items = test_client.get(f"/api/sessions/{sid}/deck", headers=host).json()["items"]
    target = deck_items[0]["id"]
    title = deck_items[0]["title"]

    # Only matches can be kept.
    early = test_client.post(
        f"/api/sessions/{sid}/album", json={"item_id": target}, headers=host
    )
    assert early.status_code == 400

    _swipe(test_client, sid, host, target, 1)
    _swipe(test_client, sid, guest, target, 1)
    saved = test_client.post(
        f"/api/sessions/{sid}/album",
        json={"item_id": target, "crowned": True},
        headers=host,
    )
    assert saved.status_code == 200
    assert saved.json()["names"] == ["Harry", "Dee"]
    assert saved.json()["crowned"] is True

    # Saving again without the crown must not un-crown it.
    again = test_client.post(
        f"/api/sessions/{sid}/album", json={"item_id": target}, headers=host
    )
    assert again.json()["crowned"] is True

    # Hard-delete the session as the purge job would: the stub remains.
    from decide.jobs import purge_blocking

    conn = db.connect()
    conn.execute(
        "UPDATE sessions SET created_at = ? WHERE id = ?",
        (int(time.time()) - 8 * 86400, sid),
    )
    conn.commit()
    purge_blocking()
    (sessions_left,) = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE id = ?", (sid,)
    ).fetchone()
    assert sessions_left == 0

    album = test_client.get("/api/album").json()
    assert len(album["entries"]) == 1
    assert album["entries"][0]["title"] == title

    emptied = test_client.delete(f"/api/album/{sid}/{target}").json()
    assert emptied["entries"] == []


def test_players_endpoint_degrades_gracefully(client):
    test_client, app = client
    mark_ready()
    assert test_client.get("/api/players").json() == {"players": []}
    refused = test_client.post(
        "/api/players/play", json={"item_id": "1", "player_id": "nope"}
    )
    assert refused.status_code == 502
    assert "Check Plex is open" in refused.json()["detail"]


def test_series_records_and_media_filter(dbenv):
    seed_items(
        [make_movie(i) for i in range(1, 4)]
        + [
            make_movie(
                100 + i,
                media_type="show",
                seasons=2 + i,
                runtime_min=None,
                title=f"Show {i}",
            )
            for i in range(1, 4)
        ]
    )
    assert deck.preview_count(DeckFilters(media="films")) == 3
    assert deck.preview_count(DeckFilters(media="series")) == 3
    conn = db.connect()
    row = conn.execute("SELECT media_type, seasons FROM items WHERE id = '101'").fetchone()
    assert row["media_type"] == "show" and row["seasons"] == 3


def test_rejoin_reissues_identity(client):
    test_client, app = client
    sid, host, guest = _session_with_two(test_client)
    # Simulate a lost cookie: rejoin with the stored participant id.
    progress = test_client.get(f"/api/sessions/{sid}/progress", headers=host).json()
    my_pid = progress["participants"][0]["participant_id"]

    rejoin = test_client.post(
        f"/api/sessions/{sid}/rejoin", json={"participant_id": my_pid}
    )
    assert rejoin.status_code == 200
    assert rejoin.json()["participant_id"] == my_pid
    fresh_cookie = {"Cookie": rejoin.headers["set-cookie"].split(";")[0]}
    test_client.cookies.clear()
    deck_resp = test_client.get(f"/api/sessions/{sid}/deck", headers=fresh_cookie)
    assert deck_resp.status_code == 200
    # Participant count unchanged — no seat burned.
    summary = test_client.get(f"/api/sessions/{sid}/summary", headers=fresh_cookie).json()
    assert len(summary["participants"]) == 2

    unknown = test_client.post(
        f"/api/sessions/{sid}/rejoin", json={"participant_id": "not-a-real-pid"}
    )
    assert unknown.status_code == 404


def test_access_endpoints_roundtrip(client):
    test_client, app = client
    initial = test_client.get("/api/settings/access").json()
    assert initial["local_url"] is None and initial["remote_url"] is None

    saved = test_client.put(
        "/api/settings/access",
        json={
            "local_url": "http://192.168.1.25:8080/",
            "remote_url": "https://harrybox.tail1234.ts.net",
        },
    ).json()
    assert saved["local_url"] == "http://192.168.1.25:8080"  # trailing slash trimmed
    assert saved["remote_url"] == "https://harrybox.tail1234.ts.net"

    cleared = test_client.put(
        "/api/settings/access", json={"local_url": "", "remote_url": ""}
    ).json()
    assert cleared["local_url"] is None and cleared["remote_url"] is None


def test_push_vapid_and_subscription(client):
    test_client, app = client
    sid, host, guest = _session_with_two(test_client)

    vapid = test_client.get("/api/push/vapid").json()
    assert len(vapid["public_key"]) > 40  # urlsafe b64 of an EC point

    sub = {
        "endpoint": "https://push.example/sub/abc123",
        "keys": {"p256dh": "BFakeKey", "auth": "authsecret"},
    }
    stored = test_client.post(f"/api/sessions/{sid}/push", json=sub, headers=host)
    assert stored.status_code == 200 and stored.json()["subscribed"] is True
    # Idempotent upsert.
    test_client.post(f"/api/sessions/{sid}/push", json=sub, headers=host)
    (count,) = db.connect().execute("SELECT COUNT(*) FROM push_subs").fetchone()
    assert count == 1

    # Unauthenticated subscription refused.
    refused = test_client.post(f"/api/sessions/{sid}/push", json=sub)
    assert refused.status_code == 401
