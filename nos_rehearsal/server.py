"""MCP server that exposes one device's production config to TrueForge.

The device, its NOS profile and its driver come from devices.yaml. Read-only
tools, including running a rehearsal in the Docker Sandbox, run on their own.
Tools that write to production are marked destructive, so TrueForge pauses for
a human before calling them.

    uv run python -m nos_rehearsal.server
"""

import json
import re
from datetime import datetime, timezone
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from nos_rehearsal import settings
from nos_rehearsal.nos.base import Config, sha256_of
from nos_rehearsal.patching import PatchRejected, apply_guarded_patch, summarize_changes
from nos_rehearsal.profiles import create_driver, load_device
from nos_rehearsal.sandbox import SandboxError, run_rehearsal

BACKUP_ID_PATTERN = re.compile(r"^\d{8}T\d{12}Z$")

READ_ONLY = ToolAnnotations(read_only_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True)

device, profile = load_device(settings.DEVICE)
driver = create_driver(device, profile)

mcp = MCPServer(
    device.name,
    instructions=(
        f"Access to the production config of {device.name}, a {profile.name} device. Always rehearse "
        "a change with rehearse_patch before calling apply_patch_to_production."
    ),
)


@mcp.tool(annotations=READ_ONLY)
def get_config_snapshot() -> dict[str, Any]:
    """Return the device's current production config (a JSON tree) and its sha256.

    Pass the sha256 back as `base_sha256` when applying, so production can refuse
    the change if it moved after the rehearsal.
    """
    config = driver.read_config()
    return {"device": device.name, "nos": profile.name, "sha256": sha256_of(config), "config": config}


@mcp.tool(annotations=READ_ONLY)
def rehearse_patch(patch: list[dict[str, Any]], script: str) -> dict[str, Any]:
    """Run your Python rehearsal script against a fresh production snapshot in an isolated Docker Sandbox.

    The script runs as `python3 rehearse.py` in a directory containing
    `snapshot.json` (the production config) and `patch.json` (the patch you
    pass). `jsonpatch` is installed; the network is not needed. Production is
    never touched. Returns `base_sha256` (pass it to apply_patch_to_production),
    the sandbox `run_id`, and the script's exit code, stdout and stderr.
    """
    snapshot = driver.read_config()
    try:
        result = run_rehearsal(script, snapshot, patch)
    except SandboxError as error:
        raise ToolError(f"Rehearsal failed to run: {error}") from error
    return {"base_sha256": sha256_of(snapshot), **result}


@mcp.tool(annotations=READ_ONLY)
def list_backups() -> list[dict[str, str]]:
    """List the production backups taken before each apply or restore, newest first."""
    backups = []
    for path in sorted(settings.BACKUP_DIR.glob("*.json"), reverse=True):
        backups.append({"backup_id": path.stem, "sha256": sha256_of(json.loads(path.read_text()))})
    return backups


@mcp.tool(annotations=DESTRUCTIVE)
def apply_patch_to_production(patch: list[dict[str, Any]], base_sha256: str) -> dict[str, Any]:
    """Apply a rehearsed JSON Patch (RFC 6902) to the device's production config.

    Refused if production no longer matches `base_sha256`, if the patch touches a
    protected path, or if it does not apply cleanly. A backup is saved first.
    """
    current = driver.read_config()
    try:
        patched = apply_guarded_patch(current, patch, base_sha256, sha256_of(current), profile)
    except PatchRejected as error:
        raise ToolError(f"Refused: {error}") from error

    backup_id = _save_backup(current)
    driver.write_config(patched)
    return {
        "status": "applied",
        "backup_id": backup_id,
        "new_sha256": sha256_of(patched),
        "changes": summarize_changes(current, patched),
    }


@mcp.tool(annotations=DESTRUCTIVE)
def restore_backup(backup_id: str) -> dict[str, Any]:
    """Replace the device's production config with a backup from `list_backups`.

    The current production config is backed up first, so a restore can be undone too.
    """
    backup_path = settings.BACKUP_DIR / f"{backup_id}.json"
    if not BACKUP_ID_PATTERN.match(backup_id) or not backup_path.is_file():
        raise ToolError(f"Unknown backup_id {backup_id!r}. Call list_backups to see valid ids.")

    current = driver.read_config()
    restored = json.loads(backup_path.read_text())

    safety_backup_id = _save_backup(current)
    driver.write_config(restored)
    return {
        "status": "restored",
        "restored_backup_id": backup_id,
        "backup_of_replaced_config": safety_backup_id,
        "new_sha256": sha256_of(restored),
        "changes": summarize_changes(current, restored),
    }


def _save_backup(config: Config) -> str:
    settings.BACKUP_DIR.mkdir(exist_ok=True)
    backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (settings.BACKUP_DIR / f"{backup_id}.json").write_text(json.dumps(config, indent=2, sort_keys=True))
    return backup_id


def main() -> None:
    mcp.run("streamable-http", host=settings.MCP_HOST, port=settings.MCP_PORT)


if __name__ == "__main__":
    main()
