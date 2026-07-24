-- Matinee schema v1.
-- Product tables follow the brief (§4.5). items carries five extra columns
-- (imdb_id, tmdb_id, tagline, last_viewed_at, updated_at) required by the
-- brief's §4.2 "fields to persist" list but omitted from the §4.5 sketch.
-- art_cache is server-internal (disk LRU index for the artwork proxy).

CREATE TABLE config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE items (
    id              TEXT PRIMARY KEY,
    guid            TEXT,
    imdb_id         TEXT,
    tmdb_id         TEXT,
    title           TEXT NOT NULL,
    year            INTEGER,
    tagline         TEXT,
    summary         TEXT,
    runtime_min     INTEGER,
    content_rating  TEXT,
    audience_rating REAL,
    genres_json     TEXT,
    directors_json  TEXT,
    cast_json       TEXT,
    thumb           TEXT,
    art             TEXT,
    view_count      INTEGER NOT NULL DEFAULT 0,
    last_viewed_at  INTEGER,
    added_at        INTEGER,
    updated_at      INTEGER,
    unusable        INTEGER NOT NULL DEFAULT 0,
    synced_at       INTEGER
);
CREATE INDEX idx_items_unusable ON items(unusable);
CREATE INDEX idx_items_guid ON items(guid);

CREATE TABLE sessions (
    id                  TEXT PRIMARY KEY,
    join_code           TEXT UNIQUE NOT NULL,
    host_participant_id TEXT,
    filters_json        TEXT NOT NULL,
    deck_json           TEXT NOT NULL,
    state               TEXT NOT NULL DEFAULT 'open',
    created_at          INTEGER NOT NULL,
    expires_at          INTEGER NOT NULL
);

CREATE TABLE participants (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    display_name TEXT NOT NULL,
    joined_at    INTEGER NOT NULL
);
CREATE INDEX idx_participants_session ON participants(session_id);

CREATE TABLE swipes (
    session_id     TEXT NOT NULL,
    participant_id TEXT NOT NULL,
    item_id        TEXT NOT NULL,
    direction      INTEGER NOT NULL,
    created_at     INTEGER NOT NULL,
    PRIMARY KEY (session_id, participant_id, item_id)
);

CREATE TABLE matches (
    session_id TEXT NOT NULL,
    item_id    TEXT NOT NULL,
    matched_at INTEGER NOT NULL,
    PRIMARY KEY (session_id, item_id)
);

CREATE TABLE art_cache (
    cache_key    TEXT PRIMARY KEY,
    size_bytes   INTEGER NOT NULL,
    etag         TEXT NOT NULL,
    last_used_at INTEGER NOT NULL
);
