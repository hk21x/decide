# Plex integration notes (M0 research)

**Date checked: 22 July 2026.** Sources are cited per section. Every claim below was
verified against the linked documentation or the python-plexapi source on `master`
that day — nothing is from memory. Items that can only be confirmed against a live
PMS are marked **⚠ verify live** with the milestone where that happens.

python-plexapi repo: <https://github.com/pkkid/python-plexapi> · docs:
<https://python-plexapi.readthedocs.io/en/latest/>

---

## 1 · Authentication and X-Plex headers

- PMS accepts the token in the **`X-Plex-Token` header**, and any `X-Plex-*` header
  may alternatively be sent as a query-string argument.
  Source: [developer.plex.tv/pms](https://developer.plex.tv/pms/).
- **Matinee rule (C1):** always header, never query string — query strings can land in
  PMS access logs and proxy logs. Note that plexapi's own
  `PlexServer.url(key, includeToken=True)` builds token-in-query URLs
  (`…{delim}X-Plex-Token={token}`) — **we never use those URLs**; all our upstream
  requests go through a `requests.Session` with the header set. plexapi's internal
  `_headers()` does send `X-Plex-Token` as a header for its own API calls, so normal
  plexapi usage is fine.
- `X-Plex-Client-Identifier` is expected on plex.tv calls, alongside identity headers
  (`X-Plex-Product`, `X-Plex-Version`, `X-Plex-Platform`, `X-Plex-Device`,
  `X-Plex-Device-Name`). plexapi supplies these from its module-level `BASE_HEADERS`.
  **Matinee must set a stable client identifier** (persisted in the config table) and
  `X-Plex-Product: Matinee` so the PIN grant shows up as one consistent device in the
  user's plex.tv authorised-devices list — pass a `headers=` dict to `MyPlexPinLogin`
  and/or set the `plexapi.X_PLEX_IDENTIFIER` module constant before first use.
  ⚠ verify at M1: exact override mechanism (module constants are read into
  `BASE_HEADERS` at import time, so set them before importing submodules, or pass
  explicit `headers=`).
- plexapi masks known secrets in its own log output (`logfilter.add_secret(...)` is
  applied to account/resource tokens in `myplex.py`) — belt-and-braces on top of our
  own log-redaction filter, not a replacement for it.

## 2 · PIN login — `MyPlexPinLogin`

Source: [myplex module docs](https://python-plexapi.readthedocs.io/en/latest/modules/myplex.html)
and [`plexapi/myplex.py` source](https://github.com/pkkid/python-plexapi/blob/master/plexapi/myplex.py).

- Constructor: `MyPlexPinLogin(session=None, requestTimeout=None, headers=None, oauth=False)`.
- Endpoint used: **`https://plex.tv/api/v2/pins`** (POST to create). The response
  carries `id` (the pin record id, stored as `self._id`) and `code` (the
  **4-character code** the user types at **https://plex.tv/link**, exposed as the
  `.pin` property).
- Polling: `checkLogin()` GETs `api/v2/pins/{id}` and returns `True` once plex.tv has
  an `authToken` for the pin; the token then lands on the **`.token` attribute** and
  `.finished` becomes `True`. There is also a blocking `waitForLogin()` and a
  threaded `run(callback, timeout=120)` — **we use neither**; our
  `GET /api/setup/pin/{id}` endpoint calls `checkLogin()` on each client poll, which
  maps exactly onto the browser-driven wizard.
- Expiry: `.expired` bool. The 120 s figure is only `run()`'s default thread timeout,
  **not** the pin's server-side TTL. ⚠ verify at M1: actual plex.tv pin TTL
  (believed ~15 min) — the wizard should surface "code expired, get a new one" off
  `.expired` / a failed poll rather than assuming a duration.
- `oauth=True` variant creates a *strong* pin (`{'strong': True}`) and provides
  `oauthUrl(forwardUrl=None)` → `https://app.plex.tv/auth/#!?…`. That flow wants a
  browser redirect back; the 4-char link-code flow is simpler for a LAN app with no
  public callback URL. **Decision: use the non-oauth link-code flow** — it matches the
  brief ("the PIN flow, in the browser") and needs no redirect handling.
- Backend state: `MyPlexPinLogin` instances are in-process objects. Our
  `POST /api/setup/pin` creates one, stores it in a small in-memory dict keyed by our
  own opaque id, and `GET /api/setup/pin/{id}` polls it. Fine for a single-process
  container; instances are dropped once finished/expired.

## 3 · Server discovery — `MyPlexAccount.resources()`

Source: same module docs/source as §2.

- `MyPlexAccount(token=...).resources()` GETs
  `https://plex.tv/api/v2/resources?includeHttps=1&includeRelay=1&includeIPv6=1` and
  returns `MyPlexResource` objects.
- Filter for servers with `'server' in resource.provides` (`provides` is a
  comma-string like `server`, `client`, `player`, …).
- Useful attributes: `name`, `clientIdentifier` (this **is** the machineIdentifier
  used in deep links), `connections` (list of `ResourceConnection`: `address`, `uri`,
  `port`, `protocol`, and booleans **`local`** and **`relay`**), and a per-server
  **`accessToken`** (may differ from the account token, e.g. shared servers).
- `resource.connect(ssl=None, timeout=None, locations=…, schemes=…)` tries
  connections in priority order and returns a connected `PlexServer`. For Matinee we
  prefer **local, non-relay** connections (we're on the same LAN as PMS by design);
  relay URIs would route traffic through Plex's infra and be slow for artwork.
- When the user enters a PMS URL directly (wizard step 1 alternative), we skip
  discovery: `PlexServer(baseurl, token, timeout=…)`, then read
  `server.machineIdentifier` and `server.friendlyName` off it. `GET /identity` on the
  PMS returns the machineIdentifier too ([developer.plex.tv/pms](https://developer.plex.tv/pms/)).

## 4 · Library listing and paging (open question 1 — answered)

Source: [library module docs](https://python-plexapi.readthedocs.io/en/latest/modules/library.html)
and [`plexapi/base.py` source](https://github.com/pkkid/python-plexapi/blob/master/plexapi/base.py).

- `section.search(libtype='movie', filters={...}, container_size=N, maxresults=None)`
  **auto-pages cleanly** — answer to open question 1 is *yes, no manual container
  handling needed*. Internally `fetchItems` loops, sending
  **`X-Plex-Container-Start` / `X-Plex-Container-Size` as HTTP headers**, until
  `container_start > total_size`, accumulating all results when `maxresults=None`.
  Default page size is `plexapi.X_PLEX_CONTAINER_SIZE` — **confirmed = 100**
  (installed plexapi 4.x `__init__.py`, checked 22 July 2026); we pass
  `container_size=200` explicitly for sync.
- Responses echo `X-Plex-Container-Start` and `X-Plex-Container-Total-Size`, which is
  how we report **sync progress** (`processed/total`) without a pre-count.
  `section.totalViewSize(libtype='movie')` also gives a count up front —
  **but pass `includeCollections=False`**. Its default (`True`) counts collections
  too: verified live 22 July 2026 against a real library — `totalViewSize` said
  2,825 while `type=1` ground truth was 2,504, the difference being exactly the
  321 collections. With the default, `count_movies()` would flag a phantom
  mismatch after every incremental sync and pointlessly promote it to a full one.
- **⚠ The N+1 trap (biggest M1 risk):** search results are *partial objects*.
  `PlexPartialObject.__getattribute__` **auto-reloads the item over HTTP** (one
  request per item!) when you access an attribute whose value is `None`/`[]` on a
  partial object. On a 5,000-film library, naively reading a sparse attribute during
  sync turns one paged listing into 5,000 extra requests. Mitigations, in order:
  1. Ask the container to include what we need: **confirmed (22 July 2026,
     installed plexapi 4.x source)** — `_buildSearchKey` sends `includeGuids=1`
     **by default** on every `search()`, so `Guid` elements arrive on the container
     with no per-item reload. ⚠ verify at M1 (live) that `genres`/`directors`/`roles`
     also come through on the container, using request counting.
  2. Disable auto-reload during sync: **confirmed** — `PlexPartialObject.__init__`
     sets `self._autoReload` from config (`plexapi.autoreload`, default True) and
     `__getattribute__` short-circuits when `self._autoReload is False`. Our
     `_to_record()` sets `movie._autoReload = False` per item before reading
     any attribute, so a sparse field can never trigger HTTP.
  3. Fallback: raw `server.query('/library/sections/{id}/all?type=1&includeGuids=1')`
     with manual container paging, parsing the XML ourselves. Keeps request count
     exactly `ceil(N/page)`.
  The M1 acceptance test asserts sync of the user's real library issues
  O(pages) requests, not O(items).
- Timestamps: `addedAt`, `updatedAt`, `lastViewedAt` come back as Python `datetime`
  objects (plexapi converts). We store epoch ints.

## 5 · Movie object field shapes

Source: [video module docs](https://python-plexapi.readthedocs.io/en/latest/modules/video.html)
and [media module docs](https://python-plexapi.readthedocs.io/en/latest/modules/media.html).

| plexapi attr | Type | Notes for our `items` table |
|---|---|---|
| `ratingKey` | int | → `id` (store as TEXT) |
| `guid` | str | Plex GUID, e.g. `plex://movie/5d776b59ad5437001f79c6f8` |
| `guids` | list[Guid] | Each `Guid.id` is `imdb://tt0133093` / `tmdb://603` / `tvdb://…` → parse into `imdb_id`, `tmdb_id`. **Only populated without reload if the container includes them — see §4 trap** |
| `title`, `year`, `tagline`, `summary` | str/int | direct |
| `duration` | int **milliseconds** | → `runtime_min = round(duration/60000)` |
| `contentRating` | str | e.g. `PG-13`, `15`, `NR` — free-form, don't enum it |
| `audienceRating` | float | usually RT audience; prefer this |
| `rating` | float | critic rating; fallback when audienceRating absent |
| `genres` / `directors` | list[Genre/Director] | MediaTag subclasses — the name is the **`.tag`** attribute (str) |
| `roles` | list[Role] | `.tag` = actor name, `.role` = character, `.thumb` = headshot; take `roles[:5]` |
| `thumb` | str | `/library/metadata/<ratingKey>/thumb/<thumbid>` — the trailing id is a cache-buster that changes when artwork updates; **store the whole path at sync time** |
| `art` | str | `/library/metadata/<ratingKey>/art/<artid>` (backdrop) |
| `viewCount` | int | 0/None = unwatched (admin's watch state — single token) |
| `lastViewedAt` | datetime | |
| `addedAt` / `updatedAt` | datetime | `updatedAt` drives incremental sync |

`unusable` flag: no `thumb` **and** no `summary` → excluded from decks (per brief §4.2).

## 6 · Incremental sync filter

Source: [library module docs — filter operators](https://python-plexapi.readthedocs.io/en/latest/modules/library.html).

- Advanced-filter operators are documented: `>>` = greater-than / "is after" for
  datetimes, `<<` = less-than / before, `!` negation, `&` AND. Documented example:
  `library.search(filters={"addedAt>>": "30d"})` — relative strings work.
- Plan: `section.search(libtype='movie', filters={'updatedAt>>': <datetime>})` for
  the 6-hourly incremental. ⚠ verify at M1 that a `datetime`/epoch-int value is
  accepted for `updatedAt>>` (docs show the relative-string form; plexapi converts
  datetimes for sort values, believed same for filters). **Fallback (already
  acceptable per plan):** full listing + upsert-by-ratingKey — at 5k items and
  O(pages) requests that's ~25–50 requests, fine every 6 h.
- Deletions: incremental filters can't see removals. The 6-hourly job also compares
  the full set of ratingKeys (cheap: one paged listing of ids, or
  `totalViewSize` mismatch → full resync). Decide exact mechanism at M1.

## 7 · Photo transcode endpoint (open question 4 — largely answered)

Sources: [`plexapi/server.py` `transcodeImage`](https://github.com/pkkid/python-plexapi/blob/master/plexapi/server.py)
(authoritative — it's what the official-adjacent client library sends),
[Arcanemagus Plex Web API wiki](https://github.com/Arcanemagus/plex-api/wiki/Plex-Web-API-Overview),
[developer.plex.tv/pms](https://developer.plex.tv/pms/) (endpoint exists; params not
detailed there). plexapi.dev's reference page exists but 403s to non-browser fetches.

```
GET {PMS}/photo/:/transcode?url=<urlencoded item thumb path>&width=600&height=900&minSize=1&upscale=1
X-Plex-Token: <token>          ← header, per §1
```

- Exact param names from plexapi's construction: `url`, `width`, `height`,
  `minSize`, `upscale`, optional `format` (`jpeg`|`png`), plus cosmetic extras we
  don't use (`opacity`, `saturation`, `blur`, `background`, `blendColor`).
  Booleans are sent as **`int(bool(v))`** → `0`/`1`. plexapi's own defaults are
  `minSize=True, upscale=True`.
- `url` is the **item's `thumb`/`art` path** (e.g. `/library/metadata/123/thumb/456`),
  URL-encoded as a query value. Images are scaled proportionally; `minSize=1` makes
  the *smaller* native dimension the one fitted, i.e. the output covers the requested
  box — with a 600×900 request on a standard 2:3 poster this yields exactly 600×900.
- **We call this endpoint directly** with our own `requests.Session` (header token),
  not via `transcodeImage()` — that method returns a URL string with
  `X-Plex-Token` embedded in the query (`includeToken=True`), which violates our C1
  logging rule.
- ⚠ verify at M1/M2 with real pixels: that a 600×900 request on a non-2:3 poster
  (and 16:9 `art` backdrops at e.g. 1280×720) comes back at the requested dimensions
  vs letterboxed — i.e. whether per-item letterboxing is ever needed (open question
  4's residue). Also confirm the response `Content-Type` (expect `image/jpeg`).

## 8 · Deep links (open question 3 — shape confirmed, iOS behaviour pending)

Sources: [Plex forum — DeepLinks](https://forums.plex.tv/t/deeplinks/940191),
[Home Assistant community thread](https://community.home-assistant.io/t/appletv-integration-deep-link-urls-which-are-working/592862?page=2),
[archived Plex forum deep-links thread](https://forums4174.rssing.com/chan-65523824/article64495.html).

- Confirmed scheme shape (community-documented; Plex has never formally documented it):

  ```
  plex://preplay/?metadataKey=/library/metadata/{ratingKey}&metadataType=1&server={machineIdentifier}
  ```

  `metadataType=1` = movie. `server` is the **40-hex machineIdentifier**
  (= `resource.clientIdentifier` = `PlexServer.machineIdentifier`), not the friendly
  name. Prefer `plex://` over the older `plexappext://` (the latter only works if the
  app is already on the right server).
- Web fallback:

  ```
  https://app.plex.tv/desktop/#!/server/{machineIdentifier}/details?key=%2Flibrary%2Fmetadata%2F{ratingKey}
  ```

  (`key` value URL-encoded.)
- ⚠ verify live at M3 on the user's actual iPhone: that current Plex for iOS
  (July 2026) still registers `plex://` and lands on the pre-play screen. Frontend
  strategy: attempt `plex://` via location change, fall back to the web URL on a
  visibility/timeout heuristic (standard mobile deep-link dance).

## 9 · Plex Lists (open question 2 — answered: not usable)

Sources: [Plex support — Lists](https://support.plex.tv/articles/lists/),
[AlternativeTo news, June 2026](https://alternativeto.net/news/2026/6/plex-introduces-social-lists-community-forums-and-personalized-discovery-features/),
[HowToGeek coverage](https://www.howtogeek.com/plex-is-fixing-playlists-by-adding-a-new-feature-called-lists/).

- Lists (April 2026) are **stored on Plex's cloud infrastructure**, not on the PMS,
  and only titles matched to Plex Discover can be added. **No public/local API is
  documented** as of 22 July 2026 — neither on developer.plex.tv nor in python-plexapi.
- "Save shortlist to Plex" therefore stays **post-v1**. If we ever want it, the
  server-local **playlist** API (`server.createPlaylist(title, items=[...])`) is
  fully supported by plexapi today and lands where both people already look — worth
  considering as the v1.x feature instead of Lists. No action for v1.

## 10 · Consolidated ⚠ verify-live list

| Item | Status |
|---|---|
| ~~`guids` on container / `includeGuids` spelling~~ | **done 22 Jul 2026** — `search()` sends `includeGuids=1` by default (plexapi 4.x source) |
| ~~`genres`/`directors`/`roles` on the section container~~ | **done 22 Jul 2026 (live)** — 2,504-item sync in ~4 s with 98–99 % field coverage; no per-item reloads |
| ~~`X_PLEX_CONTAINER_SIZE` default~~ | **done 22 Jul 2026 — 100** |
| ~~`_autoReload` off-switch mechanism~~ | **done 22 Jul 2026** — instance attr checked in `__getattribute__`; set per item in `_to_record()` |
| ~~`updatedAt>>` accepts a datetime~~ | **done 22 Jul 2026 (live)** — incremental sync against real PMS, sub-second, no error |
| ~~Transcoder dimensions + Content-Type~~ | **done 22 Jul 2026 (live)** — 600×900 poster and 1280×720 art came back at exactly the requested pixels, `image/jpeg`; no letterboxing needed |
| ~~Fixture capture~~ | **done 22 Jul 2026** — `backend/tests/fixtures/plex/movies_container_page.xml`, 3 items, file paths + uuids scrubbed, token asserted absent |
| ~~`totalViewSize` collections gotcha~~ | **found + fixed 22 Jul 2026** — pass `includeCollections=False` (see §4) |
| plex.tv PIN TTL + `.expired` behaviour | open — pin was linked before it could lapse; wizard already handles `.expired` on poll |
| Plex.tv devices list shows a single "Matinee" entry | open — needs the user to eyeball plex.tv → Settings → Authorised Devices |
| `plex://preplay/` on current Plex for iOS | M3 — tap-through on real iPhone |
