#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Detektor: kein Testlauf und kein Mutationslauf darf echte Daten neben dem Code
veraendern -- auch nicht ueber einen Symlink, der aus dem Repo herauszeigt.

    python test_schutz.py

Vorfall (Drachenhort, 2af573a): Im Clone war knowledge.jsonl ein Symlink auf
~/rag-lab/knowledge.jsonl, die LIVE-Wissensbasis der Pipe. Unter Mutation S10
("classify.py ignoriert die spiel_id") rief test_spiele.py classify.main() mit
Fake-Antwort "flavor" auf; ziel() lieferte den Modul-Default BASE/knowledge.jsonl
und classify schrieb dorthin: 79 Eintraege "flavor", 8 Minuten 0 Chunks.

Drei Schichten schuetzen, jede wird hier EINZELN geprueft -- in einer Repo-Kopie,
in der die jeweils anderen Schichten abgeschaltet sind, mit einer Waechterdatei
ausserhalb der Kopie. Ein Gesamttest wuerde das Entfernen EINER Schicht nicht
sehen, solange die anderen noch halten.
  (a) test_mutationen.py mutiert nur in einer Temp-Kopie der Quelldateien
  (b) testumgebung.py biegt alle Standardpfade der Skripte ins Temp-Verzeichnis
  (3) rag.pruefe_schreibziel: nie durch einen Symlink schreiben
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402
import classify  # noqa: E402
import vision_ingest  # noqa: E402
import ingest  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
INHALT = "".join(json.dumps({"id": i, "seite": i, "typ": "regel", "text": f"WAECHTER {i}"}) + "\n"
                 for i in range(1, 80))
S10 = ("    if not rest:\n        return KNOW", "    if True:\n        return KNOW")


