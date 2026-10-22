#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Einlesen-Reparatur (Spec mehrbuch-bestand, Abschnitt C + REQ-MB-20/-22): Trennungen,
Ueberschriften-Liste mit unscharfem Abgleich, nicht gefundene Eintraege, Layout-Ueberschriften,
gedruckte Seite.

    python test_einlesen_reparatur.py

Spec-PR: jeder Test einzeln @unittest.skip("devloop: REQ-MB-<n> ..."), [REQ-MB-<n>] im Docstring.
Nur synthetische Seitentexte, kein PDF, kein Docling (REQ-MB-17/-18).

Vom Test erwartete Schnittstellen -- neues Modul einlesen.py, ohne docling importierbar
(reine Funktionen; der Docling-Adapter liefert nur die Zeilen):
  einlesen.Protokoll()
      .trennungen_zusammengefuegt: int   .strich_behalten: int           (REQ-MB-11)
      .gefunden / .nicht_gefunden / .mehrdeutig: [(titel, seite), ...]   (REQ-MB-12/-13)
      .layout_ueberschriften: {tuple(abschnittspfad des Listenabschnitts): Anzahl}  (REQ-MB-20)
  einlesen.repariere_trennungen(text, sprache="de", konjunktionen=None, protokoll=None) -> str
      text mit "\\n" als Zeilenumbruch und U+00AD; konjunktionen=None -> Liste der Sprache
  einlesen.baue_abschnitte(seiten, liste=None, layout=None, sprache="de", reparatur=True,
                           protokoll=None) -> [{"abschnittspfad": [...], "text": str, "seiten": [...]}]
      seiten: {physische Seite: [{"text": str, "klasse": <Docling-Layout-Klasse>}, ...]}
      liste:  [{"titel": str, "ebene": int, "seite": physische Seite}, ...]
      layout: deklarierte Merkmale, z. B. {"klasse": "section_header", "hoechstlaenge": 40}
  einlesen.lies_buch_ein(spiel_id, buch_id, seiten, lesezeichen=None, labels=None,
                         data_dir=None, ueberschreiben=False) -> Protokoll
      liest die Buchdeklaration aus spiel.json ("ueberschriften", "layout", "seitenzahlen",
      "reparatur", "sprache") und schreibt data/<spiel_id>/buecher/<buch_id>/knowledge.jsonl;
      labels: PDF-Seitenlabel je physischer Seite (labels[0] = Seite 1)
  Buchdeklaration: "ueberschriften": {"quelle": "lesezeichen"} |
                                     {"quelle": "inhaltsverzeichnis", "eintraege": [{titel, ebene, seite(gedruckt)}]}
                   "seitenzahlen": {"quelle": "labels", "kontrollpunkte": {"<physisch>": gedruckt}} |
                                   {"quelle": "versatz", "versatz": n}
  Chunk aus lade_spiel: "seite" (gedruckt oder None), "seite_pdf" (physisch); rag.fundstelle(chunk)
Fassung 4:
  einlesen.baue_abschnitte(..., vorspann="Vorspann")      Text vor dem 1. Listeneintrag (REQ-MB-25);
      Buchdeklaration "vorspann": <Name> setzt ihn fuer lies_buch_ein
  einlesen.lies_buch_ein(..., pdf=None, docling_version=None, vorabmessung=None)
      pdf: Lesezeichen/Labels aus der PDF-Datei selbst (REQ-MB-24), wenn deklariert
      docling_version: Einlesen mit Docling (vom Docling-Adapter injiziert) -> Vergleich mit
          "docling_version" in vorabmessung (Pfad, Default .specify/specs/mehrbuch-bestand/
          vorabmessung.json); Protokoll.docling_version nennt die verwendete Version (REQ-MB-23)
  einlesen.lesezeichen_aus_pdf(pfad) -> [{"titel", "ebene", "seite"(physisch)}]  in Dokumentreihenfolge
  einlesen.seitenlabels_aus_pdf(pfad) -> [label je physischer Seite]                (REQ-MB-24)
Fassung 6:
  Zeile: {"text", "klasse", "schrift": {"groesse", "fett", "laufweite"} | fehlt/None (keine Schrift),
          "oben", "unten" (PDF-Punkte ab OBERER Seitenkante, wie pdfplumber top/bottom)}
  Bild-Element in den Zeilen einer Seite: nicht -- Bilder loest der Docling-Adapter auf (REQ-MB-27)
  einlesen.baue_abschnitte(..., rand=None, seitenhoehe=None)
      rand: {"kopf": pt, "fuss": pt} (REQ-MB-12/-20/-28); seitenhoehe: pt (fuer den Fussrand)
  layout: {"klasse": <Ueberschriften-Klasse fuer den Rueckfall>, "veto": [<Klassen>] (ergaenzt den
           Default table/caption/page_header/page_footer), "stufen": [{"groesse": [von, bis],
           "fett": bool, "laufweite": [von, bis]}, ...] (Stufe 1 zuerst), "hoechstlaenge": n}
  Buchdeklaration: "layout" wie oben, "rand" wie oben
  Protokoll zusaetzlich: .layout_je_stufe {n: Anzahl}, .rueckfaelle, .rand_verhindert,
      .veto_verhindert (REQ-MB-20), .randzeilen (REQ-MB-28), .aus_bildern (REQ-MB-27),
      .pdfplumber_version (REQ-MB-23)
  einlesen.lies_buch_ein(..., pdfplumber_version=None, seitenhoehe=None)
      pdfplumber_version: Einlesen mit Schriftinfo (vom Adapter injiziert) -> Vergleich mit
      "pdfplumber_version" in vorabmessung, sofern das Buch Schriftstufen deklariert
  einlesen.zeilen_aus_docling(doc, protokoll=None) -> {seite: [zeile]}            (REQ-MB-27)
      doc wie DoclingDocument: iterate_items(traverse_pictures=...) -> (item, ebene); item.label,
      item.text, item.prov[0].page_no; Text-Kinder eines Bild-Elements folgen ihm bei
      traverse_pictures=True
Fassung 7:
  Docling-Weg = einlesen.lies_pdf_ein(spiel_id, buch_id, pdf=..., ausgabe=...) mit der Docling-Attrappe
      (docling_attrappe.py); Versionen wie im Messergebnis des Spec-Ordners (REQ-MB-11, -32)
  Protokoll.binnen_grossbuchstabe / .strichrest = {"anzahl": n, "seiten": [gedruckt, sonst physisch]} (REQ-MB-32)
  (REQ-MB-31 in Fassung 9 zurueckgezogen: keine Tests, kein Zaehler "umsortiert")
  Schemafehler der Layout-/Rand-Deklaration -> KonfigFehler aus lies_buch_ein, Meldung nennt den Schluessel (REQ-MB-34)
