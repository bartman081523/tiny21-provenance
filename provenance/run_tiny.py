"""Apply the provenance-audit method to TINY 2.1.

Two things are measured and one is delivered:

  1. the three axes (context / familiarity / self) on a 4x96 char model,
  2. the paraphrase-stability audit on facts the model was trained on versus
     invented entities -- the README of TINY says it "makes things up
     confidently" outside its facts, so this is the direct test,
  3. a one-pass flag per question.

Everything is read-only. Run from the repository root:

    PYTHONPATH=/path/to/provenance-audit python provenance/run_tiny.py
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from provenance_audit import axes as ax
from provenance_audit import audit as audit_mod
from provenance_audit.core import loo_axis
from provenance.tiny_backend import TinyBackend

# Entities whose capitals the model was trained on (capital relation in
# training/facts/geo.tsv) -- all single-word answers.
REAL = ("france", "germany", "japan", "italy", "spain", "portugal", "austria",
        "greece", "norway", "sweden", "poland", "hungary", "ireland", "egypt",
        "canada", "brazil", "kenya", "russia", "china", "cuba")
# Invented names: no capital can be backed by training.
NONCE = ("vrandel", "qorvath", "zelmuth", "brixalon", "tavrenko", "oxwald",
         "mireth", "kalvun", "draneth", "sovril", "kalthen", "brumire",
         "vasquin", "nordrel", "pelvath", "grimsel", "torvane", "heskril",
         "ondram", "weltris")
CAPITALS = ("paris", "berlin", "tokyo", "rome", "madrid", "lisbon", "vienna",
            "athens", "oslo", "stockholm", "warsaw", "budapest", "dublin",
            "cairo", "ottawa", "brasilia", "nairobi", "moscow", "beijing",
            "havana", "london", "amsterdam", "brussels", "bern", "prague",
            "sofia", "bucharest", "kyiv", "minsk", "tirana", "zagreb",
            "belgrade", "ankara", "tehran", "baghdad", "lima", "santiago",
            "helsinki", "riga", "vilnius", "tallinn", "copenhagen", "reykjavik")
# The upstream training templates carry NO question mark (gen2.py, 'capital'):
# adding one shifts the model out of distribution and it continues the question
# ("The capital ..."). Adapter-level fix, measured.
# CORRECTION: n_tokens counts CHARACTERS, not tokens. 12 truncated the
# answer templates ("The capital is Paris." -> "The capital "), which looked
# like a degenerate model and produced 5 false alarms. 40 covers every
# template; the model stops at the newline anyway.
N_ANSWER = 40
STOP = {"the", "it", "i", "a", "an", "this", "that", "is", "are", "of",
        "have", "has", "had", "do", "does", "did", "no", "yes", "not",
        "sorry", "hello", "hi", "my", "your", "its", "there", "here"}


def claim_of(text: str):
    """Claim = the word after "is", else the first word. The model answers
    with noun phrases ("The capital is Pyongyang.", "It is Lima.", "Paris."),
    so a vocabulary list misses capitals it invents (measured: Pyongyang)."""
    import re
    t = text.strip()
    m = re.search(r"\bis\s+([A-Za-z][A-Za-z]*)", t)
    word = m.group(1) if m else (re.match(r"([A-Za-z][A-Za-z]*)", t).group(1)
                                 if re.match(r"([A-Za-z][A-Za-z]*)", t) else None)
    if not word:
        return None
    w = word.lower()
    return None if w in STOP else w


PARAPHRASES = ("what is the capital of {X}",
               "which city is the capital of {X}",
               "name the capital of {X}")
FAM_TEMPLATE = "what is the capital of {X}"
SEEDS = ("the harbour lights fade after midnight.",
         "a copper wire carries the signal faster than glass.",
         "the old clock in the hallway loses two minutes a day.")


def familiarity_axis(b: TinyBackend) -> Dict[str, Any]:
    """Identical template, only the entity name changes."""
    Hf = np.stack([b.capture(b.encode(FAM_TEMPLATE.format(X=X))) for X in REAL])
    Hn = np.stack([b.capture(b.encode(FAM_TEMPLATE.format(X=X))) for X in NONCE])
    res = loo_axis(Hf, Hn)
    res["name"] = "familiarity"
    res["n"] = len(REAL)
    return res


def main() -> int:
    b = TinyBackend(os.path.join(HERE, "training", "tiny2.pt"),
                    os.path.join(HERE, "training"))
    print(f"loaded {b.name}: {len(b.layers)} blocks, ctx {b.ctx}")

    fam = familiarity_axis(b)
    ctx = ax.calibrate_context(b)
    slf = ax.calibrate_self(b, SEEDS)
    calib = {"context": ctx, "familiarity": fam, "self": slf,
             "backend": b.name}
    calib["verdict"] = {a["name"]: bool(a["acc"] >= 0.75 and a["p"] < 0.05)
                        for a in (ctx, fam, slf)}
    calib["all_pass"] = bool(all(calib["verdict"].values()))
    exported = ax.export(calib)
    print("axes:", json.dumps({k: {"layer": v["layer"],
                                   "acc": round(v["acc"], 3),
                                   "p": round(v["p"], 4)}
                               for k, v in exported["axes"].items()}, indent=1))
    print("verdict:", calib["verdict"])

    print("audit: 20 real + 20 invented, 3 wordings each ...")
    real = audit_mod.audit(b, REAL, CAPITALS, n_tokens=N_ANSWER,
                           templates=PARAPHRASES, extract=claim_of)
    nonce = audit_mod.audit(b, NONCE, CAPITALS, n_tokens=N_ANSWER,
                            templates=PARAPHRASES, extract=claim_of)
    print(f"  real:  asserted {real['n_asserted']}/{real['n']}, "
          f"flagged {real['n_flagged']}, mean stability "
          f"{real['mean_stability']:.2f}")
    print(f"  nonce: asserted {nonce['n_asserted']}/{nonce['n']}, "
          f"flagged {nonce['n_flagged']}, mean stability "
          f"{nonce['mean_stability']:.2f}")

    # one-pass flag over all 40 questions
    demo = []
    for names, kind in ((REAL, "real"), (NONCE, "nonce")):
        for name in names:
            text = FAM_TEMPLATE.format(X=name)
            H = b.capture(b.encode(text))
            fam_s = float(ax.axis_scores(exported["axes"]["familiarity"], H)[0])
            demo.append({"entity": name, "kind": kind,
                         "score_familiarity": fam_s,
                         "justified": fam_s > 0.0})
    n_real_ok = sum(1 for d in demo if d["kind"] == "real" and d["justified"])
    n_nonce_flag = sum(1 for d in demo if d["kind"] == "nonce"
                       and not d["justified"])
    print(f"  indicator: real justified {n_real_ok}/{len(REAL)}, "
          f"nonce unbacked {n_nonce_flag}/{len(NONCE)}")
    # conservative mode: unbacked if the audit OR the indicator says so
    fam_of = {d["entity"]: d["score_familiarity"] for d in demo}
    union = {"real_flagged": 0, "nonce_flagged": 0}
    for rows, kind in ((real["rows"], "real"), (nonce["rows"], "nonce")):
        for r in rows:
            flag = bool(r["H"] > 0) or bool(fam_of.get(r["entity"], 0.0) <= 0.0)
            union[f"{kind}_flagged"] += int(flag)
    print(f"  conservative (audit OR indicator): real flagged "
          f"{union['real_flagged']}/{len(REAL)}, nonce flagged "
          f"{union['nonce_flagged']}/{len(NONCE)}")

    payload = {"backend": b.name, "axes": exported["axes"],
               "indicator": {"real_justified": n_real_ok,
                             "nonce_unbacked": n_nonce_flag},
               "conservative": union,
               "verdict": calib["verdict"], "all_pass": calib["all_pass"],
               "audit_real": real, "audit_nonce": nonce, "demo": demo}
    out = os.path.join(HERE, "provenance", "results.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    print(f"results: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
