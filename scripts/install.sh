#!/usr/bin/env bash
# Take a fresh clone to a registered agent. Safe to re-run; anything already
# running is left alone. Stop what this started with scripts/cleanup.sh.
set -euo pipefail
# Job control gives background services their own process group, so they
# outlive this script and a Ctrl+C at the model prompt.
set -m
cd "$(dirname "$0")/.."

TRUEFORGE_PORT=8790
LOG_DIR=logs

fail() { echo "error: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }

# Any HTTP response counts; curl tries both 127.0.0.1 and ::1 (TrueForge binds ::1).
port_open() { curl -s -o /dev/null --max-time 2 "http://localhost:$1/"; }

wait_for_port() {
    local name=$1 port=$2 seconds=$3 pid=$4
    for _ in $(seq "$seconds"); do
        port_open "$port" && return 0
        kill -0 "$pid" 2> /dev/null || break
        sleep 1
    done
    rm -f "$LOG_DIR/$name.pid"
    fail "$name did not start on port $port; see $LOG_DIR/$name.log"
}

start_in_background() {
    local name=$1 port=$2 seconds=$3
    shift 3
    if port_open "$port"; then
        echo "$name already running on port $port"
        return
    fi
    nohup "$@" > "$LOG_DIR/$name.log" 2>&1 &
    echo $! > "$LOG_DIR/$name.pid"
    wait_for_port "$name" "$port" "$seconds" $!
    echo "Started $name on port $port (log: $LOG_DIR/$name.log)"
}

step "Checking prerequisites"
for tool in uv docker node sbx curl; do
    command -v "$tool" > /dev/null || fail "$tool is not installed; see Prerequisites in README.md"
done
docker info > /dev/null 2>&1 || fail "the Docker daemon is not running"
node_major=$(node -v | sed 's/^v\([0-9]*\).*/\1/')
[ "$node_major" -ge 22 ] || fail "Node.js 22 or newer is required (found $(node -v))"

step "Installing Python dependencies"
uv sync
[ -f .env ] || { cp .env.example .env; echo "Created .env from .env.example"; }
MCP_PORT=$(sed -n 's/^MCP_PORT=//p' .env)
MCP_PORT=${MCP_PORT:-8765}
mkdir -p "$LOG_DIR"

step "Starting production (Redis) and loading the sample config"
docker compose up -d --wait
uv run python -m scripts.seed_device

step "Creating the rehearsal sandbox"
uv run python -m scripts.create_sandbox

step "Starting TrueForge and the MCP server"
start_in_background trueforge "$TRUEFORGE_PORT" 180 \
    env OUTBOUND_URL_ALLOWED_HOSTS='["127.0.0.1"]' npx --yes @truefoundry/trueforge
start_in_background mcp "$MCP_PORT" 30 uv run python -m nos_rehearsal.server

step "Registering the connector and the agent"
until uv run python -m scripts.create_agent < /dev/null; do
    read -rp "Add a model at http://localhost:$TRUEFORGE_PORT (Settings, Models) and set TRUEFORGE_MODEL in .env, then press Enter "
done

echo
echo "Ready: open http://localhost:$TRUEFORGE_PORT, Agents, sonic-migration-rehearsal."
echo "Logs: $LOG_DIR/trueforge.log, $LOG_DIR/mcp.log. Stop with ./scripts/cleanup.sh"
