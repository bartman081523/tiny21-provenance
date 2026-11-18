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
