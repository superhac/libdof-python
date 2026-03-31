#!/usr/bin/env python3
"""Minimal Wemos/Teensy serial probe for libdof command-mode debugging.

This script intentionally mirrors libdof's handshake pattern:
- Open serial port with configured baud/8N1
- Set DTR on/off
- Flush I/O
- Repeat: write 0x00, wait, read up to 1 byte expecting 'A' or 'N'
- Optionally send post-handshake commands ('C', 'O', 'T')

No external dependencies (pyserial not required).
"""

from __future__ import annotations

import argparse
import fcntl
import os
import select
import sys
import termios
import time
from typing import List


HANDSHAKE_MAP = {
    "A": {ord("A")},
    "N": {ord("N")},
    "both": {ord("A"), ord("N")},
}


def _hex_bytes(data: bytes) -> str:
    return ' '.join(f"{b:02X}" for b in data) if data else '<none>'


def _print_ascii_hint(data: bytes) -> str:
    out = []
    for b in data:
        if 32 <= b <= 126:
            out.append(chr(b))
        elif b in (10, 13):
            out.append('\\n' if b == 10 else '\\r')
        else:
            out.append('.')
    return ''.join(out) if out else '<none>'


def _set_serial(fd: int, baud: int, dtr: bool) -> None:
    attrs = termios.tcgetattr(fd)

    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
    attrs[3] = 0

    baud_map = {
        9600: "B9600",
        19200: "B19200",
        38400: "B38400",
        57600: "B57600",
        115200: "B115200",
        230400: "B230400",
        460800: "B460800",
        921600: "B921600",
        1000000: "B1000000",
        1500000: "B1500000",
        2000000: "B2000000",
    }

    name = baud_map.get(baud)
    speed = getattr(termios, name, None) if name else None
    if speed is None:
        supported = [str(k) for k, n in baud_map.items() if getattr(termios, n, None) is not None]
        raise ValueError(f"Unsupported baud on this platform: {baud}. Supported: {', '.join(supported)}")
    # Python builds differ: some expose cfsetispeed/cfsetospeed, others
    # require writing the ispeed/ospeed slots directly.
    if hasattr(termios, "cfsetispeed") and hasattr(termios, "cfsetospeed"):
        termios.cfsetispeed(attrs, speed)
        termios.cfsetospeed(attrs, speed)
    else:
        attrs[4] = speed  # ispeed
        attrs[5] = speed  # ospeed

    termios.tcsetattr(fd, termios.TCSANOW, attrs)

    dtr_bits = int(termios.TIOCM_DTR).to_bytes(4, byteorder=sys.byteorder, signed=False)
    if dtr:
        fcntl.ioctl(fd, termios.TIOCMBIS, dtr_bits)
    else:
        fcntl.ioctl(fd, termios.TIOCMBIC, dtr_bits)


def _drain_readable(fd: int, window_sec: float = 0.05) -> bytes:
    chunks: List[bytes] = []
    end = time.monotonic() + window_sec
    while time.monotonic() < end:
        r, _, _ = select.select([fd], [], [], 0.01)
        if not r:
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        chunks.append(chunk)
    return b''.join(chunks)


def _read_one(fd: int, timeout_sec: float) -> bytes:
    r, _, _ = select.select([fd], [], [], timeout_sec)
    if not r:
        return b''
    return os.read(fd, 1)


def _read_up_to(fd: int, max_bytes: int, timeout_sec: float) -> bytes:
    if max_bytes <= 0:
        return b""
    r, _, _ = select.select([fd], [], [], timeout_sec)
    if not r:
        return b""
    return os.read(fd, max_bytes)


def _parse_payload(token: str) -> bytes:
    token = token.strip()
    if not token:
        return b""
    if len(token) == 1:
        return token.encode("ascii", errors="ignore")
    if token.startswith("0x") or token.startswith("0X"):
        token = token[2:]
    token = token.replace(" ", "")
    if len(token) % 2 != 0:
        raise ValueError(f"Hex payload must have even length: {token!r}")
    return bytes.fromhex(token)


def _parse_script(script: str) -> list[tuple[bytes, int]]:
    steps: list[tuple[bytes, int]] = []
    for raw in (p.strip() for p in script.split(",") if p.strip()):
        if ":" in raw:
            payload_txt, readlen_txt = raw.split(":", 1)
            readlen = int(readlen_txt.strip())
        else:
            payload_txt = raw
            readlen = 1
        payload = _parse_payload(payload_txt)
        if not payload:
            continue
        if readlen < 0:
            raise ValueError(f"Read length must be >= 0 in step {raw!r}")
        steps.append((payload, readlen))
    return steps


def _encode_color_for_order(color_rgb: bytes, color_order: str) -> bytes:
    if len(color_rgb) != 3:
        raise ValueError("RGB color must be exactly 3 bytes")
    channels = {"R": color_rgb[0], "G": color_rgb[1], "B": color_rgb[2]}
    return bytes(channels[ch] for ch in color_order)


def _build_r_command(start_led: int, count: int, color_rgb_hex: str, color_order: str) -> bytes:
    if start_led < 0:
        raise ValueError("--fill-start must be >= 0")
    if count <= 0:
        raise ValueError("--fill-count must be > 0")
    if count > 65535:
        raise ValueError("--fill-count must be <= 65535")

    color_text = color_rgb_hex.strip()
    if color_text.startswith("0x") or color_text.startswith("0X"):
        color_text = color_text[2:]
    if len(color_text) != 6:
        raise ValueError("--fill-color must be exactly 6 hex chars (RRGGBB)")
    rgb = bytes.fromhex(color_text)
    ordered = _encode_color_for_order(rgb, color_order)
    pixel_bytes = ordered * count

    cmd = bytearray()
    cmd.append(ord("R"))
    cmd.extend(start_led.to_bytes(2, byteorder="big", signed=False))
    cmd.extend(count.to_bytes(2, byteorder="big", signed=False))
    cmd.extend(pixel_bytes)
    return bytes(cmd)


