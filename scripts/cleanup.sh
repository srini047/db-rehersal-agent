#!/usr/bin/env bash
# Stop what scripts/install.sh started and take production (Redis) down.
# Processes started by hand are left alone; the sandbox, .env, backups/ and
# rehearsals/ are kept.
set -euo pipefail
cd "$(dirname "$0")/.."

LOG_DIR=logs

kill_tree() {
    local child
    for child in $(pgrep -P "$1"); do
        kill_tree "$child"
    done
    kill "$1" 2> /dev/null || true
}

for pid_file in "$LOG_DIR"/*.pid; do
    [ -e "$pid_file" ] || continue
    name=$(basename "$pid_file" .pid)
    kill_tree "$(cat "$pid_file")"
    rm "$pid_file"
    echo "Stopped $name"
done

docker compose down
