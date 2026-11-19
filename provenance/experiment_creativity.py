"""Does creativity control confabulation? Measured.

TINY's `pick()` (dos/TINY.C): creativity 0 is the argmax; creativity > 0 is a
softmax with temperature c/5 and a threshold that drops letters below 0.15 of
the best. So the switch controls *sampling*, not knowledge.

This reproduces the sampler and measures, per creativity level:

  real capitals   sample accuracy, first-sample accuracy
  nonces          does it confabulate a capital at all? how many *distinct*
                  claims across samples (stability -- the audit's signal)
"""
from __future__ import annotations

import collections
import json
import os
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from provenance.tiny_v2 import TinyV2Backend  # noqa: E402
from provenance.router import is_fallback, prefix_for  # noqa: E402

REAL = (("france", "paris"), ("poland", "warsaw"), ("qatar", "doha"),
        ("peru", "lima"), ("japan", "tokyo"), ("nauru", "yaren"))
NONCE = ("vrandel", "qorvath", "zelmuth", "brixalon", "tavrenko", "oxwald")
LEVELS = (0, 2, 5, 9)
SAMPLES = 5


def pick(logits: np.ndarray, creativity: int, rng: np.random.Generator) -> int:
    best = int(np.argmax(logits))
    if creativity <= 0:
        return best
    t = creativity / 5.0
    z = logits - logits[best]
    p = np.exp(z / t)
    p[p < 0.15] = 0.0
    s = p.sum()
    if s <= 0:
        return best
    r = rng.random() * s
    for i in np.nonzero(p)[0]:
        r -= p[i]
        if r < 0:
            return int(i)
    return best


def generate(b, question: str, creativity: int, rng, n: int = 24) -> str:
    pre = prefix_for(question)
    text = question + "\n" + (pre or "")
    out = []
    with torch.no_grad():
        x = torch.tensor([b.encode(text)])
        while len(out) < n and x.shape[1] < b.ctx:
            logits = b.model(x)[0, -1].float().numpy()
            t = pick(logits, creativity, rng)
            if t <= 1:
                break
            out.append(t)
            x = torch.cat([x, torch.tensor([[t]])], 1)
    return b.decode(out).strip()


def main() -> int:
    b = TinyV2Backend(os.path.join(HERE, "dos", "TINY.BIN"),
                      os.path.join(HERE, "training"))
    rng = np.random.default_rng(42)
    rows = {}
    for c in LEVELS:
        real_right = real_first = 0
        nonce_claims = []
        for name, want in REAL:
            claims = [generate(b, f"what is the capital of {name}", c, rng)
                      for _ in range(SAMPLES)]
            good = [want in x.lower() for x in claims]
            real_right += sum(good)
            real_first += int(good[0])
            nonce_claims.append(("real", name, claims))
        nonce_out = []
        for name in NONCE:
            claims = [generate(b, f"what is the capital of {name}", c, rng)
                      for _ in range(SAMPLES)]
            nonce_out.append(claims)
            nonce_claims.append(("nonce", name, claims))
        # a "confabulated" nonce sample is one that produced a capital word
        def confabulates(t):
            # a nonce answered without a refusal is a confabulation
            return not is_fallback(t) and len(t.strip()) > 1
        cf = sum(confabulates(x) for cl in nonce_out for x in cl)
        cf_total = sum(len(cl) for cl in nonce_out)
        distinct = np.mean([len(set(x.lower() for x in cl)) for cl in nonce_out])
        real_distinct = np.mean([len(set(x.lower() for x in cl))
                                 for k, _, cl in nonce_claims if k == "real"])
        rows[c] = {"real_first_correct": real_first, "real_samples_correct": real_right,
                   "real_samples": len(REAL) * SAMPLES,
                   "nonce_confabulated": cf, "nonce_samples": cf_total,
                   "nonce_distinct_per_entity": float(distinct),
                   "real_distinct_per_entity": float(real_distinct)}
        print(f"creativity {c}:  real first {real_first}/{len(REAL)}  "
              f"samples {real_right}/{len(REAL)*SAMPLES}  |  nonce confabulated "
              f"{cf}/{cf_total}  distinct/entity {distinct:.1f}")
    path = os.path.join(HERE, "provenance", "experiment_creativity.json")
    json.dump(rows, open(path, "w"), indent=1)
    print(f"results: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
