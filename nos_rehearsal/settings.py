"""Runtime settings, read from the environment (and `.env` if present)."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent

# Which device from devices.yaml to serve; may be empty when it lists only one.
DEVICES_PATH = REPO_ROOT / "devices.yaml"
DEVICE = os.environ.get("DEVICE", "")
NOS_DIR = Path(__file__).resolve().parent / "nos"

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
