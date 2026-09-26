import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nos_rehearsal import settings
from nos_rehearsal.nos.base import Config

SCRIPT_NAME = "rehearse.py"
MAX_SCRIPT_CHARS = 20_000
MAX_OUTPUT_CHARS = 20_000


class SandboxError(RuntimeError):
    pass


def run_rehearsal(script: str, snapshot: Config, patch: list[dict[str, Any]]) -> dict[str, Any]:
    if len(script) > MAX_SCRIPT_CHARS:
        raise SandboxError(f"Script is longer than {MAX_SCRIPT_CHARS} characters.")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = settings.REHEARSAL_DIR / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "snapshot.json").write_text(json.dumps(snapshot, indent=2))
    (run_dir / "patch.json").write_text(json.dumps(patch, indent=2))
    (run_dir / SCRIPT_NAME).write_text(script)

    try:
        completed = subprocess.run(
            sandbox_command(run_dir),
            capture_output=True,
            text=True,
            timeout=settings.REHEARSAL_TIMEOUT_SECONDS + 30,
        )
    except FileNotFoundError as error:
        raise SandboxError("The `sbx` CLI is not installed; see the README setup steps.") from error
    except subprocess.TimeoutExpired as error:
        raise SandboxError("The sandbox did not respond in time.") from error

    return {
        "run_id": run_id,
        "sandbox": settings.SANDBOX_NAME,
        "exit_code": completed.returncode,
        "stdout": completed.stdout[-MAX_OUTPUT_CHARS:],
        "stderr": completed.stderr[-MAX_OUTPUT_CHARS:],
    }


def sandbox_command(run_dir: Path) -> list[str]:
    return [
        "sbx", "exec",
        "--workdir", str(run_dir),
        settings.SANDBOX_NAME,
        "timeout", str(settings.REHEARSAL_TIMEOUT_SECONDS),
        "python3", SCRIPT_NAME,
    ]
