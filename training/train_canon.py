"""Finetune TINY 2.1 on a canonical answer format.

The measured architecture weakness (provenance/DIAGNOSIS.md): three answer
templates plus the fallback compete at the first answer token, and the
fallback shares "I" with "It is …", so 2 of 194 capitals are refused.

This script keeps the weights but changes the *distribution*: every table
relation answers with the bare value ("{a}.") and the fallback starts with a
distinct token ("Sorry, …"). No change to the model or the trainer.

    python3 train_canon.py 8 canon.pt
"""
import sys

import gen2

# 1. one canonical answer format for every table relation
gen2.REL_T = {k: (q, ['{a}.'] if '{a}.' in a else a)
              for k, (q, a) in gen2.REL_T.items()}

# 2. the fallback must not share its first token with an answer template
def g_unknown_canon(rng, test):
    q, a, k = gen2.g_unknown(rng, test)
    if k == 'unknown' and a.lower().startswith(('i have', 'i do not')):
        a = 'Sorry, ' + a[0].lower() + a[1:]
    return q, a, k

for i, g in enumerate(gen2.GENS):
    if g[0] == 'unknown':
        gen2.GENS[i] = ('unknown', g_unknown_canon, g[2])

import train2  # imports the (now patched) gen2

if __name__ == '__main__':
    minutes = float(sys.argv[1])
    out = sys.argv[2]
    m = train2.train(minutes, out, resume='tiny2.pt', peak=5e-4,
                     decay_frac=0.3, eval_every=0)
    print('saved', out)
