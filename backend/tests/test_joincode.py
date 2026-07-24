import json
import time

from decide import db
from decide.services import joincode


def test_alphabet_and_length():
    for _ in range(200):
        code = joincode.generate()
        assert len(code) == 6
        assert all(c in joincode.ALPHABET for c in code)
        for confusable in "ILOU":
            assert confusable not in code


def test_normalise_confusables():
    assert joincode.normalise("il0o1u") == "1100 1V".replace(" ", "")
    assert joincode.normalise("  ab2xyz  ") == "AB2XYZ"


def test_allocate_retries_on_collision(dbenv, monkeypatch):
    conn = db.connect()
    conn.execute(
        "INSERT INTO sessions (id, join_code, filters_json, deck_json, state, "
        "created_at, expires_at) VALUES ('s1', 'TAKEN1', '{}', '[]', 'open', ?, ?)",
        (int(time.time()), int(time.time()) + 3600),
    )
    conn.commit()

    codes = iter(["TAKEN1", "FRESH2"])
    monkeypatch.setattr(joincode, "generate", lambda: next(codes))
    assert joincode.allocate(conn) == "FRESH2"


def test_allocate_gives_up(dbenv, monkeypatch):
    conn = db.connect()
    conn.execute(
        "INSERT INTO sessions (id, join_code, filters_json, deck_json, state, "
        "created_at, expires_at) VALUES ('s1', 'TAKEN1', ?, '[]', 'open', 0, 0)",
        (json.dumps({}),),
    )
    conn.commit()
    monkeypatch.setattr(joincode, "generate", lambda: "TAKEN1")
    try:
        joincode.allocate(conn, attempts=3)
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass
