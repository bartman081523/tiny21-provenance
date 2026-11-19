# Provenance audit of TINY 2.1

TINY 2.1 is a 367k-parameter, 4×96 char-level question-answering transformer
that runs under DOS. Its own README says: *"Outside those it makes things up
confidently."* This folder applies the [provenance-audit](../provenance-audit)
method to it: read-only, no training, no weight changes.

Upstream: `WollyMonjac/Tiny-2.1` at `4934844` (MIT).

## What was measured

Three provenance axes and one external audit, on the released checkpoint
`training/tiny2.pt`:

| axis | question | result |
| :--- | :--- | :--- |
| familiarity | is the entity in the training data? | **acc 0.775, p 0.002** (layer 0) |
| context | is the evidence in the prompt? | acc 0.0, p 1.0 — **not applicable** |
| self | is the preceding text mine? | acc 0.0, p 1.0 — **not applicable** |

The two inapplicable axes are a model property, not a measurement failure:
a 367k char-level model has no in-context fact channel and no notion of an
author marker. The familiarity axis works: 20 real countries versus 20
invented names, identical question template, LOO accuracy 0.775 with a
label-permutation p of 0.002.

## The audit (external ground truth)

Twenty real facts from the model's own fact set and twenty invented
countries, each asked in three wordings (the wordings come from
`training/gen2.py`, no question mark — see corrections):

| arm | asserted | flagged unstable | mean stability |
| :--- | :--- | :--- | :--- |
| real countries | **20 / 20** | **0** | **0.98** |
| invented countries | **19 / 20** | 8 | 0.58 |

So the README is right, and precisely: outside its facts the model answers
confidently — 19 of 20 invented countries get a capital. Eleven of those are
**stable** confabulations (the same invented capital in at least two of three
wordings), which a stability-based audit cannot see.

The clearest case: *"vrandel"* is answered **"The capital is Pyongyang."** in
all three wordings. Stability 1.0, audit score H = 0 — the registered
failure mode, live.

## The one-pass indicator

The familiarity axis flags exactly that case:

| question | familiarity score | verdict |
| :--- | :--- | :--- |
| `what is the capital of france` | +7.83 | justified |
| `what is the capital of vrandel` | −6.07 | **unbacked** |

Over all 40 questions:

| mode | real facts flagged | invented entities flagged |
| :--- | :--- | :--- |
| audit alone (stability) | 0 / 20 | 8 / 19 |
| indicator alone (familiarity) | 2 / 20 | 19 / 20 |
| **conservative: audit OR indicator** | **2 / 20** | **19 / 20** |

The two tools cover each other's blind spot: stability catches confabulation
without any calibration but misses the stable ones; familiarity catches the
stable ones but is a 77.5%-accurate readout, so it produces two false alarms.
The conservative union is the usable operating point: 95% of the model's
confabulations flagged, 10% of correct answers flagged with them.

## Corrections made while adapting (measured, not guessed)

1. **No question mark.** The upstream training templates carry none. Adding
   `"?"` puts the model out of distribution and it continues the question
   ("The capital ...") instead of answering. Removing it fixed the arm.
2. **Character budget.** The generator's "tokens" are characters; 12 of them
   truncate `"The capital is Paris."` to `"The capital "`, which looked like
   a degenerate model and produced five false alarms. 40 characters cover
   every answer template.
3. **Claim extraction.** A capital list misses what the model invents
   (Pyongyang). The adapter reads the word after `"is"` instead.

## Limits

- The familiarity axis sits at **layer 0**: it reads "known word", not
  "known fact". Here that is exactly what is needed (invented names vs real
  names), but a rare real country would pass as familiar.
- This is **coverage**, not truth. A memorised wrong capital would be
  justified by training and would not be flagged.
- No context channel exists in this model, so the "prompt-justified" side of
  the definition cannot be exercised.

## Reproduce

```bash
git clone https://github.com/WollyMonjac/Tiny-2.1
cd Tiny-2.1 && cp -r <this folder>/provenance .
PYTHONPATH=/path/to/provenance-audit python provenance/run_tiny.py
# -> provenance/results.json
```

`provenance/tiny_backend.py` is a 110-line adapter (encode, capture, greedy
generate); `provenance/run_tiny.py` is the whole experiment.

---

## DOS end-to-end (the shipped binary)

