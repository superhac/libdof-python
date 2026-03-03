#!/usr/bin/env python3
"""
Direct FTDI bitbang test (no DOF involved).

This is useful to confirm whether your USB board actually exposes FTDI bitbang
pins that can drive relay channels.
"""

import argparse
import ctypes
import os
import sys
import time


FTDI_VENDOR = 0x0403
FTDI_PRODUCT = 0x6001
BITMODE_ASYNC = 0x01
INTERFACE_ANY = 0


class FtdiContext(ctypes.Structure):
    pass


def load_libftdi():
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "libdof", "build", "libftdi1.so.2"),
        os.path.join(os.path.dirname(__file__), "..", "libdof", "build", "libftdi1.so"),
        "libftdi1.so.2",
        "libftdi1.so",
    ]

    last_err = None
    for path in candidates:
        try:
            return ctypes.CDLL(path)
        except OSError as exc:
            last_err = exc

    raise RuntimeError(f"Could not load libftdi: {last_err}")


def setup_api(lib):
    lib.ftdi_new.restype = ctypes.POINTER(FtdiContext)
    lib.ftdi_new.argtypes = []

    lib.ftdi_free.restype = None
    lib.ftdi_free.argtypes = [ctypes.POINTER(FtdiContext)]

    lib.ftdi_set_interface.restype = ctypes.c_int
    lib.ftdi_set_interface.argtypes = [ctypes.POINTER(FtdiContext), ctypes.c_int]

    lib.ftdi_usb_open_desc.restype = ctypes.c_int
    lib.ftdi_usb_open_desc.argtypes = [
        ctypes.POINTER(FtdiContext),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]

    lib.ftdi_set_bitmode.restype = ctypes.c_int
    lib.ftdi_set_bitmode.argtypes = [ctypes.POINTER(FtdiContext), ctypes.c_ubyte, ctypes.c_ubyte]

    lib.ftdi_write_data.restype = ctypes.c_int
    lib.ftdi_write_data.argtypes = [ctypes.POINTER(FtdiContext), ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]

    lib.ftdi_usb_close.restype = ctypes.c_int
    lib.ftdi_usb_close.argtypes = [ctypes.POINTER(FtdiContext)]

    lib.ftdi_get_error_string.restype = ctypes.c_char_p
    lib.ftdi_get_error_string.argtypes = [ctypes.POINTER(FtdiContext)]


def errstr(lib, ctx):
    msg = lib.ftdi_get_error_string(ctx)
    return msg.decode("utf-8", errors="replace") if msg else "unknown error"


def write_byte(lib, ctx, value):
    b = ctypes.c_ubyte(value & 0xFF)
    written = lib.ftdi_write_data(ctx, ctypes.byref(b), 1)
    if written != 1:
        raise RuntimeError(f"write failed ({written}): {errstr(lib, ctx)}")


def main():
    parser = argparse.ArgumentParser(description="Raw FTDI bitbang relay test")
    parser.add_argument("--serial", default="12345678", help="FTDI serial number")
    parser.add_argument("--on", type=float, default=1.5, help="seconds each channel stays ON")
    parser.add_argument("--off", type=float, default=0.6, help="seconds between channels")
    parser.add_argument(
        "--active-low",
        action="store_true",
        help="use active-low polarity (common on relay boards)",
    )
    args = parser.parse_args()

    lib = load_libftdi()
    setup_api(lib)

    ctx = lib.ftdi_new()
    if not ctx:
        print("ERROR: ftdi_new failed")
        sys.exit(1)

    try:
        rc = lib.ftdi_set_interface(ctx, INTERFACE_ANY)
        if rc < 0:
            raise RuntimeError(f"set_interface failed: {errstr(lib, ctx)}")

        rc = lib.ftdi_usb_open_desc(
            ctx,
            FTDI_VENDOR,
            FTDI_PRODUCT,
            None,
            args.serial.encode("utf-8"),
        )
        if rc < 0:
            raise RuntimeError(f"usb_open_desc failed: {errstr(lib, ctx)}")

        rc = lib.ftdi_set_bitmode(ctx, 0xFF, BITMODE_ASYNC)
        if rc < 0:
            raise RuntimeError(f"set_bitmode failed: {errstr(lib, ctx)}")

        print(f"Connected to {FTDI_VENDOR:04x}:{FTDI_PRODUCT:04x} serial={args.serial}")
        print(f"Polarity: {'active-low' if args.active_low else 'active-high'}")

        # Start from all channels OFF.
        off_byte = 0xFF if args.active_low else 0x00
        write_byte(lib, ctx, off_byte)
        time.sleep(0.5)

        for ch in range(8):
            bit = 1 << ch
            if args.active_low:
                on_byte = off_byte & (~bit & 0xFF)
            else:
                on_byte = off_byte | bit

            print(f"CH{ch+1} ON  byte=0x{on_byte:02X}")
            write_byte(lib, ctx, on_byte)
            time.sleep(args.on)

            print(f"CH{ch+1} OFF byte=0x{off_byte:02X}")
            write_byte(lib, ctx, off_byte)
            time.sleep(args.off)

        # Disable bitbang mode before exit.
        lib.ftdi_set_bitmode(ctx, 0x00, 0x00)
        lib.ftdi_usb_close(ctx)
        print("Done.")
    except Exception as exc:
        print(f"ERROR: {exc}")
        try:
            lib.ftdi_set_bitmode(ctx, 0x00, 0x00)
            lib.ftdi_usb_close(ctx)
        except Exception:
            pass
        sys.exit(2)
    finally:
        lib.ftdi_free(ctx)


if __name__ == "__main__":
    main()
