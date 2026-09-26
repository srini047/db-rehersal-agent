"""Run agent-written rehearsal scripts inside a Docker Sandbox (an `sbx` microVM).

Each run gets its own directory under REHEARSAL_DIR holding `snapshot.json`,
`patch.json` and `rehearse.py`. That directory tree is the only part of the
host the sandbox can see, so the script never has access to Redis, `.env`, or
the rest of the repo.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sonic_mcp import settings
from sonic_mcp.configdb import Config

SCRIPT_NAME = "rehearse.py"
MAX_SCRIPT_CHARS = 20_000
MAX_OUTPUT_CHARS = 20_000


class SandboxError(RuntimeError):
    """The rehearsal could not be run in the sandbox."""


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
    """`sbx exec` the script in the run directory, with a hard time limit inside the VM."""
    return [
        "sbx", "exec",
        "--workdir", str(run_dir),
        settings.SANDBOX_NAME,
        "timeout", str(settings.REHEARSAL_TIMEOUT_SECONDS),
        "python3", SCRIPT_NAME,
    ]
