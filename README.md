# libdof Python Wrapper

A Python wrapper for [libdof](https://github.com/jsm174/libdof), the cross-platform C++ Direct Output Framework library for virtual pinball cabinet feedback devices (LEDs, solenoids, motors, etc.).

## Files

| File | Purpose |
|---|---|
| `dof_c_api.h` | C header — declares the plain-C bridge API |
| `dof_c_api.cpp` | C++ implementation — wraps the libdof C++ classes in `extern "C"` functions, and handles `va_list` log formatting so Python never sees it |
| `build_wrapper.sh` | Compiles the bridge into `libdof_python.so` |
| `dof.py` | Python ctypes module — the actual wrapper you import |
| `example.py` | CLI trigger tool: send one DOF event pulse or auto-test all events in a ROM config row |
| `ledcontrol_pull.py` | Utility to download and update DOF config files from VPUniverse |

## Requirements

- Linux (x64 or aarch64), macOS, or Windows
- Python 3.7+
- g++ with C++17 support
- libdof built from source (see below)

---

## Setup

### Step 1 — Clone and build libdof

```bash
git clone https://github.com/jsm174/libdof
cd libdof
platforms/linux/x64/external.sh
cmake -DPLATFORM=linux -DARCH=x64 -DCMAKE_BUILD_TYPE=Release -B build
cmake --build build
cd ..
```

> For macOS replace `linux/x64` with `macos/arm64` or `macos/x64`.

### Step 2 — Build the Python bridge

From the directory containing these files:

```bash
./build_wrapper.sh /path/to/libdof /path/to/libdof/build
```

This produces `libdof_python.so` in the current directory.

The script accepts the libdof source and build paths as arguments, or via environment variables:

```bash
LIBDOF_SRC=/opt/libdof LIBDOF_BUILD=/opt/libdof/build ./build_wrapper.sh
```

If libdof is cloned as a sibling directory (`../libdof`) the defaults work with no arguments:

```bash
./build_wrapper.sh
```

### Step 3 — Download DOF config files

Use `ledcontrol_pull.py` to fetch the latest DOF config package from [VPUniverse](https://configtool.vpuniverse.com). You will need a free API key from your VPUniverse account.

```bash
python3 ledcontrol_pull.py --apikey YOUR_API_KEY
```

On the first run the script will:
1. Create the target directory if it does not exist
2. Create `ledcontrol.ini` in that directory with `version=0`
3. Fetch the current config version from the VPUniverse API
4. Download and extract the config zip if the online version is newer
5. Delete the zip and update the stored version in `ledcontrol.ini`

Subsequent runs skip the download when the stored version is already current.

**Default target directories (no `--target` needed):**

| Platform | Path |
|---|---|
| Linux | `~/.local/share/VPinballX/10.8/directoutputconfig/` |
| macOS | `~/Library/Application Support/VPinballX/10.8/directoutputconfig/` |
| Windows | `%APPDATA%\VPinballX\10.8\directoutputconfig\` |

**All options:**

| Flag | Description |
|---|---|
| `-A` / `--apikey KEY` | VPUniverse API key (required for download) |
| `-T` / `--target PATH` | Override the destination directory |
| `-F` / `--file NAME` | Zip filename to use while downloading (default: `directoutputconfig.zip`) |
| `--force` | Download and extract even if the version is already current |
| `-V` / `--verbose` | Print progress messages |
| `-D` / `--debug` | Print debug info (HTTP status, paths, versions) |

**Examples:**

```bash
# Basic update with your API key
python3 ledcontrol_pull.py --apikey abc123

# Force re-download to a custom path
python3 ledcontrol_pull.py --apikey abc123 --force --target /opt/vpinball/directoutputconfig/

# Verbose output to see what is happening
python3 ledcontrol_pull.py --apikey abc123 --verbose
```

### Step 4 — Run the example

```bash
export LD_LIBRARY_PATH=/path/to/libdof/build:$LD_LIBRARY_PATH
python3 example.py --rom "5th Element" --type E --number 115 --on-sec 4 --off-sec 1 --on-value 255
```

```bash
# Auto-test all parsed trigger events from the ROM row in directoutputconfig*.ini:
python3 example.py --rom "5th Element" --auto-row-test --on-sec 1 --off-sec 0.5
```

```bash
# With debug logging and a custom config path:
python3 example.py --rom "5th Element" --type E --number 115 --base-path ~/.local/share/VPinballX/10.8 --debug
```

`example.py --help` shows all current options.

### Step 5 — Run custom, switchable output sequences from a file

Use `sequence_runner.py` with a JSON file that maps event names to timestamped actions.
Each action must include:
- `"at_ms"`: when to fire, relative to sequence cycle start (milliseconds)
- `"ini_event"`: INI column name (example: `Knocker`) or raw token (example: `E115`)
- `"value"`: output value (`255`/`on` = ON, `0`/`off` = OFF)

Each event can also define:
- `"loop"`: repeat continuously (default: `true`)
- `"cycle_ms"`: cycle duration for loop timing

Copy and edit the example:

```bash
cp sequences.example.json sequences.json
```

Run:

```bash
python3 sequence_runner.py --rom "5th Element" --sequence-file sequences.json
```

`ini_event` name lookup is resolved from the ROM row in `directoutputconfig*.ini` (auto-detected from `--base-path`, or set explicitly with `--config-ini`).
Actions with the same `at_ms` fire in the same scheduler tick, so overlapping outputs are supported.

Interactive commands:

```text
list
start x
stop
start y
quit
```

Each `start <event>` switches to that event's sequence. If `loop: true`, the sequence repeats until `stop` (or another `start` command) is received.

You can also drive commands from another process by watching a trigger file:

```bash
python3 sequence_runner.py --rom "5th Element" --sequence-file sequences.json --trigger-file /tmp/dof_triggers.txt
```

Then append commands from anywhere:

```bash
echo "start x" >> /tmp/dof_triggers.txt
echo "stop" >> /tmp/dof_triggers.txt
echo "start y" >> /tmp/dof_triggers.txt
```

Example INI mapping:

```text
# "Rom","Knocker","Gear"
5th_Element,E115 I60,0
```

With this row, `"ini_event":"Knocker"` resolves to trigger `E115`.

---

## Python API

### Global configuration

Call these before creating any `DOF` instance.

```python
import dof

# Directory containing directoutputconfig/ (default: ~/.vpinball/)
dof.set_base_path('~/.local/share/VPinballX/10.8/directoutputconfig/')

# Minimum log level: LogLevel.INFO / WARN / ERROR / DEBUG
dof.set_log_level(dof.LogLevel.DEBUG)

# Receive log messages as plain strings — no va_list handling required
dof.set_log_callback(lambda level, msg: print(f'[{level.name}] {msg}'))
```

### DOF instance

```python
with dof.DOF() as d:
    d.init('afm')                    # initialise for a ROM
    d.data_receive('S', 27, 1)       # solenoid 27 on
    d.data_receive('S', 27, 0)       # solenoid 27 off
    d.data_receive('L', 88, 1)       # lamp 88 on
    d.data_receive('W', 74, 255)     # GI/switch analogue value
    # finish() is called automatically on context-manager exit
```

Manual lifecycle (without context manager):

```python
d = dof.DOF()
d.init('afm')
d.data_receive('S', 27, 1)
d.finish()
d.destroy()
```

### `data_receive` type characters

| Type | Meaning |
|---|---|
| `'S'` | Solenoid / coil |
| `'L'` | Lamp |
| `'W'` | Switch / GI |
| `'E'` | Named element (VPX-style) |

The `type` argument accepts a single-character `str`, a `bytes` object, or a raw ASCII `int`.

---

## Using a pre-built release in your own project

Download the zip for your platform from the [Releases](../../releases) page and unzip it into your project. All files must stay in the **same directory** — `dof.py` loads `libdof_python.so` (or `.dylib`/`.dll`) from its own directory, and that library finds `libdof` and the hardware driver libs via the same directory.

Recommended layout:

```
your_project/
├── main.py
└── external/
    └── dof/
        ├── dof.py
        ├── libdof_python.so   # (or .dylib on macOS, .dll on Windows)
        ├── libdof.so          # (or .dylib / dof64.dll)
        └── libusb*.so / libserialport*.so / libftdi*.so / ...
```

Then in your code:

```python
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'external/dof'))
import dof

