"""Registry of NOS drivers.

Profiles name a driver by key; only drivers registered here can be used, so a
profile file can never point at arbitrary Python code.
"""

from nos_rehearsal.nos.base import NosDriver
from nos_rehearsal.nos.sonic.driver import SonicRedisDriver

DRIVERS: dict[str, type[NosDriver]] = {
    "sonic-redis": SonicRedisDriver,
}
