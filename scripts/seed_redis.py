"""Load data/config_db.json into Redis as the "production" CONFIG_DB.

Re-run it at any time to reset the demo.

    uv run python -m scripts.seed_redis
"""

import json

from sonic_mcp import settings
from sonic_mcp.configdb import connect, read_config, sha256_of, write_config


def main() -> None:
    config = json.loads(settings.SEED_CONFIG_PATH.read_text())
    client = connect(settings.REDIS_URL)
    write_config(client, config)

    loaded = read_config(client)
    entry_count = sum(len(entries) for entries in loaded.values())
    print(f"Seeded {entry_count} entries across {len(loaded)} tables into {settings.REDIS_URL}")
    print(f"sha256: {sha256_of(loaded)}")


if __name__ == "__main__":
    main()
