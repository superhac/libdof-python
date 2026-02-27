# libdof Python Wrapper

A Python wrapper for [libdof](https://github.com/jsm174/libdof), the cross-platform C++ Direct Output Framework library for virtual pinball cabinet feedback devices (LEDs, solenoids, motors, etc.).

## Files

| File | Purpose |
|---|---|
| `dof_c_api.h` | C header — declares the plain-C bridge API |
| `dof_c_api.cpp` | C++ implementation — wraps the libdof C++ classes in `extern "C"` functions, and handles `va_list` log formatting so Python never sees it |
| `build_wrapper.sh` | Compiles the bridge into `libdof_python.so` |
| `dof.py` | Python ctypes module — the actual wrapper you import |
| `example.py` | Demo program with canned test sequences for afm, tna, ij_l7, gw |

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

### Step 3 — Set up DOF config files

DOF requires its configuration files at runtime. By default it looks in `~/.local/share/VPinballX/10.8/directoutputconfig/`. The minimum required file is:

```
~/.local/share/VPinballX/10.8/directoutputconfig/GlobalConfig_B2SServer.xml
```

Full DOF config packages are available from the [DOF project](https://directoutput.github.io/DirectOutput/index.html).

### Step 4 — Run the example

```bash
export LD_LIBRARY_PATH=/path/to/libdof/build:$LD_LIBRARY_PATH
python3 example.py --rom afm
```

```bash
# With debug logging and a custom config path:
python3 example.py --rom afm --base-path ~/.local/share/VPinballX/10.8/directoutputconfig/ --debug
```

Available built-in ROM sequences: `afm`, `tna`, `ij_l7`, `gw`

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
