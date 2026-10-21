#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zerschneiden nach Ueberschriften (Spec mehrbuch-bestand, Abschnitt D: REQ-MB-14/-15/-16, dazu
REQ-MB-20 auf Haeppchen-Ebene) -- vom Einlesen bis zum Index, ohne Ollama.

    python test_zerschneiden.py

Spec-PR: jeder Test einzeln @unittest.skip("devloop: REQ-MB-<n> ..."), [REQ-MB-<n>] im Docstring.

Kette im Test: einlesen.lies_buch_ein (synthetische Seitenzeilen + Lesezeichen) -> Buchdatei
-> rag.aktualisiere_index (CHUNK_SIZE/CHUNK_OVERLAP) -> rag.lade_spiel. Sollwerte kommen aus
einlesen.baue_abschnitte auf derselben Eingabe und aus rag.zerteile -- "zeichengenau wie heute".

Vom Test erwartete Schnittstellen (zusaetzlich zu test_mehrbuch.py / test_einlesen_reparatur.py):
  rag.titelvorsatz(abschnittspfad) -> str   Vorsatz, mit dem jeder Haeppchentext beginnt;
      Haeppchentext == titelvorsatz(pfad) + Stueck aus rag.zerteile(Abschnittstext)
  Chunk aus lade_spiel: "seiten" = alle (gedruckten) Seiten, ueber die sein Text laeuft;
      "seite" = die erste davon
  Ausgabe von rag.aktualisiere_index: je Buch eine Zeile mit buch_id und Haeppchenzahl
