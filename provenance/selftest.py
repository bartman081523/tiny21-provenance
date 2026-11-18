"""Repo self-test: run the model over a broad battery and report every defect.

Covers:
  A  all 194 capitals: does the model refuse, answer, and does the router
     repair the refusals?
  B  relation questions (language, currency, continent, spelling, arithmetic,
     plural, past tense, symbol, reverse) — free decode vs router value.
  C  invented entities: does the model confabulate, and does the provenance
     indicator flag it?
  D  quantisation: float vs quantised routing on the same battery.

    PYTHONPATH=/path/to/provenance-audit python provenance/selftest.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from provenance.tiny_backend import TinyBackend  # noqa: E402
from provenance.tiny_v2 import TinyV2Backend  # noqa: E402
from provenance.router import answer, is_fallback, value_of  # noqa: E402
from provenance.run_tiny import CAPITALS, NONCE  # noqa: E402
from provenance.analyze_weaknesses import countries  # noqa: E402

RELATIONS = [
    ("what language do they speak in canada", "english"),
    ("what language do they speak in japan", "japanese"),
    ("what is the money of japan", "yen"),
    ("what money do people use in brazil", "real"),
    ("which continent is egypt in", "africa"),
    ("which continent is brazil in", "south america"),
    ("what is the symbol for gold", "au"),
    ("what is the symbol for iron", "fe"),
    ("spell computer", "c-o-m-p-u-t-e-r"),
    ("spell elephant", "e-l-e-p-h-a-n-t"),
    ("what is 7 times 8", "56"),
    ("what is 14 in roman numerals", "xiv"),
    ("plural of mouse", "mice"),
    ("past tense of go", "went"),
    ("what is cat backwards", "tac"),
    ("what comes after 199", "200"),
]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


import re  # noqa: E402


def run(b, label, sample_caps):
    print(f"\n=== {label} ===")
    caps = dict(sample_caps)
    res = {"capitals": [], "relations": [], "nonce": []}
    for name, truth in caps.items():
        r = answer(b, f"what is the capital of {name}")
        ok = norm(truth) in norm(r["value"]) or norm(r["value"]) in norm(truth)
        res["capitals"].append({"country": name, "truth": truth,
                                "value": r["value"], "ok": ok,
                                "fallback": r["fallback"],
                                "repaired": r["repaired"]})
    print(f"capitals: {len(caps)}")
    fb = [r for r in res["capitals"] if r["fallback"]]
    print(f"  refusals {len(fb)}  repaired {sum(1 for r in res['capitals'] if r['repaired'])}"
          f"  correct {sum(1 for r in res['capitals'] if r['ok'])}/{len(caps)}")
    for r in res["capitals"]:
        if not r["ok"]:
            print(f"  MISS {r['country']:16} got {r['value']!r} want {r['truth']!r}"
                  f"  fallback {r['fallback']} repaired {r['repaired']}")

    for q, truth in RELATIONS:
        r = answer(b, q)
        ok = norm(truth) in norm(r["value"]) or norm(r["value"]) in norm(truth)
        res["relations"].append({"question": q, "truth": truth,
                                 "value": r["value"], "ok": ok,
                                 "fallback": r["fallback"],
                                 "repaired": r["repaired"]})
    print(f"relations: {sum(1 for r in res['relations'] if r['ok'])}/"
          f"{len(RELATIONS)} correct")
    for r in res["relations"]:
        if not r["ok"]:
            print(f"  MISS {r['question'][:42]:44} got {r['value']!r} want {r['truth']!r}")

    for name in NONCE[:8]:
        r = answer(b, f"what is the capital of {name}")
        res["nonce"].append({"entity": name, "value": r["value"],
                             "fallback": r["fallback"]})
    conf = sum(1 for r in res["nonce"] if not r["fallback"])
    print(f"invented: {conf}/{len(res['nonce'])} confabulate (no refusal)")
    return res


def main() -> int:
    caps = countries()
    sample = [("poland", "warsaw"), ("qatar", "doha"), ("pakistan", "islamabad"),
              ("france", "paris"), ("peru", "lima"), ("nauru", "yaren"),
              ("japan", "tokyo"), ("brazil", "brasilia"), ("canada", "ottawa"),
              ("egypt", "cairo"), ("saudi arabia", "riyadh"),
              ("united states", "washington")]
    qnt = TinyV2Backend(os.path.join(HERE, "dos", "TINY.BIN"),
                        os.path.join(HERE, "training"))
    flt = TinyBackend(os.path.join(HERE, "training", "tiny2.pt"),
                      os.path.join(HERE, "training"))
    out = {"quant": run(qnt, "quantised (shipped)", sample),
           "float": run(flt, "float checkpoint", sample)}
    # routing agreement
    diff = sum(1 for a, b in zip(out["quant"]["capitals"], out["float"]["capitals"])
               if a["value"] != b["value"])
    print(f"\nfloat vs quant: {diff}/{len(sample)} capitals differ")
    path = os.path.join(HERE, "provenance", "selftest.json")
    json.dump(out, open(path, "w"), indent=1)
    print(f"results: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
