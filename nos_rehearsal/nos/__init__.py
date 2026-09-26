from nos_rehearsal.nos.base import NosDriver
from nos_rehearsal.nos.sonic.driver import SonicRedisDriver

DRIVERS: dict[str, type[NosDriver]] = {
    "sonic-redis": SonicRedisDriver,
}
