"""What every NOS driver provides, and the config helpers shared by all of them."""

import hashlib
import json
from typing import Any, Protocol

Config = dict[str, Any]


class NosDriver(Protocol):
    """Reads and writes a device's production config as a normalized JSON tree."""

    def read_config(self) -> Config: ...

    def write_config(self, config: Config) -> None:
        """Make production equal to `config`, all or nothing."""


def sha256_of(config: Config) -> str:
    """Stable fingerprint of a config, independent of key order."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
