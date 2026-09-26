import json
import re
from datetime import datetime, timezone
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from nos_rehearsal import settings
from nos_rehearsal.audit import AuditLog, build_report
from nos_rehearsal.nos.base import Config, sha256_of
from nos_rehearsal.patching import PatchRejected, apply_guarded_patch, check_rehearsal, summarize_changes
from nos_rehearsal.profiles import create_driver, load_device
from nos_rehearsal.sandbox import SandboxError, run_rehearsal

BACKUP_ID_PATTERN = re.compile(r"^\d{8}T\d{12}Z$")

READ_ONLY = ToolAnnotations(read_only_hint=True)
DESTRUCTIVE = ToolAnnotations(read_only_hint=False, destructive_hint=True)

device, profile = load_device(settings.DEVICE)
driver = create_driver(device, profile)
audit = AuditLog(device.name)

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
    never touched. Returns the sandbox `run_id` and `base_sha256` (pass both to
    apply_patch_to_production), and the script's exit code, stdout and stderr.
    Only a rehearsal whose script exits with code 0 can be applied.
    """
    snapshot = driver.read_config()
    base_sha256, patch_sha256 = sha256_of(snapshot), sha256_of(patch)
    try:
        result = run_rehearsal(script, snapshot, patch)
    except SandboxError as error:
        audit.record("rehearsal_error", patch_sha256=patch_sha256, base_sha256=base_sha256, reason=str(error))
        raise ToolError(f"Rehearsal failed to run: {error}") from error
    audit.record("rehearsal", patch_sha256=patch_sha256, base_sha256=base_sha256, patch=patch, **result)
    return {"base_sha256": base_sha256, **result}


@mcp.tool(annotations=READ_ONLY)
def list_backups() -> list[dict[str, str]]:
    """List the production backups taken before each apply or restore, newest first."""
    backups = []
    for path in sorted(settings.BACKUP_DIR.glob("*.json"), reverse=True):
        backups.append({"backup_id": path.stem, "sha256": sha256_of(json.loads(path.read_text()))})
    return backups


@mcp.tool(annotations=DESTRUCTIVE)
def apply_patch_to_production(
    patch: list[dict[str, Any]], rehearsal_run_id: str, base_sha256: str
) -> dict[str, Any]:
    """Apply a rehearsed JSON Patch (RFC 6902) to the device's production config.

    Pass the `run_id` and `base_sha256` that rehearse_patch returned for this exact
    patch. Refused if that rehearsal's script did not exit with code 0 or was for a
    different patch, if production no longer matches `base_sha256`, if the patch
    touches a protected path, or if it does not apply cleanly. A backup is saved first.
    """
    patch_sha256 = sha256_of(patch)
    receipt = {"rehearsal_run_id": rehearsal_run_id, "patch_sha256": patch_sha256, "base_sha256": base_sha256}
    current = driver.read_config()
    try:
        check_rehearsal(audit.rehearsal(rehearsal_run_id), rehearsal_run_id, patch_sha256, base_sha256)
        patched = apply_guarded_patch(current, patch, base_sha256, sha256_of(current), profile)
    except PatchRejected as error:
        audit.record("apply_refused", **receipt, patch=patch, reason=str(error))
        raise ToolError(f"Refused: {error}") from error

    backup_id = _save_backup(current)
    driver.write_config(patched)
    result = {
        "backup_id": backup_id,
        "new_sha256": sha256_of(patched),
        "changes": summarize_changes(current, patched),
    }
    audit.record("apply", **receipt, patch=patch, **result)
    return {"status": "applied", **result}


@mcp.tool(annotations=DESTRUCTIVE)
def restore_backup(backup_id: str) -> dict[str, Any]:
    """Replace the device's production config with a backup from `list_backups`.

    The current production config is backed up first, so a restore can be undone too.
    """
    backup_path = settings.BACKUP_DIR / f"{backup_id}.json"
    if not BACKUP_ID_PATTERN.match(backup_id) or not backup_path.is_file():
        reason = f"Unknown backup_id {backup_id!r}. Call list_backups to see valid ids."
        audit.record("restore_refused", backup_id=backup_id, reason=reason)
        raise ToolError(reason)

    current = driver.read_config()
    restored = json.loads(backup_path.read_text())

    safety_backup_id = _save_backup(current)
    driver.write_config(restored)
    result = {
        "restored_backup_id": backup_id,
        "backup_of_replaced_config": safety_backup_id,
        "new_sha256": sha256_of(restored),
        "changes": summarize_changes(current, restored),
    }
    audit.record("restore", **result)
    return {"status": "restored", **result}


@mcp.tool(annotations=READ_ONLY)
def get_audit_report(since: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Return this device's audit log: every rehearsal, apply, refused apply and restore, oldest first.

    The server writes it as each tool call happens; the agent cannot change it.
    `since` is an ISO 8601 UTC date or time (for example `2026-09-26` or
    `2026-09-26T10:00`), and `limit` keeps only the newest events. Totals count
    every event since `since`. Quote run ids, backup ids and hashes exactly as given.
    """
    return build_report(audit, since, limit)


def _save_backup(config: Config) -> str:
    settings.BACKUP_DIR.mkdir(exist_ok=True)
    backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (settings.BACKUP_DIR / f"{backup_id}.json").write_text(json.dumps(config, indent=2, sort_keys=True))
    return backup_id


def main() -> None:
    mcp.run("streamable-http", host=settings.MCP_HOST, port=settings.MCP_PORT)


if __name__ == "__main__":
    main()
