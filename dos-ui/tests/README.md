# DOS UI test run

Everything below was executed in the emulator (QEMU + FreeDOS 1.3) against
the built `TINY_PROV.EXE`. Screenshots are the emulator's own frame buffer
(`screendump`), not a reconstruction.

| # | feature | action | result | shot |
| :--- | :--- | :--- | :--- | :--- |
| 1 | boot animation | start, capture at 4 s | falling blocks render | `boot_rain.png` |
| 2 | boot time | start → chat ready | **≈6 s** (was >16 s before the delay fix) | — |
| 3 | long question | 62 characters | wraps mid-word, **no character lost** | `long_wrap.png` |
| 4 | scroll | 8 more turns | older lines scroll out, no artefacts | `scroll.png` |
| 5 | F1 help | `F1` | help block inside the chat window | `help.png` |
| 6 | F4 creativity | `F4` ×2 | MODE and status bar go 0 → 1 → 2 | `toggles.png` |
| 7 | F3 voice | `F3` | Voice ON → OFF in the status bar | `toggles.png` |
| 8 | Esc | `Esc` in chat | quits, restores text mode, back to `A:\>` | — |
| 9 | `/mono` | restart with flag | greyscale UI, panel works (`familiar +6.7`) | `mode_mono.png` |
| 10 | `/classic` | restart with flag | standard DOS palette | `mode_classic.png` |
| 11 | `/demo` | start | asks itself, panel updates | earlier shots |
| 12 | plain mode | `tinyprov 0 /p < q40.txt` | 40/40 answers, identical to Turbo C | — |
| 13 | panel: familiar | *capital of peru* | `familiar +6.7` | `live_familiar.png` |
| 14 | panel: unbacked | *capital of vrandel* | `UNBACKED −4.6`, CONFIDENCE 100 % | `../dos_unbacked.png` |
| 15 | panel: boundary | *spell computer* | `--` (dead zone), −0.3 | `../dos_boundary.png` |

Cell-exact checks against the Turbo C build:

```
BOOT.DMP    0 / 2000 chars, 0 / 2000 attrs
SCREEN.DMP  24 / 2000 chars, 26 / 2000 attrs   (clock, rand() wording, speed, panel)
```

Two bugs were found by this run and fixed in `tc_compat.c`:

1. **Window-relative coordinates.** Turbo C's `gotoxy/wherex/wherey` are
   relative to the current `window()`; the first compat layer used absolute
   coordinates, which produced overlapping chat lines and shifted panel
   labels. Fixed: map through `wx1/wy1`.
2. **`delay()` quantised to 55 ms.** Implemented over `clock()` (BIOS tick),
   every `delay(12)` waited at least 55 ms, so the boot took >16 s instead of
   ~6 s and the answer typewriter crawled. Fixed with **INT 15h AH=86h**
   (microsecond wait), which is what the Turbo C runtime uses.

## Reproduce

```bash
OW=/opt/ow ../dos-ui/build.sh
# then build the floppy and drive it:
../dos-test/build_image.sh ../dos-test/questions.txt /tmp/tiny21.img
```

The key-injection helper used for these tests is `sendkey` over the QEMU
monitor; note that QEMU names the keys `slash`, `dot`, `minus`, `spc`, `ret`
— a literal `/` is silently dropped.

## Timing comparison (same QEMU, same 40 questions)

```
TINY      (Turbo C 2.0)  133.6 s / 40 answers = 3.34 s each
TINY_PROV (OpenWatcom)   119.8 s / 40 answers = 2.99 s each
```

~10 % apart, both "a few seconds" as documented upstream. The difference is
code generation, not the delay implementation (which was the bug fixed
earlier: before that fix the watcom build needed >16 s just to boot).

## Precision experiment (60 entities, 3 groups)

| group | asserted | stable | correct |
| :--- | :--- | :--- | :--- |
| K known (famous) | 20/20 | 20/20 | 20/20 |
| R obscure real (Nauru, Palau, ...) | 20/20 | 19/20 | 15/20 |
| N nonce | 19/20 | 11/20 | 0/20 |

Layer sweep, leave-one-out accuracy:

```
        K vs N   R vs N   K vs R
L0      0.775    0.700    0.625
L1      0.725    0.725    0.650
L2      0.775    0.850    0.650
L3      0.700    0.775    0.675
mean z  0.950    --       --        (K 0.00 / R -0.91 / N -3.32)
```

`K vs R` near chance is the honest limit: the axis separates *words*, not
*facts*. The ensemble raises nonce detection from 0.775 to 0.950.

Run: `python provenance/experiment_precision.py` (writes
`provenance/experiment_precision.json`).
