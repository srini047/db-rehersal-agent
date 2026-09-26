import hashlib
import json
from typing import Any, Protocol

Config = dict[str, Any]


class NosDriver(Protocol):
    def read_config(self) -> Config: ...

    def write_config(self, config: Config) -> None: ...


def sha256_of(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
