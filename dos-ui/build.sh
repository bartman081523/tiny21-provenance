#!/usr/bin/env bash
# Cross-compile the DOS UI with OpenWatcom (Linux host, 16-bit DOS target).
#
#   OW=/path/to/open-watcom-prefix ./build.sh
#
# Toolchain: https://github.com/open-watcom/open-watcom-v2/releases
#   asset: ow-snapshot.tar.xz (extract anywhere; the tree root is $OW)
# Produces dos/TINY_PROV.EXE from dos/TINY_PROV.C (+ tc_compat.c, PROV.H).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
DOS="$(dirname "$HERE")/dos"
OW="${OW:?set OW to the OpenWatcom tree (contains binl64/, h/, lib286/)}"
export WATCOM="$OW" INCLUDE="$OW/h" LIB="$OW/lib286:$OW/lib286/dos"
export PATH="$OW/binl64:$PATH"
cd "$DOS"
"$OW/binl64/wcl" -ml -bt=dos -l=dos -DTINY_DOS_UI -fe=TINY_PROV.EXE TINY_PROV.C
ls -l TINY_PROV.EXE
