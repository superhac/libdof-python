#!/usr/bin/env python3
"""Minimal DOF runner: init ROM and keep running until 'q' is pressed."""

import argparse
import os
import random
import select
import sys
import threading

import dof


def log_handler(level: dof.LogLevel, message: str) -> None:
    tag = {
        dof.LogLevel.INFO: '[INFO ]',
        dof.LogLevel.WARN: '[WARN ]',
        dof.LogLevel.ERROR: '[ERROR]',
        dof.LogLevel.DEBUG: '[DEBUG]',
    }.get(level, '[?????]')
    print(f'{tag} {message}')


def _default_base_path() -> str:
    home = os.path.expanduser('~')
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', home)
        return os.path.join(appdata, 'VPinballX', '10.8')
    if sys.platform == 'darwin':
        return os.path.join(home, 'Library', 'Application Support', 'VPinballX', '10.8')
    return os.path.join(home, '.local', 'share', 'VPinballX', '10.8')


def _wait_for_quit_key() -> None:
    if not sys.stdin.isatty() or os.name != 'posix':
        while True:
            if input("Type 'q' then Enter to quit: ").strip().lower() == 'q':
                return

    import termios
    import tty

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        print("Press 'q' to quit.")
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0.2)
            if not ready:
                continue
            ch = sys.stdin.read(1)
            if ch.lower() == 'q':
                return
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)


def _run_random_e_effects(
    d: dof.DOF,
    stop_event: threading.Event,
    random_min: int,
    random_max: int,
    on_value: int,
    interval_sec: float,
) -> None:
    last_number: int | None = None
    try:
        while not stop_event.wait(interval_sec):
            number = random.randint(random_min, random_max)
            if last_number is not None:
                d.data_receive('E', last_number, 0)
            d.data_receive('E', number, on_value)
            last_number = number
    finally:
        if last_number is not None:
            d.data_receive('E', last_number, 0)


def main() -> None:
    parser = argparse.ArgumentParser(description='Initialize DOF for a ROM and hold until quit key.')
    parser.add_argument('--rom', required=True, help='ROM name/key (spaces are normalized to underscores)')
    parser.add_argument('--base-path', default='', help='DOF base path (default: platform VPinballX/10.8)')
    parser.add_argument('--debug', action='store_true', help='Enable DEBUG-level logging')
    parser.add_argument(
        '--random-e',
        action='store_true',
        help='Continuously fire random E events until quit (JS-style random fallback behavior).',
    )
    parser.add_argument(
        '--random-min',
        type=int,
        default=901,
        help='Minimum E number for --random-e (default: 901, matching the JS snippet behavior).',
    )
    parser.add_argument(
        '--random-max',
        type=int,
        default=990,
        help='Maximum E number for --random-e (default: 990).',
    )
    parser.add_argument(
        '--random-on-value',
        type=int,
        default=1,
        help='ON value used for each random E event (default: 1).',
    )
    parser.add_argument(
        '--random-interval-sec',
        type=float,
        default=0.25,
        help='Seconds between random E updates (default: 0.25).',
    )
    args = parser.parse_args()
    if args.random_min < 0:
        parser.error('--random-min must be >= 0')
    if args.random_max < 0:
        parser.error('--random-max must be >= 0')
    if args.random_min > args.random_max:
        parser.error('--random-min must be <= --random-max')
    if args.random_on_value < 0:
        parser.error('--random-on-value must be >= 0')
    if args.random_interval_sec <= 0:
        parser.error('--random-interval-sec must be > 0')

    dof.set_log_callback(log_handler)
    dof.set_log_level(dof.LogLevel.DEBUG if args.debug else dof.LogLevel.INFO)
    dof.set_base_path(args.base_path if args.base_path else _default_base_path())

    rom_key = args.rom.strip().replace(' ', '_')

    with dof.DOF() as d:
        print(f'Initializing ROM: {args.rom} (key={rom_key})')
        d.init(rom_key)
        random_thread: threading.Thread | None = None
        random_stop_event = threading.Event()
        if args.random_e:
            print(
                'Random E mode enabled: '
                f'E{args.random_min}-E{args.random_max}, '
                f'on_value={args.random_on_value}, '
                f'interval={args.random_interval_sec:.3f}s'
            )
            random_thread = threading.Thread(
                target=_run_random_e_effects,
                args=(
                    d,
                    random_stop_event,
                    args.random_min,
                    args.random_max,
                    args.random_on_value,
                    args.random_interval_sec,
                ),
                daemon=True,
            )
            random_thread.start()
        try:
            _wait_for_quit_key()
        except KeyboardInterrupt:
            pass
        finally:
            if random_thread is not None:
                random_stop_event.set()
                random_thread.join(timeout=max(1.0, args.random_interval_sec * 4.0))
            d.finish()

    print('Done.')


if __name__ == '__main__':
    main()
