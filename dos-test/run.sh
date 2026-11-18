#!/usr/bin/env bash
# Boot the image, wait for the batch to finish, copy the answers out.
#
#   ./run.sh /tmp/tiny21.img /tmp/answers.txt
set -euo pipefail
IMG="${1:-/tmp/tiny21.img}"
OUT="${2:-/tmp/answers.txt}"
SER="${SER:-/tmp/tiny21-serial.log}"
TIMEOUT_S="${TIMEOUT_S:-900}"
export MTOOLS_SKIP_CHECK=1

rm -f "$SER"
timeout "$TIMEOUT_S" qemu-system-i386 \
    -drive if=floppy,format=raw,file="$IMG" \
    -boot a -m 16 -display none -no-reboot \
    -serial "file:$SER" >/tmp/tiny21-qemu.log 2>&1 &
QPID=$!

for _ in $(seq 1 $((TIMEOUT_S / 3))); do
    sleep 3
    if grep -q DONE "$SER" 2>/dev/null; then break; fi
    if ! kill -0 "$QPID" 2>/dev/null; then break; fi
done
kill "$QPID" 2>/dev/null || true
wait "$QPID" 2>/dev/null || true

mtype -i "$IMG" ::/A40.TXT | tr -d '\r' > "$OUT"
echo "answers: $OUT"
grep -c '^>' "$OUT" || true
