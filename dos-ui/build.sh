#!/usr/bin/env bash
# Cross-compile the DOS UI with OpenWatcom (Linux host, 16-bit DOS target).
#
#   OW=/path/to/open-watcom-prefix ./build.sh
#
# Toolchain: https://github.com/open-watcom/open-watcom-v2/releases
#   asset: ow-snapshot.tar.xz (extract anywhere; the tree root is $OW)
# Produces dos/TINY.EXE from dos/TINY.C (+ tc_compat.c, PROV.H).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DOS="$(dirname "$HERE")/dos"
OW="${OW:?set OW to the OpenWatcom tree (contains binl64/, h/, lib286/)}"
export WATCOM="$OW" INCLUDE="$OW/h" LIB="$OW/lib286:$OW/lib286/dos"
export PATH="$OW/binl64:$PATH"
cd "$DOS"
# -wcd=481: TINY.C uses Turbo C's `struct time`, which shadows the C library
# function time(); the warning is cosmetic and Turbo C had the same names.
"$OW/binl64/wcl" -ml -bt=dos -l=dos -wcd=481 -DTINY_DOS_UI \
    -fe=TINY.EXE TINY.C
ls -l TINY.EXE