"""
import contextlib
import importlib
import io
import os
import re
import sys
import unittest
from unittest import mock

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402
import test_mehrbuch as mb  # noqa: E402
from test_einlesen_reparatur import z, eintrag, LAYOUT_SEITEN, LAYOUT_LISTE  # noqa: E402


def einlesen():
    return importlib.import_module("einlesen")


class ZerschneideTest(mb.BestandTest):
    def lies_ein(self, seiten, liste, bid="nord", layout=None, titel="Buch Nord", weitere=()):
        """Buch deklarieren und einlesen; Rueckgabe: Sollabschnitte aus baue_abschnitte (gleiche Eingabe)."""
        extra = {"layout": layout} if layout else {}
        buecher = [mb.buch(bid, titel, "alpha", ueberschriften={"quelle": "lesezeichen"},
                           seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True, **extra)]
        buecher += [mb.buch(b, t, "alpha", ueberschriften={"quelle": "lesezeichen"},
                            seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True) for b, t, _, _ in weitere]
        self.bestand(buecher)
        for b, _, s, l in weitere:
            einlesen().lies_buch_ein(mb.SID, b, s, lesezeichen=l)
        einlesen().lies_buch_ein(mb.SID, bid, seiten, lesezeichen=liste)
        return einlesen().baue_abschnitte(seiten, liste, layout=layout, sprache="de", reparatur=True,
                                          protokoll=einlesen().Protokoll())

    def chunks(self, size, overlap, ausgabe=None):
        with mock.patch.multiple(rag, CHUNK_SIZE=size, CHUNK_OVERLAP=overlap):
            self.baue(ausgabe=ausgabe)
            chunks, _ = rag.lade_spiel(self.oeffne(), mb.SID)
        return chunks

    def je_pfad(self, chunks, bid="nord"):
        out = {}
        for c in chunks:
            if c["buch_id"] == bid:
                out.setdefault(tuple(c["abschnittspfad"]), []).append(c)
        return out

    def stueck(self, c):
        vorsatz = rag.titelvorsatz(c["abschnittspfad"])
        self.assertTrue(c["text"].startswith(vorsatz), (vorsatz, c["text"]))
        return c["text"][len(vorsatz):]


def werte(marke, n):
    """Synthetischer Werteblock ohne Achsen- und Titelwoerter."""
    return [z(f"{marke} Stufe {i} Probe {i + 3} Schwelle {2 * i}.") for i in range(n)]


BUCH_SEITEN = {1: [z("Kapitel", "section_header"), z("Kurze Einleitung kap.")] + werte("ka", 3),
               2: [z("Erster Teil", "section_header")] + werte("ea", 6),
               3: [z("Zweiter Teil", "section_header")] + werte("zb", 2) +
                  [z("Dritter Teil", "section_header")] + werte("dc", 9)}
BUCH_LISTE = [eintrag("Kapitel", 1, 1), eintrag("Erster Teil", 2, 2), eintrag("Zweiter Teil", 3, 2),
              eintrag("Dritter Teil", 3, 2)]


class TestAbschnittsgrenzen(ZerschneideTest):
    @unittest.skip("devloop: REQ-MB-14 noch nicht implementiert")
    def test_req_mb_14_kein_haeppchen_ueber_eine_abschnittsgrenze(self):
        """[REQ-MB-14] Jedes Haeppchen (ohne Vorsatz) ist Teilstring genau eines Abschnitts; auch die Ueberlappung nicht darueber."""
        abschnitte = self.lies_ein(BUCH_SEITEN, BUCH_LISTE)
        self.assertEqual([a["abschnittspfad"] for a in abschnitte],
                         [["Kapitel"], ["Kapitel", "Erster Teil"], ["Kapitel", "Zweiter Teil"],
                          ["Kapitel", "Dritter Teil"]])
        chunks = self.chunks(60, 20)
        self.assertGreater(len(chunks), len(abschnitte))          # es wird wirklich geteilt
        for c in chunks:
            with self.subTest(text=c["text"]):
                st = self.stueck(c)
                eigener = next(a for a in abschnitte if a["abschnittspfad"] == c["abschnittspfad"])
                self.assertIn(st, eigener["text"])                 # reicht nicht ueber die Grenze
                if len(st) >= 20:                                  # kurze Reststuecke ("4.") sind mehrdeutig
                    self.assertEqual([a["abschnittspfad"] for a in abschnitte if st in a["text"]],
                                     [c["abschnittspfad"]], st)

    @unittest.skip("devloop: REQ-MB-14 noch nicht implementiert")
    def test_req_mb_14_innerhalb_zeichengenau_wie_zerteile(self):
        """[REQ-MB-14] Innerhalb eines Abschnitts: Stuecke = rag.zerteile(Abschnittstext) mit CHUNK_SIZE/OVERLAP, ohne Vorsatz gezaehlt."""
        abschnitte = self.lies_ein(BUCH_SEITEN, BUCH_LISTE)
        je = self.je_pfad(self.chunks(60, 20))
        for a in abschnitte:
            with self.subTest(pfad=a["abschnittspfad"]):
                self.assertEqual([self.stueck(c) for c in je[tuple(a["abschnittspfad"])]],
                                 rag.zerteile(a["text"], 60, 20))

    @unittest.skip("devloop: REQ-MB-14 noch nicht implementiert")
    def test_req_mb_14_laenge_chunk_size_plus_eins_ergibt_zwei(self):
        """[REQ-MB-14] Abschnitt der Laenge CHUNK_SIZE + 1 (ohne Vorsatz) -> genau 2 Haeppchen, gleich zerteile."""
        abschnitte = self.lies_ein(BUCH_SEITEN, BUCH_LISTE)
        dritter = next(a for a in abschnitte if a["abschnittspfad"][-1] == "Dritter Teil")
        n = len(dritter["text"])
        self.assertGreater(n, 40)
        je = self.je_pfad(self.chunks(n - 1, 10))
        stuecke = [self.stueck(c) for c in je[tuple(dritter["abschnittspfad"])]]
        self.assertEqual(len(stuecke), 2)
        self.assertEqual(stuecke, rag.zerteile(dritter["text"], n - 1, 10))

    @unittest.skip("devloop: REQ-MB-14 noch nicht implementiert")
    def test_req_mb_14_kurze_geschwister_nicht_zusammengelegt(self):
        """[REQ-MB-14] Zwei Geschwister mit je ~50 Zeichen -> 2 Haeppchen (keine Zusammenlegung), Text unveraendert."""
        seiten = {1: [z("Haupt", "section_header"), z("Vorwort zum Hauptteil."),
                      z("Links", "section_header"), z("Fuenfzig Zeichen links, ungefaehr so lang wie hier."),
                      z("Rechts", "section_header"), z("Fuenfzig Zeichen rechts, ungefaehr so lang wie da.")]}
        liste = [eintrag("Haupt", 1, 1), eintrag("Links", 1, 2), eintrag("Rechts", 1, 2)]
        abschnitte = self.lies_ein(seiten, liste)
        je = self.je_pfad(self.chunks(400, 150))
        for pfad in (("Haupt", "Links"), ("Haupt", "Rechts")):
            with self.subTest(pfad=pfad):
                self.assertEqual(len(je[pfad]), 1)
                self.assertEqual(self.stueck(je[pfad][0]),
                                 next(a["text"] for a in abschnitte if tuple(a["abschnittspfad"]) == pfad))
        self.assertEqual(sum(len(v) for v in je.values()), 3)

    @unittest.skip("devloop: REQ-MB-14 noch nicht implementiert")
    def test_req_mb_14_protokoll_haeppchenzahl_je_buch(self):
        """[REQ-MB-14] Die Ausgabe des Index-Laufs weist die Haeppchenzahl je Buch aus."""
        kurz = {1: [z("Nur eins", "section_header"), z("Ein einziger kurzer Satz.")]}
        self.lies_ein(BUCH_SEITEN, BUCH_LISTE,
                      weitere=[("sued", "Buch Sued", kurz, [eintrag("Nur eins", 1)])])
        meldungen = []
        chunks = self.chunks(60, 20, ausgabe=meldungen.append)
        zahl = {b: sum(1 for c in chunks if c["buch_id"] == b) for b in ("nord", "sued")}
        self.assertEqual(zahl["sued"], 1)
        self.assertGreater(zahl["nord"], 4)
        for b, n in zahl.items():
            with self.subTest(buch=b):
                muster = re.compile(rf"(?<![\w-]){b}(?![\w-]).*(?<!\d){n}(?!\d)")
                self.assertTrue(any(muster.search(m) for m in meldungen), meldungen)


class TestTitelTraegtMit(ZerschneideTest):
    SEITEN = {1: [z("Tiere", "section_header"), z("Einleitung zu den Tieren.")],
              2: [z("Grauer Wolf", "section_header")] + werte("gw", 8),
              3: [z("Roter Fuchs", "section_header")] + werte("rf", 3)}
    LISTE = [eintrag("Tiere", 1, 1), eintrag("Grauer Wolf", 2, 2), eintrag("Roter Fuchs", 3, 2)]

    @unittest.skip("devloop: REQ-MB-15 noch nicht implementiert")
    def test_req_mb_15_alle_drei_haeppchen_beginnen_mit_dem_pfad(self):
        """[REQ-MB-15] "Grauer Wolf" ueber drei Haeppchen: eingebettet und im Prompt beginnen alle mit dem Pfad; BM25 findet alle drei."""
        abschnitte = self.lies_ein(self.SEITEN, self.LISTE)
        wolf = next(a for a in abschnitte if a["abschnittspfad"] == ["Tiere", "Grauer Wolf"])
        size = next(s for s in range(30, len(wolf["text"])) if len(rag.zerteile(wolf["text"], s, 10)) == 3)
        vorher = len(self.netz.eingebettet)
        chunks = self.chunks(size, 10)
        eingebettet = self.netz.eingebettet[vorher:]
        wolf_chunks = self.je_pfad(chunks)[("Tiere", "Grauer Wolf")]
        self.assertEqual(len(wolf_chunks), 3)
        vorsatz = rag.titelvorsatz(["Tiere", "Grauer Wolf"])
        self.assertLess(vorsatz.index("Tiere"), vorsatz.index("Grauer Wolf"))
        for i, c in enumerate(wolf_chunks):
            with self.subTest(haeppchen=i):
                self.assertTrue(c["text"].startswith(vorsatz))
                self.assertIn(c["text"], eingebettet)                 # so eingebettet, wie es im Prompt steht
                if i:
                    self.assertNotIn("Grauer", self.stueck(c))        # Mitte/Ende: Titel nur durch den Vorsatz
        with mock.patch.multiple(rag, CHUNK_SIZE=size, CHUNK_OVERLAP=10):
            con = self.oeffne()
            hits = rag.retrieve("Grauer Wolf", k=len(chunks), spiel_id=mb.SID, index=con)
            kontext = rag.baue_kontext(hits)
            for c in wolf_chunks:
                self.assertIn(c["text"], kontext)
            folge = rag.bm25_rangfolge(con, "Grauer Wolf", chunks, len(chunks))
        gefunden = {tuple(chunks[i]["abschnittspfad"]) + (chunks[i]["text"],) for i in folge}
        self.assertLessEqual({("Tiere", "Grauer Wolf", c["text"]) for c in wolf_chunks}, gefunden)
        self.assertFalse(any(p[:2] == ("Tiere", "Roter Fuchs") for p in gefunden))


class TestSeitenUeberGrenzen(ZerschneideTest):
    SEITEN = {4: [z("Lange Regel", "section_header"),
                  z("Vier eins vier zwei vier drei vier vier vier fuenfmal nicht vier sechs vier sieben vier acht.")],
              5: [z("Fuenf am Ende."), z("Fuenf zwei.")]}
    LISTE = [eintrag("Lange Regel", 4, 1)]

    @unittest.skip("devloop: REQ-MB-16 noch nicht implementiert")
    def test_req_mb_16_haeppchen_traegt_alle_seiten_fundstelle_die_erste(self):
        """[REQ-MB-16] Abschnitt von Seite 4 nach 5: Haeppchen ueber die Grenze traegt [4, 5], Fundstelle nennt 4, Erwartung 5 trifft."""
        (abschnitt,) = self.lies_ein(self.SEITEN, self.LISTE)
        self.assertEqual(abschnitt["seiten"], [4, 5])
        text = abschnitt["text"]
        grenze = text.index("Fuenf am Ende.")
        size = grenze - 3
        self.assertEqual(len(rag.zerteile(text, size, 10)), 2)      # 1. nur Seite 4, 2. ueber die Grenze
        chunks = self.chunks(size, 10)
        erstes, zweites = self.je_pfad(chunks)[("Lange Regel",)]
        self.assertEqual((erstes["seiten"], erstes["seite"]), ([4], 4))
        self.assertEqual((zweites["seiten"], zweites["seite"]), ([4, 5], 4))
        f = rag.fundstelle(zweites)
        self.assertRegex(f, r"(?<!\d)4(?!\d)")
        self.assertNotRegex(f, r"(?<!\d)5(?!\d)")
        self.schreibe_golden([
            {"id": 1, "frage": "Lange Regel", "typ": "fakt", "erwartet": "-", "keywords": [],
             "seiten": [{"buch_id": "nord", "seite": 5}]},
            {"id": 2, "frage": "Lange Regel", "typ": "fakt", "erwartet": "-", "keywords": [],
             "seiten": [{"buch_id": "nord", "seite": 6}]}])
        with mock.patch.multiple(rag, CHUNK_SIZE=size, CHUNK_OVERLAP=10), \
                mock.patch.object(rag, "answer", lambda *a: "x"), contextlib.redirect_stdout(io.StringIO()):
            saetze = rag.cmd_eval_spiele([mb.SID])
        self.assertEqual([s["kategorie"] for s in saetze], [rag.KAT_GETROFFEN, rag.KAT_VERFEHLT])


class TestLayoutImIndex(ZerschneideTest):
    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_haeppchen_der_unterabschnitte_beginnen_mit_ihrem_namen(self):
        """[REQ-MB-20] Im Index: Haeppchen unter K1 > U1 > Alpha / Beta beginnen mit ihrem Pfad; "Gamma" steht in Beta."""
        self.lies_ein(LAYOUT_SEITEN, LAYOUT_LISTE, layout={"klasse": "section_header"})
        je = self.je_pfad(self.chunks(400, 150))
        self.assertEqual(set(je), {("K1",), ("K1", "U1"), ("K1", "U1", "Alpha"), ("K1", "U1", "Beta")})
        for name in ("Alpha", "Beta"):
            pfad = ("K1", "U1", name)
            vorsatz = rag.titelvorsatz(list(pfad))
            self.assertIn(name, vorsatz)
            for c in je[pfad]:
                self.assertTrue(c["text"].startswith(vorsatz), c["text"])
        self.assertIn("Text nach Gamma.", "".join(c["text"] for c in je[("K1", "U1", "Beta")]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
