#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
messung/bewerte.py -- ruft judge.bewerte, schreibt urteile.jsonl, bricht bei unbekannter Frage ab.

    python test_messung_bewerte.py

judge.bewerte ist durch einen Fake ersetzt: kein Modell, kein Netz, kein Key.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import judge  # noqa: E402
from messung import bewerte as b  # noqa: E402

GOLDEN = {"spiel_id": "spiel-a", "fragen": [
    {"id": 1, "frage": "Frage eins?", "typ": "fakt", "erwartet": "eins", "keywords": ["eins"], "seiten": [1]},
    {"id": 2, "frage": "Frage zwei?", "typ": "leerstelle", "erwartet": "nichts", "erwartet_verweigerung": True,
     "keywords": [], "seiten": []}]}


def zeile(fid, antwort, sid="spiel-a"):
    return {"spiel_id": sid, "frage_id": fid, "frage": f"F{fid}", "antwort": antwort, "abgerufen": [1],
            "scores": [0.5], "entscheid": None, "probs": None, "t_antwort": 1.5}


class BewerteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.golden = os.path.join(self.tmp.name, "golden")
        os.makedirs(os.path.join(self.golden, "spiel-a"))
        with open(os.path.join(self.golden, "spiel-a", "golden_set.json"), "w", encoding="utf-8") as f:
            json.dump(GOLDEN, f)
        self.aufrufe = []

        def fake(modus, modell, frage, antwort):
            self.aufrufe.append((modus, modell, frage["id"], antwort))
            if frage["id"] == 2:
                return {"urteil": "richtig", "rohtext": "fest", "input_tokens": 0, "output_tokens": 0,
                        "deterministisch": True}
            return {"urteil": "falsch", "rohtext": "Begruendung", "input_tokens": 100, "output_tokens": 7}
        p = mock.patch.object(judge, "bewerte", fake)
        p.start()
        self.addCleanup(p.stop)

    def lauf(self, name, zeilen):
        verz = os.path.join(self.tmp.name, name)
        os.makedirs(verz)
        pfad = os.path.join(verz, "antworten.jsonl")
        with open(pfad, "w", encoding="utf-8") as f:
            for z in zeilen:
                f.write(json.dumps(z) + "\n")
        return pfad

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = b.main(list(argv))
        return rc, out.getvalue(), err.getvalue()


class TestBewerte(BewerteTest):
    def test_schreibt_urteile_neben_die_antworten(self):
        pfad = self.lauf("l1", [zeile(1, "A eins"), zeile(2, "In den gefundenen Stellen steht dazu nichts.")])
        rc, out, err = self.cli("--golden", self.golden, pfad)
        self.assertEqual(rc, 0, err)
        ziel = os.path.join(os.path.dirname(pfad), "urteile.jsonl")
        self.assertEqual(out.strip().splitlines()[-1], ziel)
        with open(ziel, encoding="utf-8") as f:
            zeilen = [json.loads(z) for z in f]
        self.assertEqual([z["urteil"] for z in zeilen], ["falsch", "richtig"])
        self.assertEqual(zeilen[0]["begruendung"], "Begruendung")
        self.assertEqual((zeilen[0]["input_tokens"], zeilen[0]["output_tokens"]), (100, 7))
        self.assertEqual([z["deterministisch"] for z in zeilen], [False, True])
        self.assertEqual(zeilen[0]["t_antwort"], 1.5)            # Felder des Laufs bleiben erhalten
        self.assertEqual(zeilen[0]["antwort"], "A eins")

    def test_default_ist_anthropic_haiku_und_argumente_gelten(self):
        pfad = self.lauf("l1", [zeile(1, "x")])
        self.cli("--golden", self.golden, pfad)
        self.assertEqual(self.aufrufe[-1][:2], ("anthropic", judge.ANTHROPIC_DEFAULT))
        self.cli("--golden", self.golden, "--modus", "frei", "--modell", "qwen-x", pfad)
        self.assertEqual(self.aufrufe[-1][:2], ("frei", "qwen-x"))

    def test_frage_geht_als_golden_frage_an_den_judge(self):
        pfad = self.lauf("l1", [zeile(1, "x")])
        self.cli("--golden", self.golden, pfad)
        self.assertEqual(self.aufrufe, [("anthropic", judge.ANTHROPIC_DEFAULT, 1, "x")])

    def test_laufverzeichnis_statt_datei(self):
        pfad = self.lauf("l1", [zeile(1, "x")])
        rc, _, _ = self.cli("--golden", self.golden, os.path.dirname(pfad))
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(pfad), "urteile.jsonl")))

    def test_unbekannte_frage_bricht_laut_ab_ohne_modellaufruf(self):
        pfad = self.lauf("l1", [zeile(1, "x"), zeile(99, "y")])
        rc, _, err = self.cli("--golden", self.golden, pfad)
        self.assertEqual(rc, 1)
        self.assertIn("99", err)
        self.assertIn("nicht im Golden Set", err)
        self.assertEqual(self.aufrufe, [])                        # nichts bezahlt
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(pfad), "urteile.jsonl")))

    def test_unbekanntes_spiel_bricht_ab(self):
        pfad = self.lauf("l1", [zeile(1, "x", sid="spiel-z")])
        rc, _, err = self.cli("--golden", self.golden, pfad)
        self.assertEqual((rc, self.aufrufe), (1, []))
        self.assertIn("spiel-z", err)

    def test_fehler_im_zweiten_lauf_verhindert_auch_den_ersten(self):
        gut = self.lauf("l1", [zeile(1, "x")])
        schlecht = self.lauf("l2", [zeile(42, "y")])
        rc, _, _ = self.cli("--golden", self.golden, gut, schlecht)
        self.assertEqual((rc, self.aufrufe), (1, []))
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(gut), "urteile.jsonl")))

    def test_golden_set_flach_als_spiel_id_json(self):
        flach = os.path.join(self.tmp.name, "flach")
        os.makedirs(flach)
        with open(os.path.join(flach, "spiel-a.json"), "w", encoding="utf-8") as f:
            json.dump(GOLDEN, f)
        pfad = self.lauf("l1", [zeile(1, "x")])
        self.assertEqual(self.cli("--golden", flach, pfad)[0], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
