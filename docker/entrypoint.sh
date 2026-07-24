#!/bin/sh
# Drop to the requested UID/GID (the self-hosted convention) before serving.
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

mkdir -p "${DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
    chown -R "$PUID:$PGID" "${DATA_DIR:-/data}"
    exec gosu "$PUID:$PGID" "$@"
fi

exec "$@"