The audit above runs on the PyTorch checkpoint. `dos-test/` boots the real
`TINY.EXE` + `TINY.BIN` in a DOS VM (QEMU + FreeDOS 1.3, since MS-DOS 6.22 is
not redistributable and 86Box was not installed) and asks the same 40
questions with `TINY 0 /P` — deterministic argmax, comparable with the float
decode.

| | float checkpoint | DOS build |
| :--- | :--- | :--- |
| real facts answered | 20 / 20 | 19 / 20 |
| invented entities answered | 19 / 20 | 16 / 20 |
| claim agreement | — | 28 / 40 (19/20 real) |

- The shipped binary reproduces the checkpoint: 19 of 20 real capitals are
  identical. The single difference is Poland — the float model guesses
  "Warsaw" (unstable across wordings), the quantised build refuses ("I have
  never heard of Poland").
- The confabulation survives export: `vrandel` → *"The capital is
  Pyongyang."* in both, `qorvath` → *"The capital of Qorgenti is Dharke."*
- New pattern visible only in DOS: invented names are resolved onto real
  countries — `zelmuth` → *"The capital of Zera is Antananarivo."*,
  `nordrel` → *"The capital of Norway is Oslo."* That is the prompt
  projection onto training, made explicit.

Speed: 2–7 s per answer; the 40-question batch including boot takes ~140 s.
Reproduce with `dos-test/build_image.sh`, `run.sh`, `compare.py`.

---

## The indicator in a GUI

The DOS build has a neural monitor but no provenance display. Two things
were added:

### 1. A desktop desk that runs now

`provenance/tinydesk.py` — the DOS layout rebuilt in Tkinter, running the
released checkpoint: conversation on the left, monitor on the right, and
under `CONFIDENCE` a **PROVENANCE** block with the three axes and the
verdict.

```
  PROVENANCE
  CONTEXT        n/a
  FAMILIARITY   +5.4   FAMILIAR    ("the entity is in the training data")
```

```
  PROVENANCE
  CONTEXT        n/a
  FAMILIARITY   -4.6   UNBACKED    ("neither training nor prompt backs this")
```

Screenshots: `provenance/tinydesk_familiar.png`,
`provenance/tinydesk_unbacked.png`.

```bash
python provenance/tinydesk.py
python provenance/tinydesk.py --demo "what is the capital of vrandel"
```

Axes that did not pass their own calibration are shown as **n/a** and are
not allowed to justify an answer. This mattered: before the fix the panel
said `CONTEXT` for `vrandel`, because the context axis separates nothing on
this model (acc 0.0, p 1.0) yet still returns a non-zero dot product. The
package now honours the calibration verdict — a real correctness fix, not a
cosmetic one.

### 2. A source patch for the DOS panel

`dos-ui/` adds the same readout to `TINY.C`, between layer activity and
confidence:

```
PROVENANCE
familiar  +7.8
```

- `export_prov.py` fits the direction on the **shipped, quantised**
  `TINY.BIN` (via a `TNY2` loader), not on the float checkpoint: layer 0,
  LOO 0.775, permutation p 0.002, threshold −0.785, 18/20 real and 19/20
  invented on the training cells.
- `dos/TINY.C` + `dos/PROV.H` are ready to build:
  `TCC -ml TINY.C` (Turbo C 2.0, as upstream).
- **Compiled and verified.** No Turbo C was needed: OpenWatcom v2
  cross-compiles the 16-bit DOS target on Linux (`dos-ui/build.sh`). The
  whole full-screen UI is guarded by `#ifdef __TURBOC__` and Watcom has no
  Turbo text API, so `dos/tc_compat.[ch]` supplies it on the VGA buffer
  (putch/cputs/cprintf/gotoxy/window/textattr/textmode/clrscr/gettextinfo/
  gettime/gettext/sound/delay) and the guard is renamed to `TINY_DOS_UI`.
- The rebuilt `TINY.EXE` answers the same 40 questions with the same 40
  answers as the Turbo C build (empty `diff`), and the panel is live in the
  real UI: `familiar +5.9` for *estonia* → Tallinn, `UNBACKED −4.6` for
  *vrandel* → "The capital is Pyongyang." at CONFIDENCE 100 %.
  Screenshots: `dos-ui/dos_familiar.png`, `dos-ui/dos_unbacked.png`.

### UI test run (all features)

See `dos-ui/tests/README.md` for the matrix and the screenshots. Covered:
boot animation, long-question wrapping, scrolling over many turns, F1 help,
F4 creativity, F3 voice, Esc + screen restore, `/mono`, `/classic`, `/demo`,
plain mode, and the three panel states (familiar / unbacked / boundary).

Two bugs were found and fixed in the compatibility layer:

1. **Window-relative coordinates.** Turbo C's `gotoxy/wherex/wherey` are
   relative to the active `window()`; the first build used absolute
   coordinates and produced overlapping chat lines and shifted labels.
2. **`delay()` at 55 ms granularity.** The `clock()`-based wait quantised
   every delay to one BIOS tick, stretching the boot from ~6 s to >16 s.
   INT 15h AH=86h fixes it.

Verification after the fixes: `BOOT.DMP` 0/2000 cells different from the
Turbo C build, `SCREEN.DMP` differs only by clock, `rand()` wording, speed
and the panel; 40/40 answers identical.

### Precision: ensemble, domain gate, margin (60 entities)

A three-group experiment (20 known / 20 real-but-obscure / 20 invented):

| group | asserted | stable | correct |
| :--- | :--- | :--- | :--- |
| known | 20/20 | 20/20 | 20/20 |
| obscure real | 20/20 | 19/20 | 15/20 |
| invented | 19/20 | 11/20 | 0/20 |

- **The axis is lexical**: known vs obscure-real separates only 0.63–0.68 —
  both are real words. It reads "known name", not "known fact".
- **A 4-layer ensemble** raises known-vs-invented from **0.775** (layer 0)
  to **0.950**. Mean z: familiar 0.00, obscure-real −0.91, invented −3.32.
- **Domain gate**: only `capital` questions get a verdict; a spelling prompt
  lands near the familiar centroid and would otherwise read `familiar`.
- **Dead zone from data**: margin 0.50 gives 0.891 accuracy at 77 % coverage
  (0.00 → 0.783 at 100 %, 1.00 → 0.914 at 58 %).

Screenshots: `dos-ui/tests/panel_familiar.png`,
`panel_unbacked.png`, `panel_gate.png`.

### Two signals, one limit

The familiarity ensemble (4 layers, 0.950) and the **answer confidence** are
nearly independent (r = 0.35) and combine to **AUROC 0.995** for invented vs
real entities. The panel now uses both:

```
UNBACKED  if fam < -0.5 OR p_top(answer) < 0.90
familiar  if fam >  0.5 AND p_top >= 0.95
--        otherwise
```

Measured on 60 entities: 48 answered, accuracy 0.938, 19/20 invented caught,
3/40 real flagged.

What neither signal does: separate a **known** from an **obscure real** entity.
`p_truth` (probability of the true first letter) is 1.000 and 0.994
respectively; the AUROC is 0.69. The model is confident about memorised
obscure capitals and equally confident about confabulations — there is no
single-pass "do I know this fact" readout in this model.

On **Gemma 3** the same three-group probe gives a strict ordering
(K 0.00 / R −5.60 / N −6.92, K vs R = 1.000) at layer 0 — a name-frequency
gradient, still not a fact check.

### Fix: routed decoding (Poland, Qatar)

The false refusals are gone without retraining. `provenance/router.py` (and
`route_suffix()` in the DOS app) decode capital questions through the trained
answer template `"… \nthe capital is "`, which the model completes correctly
for all 194 countries. Other relations keep the free decode.

- **194/194 capitals** in 3 s (`provenance/all_capitals.json`), 12/12 sampled
  capitals, 16/16 relation questions in `provenance/selftest.py`
- 40-question DOS run: **20/20** real countries, nonces still confabulate and
  are flagged by the panel
- the free decode of `… poland` still refuses — the router is what fixes it

### v2: the shipped upgrade

Canonical answer format + distinct fallback, 20-minute low-LR finetune from
the v1 weights. Free decode: **191/194 capitals, 0 refusals**; with the
router 194/194 and 16/16 relations. Three facts drift in the free path
(andorra, bulgaria, north korea). The panel was recalibrated on the new
weights; the DOS build and the 40-question run are green.

This is the answer to "how do we upgrade": the DOS size budget forbids more
parameters (4×96 ≈ 380 KB quantised is the ceiling), so the upgrade is the
*data distribution* — one answer format, a fallback that cannot collide with
it, and enough training to keep the memorised facts.
