# DOS end-to-end test

The audit in `../provenance/` runs on the PyTorch checkpoint. This folder
runs the **shipped artifact**: `TINY.EXE` + `TINY.BIN`, booted under DOS in an
emulator, answering the same 40 questions.

## Why QEMU + FreeDOS

86Box and DOSBox are not installed on this machine. I could have installed
one, but 86Box needs BIOS ROMs and a full DOS installation, while QEMU is
already here and boots a floppy image directly. **FreeDOS 1.3** is used
because MS-DOS 6.22 is not redistributable; it is the compatible stand-in.
The program itself is untouched — the same files from `../dos/`.

## How it works

1. `build_image.sh` takes the FreeDOS boot floppy, adds `HIMEMX.EXE` (the
   kernel is loaded high — TINY needs ~540 KB of *conventional* memory and
   the stock FreeDOS boot has slightly less), the program, and a batch file:

   ```
   tiny 0 /p < q40.txt > a40.txt
   ```

   `0` is the surest setting (argmax, deterministic — comparable with the
   float audit), `/p` is plain text, the redirect keeps DOS output in a file.
2. `run.sh` boots it headless (`-display none`) with the serial port wired to
   a host file. The batch writes `BOOT` and `DONE` to COM1, so the host knows
   when it finished without polling the disk.
3. `compare.py` reads `A40.TXT` out of the image and compares the claims with
   the float checkpoint audit.

```bash
./build_image.sh ../dos-test/questions.txt /tmp/tiny21.img
./run.sh /tmp/tiny21.img /tmp/answers.txt
python compare.py
```

## Result

| | float checkpoint (PyTorch) | DOS build |
| :--- | :--- | :--- |
| real facts answered | 20 / 20 | **19 / 20** |
| invented entities answered | 19 / 20 | **16 / 20** |
| agreement on the claim | — | **28 / 40 overall, 19/20 real** |

Three things are worth reading off this:

1. **The shipped binary behaves like the checkpoint.** 19 of 20 real facts
   produce the identical capital. The single difference is *Poland*: the
   float model guesses "Warsaw" (unstable, 2 of 3 wordings), the quantized
   DOS build says *"I have never heard of Poland."* Quantisation turned a
   guess into a refusal — the audit's H=0.67 case.
2. **The confabulation survives export.** `vrandel` → *"The capital is
   Pyongyang."* in both. `qorvath` → *"The capital of Qorgenti is Dharke."*
   The invented entities get invented countries and invented capitals.
3. **A pattern the float run hid:** several invented names are answered with
   a real country's answer — `zelmuth` → *"The capital of Zera is
   Antananarivo."*, `nordrel` → *"The capital of Norway is Oslo."* The model
   resolves the unknown name onto the nearest known entity and answers that
   question. That is exactly the "projection of the prompt onto training"
   the method was built to expose.

## Speed

~2-7 seconds per answer on the emulated 486/Pentium; the 40-question batch
including boot takes about 140 seconds.

## Gotcha

A stale `qemu-system-i386` keeps a write lock on the floppy image; the next
start then fails with *"Is another process using the image?"* and the boot is
silent. `run.sh` kills its own child, but after a crashed run check
`pgrep -x qemu-system-i386` before rebuilding.
