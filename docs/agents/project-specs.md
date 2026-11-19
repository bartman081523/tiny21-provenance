# Project specs, tools, build & conventions

> **Zweck.** Jeder projektspezifische Fakt für Agenten und Beitragende.
> Geladen vom Metaprompt in [`AGENTS.md`](../../AGENTS.md), zusammen mit
> [`research.md`](research.md) und [`devmind.md`](devmind.md).
>
> **Evidenzregeln.** Jede Aussage ist belegt (`file:line`, Git-Historie,
> CI-Config oder ausgeführtes Kommando). Kommandos tragen
> `<!-- verified YYYY-MM-DD: <Beobachtung> -->` oder
> `<!-- UNVERIFIED — source: <Fundstelle> -->`.

## Build Commands

Zwei Welten: Python (Training, Analyse, Tests) und C (16-Bit-DOS-Binary).

```bash
# DOS-Binary bauen (OpenWatcom-Cross-Compiler, Linux-Host)
OW=<open-watcom-tree> ./dos-ui/build.sh

# Python-Umgebung + Tests (12 Tests, inkl. 194-Hauptstädte-Batterie)
pip install -r requirements-dev.txt      # torch vorher separat installieren
python -m pytest tests -q

# PyTorch-Checkpoint -> geschicktes TNY2-Binary
python training/train2.py export training/v2.pt dos/TINY.BIN

# Familiaritäts-Ensemble neu auf die Gewichte fitten -> PROV.H
python dos-ui/export_prov.py dos/TINY.BIN dos-ui/PROV.H
```
<!-- verified 2026-11-19: build.sh exit 0, TINY.EXE 70784 B, sha256 a36fe361… unverändert -->
<!-- verified 2026-11-19: pytest 12 passed (ohne PYTHONPATH, Venv mit provenance-audit-Paket) -->
<!-- verified 2026-11-19: train2.py export -> 381808 B; export_prov.py -> PROV.H (Ensemble 0.950, thr -1.710) -->

`build.sh` verlangt `OW` (Baum mit `binl64/`, `h/`, `lib286/`); ohne die
Variable bricht es mit einer klaren Meldung ab (`dos-ui/build.sh:12`).
`requirements-dev.txt` zieht `provenance-audit` als Paket von Git — kein
`PYTHONPATH` auf ein Nachbarverzeichnis nötig.

## Specifications & references

- **TINY 2.1 (Upstream)** — `WollyMonjac/Tiny-2.1`, Turbo C 2.0, LARGE-Modell.
  Unser gepatchtes C liegt als `dos/TINY.C`; der Diff gegen Upstream-Commit
  `4934844` ist `dos-ui/provenance.patch` (mit neutralen Labels, anwendbar
  auf eine lokale `TINY.C`).
- **TNY2-Dateiformat** — Header `TNY2` + `D,L,H,HID` als int16, danach eine
  Skala pro Zeile (`provenance/tiny_v2.py:1-8`); Erzeuger ist
  `training/train2.export`.
- **OpenWatcom v2** — Cross-Compiler, Flag-Satz
  `wcl -ml -bt=dos -l=dos -wcd=481 -DTINY_DOS_UI` (`dos-ui/build.sh:19-20`).
- **provenance-audit** — getrenntes Paket/Repo mit der Achsen-Mathematik
  (`provenance_audit.core.loo_axis`, `paired_direction`,
  `midpoint_threshold`); hier nur konsumiert.
- **Antwortformat v2** — kanonisch eine Vorlage pro Relation, nackter Wert,
  Fallback `"Sorry, …"` (`provenance/DIAGNOSIS.md`).
- **DOS-Budget** — 4×96 ≈ 380 KB quantisiert passt in ~540 KB
  konventionellen Speicher; 4×128 passt nicht (`provenance/DIAGNOSIS.md`).

## Linting / Formatting

Nichts erzwungen: kein `.editorconfig`, keine Python-Lint-Config, kein
Lint-Job in der CI (verifiziert 2026-11-19). Die C-Seite wird über
Compiler-Warnungen sauber gehalten — der Build läuft mit `no warnings,
no errors` (`-wcd=481` unterdrückt nur die Turbo-C-`time`-Kollision).

## Coding Conventions

- **C:** Turbo-C-2.0-kompatibel bleiben; Compiler-Weichen über
  `TINY_DOS_UI` statt `__TURBOC__` (3 Stellen im Patch), damit OpenWatcom
  baut, ohne Compiler-Makros zu verbiegen (`dos-ui/provenance.patch:1-12`).
- **C:** Neue UI-Ausgaben über `tc_compat.[ch]`, nicht über Turbo-C-Interna.
- **Python:** `provenance/` ist read-only gegenüber den Gewichten; der
  Router baut die Token-Ids selbst, weil die Backends `\n` anhängen
  (`provenance/router.py:80-100`).
- **Python:** Tests laufen ohne Modell-Download; die 194er-Batterie ist der
  Vertrag (dauert ~4 s).
