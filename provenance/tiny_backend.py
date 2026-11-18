"""Read-only backend for TINY 2.1 (char-level QA transformer, 367k params).

The model is the upstream one: 4 blocks, 96 wide, one letter at a time.
Nothing is trained and no weight is touched; this adapter only encodes,
captures hidden states and generates greedily.
"""
from __future__ import annotations

import os
import sys
from typing import List, Sequence, Tuple

import numpy as np

try:
    import torch
except Exception:  # pragma: no cover
    torch = None

_TRAIN2 = None


def _train2(training_dir: str = "training"):
    """Import the upstream training module (defines the model and vocab)."""
    global _TRAIN2
    if _TRAIN2 is None:
        sys.path.insert(0, os.path.abspath(training_dir))
        import train2  # noqa: E402
        _TRAIN2 = train2
    return _TRAIN2


class TinyBackend:
    def __init__(self, ckpt: str = "training/tiny2.pt",
                 training_dir: str = "training"):
        t2 = _train2(training_dir)
        self.t2 = t2
        self.model = t2.load_model(ckpt)
        self.model.eval()
        self.layers = self.model.blocks
        self.name = "tiny-2.1"
        self.ckpt = ckpt
        self.ctx = t2.CTX

    # -- vocabulary --------------------------------------------------------
    def encode(self, text: str) -> List[int]:
        return self.t2.encode(text.lower())

    def decode(self, ids: Sequence[int]) -> str:
        return self.t2.decode(list(ids))

    def first_token(self, text: str) -> int:
        ids = self.encode(text)
        if not ids:
            raise ValueError(f"first_token: {text!r} is empty.")
        return ids[0]

    # -- hidden states -----------------------------------------------------
    def capture(self, ids: Sequence[int]) -> np.ndarray:
        store = {}

        def mk(i):
            def hook(_m, _inp, out):
                store[i] = out[0, -1].detach().float().numpy()
            return hook

        handles = [self.layers[i].register_forward_hook(mk(i))
                   for i in range(len(self.layers))]
        try:
            with torch.no_grad():
                self.model(torch.tensor([list(ids)], dtype=torch.long))
        finally:
            for h in handles:
                h.remove()
        if len(store) != len(self.layers):
            raise RuntimeError("capture: a block hook did not fire.")
        return np.stack([store[i] for i in range(len(self.layers))])

    # -- generation (upstream protocol: question + newline, stop at newline)
    def generate(self, prompt: str, n_tokens: int = 40
                 ) -> Tuple[List[int], str]:
        ids = self.encode(prompt + "\n")
        out: List[int] = []
        with torch.no_grad():
            x = torch.tensor([ids], dtype=torch.long)
            while len(out) < n_tokens and x.shape[1] < self.ctx:
                nxt = int(self.model(x)[0, -1].argmax(-1))
                if nxt <= 1:
                    break
                out.append(nxt)
                x = torch.cat([x, torch.tensor([[nxt]])], 1)
        return out, self.decode(out)

    def top_prob(self, ids: Sequence[int]) -> float:
        with torch.no_grad():
            logits = self.model(torch.tensor([list(ids)], dtype=torch.long))
        return float(torch.softmax(logits[0, -1], -1).max())
