"""Runtime settings, read from the environment (and `.env` if present)."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/4")
SEED_CONFIG_PATH = REPO_ROOT / "data" / "config_db.json"
BACKUP_DIR = REPO_ROOT / "backups"

# Docker Sandbox (sbx microVM) that runs the agent's rehearsal scripts. Only
# REHEARSAL_DIR is mounted into it.
SANDBOX_NAME = os.environ.get("SANDBOX_NAME", "sonic-rehearsal")
REHEARSAL_DIR = REPO_ROOT / "rehearsals"
REHEARSAL_TIMEOUT_SECONDS = int(os.environ.get("REHEARSAL_TIMEOUT_SECONDS", "60"))

MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "8765"))
MCP_URL = os.environ.get("MCP_URL", f"http://127.0.0.1:{MCP_PORT}/mcp")

TRUEFORGE_BASE_URL = os.environ.get("TRUEFORGE_BASE_URL", "http://localhost:8790")
TRUEFORGE_MODEL = os.environ.get("TRUEFORGE_MODEL", "")