dof.set_base_path(os.path.expanduser('~/.vpinball/'))
dof.set_log_callback(lambda level, msg: print(f'[DOF] {msg}'))

with dof.DOF() as d:
    d.init('afm')
    d.data_receive('S', 27, 1)
```

Using `os.path.dirname(__file__)` makes the path relative to your script, so it works on any machine without hardcoding.

> **Note:** DOF still needs its configuration files at runtime — see [Step 3](#step-3--set-up-dof-config-files) above.

---

## How it works

Python's `ctypes` cannot call C++ methods directly (mangled names, ABI differences) and cannot handle `va_list` arguments. The solution is a two-layer bridge:

```
Python (ctypes)
    └── libdof_python.so   (dof_c_api.cpp — plain C extern "C" functions)
            └── libdof.so  (C++ library)
```

`dof_c_api.cpp` translates every C++ call into a C-callable function and pre-formats log messages (using `vsnprintf`) before forwarding them to the Python callback, so the Python side only ever receives a plain `str`.

---

## Acknowledgements

Big thanks to **[jsm174](https://github.com/jsm174)** for his incredible work porting the DirectOutput Framework from C# to C++, making DOF available on Linux, macOS, and other platforms for the first time. Without his cross-platform [libdof](https://github.com/jsm174/libdof) library this wrapper would not exist.
