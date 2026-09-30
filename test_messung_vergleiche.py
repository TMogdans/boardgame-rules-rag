#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
messung/vergleiche.py -- Kennzahlen an handgebauten Urteilen, ohne Modell.

    python test_messung_vergleiche.py

Die Soll-Werte sind von Hand ausgezaehlt (siehe SETTING_A/SETTING_B unten):
  Lauf A1: 2 richtig, 1 teilweise, 2 falsch, 1 unsicher -> Treffsicherheit 2/(6-1) = 0.4
  Lauf A2: 1 richtig, 2 teilweise, 2 falsch, 1 unsicher -> 1/(6-1) = 0.2
Ein Nenner ohne Abzug der unsicheren Urteile (2/6) waere eine andere Zahl.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
from messung import vergleiche as v  # noqa: E402

S = "spiel-a"
# Urteile je Frage 1..6, Laufzeit je Frage
A1 = (["richtig", "richtig", "falsch", "falsch", "unsicher", "teilweise"], [1, 2, 3, 4, 5, 60])
A2 = (["richtig", "falsch", "falsch", "teilweise", "unsicher", "teilweise"], [1, 1, 1, 1, 1, 1])
B1 = (["richtig", "richtig", "richtig", "teilweise", "falsch", "teilweise"], [2, 2, 2, 2, 2, 2])
B2 = (["richtig", "richtig", "teilweise", "teilweise", "falsch", "falsch"], [2, 2, 2, 2, 2, 2])
SETTING_A, SETTING_B = (A1, A2), (B1, B2)


def schreibe_lauf(wurzel, name, urteile, zeiten):
    verz = os.path.join(wurzel, name)
    os.makedirs(verz)
    with open(os.path.join(verz, "urteile.jsonl"), "w", encoding="utf-8") as f:
        for i, (u, t) in enumerate(zip(urteile, zeiten), 1):
            f.write(json.dumps({"spiel_id": S, "frage_id": i, "antwort": "x", "urteil": u, "t_antwort": t}) + "\n")
    return verz


class VergleicheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.w = self.tmp.name
        self.zaehler = 0

    def laeufe(self, *runs, praefix="l"):
        """Legt je Lauf ein frisches Verzeichnis an (auch bei mehrfachem Aufruf im selben Test)."""
        aus = []
        for r in runs:
            self.zaehler += 1
            aus.append(v.lies_lauf(schreibe_lauf(self.w, f"{praefix}{self.zaehler}", *r)))
        return aus


class TestKennzahlen(VergleicheTest):
    def test_zaehler_und_treffsicherheit_je_lauf(self):
        a1, a2 = (v.kennzahlen_lauf(l) for l in self.laeufe(A1, A2))
        self.assertEqual(a1["zaehler"], {"richtig": 2, "teilweise": 1, "falsch": 2, "unsicher": 1, "unparsebar": 0})
        self.assertEqual(a2["zaehler"], {"richtig": 1, "teilweise": 2, "falsch": 2, "unsicher": 1, "unparsebar": 0})
        self.assertEqual((a1["treffsicherheit"]["zaehler"], a1["treffsicherheit"]["nenner"]), (2, 5))
        self.assertAlmostEqual(a1["treffsicherheit"]["quote"], 0.4)
        self.assertEqual(a2["treffsicherheit"]["nenner"], 5)
        self.assertAlmostEqual(a2["treffsicherheit"]["quote"], 0.2)

    def test_nenner_ohne_unsichere_null_gibt_keine_quote(self):
        (l,) = self.laeufe((["unsicher", "unsicher"], [1, 1]))
        t = v.kennzahlen_lauf(l)["treffsicherheit"]
        self.assertEqual((t["zaehler"], t["nenner"], t["quote"]), (0, 0, None))

    def test_unparsebar_bleibt_im_nenner(self):
        (l,) = self.laeufe((["richtig", "unparsebar", "unsicher", "falsch"], [1, 1, 1, 1]))
        t = v.kennzahlen_lauf(l)["treffsicherheit"]
        self.assertEqual((t["zaehler"], t["nenner"]), (1, 3))

    def test_laufzeit_typisch_ist_median_und_maximum_wird_gezeigt(self):
        a1, a2 = self.laeufe(A1, A2)
        z = v.kennzahlen_lauf(a1)["zeit"]
        self.assertEqual((z["median"], z["max"]), (3.5, 60))      # Mittelwert waere 12.5
        s = v.setting_kennzahlen("A", [a1, a2])["zeit"]
        # gepoolt: 12 Werte, sieben davon 1 -> Median 1; Mittelwert waere 80/12
        self.assertEqual((s["n"], s["median"], s["max"]), (12, 1, 60))

    def test_unbekanntes_urteil_bricht_ab(self):
        (l,) = self.laeufe((["vielleicht"], [1]))
        with self.assertRaises(v.VergleichFehler):
            v.kennzahlen_lauf(l)


