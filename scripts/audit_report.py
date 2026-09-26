import argparse

from nos_rehearsal import settings
from nos_rehearsal.audit import AuditLog, build_report, render_markdown
from nos_rehearsal.profiles import load_device


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the device's audit log as a Markdown report.")
    parser.add_argument("--since", help="ISO 8601 UTC date or time, for example 2026-09-26")
    args = parser.parse_args()

    device, _ = load_device(settings.DEVICE)
    print(render_markdown(build_report(AuditLog(device.name), args.since)))


if __name__ == "__main__":
    main()
