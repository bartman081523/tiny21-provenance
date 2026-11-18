#!/usr/bin/env python3
"""Compare the answers of the DOS build with the float checkpoint audit.

    PYTHONPATH=/path/to/provenance-audit python compare.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
sys.path.insert(0, os.environ.get("PROVENANCE_AUDIT", os.path.join(
    os.path.dirname(REPO), "provenance-audit")))

from provenance.run_tiny import claim_of  # noqa: E402

answers = [l.strip() for l in open(os.path.join(HERE, "dos_answers.txt"),
                                   encoding="utf-8") if l.strip()]
res = json.load(open(os.path.join(REPO, "provenance", "results.json"),
                     encoding="utf-8"))
rows = res["audit_real"]["rows"] + res["audit_nonce"]["rows"]
kinds = ["real"] * 20 + ["nonce"] * 20

agree = 0
per_kind = {"real": [0, 0], "nonce": [0, 0]}     # [agree, total]
print(f"{'entity':10} {'kind':6} {'float':12} {'dos':12} {'':4} | dos answer")
for r, k, a in zip(rows, kinds, answers):
    d = claim_of(a)
    ok = d == r["claim"]
    agree += ok
    per_kind[k][0] += ok
    per_kind[k][1] += 1
    print(f"{r['entity']:10} {k:6} {str(r['claim']):12} {str(d):12} "
          f"{'ok' if ok else 'DIFF':4} | {a[:56]}")

print()
print(f"agreement overall {agree}/{len(rows)}")
for k, (a, t) in per_kind.items():
    print(f"  {k:6} {a}/{t}")
asserted = sum(1 for a, k in zip(answers, kinds) if k == "nonce" and claim_of(a))
print(f"  nonce asserted in DOS {asserted}/20")
