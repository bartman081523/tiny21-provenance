"""Architecture weaknesses of TINY 2.1 — measured in pure PyTorch.

Three questions:

1. Why does Poland fall into the "I have never heard of ..." fallback while
   the template slot says "Warsaw" with p = 0.997?
2. Which other facts are at the same edge?
3. What does the model represent for those names (familiarity ensemble)?

Everything is one forward per entity; no emulator, no generation loops.
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

from provenance.tiny_v2 import TinyV2Backend  # noqa: E402
from provenance.run_tiny import REAL, NONCE  # noqa: E402
from provenance_audit.core import paired_direction  # noqa: E402

TEMPLATE = "what is the capital of {X}\nthe capital is "
FREE = "what is the capital of {X}\n"


def countries():
    rows = []
    path = os.path.join(HERE, "training", "facts", "geo.tsv")
    for line in open(path, encoding="utf-8", errors="replace"):
        p = line.rstrip("\n").split("\t")
        if len(p) == 3 and p[0] == "capital":
            rows.append((p[1].lower(), p[2].lower()))
    return rows


def main() -> int:
    b = TinyV2Backend(os.path.join(HERE, "dos", "TINY.BIN"),
                      os.path.join(HERE, "training"))
    rows = countries()
    print(f"{len(rows)} countries")

    # familiarity ensemble fitted exactly as the DOS panel does it
    def state(name):
        return b.capture(b.encode(TEMPLATE.format(X=name)))
    HK = np.stack([state(x) for x in REAL])
    HN = np.stack([state(x) for x in NONCE])
    L = HK.shape[1]
    dirs, means, stds = [], [], []
    zk = np.zeros(len(HK)); zn = np.zeros(len(HN))
    for l in range(L):
        d = paired_direction(HK[:, l], HN[:, l])
        vk, vn = HK[:, l] @ d, HN[:, l] @ d
        mu, sd = float(vk.mean()), float(vk.std() + 1e-9)
        dirs.append(d); means.append(mu); stds.append(sd)
        zk += (vk - mu) / sd; zn += (vn - mu) / sd
    zk /= L; zn /= L
    thr = 0.5 * (float(zk.mean()) + float(zn.mean()))

    out = []
    for name, cap in rows:
        H = state(name)
        z = 0.0
        for l in range(L):
            z += (float(H[l] @ dirs[l]) - means[l]) / stds[l]
        z = z / L - thr
        ids = b.encode(FREE.format(X=name))
        with torch.no_grad():
            lg = b.model(torch.tensor([ids]))[0, -1].float()
        p = torch.softmax(lg, -1).numpy()
        first_true = ord(cap[0].upper()) - 30
        p_i = float(p[ord("I") - 30])
        p_t = float(p[ord("T") - 30])
        out.append({"country": name, "capital": cap, "z": float(z),
                    "p_fallback": p_i, "p_template": p_t,
                    "p_answer": float(p[first_true]),
                    "argmax": b.decode([int(np.argmax(p))]).strip()})

    zs = np.array([r["z"] for r in out])
    pf = np.array([r["p_fallback"] for r in out])
    pa = np.array([r["p_answer"] for r in out])
    print(f"\nfamiliarity z:  min {zs.min():+.2f}  median {np.median(zs):+.2f}  "
          f"max {zs.max():+.2f}")
    print(f"fallback mass:  min {pf.min():.3f}  median {np.median(pf):.3f}  "
          f"max {pf.max():.3f}")
    print(f"corr(z, p_fallback) = {np.corrcoef(zs, pf)[0,1]:+.3f}")
    print(f"corr(z, p_answer)   = {np.corrcoef(zs, pa)[0,1]:+.3f}")

    print("\n15 lowest familiarity (nonce-like names?):")
    for r in sorted(out, key=lambda r: r["z"])[:15]:
        print(f"  {r['country']:16} z {r['z']:+.2f}  fallback {r['p_fallback']:.2f}  "
              f"answer {r['p_answer']:.2f}  argmax {r['argmax']!r}")

    print("\n15 weakest answer starts (the fallback wins easily):")
    for r in sorted(out, key=lambda r: r["p_answer"])[:15]:
        print(f"  {r['country']:16} answer {r['p_answer']:.2f}  fallback "
              f"{r['p_fallback']:.2f}  z {r['z']:+.2f}  argmax {r['argmax']!r}")

    # where does Poland sit?
    pol = next(r for r in out if r["country"] == "poland")
    rank = sorted(out, key=lambda r: r["z"]).index(pol) + 1
    print(f"\nPoland: z {pol['z']:+.2f} (rank {rank}/{len(out)}), "
          f"fallback {pol['p_fallback']:.2f}, answer {pol['p_answer']:.2f}, "
          f"argmax {pol['argmax']!r}")

    # what happens after the 'I' the model picks?
    ids = b.encode(FREE.format(X="poland")) + [ord("I") - 30]
    with torch.no_grad():
        lg = b.model(torch.tensor([ids]))[0, -1].float()
    p = torch.softmax(lg, -1).numpy()
    top = torch.topk(torch.tensor(p), 4)
    print("after 'I' for poland:",
          [(b.decode([int(i)]), round(float(v), 3)) for v, i in zip(top.values, top.indices)])

    # suffix groups
    groups = {"-land": [], "other": []}
    for r in out:
        groups["-land" if r["country"].endswith("land") else "other"].append(r)
    print("\nsuffix groups:")
    for g, rs in groups.items():
        print(f"  {g:6} n {len(rs):3}  z {np.mean([r['z'] for r in rs]):+.2f}  "
              f"fallback {np.mean([r['p_fallback'] for r in rs]):.3f}  "
              f"answer {np.mean([r['p_answer'] for r in rs]):.3f}")

    dst = os.path.join(HERE, "provenance", "analyze_weaknesses.json")
    json.dump({"rows": out, "thr": thr}, open(dst, "w"), indent=1)
    print(f"\nresults: {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