class TestStabilUndGleichgerichtet(VergleicheTest):
    def test_stabil_nur_wenn_alle_wiederholungen_gleich(self):
        richtig, falsch = v.stabil(self.laeufe(A1, A2))
        # Frage 1 immer richtig; Frage 3 immer falsch. Frage 2 (richtig/falsch) und 4 (falsch/teilweise) nicht.
        self.assertEqual(richtig, [(S, 1)])
        self.assertEqual(falsch, [(S, 3)])

    def test_gleichgerichtet_verlangt_jeden_lauf_besser_als_jeden_basislauf(self):
        a = self.laeufe(A1, A2, praefix="a")
        b = self.laeufe(B1, B2, praefix="b")
        besser, schlechter = v.gleichgerichtet(a, b)
        # Frage 3: A (falsch, falsch) -> B (richtig, teilweise): verbessert.
        # Frage 5: A (unsicher, unsicher) -> B (falsch, falsch): verschlechtert.
        # Nicht gezaehlt: 2 (A schwankt richtig/falsch), 4 (A falsch/teilweise gegen B teilweise/teilweise),
        # 6 (B schwankt teilweise/falsch), 1 (unveraendert).
        self.assertEqual(besser, [(S, 3)])
        self.assertEqual(schlechter, [(S, 5)])

    def test_unparsebar_hat_keine_richtung(self):
        a = self.laeufe((["falsch"], [1]), (["falsch"], [1]), praefix="a")
        b = self.laeufe((["richtig"], [1]), (["unparsebar"], [1]), praefix="b")
        self.assertEqual(v.gleichgerichtet(a, b), ([], []))

    def test_vergleich_mit_einem_lauf_je_setting_macht_keine_aussage(self):
        a = self.laeufe(A1, praefix="a")
        b = self.laeufe(B1, praefix="b")
        erg = v.vergleiche({"A": a, "B": b})
        self.assertIsNone(erg["paare"]["B"])
        self.assertIn("keine Aussage", v.formatiere(erg))

    def test_vergleiche_liefert_paare_und_basis(self):
        erg = v.vergleiche({"A": self.laeufe(A1, A2, praefix="a"), "B": self.laeufe(B1, B2, praefix="b")})
        self.assertEqual(erg["basis"], "A")
        self.assertEqual(erg["paare"]["B"], ([(S, 3)], [(S, 5)]))
        erg = v.vergleiche({"A": self.laeufe(A1, A2, praefix="a"), "B": self.laeufe(B1, B2, praefix="b")},
                           basis_name="B")
        self.assertEqual(erg["paare"]["A"], ([(S, 5)], [(S, 3)]))

    def test_setting_mit_verschiedenen_fragen_bricht_ab(self):
        a = self.laeufe(A1, (["richtig"] * 5, [1] * 5))
        with self.assertRaises(v.VergleichFehler):
            v.setting_kennzahlen("A", a)

    def test_min_max_der_treffsicherheit_ohne_mittelwert(self):
        s = v.setting_kennzahlen("A", self.laeufe(A1, A2))
        self.assertAlmostEqual(s["treffsicherheit_min"], 0.2)
        self.assertAlmostEqual(s["treffsicherheit_max"], 0.4)
        self.assertNotIn("treffsicherheit_mittel", s)


class TestAusgabeUndCli(VergleicheTest):
    def test_ausgabe_nennt_median_und_maximum(self):
        text = v.formatiere(v.vergleiche({"A": self.laeufe(A1, A2)}))
        self.assertIn("typisch (Median) 1.0s, Maximum 60.0s", text)
        self.assertIn("Minimum 0.200, Maximum 0.400", text)
        self.assertIn("stabil richtig: 1   stabil falsch: 1", text)

    def test_parse_argumente(self):
        self.assertEqual(v.parse_argumente(["A=x,y", "/pfad/zu/lauf-b"]),
                         {"A": ["x", "y"], "lauf-b": ["/pfad/zu/lauf-b"]})
        with self.assertRaises(v.VergleichFehler):
            v.parse_argumente(["A=x", "A=y"])

    def test_main_und_fehlende_urteile(self):
        for n, r in (("a1", A1), ("a2", A2), ("b1", B1), ("b2", B2)):
            schreibe_lauf(self.w, n, *r)
        p = lambda n: os.path.join(self.w, n)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = v.main([f"A={p('a1')},{p('a2')}", f"B={p('b1')},{p('b2')}"])
        self.assertEqual(rc, 0, err.getvalue())
        self.assertIn(f"verbessert: 1   verschlechtert: 1", out.getvalue())
        os.makedirs(p("leer"))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(v.main([p("leer")]), 1)
        self.assertIn("bewerte.py", err.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
