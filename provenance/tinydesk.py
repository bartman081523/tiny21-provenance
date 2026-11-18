"""TINY 2.1 desk: the DOS interface with the provenance panel.

Runs the released checkpoint in PyTorch and shows, next to the neural
monitor, what the DOS build cannot show yet:

    CONTEXT      is there evidence in the prompt?
    FAMILIARITY  is the entity in the training data?
    SELF         is the preceding text the model's own?

The verdict is the same one the audit uses: justified = context or
familiarity, otherwise UNBACKED.

    python tinydesk.py                       # interactive
    python tinydesk.py --demo "vrandel"      # asks one question, shows it
    python tinydesk.py --shot out.png --demo "vrandel"
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import numpy as np  # noqa: E402

from provenance.tiny_backend import TinyBackend  # noqa: E402

BG = "#06121a"
PANEL = "#0a2630"
FRAME = "#1f8fa8"
CYAN = "#33e0ff"
MINT = "#6dffb0"
AMBER = "#ffce5a"
RED = "#ff5a5a"
DIM = "#4a7a86"
TEXT = "#cfeef5"

# display scales only (the axes are unbounded dot products, not probabilities)
SCALE = {"context": 20.0, "familiarity": 10.0, "self": 2500.0}


class Desk:
    def __init__(self, root: tk.Tk, backend: TinyBackend, calib: dict):
        self.root = root
        self.b = backend
        self.axes = calib["axes"]
        self.active = calib.get("verdict") or {k: True for k in self.axes}
        root.title("TINY 2.1 — provenance desk")
        root.configure(bg=BG)
        root.geometry("980x560")

        self.chat = tk.Text(root, bg=BG, fg=TEXT, font=("Courier", 13),
                            bd=0, highlightthickness=1,
                            highlightbackground=FRAME, wrap="word",
                            state="disabled", padx=10, pady=8)
        self.chat.place(x=8, y=8, width=620, height=470)

        self.panel = tk.Frame(root, bg=PANEL, highlightthickness=1,
                              highlightbackground=FRAME)
        self.panel.place(x=636, y=8, width=336, height=470)

        self.entry = tk.Entry(root, bg="#0b1c24", fg=AMBER,
                              insertbackground=AMBER, font=("Courier", 13),
                              bd=0, highlightthickness=1,
                              highlightbackground=FRAME)
        self.entry.place(x=8, y=494, width=964, height=34)
        self.entry.bind("<Return>", self.ask)
        self.entry.focus_set()

        self.status = tk.Label(root, text="", bg=BG, fg=DIM,
                               font=("Courier", 10), anchor="w")
        self.status.place(x=8, y=532, width=964, height=18)

        self._panel_widgets()
        self._say("TINY 2.1 — 4 layers, 96 wide, %d blocks.\n"
                  "Ask about countries, animals, sums, words. "
                  "The right panel is the provenance monitor.\n\n"
                  % len(backend.layers))

    # -- panel ------------------------------------------------------------
    def _panel_widgets(self):
        def label(y, text, colour=DIM, size=10):
            tk.Label(self.panel, text=text, bg=PANEL, fg=colour,
                     font=("Courier", size, "bold"), anchor="w").place(
                x=12, y=y, width=310)

        label(10, "NEURAL MONITOR", DIM)
        label(34, "LAYER ACTIVITY", DIM)
        self.layer_bars = []
        for i in range(4):
            tk.Label(self.panel, text="L%d" % (i + 1), bg=PANEL, fg=CYAN,
                     font=("Courier", 10)).place(x=12, y=56 + i * 20)
            c = tk.Canvas(self.panel, height=10, bg="#031017",
                          highlightthickness=0)
            c.place(x=42, y=58 + i * 20, width=270, height=10)
            self.layer_bars.append(c)

        label(148, "CONFIDENCE", DIM)
        self.conf = tk.Canvas(self.panel, height=12, bg="#031017",
                              highlightthickness=0)
        self.conf.place(x=12, y=164, width=300, height=12)
        self.conf_txt = tk.Label(self.panel, text="", bg=PANEL, fg=MINT,
                                 font=("Courier", 10), anchor="e")
        self.conf_txt.place(x=220, y=146, width=92)

        label(196, "PROVENANCE", AMBER)
        self.prov_rows = {}
        for i, key in enumerate(("context", "familiarity", "self")):
            y = 216 + i * 22
            tk.Label(self.panel, text=key.upper()[:11], bg=PANEL, fg=DIM,
                     font=("Courier", 9)).place(x=12, y=y, width=76)
            c = tk.Canvas(self.panel, height=9, bg="#031017",
                          highlightthickness=0)
            c.place(x=90, y=y + 4, width=176, height=9)
            v = tk.Label(self.panel, text="", bg=PANEL, fg=TEXT,
                         font=("Courier", 9), anchor="e")
            v.place(x=268, y=y, width=56)
            self.prov_rows[key] = (c, v)

        self.verdict = tk.Label(self.panel, text="—", bg=PANEL, fg=TEXT,
                                font=("Courier", 15, "bold"))
        self.verdict.place(x=12, y=286, width=312, height=28)
        self.reason = tk.Label(self.panel, text="", bg=PANEL, fg=DIM,
                               font=("Courier", 9), anchor="w")
        self.reason.place(x=12, y=316, width=312, height=16)

        label(348, "HOW TO READ", DIM)
        tk.Label(self.panel, text="familiar = the entity is in training\n"
                                  "context  = the evidence is in the prompt\n"
                                  "otherwise the answer is UNBACKED",
                 bg=PANEL, fg=DIM, font=("Courier", 9), justify="left",
                 anchor="nw").place(x=12, y=368, width=312, height=64)

    # -- helpers ----------------------------------------------------------
    def _say(self, text, colour=TEXT):
        self.chat.configure(state="normal")
        self.chat.insert("end", text)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _bar(self, canvas, frac, width, colour):
        canvas.delete("all")
        frac = max(0.0, min(1.0, frac))
        canvas.create_rectangle(0, 0, width * frac, 12, fill=colour,
                                width=0)

    def _axis(self, key, H):
        a = self.axes[key]
        score = float(H[int(a["layer"])] @ np.asarray(a["direction"])
                      - float(a["threshold"]))
        return score

    # -- one question -----------------------------------------------------
    def ask(self, event=None):
        q = self.entry.get().strip()
        if not q:
            return
        self.entry.delete(0, "end")
        self._say("you  %s\n" % q, AMBER)
        self.root.update_idletasks()

        H = self.b.capture(self.b.encode(q))
        scores = {k: self._axis(k, H) for k in SCALE}
        # layer activity = hidden-state norm per block, normalised to the max
        norms = np.linalg.norm(H, axis=1)
        top = float(norms.max()) or 1.0
        for i, c in enumerate(self.layer_bars):
            self._bar(c, float(norms[i]) / top, 270,
                      MINT if i % 2 else CYAN)

        ids = self.b.encode(q + "\n")
        top_p = self.b.top_prob(ids)
        self._bar(self.conf, top_p, 300, MINT if top_p > .8 else
                  AMBER if top_p > .5 else RED)
        self.conf_txt.configure(text="%3d%%" % int(top_p * 100))

        for key, (c, v) in self.prov_rows.items():
            s = scores[key]
            self._bar(c, (np.tanh(s / SCALE[key]) + 1) / 2, 176,
                      MINT if s > 0 else RED if s < 0 else DIM)
            if not self.active.get(key, True):
                v.configure(text="n/a", fg=DIM)
                c.delete("all")
            else:
                v.configure(text="%+.1f" % s, fg=MINT if s > 0 else RED)

        ctx = self.active.get("context", True) and scores["context"] > 0
        fam = self.active.get("familiarity", True) and scores["familiarity"] > 0
        if not (self.active.get("context", True)
                or self.active.get("familiarity", True)):
            text, colour = "NO AXIS", DIM
        elif fam:
            text, colour = "FAMILIAR", MINT
        elif ctx:
            text, colour = "CONTEXT", CYAN
        else:
            text, colour = "UNBACKED", RED
        self.verdict.configure(text=text, fg=colour)
        self.reason.configure(
            text=("no calibrated axis on this model" if colour == DIM else
                  "the entity is in the training data" if fam else
                  "the evidence is in the prompt" if ctx else
                  "neither training nor prompt backs this answer"))

        gen, ans = self.b.generate(q, 40)
        self._say("tiny %s\n\n" % ans.strip(), MINT)
        self.status.configure(
            text="mode: %s | axes: context %.1f / familiarity %.1f / self %.1f"
                 % (os.path.basename(getattr(self.b, "ckpt", "tiny2.pt")),
                    scores["context"], scores["familiarity"],
                    scores["self"]))
        return ans


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", default=os.path.join(REPO, "training", "tiny2.pt"))
    ap.add_argument("--calib", default=os.path.join(REPO, "provenance",
                                                    "results.json"))
    ap.add_argument("--demo", default=None, help="ask this on start")
    ap.add_argument("--shot", default=None, help="screenshot then exit")
    a = ap.parse_args()

    calib = json.load(open(a.calib, encoding="utf-8"))
    b = TinyBackend(a.ckpt, os.path.join(REPO, "training"))
    root = tk.Tk()
    desk = Desk(root, b, calib)

    def shoot():
        subprocess.run(["import", "-window", "root", a.shot], check=False)
        root.destroy()

    def start():
        if a.demo:
            desk.entry.insert(0, a.demo)
            desk.ask()
        if a.shot:
            root.after(900, shoot)

    root.after(600, start)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
