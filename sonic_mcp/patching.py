"""Server-side rules a patch must pass before it may touch production.

These run inside the MCP server, after a human has approved the call, so they
hold even if the agent (or the person approving) gets something wrong.
"""

import copy

import jsonpatch
import jsonpointer

from sonic_mcp.configdb import Config

# Changing these can cut the switch off from its management network or change
# its identity, so no patch may touch them, approved or not.
PROTECTED_TABLES = frozenset({"DEVICE_METADATA", "MGMT_INTERFACE"})


class PatchRejected(ValueError):
    """The patch is not allowed to be applied to production."""


def apply_guarded_patch(config: Config, patch: list[dict], base_sha256: str, current_sha256: str) -> Config:
    """Return the patched config, or raise PatchRejected explaining why not."""
    if base_sha256 != current_sha256:
        raise PatchRejected(
            f"Production changed since it was rehearsed (rehearsed {base_sha256[:12]}, "
            f"now {current_sha256[:12]}). Take a new snapshot and rehearse again."
        )

    protected = touched_tables(patch) & PROTECTED_TABLES
    if protected:
        raise PatchRejected(f"Patch touches protected tables {sorted(protected)}; these are never changed by the agent.")

    try:
        patched = jsonpatch.apply_patch(copy.deepcopy(config), patch)
    except (jsonpatch.JsonPatchException, jsonpointer.JsonPointerException) as error:
        raise PatchRejected(f"Patch does not apply cleanly: {error}") from error

    check_config_shape(patched)
    return patched


def touched_tables(patch: list[dict]) -> set[str]:
    """Top-level tables named by any operation's `path` or `from`."""
    if not isinstance(patch, list) or not patch:
        raise PatchRejected("Patch must be a non-empty JSON Patch array.")

    tables = set()
    for operation in patch:
        if not isinstance(operation, dict) or "path" not in operation:
            raise PatchRejected(f"Not a JSON Patch operation: {operation!r}")
        for pointer in (operation.get("path"), operation.get("from")):
            if pointer is None:
                continue
            parts = jsonpointer.JsonPointer(pointer).parts
            if not parts:
                raise PatchRejected("Patch may not replace the whole CONFIG_DB.")
            tables.add(parts[0])
    return tables


def check_config_shape(config: Config) -> None:
    """Every value must be a string or a list of strings, as in config_db.json."""
    for table, entries in config.items():
        if not isinstance(entries, dict):
            raise PatchRejected(f"Table {table} must be an object of entries.")
        for entry, fields in entries.items():
            if not isinstance(fields, dict):
                raise PatchRejected(f"Entry {table}|{entry} must be an object of fields.")
            for name, value in fields.items():
                is_string_list = isinstance(value, list) and all(isinstance(item, str) for item in value)
                if not (isinstance(value, str) or is_string_list):
                    raise PatchRejected(f"{table}|{entry} field {name} must be a string or list of strings.")


def summarize_changes(before: Config, after: Config) -> dict[str, dict[str, list[str]]]:
    """Per table, which entries were added, removed or modified."""
    summary = {}
    for table in sorted(before.keys() | after.keys()):
        old, new = before.get(table, {}), after.get(table, {})
        changes = {
            "added": sorted(new.keys() - old.keys()),
            "removed": sorted(old.keys() - new.keys()),
            "modified": sorted(entry for entry in old.keys() & new.keys() if old[entry] != new[entry]),
        }
        if any(changes.values()):
            summary[table] = changes
    return summary
