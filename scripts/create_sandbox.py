"""Create the Docker Sandbox that runs rehearsal scripts. Safe to re-run.

The sandbox only mounts the rehearsals/ directory. After jsonpatch is
installed, all of its outbound network access is denied.

    uv run python -m scripts.create_sandbox
"""

import subprocess
import sys

from sonic_mcp import settings

NAME = settings.SANDBOX_NAME


def main() -> None:
    settings.REHEARSAL_DIR.mkdir(exist_ok=True)

    if NAME in sbx("ls", "--quiet").split():
        print(f"Sandbox {NAME} already exists")
    else:
        sbx("create", "--name", NAME, "shell", str(settings.REHEARSAL_DIR))
        print(f"Created sandbox {NAME} with workspace {settings.REHEARSAL_DIR}")

    sbx("exec", NAME, "python3", "-m", "pip", "install", "--quiet", "--user", "--break-system-packages", "jsonpatch")
    print("Installed jsonpatch in the sandbox")

    sbx("policy", "deny", "network", "--sandbox", NAME, "**")
    print(f"Denied all outbound network access for {NAME}")


def sbx(*args: str) -> str:
    completed = subprocess.run(["sbx", *args], capture_output=True, text=True)
    if completed.returncode != 0:
        sys.exit(f"`sbx {' '.join(args)}` failed:\n{completed.stderr or completed.stdout}")
    return completed.stdout


if __name__ == "__main__":
    main()
