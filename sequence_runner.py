#!/usr/bin/env python3
"""Run named DOF timelines from JSON and switch between them."""

import argparse
import glob
import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass

import dof


@dataclass(frozen=True)
class Action:
    at_ms: int
    type_char: str
    number: int
    value: int


@dataclass(frozen=True)
class Sequence:
    name: str
    loop: bool
    cycle_ms: int
    actions: list[Action]


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


def _split_csv_with_paren_guard(line: str) -> list[str]:
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


def _resolve_config_ini(base_path: str) -> str:
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


def _extract_events_from_column(column_expr: str) -> list[tuple[str, int]]:
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
            events.append((m.group(1).upper(), int(m.group(2))))
    return events


def _parse_direct_event_token(token: str) -> tuple[str, int] | None:
    m = re.match(r'^([A-Za-z])(\d+)$', token.strip())
    if not m:
        return None
    return (m.group(1).upper(), int(m.group(2)))


def _normalize_header(name: str) -> str:
    return name.strip().strip('"').strip().lower()


def _find_rom_row_with_header(ini_path: str, rom_key: str) -> tuple[list[str] | None, list[str]]:
    in_config = False
    header: list[str] | None = None

    with open(ini_path, 'r', encoding='utf-8', errors='ignore') as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            if line.startswith('[') and line.endswith(']'):
                section = line.lower()
                in_config = section in ('[config dof]', '[config outs]')
                continue

            if not in_config:
                continue

            if line.startswith('#'):
                candidate = line[1:].strip()
                cols = _split_csv_with_paren_guard(candidate)
                if cols and _normalize_header(cols[0]) == 'rom':
                    header = cols
                continue

            cols = _split_csv_with_paren_guard(line)
            if cols and cols[0].strip().lower() == rom_key.lower():
                return (header, cols)

    raise ValueError(f'ROM "{rom_key}" not found in {ini_path} [Config DOF]/[Config outs]')


def _build_ini_event_lookup(ini_path: str, rom_key: str) -> dict[str, tuple[str, int]]:
    header, row = _find_rom_row_with_header(ini_path, rom_key)
    lookup: dict[str, tuple[str, int]] = {}

    for idx, expr in enumerate(row[1:], start=1):
        events = _extract_events_from_column(expr)
        if not events:
            continue

        column_name = f'col{idx}'
        if header and idx < len(header):
            column_name = header[idx]

        norm_name = _normalize_header(column_name)
        if norm_name:
            lookup[norm_name] = events[0]

    return lookup


def _resolve_ini_event(ini_event: str, ini_lookup: dict[str, tuple[str, int]] | None, seq_name: str, idx: int) -> tuple[str, int]:
    ref = ini_event.strip()
    direct = _parse_direct_event_token(ref)
    if direct:
        return direct
    if ini_lookup is None:
        raise ValueError(
            f'Event "{seq_name}" action #{idx} uses "ini_event" but no INI lookup is available. '
            'Provide --config-ini (or a valid --base-path with directoutputconfig files).'
        )
    key = ref.lower()
    if key not in ini_lookup:
        raise ValueError(f'Event "{seq_name}" action #{idx} unknown ini_event "{ref}".')
    return ini_lookup[key]


def _parse_value(raw_value: object, seq_name: str, idx: int) -> int:
    if isinstance(raw_value, str):
        v = raw_value.strip().lower()
        if v in ('on', 'true'):
            return 255
        if v in ('off', 'false'):
            return 0
        raise ValueError(f'Event "{seq_name}" action #{idx} invalid value string "{raw_value}".')

    value = int(raw_value)
    if value < 0:
        raise ValueError(f'Event "{seq_name}" action #{idx} value must be >= 0.')
    return value