"""
import importlib
import json
import os
import unicodedata
from unittest import mock
import sys
import unittest

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402
import test_mehrbuch as mb  # noqa: E402  -- Bestand-Hilfen (Attrappen, spiel.json, Index)

SHY = "­"


def einlesen():
    """Spaet importiert: das Modul entsteht erst mit der Implementierung."""
    return importlib.import_module("einlesen")


def z(text, klasse="text", schrift=None, oben=None, hoehe=10):
    """Extraktionszeile; schrift None = keine zugeordnete Schrift; oben = Abstand von der oberen Kante."""
    d = {"text": text, "klasse": klasse}
    if schrift is not None:
        d["schrift"] = dict(schrift)
    if oben is not None:
        d["oben"], d["unten"] = oben, oben + hoehe
    return d


S1 = {"groesse": 14.0, "fett": True, "laufweite": 0.0}       # Stufe 1 (z. B. Talentname)
S2 = {"groesse": 12.0, "fett": True, "laufweite": 0.0}       # Stufe 2 (Zwischenueberschrift)
FT = {"groesse": 10.0, "fett": False, "laufweite": 0.0}      # Fliesstext
STUFEN = [{"groesse": [13.5, 14.5], "fett": True}, {"groesse": [11.5, 12.5], "fett": True}]
SEITENHOEHE = 800


def eintrag(titel, seite, ebene=1):
    return {"titel": titel, "ebene": ebene, "seite": seite}


def nach_pfad(abschnitte):
    return {tuple(a["abschnittspfad"]): a for a in abschnitte}


# ===================================================================================
# REQ-MB-11: Trennungen
# ===================================================================================
TRENNUNGEN = [  # (Eingabe, Ergebnis, Fall) -- Tabelle der Spec, woertlich
    ("Akti-\nonswürfel", "Aktionswürfel", "Trennung, Kleinbuchstabe folgt"),
    (f"Bewusstlosigkeits{SHY}schwelle", "Bewusstlosigkeitsschwelle", "weicher Trennstrich im Wort"),
    (f"Bewusstlosigkeits{SHY}\nschwelle", "Bewusstlosigkeitsschwelle", "weicher Trennstrich am Zeilenende"),
    ("Zwerg-\nKrieger", "Zwerg-Krieger", "echter Bindestrich, Grossbuchstabe folgt"),
    ("ED4-\nRegeln", "ED4-Regeln", "Bindestrich nach Ziffer"),
    ("Nah-\nund Fernkampf", "Nah- und Fernkampf", "Ergaenzungsstrich vor Konjunktion"),
    ("Stufen/\nAktionswürfel", "Stufen/Aktionswürfel", "Schraegstrich bleibt"),
    ("Schaden - 2", "Schaden - 2", "freistehender Strich bleibt"),
    ("Wurf\nStufe", "Wurf Stufe", "gewoehnlicher Umbruch"),
]


class TestTrennungen(unittest.TestCase):
    @unittest.skip("devloop: REQ-MB-11 noch nicht implementiert")
    def test_req_mb_11_tabelle_der_spec(self):
        """[REQ-MB-11] Jede Zeile der Trennungstabelle liefert genau das Ergebnis der Spec."""
        for eingabe, ergebnis, fall in TRENNUNGEN:
            with self.subTest(fall=fall):
                self.assertEqual(einlesen().repariere_trennungen(eingabe, sprache="de"), ergebnis)

    @unittest.skip("devloop: REQ-MB-11 noch nicht implementiert")
    def test_req_mb_11_protokoll_zaehler_exakt(self):
        """[REQ-MB-11] Protokoll zaehlt zusammengefuegte Trennungen und behaltene Striche exakt (3 und 4)."""
        e = einlesen()
        text = ("Akti-\nonswürfel Bonus-\nwürfel und Ma-\ngie. "          # 3 x zusammengefuegt
                "Zwerg-\nKrieger Elf-\nMagier ED4-\nRegeln Nah-\nund "     # 4 x Strich behalten
                "Fernkampf Wurf\nStufe")                                   # gewoehnlicher Umbruch: kein Zaehler
        p = e.Protokoll()
        self.assertEqual(e.repariere_trennungen(text, sprache="de", protokoll=p),
                         "Aktionswürfel Bonuswürfel und Magie. Zwerg-Krieger Elf-Magier ED4-Regeln Nah- und "
                         "Fernkampf Wurf Stufe")
        self.assertEqual((p.trennungen_zusammengefuegt, p.strich_behalten), (3, 4))
        p2 = e.Protokoll()
        e.repariere_trennungen("Wurf\nStufe Schaden - 2 Stufen/\nAktionswürfel", sprache="de", protokoll=p2)
        self.assertEqual(p2.trennungen_zusammengefuegt, 0)

    @unittest.skip("devloop: REQ-MB-11 noch nicht implementiert")
    def test_req_mb_11_konjunktionsliste_ist_konfiguration(self):
        """[REQ-MB-11] Die Konjunktionsliste kommt aus der Konfiguration: ohne "und" gilt die Trennungsregel."""
        e = einlesen()
        self.assertEqual(e.repariere_trennungen("Nah-\nund Fernkampf", konjunktionen=("und",)), "Nah- und Fernkampf")
        self.assertEqual(e.repariere_trennungen("Nah-\nund Fernkampf", konjunktionen=()), "Nahund Fernkampf")
        self.assertEqual(e.repariere_trennungen("Nah-\noder Fernkampf", konjunktionen=("oder",)),
                         "Nah- oder Fernkampf")


# ===================================================================================
# REQ-MB-12 / REQ-MB-13: Ueberschriften-Liste, unscharfer Abgleich, nicht gefunden
# ===================================================================================
ERSETZT = [  # (Listentitel auf Seite 7, Zeile auf Seite 7, Grund) -- Tabelle der Spec
    ("Bonuswürfel", "Bonusw rfel", "1 Auslassung, k = 1"),
    ("Aktionswürfel", "A ktionswürfel", "nur Leerzeichen"),
    ("Stufen/Aktionswürfel", "Stufen/Aktionsw rfel", "1 Auslassung, k = 2"),
    ("Ätherhaut", "therhaut", "1 Auslassung, k = 1"),
    ("Bonuswürfel", "BONUSWÜRFEL", "nur Gross/Klein"),
]
NICHT_ERSETZT = [  # (Listentitel, Zeile, Seite der Zeile, Grund)
    ("Bonuswürfel", "Bonusw rf l", 7, "2 Auslassungen > k = 1"),
    ("Bonuswürfel", "Bonus", 7, "6 Auslassungen"),
    ("Bonuswürfel", "Bonuswürfel einsetzen …", 7, "Zeile laenger als Titel (Fliesstext)"),
    ("Feuerball", "Feuerwall", 7, "Vertauschung, keine Auslassung"),
    ("Rang", "Rng", 7, "Titel < 6, k = 0"),
    ("Bonuswürfel", "Bonusw rfel", 8, "nicht Zielseite"),
    ("Die Kreaturen von Barsaive", "DLE I<REATUREN VON BARSALVE", 7, "Klasse (3) -> REQ-MB-13"),
]


class TestUeberschriftenListe(unittest.TestCase):
    def baue(self, seiten, liste, **kw):
        p = einlesen().Protokoll()
        return einlesen().baue_abschnitte(seiten, liste, protokoll=p, **kw), p

    @unittest.skip("devloop: REQ-MB-12 noch nicht implementiert")
    def test_req_mb_12_ersetzte_faelle(self):
        """[REQ-MB-12] Passende Zeile auf der Zielseite wird durch den Listentitel ersetzt und beginnt den Abschnitt."""
        for titel, zeile, grund in ERSETZT:
            with self.subTest(grund=grund, zeile=zeile):
                seiten = {6: [z("Einleitung ohne Titel.")], 7: [z(zeile, "section_header"), z("Fliesstext dazu.")]}
                abschnitte, p = self.baue(seiten, [eintrag("Einleitung", 6), eintrag(titel, 7)])
                a = nach_pfad(abschnitte)[(titel,)]
                self.assertTrue(a["text"].startswith(titel), a["text"])
                self.assertNotIn(zeile, a["text"].replace(titel, ""))
                self.assertIn("Fliesstext dazu.", a["text"])
                self.assertNotIn(zeile, "".join(b["text"] for b in abschnitte).replace(titel, ""))
                self.assertIn((titel, 7), p.gefunden)
                self.assertEqual(p.nicht_gefunden, [("Einleitung", 6)])

    @unittest.skip("devloop: REQ-MB-12 noch nicht implementiert")
    def test_req_mb_12_nicht_ersetzte_faelle_bleiben_byte_gleich(self):
        """[REQ-MB-12] Nicht passende Zeilen bleiben byte-gleich; der Eintrag faellt unter REQ-MB-13."""
        for titel, zeile, seite, grund in NICHT_ERSETZT:
            with self.subTest(grund=grund):
                seiten = {7: [z("Erster Satz der Seite.")], 8: [z("Zweite Seite.")]}
                seiten[seite] = [z(zeile, "section_header")] + seiten[seite]
                abschnitte, p = self.baue(seiten, [eintrag(titel, 7)])
                a = nach_pfad(abschnitte)[(titel,)]
                self.assertIn(zeile, a["text"])
                self.assertIn("Erster Satz der Seite.", a["text"])
                self.assertEqual(p.gefunden, [])
                self.assertEqual(p.nicht_gefunden, [(titel, 7)])

    @unittest.skip("devloop: REQ-MB-12 noch nicht implementiert")
    def test_req_mb_12_gleichstand_erste_zeile_und_protokoll_mehrdeutig(self):
        """[REQ-MB-12] Zwei gleich gute Zeilen: die erste in Lesereihenfolge gewinnt, Protokoll mehrdeutig = 1."""
        seiten = {7: [z("Bonusw rfel", "section_header"), z("Erster Text."),
                      z("Bonuswürfl", "section_header"), z("Zweiter Text.")]}
        abschnitte, p = self.baue(seiten, [eintrag("Bonuswürfel", 7)])
        self.assertEqual(len(abschnitte), 1)
        a = abschnitte[0]
        self.assertEqual(a["abschnittspfad"], ["Bonuswürfel"])
        self.assertTrue(a["text"].startswith("Bonuswürfel"))
        self.assertNotIn("Bonusw rfel", a["text"])
        self.assertIn("Bonuswürfl", a["text"])                 # die zweite bleibt byte-gleich Fliesstext
        self.assertLess(a["text"].index("Erster Text."), a["text"].index("Bonuswürfl"))
        self.assertEqual(p.mehrdeutig, [("Bonuswürfel", 7)])
        self.assertEqual(p.gefunden, [("Bonuswürfel", 7)])

    @unittest.skip("devloop: REQ-MB-12 noch nicht implementiert")
    def test_req_mb_12_wenigste_auslassungen_gewinnen(self):
        """[REQ-MB-12] Mehrere passende Zeilen: die mit den wenigsten Auslassungen gewinnt, auch wenn sie spaeter steht."""
        seiten = {7: [z("Bonusw rfel", "section_header"), z("Vorher."),
                      z("BONUSWÜRFEL", "section_header"), z("Nachher.")]}
        abschnitte, p = self.baue(seiten, [eintrag("Einleitung", 7), eintrag("Bonuswürfel", 7)])
        pfade = nach_pfad(abschnitte)
        self.assertIn("Bonusw rfel", pfade[("Einleitung",)]["text"])
        self.assertIn("Vorher.", pfade[("Einleitung",)]["text"])
        self.assertTrue(pfade[("Bonuswürfel",)]["text"].startswith("Bonuswürfel"))
        self.assertIn("Nachher.", pfade[("Bonuswürfel",)]["text"])
        self.assertNotIn("BONUSWÜRFEL", pfade[("Bonuswürfel",)]["text"])
        self.assertEqual(p.mehrdeutig, [])

    @unittest.skip("devloop: REQ-MB-12 noch nicht implementiert")
    def test_req_mb_12_eine_zeile_hoechstens_ein_eintrag(self):
        """[REQ-MB-12] Eine Zeile wird hoechstens einem Eintrag zugeordnet (Listenreihenfolge); der zweite beginnt hinter ihr (REQ-MB-13)."""
        seiten = {7: [z("Ablauf", "section_header"), z("Text zum Ablauf.")]}
        abschnitte, p = self.baue(seiten, [eintrag("Ablauf", 7, 1), eintrag("Ablauf", 7, 2)])
        self.assertEqual(p.gefunden, [("Ablauf", 7)])
        self.assertEqual(p.nicht_gefunden, [("Ablauf", 7)])
        self.assertEqual([a["abschnittspfad"] for a in abschnitte], [["Ablauf"], ["Ablauf", "Ablauf"]])
        self.assertEqual(abschnitte[0]["text"], "Ablauf")
        self.assertIn("Text zum Ablauf.", abschnitte[1]["text"])

    @unittest.skip("devloop: REQ-MB-12 noch nicht implementiert")
    def test_req_mb_12_formatzeichen_cf_werden_beim_abgleich_entfernt(self):
        """[REQ-MB-12] norm() entfernt Formatzeichen (Cf): "Bewusstlosigkeits·schwelle" (U+00AD) und "Bonus<U+200B>würfel" passen mit 0 Auslassungen."""
        for titel, zeile in (("Bewusstlosigkeitsschwelle", f"Bewusstlosigkeits{SHY}schwelle"),
                             ("Bonuswürfel", "Bonus\u200bwürfel")):
            with self.subTest(titel=titel):
                seiten = {7: [z(zeile, "section_header"), z("Fliesstext dazu.")]}
                abschnitte, p = self.baue(seiten, [eintrag(titel, 7)])
                self.assertEqual(p.gefunden, [(titel, 7)])
                self.assertEqual(abschnitte[0]["abschnittspfad"], [titel])
                self.assertTrue(abschnitte[0]["text"].startswith(titel))
                self.assertNotIn("\u200b", abschnitte[0]["text"])

    @unittest.skip("devloop: REQ-MB-12 noch nicht implementiert")
    def test_req_mb_12_randzeile_ist_kein_kandidat(self):
        """[REQ-MB-12] Kopfrand deklariert: Kolumnentitel "Bonuswürfel" im Rand ist kein Kandidat -> Abschnitt beginnt im Satzspiegel, mehrdeutig 0; ohne Rand: erste Zeile, mehrdeutig 1."""
        seiten = {6: [z("Davor", "section_header", oben=100), z("Text davor.", oben=120)],
                  7: [z("Bonuswürfel", "section_header", oben=20),           # Mitte 25 < 50: im Kopfrand
                      z("Zwischentext der Seite.", oben=100),
                      z("Bonuswürfel", "section_header", oben=140),
                      z("Echter Abschnittstext.", oben=160)]}
        liste = [eintrag("Davor", 6), eintrag("Bonuswürfel", 7)]
        abschnitte, p = self.baue(seiten, liste, rand={"kopf": 50}, seitenhoehe=SEITENHOEHE)
        bonus = nach_pfad(abschnitte)[("Bonuswürfel",)]["text"]
        self.assertIn("Echter Abschnittstext.", bonus)
        self.assertNotIn("Zwischentext der Seite.", bonus)
        self.assertEqual(p.mehrdeutig, [])
        self.assertEqual(p.gefunden, [("Davor", 6), ("Bonuswürfel", 7)])
        # Gegenprobe ohne Randangabe: beide Zeilen passen gleich gut -> die erste gewinnt
        abschnitte, p = self.baue(seiten, liste, seitenhoehe=SEITENHOEHE)
        bonus = nach_pfad(abschnitte)[("Bonuswürfel",)]["text"]
        self.assertIn("Zwischentext der Seite.", bonus)
        self.assertEqual(p.mehrdeutig, [("Bonuswürfel", 7)])

    @unittest.skip("devloop: REQ-MB-12 noch nicht implementiert")
    def test_req_mb_12_ebenen_aus_der_liste(self):
        """[REQ-MB-12] Die Liste ist Wahrheit fuer ihre Ebenen: Pfade K1, K1 > U1, K1 > U2, K2."""
        seiten = {1: [z("K1", "section_header"), z("Text K1."), z("U1", "section_header"), z("Text U1.")],
                  2: [z("U2", "section_header"), z("Text U2."), z("K2", "section_header"), z("Text K2.")]}
        abschnitte, p = self.baue(seiten, [eintrag("K1", 1, 1), eintrag("U1", 1, 2), eintrag("U2", 2, 2),
                                           eintrag("K2", 2, 1)])
        self.assertEqual([a["abschnittspfad"] for a in abschnitte], [["K1"], ["K1", "U1"], ["K1", "U2"], ["K2"]])
        self.assertEqual(len(p.gefunden), 4)
        texte = nach_pfad(abschnitte)
        self.assertIn("Text U1.", texte[("K1", "U1")]["text"])
        self.assertNotIn("Text U1.", texte[("K1",)]["text"])

    @unittest.skip("devloop: REQ-MB-12 noch nicht implementiert")
    def test_req_mb_12_reihenfolge_abgleich_vor_trennungsreparatur(self):
        """[REQ-MB-12] Erst der Abgleich auf Zeilen, dann die Trennungsreparatur: "Wurf" wird nicht mit "Stufe ..." verschmolzen."""
        seiten = {7: [z("Wurf", "section_header"), z("Stufe und Akti-"), z("onswürfel.")]}
        abschnitte, p = self.baue(seiten, [eintrag("Wurf", 7)])
        self.assertEqual(p.gefunden, [("Wurf", 7)])
        self.assertIn("Aktionswürfel.", abschnitte[0]["text"])
        ohne, _ = self.baue(seiten, [eintrag("Wurf", 7)], reparatur=False)
        self.assertNotIn("Aktionswürfel", ohne[0]["text"])
        self.assertIn("Akti-", ohne[0]["text"])


class TestNichtGefunden(unittest.TestCase):
    @unittest.skip("devloop: REQ-MB-13 noch nicht implementiert")
    def test_req_mb_13_abschnitt_ab_seitenanfang_und_protokoll(self):
        """[REQ-MB-13] (a) Eintrag ohne Gegenstueck, als erster seiner Seite: Abschnitt beginnt am Seitenanfang, Protokoll nennt ihn."""
        e = einlesen()
        seiten = {6: [z("Kapitel A", "section_header"), z("Text A.")],
                  7: [z("Text B eins."), z("Text B zwei.")],
                  8: [z("Kapitel C", "section_header"), z("Text C.")]}
        p = e.Protokoll()
        abschnitte = e.baue_abschnitte(seiten, [eintrag("Kapitel A", 6), eintrag("Kapitel B", 7),
                                                eintrag("Kapitel C", 8)], protokoll=p)
        self.assertEqual([a["abschnittspfad"] for a in abschnitte], [["Kapitel A"], ["Kapitel B"], ["Kapitel C"]])
        a, b, c = abschnitte
        self.assertIn("Text A.", a["text"])
        self.assertNotIn("Text B eins.", a["text"])
        self.assertIn("Text B eins.", b["text"])
        self.assertIn("Text B zwei.", b["text"])
        self.assertNotIn("Text C.", b["text"])
        self.assertEqual(b["seiten"], [7])
        self.assertEqual(p.nicht_gefunden, [("Kapitel B", 7)])
        self.assertEqual(p.gefunden, [("Kapitel A", 6), ("Kapitel C", 8)])
        self.assertEqual(p.mehrdeutig, [])

    @unittest.skip("devloop: REQ-MB-13 noch nicht implementiert")
    def test_req_mb_13_beginnt_hinter_dem_vorangehenden_gefundenen_eintrag(self):
        """[REQ-MB-13] (b) Liste A, B auf derselben Seite, nur A gefunden: B beginnt direkt hinter Zeile A, der Fliesstext liegt in B."""
        e = einlesen()
        seiten = {6: [z("Vorher", "section_header"), z("Text vorher.")],
                  7: [z("Satz am Seitenanfang."), z("Kapitel A", "section_header"), z("Fliesstext nach A."),
                      z("Noch mehr Fliesstext.")],
                  8: [z("Kapitel C", "section_header"), z("Text C.")]}
        p = e.Protokoll()
        abschnitte = e.baue_abschnitte(seiten, [eintrag("Vorher", 6), eintrag("Kapitel A", 7), eintrag("Kapitel B", 7),
                                                eintrag("Kapitel C", 8)], protokoll=p)
        self.assertEqual([a["abschnittspfad"] for a in abschnitte],
                         [["Vorher"], ["Kapitel A"], ["Kapitel B"], ["Kapitel C"]])
        vorher, a, b, c = abschnitte
        self.assertIn("Satz am Seitenanfang.", vorher["text"])     # Seite 7 vor Zeile A gehoert noch zu "Vorher"
        self.assertEqual(a["text"], "Kapitel A")
        self.assertIn("Fliesstext nach A.", b["text"])
        self.assertIn("Noch mehr Fliesstext.", b["text"])
        self.assertNotIn("Fliesstext", a["text"])
        self.assertEqual(p.nicht_gefunden, [("Kapitel B", 7)])
        self.assertEqual(p.gefunden, [("Vorher", 6), ("Kapitel A", 7), ("Kapitel C", 8)])

    @unittest.skip("devloop: REQ-MB-13 noch nicht implementiert")
    def test_req_mb_13_listenreihenfolge_ist_massgeblich(self):
        """[REQ-MB-13] Vorangehend in LISTENreihenfolge: B steht in der Liste vor A -> B beginnt am Seitenanfang, nicht hinter A."""
        e = einlesen()
        seiten = {6: [z("Vorher", "section_header"), z("Text vorher.")],
                  7: [z("Satz am Seitenanfang."), z("Kapitel A", "section_header"), z("Fliesstext nach A.")]}
        p = e.Protokoll()
        abschnitte = e.baue_abschnitte(seiten, [eintrag("Vorher", 6), eintrag("Kapitel B", 7), eintrag("Kapitel A", 7)],
                                       protokoll=p)
        pfade = nach_pfad(abschnitte)
        self.assertIn("Satz am Seitenanfang.", pfade[("Kapitel B",)]["text"])
        self.assertNotIn("Satz am Seitenanfang.", pfade[("Vorher",)]["text"])
        self.assertIn("Fliesstext nach A.", pfade[("Kapitel A",)]["text"])
        self.assertEqual(p.nicht_gefunden, [("Kapitel B", 7)])



# ===================================================================================
# REQ-MB-20: Layout-Ueberschriften unterhalb der Liste
# ===================================================================================
LAYOUT_SEITEN = {1: [z("K1", "section_header"), z("Einleitung K1."),
                     z("U1", "section_header"), z("Text U1."),
                     z("Alpha", "section_header"), z("Text Alpha eins."), z("Text Alpha zwei."),
                     z("Beta", "section_header"), z("Text Beta."),
                     z("Gamma"), z("Text nach Gamma.")]}
LAYOUT_LISTE = [eintrag("K1", 1, 1), eintrag("U1", 1, 2)]


class TestLayoutUeberschriften(unittest.TestCase):
    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_layout_ueberschriften_verfeinern_den_pfad(self):
        """[REQ-MB-20] Ohne Schriftstufen entscheidet 5(b), die Klasse (Rueckfall): K1 > U1 > Alpha / Beta; "Gamma" (Klasse text) bleibt in Beta."""
        e = einlesen()
        p = e.Protokoll()
        abschnitte = e.baue_abschnitte(LAYOUT_SEITEN, LAYOUT_LISTE, layout={"klasse": "section_header"}, protokoll=p)
        self.assertEqual([a["abschnittspfad"] for a in abschnitte],
                         [["K1"], ["K1", "U1"], ["K1", "U1", "Alpha"], ["K1", "U1", "Beta"]])
        pfade = nach_pfad(abschnitte)
        self.assertIn("Text Alpha zwei.", pfade[("K1", "U1", "Alpha")]["text"])
        self.assertNotIn("Text Beta.", pfade[("K1", "U1", "Alpha")]["text"])
        beta = pfade[("K1", "U1", "Beta")]["text"]
        self.assertIn("Gamma", beta)
        self.assertIn("Text nach Gamma.", beta)
        self.assertEqual({k: v for k, v in p.layout_ueberschriften.items() if v}, {("K1", "U1"): 2})
        self.assertEqual(len(p.gefunden), 2)        # K1/U1 gehoeren der Liste, nicht dem Layout
        self.assertEqual(p.rueckfaelle, 2)
        self.assertEqual({k: v for k, v in p.layout_je_stufe.items() if v}, {1: 2})

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_ohne_merkmale_nur_die_liste(self):
        """[REQ-MB-20] Ohne deklarierte Merkmale: Pfade nur aus der Liste (Wirkung von REQ-MB-12 unveraendert)."""
        e = einlesen()
        abschnitte = e.baue_abschnitte(LAYOUT_SEITEN, LAYOUT_LISTE, protokoll=e.Protokoll())
        self.assertEqual([a["abschnittspfad"] for a in abschnitte], [["K1"], ["K1", "U1"]])
        u1 = abschnitte[1]["text"]
        for t in ("Alpha", "Text Alpha zwei.", "Beta", "Text nach Gamma."):
            self.assertIn(t, u1)

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_zeilenmerkmale_sind_notwendig(self):
        """[REQ-MB-20] Bedingung 4: Hoechstlaenge gilt zusaetzlich -- auch mit Schrift der Stufe 1 und auch im Rueckfall."""
        e = einlesen()
        seiten = {1: [z("K1", "section_header", S1), z("Einleitung.", schrift=FT),
                      z("Kurz", schrift=S1), z("Text kurz.", schrift=FT),
                      z("Diese Kopfzeile ist zu lang", schrift=S1), z("Text lang.", schrift=FT),
                      z("Ohne", "section_header"), z("Text ohne.", schrift=FT),
                      z("Ohne Schrift und zu lang", "section_header"), z("Text Rest.", schrift=FT)]}
        p = e.Protokoll()
        abschnitte = e.baue_abschnitte(seiten, [eintrag("K1", 1)],
                                       layout={"klasse": "section_header", "stufen": STUFEN, "hoechstlaenge": 10},
                                       protokoll=p)
        self.assertEqual([a["abschnittspfad"] for a in abschnitte], [["K1"], ["K1", "Kurz"], ["K1", "Ohne"]])
        pfade = nach_pfad(abschnitte)
        self.assertIn("Diese Kopfzeile ist zu lang", pfade[("K1", "Kurz")]["text"])
        self.assertIn("Ohne Schrift und zu lang", pfade[("K1", "Ohne")]["text"])
        self.assertEqual(p.rueckfaelle, 1)

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_nicht_gegen_die_liste_abgeglichen(self):
        """[REQ-MB-20] Layout-Ueberschriften werden nicht gegen die Liste abgeglichen oder ersetzt: Zeile bleibt, wie sie ist."""
        e = einlesen()
        seiten = {1: [z("K1", "section_header"), z("Einleitung."), z("Bonusw rfel", "section_header"), z("Text.")]}
        abschnitte = e.baue_abschnitte(seiten, [eintrag("K1", 1)], layout={"klasse": "section_header"},
                                       protokoll=e.Protokoll())
        self.assertEqual([a["abschnittspfad"] for a in abschnitte], [["K1"], ["K1", "Bonusw rfel"]])


def schrift_seiten(*einschub, kopf=None):
    """Grundfall (Spec-Detektor): K1 > U1, Alpha/Beta in Schrift der Stufe 1, je Text; einschub nach
    dem Text von Beta. Alle Zeilen mit Lage (Abstand 20 pt), Seitenhoehe 800."""
    zeilen = [z("K1", "section_header", S1), z("Einleitung K1.", schrift=FT),
              z("U1", "section_header", S1), z("Text U1.", schrift=FT),
              z("Alpha", "section_header", S1), z("Text Alpha.", schrift=FT),
              z("Beta", "section_header", S1), z("Text Beta.", schrift=FT)] + list(einschub)
    for i, zeile in enumerate(zeilen):
        zeile.setdefault("oben", 100 + 20 * i)
        zeile.setdefault("unten", zeile["oben"] + 10)
    return {1: ([kopf] if kopf else []) + zeilen}


LAYOUT_SCHRIFT = {"klasse": "section_header", "stufen": STUFEN}


class TestLayoutSchrift(unittest.TestCase):
    """REQ-MB-20, Kombinationsregel: Rand, Veto, Listenzuordnung, Zeilenmerkmale -- dann Schrift-Stufe
    oder Rueckfall 5(b)."""

    def baue(self, seiten, layout=None, **kw):
        e = einlesen()
        p = e.Protokoll()
        abschnitte = e.baue_abschnitte(seiten, LAYOUT_LISTE, layout=layout or LAYOUT_SCHRIFT,
                                       seitenhoehe=SEITENHOEHE, protokoll=p, **kw)
        return [a["abschnittspfad"] for a in abschnitte], nach_pfad(abschnitte), p

    @staticmethod
    def ohne(pfade, wort):
        return not any(wort in teil for pfad in pfade for teil in pfad)

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_grundfall_schrift_der_stufe_1(self):
        """[REQ-MB-20] Grundfall: Alpha, Beta mit Schrift der Stufe 1 -> K1 > U1 > Alpha / Beta, Protokoll U1 = 2, kein Rueckfall."""
        pfade, je, p = self.baue(schrift_seiten())
        self.assertEqual(pfade, [["K1"], ["K1", "U1"], ["K1", "U1", "Alpha"], ["K1", "U1", "Beta"]])
        self.assertIn("Text Alpha.", je[("K1", "U1", "Alpha")]["text"])
        self.assertEqual({k: v for k, v in p.layout_ueberschriften.items() if v}, {("K1", "U1"): 2})
        self.assertEqual({k: v for k, v in p.layout_je_stufe.items() if v}, {1: 2})
        self.assertEqual((p.rueckfaelle, p.rand_verhindert, p.veto_verhindert), (0, 0, 0))

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_a_kolumnentitel_im_kopfrand(self):
        """[REQ-MB-20] (a) Zeile im Kopfrand mit Ueberschriften-Klasse und Schrift der Stufe 1 -> keine Ueberschrift, Rand-Zaehler 1; 1 pt ausserhalb -> Ueberschrift."""
        kopf = z("Kolumne", "section_header", S1, oben=44)               # Mitte 49 < 50
        pfade, _, p = self.baue(schrift_seiten(z("Text Kolumne.", schrift=FT, oben=300), kopf=kopf),
                                rand={"kopf": 50})
        self.assertTrue(self.ohne(pfade, "Kolumne"), pfade)
        self.assertEqual(p.rand_verhindert, 1)
        draussen = z("Kolumne", "section_header", S1, oben=46)           # Mitte 51: 1 pt ausserhalb
        seiten = schrift_seiten(z("Text Kolumne.", schrift=FT, oben=300))
        seiten[1].insert(4, draussen)                                      # hinter "Text U1." (Lesereihenfolge)
        pfade, _, p = self.baue(seiten, rand={"kopf": 50})
        self.assertIn(["K1", "U1", "Kolumne"], pfade)
        self.assertEqual(p.rand_verhindert, 0)

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_b_schrift_hinreichend_auch_mit_klasse_text(self):
        """[REQ-MB-20] (b) "Delta" mit Schrift der Stufe 1, Klasse text -> Ueberschrift K1 > U1 > Delta, kein Rueckfall."""
        pfade, je, p = self.baue(schrift_seiten(z("Delta", schrift=S1), z("Text Delta.", schrift=FT)))
        self.assertEqual(pfade[-1], ["K1", "U1", "Delta"])
        self.assertIn("Text Delta.", je[("K1", "U1", "Delta")]["text"])
        self.assertNotIn("Text Delta.", je[("K1", "U1", "Beta")]["text"])
        self.assertEqual(p.rueckfaelle, 0)

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_c_stufe_2_liegt_unter_dem_talent(self):
        """[REQ-MB-20] (c) In Alpha: Text, "Unter" (Stufe 2), Text, dann Beta -> Alpha, Alpha > Unter, Beta; kein K1 > U1 > Unter."""
        seiten = {1: [z("K1", "section_header", S1), z("Einleitung K1.", schrift=FT),
                      z("U1", "section_header", S1), z("Text U1.", schrift=FT),
                      z("Alpha", "section_header", S1), z("Text vor Unter.", schrift=FT),
                      z("Unter", "section_header", S2), z("Text nach Unter.", schrift=FT),
                      z("Beta", "section_header", S1), z("Text Beta.", schrift=FT)]}
        pfade, je, p = self.baue(seiten)
        self.assertEqual(pfade, [["K1"], ["K1", "U1"], ["K1", "U1", "Alpha"], ["K1", "U1", "Alpha", "Unter"],
                                 ["K1", "U1", "Beta"]])
        self.assertIn("Text vor Unter.", je[("K1", "U1", "Alpha")]["text"])
        self.assertNotIn("Text nach Unter.", je[("K1", "U1", "Alpha")]["text"])
        self.assertIn("Text nach Unter.", je[("K1", "U1", "Alpha", "Unter")]["text"])
        self.assertNotIn("Text Beta.", je[("K1", "U1", "Alpha", "Unter")]["text"])   # Stufe 1 beendet Stufe 2
        self.assertEqual({k: v for k, v in p.layout_je_stufe.items() if v}, {1: 2, 2: 1})
        self.assertEqual({k: v for k, v in p.layout_ueberschriften.items() if v}, {("K1", "U1"): 3})

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_c_fehlende_stufe_wird_uebersprungen(self):
        """[REQ-MB-20] Stufe 2 ohne offene Stufe 1 im Listenabschnitt -> K1 > U1 > Unter (keine Luecke gefuellt)."""
        seiten = {1: [z("K1", "section_header", S1), z("Einleitung K1.", schrift=FT),
                      z("U1", "section_header", S1), z("Text U1.", schrift=FT),
                      z("Unter", "section_header", S2), z("Text nach Unter.", schrift=FT)]}
        pfade, je, _ = self.baue(seiten)
        self.assertEqual(pfade, [["K1"], ["K1", "U1"], ["K1", "U1", "Unter"]])

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_d_e_fliesstextschrift_ist_nie_ueberschrift(self):
        """[REQ-MB-20] (d) "Gamma" Klasse text, Fliesstextschrift; (e) "Epsilon" Ueberschriften-Klasse, Fliesstextschrift -> beide bleiben in Beta."""
        pfade, je, p = self.baue(schrift_seiten(z("Gamma", schrift=FT), z("Text Gamma.", schrift=FT),
                                                z("Epsilon", "section_header", FT), z("Text Epsilon.", schrift=FT)))
        self.assertEqual(pfade[-1], ["K1", "U1", "Beta"])
        for t in ("Gamma", "Text Gamma.", "Epsilon", "Text Epsilon."):
            self.assertIn(t, je[("K1", "U1", "Beta")]["text"])
        self.assertEqual(p.rueckfaelle, 0)

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_f_rueckfall_ohne_schrift(self):
        """[REQ-MB-20] (f) Zeile ohne zugeordnete Schrift mit Ueberschriften-Klasse -> Stufe 1, Rueckfall-Zaehler 1."""
        pfade, je, p = self.baue(schrift_seiten(z("Omega", "section_header"), z("Text Omega.", schrift=FT)))
        self.assertEqual(pfade[-1], ["K1", "U1", "Omega"])
        self.assertEqual(p.rueckfaelle, 1)
        self.assertEqual({k: v for k, v in p.layout_je_stufe.items() if v}, {1: 3})

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_g_veto_tabelle_und_gegenprobe(self):
        """[REQ-MB-20] (g) fette Tabellenzeile "Zeta" (table, Stufe 1) -> keine Ueberschrift, Text bleibt in Beta, Veto-Zaehler 1; mit Klasse text -> Ueberschrift."""
        pfade, je, p = self.baue(schrift_seiten(z("Zeta", "table", S1), z("Text Zeta.", schrift=FT)))
        self.assertTrue(self.ohne(pfade, "Zeta"), pfade)
        self.assertIn("Zeta", je[("K1", "U1", "Beta")]["text"])
        self.assertIn("Text Zeta.", je[("K1", "U1", "Beta")]["text"])
        self.assertEqual(p.veto_verhindert, 1)
        pfade, _, p = self.baue(schrift_seiten(z("Zeta", "text", S1), z("Text Zeta.", schrift=FT)))
        self.assertEqual(pfade[-1], ["K1", "U1", "Zeta"])
        self.assertEqual(p.veto_verhindert, 0)

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_h_veto_bildunterschrift_und_seitenkopf(self):
        """[REQ-MB-20] (h) "Eta" (caption, Stufe 1) und Seitenkopf/-fuss (page_header/page_footer, Stufe 1) -> keine Ueberschrift."""
        pfade, _, p = self.baue(schrift_seiten(z("Eta", "caption", S1), z("Kopfzeile", "page_header", S1),
                                               z("Fusszeile", "page_footer", S1), z("Text danach.", schrift=FT)))
        for wort in ("Eta", "Kopfzeile", "Fusszeile"):
            self.assertTrue(self.ohne(pfade, wort), (wort, pfade))
        self.assertEqual(p.veto_verhindert, 3)

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_veto_deklaration_ergaenzt_den_default(self):
        """[REQ-MB-20] Veto des Buchs ["formula"] ergaenzt die Default-Menge: formula UND table bleiben Fliesstext."""
        layout = dict(LAYOUT_SCHRIFT, veto=["formula"])
        pfade, _, p = self.baue(schrift_seiten(z("Theta", "formula", S1), z("Zeta", "table", S1),
                                               z("Text danach.", schrift=FT)), layout=layout)
        self.assertTrue(self.ohne(pfade, "Theta"), pfade)
        self.assertTrue(self.ohne(pfade, "Zeta"), pfade)
        self.assertEqual(p.veto_verhindert, 2)
        pfade, _, _ = self.baue(schrift_seiten(z("Theta", "formula", S1), z("Text danach.", schrift=FT)))
        self.assertEqual(pfade[-1], ["K1", "U1", "Theta"])        # ohne Deklaration ist formula kein Veto


# ===================================================================================
# REQ-MB-25: Vorspann
# ===================================================================================
class TestVorspann(unittest.TestCase):
    SEITEN = {1: [z("Ein eindeutiger Vorspanntext quorx."), z("Noch ein Satz davor.")],
              2: [z("Kapitel", "section_header"), z("Text im Kapitel.")]}

    @unittest.skip("devloop: REQ-MB-25 noch nicht implementiert")
    def test_req_mb_25_text_vor_dem_ersten_eintrag_wird_vorspann(self):
        """[REQ-MB-25] Text vor dem ersten Listeneintrag -> Abschnitt ["Vorspann"]; konfigurierter Name -> dieser Name."""
        e = einlesen()
        abschnitte = e.baue_abschnitte(self.SEITEN, [eintrag("Kapitel", 2)], protokoll=e.Protokoll())
        self.assertEqual([a["abschnittspfad"] for a in abschnitte], [["Vorspann"], ["Kapitel"]])
        self.assertIn("quorx", abschnitte[0]["text"])
        self.assertIn("Noch ein Satz davor.", abschnitte[0]["text"])
        self.assertNotIn("quorx", abschnitte[1]["text"])
        anders = e.baue_abschnitte(self.SEITEN, [eintrag("Kapitel", 2)], vorspann="Auftakt", protokoll=e.Protokoll())
        self.assertEqual([a["abschnittspfad"] for a in anders], [["Auftakt"], ["Kapitel"]])
        ohne = e.baue_abschnitte({2: self.SEITEN[2]}, [eintrag("Kapitel", 2)], protokoll=e.Protokoll())
        self.assertEqual([a["abschnittspfad"] for a in ohne], [["Kapitel"]])     # kein leerer Vorspann


# ===================================================================================
# REQ-MB-22: gedruckte Seite (Labels oder Versatz, Kontrollpunkte, roemische Seiten)
# ===================================================================================
LABEL_SEITEN = {1: [z("Titelei", "section_header"), z("Titeleitext.")],
                2: [z("Vorwort", "section_header"), z("Vorworttext roemisch.")],
                3: [z("Kapitel", "section_header"), z("Feuer Kapiteltext eins.")],
                4: [z("Erde Kapiteltext zwei.")]}
LABEL_LESEZEICHEN = [eintrag("Titelei", 1), eintrag("Vorwort", 2), eintrag("Kapitel", 3)]


class TestGedruckteSeite(mb.BestandTest):
    def lege_an(self, seitenzahlen, ueberschriften=None):
        self.bestand([mb.buch("nord", "Buch Nord", "alpha", ueberschriften=ueberschriften or {"quelle": "lesezeichen"},
                              seitenzahlen=seitenzahlen, reparatur=True)])

    def chunks(self):
        self.baue()
        chunks, _ = rag.lade_spiel(self.oeffne(), mb.SID)
        return chunks

    @unittest.skip("devloop: REQ-MB-22 noch nicht implementiert")
    def test_req_mb_22_labels_ergeben_gedruckte_und_physische_seite(self):
        """[REQ-MB-22] Labels (i, ii, 1, 2): Haeppchen von physisch 3 traegt gedruckt 1 und physisch 3; "ii" -> "PDF-S. 2"."""
        self.lege_an({"quelle": "labels"})
        einlesen().lies_buch_ein(mb.SID, "nord", LABEL_SEITEN, lesezeichen=LABEL_LESEZEICHEN,
                                 labels=["i", "ii", "1", "2"])
        chunks = self.chunks()
        kapitel = next(c for c in chunks if "Kapiteltext eins" in c["text"])
        self.assertEqual((kapitel["seite"], kapitel["seite_pdf"]), (1, 3))
        vorwort = next(c for c in chunks if "Vorworttext" in c["text"])
        self.assertIsNone(vorwort["seite"])
        self.assertEqual(vorwort["seite_pdf"], 2)
        self.assertIn("PDF-S. 2", rag.fundstelle(vorwort))
        self.assertNotIn("PDF-S.", rag.fundstelle(kapitel))

    @unittest.skip("devloop: REQ-MB-22 noch nicht implementiert")
    def test_req_mb_22_versatz_ohne_labels_gleiches_ergebnis(self):
        """[REQ-MB-22] Versatz 2 ohne Labels -> Haeppchen von physisch 3 traegt gedruckt 1, physisch 3."""
        self.lege_an({"quelle": "versatz", "versatz": 2})
        einlesen().lies_buch_ein(mb.SID, "nord", LABEL_SEITEN, lesezeichen=LABEL_LESEZEICHEN)
        kapitel = next(c for c in self.chunks() if "Kapiteltext eins" in c["text"])
        self.assertEqual((kapitel["seite"], kapitel["seite_pdf"]), (1, 3))

    @unittest.skip("devloop: REQ-MB-22 noch nicht implementiert")
    def test_req_mb_22_kontrollpunkt_widerspricht_labels(self):
        """[REQ-MB-22] Labels widersprechen einem Kontrollpunkt -> KonfigFehler mit Hinweis auf den Versatz, nichts geschrieben."""
        self.lege_an({"quelle": "labels", "kontrollpunkte": {"3": 5}})
        with self.assertRaises(rag.KonfigFehler) as ctx:
            einlesen().lies_buch_ein(mb.SID, "nord", LABEL_SEITEN, lesezeichen=LABEL_LESEZEICHEN,
                                     labels=["i", "ii", "1", "2"])
        self.assertIn("ersatz", str(ctx.exception))          # "Versatz" / "versatz"
        self.assertFalse(os.path.exists(self.buchdatei("nord")))
        # passender Kontrollpunkt: kein Fehler
        self.lege_an({"quelle": "labels", "kontrollpunkte": {"3": 1}})
        einlesen().lies_buch_ein(mb.SID, "nord", LABEL_SEITEN, lesezeichen=LABEL_LESEZEICHEN,
                                 labels=["i", "ii", "1", "2"])
        self.assertTrue(os.path.exists(self.buchdatei("nord")))

    @unittest.skip("devloop: REQ-MB-12 noch nicht implementiert")
    def test_req_mb_12_inhaltsverzeichnis_liste_mit_gedruckten_seiten(self):
        """[REQ-MB-12] Lieferant Inhaltsverzeichnis: gedruckte Seite 1 wird per Versatz auf physisch 3 umgerechnet und gefunden."""
        self.lege_an({"quelle": "versatz", "versatz": 2},
                     {"quelle": "inhaltsverzeichnis", "eintraege": [eintrag("Kapitel", 1)]})
        p = einlesen().lies_buch_ein(mb.SID, "nord", LABEL_SEITEN)
        self.assertEqual(p.nicht_gefunden, [])
        self.assertEqual(len(p.gefunden), 1)
        kapitel = next(c for c in self.chunks() if "Kapiteltext eins" in c["text"])
        self.assertEqual(kapitel["abschnittspfad"], ["Kapitel"])
        self.assertEqual((kapitel["seite"], kapitel["seite_pdf"]), (1, 3))


# ===================================================================================
# REQ-MB-23: Docling-Version beim Einlesen gegen das Messergebnis
# ===================================================================================
class TestDoclingVersion(mb.BestandTest):
    """Version injiziert (kein echtes Docling): lies_buch_ein(..., docling_version=..., vorabmessung=...)."""
    SEITEN = {1: [z("Kapitel", "section_header"), z("Feuer Text eins.")]}
    LISTE = [eintrag("Kapitel", 1)]

    def setUp(self):
        super().setUp()
        self.bestand([mb.buch("nord", "Buch Nord", "alpha", ueberschriften={"quelle": "lesezeichen"},
                              seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True)])
        self.messung = os.path.join(self.tmp.name, "vorabmessung.json")

    def schreibe_messung(self, **felder):
        m = {"seiten": list(range(1, 11)), "zweispalten_mit_tabelle": [1, 2, 3], "talentseiten": list(range(4, 20)),
             "L": {"richtig": 40, "absaetze": 41}, "T": 0,
             "H": {"erkannt": 9, "vorhanden": 9, "fehltreffer": 0, "anker": 8, "handgeprueft": 1}}
        m.update(felder)
        with open(self.messung, "w", encoding="utf-8") as f:
            json.dump(m, f)

    def lies(self, version, **kw):
        return einlesen().lies_buch_ein(mb.SID, "nord", self.SEITEN, lesezeichen=self.LISTE, docling_version=version,
                                        vorabmessung=self.messung, **kw)

    def pruefe_abbruch(self, version="2.5.1"):
        """KonfigFehler -- ohne Buchdatei, und eine vorhandene bleibt unveraendert."""
        with self.assertRaises(rag.KonfigFehler):
            self.lies(version)
        self.assertFalse(os.path.exists(self.buchdatei("nord")))
        einlesen().lies_buch_ein(mb.SID, "nord", {1: [z("Kapitel", "section_header"), z("Alter Stand.")]},
                                 lesezeichen=self.LISTE)                       # ohne Docling: kein Vergleich
        vorher = mb.hashes(os.path.dirname(self.buchdatei("nord")))
        with self.assertRaises(rag.KonfigFehler):
            self.lies(version, ueberschreiben=True)
        self.assertEqual(mb.hashes(os.path.dirname(self.buchdatei("nord"))), vorher)

    @unittest.skip("devloop: REQ-MB-23 noch nicht implementiert")
    def test_req_mb_23_gleiche_version_laeuft_und_steht_im_protokoll(self):
        """[REQ-MB-23] Docling-Version gleich der im Messergebnis -> Einlesen laeuft, Protokoll nennt die Version."""
        self.schreibe_messung(docling_version="2.5.1")
        p = self.lies("2.5.1")
        self.assertEqual(p.docling_version, "2.5.1")
        self.assertTrue(os.path.exists(self.buchdatei("nord")))

    @unittest.skip("devloop: REQ-MB-23 noch nicht implementiert")
    def test_req_mb_23_abweichende_version_ist_konfigfehler(self):
        """[REQ-MB-23] Abweichende Docling-Version -> KonfigFehler, keine Buchdatei bzw. alte unveraendert."""
        self.schreibe_messung(docling_version="2.5.1")
        self.pruefe_abbruch("2.6.0")

    @unittest.skip("devloop: REQ-MB-23 noch nicht implementiert")
    def test_req_mb_23_fehlendes_messergebnis_ist_konfigfehler(self):
        """[REQ-MB-23] vorabmessung.json fehlt -> KonfigFehler beim Einlesen mit Docling, keine/unveraenderte Buchdatei."""
        self.assertFalse(os.path.exists(self.messung))
        self.pruefe_abbruch()

    @unittest.skip("devloop: REQ-MB-23 noch nicht implementiert")
    def test_req_mb_23_messergebnis_ohne_version_ist_konfigfehler(self):
        """[REQ-MB-23] vorabmessung.json ohne docling_version -> KonfigFehler, keine/unveraenderte Buchdatei."""
        self.schreibe_messung()
        self.pruefe_abbruch()


# ===================================================================================
# REQ-MB-24: PDF-Adapter fuer Lesezeichen und Seitenlabels (synthetisches PDF, pypdf)
# ===================================================================================
PDF_LESEZEICHEN = [("Vorwort", 1, 2), ("Kapitel Eins", 1, 3), ("Teil A", 2, 4), ("Teil B", 2, 5),
                   ("Kapitel Zwei", 1, 6)]                      # (Titel, Ebene, physische Seite)
PDF_LABELS = ["i", "ii", "1", "2", "3", "4"]


def baue_pdf(pfad):
    """6 Seiten; Labels i, ii, dann arabisch ab 1; Lesezeichen auf 2 Ebenen."""
    import pypdf
    w = pypdf.PdfWriter()
    for _ in PDF_LABELS:
        w.add_blank_page(width=200, height=200)
    w.set_page_label(0, 1, style="/r")
    w.set_page_label(2, len(PDF_LABELS) - 1, style="/D", start=1)
    eltern = None
    for titel, ebene, seite in PDF_LESEZEICHEN:
        item = w.add_outline_item(titel, seite - 1, parent=eltern if ebene == 2 else None)
        if ebene == 1:
            eltern = item
    w.write(pfad)
    return pfad


class TestPdfAdapter(mb.BestandTest):
    def setUp(self):
        super().setUp()
        self.pdf = baue_pdf(os.path.join(self.tmp.name, "testbuch.pdf"))

    @unittest.skip("devloop: REQ-MB-24 noch nicht implementiert")
    def test_req_mb_24_lesezeichen_und_labels_aus_der_pdf(self):
        """[REQ-MB-24] Synthetisches PDF: Lesezeichen (2 Ebenen) -> Titel/Ebene/Seite/Reihenfolge; Labels je physischer Seite."""
        e = einlesen()
        self.assertEqual(e.lesezeichen_aus_pdf(self.pdf),
                         [{"titel": t, "ebene": eb, "seite": s} for t, eb, s in PDF_LESEZEICHEN])
        self.assertEqual(e.seitenlabels_aus_pdf(self.pdf), PDF_LABELS)

    @unittest.skip("devloop: REQ-MB-24 noch nicht implementiert")
    def test_req_mb_24_einlesen_liest_die_pdf_selbst(self):
        """[REQ-MB-24] lies_buch_ein(pdf=...) nimmt Liste und gedruckte Seiten aus der Datei: Pfade und Seiten je Haeppchen."""
        self.bestand([mb.buch("nord", "Buch Nord", "alpha", ueberschriften={"quelle": "lesezeichen"},
                              seitenzahlen={"quelle": "labels"}, reparatur=True)])
        seiten = {1: [z("Titelei ohne Lesezeichen.")]}
        for titel, _, s in PDF_LESEZEICHEN:
            seiten[s] = [z(titel, "section_header"), z(f"Inhalt auf physisch {s}.")]
        p = einlesen().lies_buch_ein(mb.SID, "nord", seiten, pdf=self.pdf)
        self.assertEqual(len(p.gefunden), len(PDF_LESEZEICHEN))
        self.baue()
        chunks, _ = rag.lade_spiel(self.oeffne(), mb.SID)
        soll = {2: (["Vorwort"], None), 3: (["Kapitel Eins"], 1), 4: (["Kapitel Eins", "Teil A"], 2),
                5: (["Kapitel Eins", "Teil B"], 3), 6: (["Kapitel Zwei"], 4)}
        for physisch, (pfad, gedruckt) in soll.items():
            with self.subTest(physisch=physisch):
                c = next(c for c in chunks if f"physisch {physisch}." in c["text"])
                self.assertEqual((c["abschnittspfad"], c["seite"], c["seite_pdf"]), (pfad, gedruckt, physisch))


class TestPdfplumberVersion(TestDoclingVersion):
    """REQ-MB-23 fuer pdfplumber: Buch mit Schriftstufen, Version injiziert."""
    SEITEN = {1: [z("Kapitel", "section_header", S1), z("Feuer Text eins.", schrift=FT)]}

    def setUp(self):
        super().setUp()
        self.bestand([mb.buch("nord", "Buch Nord", "alpha", ueberschriften={"quelle": "lesezeichen"},
                              seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True,
                              layout={"klasse": "section_header", "stufen": STUFEN})])

    def lies(self, version, **kw):
        return einlesen().lies_buch_ein(mb.SID, "nord", self.SEITEN, lesezeichen=self.LISTE,
                                        pdfplumber_version=version, vorabmessung=self.messung, **kw)

    @unittest.skip("devloop: REQ-MB-23 noch nicht implementiert")
    def test_req_mb_23_gleiche_version_laeuft_und_steht_im_protokoll(self):
        """[REQ-MB-23] pdfplumber-Version gleich der im Messergebnis (Buch mit Schriftstufen) -> laeuft, Protokoll nennt sie."""
        self.schreibe_messung(docling_version="2.131.0", pdfplumber_version="0.11.4")
        p = self.lies("0.11.4")
        self.assertEqual(p.pdfplumber_version, "0.11.4")
        self.assertTrue(os.path.exists(self.buchdatei("nord")))

    @unittest.skip("devloop: REQ-MB-23 noch nicht implementiert")
    def test_req_mb_23_abweichende_version_ist_konfigfehler(self):
        """[REQ-MB-23] Abweichende pdfplumber-Version -> KonfigFehler, keine Buchdatei bzw. alte unveraendert."""
        self.schreibe_messung(docling_version="2.131.0", pdfplumber_version="0.11.4")
        self.pruefe_abbruch("0.11.5")

    @unittest.skip("devloop: REQ-MB-23 noch nicht implementiert")
    def test_req_mb_23_fehlendes_messergebnis_ist_konfigfehler(self):
        """[REQ-MB-23] vorabmessung.json fehlt -> KonfigFehler beim Einlesen mit Schriftinfo."""
        self.pruefe_abbruch("0.11.4")

    @unittest.skip("devloop: REQ-MB-23 noch nicht implementiert")
    def test_req_mb_23_messergebnis_ohne_version_ist_konfigfehler(self):
        """[REQ-MB-23] vorabmessung.json ohne pdfplumber_version -> KonfigFehler beim Einlesen mit Schriftinfo."""
        self.schreibe_messung(docling_version="2.131.0")
        self.pruefe_abbruch("0.11.4")

    @unittest.skip("devloop: REQ-MB-23 noch nicht implementiert")
    def test_req_mb_23_buch_ohne_schriftstufen_braucht_keine_pdfplumber_version(self):
        """[REQ-MB-23] Buch ohne Schriftstufen liest trotz fehlender pdfplumber_version ein."""
        self.bestand([mb.buch("nord", "Buch Nord", "alpha", ueberschriften={"quelle": "lesezeichen"},
                              seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True,
                              layout={"klasse": "section_header"})])
        self.schreibe_messung(docling_version="2.131.0")
        einlesen().lies_buch_ein(mb.SID, "nord", self.SEITEN, lesezeichen=self.LISTE, pdfplumber_version="0.11.4",
                                 vorabmessung=self.messung)
        self.assertTrue(os.path.exists(self.buchdatei("nord")))


# ===================================================================================
# REQ-MB-27: Text aus Bild-Elementen (Docling-Adapter, synthetische Struktur)
# ===================================================================================
class _Prov:
    def __init__(self, seite):
        self.page_no = seite


class _Item:
    def __init__(self, label, text="", seite=1, kinder=()):
        self.label, self.text, self.prov, self.kinder = label, text, [_Prov(seite)], list(kinder)


class FakeDoclingDoc:
    """Wie DoclingDocument.iterate_items: Text-Kinder eines Bild-Elements nur mit traverse_pictures=True."""

    def __init__(self, items):
        self.items = items

    def iterate_items(self, traverse_pictures=False, **_):
        for item in self.items:
            yield item, 1
            if traverse_pictures:
                for kind in item.kinder:
                    yield kind, 2


BILD_DOC = [_Item("section_header", "Kapitel", 1), _Item("text", "Vor dem Bild vormarke."),
            _Item("picture", "", 1, [_Item("text", "Kind eins bildmarkeeins."), _Item("text", "Kind zwei bildmarkezwei.")]),
            _Item("text", "Nach dem Bild nachmarke."), _Item("picture", "", 1, [])]
BILD_MARKEN = ["vormarke", "bildmarkeeins", "bildmarkezwei", "nachmarke"]


class TestBildElemente(mb.BestandTest):
    @unittest.skip("devloop: REQ-MB-27 noch nicht implementiert")
    def test_req_mb_27_text_kinder_genau_einmal_an_der_stelle_des_bildes(self):
        """[REQ-MB-27] Vor, Kind 1, Kind 2, Nach -- jeder Marker genau einmal; leeres Bild ohne Zeile; Protokoll-Zaehler 2."""
        e = einlesen()
        p = e.Protokoll()
        seiten = e.zeilen_aus_docling(FakeDoclingDoc(BILD_DOC), protokoll=p)
        texte = [zeile["text"] for zeile in seiten[1]]
        self.assertEqual(texte, ["Kapitel", "Vor dem Bild vormarke.", "Kind eins bildmarkeeins.",
                                 "Kind zwei bildmarkezwei.", "Nach dem Bild nachmarke."])
        self.assertEqual(p.aus_bildern, 2)

    @unittest.skip("devloop: REQ-MB-27 noch nicht implementiert")
    def test_req_mb_27_nach_index_auffindbar(self):
        """[REQ-MB-27] Nach Einlesen und index findet lade_spiel/BM25 jeden Marker in genau einem Haeppchen, in Reihenfolge."""
        e = einlesen()
        self.bestand([mb.buch("nord", "Buch Nord", "alpha", ueberschriften={"quelle": "lesezeichen"},
                              seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True)])
        seiten = e.zeilen_aus_docling(FakeDoclingDoc(BILD_DOC))
        e.lies_buch_ein(mb.SID, "nord", seiten, lesezeichen=[eintrag("Kapitel", 1)])
        self.baue()
        con = self.oeffne()
        chunks, _ = rag.lade_spiel(con, mb.SID)
        text = " ".join(c["text"] for c in chunks)
        for marke in BILD_MARKEN:
            with self.subTest(marke=marke):
                self.assertEqual(text.count(marke), 1)
                self.assertEqual(len(rag.bm25_rangfolge(con, marke, chunks, 5)), 1)
        self.assertEqual([text.index(m) for m in BILD_MARKEN], sorted(text.index(m) for m in BILD_MARKEN))


# ===================================================================================
# REQ-MB-28: Randzeilen verwerfen
# ===================================================================================
def rand_seiten():
    """Zwei Seiten, je Kopfzeile (Mitte 25), Fusszeile (Mitte 785) und Fliesstext mit eigenem Marker."""
    return {n: [z(f"KOPFMARKE-{n} Kolumne", "page_header", oben=20),
                z(f"Abschnitt {n}", "section_header", oben=100),
                z(f"Fliesstext textmarke{n} der Seite.", oben=130),
                z(f"FUSSMARKE-{n} Seite {n}", "page_footer", oben=780)] for n in (1, 2)}


RAND_LISTE = [eintrag("Abschnitt 1", 1), eintrag("Abschnitt 2", 2)]
RAND = {"kopf": 50, "fuss": 40}


class TestRandzeilen(mb.BestandTest):
    def deklariere(self, rand_bei):
        self.bestand([mb.buch(b, f"Buch {b}", "alpha", quelle=f"{b}.pdf", ueberschriften={"quelle": "lesezeichen"},
                              seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True,
                              **({"rand": RAND} if b in rand_bei else {})) for b in ("nord", "sued")])

    def lies_und_baue(self, rand_bei):
        self.deklariere(rand_bei)
        prot = {}
        for b in ("nord", "sued"):
            if os.path.exists(self.buchdatei(b)):
                os.remove(self.buchdatei(b))
            prot[b] = einlesen().lies_buch_ein(mb.SID, b, rand_seiten(), lesezeichen=RAND_LISTE,
                                               seitenhoehe=SEITENHOEHE)
        self.baue()
        con = self.oeffne()
        chunks, _ = rag.lade_spiel(con, mb.SID)
        return con, chunks, prot

    @unittest.skip("devloop: REQ-MB-28 noch nicht implementiert")
    def test_req_mb_28_rein_baue_abschnitte(self):
        """[REQ-MB-28] Rand deklariert: Kopf-/Fusszeilen in keinem Abschnittstext und keinem Pfad, Zaehler 4; ohne Rand unveraendert."""
        e = einlesen()
        p = e.Protokoll()
        abschnitte = e.baue_abschnitte(rand_seiten(), RAND_LISTE, rand=RAND, seitenhoehe=SEITENHOEHE, protokoll=p)
        alles = " ".join(a["text"] + " " + " ".join(a["abschnittspfad"]) for a in abschnitte)
        self.assertNotIn("KOPFMARKE", alles)
        self.assertNotIn("FUSSMARKE", alles)
        self.assertIn("textmarke1", alles)
        self.assertIn("textmarke2", alles)
        self.assertEqual(p.randzeilen, 4)
        p0 = e.Protokoll()
        ohne = e.baue_abschnitte(rand_seiten(), RAND_LISTE, seitenhoehe=SEITENHOEHE, protokoll=p0)
        self.assertIn("KOPFMARKE-2", " ".join(a["text"] for a in ohne))
        self.assertEqual(p0.randzeilen, 0)

    @unittest.skip("devloop: REQ-MB-28 noch nicht implementiert")
    def test_req_mb_28_nach_index_nur_beim_buch_mit_randangabe(self):
        """[REQ-MB-28] Zwei Buecher, nur nord mit Rand: nord ohne Kopf-/Fussmarker (BM25, lade_spiel), Zaehler nur bei nord; sued wie ohne Randangabe."""
        _, _, _ = self.lies_und_baue(rand_bei=())
        con0 = self.oeffne()
        sued_ohne = [c["text"] for c in rag.lade_spiel(con0, mb.SID)[0] if c["buch_id"] == "sued"]
        con, chunks, prot = self.lies_und_baue(rand_bei=("nord",))
        self.assertEqual((prot["nord"].randzeilen, prot["sued"].randzeilen), (4, 0))
        nord = [c for c in chunks if c["buch_id"] == "nord"]
        for c in nord:
            self.assertNotIn("KOPFMARKE", c["text"])
            self.assertNotIn("FUSSMARKE", c["text"])
            self.assertFalse(any("MARKE" in t for t in c["abschnittspfad"]), c["abschnittspfad"])
        self.assertTrue(any("textmarke1" in c["text"] for c in nord))
        self.assertTrue(any("textmarke2" in c["text"] for c in nord))
        treffer = [chunks[i]["buch_id"] for i in rag.bm25_rangfolge(con, "KOPFMARKE FUSSMARKE", chunks, 20)]
        self.assertTrue(treffer)
        self.assertEqual(set(treffer), {"sued"})
        self.assertEqual([c["text"] for c in chunks if c["buch_id"] == "sued"], sued_ohne)


# ===================================================================================
# Fassung 8: Randgrenze inklusiv (REQ-MB-12, -20, -28)
# ===================================================================================
def grenzzeile(text, mitte, klasse="section_header", schrift=S1):
    d = {"text": text, "klasse": klasse, "oben": mitte - 5, "unten": mitte + 5}
    if schrift is not None:
        d["schrift"] = dict(schrift)
    return d


class TestRandgrenzeInklusiv(unittest.TestCase):
    """Kopfrand 50, Fussrand 40 bei Seitenhoehe 800 (Grenze 760): Mittelpunkt genau auf der Grenze ist Rand,
    0,01 pt weiter innen nicht. Faengt: Vergleich "<=" bzw. ">=" durch "<" bzw. ">" ersetzt."""
    RAND = {"kopf": 50, "fuss": 40}

    def baue(self, kopf_mitte, fuss_mitte):
        e = einlesen()
        p = e.Protokoll()
        seiten = {1: [grenzzeile("Kolumne", kopf_mitte), grenzzeile("K1", 100),
                      grenzzeile("Text K1.", 120, "text", FT), grenzzeile("Fussstufe", fuss_mitte)]}
        abschnitte = e.baue_abschnitte(seiten, [eintrag("K1", 1)], layout={"klasse": "section_header", "stufen": STUFEN},
                                       rand=self.RAND, seitenhoehe=SEITENHOEHE, protokoll=p)
        return [a["abschnittspfad"] for a in abschnitte], " ".join(a["text"] for a in abschnitte), p

    @unittest.skip("devloop: REQ-MB-20 neu in Fassung 8")
    def test_req_mb_20_mittelpunkt_auf_der_grenze_ist_rand(self):
        """[REQ-MB-20] Kopf-/Fusszeile (Stufe 1) mit Mittelpunkt genau auf der Grenze: keine Ueberschrift, Rand-Zaehler 2; Grenze +-0,01 pt nach innen: beide Ueberschrift."""
        pfade, _, p = self.baue(50.0, 760.0)
        self.assertEqual(pfade, [["K1"]])
        self.assertEqual(p.rand_verhindert, 2)
        pfade, _, p = self.baue(50.01, 759.99)
        self.assertIn(["K1", "Fussstufe"], pfade)
        self.assertEqual(p.rand_verhindert, 0)

    @unittest.skip("devloop: REQ-MB-28 neu in Fassung 8")
    def test_req_mb_28_grenzzeile_verworfen_und_gezaehlt(self):
        """[REQ-MB-28] Mittelpunkt genau auf der Grenze: Zeile verworfen und gezaehlt (2); Grenze + 0,01 pt nach innen: Zeile bleibt, Zaehler 0."""
        _, text, p = self.baue(50.0, 760.0)
        self.assertNotIn("Kolumne", text)
        self.assertNotIn("Fussstufe", text)
        self.assertEqual(p.randzeilen, 2)
        _, text, p = self.baue(50.01, 759.99)
        self.assertIn("Kolumne", text)
        self.assertIn("Fussstufe", text)
        self.assertEqual(p.randzeilen, 0)

    @unittest.skip("devloop: REQ-MB-12 neu in Fassung 8")
    def test_req_mb_12_grenzzeile_ist_kein_kandidat(self):
        """[REQ-MB-12] Kolumnentitel "Bonuswürfel" mit Mittelpunkt genau auf der Kopfrandgrenze ist kein Kandidat (mehrdeutig 0); 0,01 pt innen schon (mehrdeutig 1)."""
        e = einlesen()
        for mitte, mehrdeutig in ((50.0, []), (50.01, [("Bonuswürfel", 1)])):
            with self.subTest(mitte=mitte):
                p = e.Protokoll()
                seiten = {1: [grenzzeile("Bonuswürfel", mitte), grenzzeile("Bonuswürfel", 200),
                              grenzzeile("Text.", 220, "text", FT)]}
                e.baue_abschnitte(seiten, [eintrag("Bonuswürfel", 1)], rand={"kopf": 50}, seitenhoehe=SEITENHOEHE,
                                  protokoll=p)
                self.assertEqual(p.mehrdeutig, mehrdeutig)
                self.assertEqual(p.gefunden, [("Bonuswürfel", 1)])


    @unittest.skip("devloop: REQ-MB-28 neu in Fassung 9")
    def test_req_mb_28_zeile_ohne_lage_gilt_als_nicht_im_rand(self):
        """[REQ-MB-28] Lesart: Rand deklariert, Zeile ohne Lage -> nicht im Rand (bleibt, kann Ueberschrift werden), gezaehlt (ohne_lage). Faengt: Zeile ohne Lage verworfen bzw. nicht gezaehlt."""
        e = einlesen()
        p = e.Protokoll()
        seiten = {1: [grenzzeile("K1", 100), {"text": "Ohne Lage", "klasse": "section_header", "schrift": dict(S1)},
                      {"text": "Text ohne Lage.", "klasse": "text", "schrift": dict(FT)}]}
        abschnitte = e.baue_abschnitte(seiten, [eintrag("K1", 1)], layout={"klasse": "section_header", "stufen": STUFEN},
                                       rand=self.RAND, seitenhoehe=SEITENHOEHE, protokoll=p)
        self.assertIn(["K1", "Ohne Lage"], [a["abschnittspfad"] for a in abschnitte])
        self.assertIn("Text ohne Lage.", " ".join(a["text"] for a in abschnitte))
        self.assertEqual((p.randzeilen, p.ohne_lage), (0, 2))

# ===================================================================================
# Fassung 7 -- Docling-Weg mit Attrappe (REQ-MB-11, -32)
# ===================================================================================
import docling_attrappe as da  # noqa: E402

MESSUNG = os.path.join(BASE, ".specify", "specs", "mehrbuch-bestand", "vorabmessung.json")


def gemessene_versionen():
    """Versionen aus dem Messergebnis im Spec-Ordner -- dieselben, die das Einlesen verlangt."""
    with open(MESSUNG, encoding="utf-8") as f:
        m = json.load(f)
    return {"docling": m["docling_version"], "pdfplumber": m["pdfplumber_version"]}


def leeres_pdf(pfad, seiten):
    import pypdf
    w = pypdf.PdfWriter()
    for _ in range(seiten):
        w.add_blank_page(width=da.BREITE, height=da.HOEHE)
    w.write(pfad)
    return pfad


class DoclingWegTest(mb.BestandTest):
    def deklariere(self, kapitel_seite=1):
        self.bestand([mb.buch("nord", "Buch Nord", "alpha", ueberschriften={"quelle": "inhaltsverzeichnis",
                                                                           "eintraege": [eintrag("Kapitel", kapitel_seite)]},
                              seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True)])

    def docling(self, elemente):
        """elemente: {seite: [(Label, Text)]} -> Protokoll des Docling-Wegs (lies_pdf_ein)."""
        pdf = leeres_pdf(os.path.join(self.tmp.name, "buch.pdf"), max(elemente))
        doc = {s: [da.Element(lab, text) for lab, text in liste] for s, liste in elemente.items()}
        with da.installiere(doc, gemessene_versionen()):
            return einlesen().lies_pdf_ein(mb.SID, "nord", pdf=pdf, ausgabe=lambda *_: None)

    def buchtext(self):
        with open(self.buchdatei("nord"), encoding="utf-8") as f:
            return "\n".join(json.loads(z)["text"] for z in f)

    def haeppchentext(self):
        self.baue()
        return "\n".join(c["text"] for c in rag.lade_spiel(self.oeffne(), mb.SID)[0])


class TestTrennungDoclingWeg(DoclingWegTest):
    @unittest.skip("devloop: REQ-MB-11 noch nicht implementiert")
    def test_req_mb_11_docling_weg_laesst_zeilenenden_unangetastet(self):
        """[REQ-MB-11] Docling-Weg: Element "Akti-⏎onswürfel" bleibt byte-gleich, "Bewusstlosigkeits·schwelle" -> ohne U+00AD, Zaehler 0."""
        self.deklariere()
        p = self.docling({1: [("section_header", "Kapitel"), ("text", "Akti-\nonswürfel"),
                              ("text", f"Bewusstlosigkeits{SHY}schwelle")]})
        for text in (self.buchtext(), self.haeppchentext()):
            self.assertIn("Akti-\nonswürfel", text)
            self.assertNotIn("Aktionswürfel", text)
            self.assertIn("Bewusstlosigkeitsschwelle", text)
            self.assertNotIn(SHY, text)
        self.assertEqual(p.trennungen_zusammengefuegt, 0)

    @unittest.skip("devloop: REQ-MB-11 noch nicht implementiert")
    def test_req_mb_11_zeilenweg_repariert_dasselbe_element(self):
        """[REQ-MB-11] Zeilenweg: dasselbe Element "Akti-⏎onswürfel" -> "Aktionswürfel" (der Weg entscheidet, nicht der Text)."""
        self.deklariere()
        p = einlesen().lies_buch_ein(mb.SID, "nord", {1: [z("Kapitel", "section_header"), z("Akti-\nonswürfel")]})
        self.assertIn("Aktionswürfel", self.buchtext())
        self.assertEqual(p.trennungen_zusammengefuegt, 1)


class TestVerdachtszaehler(DoclingWegTest):
    ELEMENTE = {1: [("section_header", "Kapitel"), ("text", "Das NovizenTalent wirkt")],
                2: [("text", "die Akti- onswürfel")],
                3: [("text", "Nah- und Fernkampf"), ("text", "ED4-Regeln"), ("text", "Zwerg-Krieger")]}

    @unittest.skip("devloop: REQ-MB-32 noch nicht implementiert")
    def test_req_mb_32_docling_weg_zaehlt_verdachtsfaelle(self):
        """[REQ-MB-32] Docling-Weg: Binnen-Grossbuchstabe = 1 (S. 1), Strichrest = 1 (S. 2); "Nah- und" (Konjunktion) zaehlt nicht; Texte byte-gleich."""
        self.deklariere()
        p = self.docling(self.ELEMENTE)
        self.assertEqual(p.binnen_grossbuchstabe, {"anzahl": 1, "seiten": [1]})
        self.assertEqual(p.strichrest, {"anzahl": 1, "seiten": [2]})
        text = self.haeppchentext()
        for _, element in [x for liste in self.ELEMENTE.values() for x in liste]:
            self.assertIn(element, text)

    @unittest.skip("devloop: REQ-MB-32 noch nicht implementiert")
    def test_req_mb_32_auch_auf_dem_zeilenweg_und_gedruckte_seite(self):
        """[REQ-MB-32] Zeilenweg, Versatz 2: Verdachtsfaelle mit gedruckter Seite (physisch 3 -> 1, physisch 4 -> 2)."""
        self.bestand([mb.buch("nord", "Buch Nord", "alpha", ueberschriften={"quelle": "inhaltsverzeichnis",
                                                                           "eintraege": [eintrag("Kapitel", 1)]},
                              seitenzahlen={"quelle": "versatz", "versatz": 2}, reparatur=True)])
        p = einlesen().lies_buch_ein(mb.SID, "nord", {3: [z("Kapitel", "section_header"), z("Das NovizenTalent wirkt")],
                                                      4: [z("die Akti- onswürfel"), z("Nah- und Fernkampf")]})
        self.assertEqual(p.binnen_grossbuchstabe, {"anzahl": 1, "seiten": [1]})
        self.assertEqual(p.strichrest, {"anzahl": 1, "seiten": [2]})


    @unittest.skip("devloop: REQ-MB-32 neu in Fassung 9")
    def test_req_mb_32_mehrere_leerzeichen_zaehlen_strich_nach_ziffer_nicht(self):
        """[REQ-MB-32] Strichrest mit mehreren Leerzeichen ("Akti-   onswürfel") zaehlt; "4- teiliges" (Ziffer vor dem Strich) zaehlt nicht. Faengt: genau ein Leerzeichen verlangt; Ziffer als Buchstabe."""
        self.deklariere()
        p = self.docling({1: [("section_header", "Kapitel"), ("text", "die Akti-   onswürfel")],
                          2: [("text", "ein 4- teiliges Set")]})
        self.assertEqual(p.strichrest, {"anzahl": 1, "seiten": [1]})

# ===================================================================================
# REQ-MB-33: Listentitel normalisiert
# ===================================================================================
UEBERSICHT_NFD = unicodedata.normalize("NFD", "Übersicht")
MB33_LESEZEICHEN = [("Kapitel\r\nZwei", 1), ("Teil  Drei\t", 2), (UEBERSICHT_NFD, 3), ("Teil\u00a0Vier", 4)]


class TestTitelNormalisiert(mb.BestandTest):
    def pdf(self):
        import pypdf
        w = pypdf.PdfWriter()
        for _ in range(4):
            w.add_blank_page(width=da.BREITE, height=da.HOEHE)
        for titel, seite in MB33_LESEZEICHEN:
            w.add_outline_item(titel, seite - 1)
        pfad = os.path.join(self.tmp.name, "titel.pdf")
        w.write(pfad)
        return pfad

    @unittest.skip("devloop: REQ-MB-33 noch nicht implementiert")
    def test_req_mb_33_lesezeichen_und_inhaltsverzeichnis_normalisiert(self):
        """[REQ-MB-33] Lesezeichen mit CR/LF, Doppelleerzeichen/Tab, NFD, NBSP (U+00A0) und Inhaltsverzeichnis-Titel mit CR/LF -> normalisierte Pfade, einzeiliger Vorsatz, Praefix-Zuweisung greift (auch mit unnormalisiertem Praefix)."""
        self.bestand([
            mb.buch("a", "Buch A", "alpha", quelle="a.pdf", ueberschriften={"quelle": "lesezeichen"},
                    seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True,
                    inhaltsarten=[(("Kapitel Zwei",), "welt")]),
            mb.buch("b", "Buch B", "alpha", quelle="b.pdf", ueberschriften={"quelle": "inhaltsverzeichnis", "eintraege": [
                {"titel": "Anhang\r\nEins", "ebene": 1, "seite": 1}]},
                seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True,
                inhaltsarten=[(("Anhang\nEins",), "welt")])])                  # Praefix bewusst unnormalisiert
        p = einlesen().lies_buch_ein(mb.SID, "a", {1: [z("Kapitel Zwei", "section_header"), z("Text zwei.")],
                                                   2: [z("Teil Drei", "section_header"), z("Text drei.")],
                                                   3: [z("Übersicht", "section_header"), z("Text uebersicht.")],
                                                   4: [z("Teil Vier", "section_header"), z("Text vier.")]},
                                     pdf=self.pdf())
        self.assertEqual(p.gefunden, [("Kapitel Zwei", 1), ("Teil Drei", 2), ("Übersicht", 3), ("Teil Vier", 4)])
        einlesen().lies_buch_ein(mb.SID, "b", {1: [z("Anhang Eins", "section_header"), z("Text anhang.")]})
        self.baue()
        chunks, _ = rag.lade_spiel(self.oeffne(), mb.SID)
        pfade = {(c["buch_id"], tuple(c["abschnittspfad"])): c for c in chunks}
        self.assertEqual(set(pfade), {("a", ("Kapitel Zwei",)), ("a", ("Teil Drei",)), ("a", ("Übersicht",)),
                                      ("a", ("Teil Vier",)), ("b", ("Anhang Eins",))})
        self.assertEqual(unicodedata.normalize("NFC", "Übersicht"), pfade[("a", ("Übersicht",))]["abschnittspfad"][0])
        for (bid, pfad), c in pfade.items():
            with self.subTest(pfad=pfad):
                vorsatz = rag.titelvorsatz(list(pfad))
                self.assertTrue(c["text"].startswith(vorsatz))
                self.assertEqual(vorsatz.count("\n"), 1)
                self.assertTrue(vorsatz.endswith("\n"))
                for schlecht in ("\r", "\t", "  ", "\u00a0"):
                    self.assertNotIn(schlecht, vorsatz)
                    self.assertFalse(any(schlecht in t for t in c["abschnittspfad"]))
                self.assertEqual(c["inhaltsart"], "welt" if pfad in (("Kapitel Zwei",), ("Anhang Eins",)) else "regel")

    @unittest.skip("devloop: REQ-MB-33 noch nicht implementiert")
    def test_req_mb_33_jedes_pfadelement_normalisiert(self):
        """[REQ-MB-33] Listentitel, ersetzte Zeile, Protokoll, Layout-Ueberschrift und Vorspann-Name mit titelnorm."""
        e = einlesen()
        p = e.Protokoll()
        seiten = {1: [z("Vorspanntext."), z("Kapitel  Zwei", "section_header"), z("Text."),
                      z(" Gamma \t Zeile ", "section_header"), z("Text gamma.")],
                  2: [z("Text auf Seite zwei.")]}
        abschnitte = e.baue_abschnitte(seiten, [{"titel": "Kapitel\r\nZwei", "ebene": 1, "seite": 1},
                                                {"titel": "Fehlt\r\nganz", "ebene": 1, "seite": 2}],
                                       layout={"klasse": "section_header"}, vorspann="Vor\r\nspann", protokoll=p)
        pfade = [a["abschnittspfad"] for a in abschnitte]
        self.assertIn(["Vor spann"], pfade)
        self.assertIn(["Kapitel Zwei", "Gamma Zeile"], pfade)
        self.assertIn(["Fehlt ganz"], pfade)
        kapitel = next(a for a in abschnitte if a["abschnittspfad"] == ["Kapitel Zwei"])
        self.assertTrue(kapitel["text"].startswith("Kapitel Zwei"))
        self.assertEqual(p.gefunden, [("Kapitel Zwei", 1)])
        self.assertEqual(p.nicht_gefunden, [("Fehlt ganz", 2)])


# ===================================================================================
# REQ-MB-34: Schema der Layout-/Rand-Deklaration
# ===================================================================================
GUELTIG_LAYOUT = {"klasse": "section_header", "veto": ["formula"], "hoechstlaenge": 40,
                  "stufen": [{"groesse": [13.5, 14.5], "laufweite": [-1, 1], "fett": True, "kursiv": False,
                              "kapitaelchen": False}, {"groesse": [11.5, 12.5]}]}
GUELTIG_RAND = {"kopf": 40, "fuss": 30}
VERSTOESSE = [  # (Name, layout, rand, Schluessel in der Meldung)
    ("Stufe groese", {"stufen": [{"groese": [10, 12]}]}, None, "groese"),
    ("layout groese", {"groese": [10, 12]}, None, "groese"),
    ("Stufe leer", {"stufen": [{}]}, None, "stufen"),
    ("groesse von > bis", {"stufen": [{"groesse": [14, 12]}]}, None, "groesse"),
    ("groesse ein Wert", {"stufen": [{"groesse": [12]}]}, None, "groesse"),
    ("rand Zeichenkette", None, {"kopf": "40"}, "kopf"),
    ("rand Wahrheitswert", None, {"kopf": True}, "kopf"),
    ("rand negativ", None, {"fuss": -5}, "fuss"),
    ("rand leer", None, {}, "rand"),
    ("veto Zeichenkette", {"veto": "table"}, None, "veto"),
    ("hoechstlaenge 0", {"hoechstlaenge": 0}, None, "hoechstlaenge"),
    ("eigene_zeile", {"eigene_zeile": True}, None, "eigene_zeile"),
    # Fassung 9: je Schemazweig ein Verstoss
    ("groesse von 0", {"stufen": [{"groesse": [0, 12]}]}, None, "groesse"),
    ("groesse negativ", {"stufen": [{"groesse": [-2, 12]}]}, None, "groesse"),
    ("laufweite von > bis", {"stufen": [{"laufweite": [2, 1]}]}, None, "laufweite"),
    ("laufweite Zeichenkette", {"stufen": [{"laufweite": ["0", "1"]}]}, None, "laufweite"),
    ("fett als Zahl", {"stufen": [{"fett": 1}]}, None, "fett"),
    ("kursiv als Text", {"stufen": [{"groesse": [10, 12], "kursiv": "ja"}]}, None, "kursiv"),
    ("klasse leer", {"klasse": ""}, None, "klasse"),
    ("klasse keine Zeichenkette", {"klasse": 5}, None, "klasse"),
    ("veto mit leerem Element", {"veto": ["table", ""]}, None, "veto"),
    ("veto mit Zahl", {"veto": [3]}, None, "veto"),
    ("stufen leer", {"stufen": []}, None, "stufen"),
    ("hoechstlaenge Kommazahl", {"hoechstlaenge": 2.5}, None, "hoechstlaenge"),
    ("hoechstlaenge Wahrheitswert", {"hoechstlaenge": True}, None, "hoechstlaenge"),
    ("rand unbekannter Schluessel", None, {"oben": 10}, "oben"),
]
SCHEMA_SEITEN = {1: [z("Kapitel", "section_header", S1, oben=100), z("Text Kapitel.", schrift=FT, oben=120),
                     z("Alpha", "section_header", S1, oben=140), z("Text Alpha.", schrift=FT, oben=160)]}


class TestSchema(mb.BestandTest):
    def deklariere(self, layout=None, rand=None):
        extra = {}
        if layout is not None:
            extra["layout"] = layout
        if rand is not None:
            extra["rand"] = rand
        self.bestand([mb.buch("nord", "Buch Nord", "alpha", ueberschriften={"quelle": "lesezeichen"},
                              seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True, **extra)])

    def lies(self, **kw):
        return einlesen().lies_buch_ein(mb.SID, "nord", SCHEMA_SEITEN, lesezeichen=[eintrag("Kapitel", 1)],
                                        seitenhoehe=SEITENHOEHE, **kw)

    @unittest.skip("devloop: REQ-MB-34 noch nicht implementiert")
    def test_req_mb_34_verstoesse_brechen_ab_ohne_zu_schreiben(self):
        """[REQ-MB-34] Je Schemaverstoss: KonfigFehler mit dem Schluessel, keine Buchdatei bzw. die alte byte-gleich."""
        for name, layout, rand, schluessel in VERSTOESSE:
            with self.subTest(fall=name):
                self.deklariere(layout, rand)
                if os.path.exists(self.buchdatei("nord")):
                    os.remove(self.buchdatei("nord"))
                with self.assertRaises(rag.KonfigFehler) as ctx:
                    self.lies()
                self.assertIn(schluessel, str(ctx.exception))
                self.assertFalse(os.path.exists(self.buchdatei("nord")))
                self.deklariere()
                self.lies()
                vorher = mb.hashes(os.path.dirname(self.buchdatei("nord")))
                self.deklariere(layout, rand)
                with self.assertRaises(rag.KonfigFehler):
                    self.lies(ueberschreiben=True)
                self.assertEqual(mb.hashes(os.path.dirname(self.buchdatei("nord"))), vorher)

    @unittest.skip("devloop: REQ-MB-34 noch nicht implementiert")
    def test_req_mb_34_gueltige_vollkonfiguration_liest_ein(self):
        """[REQ-MB-34] Gueltige Deklaration mit allen Schluesseln liest ein und ergibt dieselben Abschnitte wie baue_abschnitte."""
        self.deklariere(GUELTIG_LAYOUT, GUELTIG_RAND)
        self.lies()
        soll = einlesen().baue_abschnitte(SCHEMA_SEITEN, [eintrag("Kapitel", 1)], layout=GUELTIG_LAYOUT, rand=GUELTIG_RAND,
                                          seitenhoehe=SEITENHOEHE, protokoll=einlesen().Protokoll())
        with open(self.buchdatei("nord"), encoding="utf-8") as f:
            ist = [json.loads(x) for x in f]
        self.assertEqual([(e["abschnittspfad"], e["text"]) for e in ist], [(a["abschnittspfad"], a["text"]) for a in soll])
        self.assertIn(["Kapitel", "Alpha"], [e["abschnittspfad"] for e in ist])


if __name__ == "__main__":
    unittest.main(verbosity=2)
