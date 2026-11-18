"""Answer router: repair false refusals without retraining.

The measured failure (provenance/DIAGNOSIS.md): the free decode picks the
fallback branch ("I have never heard of …") for 2 of 194 capitals even though
the model knows the answer (template slot p = 0.997). The fallback and the
ordinary template "It is X." share their first token, so the routing is a
coin flip at the edge.

This module keeps the free decode first and only *repairs* it when the model
actually refused: it retries with the relation's answer prefix, which is in
the training distribution for that relation. A retry can only turn a refusal
into an answer; if the retry also refuses, the first result stands.

    from provenance.router import answer
    answer(backend, "what is the capital of poland")
    # {'text': 'Warsaw.', 'value': 'Warsaw', 'fallback': False,
    #  'repaired': True, 'prefix': 'the capital is '}
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

# Refusals the model was trained to emit for unknown entities.
FALLBACKS = ("i have never heard", "i do not know", "i did not understand",
             "hmm?", "sorry, i do not know")

# Relation -> prefix that puts the model on the answer track. Only relations
# whose prefix was measured to work are listed; everything else stays free.
PREFIXES = (
    ("capital", "the capital is "),
    ("main city", "the capital is "),      # gen2: "what is the main city of X"
    ("government of", "the capital is "),  # gen2: "where is the government of X"
    ("money", "they use "),
    ("currency", "they use "),
    ("language", "they speak "),
    ("continent", "it is in "),
    ("symbol", "it is "),
    ("colour", "it is "),
    ("color", "it is "),
)

FILLERS = ("it is ", "the capital is ", "they speak ", "they use ",
           "the answer is ")


def prefix_for(question: str) -> Optional[str]:
    q = question.lower()
    for key, pre in PREFIXES:
        if key in q:
            return pre
    return None


def is_fallback(text: str) -> bool:
    t = text.strip().lower()
    return any(t.startswith(f) for f in FALLBACKS)


_TPL = re.compile(
    r"^(the capital of .+? is|the capital is|it is|they speak|they use|"
    r"the answer is)\s+", re.I)


def value_of(text: str) -> str:
    """Strip any trained answer template and the final period."""
    t = text.strip()
    m = _TPL.match(t)
    if m:
        t = t[m.end():]
    else:
        low = t.lower()
        for f in FILLERS:
            if low.startswith(f):
                t = t[len(f):]
                break
    return t.strip().rstrip(".").strip()


def _generate(backend: Any, ids, n: int) -> str:
    """Greedy from explicit token ids.

    The backends append a newline to a prompt string; the routed decode needs
    an exact prompt ("question\nthe capital is "), so the router builds the
    ids itself.
    """
    import torch
    out = []
    with torch.no_grad():
        x = torch.tensor([list(ids)])
        while len(out) < n and x.shape[1] < backend.ctx:
            t = int(backend.model(x)[0, -1].argmax(-1))
            if t <= 1:
                break
            out.append(t)
            x = torch.cat([x, torch.tensor([[t]])], 1)
    return backend.decode(out).strip()


def answer(backend: Any, question: str, n: int = 40,
           repair: bool = True) -> Dict[str, Any]:
    """Routed decode first, free decode as the fallback.

    For a question with a known answer template the routed decode is shorter
    and more accurate (it removes the four-way first-token split). If the
    routed decode refuses, the free decode is tried; if that refuses too the
    refusal stands.
    """
    pre = prefix_for(question) if repair else None
    free_text = None
    if pre is not None:
        text = _generate(backend, backend.encode(question + "\n" + pre), n)
        if not is_fallback(text):
            return {"question": question, "text": text,
                    "value": value_of(text), "fallback": False,
                    "repaired": False, "prefix": pre, "via": "routed"}
        free_text = text
    text = _generate(backend, backend.encode(question + "\n"), n)
    out = {"question": question, "text": text, "value": value_of(text),
           "fallback": is_fallback(text), "repaired": False,
           "prefix": pre, "via": "free"}
    if out["fallback"] and pre is not None and free_text is not None:
        out["first_text"] = free_text
    return out
