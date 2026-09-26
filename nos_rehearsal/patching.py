import copy
from collections.abc import Callable
from typing import Any

import jsonpatch
import jsonpointer

from nos_rehearsal.nos.base import Config
from nos_rehearsal.profiles import NosProfile

VALUE_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "string": lambda value: isinstance(value, str),
    "string-list": lambda value: isinstance(value, list) and all(isinstance(item, str) for item in value),
    "number": lambda value: isinstance(value, int | float) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
}


class PatchRejected(ValueError):
    pass


def apply_guarded_patch(
    config: Config, patch: list[dict], base_sha256: str, current_sha256: str, profile: NosProfile
) -> Config:
    if base_sha256 != current_sha256:
        raise PatchRejected(
            f"Production changed since it was rehearsed (rehearsed {base_sha256[:12]}, "
            f"now {current_sha256[:12]}). Take a new snapshot and rehearse again."
        )

    protected = protected_paths_touched(patch, profile.protected_paths)
    if protected:
        raise PatchRejected(f"Patch touches protected paths {protected}; these are never changed by the agent.")

    try:
        patched = jsonpatch.apply_patch(copy.deepcopy(config), patch)
    except (jsonpatch.JsonPatchException, jsonpointer.JsonPointerException) as error:
        raise PatchRejected(f"Patch does not apply cleanly: {error}") from error

    check_config_shape(patched, profile)
    return patched


def protected_paths_touched(patch: list[dict], protected_paths: list[str]) -> list[str]:
    protected = {path: jsonpointer.JsonPointer(path).parts for path in protected_paths}
    touched = set()
    for parts in _operation_pointers(patch):
        for path, protected_parts in protected.items():
            shared = min(len(parts), len(protected_parts))
            if parts[:shared] == protected_parts[:shared]:
                touched.add(path)
    return sorted(touched)


def check_config_shape(config: Config, profile: NosProfile) -> None:
    _check_node(config, [], profile)


def summarize_changes(before: Config, after: Config) -> dict[str, dict[str, list[str]]]:
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


def _operation_pointers(patch: list[dict]) -> list[list[str]]:
    if not isinstance(patch, list) or not patch:
        raise PatchRejected("Patch must be a non-empty JSON Patch array.")

    pointers = []
    for operation in patch:
        if not isinstance(operation, dict) or "path" not in operation:
            raise PatchRejected(f"Not a JSON Patch operation: {operation!r}")
        for pointer in (operation.get("path"), operation.get("from")):
            if pointer is None:
                continue
            parts = jsonpointer.JsonPointer(pointer).parts
            if not parts:
                raise PatchRejected("Patch may not replace the whole configuration.")
            pointers.append(parts)
    return pointers


def _check_node(node: Any, parts: list[str], profile: NosProfile) -> None:
    depth, leaf_depth = len(parts), profile.leaf_depth
    location = jsonpointer.JsonPointer.from_parts(parts).path or "/"

    if isinstance(node, dict) and (leaf_depth is None or depth < leaf_depth):
        for key, child in node.items():
            _check_node(child, [*parts, key], profile)
        return
    if leaf_depth is not None and depth < leaf_depth:
        raise PatchRejected(f"{location} must be an object.")
    if not any(VALUE_TYPE_CHECKS[value_type](node) for value_type in profile.value_types):
        raise PatchRejected(f"{location} must be one of: {', '.join(profile.value_types)}.")
