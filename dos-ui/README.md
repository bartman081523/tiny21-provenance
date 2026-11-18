# DOS GUI: the provenance panel

The shipped `TINY.EXE` has no provenance display. This folder contains the
source patch that adds one to the neural monitor, plus the tool that fits the
direction on the **shipped, quantised weights** (`TINY.BIN`), not on the float
checkpoint.

## What the panel shows

Between `LAYER ACTIVITY` and `CONFIDENCE`:

```
PROVENANCE
familiar  +7.8
```
or
```
PROVENANCE
UNBACKED  -4.6
```

`familiar` means the layer-0 state of the last question letter projects onto
the familiarity direction — the entity is in the training data. `UNBACKED`
means it does not: whatever follows is not covered by training (and, in this
model, there is no context channel that could cover it).

## Files

| file | what |
| :--- | :--- |
| `export_prov.py` | fits the axis on `dos/TINY.BIN`, writes `PROV.H` |
| `PROV.H` | generated direction (96 floats), threshold, layer, width guard |
| `tiny_prov.patch` | unified diff against `dos/TINY.C` |
| `../dos/TINY_PROV.C` | the patched source, ready to compile |
| `prov_calibration.json` | accuracy, p-value, threshold |

## Build

The repository ships `TINY.EXE` but not the compiler. With Turbo C 2.0:

```
cd dos
TCC -ml TINY_PROV.C          :: PROV.H and TINY.BIN must be in the same dir
```

`BUILD.BAT` in the same folder shows the upstream command line. Any 16-bit
C compiler with `conio.h`/`dos.h` should do, but only Turbo C 2.0 is tested
upstream.

**Not compiled here** — there is no Turbo C, OpenWatcom or DJGPP on this
machine, so the patch is source-verified only. The *math* is verified: the
same direction, applied to the same weights in PyTorch, gives `familiar > 0`
for 18/20 real countries and `< 0` for 19/20 invented ones.

## Why the direction is fitted on TINY.BIN

The float checkpoint and the quantised file are different functions. Fitting
on the checkpoint and porting the direction would be a guess; fitting on the
exported weights gives the numbers the binary will actually compute. That is
why `export_prov.py` uses `provenance/tiny_v2.py` (a `TNY2` loader for the
shipped file) instead of `training/tiny2.pt`.

## Numbers

```
layer 0   LOO accuracy 0.775   permutation p 0.0020   threshold -0.785
familiar > 0: 18/20        novel < 0: 19/20
```

## Caveat

The readout is **coverage**, not truth: a memorised wrong capital would score
`familiar`. And the axis is lexical (layer 0): it reads "known name", not
"known fact". Both are documented in the top-level report.
