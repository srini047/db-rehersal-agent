import json
import sys

from nos_rehearsal import settings
from nos_rehearsal.nos.base import sha256_of
from nos_rehearsal.profiles import create_driver, load_device


def main() -> None:
    device, profile = load_device(settings.DEVICE)
    if profile.sample_config is None:
        sys.exit(f"The {profile.name} profile has no sample_config to seed.")

    config = json.loads((settings.REPO_ROOT / profile.sample_config).read_text())
    driver = create_driver(device, profile)
    driver.write_config(config)

    loaded = driver.read_config()
    print(f"Seeded {device.name} ({profile.name}) from {profile.sample_config}: {len(loaded)} top-level keys")
    print(f"sha256: {sha256_of(loaded)}")


if __name__ == "__main__":
    main()
