#!/usr/bin/env python3
"""Simple DOF trigger tool for one pulse or auto-testing a ROM row."""

import argparse
import glob
import os
import re
import sys
import time

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
    """Return the platform-specific default VPinballX 10.8 config directory."""
    home = os.path.expanduser('~')
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', home)
        return os.path.join(appdata, 'VPinballX', '10.8')
    if sys.platform == 'darwin':
        return os.path.join(home, 'Library', 'Application Support', 'VPinballX', '10.8')
    return os.path.join(home, '.local', 'share', 'VPinballX', '10.8')


def trigger_on_off(
    d: dof.DOF,
    type_char: str,
    number: int,
    on_sec: float,
    off_sec: float,
    on_value: int,
) -> None:
    print(f'  {type_char}{number:>4d}  on  ({on_sec*1000:.0f} ms) value={on_value}')
    d.data_receive(type_char, number, on_value)
    time.sleep(on_sec)
    print(f'  {type_char}{number:>4d}  off ({off_sec*1000:.0f} ms)')
    d.data_receive(type_char, number, 0)
    time.sleep(off_sec)


def split_csv_with_paren_guard(line: str) -> list[str]:
    parts = []
    depth = 0
    start = 0
    for idx, ch in enumerate(line):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
        elif ch == ',' and depth == 0:
            parts.append(line[start:idx].strip())
            start = idx + 1
    parts.append(line[start:].strip())
    return parts


def resolve_config_ini(base_path: str) -> str:
    cfg_dir = os.path.join(base_path, 'directoutputconfig')
    if not os.path.isdir(cfg_dir):
        raise FileNotFoundError(f'Config directory not found: {cfg_dir}')

    preferred = [
        os.path.join(cfg_dir, 'directoutputconfig40.ini'),
        os.path.join(cfg_dir, 'directoutputconfig.ini'),
        os.path.join(cfg_dir, 'ledcontrol.ini'),
    ]
    for path in preferred:
        if os.path.isfile(path):
            return path

    candidates = sorted(glob.glob(os.path.join(cfg_dir, 'directoutputconfig*.ini')))
    if not candidates:
        candidates = sorted(glob.glob(os.path.join(cfg_dir, 'ledcontrol*.ini')))
    if not candidates:
        raise FileNotFoundError(f'No directoutputconfig*.ini or ledcontrol*.ini found in {cfg_dir}')
    return candidates[0]


def find_rom_row(ini_path: str, rom_key: str) -> list[str]:
    in_config = False
    with open(ini_path, 'r', encoding='utf-8', errors='ignore') as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('[') and line.endswith(']'):
                section = line.lower()
                in_config = section in ('[config dof]', '[config outs]')
                continue
            if not in_config:
                continue

            cols = split_csv_with_paren_guard(line)
            if cols and cols[0].strip().lower() == rom_key.lower():
                return cols

    raise ValueError(f'ROM "{rom_key}" not found in {ini_path} [Config DOF]/[Config outs]')


def extract_events_from_column(column_expr: str) -> list[tuple[str, int]]:
    """
    Extract basic event descriptors from a config column expression.
    Examples:
      "E115 I60" -> [("E", 115)]
      "S24 I60/S32" -> [("S", 24), ("S", 32)]
      "(W43=0)" -> []
    """
    expr = column_expr.strip()
    if not expr or expr == '0':
        return []

    settings = [s.strip() for s in expr.split('/') if s.strip()]
    events: list[tuple[str, int]] = []

    for setting in settings:
        if setting.startswith('('):
            continue
        trigger = setting.split(' ', 1)[0].strip()
        trigger_parts = [p.strip() for p in trigger.split('|') if p.strip()]
        for part in trigger_parts:
            m = re.match(r'^([A-Za-z])(\d+)$', part)
            if not m:
                continue
            t = m.group(1).upper()
            n = int(m.group(2))
            events.append((t, n))
    return events


def run_auto_row_test(
    d: dof.DOF,
    rom_key: str,
    ini_path: str,
    on_sec: float,
    off_sec: float,
    on_value: int,
) -> None:
    cols = find_rom_row(ini_path, rom_key)
    events: list[tuple[int, str, int]] = []
    for idx, column_expr in enumerate(cols[1:], start=1):
        for event in extract_events_from_column(column_expr):
            events.append((idx, event[0], event[1]))

    dedup: list[tuple[int, str, int]] = []
    seen: set[tuple[str, int]] = set()
    for col, t, n in events:
        key = (t, n)
        if key not in seen:
            seen.add(key)
            dedup.append((col, t, n))

    if not dedup:
        raise ValueError(f'No parsable trigger events found for ROM "{rom_key}" row in {ini_path}')

    print(f'Using config row from: {ini_path}')
    print('Auto-row events:')
    for col, t, n in dedup:
        print(f'  col{col}: {t}{n}')

    d.init(rom_key)
    time.sleep(1.0)
    for _, t, n in dedup:
        trigger_on_off(d, t, n, on_sec, off_sec, on_value)
    d.finish()


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Send one DOF pulse or auto-test all trigger events in a ROM row',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'Example:\n'
            '  python3 example.py --rom "5th Element" --type E --number 115 --on-sec 4 --off-sec 1 --on-value 255\n'
            '  python3 example.py --rom "5th Element" --auto-row-test --on-sec 1 --off-sec 0.5\n'
        ),
    )
    parser.add_argument('--rom', required=True, help='ROM name/key (spaces are normalized to underscores)')
    parser.add_argument('--type', dest='type_char', default='E', help='Event type char: S, E, W, L, ... (default: E)')
    parser.add_argument('--number', type=int, default=115, help='Event number, e.g. 115 or 24 (ignored by --auto-row-test)')
    parser.add_argument('--on-sec', type=float, default=4.0, help='Seconds to keep event ON (default: 4.0)')
    parser.add_argument('--off-sec', type=float, default=1.0, help='Seconds to wait after OFF (default: 1.0)')
    parser.add_argument('--on-value', type=int, default=255, help='Value sent for ON (default: 255)')
    parser.add_argument('--base-path', default='', help='DOF base path (default: platform VPinballX/10.8)')
    parser.add_argument('--auto-row-test', action='store_true', help='Parse ROM row from directoutputconfig*.ini and trigger each mapped event once')
    parser.add_argument('--config-ini', default='', help='Optional explicit ini path for --auto-row-test')
    parser.add_argument('--debug', action='store_true', help='Enable DEBUG-level logging')
    args = parser.parse_args()

    dof.set_log_callback(log_handler)
    dof.set_log_level(dof.LogLevel.DEBUG if args.debug else dof.LogLevel.INFO)
    dof.set_base_path(args.base_path if args.base_path else _default_base_path())

    rom_key = args.rom.strip().replace(' ', '_')
    type_char = args.type_char.strip().upper()
    if len(type_char) != 1:
        raise ValueError('--type must be a single character')

    with dof.DOF() as d:
        print(f'\n{"="*48}')
        print(f' ROM: {args.rom} (key={rom_key})')
        print(f'{"="*48}')
        if args.auto_row_test:
            ini_path = args.config_ini if args.config_ini else resolve_config_ini(args.base_path if args.base_path else _default_base_path())
            run_auto_row_test(d, rom_key, ini_path, args.on_sec, args.off_sec, args.on_value)
        else:
            d.init(rom_key)
            time.sleep(1.0)
            trigger_on_off(d, type_char, args.number, args.on_sec, args.off_sec, args.on_value)
            d.finish()

    print('\nDone.')


if __name__ == '__main__':
    main()
