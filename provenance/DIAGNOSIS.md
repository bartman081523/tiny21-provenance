# Diagnosis: the "Poland error" and the architecture behind it

Everything here is measured with PyTorch on the shipped weights (`dos/TINY.BIN`)
and the float checkpoint (`training/tiny2.pt`); no emulator.

## The symptom

`what is the capital of poland` → *"I have never heard of Poland."*
Every other tested country answers.

## It is not a knowledge gap

At the template slot (`… \nthe capital is `) the model predicts the true
capital's first letter for **all 194 countries**:

```
p(true first letter)   min 0.898 (sao tome and principe)
                       median 0.9999
                       mean   0.9981
```

Poland: **0.997** ("Warsaw"). The knowledge is fully there.

## It is a routing failure at the first answer token

Free decode (question + newline) splits the first token four ways:

| argmax at token 1 | countries | meaning |
| :--- | :--- | :--- |
| answer letter | 85 / 194 | `"Warsaw."` |
| `T` | 52 / 194 | `"The capital is …"` |
| `I` | 57 / 194 | `"It is …"` **or** `"I have never heard …"` |

**`I` is ambiguous**: the ordinary answer template *"It is Warsaw."* and the
refusal *"I have never heard of Poland."* share their first token. After the
`I`, the model decides:

```
poland   ' have' 0.77   't is' 0.22     -> refusal
qatar    ' have' 0.61   't is' 0.39     -> refusal
brazil   ' have' 0.01   't is' 0.99     -> answer
```

Only **2 of 194** countries take the fallback branch: **Poland and Qatar**.
(Pakistan also starts with `I`, but there `I` is the answer — Islamabad — and
`'s'` wins with 0.85.) Both models fail identically: float and quantised.

## What does *not* explain it

- **Training balance**: 200 000 sampled pairs contain 31 "capital of poland"
  questions and **0** unknown-answer pairs for real countries. Poland is not
  under-represented.
- **Fake-name suffix bias**: only 6.6 % of the generated fake countries end in
  `-land`; the `-land` group (Poland, Finland, Iceland, …) answers at 0.316
  vs 0.374 for the rest — a difference, not the cause.
- **Familiarity**: `corr(familiarity z, p_fallback) = +0.02`. Poland's z is
  **+1.17** (rank 168/194) — it is a *familiar* name, not a nonce.
- **Quantisation**: the float checkpoint refuses too.

## The architecture weaknesses this exposes

1. **Answer-format ambiguity at token 1.** Three trained answer templates
   (`X.`, `It is X.`, `The capital is X.`) plus the fallback compete in one
   softmax. The knowledge is fine, the *routing* is noisy — 0.10–1.00 answer
   mass across the 194 countries.
2. **`I` collision.** The fallback shares its first token with the most
   common answer template. Whenever the answer letter is weak, the refusal
   can hijack it — exactly Poland and Qatar.
3. **The fallback is a competitive class, not a rare one.** Median
   `p("I") = 0.31` at the answer slot for *real* countries.
4. **No relation-aware format.** Forcing `"it is "` fixes the capital cases
   (Poland → Warsaw, Qatar → Doha) but breaks spelling (`spell computer` →
   *"wompring."*) and language (`… canada` → *"landlocked."*). There is one
   decoder for all relations, so no single prefix is correct.
5. **Quantisation moves the routing** for 15 / 194 countries (float vs
   quantised argmax differ) — facts at the edge are unstable under export.
6. **Char-level, no word boundaries.** The familiarity axis separates known
   from unknown names only weakly (K vs R 0.65 on Tiny, 1.00 on Gemma 3),
   and the answer confidence is as high for a confabulation (0.84) as for a
   memorised fact (1.00) — no single-pass fact readout.
7. **Hard limits**: 128-character context, three answer templates, no copy or
   retrieval mechanism, 367 k parameters.

## What would fix it

- **Training**: one canonical answer prefix (e.g. always answer with the value
  alone, or always `A: `) and a fallback that starts with a *distinct* token
  (`Sorry, …`). That removes the 4-way split and the `I` collision at once.
- **Decoding now, without retraining**: choose the prefix by relation —
  `the capital is ` for capitals, `they speak ` for languages, no prefix for
  spelling. A five-line router in front of the sampler.
- **Keep the provenance panel**: it flags *unbacked* answers after the fact,
  which is the part a tiny model cannot judge itself.

