#!/usr/bin/env python3
"""Sweep LED/lamp events across a numeric range."""

import argparse
import os
import sys
import time

import dof


def _default_base_path() -> str:
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", home)
        return os.path.join(appdata, "VPinballX", "10.8")
    if sys.platform == "darwin":
        return os.path.join(home, "Library", "Application Support", "VPinballX", "10.8")
    return os.path.join(home, ".local", "share", "VPinballX", "10.8")


def _log_handler(level: dof.LogLevel, message: str) -> None:
    tag = {
        dof.LogLevel.INFO: "[INFO ]",
        dof.LogLevel.WARN: "[WARN ]",
        dof.LogLevel.ERROR: "[ERROR]",
        dof.LogLevel.DEBUG: "[DEBUG]",
    }.get(level, "[?????]")
    print(f"{tag} {message}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Turn on LED/lamp events in sequence and hold each briefly."
    )
    parser.add_argument("--rom", default="pinupmenu", help='ROM name/key (default: "pinupmenu")')
    parser.add_argument(
        "--base-path",
        default="",
        help="DOF base path (default: platform VPinballX/10.8)",
    )
    parser.add_argument("--start", type=int, default=289, help="First LED number (default: 289)")
    parser.add_argument("--end", type=int, default=912, help="Last LED number (default: 912)")
    parser.add_argument(
        "--event-type",
        default="E",
        help='DOF event type to sweep, such as E or L (default: "E")',
    )
    parser.add_argument(
        "--hold-sec",
        type=float,
        default=0.2,
        help="Seconds to hold each LED ON (default: 0.2)",
    )
    parser.add_argument(
        "--on-value",
        type=int,
        default=1,
        help="ON value sent for each LED event (default: 1)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG-level logging")
    args = parser.parse_args()

    if args.start < 0:
        parser.error("--start must be >= 0")
    if args.end < 0:
        parser.error("--end must be >= 0")
    if args.start > args.end:
        parser.error("--start must be <= --end")
    event_type = args.event_type.strip().upper()
    if len(event_type) != 1 or not event_type.isalpha():
        parser.error('--event-type must be a single letter such as E or L')
    if args.hold_sec <= 0:
        parser.error("--hold-sec must be > 0")
    if args.on_value < 0:
        parser.error("--on-value must be >= 0")

    base_path = args.base_path if args.base_path else _default_base_path()
    rom_key = args.rom.strip().replace(" ", "_")

    dof.set_log_callback(_log_handler)
    dof.set_log_level(dof.LogLevel.DEBUG if args.debug else dof.LogLevel.INFO)
    dof.set_base_path(base_path)

    print(
        f'Initializing ROM: {args.rom} (key={rom_key}), '
        f'sweeping {event_type}{args.start}-{event_type}{args.end}, '
        f'hold={args.hold_sec:.3f}s, on_value={args.on_value}'
    )

    with dof.DOF() as d:
        d.init(rom_key)
        for number in range(args.start, args.end + 1):
            print(f"ON  {event_type}{number}")
            d.data_receive(event_type, number, args.on_value)
            try:
                time.sleep(args.hold_sec)
            finally:
                d.data_receive(event_type, number, 0)
            print(f"OFF {event_type}{number}")

    print("Done.")


if __name__ == "__main__":
    main()
