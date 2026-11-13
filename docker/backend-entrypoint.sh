#!/bin/sh
# Runs the backend as the user "app" (uid 10001), not as root.
#
# Started as root (docker compose, docker run): gives app the directories the backend writes
# to, in case an earlier image filled them as root, then drops root and runs the command.
# Started as another user (Kubernetes with runAsUser, docker run --user): runs the command.
set -e

if [ "$(id -u)" = "0" ]; then
    # Files and logs (LOG_DIRECTORY only if it's set to somewhere else) and the dev certificates
    for dir in "${FILESYSTEM_PATH:-/app/.filesystem}" "${FILES_DIR:-/app/.filesystem/files}" "${LOG_DIRECTORY:-}" /app/devcerts; do
        [ -n "$dir" ] || continue
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir" 2>/dev/null && chown app:app "$dir" || true
        # Only when something in it isn't app's yet, so later starts don't touch the volume
        elif [ -n "$(find "$dir" ! -user app -print -quit 2>/dev/null)" ]; then
            echo "backend-entrypoint: giving $dir to the user app"
            chown -R app:app "$dir" || echo "backend-entrypoint: could not change the owner of $dir" >&2
        fi
    done
    export HOME=/home/app
    exec setpriv --reuid=app --regid=app --init-groups --no-new-privs "$@"
fi

# A user without a home of its own (any other uid): caches go to /tmp
[ -w "${HOME:-/}" ] || export HOME=/tmp

exec "$@"