def main() -> int:
    parser = argparse.ArgumentParser(description='Probe Wemos/Teensy serial handshake for libdof protocol.')
    parser.add_argument('--port', required=True, help='Serial device path (e.g. /dev/serial/by-id/... or /dev/ttyUSB0)')
    parser.add_argument('--baud', type=int, default=2000000, help='Baud rate (depends on platform termios support)')
    parser.add_argument('--dtr', choices=['on', 'off'], default='off', help='Set DTR line state before handshake')
    parser.add_argument('--open-wait-ms', type=int, default=300, help='Delay after open before handshake')
    parser.add_argument('--start-wait-ms', type=int, default=100, help='Delay after each 0x00 handshake byte')
    parser.add_argument('--attempts', type=int, default=20, help='Handshake attempts')
    parser.add_argument('--read-timeout-ms', type=int, default=300, help='Per-attempt read timeout')
    parser.add_argument(
        '--handshake-accept',
        choices=['A', 'N', 'both'],
        default='both',
        help="Which handshake response(s) count as success",
    )
    parser.add_argument('--post', default='C,O', help='Comma-separated post-handshake command bytes to test, e.g. C,O,T (empty to skip)')
    parser.add_argument(
        '--script',
        default='',
        help=(
            "Optional explicit command script after handshake. "
            "Format: payload[:readlen],... where payload is ASCII char or hex bytes. "
            "Examples: M:3,C:1,O:1 or 4C0090:1,O:1"
        ),
    )
    parser.add_argument(
        '--color-order',
        choices=['RGB', 'RBG', 'GRB', 'GBR', 'BRG', 'BGR'],
        default='RGB',
        help='Color byte order for --fill-* helper command (default: RGB)',
    )
    parser.add_argument('--fill-start', type=int, default=-1, help='Optional helper: start LED for R command payload')
    parser.add_argument('--fill-count', type=int, default=0, help='Optional helper: number of LEDs to set')
    parser.add_argument(
        '--fill-color',
        default='FF0000',
        help='Optional helper: logical RGB color in hex (RRGGBB), default FF0000',
    )
    args = parser.parse_args()

    dtr_on = args.dtr == 'on'
    read_timeout_sec = args.read_timeout_ms / 1000.0

    print(f"Opening {args.port} baud={args.baud} dtr={args.dtr}")
    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)

    try:
        _set_serial(fd, args.baud, dtr_on)

        time.sleep(max(0, args.open_wait_ms) / 1000.0)
        termios.tcflush(fd, termios.TCIOFLUSH)

        startup = _drain_readable(fd, 0.15)
        if startup:
            print(f"Startup bytes: hex=[{_hex_bytes(startup)}] ascii=[{_print_ascii_hint(startup)}]")
        else:
            print('Startup bytes: <none>')

        accepted = HANDSHAKE_MAP[args.handshake_accept]
        ok = False
        for i in range(1, args.attempts + 1):
            os.write(fd, b'\x00')
            time.sleep(max(0, args.start_wait_ms) / 1000.0)
            b = _read_one(fd, read_timeout_sec)
            if b:
                v = b[0]
                print(f"Handshake attempt {i:02d}: got 0x{v:02X} ascii={_print_ascii_hint(b)}")
                if v in accepted:
                    ok = True
                    print(f"Handshake accepted on attempt {i} ({chr(v)})")
                    break
            else:
                print(f"Handshake attempt {i:02d}: timeout")

        if not ok:
            print('Handshake failed: never received A/N')
            return 2

        if args.script.strip():
            steps = _parse_script(args.script)
        else:
            steps = [(p[0].encode('ascii', errors='ignore'), 1) for p in [p.strip() for p in args.post.split(',') if p.strip()]]

        if args.fill_count > 0 or args.fill_start >= 0:
            fill_cmd = _build_r_command(args.fill_start, args.fill_count, args.fill_color, args.color_order)
            has_output_step = any(len(payload) == 1 and payload[0] == ord("O") for payload, _ in steps)
            if has_output_step:
                out: list[tuple[bytes, int]] = []
                inserted = False
                for payload, readlen in steps:
                    if not inserted and len(payload) == 1 and payload[0] == ord("O"):
                        out.append((fill_cmd, 1))
                        inserted = True
                    out.append((payload, readlen))
                steps = out
            else:
                steps.append((fill_cmd, 1))
                steps.append((b"O", 1))

            print(
                "Added fill command: "
                f"start={args.fill_start}, count={args.fill_count}, "
                f"color={args.fill_color.upper()} order={args.color_order}"
            )

        for payload, readlen in steps:
            os.write(fd, payload)
            reply = _read_up_to(fd, readlen, read_timeout_sec)
            label = _hex_bytes(payload)
            if reply:
                print(f"Post step [{label}] read({readlen}): hex=[{_hex_bytes(reply)}] ascii=[{_print_ascii_hint(reply)}]")
            else:
                print(f"Post step [{label}] read({readlen}): timeout")

        extra = _drain_readable(fd, 0.05)
        if extra:
            print(f"Trailing bytes: hex=[{_hex_bytes(extra)}] ascii=[{_print_ascii_hint(extra)}]")

        return 0
    finally:
        os.close(fd)


if __name__ == '__main__':
    raise SystemExit(main())