- **Kommentare/Docstrings:** deutsch, mit Begründung statt Beschreibung
  (`provenance/DIAGNOSIS.md`, `dos/TINY.C`).

## Commit Message Style

`Bereich: Gegenstand`, deutsch oder englisch, Bereich klein geschrieben:

```
deps: declare provenance-audit as a package (no sibling PYTHONPATH)
v2: canonical answer format shipped (191/194 free, 0 refusals; 194/194 routed)
router: routed decode first (194/194 capitals), add the full battery to CI
ci: stage release assets flat so the release job finds them
diagnosis: why Poland is refused, and the architecture behind it
```

Messwerte gehören in die Betreffzeile, wenn sie die Änderung begründen.

## Common Workflows

1. **Nach jeder Modell-/Router-Änderung:** `python -m pytest tests -q`
   (12 Tests, u. a. 194/194 Hauptstädte mit Router).
2. **Ein Test:** `python -m pytest tests/test_repo.py::test_all_capitals -q`.
3. **DOS-Binary neu bauen und prüfen:** `OW=<tree> ./dos-ui/build.sh`,
   dann `sha256sum dos/TINY.EXE` gegen den Release-Hash.
4. **Neues Modell ausliefern:** `train2.py export` → `export_prov.py`
   (PROV.H) → `build.sh` → pytest → Tag `v*` (CI baut und veröffentlicht).
5. **DOS-Verhalten prüfen:** QEMU mit 1,44-MB-Image, `HIMEMX.EXE` +
   `DOS=HIGH,UMB`, Batch `tiny 0 /p < q.txt`.

## Architecture Overview

1. **Embedding** — Zeichen-Vokabular (256), Hidden 96, 4 Schichten, 4 Heads;
   TNY2 quantisiert die Gewichte mit einer Skala pro Zeile
   (`provenance/tiny_v2.py:1-8`).
2. **Antwort-Decode** — freier Decode liefert den kanonischen Wert;
   `Sorry, …` ist der eigene Fallback-Token (v2, kollisionsfrei).
3. **Router (routed-first)** — erkennt die Relation, baut den Präfix
   (`"the capital is "`) und decodiert den Wert direkt
   (`provenance/router.py:47-100`); 194/194 Hauptstädte, 16/16 Relationen.
4. **Provenienz-Panel** — 4-Schichten-Familiaritäts-Ensemble + Antwort-
   Konfidenz + Domain-Gate; Regel `UNBACKED`, wenn `fam < −0.5` oder
   `p_top < 0.90` (`dos/TINY.C`, `dos/PROV.H`).
5. **DOS-UI** — `TINY.EXE` lädt `TINY.BIN`, zeigt Antwort + Panel; 8.3-Namen,
   konventioneller Speicher.

| Datei | Rolle |
| :--- | :--- |
| `dos/TINY.C` | DOS-Programm (gepatcht): UI, Panel, `route_suffix()` |
| `dos/TINY.BIN` | geschickte Gewichte (TNY2, v2) |
| `dos/PROV.H` | generierte Panel-Kalibrierung |
| `dos-ui/build.sh` | OpenWatcom-Build |
| `dos-ui/export_prov.py` | fittet das Ensemble, schreibt `PROV.H` |
| `provenance/router.py` | routed-first Decode + Helfer |
| `provenance/tiny_v2.py` | TNY2-Loader/Backend |
| `provenance/analyze_weaknesses.py` | 194-Länder-Sweep, Familiarität, Fallback-Masse |
| `training/train2.py` | Training + `export` |
| `training/train_v2.py` | v2-Finetune (kanonisches Format) |
| `tests/test_repo.py` | 12 Tests inkl. voller Batterie |

## Testing

`pytest` ist die Suite; es gibt keine weiteren Runner.

- **Alles:** `python -m pytest tests -q` → 12 passed (~4 s), ohne Netz und
  ohne Modell-Download.
- **Einzelfall:** `python -m pytest tests/test_repo.py::test_all_capitals -q`
  (194 Länder × Router) bzw. `::test_routed_capital_answers`.
- **Fixtures:** keine Golden-Files; die Erwartungen stehen als Tabellen im
  Test (`tests/test_repo.py:116`).
- **DOS-Seite:** `TINY.EXE 0 /p` (Selbsttest 12/12) und der
  40-Fragen-Batch in QEMU; Ergebnisse werden als Roh-Log behalten.
- **Kalibrierung:** `test_calibration_is_consistent` prüft `PROV.H` gegen die
  Gewichte — nach jedem Re-Export laufen lassen.

## CI

`.github/workflows/ci.yml`, zwei Jobs:

- **python** — Python 3.11, `numpy`, `pytest`, CPU-Torch,
  `provenance-audit` von Git, dann `pytest tests -q`.
- **dos** — OpenWatcom-Snapshot (gecacht), `./dos-ui/build.sh`, Staging von
  `TINY.EXE`/`TINY.BIN`/`PROV.H` + SHA256, Upload als Artefakt.

