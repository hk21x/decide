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
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(migrations.MIGRATIONS) == 2
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
