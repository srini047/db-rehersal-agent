"""Read and write a SONiC CONFIG_DB stored in Redis.

SONiC keeps CONFIG_DB in Redis database 4, one hash per entry:

- The key is "TABLE|entry", e.g. "VLAN_MEMBER|Vlan100|Ethernet0".
- List values live in fields ending in "@", joined with commas
  ("members@" = "Ethernet0,Ethernet4").
- An entry with no fields holds a placeholder field "NULL" = "NULL".

In Python the same data is the config_db.json shape: {table: {entry: {field: value}}}.
"""

import hashlib
import json

import redis

KEY_SEPARATOR = "|"
LIST_SUFFIX = "@"
EMPTY_ENTRY_FIELD = "NULL"

FieldValue = str | list[str]
Config = dict[str, dict[str, dict[str, FieldValue]]]
RedisHashes = dict[str, dict[str, str]]


def to_redis_hashes(config: Config) -> RedisHashes:
    """Flatten a config_db.json-style dict into Redis keys and hash fields."""
    return {
        f"{table}{KEY_SEPARATOR}{entry}": _encode_fields(fields)
        for table, entries in config.items()
        for entry, fields in entries.items()
    }


def from_redis_hashes(hashes: RedisHashes) -> Config:
    """Rebuild a config_db.json-style dict from Redis keys and hash fields."""
    config: Config = {}
    for key, fields in sorted(hashes.items()):
        table, entry = key.split(KEY_SEPARATOR, 1)
        config.setdefault(table, {})[entry] = _decode_fields(fields)
    return config


def sha256_of(config: Config) -> str:
    """Stable fingerprint of a config, independent of key order."""
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def connect(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, decode_responses=True)


def read_config(client: redis.Redis) -> Config:
    keys = sorted(client.scan_iter())
    with client.pipeline(transaction=False) as pipe:
        for key in keys:
            pipe.hgetall(key)
        values = pipe.execute()
    return from_redis_hashes(dict(zip(keys, values)))


def write_config(client: redis.Redis, config: Config) -> None:
    """Replace the whole CONFIG_DB with `config` in a single MULTI/EXEC transaction."""
    old_keys = list(client.scan_iter())
    with client.pipeline(transaction=True) as pipe:
        if old_keys:
            pipe.delete(*old_keys)
        for key, fields in to_redis_hashes(config).items():
            pipe.hset(key, mapping=fields)
        pipe.execute()


def _encode_fields(fields: dict[str, FieldValue]) -> dict[str, str]:
    if not fields:
        return {EMPTY_ENTRY_FIELD: EMPTY_ENTRY_FIELD}
    encoded = {}
    for name, value in fields.items():
        if isinstance(value, list):
            encoded[name + LIST_SUFFIX] = ",".join(value)
        else:
            encoded[name] = value
    return encoded


def _decode_fields(fields: dict[str, str]) -> dict[str, FieldValue]:
    decoded: dict[str, FieldValue] = {}
    for name, value in fields.items():
        if name == EMPTY_ENTRY_FIELD:
            continue
        if name.endswith(LIST_SUFFIX):
            decoded[name.removesuffix(LIST_SUFFIX)] = value.split(",") if value else []
        else:
            decoded[name] = value
    return decoded