Auf `v*`-Tags wird ein Release mit den gestagten Dateien veröffentlicht.
Lokal reproduzierbar mit den Kommandos oben; der CI-Build ist byte-identisch
zum lokalen (`sha256 a36fe361…`, verifiziert 2026-11-19).

## Runtime Configuration / Usage

- **Start:** `CD \TINY` → `TINY`; erwartet `TINY.BIN` im selben Verzeichnis.
- **Speicher:** ~540 KB konventionell; HIMEMX + `DOS=HIGH,UMB` im Test-Image.
- **Dateigrößen:** `TINY.EXE` 70 784 B, `TINY.BIN` 381 808 B (v2).
- **Panel-Regel:** `UNBACKED` bei `fam < −0.5` oder `p_top < 0.90`;
  `familiar` bei `fam > 0.5` und `p_top ≥ 0.95`; sonst `--`; Domain-Gate auf
  `"capital"`.
- **Router:** routed-first für bekannte Relationen, freier Decode als Fallback.

## Dependencies

- **Python-Dev:** `requirements-dev.txt` — `numpy>=1.23`, `pytest`,
  `provenance-audit` (Git-Referenz). `torch` ist bewusst nicht gepinnt
  (CPU-Wheel in der CI, GPU lokal).
- **C:** OpenWatcom v2 (`wcl`), `mtools` für die Disketten-Images, `qemu-system-i386`
  für die DOS-Tests.
- Keine weiteren Manifeste; es gibt kein `pyproject.toml`/`setup.py`.

## Source Layout

```
dos/              TINY.C, TINY.BIN, PROV.H, TINY.EXE, Upstream-README
dos-ui/           build.sh, export_prov.py, provenance.patch, README
dos-test/         QEMU-Images/Batches für die DOS-Verifikation
provenance/       Router, Backends, Achsen-Analysen, Experimente, DIAGNOSIS
training/         train2.py (Train/Export), train_v2.py, Generator, Fakten
tests/            pytest-Suite (12 Tests)
```

Build-Output landet direkt in `dos/` (`TINY.EXE`), der Rest ist Quellcode
oder generiertes Artefakt (siehe unten).

## Generated artefacts (never hand-edit)

| Datei | Quelle | Kommando |
| :--- | :--- | :--- |
| `dos/TINY.BIN` | `training/v2.pt` | `python training/train2.py export training/v2.pt dos/TINY.BIN` <!-- verified 2026-11-19: 381808 B --> |
| `dos/TINY.EXE` | `dos/TINY.C` + `PROV.H` | `OW=<tree> ./dos-ui/build.sh` <!-- verified 2026-11-19: sha256 a36fe361… --> |
| `dos/PROV.H` | `dos/TINY.BIN` | `python dos-ui/export_prov.py dos/TINY.BIN dos-ui/PROV.H` <!-- verified 2026-11-19 --> |
| `training/v2.pt` | `tiny2.pt` + Korpus | `python training/train_v2.py 20 v2.pt` <!-- UNVERIFIED — source: train_v2.py; Lauf dauerte 20 min, Ergebnis committed --> |
| `dos-ui/provenance.patch` | Upstream `TINY.C` (Commit 4934844) | `git show 4934844:dos/TINY.C > /tmp/u.c && diff -u --label TINY.C --label TINY.C /tmp/u.c dos/TINY.C` <!-- verified 2026-11-19: Patch reproduziert dos/TINY.C byte-genau --> |

## Writing pull requests / issues

Kein `CONTRIBUTING.md`, keine Templates. Upstream ist
`WollyMonjac/Tiny-2.1`; Änderungen am C-Kern gehören als Patch
(`dos-ui/provenance.patch`) in ein Issue/PR dort, nicht als stiller Fork.
Im eigenen Repo gilt die Commit-Norm oben plus: Messwerte mitliefern,
Fehlläufe nicht wegretuschieren.

## Verification log

| Command | Status | Evidence | Date |
| :--- | :--- | :--- | :--- |
| `OW=<tree> ./dos-ui/build.sh` | verified | exit 0, sha256 unverändert | 2026-11-19 |
| `python -m pytest tests -q` | verified | 12 passed, ohne PYTHONPATH | 2026-11-19 |
| `python training/train2.py export …` | verified | 381 808 B TNY2 | 2026-11-19 |
| `python dos-ui/export_prov.py …` | verified | PROV.H, Ensemble 0.950 | 2026-11-19 |
| Patch gegen Upstream 4934844 | verified | reproduziert `dos/TINY.C` | 2026-11-19 |
| `python training/train_v2.py 20 v2.pt` | UNVERIFIED (in dieser Session) | 20-min-Lauf, Ergebnis committed | 2026-11-19 |
| QEMU-DOS-Lauf im 1,44-MB-Image | verified (frühere Session) | 20/20 reale Hauptstädte | 2026-11-19 |
