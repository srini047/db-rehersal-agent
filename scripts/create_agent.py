"""Register the device's MCP connector and the rehearsal agent in TrueForge.

The agent's instructions are agent/instructions.md plus the device's NOS
profile (reference checks and protected paths). Safe to re-run: both are
created the first time and updated after that. The MCP server must be running,
so TrueForge can list its tools.

    uv run python -m scripts.create_agent
"""

import sys

from trueforge_sdk import AgentSpec, McpServer, Model, RemoteMcpServerManifest, TrueForge

from nos_rehearsal import settings
from nos_rehearsal.profiles import Device, NosProfile, load_device

AGENT_NAME = "sonic-migration-rehearsal"
AGENT_DESCRIPTION = (
    "Rehearses network config JSON Patches in a Docker Sandbox and applies them to production only after approval."
)
INSTRUCTIONS_PATH = settings.REPO_ROOT / "agent" / "instructions.md"

# Named explicitly as well as by annotation, so the gate holds even if the
# server's destructive annotations are ever dropped.
GATED_TOOLS = ["@destructive", "apply_patch_to_production", "restore_backup"]


def main() -> None:
    device, profile = load_device(settings.DEVICE)
    client = TrueForge(base_url=settings.TRUEFORGE_BASE_URL)
    model_name = settings.TRUEFORGE_MODEL or _exit_with_model_help(client)

    client.settings.mcp_servers.create_or_update(
        manifest=RemoteMcpServerManifest(
            name=device.name,
            description=f"Production config of {device.name} ({profile.name}): snapshot, rehearse in a sandbox, apply, back up and restore.",
            url=settings.MCP_URL,
        )
    )
    tools = client.mcp_servers.list_tools(name=device.name)
    print(f"Connector {device.name} -> {settings.MCP_URL}: {len(tools.data)} tools")

    spec = AgentSpec(
        model=Model(name=model_name),
        instructions=render_instructions(device, profile),
        mcp_servers=[McpServer(name=device.name, require_approval_for_tools=GATED_TOOLS, preload=True)],
    )

    existing = next((agent for agent in client.agents.list(agent_name=AGENT_NAME) if agent.name == AGENT_NAME), None)
    if existing:
        client.agents.update(agent_id=existing.id, manifest=spec, description=AGENT_DESCRIPTION)
        print(f"Updated agent {AGENT_NAME} ({existing.id}) using {model_name}")
    else:
        created = client.agents.create(name=AGENT_NAME, description=AGENT_DESCRIPTION, manifest=spec)
        print(f"Created agent {AGENT_NAME} ({created.data.id}) using {model_name}")


def render_instructions(device: Device, profile: NosProfile) -> str:
    checks = "\n".join(f"- {check.description}" for check in profile.checks) or "- None."
    protected = "\n".join(f"- `{path}`" for path in profile.protected_paths)
    return (
        f"{INSTRUCTIONS_PATH.read_text().rstrip()}\n\n"
        f"## Device\n\n`{device.name}` runs {profile.name}.\n\n"
        f"## Reference checks\n\nFor {profile.name}, your rehearsal script must check the patched config for:\n\n{checks}\n\n"
        f"## Protected paths\n\nThe server refuses any patch that touches these, even when approved:\n\n{protected}\n"
    )


def _exit_with_model_help(client: TrueForge) -> str:
    available = [model.name for model in client.models.list().data]
    sys.exit(f"Set TRUEFORGE_MODEL in .env to one of the models configured in TrueForge: {', '.join(available) or 'none yet'}")


if __name__ == "__main__":
    main()
