import json
import threading
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from nos_rehearsal import settings

OMITTED_FROM_REPORT = ("stdout", "stderr")


class AuditLog:
    def __init__(self, device: str) -> None:
        self.device = device
        self.path = settings.AUDIT_DIR / f"{device}.jsonl"
        self._lock = threading.Lock()

    def record(self, event: str, **details: Any) -> None:
        entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **details}
        line = json.dumps(entry) + "\n"
        with self._lock:
            settings.AUDIT_DIR.mkdir(exist_ok=True)
            with self.path.open("a") as log:
                log.write(line)

    def events(self, since: str | None = None) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        with self.path.open() as log:
            entries = [json.loads(line) for line in log if line.strip()]
        return [entry for entry in entries if since is None or entry["at"] >= since]

    def rehearsal(self, run_id: str) -> dict[str, Any] | None:
        return next(
            (entry for entry in self.events() if entry["event"] == "rehearsal" and entry["run_id"] == run_id),
            None,
        )


def build_report(log: AuditLog, since: str | None = None, limit: int | None = None) -> dict[str, Any]:
    events = log.events(since)
    shown = events if limit is None else events[max(len(events) - limit, 0):]
    return {
        "device": log.device,
        "since": since,
        "totals": dict(Counter(entry["event"] for entry in events)),
        "event_count": len(events),
        "events": [{key: value for key, value in entry.items() if key not in OMITTED_FROM_REPORT} for entry in shown],
    }


def render_markdown(report: dict[str, Any]) -> str:
    totals = ", ".join(f"{name} {count}" for name, count in sorted(report["totals"].items())) or "no events"
    lines = [f"# Audit report: {report['device']}", ""]
    if report["since"]:
        lines += [f"Since {report['since']} (UTC).", ""]
    lines += [
        f"Totals: {totals}. Showing {len(report['events'])} of {report['event_count']} events.",
        "",
        "| Time (UTC) | Event | Details |",
        "| --- | --- | --- |",
    ]
    for entry in report["events"]:
        details = _details(entry).replace("|", r"\|")
        lines.append(f"| {entry['at']} | {entry['event']} | {details} |")
    return "\n".join(lines)


def _details(entry: dict[str, Any]) -> str:
    kind = entry["event"]
    if kind == "rehearsal":
        return (
            f"run `{entry['run_id']}`, exit code {entry['exit_code']}, "
            f"patch `{_short(entry['patch_sha256'])}`, base `{_short(entry['base_sha256'])}`"
        )
    if kind == "apply":
        return (
            f"run `{entry['rehearsal_run_id']}`, backup `{entry['backup_id']}`, "
            f"`{_short(entry['base_sha256'])}` to `{_short(entry['new_sha256'])}`; {_changes(entry['changes'])}"
        )
    if kind == "restore":
        return (
            f"restored `{entry['restored_backup_id']}`, replaced config saved as "
            f"`{entry['backup_of_replaced_config']}`, now `{_short(entry['new_sha256'])}`; {_changes(entry['changes'])}"
        )
    return entry.get("reason", "")


def _changes(changes: dict[str, dict[str, list[str]]]) -> str:
    tables = []
    for table, kinds in changes.items():
        parts = [f"{kind} {', '.join(entries)}" for kind, entries in kinds.items() if entries]
        tables.append(f"{table} {'; '.join(parts)}")
    return " / ".join(tables) or "no changes"


def _short(sha256: str) -> str:
    return sha256[:12]
