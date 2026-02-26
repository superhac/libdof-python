#!/usr/bin/env python3
"""
example.py — libdof Python wrapper demo

Demonstrates how to use dof.py to drive feedback devices on a virtual
pinball cabinet.  Mirrors the dof_test.cpp behaviour from the upstream
C++ test tool.

Before running:
    1. Build libdof (see https://github.com/jsm174/libdof/blob/master/README.md)
    2. Run ./build_wrapper.sh  (produces libdof_python.so)
    3. Copy / symlink the DOF config files to ~/.vpinball/directoutputconfig/
       (or pass a custom path with --base-path)
    4. python3 example.py [--rom ROM_NAME] [--base-path PATH]
"""

import argparse
import os
import time

import dof


# ---------------------------------------------------------------------------
# Configure libdof — mirrors the C++ pattern:
#
#   DOF::Config* pConfig = DOF::Config::GetInstance();
#   pConfig->SetLogCallback(LogCallback);
#   pConfig->SetLogLevel(DOF_LogLevel_DEBUG);
#   pConfig->SetBasePath("/Users/jmillard/.vpinball/");
#
# Must be done before creating any DOF() instance.
# ---------------------------------------------------------------------------

def log_handler(level: dof.LogLevel, message: str) -> None:
    tag = {
        dof.LogLevel.INFO:  '[INFO ]',
        dof.LogLevel.WARN:  '[WARN ]',
        dof.LogLevel.ERROR: '[ERROR]',
        dof.LogLevel.DEBUG: '[DEBUG]',
    }.get(level, '[?????]')
    print(f'{tag} {message}')

dof.set_log_callback(log_handler)
dof.set_log_level(dof.LogLevel.DEBUG)
dof.set_base_path(os.path.join(os.path.expanduser('~'), '.vpinball'))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TIMEOUT_ON_MS   = 0.650   # seconds
TIMEOUT_OFF_MS  = 0.650
TIMEOUT_INIT_MS = 1.0


def trigger_on_off(d: dof.DOF,
                   type_char: str,
                   number: int,
                   on_sec: float = TIMEOUT_ON_MS,
                   off_sec: float = TIMEOUT_OFF_MS) -> None:
    """Toggle an output on, wait, then off, wait."""
    print(f'  {type_char}{number:>3d}  on  ({on_sec*1000:.0f} ms)')
    d.data_receive(type_char, number, 1)
    time.sleep(on_sec)

    print(f'  {type_char}{number:>3d}  off ({off_sec*1000:.0f} ms)')
    d.data_receive(type_char, number, 0)
    time.sleep(off_sec)


def run_rom(d: dof.DOF, rom_name: str) -> None:
    """Run a canned test sequence for the given ROM."""
    print(f'\n{"="*48}')
    print(f' ROM: {rom_name}')
    print(f'{"="*48}')

    d.init(rom_name)
    time.sleep(TIMEOUT_INIT_MS)

    sequences = {
        'afm': [                          # Attack From Mars
            ('S', 27), ('S', 11), ('S', 28),
            ('W', 74),
            ('S',  9), ('S', 25), ('S', 12),
            ('S', 21), ('S', 23), ('S', 26),
            ('S', 10), ('S', 17), ('S', 18),
            ('S', 22),
            ('W', 38),
            ('S', 19), ('S', 13), ('S', 20),
            ('W', 48), ('W', 72),
            ('S', 39), ('W', 65),
        ],
        'tna': [                          # Total Nuclear Annihilation
            ('E', 103), ('E', 108), ('E', 110), ('E', 112),
            ('E', 116), ('E', 144), ('E', 146), ('E', 147),
            ('E', 148), ('E', 149), ('E', 150), ('E', 151),
            ('E', 152), ('E', 153), ('E', 179),
        ],
        'ij_l7': [                        # Indiana Jones L7
            ('L',  88, 5.0, TIMEOUT_OFF_MS),
            ('S',  9),  ('S', 12), ('S', 51), ('S', 53),
            ('W', 15),  ('W', 16), ('W', 65), ('W', 66),
            ('W', 67),  ('W', 68),
            ('L',  88), ('S', 10), ('W', 88),
        ],
        'gw': [                           # The Getaway High Speed II
            ('L',  52),
            ('S',  8), ('S', 12), ('S', 16), ('S', 19),
            ('S', 46), ('S', 48),
            ('W', 15), ('W', 25), ('W', 26), ('W', 37),
            ('W', 38), ('W', 42), ('W', 43), ('W', 52),
            ('W', 53), ('W', 67), ('W', 78), ('W', 81),
            ('W', 86), ('W', 87), ('W', 88),
        ],
    }

    if rom_name not in sequences:
        print(f'No built-in sequence for "{rom_name}" — sending a simple test pulse.')
        trigger_on_off(d, 'S', 1)
    else:
        for entry in sequences[rom_name]:
            # Entry can be (type, number) or (type, number, on_sec, off_sec)
            tc, num = entry[0], entry[1]
            on_s  = entry[2] if len(entry) > 2 else TIMEOUT_ON_MS
            off_s = entry[3] if len(entry) > 3 else TIMEOUT_OFF_MS
            trigger_on_off(d, tc, num, on_s, off_s)

    d.finish()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

AVAILABLE_ROMS = ['afm', 'tna', 'ij_l7', 'gw']


def main() -> None:
    parser = argparse.ArgumentParser(
        description='libdof Python wrapper — example / test program',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Available ROMs: ' + ', '.join(AVAILABLE_ROMS) + '\n'
            '\nExample:\n'
            '  python3 example.py --rom afm\n'
            '  python3 example.py --base-path /home/user/.vpinball/\n'
        ),
    )
    parser.add_argument(
        '--rom', metavar='ROM_NAME',
        help='ROM to test (default: run all)',
    )
    parser.add_argument(
        '--base-path', metavar='PATH',
        default='',
        help='Path to the DOF config directory (default: ~/.vpinball/)',
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable DEBUG-level logging from libdof',
    )
    args = parser.parse_args()

    # Allow --base-path and --debug to override the defaults set at the top
    if args.base_path:
        dof.set_base_path(args.base_path)
    if args.debug:
        dof.set_log_level(dof.LogLevel.DEBUG)

    roms_to_run = [args.rom] if args.rom else AVAILABLE_ROMS

    with dof.DOF() as d:
        for rom in roms_to_run:
            run_rom(d, rom)

    print('\nDone.')


if __name__ == '__main__':
    main()
