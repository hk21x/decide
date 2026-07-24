from conftest import FakeSource, make_movie, mark_ready, seed_items

from decide import db
from decide.services.artcache import ArtCache


def test_lru_evicts_oldest_first(dbenv, tmp_path):
    cache = ArtCache(root=tmp_path / "art", cap_bytes=250)
    conn = db.connect()
    for i, key in enumerate(["old", "mid", "new"], start=1):
        cache.store_blocking(key, b"x" * 100)
        conn.execute(
            "UPDATE art_cache SET last_used_at = ? WHERE cache_key = ?", (i * 100, key)
        )
        conn.commit()

    cache.evict_blocking()  # 300 bytes > 250 cap -> evict to <= 225

    remaining = {
        r["cache_key"] for r in conn.execute("SELECT cache_key FROM art_cache")
    }
    assert remaining == {"mid", "new"}
    assert not (tmp_path / "art" / "old.img").exists()
    assert (tmp_path / "art" / "new.img").exists()


def test_store_is_atomic_and_rehit_uses_index(dbenv, tmp_path):
    cache = ArtCache(root=tmp_path / "art", cap_bytes=10_000)
    path, etag = cache.store_blocking("k1", b"hello-poster")
    assert path.read_bytes() == b"hello-poster"
    hit = cache.lookup_blocking("k1")
    assert hit is not None and hit[1] == etag


def test_missing_file_heals_index(dbenv, tmp_path):
    cache = ArtCache(root=tmp_path / "art", cap_bytes=10_000)
    path, _ = cache.store_blocking("k1", b"data")
    path.unlink()
    assert cache.lookup_blocking("k1") is None
    (count,) = db.connect().execute("SELECT COUNT(*) FROM art_cache").fetchone()
    assert count == 0


class FailingSource(FakeSource):
    def fetch_artwork(self, image_path, width, height):
        raise RuntimeError("PMS is down")


def test_art_endpoint_cache_etag_and_placeholder(client):
    test_client, app = client
    mark_ready()
    seed_items([make_movie(1), make_movie(2, art=None)])
    art_bytes = b"\xff\xd8\xff" + b"J" * 500
    app.state.source_factory = lambda: FakeSource([])  # fetch_artwork returns fake jpeg

    class ArtSource(FakeSource):
        def fetch_artwork(self, image_path, width, height):
            return art_bytes, "image/jpeg"

    app.state.source_factory = lambda: ArtSource([])

    first = test_client.get("/api/art/1?kind=poster")
    assert first.status_code == 200
    assert first.headers["content-type"] == "image/jpeg"
    assert first.content == art_bytes
    etag = first.headers["etag"]
    assert etag.startswith('"') and first.headers["cache-control"] == "public, max-age=604800"

    revalidated = test_client.get("/api/art/1?kind=poster", headers={"If-None-Match": etag})
    assert revalidated.status_code == 304

    # No backdrop path stored -> placeholder SVG, short max-age, no disk cache.
    placeholder = test_client.get("/api/art/2?kind=backdrop")
    assert placeholder.status_code == 200
    assert placeholder.headers["content-type"].startswith("image/svg+xml")
    assert "Film 2" in placeholder.text
    assert placeholder.headers["cache-control"] == "public, max-age=300"

    # Upstream failure on an uncached size -> placeholder, not a broken image.
    app.state.source_factory = lambda: FailingSource([])
    fallback = test_client.get("/api/art/1?kind=poster&w=300&h=450")
    assert fallback.status_code == 200
    assert fallback.headers["content-type"].startswith("image/svg+xml")

    # The cached size still serves from disk even though the source is down.
    cached = test_client.get("/api/art/1?kind=poster")
    assert cached.status_code == 200
    assert cached.content == art_bytes

    assert test_client.get("/api/art/does-not-exist").status_code == 404
