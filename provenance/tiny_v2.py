"""TNY2 weight file (the shipped TINY.BIN) as a PyTorch model.

`train2.load_old_bin` reads the version-1 format (no header, fixed sizes) and
cannot open the shipped file. The layout below is the inverse of
`train2.export`: header 'TNY2' + D,L,H,HID as int16, then one scale per row
followed by int8 values, and float32 gains per norm.
"""
from __future__ import annotations

import struct
import sys
from typing import Tuple

import numpy as np
import torch


def load_v2(path: str, train2) -> Tuple[torch.nn.Module, Tuple[int, int, int, int]]:
    b = open(path, "rb").read()
    if b[:4] != b"TNY2":
        raise ValueError(f"{path}: not a TNY2 file")
    D, L, H, HID = struct.unpack_from("<4h", b, 4)
    off = [12]

    def table(rows: int, cols: int) -> torch.Tensor:
        out = np.empty((rows, cols), np.float32)
        for r in range(rows):
            s = struct.unpack_from("<f", b, off[0])[0]
            w = np.frombuffer(b, np.int8, cols, off[0] + 4).astype(np.float32)
            out[r] = w * s
            off[0] += 4 + cols
        return torch.tensor(out)

    def gains() -> torch.Tensor:
        g = np.frombuffer(b, "<f4", D, off[0]).copy()
        off[0] += 4 * D
        return torch.tensor(g)

    m = train2.Model(train2.Cfg(D, L, H, HID))
    with torch.no_grad():
        m.emb.weight.copy_(table(train2.VOCAB, D))
        m.pos.weight.copy_(table(train2.CTX, D))
        for blk in m.blocks:
            blk.n1.g.copy_(gains())
            for lin in (blk.q, blk.k, blk.v, blk.o):
                lin.weight.copy_(table(D, D))
            blk.n2.g.copy_(gains())
            blk.f1.weight.copy_(table(HID, D))
            blk.f2.weight.copy_(table(D, HID))
        m.nf.g.copy_(gains())
    if off[0] != len(b):
        raise ValueError(f"{path}: {len(b) - off[0]} bytes left over")
    return m, (D, L, H, HID)


class TinyV2Backend:
    """Same adapter contract as provenance.tiny_backend.TinyBackend, but on
    the shipped, quantised weights."""

    def __init__(self, ckpt: str = "dos/TINY.BIN",
                 training_dir: str = "training"):
        sys.path.insert(0, training_dir)
        import train2
        self.t2 = train2
        self.model, dims = load_v2(ckpt, train2)
        self.model.eval()
        self.layers = self.model.blocks
        self.name = "tiny-2.1 quantised"
        self.ckpt = ckpt
        self.ctx = train2.CTX
        self.dims = dims

    def encode(self, text):  # noqa: D102 - adapter contract
        return self.t2.encode(text.lower())

    def decode(self, ids):
        return self.t2.decode(list(ids))

    def first_token(self, text):
        ids = self.encode(text)
        if not ids:
            raise ValueError(f"first_token: {text!r} is empty.")
        return ids[0]

    def capture(self, ids):
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
        return np.stack([store[i] for i in range(len(self.layers))])

    def generate(self, prompt, n_tokens=40):
        ids = self.encode(prompt + "\n")
        out = []
        with torch.no_grad():
            x = torch.tensor([ids], dtype=torch.long)
            while len(out) < n_tokens and x.shape[1] < self.ctx:
                nxt = int(self.model(x)[0, -1].argmax(-1))
                if nxt <= 1:
                    break
                out.append(nxt)
                x = torch.cat([x, torch.tensor([[nxt]])], 1)
        return out, self.decode(out)

    def top_prob(self, ids):
        with torch.no_grad():
            logits = self.model(torch.tensor([list(ids)], dtype=torch.long))
        return float(torch.softmax(logits[0, -1], -1).max())
