"""Precision experiment: what does the familiarity axis actually measure?

Three groups, identical question template:

    K  known       20 real countries whose capitals the model answers
                   correctly and stably (measured earlier)
    R  real, unknown  20 real countries with famous names but obscure facts
                   (Nauru, Tuvalu, Palau, ...) -- real words, likely no fact
    N  nonce       20 invented names (no training support by construction)

If the axis is lexical, K and R score the same and both beat N. If it tracks
fact coverage, R falls towards N.

Also: layer sweep (which layer carries it), an ensemble, and a margin
calibration (accuracy as a function of |score|) so the dead zone can be set
from data instead of a guess.

    PYTHONPATH=/path/to/provenance-audit python provenance/experiment_precision.py
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
from provenance.run_tiny import REAL, NONCE, CAPITALS, PARAPHRASES, N_ANSWER, claim_of  # noqa: E402
from provenance_audit import audit as audit_mod  # noqa: E402

# real countries with famous names and obscure capitals (all in the fact file,
# so "unknown" is the model's weakness, not missing data)
OBSCURE = (
    ("nauru", "yaren"), ("tuvalu", "funafuti"), ("palau", "ngerulmud"),
    ("kiribati", "south tarawa"), ("comoros", "moroni"),
    ("vanuatu", "port vila"), ("lesotho", "maseru"), ("bhutan", "thimphu"),
    ("maldives", "male"), ("seychelles", "victoria"), ("barbados", "bridgetown"),
    ("grenada", "st georges"), ("dominica", "roseau"), ("saint lucia", "castries"),
    ("belize", "belmopan"), ("suriname", "paramaribo"), ("guyana", "georgetown"),
    ("sao tome and principe", "sao tome"), ("eswatini", "lobamba"),
    ("antigua and barbuda", "saint johns"),
)
FAM = "what is the capital of {X}"


def fam_scores(b: TinyV2Backend, names):
    """(n, layers) matrix of scores on the fitted direction (per layer)."""
    H = np.stack([b.capture(b.encode(FAM.format(X=x))) for x in names])
    return H


def fit_scores(Hf, Hn, layer):
    from provenance_audit.core import paired_direction, midpoint_threshold
    d = paired_direction(Hf[:, layer], Hn[:, layer])
    thr = midpoint_threshold(Hf[:, layer], Hn[:, layer], d)
    return d, thr


def main() -> int:
    b = TinyV2Backend(os.path.join(HERE, "dos", "TINY.BIN"),
                      os.path.join(HERE, "training"))
    prev = json.load(open(os.path.join(HERE, "provenance", "results.json"),
                          encoding="utf-8"))
    k_audit = {r["entity"]: r for r in prev["audit_real"]["rows"]}
    n_audit = {r["entity"]: r for r in prev["audit_nonce"]["rows"]}

    print("capturing hidden states (60 entities x 4 layers) ...")
    HK = fam_scores(b, REAL)
    HR = fam_scores(b, [x[0] for x in OBSCURE])
    HN = fam_scores(b, NONCE)

    print("auditing the 20 obscure real countries (3 wordings each) ...")
    r_rows = []
    for name, true_cap in OBSCURE:
        r = audit_mod.audit_entity(b, name, CAPITALS, n_tokens=N_ANSWER,
                                   templates=PARAPHRASES, extract=claim_of)
        r["truth"] = true_cap
        r["correct"] = bool(r["claim"] and r["claim"].replace(" ", "")
                            == true_cap.replace(" ", ""))
        r_rows.append(r)

    # labels: "backed by training" = answered correctly (real groups) / False (nonce)
    labels = {}
    for name in REAL:
        labels[name] = bool(k_audit[name].get("claim") and
                            k_audit[name]["stability"] >= 2 / 3)
    for r in r_rows:
        labels[r["entity"]] = bool(r["correct"] and r["stability"] >= 2 / 3)
    for name in NONCE:
        labels[name] = False

    print("\n=== audit by group ===")
    for gname, rows in (("K known", [k_audit[x] for x in REAL]),
                        ("R obscure", r_rows),
                        ("N nonce", [n_audit[x] for x in NONCE])):
        asserted = sum(1 for r in rows if r.get("claim"))
        stable = sum(1 for r in rows if r.get("stability", 0) >= 2 / 3)
        correct = sum(1 for r in rows if r.get("correct") or
                      (gname.startswith("K") and labels.get(r.get("entity", ""), False)))
        print(f"  {gname:10} asserted {asserted:2}/20  stable {stable:2}/20  "
              f"correct {correct:2}/20  mean stab "
              f"{np.mean([r.get('stability', 0) for r in rows]):.2f}")

    print("\n=== layer sweep (LOO accuracy) ===")
    best = None
    sweep = {}
    for l in range(HK.shape[1]):
        # LOO per layer for the three contrasts
        def acc(a, b_):
            from provenance_audit.core import loo_axis as la
            return la(a[:, l:l + 1, :], b_[:, l:l + 1, :], n_perm=0)["acc"]
        k_n = acc(HK, HN)
        r_n = acc(HR, HN)
        k_r = acc(HK, HR)
        sweep[l] = {"K_vs_N": k_n, "R_vs_N": r_n, "K_vs_R": k_r}
        print(f"  layer {l}:  K vs N {k_n:.3f}   R vs N {r_n:.3f}   "
              f"K vs R {k_r:.3f}")
        if best is None or k_r < best[1]:
            best = (l, k_r)

    # ensemble: standardise each layer's projection by the K group, average
    from provenance_audit.core import paired_direction, midpoint_threshold
    def zscores(H):
        Z = np.zeros((len(H), H.shape[1]))
        for l in range(H.shape[1]):
            d = paired_direction(HK[:, l], HN[:, l])
            v = H[:, l] @ d
            Z[:, l] = (v - (HK[:, l] @ d).mean()) / ((HK[:, l] @ d).std() + 1e-9)
        return Z.mean(axis=1)
    ek, en, er = zscores(HK), zscores(HN), zscores(HR)
    thr_e = 0.5 * (ek.mean() + en.mean())
    acc_e = (sum(1 for v in ek if v > thr_e) + sum(1 for v in en if v <= thr_e)) / 40
    print(f"\n  ensemble (mean z over 4 layers): K vs N {acc_e:.3f}   "
          f"mean z  K {ek.mean():+.2f}  R {er.mean():+.2f}  N {en.mean():+.2f}")

    print("\n=== margin calibration (|score| vs correctness) ===")
    l0 = 0
    d0, thr0 = fit_scores(HK, HN, l0)
    rows = []
    for name, H in ((x, HK[i]) for i, x in enumerate(REAL)):
        rows.append((abs(float(H[l0] @ d0) - thr0), labels[name]))
    for r in r_rows:
        i = [x[0] for x in OBSCURE].index(r["entity"])
        rows.append((abs(float(HR[i][l0] @ d0) - thr0), labels[r["entity"]]))
    for i, name in enumerate(NONCE):
        rows.append((abs(float(HN[i][l0] @ d0) - thr0), False))
    rows.sort()
    bins = [(0, 1), (1, 2), (2, 4), (4, 8), (8, 1e9)]
    print(f"  {'|score|':>12} {'n':>4} {'backed':>7} {'rate':>6}")
    for lo, hi in bins:
        sel = [b_ for s, b_ in rows if lo <= s < hi]
        if sel:
            print(f"  {f'{lo:g}-{hi:g}':>12} {len(sel):>4} {sum(sel):>7} "
                  f"{sum(sel)/len(sel):>6.2f}")

    payload = {"sweep": sweep, "obscure": r_rows,
               "labels": labels,
               "group_means": {
                   "K": HK.mean(axis=(0, 2)).tolist(),
                   "R": HR.mean(axis=(0, 2)).tolist(),
                   "N": HN.mean(axis=(0, 2)).tolist()},
               "margin_bins": [[lo, hi, sum(1 for s, _ in rows if lo <= s < hi),
                                sum(b_ for s, b_ in rows if lo <= s < hi)]
                               for lo, hi in bins]}
    out = os.path.join(HERE, "provenance", "experiment_precision.json")
    json.dump(payload, open(out, "w"), indent=1)
    print(f"\nresults: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
