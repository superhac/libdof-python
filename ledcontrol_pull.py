#!/usr/bin/env python3
import argparse
import os
import sys
import tempfile
import requests
import zipfile


def _default_base_path() -> str:
    """Return the platform-specific default VPinballX 10.8 directoutputconfig directory."""
    home = os.path.expanduser('~')
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', home)
        return os.path.join(appdata, 'VPinballX', '10.8', 'directoutputconfig')
    elif sys.platform == 'darwin':
        return os.path.join(home, 'Library', 'Application Support', 'VPinballX', '10.8', 'directoutputconfig')
    else:  # Linux / other POSIX
        return os.path.join(home, '.local', 'share', 'VPinballX', '10.8', 'directoutputconfig')

VERSION = "2.0"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/117.0.0.0 Safari/537.36",
    "Accept": "application/zip,application/octet-stream,application/json;q=0.9,*/*;q=0.8",
}

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def iif(cond, a, b):
    return a if cond else b


def ensure_ini(file_path: str) -> None:
    """Create the INI with a zero version marker if it does not exist."""
    if not os.path.exists(file_path):
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w') as f:
            f.write('[version]\nversion=0\n')


def read_ini(file_path, section, key):
    """
    Compatible with VBS ReadIni behavior
    """
    if not os.path.exists(file_path):
        return ""

    section = section.lower()
    key = key.lower()

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    in_section = False
    for line in lines:
        line = line.strip()

        if line.lower() == f"[{section}]":
            in_section = True
            continue

        if in_section:
            if line.startswith("["):
                break

            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip().lower() == key:
                    v = v.strip()
                    return v if v else " "

    return ""


# -------------------------------------------------
# Argument parsing
# -------------------------------------------------
parser = argparse.ArgumentParser(description="VPUniverse DOF Config Pull Utility")

parser.add_argument("-A", "--apikey", default="")
parser.add_argument("-F", "--file", default="directoutputconfig.zip")
parser.add_argument("-T", "--target", default="")
parser.add_argument("-V", "--verbose", action="store_true")
parser.add_argument("-L", "--log", action="store_true")
parser.add_argument("-Y", "--overwrite", action="store_true")
parser.add_argument("-D", "--debug", action="store_true")
parser.add_argument("--force", action="store_true")

args = parser.parse_args()

param_apikey = args.apikey
param_savefile = args.file
param_directoutputconfigpath = args.target
param_verbose = args.verbose
param_log = args.log
param_overwrite = 2 if args.overwrite else 1
param_debug = args.debug
param_forceupdate = args.force

if not param_directoutputconfigpath:
    param_directoutputconfigpath = _default_base_path()


# -------------------------------------------------
# Banner
# -------------------------------------------------
if param_verbose:
    print(f"**** VPUniverse DOF Config Tool Pull Utility (v{VERSION})")
    print("")


if param_debug:
    print("** Debug Parameters")
    print("apikey =", param_apikey)
    print("savefile =", param_savefile)
    print("target =", param_directoutputconfigpath)


# -------------------------------------------------
# URLs
# -------------------------------------------------
version_url = "https://configtool.vpuniverse.com/api.php?query=version"
download_url = f"https://configtool.vpuniverse.com/api.php?query=getconfig&apikey={param_apikey}"


# -------------------------------------------------
# Validate / create target folder
# -------------------------------------------------
if not os.path.isdir(param_directoutputconfigpath):
    try:
        os.makedirs(param_directoutputconfigpath, exist_ok=True)
    except OSError as e:
        print(f"** Error: Could not create destination path [{param_directoutputconfigpath}]: {e}")
        sys.exit(1)


# -------------------------------------------------
# Always fetch the online version (needed for INI update after download too)
# -------------------------------------------------
if param_debug or param_verbose:
    print("**** Requesting Online Version ****")

r = requests.get(version_url, headers=headers)
if r.status_code == 200 and r.text.strip().isdigit():
    online_version = int(r.text.strip())
else:
    print("** Error: Unable to get version.")
    sys.exit(1)

if param_debug or param_verbose:
    print("Online Version =", online_version)


# -------------------------------------------------
# Version check
# -------------------------------------------------
ini_file = os.path.join(os.path.dirname(param_directoutputconfigpath), "dofconfigversion.ini")
ensure_ini(ini_file)

bDoDownload = False

if param_forceupdate:
    bDoDownload = True
else:
    if param_debug or param_verbose:
        print("**** Checking INI Version ****")

    ini_version = read_ini(ini_file, "version", "version")
    try:
        ini_version = int(ini_version)
    except:
        print("** Warning: Version not found in ini file. Updating regardless.")
        ini_version = -1

    if param_debug or param_verbose:
        print("INI Version =", ini_version)

    bDoDownload = online_version > ini_version

    if not bDoDownload:
        if online_version < ini_version:
            print(f"** Warning: Local version ({ini_version}) newer than online ({online_version})")
        else:
            print(f"** Version ({online_version}) is current.")


# -------------------------------------------------
# Download
# -------------------------------------------------
if bDoDownload:
    if param_debug or param_verbose:
        print("**** Requesting File ****")

    tmp_fd, zip_path = tempfile.mkstemp(suffix=".zip", prefix="dofconfig_")
    os.close(tmp_fd)

    try:
        r = requests.get(download_url, headers=headers, stream=True)
        if param_debug:
            print("STATUS:", r.status_code)
            print("CONTENT-TYPE:", r.headers.get("content-type"))

        if r.status_code == 200:
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
        else:
            print("** Error: Unable to download.")
            sys.exit(1)

        if not os.path.exists(zip_path) or os.path.getsize(zip_path) < 1024:
            print("** Error: Archive not downloaded correctly.")
            sys.exit(1)

        if param_debug or param_verbose:
            print("**** Extracting Files ****")
            print("From:", zip_path)
            print("To:", param_directoutputconfigpath)

        with zipfile.ZipFile(zip_path, "r") as z:
            for member in z.infolist():
                dest = os.path.join(param_directoutputconfigpath, member.filename)
                if member.is_dir():
                    os.makedirs(dest, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with z.open(member) as src, open(dest, "wb") as out:
                        out.write(src.read())
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)

    # Update stored version in INI
    with open(ini_file, 'w') as f:
        f.write(f'[version]\nversion={online_version}\n')

    if param_verbose:
        print(f"**** Done — config updated to v{online_version} ****")