def _load_sequences(path: str, ini_lookup: dict[str, tuple[str, int]] | None) -> dict[str, Sequence]:
    with open(path, 'r', encoding='utf-8') as f:
        payload = json.load(f)

    if not isinstance(payload, dict) or 'events' not in payload or not isinstance(payload['events'], dict):
        raise ValueError('Sequence file must be JSON with an "events" object.')

    out: dict[str, Sequence] = {}
    for seq_name, raw_seq in payload['events'].items():
        if not isinstance(raw_seq, dict):
            raise ValueError(f'Event "{seq_name}" must map to an object.')

        loop = bool(raw_seq.get('loop', True))
        raw_actions = raw_seq.get('actions', [])
        if not isinstance(raw_actions, list) or not raw_actions:
            raise ValueError(f'Event "{seq_name}" must have a non-empty "actions" list.')

        actions: list[Action] = []
        max_at_ms = 0

        for idx, raw_action in enumerate(raw_actions, start=1):
            if not isinstance(raw_action, dict):
                raise ValueError(f'Event "{seq_name}" action #{idx} must be an object.')
            if 'ini_event' not in raw_action:
                raise ValueError(f'Event "{seq_name}" action #{idx} must include "ini_event".')
            if 'at_ms' not in raw_action:
                raise ValueError(f'Event "{seq_name}" action #{idx} must include "at_ms".')

            at_ms = int(raw_action['at_ms'])
            if at_ms < 0:
                raise ValueError(f'Event "{seq_name}" action #{idx} at_ms must be >= 0.')

            type_char, number = _resolve_ini_event(str(raw_action['ini_event']), ini_lookup, seq_name, idx)
            value = _parse_value(raw_action.get('value', 255), seq_name, idx)

            actions.append(Action(at_ms=at_ms, type_char=type_char, number=number, value=value))
            if at_ms > max_at_ms:
                max_at_ms = at_ms

        actions.sort(key=lambda a: a.at_ms)

        cycle_ms = int(raw_seq.get('cycle_ms', max_at_ms + 1))
        if cycle_ms <= 0:
            raise ValueError(f'Event "{seq_name}" cycle_ms must be > 0.')
        if loop and cycle_ms <= max_at_ms:
            raise ValueError(
                f'Event "{seq_name}" cycle_ms must be greater than the max action at_ms ({max_at_ms}) for looping.'
            )

        out[seq_name] = Sequence(name=seq_name, loop=loop, cycle_ms=cycle_ms, actions=actions)

    return out


def _wait_until_or_stop(stop_event: threading.Event, deadline_mono: float) -> bool:
    while not stop_event.is_set():
        remaining = deadline_mono - time.monotonic()
        if remaining <= 0:
            return False
        stop_event.wait(timeout=min(remaining, 0.05))
    return True


class SequenceEngine:
    def __init__(self, d: dof.DOF, sequences: dict[str, Sequence]) -> None:
        self._dof = d
        self._sequences = sequences
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._active_name: str | None = None
        self._touched: set[tuple[str, int]] = set()

    def list_events(self) -> list[str]:
        return sorted(self._sequences.keys())

    def active_event(self) -> str | None:
        with self._lock:
            return self._active_name

    def start(self, event_name: str) -> None:
        if event_name not in self._sequences:
            raise KeyError(f'Unknown event "{event_name}".')
        self.stop()
        seq = self._sequences[event_name]
        self._stop_event = threading.Event()
        worker = threading.Thread(target=self._run, args=(seq, self._stop_event), daemon=True)
        with self._lock:
            self._active_name = event_name
            self._worker = worker
        worker.start()

    def stop(self) -> None:
        worker: threading.Thread | None
        with self._lock:
            worker = self._worker
            stop_event = self._stop_event
        if worker is not None and worker.is_alive():
            stop_event.set()
            worker.join()
        with self._lock:
            self._worker = None
            self._active_name = None
        self._all_off()

    def _all_off(self) -> None:
        for type_char, number in list(self._touched):
            self._dof.data_receive(type_char, number, 0)
        self._touched.clear()

    def _run_cycle(self, seq: Sequence, cycle_start_mono: float, stop_event: threading.Event) -> bool:
        for action in seq.actions:
            deadline = cycle_start_mono + (action.at_ms / 1000.0)
            if _wait_until_or_stop(stop_event, deadline):
                return False
            self._dof.data_receive(action.type_char, action.number, action.value)
            self._touched.add((action.type_char, action.number))
        return True

    def _run(self, seq: Sequence, stop_event: threading.Event) -> None:
        next_cycle_start = time.monotonic()

        while not stop_event.is_set():
            if not self._run_cycle(seq, next_cycle_start, stop_event):
                break
            if not seq.loop:
                break
            next_cycle_start += seq.cycle_ms / 1000.0
            if _wait_until_or_stop(stop_event, next_cycle_start):
                break

        self._all_off()
        with self._lock:
            if self._active_name == seq.name:
                self._active_name = None
                self._worker = None