def summe(pfad):
    with open(pfad, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def ersetze(pfad, alt, neu):
    with open(pfad, encoding="utf-8") as f:
        s = f.read()
    assert s.count(alt) == 1, (pfad, alt)
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(s.replace(alt, neu))


class Kopie(unittest.TestCase):
    """Repo-Kopie mit Waechter-knowledge.jsonl, als Symlink nach draussen oder als Datei."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rag-schutz-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo, self.draussen = os.path.join(self.tmp, "repo"), os.path.join(self.tmp, "rag-lab")
        os.makedirs(self.draussen)
        os.makedirs(self.repo)
        for name in os.listdir(BASE):
            q = os.path.join(BASE, name)
            if (name.endswith(".py") or name in ("golden_set.example.json", "regression_referenz.json", "pipe_referenz.json",
                                                                "pipe_verlauf_referenz.json")) \
                    and os.path.isfile(q) and not os.path.islink(q):
                shutil.copy(q, self.repo)
        os.makedirs(os.path.join(self.repo, "pdfs"))

    def waechter(self, als_symlink):
        ziel = os.path.join(self.draussen if als_symlink else self.repo, "knowledge.jsonl")
        with open(ziel, "w") as f:
            f.write(INHALT)
        if als_symlink:
            os.symlink(ziel, os.path.join(self.repo, "knowledge.jsonl"))
        return ziel

    def ohne_testumgebung(self):
        with open(os.path.join(self.repo, "testumgebung.py"), "w", encoding="utf-8") as f:
            f.write('"""abgeschaltet (Detektor-Test)"""\n')

    def ohne_symlinkschutz(self):
        pfad = os.path.join(self.repo, "rag.py")
        with open(pfad, encoding="utf-8") as f:
            schon_aus = "    if os.path.islink(pfad):\n        raise KonfigFehler(" not in f.read()
        if not schon_aus:          # unter Mutation Y1 ist er bereits aus
            ersetze(pfad, "    if os.path.islink(pfad):\n        raise KonfigFehler(",
                    "    if False:\n        raise KonfigFehler(")

    def lauf(self, *args, env=None):
        umgebung = {k: v for k, v in os.environ.items()
                    if k not in ("DATA_DIR", "INDEX_PATH", "KNOWLEDGE_JSONL", "GOLDEN_SET", "NUR")}
        umgebung.update(env or {})
        return subprocess.run([sys.executable, *args], cwd=self.repo, env=umgebung, capture_output=True, text=True)


class TestSchichtTestumgebung(Kopie):
    """(b) allein: Symlinkschutz aus, Waechter als normale Datei neben dem Code."""

    def test_vorfall_s10_mit_test_spiele(self):
        w = self.waechter(als_symlink=False)
        self.ohne_symlinkschutz()
        ersetze(os.path.join(self.repo, "classify.py"), *S10)
        p = self.lauf("test_spiele.py")
        self.assertNotEqual(p.returncode, 0, "S10 muss rot werden -- sonst prueft der Detektor nichts")
        self.assertEqual(summe(w), hashlib.sha256(INHALT.encode()).hexdigest(), "Testlauf schrieb in echte Daten")

    def test_skripte_mit_standardpfad(self):
        w = self.waechter(als_symlink=False)
        self.ohne_symlinkschutz()
        bild = os.path.join(self.tmp, "seite_6.png")
        open(bild, "wb").close()
        skript = (
            "import testumgebung, types, classify, vision_ingest\n"
            "classify.requests = types.SimpleNamespace(post=lambda *a, **k: types.SimpleNamespace(\n"
            "    raise_for_status=lambda: None, json=lambda: {'message': {'content': 'flavor'}}))\n"
            "import os; open(classify.KNOW, 'w').write(open('knowledge.jsonl').read())\n"
            "classify.main()\n"
            f"vision_ingest.frag_vision = lambda img: 'Karte: 1'\n"
            f"vision_ingest.main([{bild!r}])\n")
        p = self.lauf("-c", skript)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(summe(w), hashlib.sha256(INHALT.encode()).hexdigest(), "Skript schrieb in echte Daten")


class TestJudgeKey(unittest.TestCase):
    """testumgebung laesst keinen Test den echten Anthropic-Key lesen (judge.py)."""

    def test_echter_key_bleibt_unberuehrt(self):
        home = tempfile.mkdtemp(prefix="rag-home-")
        self.addCleanup(shutil.rmtree, home, True)
        os.makedirs(os.path.join(home, ".config", "anthropic"))
        with open(os.path.join(home, ".config", "anthropic", "api_key"), "w") as f:
            f.write("KOEDER-KEY")
        skript = ("import testumgebung, judge\n"
                  "try:\n    print(judge.lies_anthropic_key())\n"
                  "except Exception as e:\n    print(type(e).__name__)\n")
        p = subprocess.run([sys.executable, "-c", skript], cwd=BASE, capture_output=True, text=True,
                           env=dict(os.environ, HOME=home))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("KOEDER-KEY", p.stdout)
        self.assertIn("ModusNichtVerfuegbar", p.stdout)
        # Gegenprobe: ohne testumgebung wuerde judge den Key finden
        p = subprocess.run([sys.executable, "-c", "import judge; print(judge.lies_anthropic_key())"],
                           cwd=BASE, capture_output=True, text=True, env=dict(os.environ, HOME=home))
        self.assertIn("KOEDER-KEY", p.stdout)


J1 = ("def lies_anthropic_key(pfad=None):\n    pfad = pfad or ANTHROPIC_KEY_DATEI",
      "def lies_anthropic_key(pfad=ANTHROPIC_KEY_DATEI):\n    pfad = pfad")
# Zaehlt jeden Dateizugriff (Audit-Hook "open") unter dem "echten" HOME des Prozesses.
AUDIT = ("import os, sys\n"
         "ECHT = os.path.realpath(os.environ['HOME'])\n"
         "zugriffe = []\n"
         "def hook(ereignis, args):\n"
         "    if ereignis == 'open' and isinstance(args[0], str) and os.path.realpath(args[0]).startswith(ECHT + os.sep):\n"
         "        zugriffe.append(args[0])\n"
         "sys.addaudithook(hook)\n")


class TestJudgeKeyUnterMutation(Kopie):
    """Runde 7 SOLLTE-1: testumgebung und Treiber lenken HOME um -- selbst unter der
    Kritiker-Mutation J1 (Key-Pfad beim Import als Default-Argument gebunden) liest kein
    Test den echten Key. Beleg per Audit-Hook (Zugriffszaehler) und Kanarien-Key."""

    def echtes_home(self):
        home = os.path.join(self.tmp, "echtes-home")
        os.makedirs(os.path.join(home, ".config", "anthropic"))
        with open(os.path.join(home, ".config", "anthropic", "api_key"), "w") as f:
            f.write("KANARIE-ECHTER-KEY")
        return home

    def skript(self, mit_testumgebung):
        return (AUDIT + ("import testumgebung\n" if mit_testumgebung else "")
                + "import judge\n"
                  "try:\n    print('KEY', judge.lies_anthropic_key())\n"
                  "except judge.ModusNichtVerfuegbar:\n    print('NICHT-VERFUEGBAR')\n"
                  "print('ZUGRIFFE', len(zugriffe))\n")

    def test_j1_liest_keinen_echten_key(self):
        home = self.echtes_home()
        ersetze(os.path.join(self.repo, "judge.py"), *J1)
        p = self.lauf("-c", self.skript(True), env={"HOME": home, "XDG_CONFIG_HOME": os.path.join(home, ".config")})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("KANARIE", p.stdout)
        self.assertIn("NICHT-VERFUEGBAR", p.stdout)
        self.assertIn("ZUGRIFFE 0\n", p.stdout)
        # Gegenprobe: ohne testumgebung liest die J1-Mutante den Kanarien-Key -- der Zaehler sieht es
        p = self.lauf("-c", self.skript(False), env={"HOME": home})
        self.assertIn("KEY KANARIE-ECHTER-KEY", p.stdout)
        self.assertNotIn("ZUGRIFFE 0\n", p.stdout)

    def test_treiber_lenkt_home_um(self):
        # Die Testdateien, die der Mutationstreiber startet, sehen nie den echten HOME --
        # auch eine Testdatei ohne testumgebung nicht.
        home = self.echtes_home()
        lauf = os.path.join(self.tmp, "lauf")
        os.makedirs(lauf)
        with open(os.path.join(lauf, "test_home.py"), "w") as f:
            f.write("import judge_frei\n")
        with open(os.path.join(lauf, "judge_frei.py"), "w") as f:
            f.write("import os, sys\n"
                    "pfad = os.path.expanduser('~/.config/anthropic/api_key')\n"
                    "x = os.path.join(os.environ.get('XDG_CONFIG_HOME', ''), 'anthropic', 'api_key')\n"
                    "sys.exit(1 if any(os.path.exists(q) for q in (pfad, x)) else 0)\n")
        import test_mutationen
        with mock.patch.dict(os.environ, HOME=home, XDG_CONFIG_HOME=os.path.join(home, ".config")):
            self.assertEqual(test_mutationen.rote_tests(lauf, ["test_home.py"]), [])
            # Gegenprobe: mit dem echten HOME wird die Testdatei rot
            p = subprocess.run([sys.executable, "test_home.py"], cwd=lauf, capture_output=True)
            self.assertEqual(p.returncode, 1)


class TestSchichtSymlinkschutz(Kopie):
    """(3) allein: testumgebung aus, Waechter als Symlink nach draussen."""

    def test_vorfall_s10_mit_test_spiele(self):
        w = self.waechter(als_symlink=True)
        self.ohne_testumgebung()
        ersetze(os.path.join(self.repo, "classify.py"), *S10)
        self.lauf("test_spiele.py")
        self.assertEqual(summe(w), hashlib.sha256(INHALT.encode()).hexdigest(), "schrieb durch den Symlink")


class TestSchichtTreiberkopie(Kopie):
    """(a) allein: testumgebung und Symlinkschutz aus, Waechter als Symlink; Treiber mit S10."""

    def test_mutationstreiber_mutiert_nie_das_arbeitsverzeichnis(self):
        w = self.waechter(als_symlink=True)
        self.ohne_testumgebung()
        self.ohne_symlinkschutz()
        vorher = {n: summe(os.path.join(self.repo, n)) for n in os.listdir(self.repo) if n.endswith(".py")}
        p = self.lauf("test_mutationen.py", env={"NUR": "S10"})
        self.assertIn("S10", p.stdout, p.stdout + p.stderr)
        self.assertEqual(summe(w), hashlib.sha256(INHALT.encode()).hexdigest(), "Mutationslauf schrieb in echte Daten")
        nachher = {n: summe(os.path.join(self.repo, n)) for n in vorher}
        self.assertEqual(nachher, vorher, "Treiber hat Dateien im Arbeitsverzeichnis veraendert")


class TestSymlinkschutzDirekt(unittest.TestCase):
    """Jede Schreibstelle lehnt einen Symlink ab und laesst das Ziel unberuehrt."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ziel = os.path.join(self.tmp, "echt.jsonl")
        with open(self.ziel, "w") as f:
            f.write(INHALT)
        self.link = os.path.join(self.tmp, "knowledge.jsonl")
        os.symlink(self.ziel, self.link)

    def unberuehrt(self):
        self.assertEqual(summe(self.ziel), hashlib.sha256(INHALT.encode()).hexdigest())

    def test_rag_schreiben(self):
        with self.assertRaises(rag.KonfigFehler) as ctx:
            rag.schreibe_jsonl(self.link, [{"x": 1}])
        self.assertIn("Symlink", str(ctx.exception))
        self.unberuehrt()
        idx = os.path.join(self.tmp, "index.sqlite")
        os.symlink(self.ziel, idx)
        with self.assertRaises(rag.KonfigFehler):
            rag.oeffne_index(idx, schreibend=True)
        self.unberuehrt()

    def test_lesen_durch_symlink_bleibt_erlaubt(self):
        self.assertEqual(len(rag.lies_jsonl(self.link)), 79)

    def test_classify(self):
        import types
        fake = types.SimpleNamespace(post=lambda *a, **k: types.SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: {"message": {"content": "flavor"}}))
        with mock.patch.object(classify, "KNOW", self.link), mock.patch.object(classify, "requests", fake), \
             self.assertRaises(rag.KonfigFehler), mock.patch("sys.stdout", io.StringIO()):
            classify.main()
        self.unberuehrt()

    def test_vision_ingest(self):
        bild = os.path.join(self.tmp, "seite_6.png")
        open(bild, "wb").close()
        with mock.patch.object(vision_ingest, "KNOW", self.link), \
             mock.patch.object(vision_ingest, "frag_vision", lambda img: "Karte: 1"), \
             self.assertRaises(rag.KonfigFehler), mock.patch("sys.stdout", io.StringIO()):
            vision_ingest.main([bild])
        self.unberuehrt()

    def test_ingest_mit_haengendem_symlink(self):
        # Zeigt der Symlink ins Leere, greift die "Datei existiert schon"-Sperre nicht --
        # ohne Symlinkschutz entstuende die Zieldatei draussen.
        import types
        os.remove(self.ziel)
        doc = types.SimpleNamespace(iterate_items=lambda: [(types.SimpleNamespace(
            text="Regel.", prov=[types.SimpleNamespace(page_no=1)]), 0)])
        with mock.patch.object(ingest, "OUT", self.link), \
             mock.patch.object(ingest, "DocumentConverter", lambda: types.SimpleNamespace(
                 convert=lambda p: types.SimpleNamespace(document=doc))), \
             mock.patch.object(ingest, "verbalize", lambda t: "v"), \
             mock.patch.object(sys, "argv", ["ingest.py", "x.pdf"]), mock.patch("sys.stdout", io.StringIO()), \
             self.assertRaises(rag.KonfigFehler):
            ingest.main()
        self.assertFalse(os.path.exists(self.ziel))


if __name__ == "__main__":
    unittest.main(verbosity=2)