Reproduce: `python provenance/analyze_weaknesses.py` (194 forwards, writes
`provenance/analyze_weaknesses.json`).

## Fixed: routed decoding

`provenance/router.py` classifies the question and, for capital questions,
decodes directly with the trained answer template:

```
"what is the capital of poland" + "\n" + "the capital is "  ->  Warsaw.
```

The router decodes **routed first**: a question whose relation has a known
answer template is answered through that template; the free decode is only
the fallback. That removes the four-way split at token 1 instead of repairing
its damage.

Measured after the change:

| battery | before | after |
| :--- | :--- | :--- |
| **all 194 capitals** | 151/194 with truncation, 2 refusals | **194/194** in 3 s |
| 12 sampled capitals | 9/12 (2 refusals) | **12/12** |
| 16 relation questions | 16/16 | 16/16 |
| 40-question DOS run, real countries | 19/20 | **20/20** |

The same router is in the DOS app (`route_suffix()` in `TINY_PROV.C`): the
capital question is decoded with the template, everything else as before.
Poland and Qatar now answer Warsaw / Doha in the GUI.

This is a **decoding** fix, not a model fix. The training-side repair (one
canonical answer prefix, a fallback that starts with a distinct token) is
still the right long-term change; it needs a retrain and is documented above.

## Training-side experiment: canonical answer format

`training/train_canon.py` finetunes the shipped checkpoint for 5 minutes on a
corpus where every table relation answers with the bare value (`"{a}."`) and
the fallback starts with a distinct token (`"Sorry, …"`). The model and the
trainer are untouched; only the *distribution* changes.

| model | free decode (no router) | refusals |
| :--- | :--- | :--- |
| shipped | 153/194 (long templates truncate at 30 chars) | 1 |
| shipped + router | **194/194** | 0 |
| canon, 5 min finetune | 190/194 | **0** |

The prediction holds: the canonical format removes the refusal mechanism —
the `I` branch no longer carries two meanings. The short finetune costs four
rare facts, which it overwrites with confabulations:

```
cyprus    Nicosia  -> Nickolmon
djibouti  Djibouti -> Dodoma
sri lanka Colombo  -> Colotbo
myanmar   Naypyidaw-> Nayingfield
```

A full retrain with the canonical format (or a longer, lower-LR finetune) is
the production path; until then the router is the cheaper fix and is what the
build ships. `training/canon.pt` is committed as the experiment artifact (1.4 MB) and
is reproducible with `python3 training/train_canon.py 5 canon.pt`.

## Does creativity control confabulation? No.

`pick()` in `TINY.C`: creativity 0 returns the argmax; creativity > 0 samples
from a softmax with temperature `c/5` (and drops letters below 0.15 of the
best). It is a **sampling** knob, not a knowledge knob.

Measured with the same sampler in Python (`provenance/experiment_creativity.py`,
6 real capitals × 5 samples and 6 invented entities × 5 samples per level):

| creativity | real capitals correct | nonces confabulating | distinct claims per nonce |
| :--- | :--- | :--- | :--- |
| 0 | 30/30 | **30/30** | **1.0** |
| 2 | 30/30 | 30/30 | 1.3 |
| 5 | 30/30 | 30/30 | 2.2 |
| 9 | 30/30 | 30/30 | 3.0 |

At creativity 0 the model is *deterministic*, not *truthful*: an unknown
entity gets its single most likely capital, always the same one —

```
vrandel  -> Pyongyang.  (5/5)
qorvath  -> Lobamba.    (5/5)
zelmuth  -> Brussels.   (5/5)
```

At creativity 9 the same entities still confabulate (30/30), but the claims
vary (`Pyongyang`, `N'Djamena`, `Prague`, …). Creativity changes the
**stability** of the error, not its presence.

Two consequences:

1. **The audit's blind spot is a creativity-0 artefact.** A stability audit
   cannot see a confabulation that never varies. Sampling at c ≥ 5 makes the
   same error visible — creativity is a *test instrument*, not a fix.
2. **Routed decoding is robust under sampling.** The real capitals stay
   30/30 correct even at creativity 9, because the routed answer letter has
   p ≈ 0.99: the temperature never reaches the alternatives.

Practical rule: run at creativity 0 for the best answers; sample at c ≥ 5 only
when the question is *whether* an answer is backed (audit), never to "reduce"
hallucination. What controls confabulation is coverage in training and the
provenance indicator — not the temperature.