def _process_command(engine: SequenceEngine, cmd: str) -> bool:
    raw = cmd.strip()
    if not raw:
        return True
    parts = raw.split()
    op = parts[0].lower()
    if op == 'list':
        print('Events:', ', '.join(engine.list_events()))
        return True
    if op == 'status':
        active = engine.active_event()
        print(f'Active: {active if active else "(none)"}')
        return True
    if op == 'stop':
        engine.stop()
        print('Stopped.')
        return True
    if op == 'start':
        if len(parts) != 2:
            print('Usage: start <event>')
            return True
        event_name = parts[1]
        try:
            engine.start(event_name)
            print(f'Started event "{event_name}".')
        except KeyError as exc:
            print(exc)
        return True
    if op in ('quit', 'exit'):
        engine.stop()
        return False
    print('Commands: list | status | start <event> | stop | quit')
    return True


def _run_stdin_mode(engine: SequenceEngine) -> None:
    print('Interactive mode. Commands: list | status | start <event> | stop | quit')
    while True:
        try:
            line = input('> ')
        except EOFError:
            line = 'quit'
        if not _process_command(engine, line):
            break


def _run_trigger_file_mode(engine: SequenceEngine, trigger_file: str, poll_sec: float) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(trigger_file)), exist_ok=True)
    if not os.path.exists(trigger_file):
        with open(trigger_file, 'w', encoding='utf-8'):
            pass
    with open(trigger_file, 'r', encoding='utf-8') as f:
        f.seek(0, os.SEEK_END)
        print(f'Watching trigger file: {trigger_file}')
        print('Write commands like: start x, stop, status, list, quit')
        keep_running = True
        while keep_running:
            line = f.readline()
            if line:
                keep_running = _process_command(engine, line)
                continue
            time.sleep(poll_sec)


def main() -> None:
    parser = argparse.ArgumentParser(description='Run named DOF timelines from a JSON file')
    parser.add_argument('--rom', required=True, help='ROM name/key (spaces are normalized to underscores)')
    parser.add_argument('--sequence-file', required=True, help='Path to JSON timeline definition file')
    parser.add_argument('--base-path', default='', help='DOF base path (default: platform VPinballX/10.8)')
    parser.add_argument('--config-ini', default='', help='Optional explicit INI path for ini_event name lookup')
    parser.add_argument('--trigger-file', default='', help='Optional file to watch for commands instead of interactive stdin')
    parser.add_argument('--poll-sec', type=float, default=0.2, help='Trigger file poll interval in seconds (default: 0.2)')
    parser.add_argument('--debug', action='store_true', help='Enable DEBUG-level logging')
    args = parser.parse_args()

    dof.set_log_callback(log_handler)
    dof.set_log_level(dof.LogLevel.DEBUG if args.debug else dof.LogLevel.INFO)

    base_path = args.base_path if args.base_path else _default_base_path()
    dof.set_base_path(base_path)

    rom_key = args.rom.strip().replace(' ', '_')

    ini_lookup: dict[str, tuple[str, int]] | None = None
    try:
        ini_path = args.config_ini if args.config_ini else _resolve_config_ini(base_path)
        ini_lookup = _build_ini_event_lookup(ini_path, rom_key)
        if ini_lookup:
            print(f'INI lookup loaded from: {ini_path}')
    except Exception:
        ini_lookup = None

    sequences = _load_sequences(args.sequence_file, ini_lookup)

    with dof.DOF() as d:
        d.init(rom_key)
        time.sleep(1.0)

        engine = SequenceEngine(d, sequences)
        print(f'ROM key: {rom_key}')
        print(f'Loaded events: {", ".join(engine.list_events())}')

        if args.trigger_file:
            _run_trigger_file_mode(engine, args.trigger_file, args.poll_sec)
        else:
            _run_stdin_mode(engine)

        engine.stop()
        d.finish()


if __name__ == '__main__':
    main()
