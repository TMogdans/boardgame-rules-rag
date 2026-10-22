#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zuordnung der pdfplumber-Zeichen zu den Extraktionszeilen (Spec mehrbuch-bestand, REQ-MB-29) --
mit echtem pdfplumber und einem im Test per reportlab erzeugten PDF (reine Testabhaengigkeiten,
von der Spec in der Testumgebung vorausgesetzt).

    python test_pdf_schrift.py

Spec-PR: jeder Test einzeln @unittest.skip("devloop: REQ-MB-29 ..."), [REQ-MB-29] im Docstring.

Vom Test erwartete Schnittstelle:
  einlesen.ordne_schrift_zu(pdf_pfad, seiten, rand=None) -> {seite: [zeile]}
      seiten: {physische Seite: [{"text", "klasse", "x0", "x1", "oben", "unten"}]}  -- Lage der
              Extraktionszeile in PDF-Punkten, Ursprung OBEN links (wie pdfplumber top/bottom)
      je Zeile zusaetzlich: "schrift": {"groesse", "fett", "laufweite"} oder None (keine eindeutige
              Mehrheit), "oben"/"unten" aus den zugeordneten Zeichen, "im_rand": bool (nur mit rand)
      rand: {"kopf": pt, "fuss": pt}; im Rand, wenn der vertikale Mittelpunkt darin liegt
"""
import importlib
import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis

BREITE, HOEHE = 600, 800
X, Y = ("Helvetica-Bold", 14), ("Helvetica", 10)          # Schrift X (14 pt fett), Schrift Y (10 pt)


def einlesen():
    return importlib.import_module("einlesen")


def baue_pdf(pfad):
    """Seite 1: rein, gemischt, Gleichstand, zwei Spalten. Seite 2: eine Zeile oben (Randfall).
    Rueckgabe: {seite: [Extraktionszeile mit Lage]} -- die Lage so, wie ein Layout-Extraktor sie
    liefern wuerde (Kasten um den Text, kein Zeichenwissen)."""
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase.pdfmetrics import stringWidth
    c = canvas.Canvas(pfad, pagesize=(BREITE, HOEHE))
    seiten = {1: [], 2: []}

    def zeile(seite, x, grundlinie, teile, name, klasse="text"):
        t = c.beginText(x, HOEHE - grundlinie)
        breite, groesste = 0.0, 0
        for text, (font, size) in teile:
            t.setFont(font, size)
            t.textOut(text)
            breite += stringWidth(text, font, size)
            groesste = max(groesste, size)
        c.drawText(t)
        seiten[seite].append({"text": "".join(text for text, _ in teile), "klasse": klasse, "name": name,
                              "x0": x - 1, "x1": x + breite + 1, "oben": grundlinie - groesste, "unten": grundlinie + 3})

    zeile(1, 50, 100, [("Ganz fett", X)], "rein", "section_header")
    zeile(1, 50, 160, [("Mehrheitfett", X), (" kl", Y)], "gemischt")
    zeile(1, 50, 220, [("AAAAA", X), (" bbbbb", Y)], "gleichstand")
    zeile(1, 50, 280, [("Links fett", X)], "links")
    zeile(1, 320, 280, [("rechts duenn", Y)], "rechts")
    c.showPage()
    zeile(2, 50, 40, [("Kolumnentitel", X)], "randzeile", "section_header")
    c.showPage()
    c.save()
    return seiten


def mitte_aus_zeichen(pfad, seite, text):
    """Vertikaler Mittelpunkt der Zeichen einer Zeile -- gemessen mit pdfplumber selbst, um den Rand
    auf +-1 pt um die Zeile zu legen (Kalibrierung der Testdaten, nicht der Pruefling)."""
    import pdfplumber
    with pdfplumber.open(pfad) as pdf:
        zeichen = [ch for ch in pdf.pages[seite - 1].chars if not ch["text"].isspace()]
    assert "".join(ch["text"] for ch in zeichen) == text.replace(" ", ""), zeichen
    return (min(ch["top"] for ch in zeichen) + max(ch["bottom"] for ch in zeichen)) / 2


class SchriftTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pdf = os.path.join(self.tmp.name, "schrift.pdf")
        self.seiten = baue_pdf(self.pdf)

    def zugeordnet(self, rand=None):
        eingabe = {s: [{k: v for k, v in z.items() if k != "name"} for z in zeilen] for s, zeilen in self.seiten.items()}
        aus = einlesen().ordne_schrift_zu(self.pdf, eingabe, rand=rand)
        return {soll["name"]: ist for s in self.seiten for soll, ist in zip(self.seiten[s], aus[s])}

    def assertSchrift(self, schrift, soll):
        font, size = soll
        self.assertIsNotNone(schrift)
        self.assertAlmostEqual(schrift["groesse"], size, delta=0.1)
        self.assertEqual(schrift["fett"], font.endswith("Bold"))

    def test_req_mb_29_reine_und_gemischte_zeile(self):
        """[REQ-MB-29] Zeile ganz in X -> X; gemischte Zeile mit Mehrheit X und kuerzerem Teil in Y -> X."""
        z = self.zugeordnet()
        self.assertSchrift(z["rein"]["schrift"], X)
        self.assertSchrift(z["gemischt"]["schrift"], X)
        self.assertEqual([zeile["text"] for zeile in z.values()][:2], ["Ganz fett", "Mehrheitfett kl"])   # Text unveraendert

    def test_req_mb_29_gleichstand_ohne_schrift(self):
        """[REQ-MB-29] Gleich viele Zeichen (ohne Leerzeichen) in X und Y -> keine zugeordnete Schrift."""
        self.assertIsNone(self.zugeordnet()["gleichstand"].get("schrift"))

    def test_req_mb_29_zwei_spalten_gleicher_hoehe(self):
        """[REQ-MB-29] Zwei Spalten mit gleich hohen Zeilen: links X, rechts Y -- Zeichen der Nachbarspalte zaehlen nicht."""
        z = self.zugeordnet()
        self.assertSchrift(z["links"]["schrift"], X)
        self.assertSchrift(z["rechts"]["schrift"], Y)

    def test_req_mb_29_kopfrand_plus_minus_ein_punkt(self):
        """[REQ-MB-29] Zeile im deklarierten Kopfrand -> als Rand erkannt; dieselbe Zeile 1 pt ausserhalb -> nicht."""
        mitte = mitte_aus_zeichen(self.pdf, 2, "Kolumnentitel")
        drin = self.zugeordnet(rand={"kopf": mitte + 1})["randzeile"]
        self.assertTrue(drin["im_rand"])
        self.assertAlmostEqual((drin["oben"] + drin["unten"]) / 2, mitte, delta=0.01)   # Lage aus den Zeichen
        self.assertFalse(self.zugeordnet(rand={"kopf": mitte - 1})["randzeile"]["im_rand"])
        self.assertFalse(self.zugeordnet(rand={"kopf": mitte + 1})["rein"]["im_rand"])
        fuss = HOEHE - mitte                       # Fussrand von unten gemessen: die Zeile oben ist nie darin
        self.assertFalse(self.zugeordnet(rand={"fuss": fuss - 1})["randzeile"]["im_rand"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
