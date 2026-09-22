#!/bin/sh
# Fix /data ownership, then drop to PUID:PGID before starting the app.
set -e
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if [ "$(id -u)" = "0" ]; then
  mkdir -p /data
  if ! chown -R "$PUID:$PGID" /data 2>/dev/null; then
    echo "Warning: could not change ownership of /data to $PUID:$PGID (NFS/SMB share?)." >&2
  fi
  exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"
fi

exec "$@"
