"""Tiny v2: canonical answer format + distinct fallback, long low-LR finetune.

Keeps the shipped weights as the start (the facts are already memorised) and
finetunes the *distribution*: every table relation answers with the bare
value, the fallback starts with a distinct token. Low learning rate so the
memorised facts do not drift away.

    python3 train_v2.py 20 v2.pt
"""
import sys

import gen2

# 1. one canonical answer format per relation (only where '{a}.' is legal)
gen2.REL_T = {k: (q, ['{a}.'] if '{a}.' in a else a)
              for k, (q, a) in gen2.REL_T.items()}

# 2. the fallback must not share its first token with an answer template
def g_unknown_v2(rng, test):
    q, a, k = gen2.g_unknown(rng, test)
    if k == 'unknown' and a.lower().startswith(('i have', 'i do not')):
        a = 'Sorry, ' + a[0].lower() + a[1:]
    return q, a, k

for i, g in enumerate(gen2.GENS):
    if g[0] == 'unknown':
        gen2.GENS[i] = ('unknown', g_unknown_v2, g[2])

import train2

if __name__ == '__main__':
    minutes = float(sys.argv[1])
    out = sys.argv[2]
    # low, heavily-decaying learning rate: adopt the format, keep the facts
    m = train2.train(minutes, out, resume='tiny2.pt', peak=2e-4,
                     decay_frac=0.5, eval_every=0)
    print('saved', out)
