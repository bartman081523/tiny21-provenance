"""Fact-axis experiment: does the answer distribution know what the name does not?

The familiarity axis separates invented names from real ones (0.95 ensemble)
but only weakly famous from obscure real ones (K vs R 0.63-0.68). This asks
whether a *second*, cheap signal from the same forward separates them:

    p_top      probability of the first answer letter at the slot
    entropy    entropy of that distribution
    p_truth    probability of the true capital's first letter (K/R only)

If none of them separates known from obscure, the honest statement is: this
model has no single-pass "do I know this fact" readout -- its confidence is
the same for a memorised capital and for a confabulation.

    PYTHONPATH=/path/to/provenance-audit python provenance/experiment_fact_axis.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from provenance.tiny_v2 import TinyV2Backend  # noqa: E402
from provenance.run_tiny import REAL, NONCE  # noqa: E402
from provenance.experiment_precision import OBSCURE  # noqa: E402

SLOT = "what is the capital of {X}\nthe capital is "


def features(b, name, truth=None):
    import torch
    ids = b.encode(SLOT.format(X=name))
    with torch.no_grad():
        logits = b.model(torch.tensor([ids]))[0, -1].float()
    p = torch.softmax(logits, -1).numpy()
    p_top = float(p.max())
    ent = float(-(p * np.log(p + 1e-30)).sum())
    p_truth = None
    if truth:
        tid = ord(truth[0].upper()) - 30  # char vocab: id = ord - 30 (backend lowercases)
        p_truth = float(p[tid])
    return {"p_top": p_top, "entropy": ent, "p_truth": p_truth}


def auroc(y, s):
    y = np.asarray(y, int); s = np.asarray(s, float)
    pos, neg = s[y == 1], s[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt) / (len(pos) * len(neg))


def main() -> int:
    b = TinyV2Backend(os.path.join(HERE, "dos", "TINY.BIN"),
                      os.path.join(HERE, "training"))
    # true capitals for the known group come from the fact table
    truth = {}
    for line in open(os.path.join(HERE, "training", "facts", "geo.tsv"),
                     encoding="utf-8", errors="replace"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) == 3 and parts[0] == "capital":
            truth[parts[1].lower()] = parts[2].lower()
    groups = {
        "K": [(x, truth.get(x.lower())) for x in REAL],
        "R": [(x, t) for x, t in OBSCURE],
        "N": [(x, None) for x in NONCE],
    }
    rows = {}
    for g, items in groups.items():
        rows[g] = [dict(entity=x, truth=t, **features(b, x, t)) for x, t in items]

    print(f"{'group':>6} {'p_top mean':>11} {'entropy':>8} {'p_truth':>8}")
    for g in ("K", "R", "N"):
        pt = np.mean([r["p_top"] for r in rows[g]])
        en = np.mean([r["entropy"] for r in rows[g]])
        pv = [r["p_truth"] for r in rows[g] if r["p_truth"] is not None]
        print(f"{g:>6} {pt:>11.3f} {en:>8.3f} "
              f"{(np.mean(pv) if pv else float('nan')):>8.3f}")

    def contrast(a, b_, key):
        y = [1] * len(rows[a]) + [0] * len(rows[b_])
        s = [r[key] for r in rows[a]] + [r[key] for r in rows[b_]]
        return auroc(y, s)

    print("\nAUROC (1.0 = perfect separation)")
    for key in ("p_top", "entropy"):
        print(f"  {key:8} K vs N {contrast('K','N',key):.3f}   "
              f"R vs N {contrast('R','N',key):.3f}   "
              f"K vs R {contrast('K','R',key):.3f}")
    print(f"  p_truth  K vs R {contrast('K','R','p_truth'):.3f}")

    out = os.path.join(HERE, "provenance", "experiment_fact_axis.json")
    json.dump({"rows": rows, "slot": SLOT}, open(out, "w"), indent=1)
    print(f"\nresults: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
