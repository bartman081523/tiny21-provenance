"""Tests for the repo's Python side and the decoding router.

Model tests load the shipped weights; they are skipped automatically when
torch is not installed.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from provenance.router import is_fallback, prefix_for, value_of  # noqa: E402


# ---------------------------------------------------------------- router ----
def test_prefix_for_capital():
    assert prefix_for("What is the capital of Poland?") == "the capital is "


def test_prefix_for_other_relations():
    assert prefix_for("what language do they speak in canada") == "they speak "
    assert prefix_for("what is the money of japan") == "they use "


def test_prefix_none_for_spelling():
    assert prefix_for("spell computer") is None


def test_fallback_detection():
    assert is_fallback("I have never heard of Poland.")
    assert is_fallback("I do not know a country called Zorbia.")
    assert not is_fallback("Warsaw.")
    assert not is_fallback("It is Warsaw.")


def test_value_of_strips_all_templates():
    assert value_of("Warsaw.") == "Warsaw"
    assert value_of("It is Warsaw.") == "Warsaw"
    assert value_of("The capital is Warsaw.") == "Warsaw"
    assert value_of("The capital of Poland is Warsaw.") == "Warsaw"
    assert value_of("they speak English.") == "English"


# ---------------------------------------------------------------- weights ---
def test_weights_present():
    for p in ("dos/TINY.BIN", "dos/TINY_PROV.EXE", "training/tiny2.pt"):
        assert os.path.getsize(os.path.join(ROOT, p)) > 1000, p


def test_calibration_is_consistent():
    cal = json.load(open(os.path.join(ROOT, "dos-ui",
                                      "prov_calibration.json")))
    assert 0.7 <= cal["acc"] <= 1.0
    assert cal["p"] < 0.05
    assert cal["layer"] >= 0
    header = open(os.path.join(ROOT, "dos", "PROV.H"), encoding="ascii").read()
    assert "#define PROV_D 96" in header
    assert "#define PROV_L 4" in header
    assert "#define PROV_MARGIN" in header


# ---------------------------------------------------------------- model -----
torch = pytest.importorskip("torch")


@pytest.fixture(scope="module")
def quant():
    from provenance.tiny_v2 import TinyV2Backend
    return TinyV2Backend(os.path.join(ROOT, "dos", "TINY.BIN"),
                         os.path.join(ROOT, "training"))


def test_loader_dims(quant):
    assert quant.dims == (96, 4, 4, 256)


def test_routed_capital_answers(quant):
    from provenance.router import answer
    for country, want in (("france", "paris"), ("poland", "warsaw"),
                          ("qatar", "doha"), ("peru", "lima")):
        r = answer(quant, f"what is the capital of {country}")
        assert want in r["value"].lower(), (country, r["value"])
        assert not r["fallback"], (country, r["text"])


def test_fallback_repaired(quant):
    from provenance.router import answer
    r = answer(quant, "what is the capital of poland", repair=True)
    assert not r["fallback"] and "warsaw" in r["value"].lower()
    # the free decode of that question is the refusal -- the router is what
    # turns it into an answer
    free = quant.generate("what is the capital of poland\n", 40)[1]
    assert is_fallback(free)


def test_nonce_is_flagged_by_familiarity(quant):
    from provenance_audit.core import paired_direction
    from provenance.run_tiny import REAL, NONCE
    import numpy as np
    H = lambda n: quant.capture(quant.encode(
        f"what is the capital of {n}\nthe capital is "))
    HK = np.stack([H(x) for x in REAL])
    HN = np.stack([H(x) for x in NONCE])
    d = paired_direction(HK[:, 0], HN[:, 0])
    mu, sd = float((HK[:, 0] @ d).mean()), float((HK[:, 0] @ d).std())
    z = lambda n: float(((H(n)[0] @ d) - mu) / sd)
    assert z("france") > z("vrandel")
