# decide

**Swipe. Decide. Watch.** A self-hosted swipe-to-match film picker that works
with your Plex library. Two to four people swipe through the same small deck
of films; when everyone says "Tonight" to the same one, it's a match — and a
ticket stub prints.

decide is an independent project that works with Plex Media Server. It is not
affiliated with or endorsed by Plex, Inc.

## How it works

1. One person sets the filters — mood, runtime, rating, certificate — and gets
   a six-character join code (and a QR).
2. Everyone swipes the same frozen deck of 20–50 films, together or whenever
   suits them. Right means "I'd watch this tonight".
3. Unanimous right-swipes land in a shared shortlist as ticket stubs. Tap one
   to open it in Plex.

Your Plex token never leaves the server: all Plex traffic, including artwork,
is proxied by the backend. Once the library is synced, everything works on the
LAN with no internet access.

## Quick start

```yaml
# compose.yaml
services:
  decide:
    image: ghcr.io/OWNER/decide:latest
    container_name: decide
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - PUID=1000
      - PGID=1000
    restart: unless-stopped
```

```
docker compose up -d
```

Open `http://<host>:8080`, sign in with Plex (a 4-character code at
plex.tv/link — decide never asks for your password), pick your server and film
libraries, and let the first sync run. That's it.

On iPhone or Android, open the site and **Add to Home Screen** — decide is a
PWA and behaves like an app, including offline swiping that syncs back when
the connection returns.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8080` | Listen port |
| `DATA_DIR` | `/data` | SQLite database + artwork cache |
| `PUID` / `PGID` | `1000` | Run as this user/group |
| `ART_CACHE_MB` | `500` | Artwork disk-cache cap |
| `PLEX_URL` | — | Declarative config: skip the wizard |
| `PLEX_TOKEN` | — | Declarative config: skip the wizard |
| `PLEX_SECTIONS` | — | Comma-separated movie section ids |
| `SECRET_KEY` | auto-generated | Cookie-signing key override |

## Reverse proxy

decide uses a WebSocket at `/api/sessions/*/live` — make sure upgrades pass
through.

**Caddy** (WebSockets work out of the box):

```
decide.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

**nginx**:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

## Remote access

Remote access is deliberately out of scope — bring whatever already works for
the rest of your self-hosted stack. [Tailscale](https://tailscale.com/kb/)
is the easiest route if you have nothing yet.

If your Plex server runs in Docker and LAN clients appear as remote (source-IP
NAT), that's a Plex networking quirk, not a decide one — see the
[Plex forum thread on Docker and local network discovery](https://forums.plex.tv/t/plex-docker-container-sees-local-devices-as-remote/124882).

## Development

Backend (Python 3.12, FastAPI, SQLite — managed with [uv](https://docs.astral.sh/uv/)):

```
cd backend
uv sync
DATA_DIR=.dev-data uv run uvicorn decide.main:app --reload --port 8080
uv run pytest
```

Frontend (React 18 + Vite + TypeScript + Tailwind):

```
cd frontend
npm install
npm run dev   # proxies /api to :8080
```

Media-server access sits behind a `MediaSource` protocol
(`backend/src/decide/sources/`) — Plex is the only implementation today;
a Jellyfin source can drop in without touching the rest.

Verified Plex endpoint behaviour is documented in
[docs/plex-notes.md](docs/plex-notes.md).

## Not in v1 (by design)

Video playback (Plex's job), TV shows, more than four people, per-person watch
state, recommendations, accounts, and solving your remote access for you.
