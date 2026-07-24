import json
import time

from decide import db
from decide.services.matches import apply_swipes, undo_swipe


def _mk_session(sid="s1", deck=("10", "11", "12"), participants=("p1", "p2")):
    conn = db.connect()
    now = int(time.time())
    conn.execute(
        "INSERT INTO sessions (id, join_code, host_participant_id, filters_json, "
        "deck_json, state, created_at, expires_at) VALUES (?, ?, ?, '{}', ?, 'open', ?, ?)",
        (sid, f"C{sid[:5].upper()}", participants[0], json.dumps(list(deck)), now, now + 3600),
    )
    for pid in participants:
        conn.execute(
            "INSERT INTO participants (id, session_id, display_name, joined_at) "
            "VALUES (?, ?, ?, ?)",
            (pid, sid, pid.upper(), now),
        )
    conn.commit()
    return conn


def _add_participant(conn, sid, pid):
    conn.execute(
        "INSERT INTO participants (id, session_id, display_name, joined_at) "
        "VALUES (?, ?, ?, ?)",
        (pid, sid, pid.upper(), int(time.time())),
    )
    conn.commit()


def _match_items(conn, sid):
    return {r["item_id"] for r in conn.execute(
        "SELECT item_id FROM matches WHERE session_id = ?", (sid,)
    )}


def test_two_person_match(dbenv):
    conn = _mk_session()
    first = apply_swipes(conn, "s1", "p1", [("10", 1), ("11", 0)])
    assert first.new_matches == []
    second = apply_swipes(conn, "s1", "p2", [("10", 1), ("11", 1)])
    assert second.new_matches == ["10"]  # 11 has p1's left swipe
    assert _match_items(conn, "s1") == {"10"}


def test_solo_participant_matches_instantly(dbenv):
    conn = _mk_session(sid="solo", participants=("p1",))
    outcome = apply_swipes(conn, "solo", "p1", [("10", 1)])
    assert outcome.new_matches == ["10"]


def test_three_person_requires_all(dbenv):
    conn = _mk_session(sid="s3", participants=("p1", "p2", "p3"))
    apply_swipes(conn, "s3", "p1", [("10", 1)])
    partial = apply_swipes(conn, "s3", "p2", [("10", 1)])
    assert partial.new_matches == []
    final = apply_swipes(conn, "s3", "p3", [("10", 1)])
    assert final.new_matches == ["10"]


def test_late_joiner_keeps_match(dbenv):
    conn = _mk_session()
    apply_swipes(conn, "s1", "p1", [("10", 1)])
    apply_swipes(conn, "s1", "p2", [("10", 1)])
    assert _match_items(conn, "s1") == {"10"}

    _add_participant(conn, "s1", "p3")
    # P3 actively swiping left does NOT delete the standing match —
    # it just reads as "2 of 3" in the UI.
    outcome = apply_swipes(conn, "s1", "p3", [("10", 0)])
    assert outcome.removed_matches == []
    assert _match_items(conn, "s1") == {"10"}


def test_retraction_by_changing_direction_removes_match(dbenv):
    conn = _mk_session()
    apply_swipes(conn, "s1", "p1", [("10", 1)])
    apply_swipes(conn, "s1", "p2", [("10", 1)])
    outcome = apply_swipes(conn, "s1", "p2", [("10", 0)])
    assert outcome.removed_matches == ["10"]
    assert _match_items(conn, "s1") == set()


def test_undo_removes_swipe_and_match(dbenv):
    conn = _mk_session()
    apply_swipes(conn, "s1", "p1", [("10", 1)])
    apply_swipes(conn, "s1", "p2", [("10", 1)])
    outcome = undo_swipe(conn, "s1", "p2", "10")
    assert outcome.accepted == 1
    assert outcome.removed_matches == ["10"]
    (count,) = conn.execute(
        "SELECT COUNT(*) FROM swipes WHERE session_id = 's1' AND participant_id = 'p2'"
    ).fetchone()
    assert count == 0


def test_undo_left_swipe_touches_no_match(dbenv):
    conn = _mk_session()
    apply_swipes(conn, "s1", "p1", [("10", 0)])
    outcome = undo_swipe(conn, "s1", "p1", "10")
    assert outcome.accepted == 1
    assert outcome.removed_matches == []


def test_undo_nothing_is_noop(dbenv):
    conn = _mk_session()
    outcome = undo_swipe(conn, "s1", "p1", "99")
    assert outcome.accepted == 0


def test_replay_is_idempotent(dbenv):
    deck = tuple(str(i) for i in range(100, 130))
    conn = _mk_session(sid="replay", deck=deck, participants=("p1", "p2"))
    batch = [(item, 1 if i % 2 else 0) for i, item in enumerate(deck)]
    apply_swipes(conn, "replay", "p1", batch)
    apply_swipes(conn, "replay", "p1", batch)  # offline queue replay
    (count,) = conn.execute(
        "SELECT COUNT(*) FROM swipes WHERE session_id = 'replay' AND participant_id = 'p1'"
    ).fetchone()
    assert count == 30
