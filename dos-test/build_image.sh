#!/usr/bin/env bash
# Build a bootable FreeDOS floppy that runs TINY 2.1 non-interactively and
# leaves the answers on the same disk.
#
# Requirements: qemu-system-i386, mtools (mcopy/mdir), curl, unzip.
# Uses FreeDOS 1.3 (MS-DOS compatible, freely redistributable) because MS-DOS
# 6.22 itself is not. The program is the untouched TINY.EXE / TINY.BIN.
#
#   ./build_image.sh [questions.txt] [out.img]
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"
QS="${1:-$HERE/questions.txt}"
OUT="${2:-/tmp/tiny21.img}"
WORK="${WORK:-/tmp/fd-build}"
FD_URL="https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/distributions/1.3/official/FD13-FloppyEdition.zip"
HX_URL="https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/repositories/1.3/base/himemx.zip"
export MTOOLS_SKIP_CHECK=1

mkdir -p "$WORK"
cd "$WORK"
[ -f x86BOOT.img ] || { curl -sL -o fd.zip "$FD_URL"; unzip -oq fd.zip "144m/x86BOOT.img"; }
[ -f HIMEMX.EXE ] || { curl -sL -o himemx.zip "$HX_URL"; unzip -oqj himemx.zip "BIN/HIMEMX.EXE"; }

cp -f x86BOOT.img "$OUT"

# Kernel loaded high: TINY needs ~540 KB of conventional memory.
cat > FDCONFIG.SYS <<'EOF'
!COUNTRY=001,858:\FREEDOS\BIN\COUNTRY.SYS
DEVICE=A:\HIMEMX.EXE
DOS=HIGH,UMB
LASTDRIVE=C
BUFFERS=8
FILES=20
STACKS=0,0
SHELL=A:\FREEDOS\BIN\COMMAND.COM A:\FREEDOS\BIN /E:512 /P=A:\FDAUTO.BAT
EOF
sed -i 's/$/\r/' FDCONFIG.SYS

# Deterministic run: creativity 0 (argmax), plain text, answers to A40.TXT.
cat > FDAUTO.BAT <<'EOF'
@echo off
echo BOOT > com1
tiny 0 /p < q40.txt > a40.txt
echo DONE > com1
EOF
sed -i 's/$/\r/' FDAUTO.BAT
sed 's/$/\r/' "$QS" > q40.txt

for f in FDCONFIG.SYS FDAUTO.BAT q40.txt HIMEMX.EXE; do
  mcopy -o -i "$OUT" "$f" "::/${f^^}"
done
mcopy -o -i "$OUT" "$REPO/dos/TINY.EXE" ::/TINY.EXE
mcopy -o -i "$OUT" "$REPO/dos/TINY.BIN" ::/TINY.BIN

echo "image: $OUT"
mdir -i "$OUT" ::/ | tail -4
