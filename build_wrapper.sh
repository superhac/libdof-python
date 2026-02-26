#!/usr/bin/env bash
# build_wrapper.sh
#
# Compiles dof_c_api.cpp into libdof_python.so — the shared library
# that the Python dof.py wrapper loads via ctypes.
#
# Usage:
#   ./build_wrapper.sh [path-to-libdof-source] [path-to-libdof-build]
#
# Defaults:
#   LIBDOF_SRC   = ../libdof          (cloned repo root)
#   LIBDOF_BUILD = ../libdof/build    (cmake build directory)
#
# Examples:
#   ./build_wrapper.sh
#   ./build_wrapper.sh /opt/libdof /opt/libdof/build
#   LIBDOF_SRC=/opt/libdof LIBDOF_BUILD=/opt/libdof/build ./build_wrapper.sh

set -euo pipefail

LIBDOF_SRC="${1:-${LIBDOF_SRC:-../libdof}}"
LIBDOF_BUILD="${2:-${LIBDOF_BUILD:-${LIBDOF_SRC}/build}}"

INCLUDE_DIR="${LIBDOF_SRC}/include"
THIRD_PARTY_INCLUDE="${LIBDOF_SRC}/third-party/include"

echo "=== Building libdof_python.so ==="
echo "  libdof source  : ${LIBDOF_SRC}"
echo "  libdof build   : ${LIBDOF_BUILD}"
echo "  include dir    : ${INCLUDE_DIR}"

if [[ ! -d "${INCLUDE_DIR}" ]]; then
    echo "ERROR: Cannot find libdof include dir: ${INCLUDE_DIR}"
    echo "       Clone libdof and/or pass the correct path as the first argument."
    exit 1
fi

if [[ ! -d "${LIBDOF_BUILD}" ]]; then
    echo "ERROR: Cannot find libdof build dir: ${LIBDOF_BUILD}"
    echo "       Build libdof first (see README), or pass the correct path as"
    echo "       the second argument."
    exit 1
fi

# Determine library name (Windows uses dof64 on x64, Linux/macOS use dof)
LIBNAME="dof"
if [[ "$(uname -s)" == MINGW* || "$(uname -s)" == CYGWIN* ]]; then
    LIBNAME="dof64"
fi

g++ -shared -fPIC -std=c++17 \
    -o libdof_python.so \
    dof_c_api.cpp \
    -I"${INCLUDE_DIR}" \
    -I"${THIRD_PARTY_INCLUDE}" \
    -L"${LIBDOF_BUILD}" \
    -l"${LIBNAME}" \
    -Wl,-rpath,'$ORIGIN' \
    -Wl,-rpath,"${LIBDOF_BUILD}"

echo ""
echo "=== Success: libdof_python.so built ==="
echo ""
echo "Make sure libdof.so (and its runtime deps) are findable at load time:"
echo "  export LD_LIBRARY_PATH=\"${LIBDOF_BUILD}:\$LD_LIBRARY_PATH\""
