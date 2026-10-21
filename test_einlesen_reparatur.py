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
"""
import importlib
import os
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


def z(text, klasse="text"):
    return {"text": text, "klasse": klasse}


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
                seiten = {6: [z("Vorspann ohne Titel.")], 7: [z(zeile, "section_header"), z("Fliesstext dazu.")]}
                abschnitte, p = self.baue(seiten, [eintrag("Vorspann", 6), eintrag(titel, 7)])
                a = nach_pfad(abschnitte)[(titel,)]
                self.assertTrue(a["text"].startswith(titel), a["text"])
                self.assertNotIn(zeile, a["text"].replace(titel, ""))
                self.assertIn("Fliesstext dazu.", a["text"])
                self.assertNotIn(zeile, "".join(b["text"] for b in abschnitte).replace(titel, ""))
                self.assertIn((titel, 7), p.gefunden)
                self.assertEqual(p.nicht_gefunden, [("Vorspann", 6)])

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
        abschnitte, p = self.baue(seiten, [eintrag("Vorspann", 7), eintrag("Bonuswürfel", 7)])
        pfade = nach_pfad(abschnitte)
        self.assertIn("Bonusw rfel", pfade[("Vorspann",)]["text"])
        self.assertIn("Vorher.", pfade[("Vorspann",)]["text"])
        self.assertTrue(pfade[("Bonuswürfel",)]["text"].startswith("Bonuswürfel"))
        self.assertIn("Nachher.", pfade[("Bonuswürfel",)]["text"])
        self.assertNotIn("BONUSWÜRFEL", pfade[("Bonuswürfel",)]["text"])
        self.assertEqual(p.mehrdeutig, [])

    @unittest.skip("devloop: REQ-MB-12 noch nicht implementiert")
    def test_req_mb_12_eine_zeile_hoechstens_ein_eintrag(self):
        """[REQ-MB-12] Eine Zeile wird hoechstens einem Eintrag zugeordnet (Listenreihenfolge); der zweite ist nicht gefunden."""
        seiten = {7: [z("Ablauf", "section_header"), z("Text zum Ablauf.")]}
        abschnitte, p = self.baue(seiten, [eintrag("Ablauf", 7, 1), eintrag("Ablauf", 7, 2)])
        self.assertEqual(p.gefunden, [("Ablauf", 7)])
        self.assertEqual(p.nicht_gefunden, [("Ablauf", 7)])
        # kein Eintrag verschwindet (REQ-MB-13); WO der zweite beginnt, laesst die Spec offen
        self.assertEqual(sorted(tuple(a["abschnittspfad"]) for a in abschnitte), [("Ablauf",), ("Ablauf", "Ablauf")])
        self.assertEqual(sum(a["text"].count("Text zum Ablauf.") for a in abschnitte), 1)

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
        """[REQ-MB-13] Eintrag ohne Gegenstueck: Abschnitt beginnt am Anfang der Zielseite, Protokoll nennt Titel und Seite."""
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
        """[REQ-MB-20] Zeilen mit allen Merkmalen -> K1 > U1 > Alpha / Beta; "Gamma" ohne Merkmale bleibt Fliesstext in Beta."""
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
    def test_req_mb_20_alle_merkmale_muessen_passen(self):
        """[REQ-MB-20] Layout-Ueberschrift genau dann, wenn ALLE deklarierten Merkmale passen (hier Klasse UND Hoechstlaenge)."""
        e = einlesen()
        seiten = {1: [z("K1", "section_header"), z("Einleitung."),
                      z("Kurz", "section_header"), z("Text kurz."),
                      z("Diese Kopfzeile ist zu lang", "section_header"), z("Text lang.")]}
        p = e.Protokoll()
        abschnitte = e.baue_abschnitte(seiten, [eintrag("K1", 1)],
                                       layout={"klasse": "section_header", "hoechstlaenge": 10}, protokoll=p)
        self.assertEqual([a["abschnittspfad"] for a in abschnitte], [["K1"], ["K1", "Kurz"]])
        self.assertIn("Diese Kopfzeile ist zu lang", abschnitte[1]["text"])
        self.assertEqual({k: v for k, v in p.layout_ueberschriften.items() if v}, {("K1",): 1})

    @unittest.skip("devloop: REQ-MB-20 noch nicht implementiert")
    def test_req_mb_20_nicht_gegen_die_liste_abgeglichen(self):
        """[REQ-MB-20] Layout-Ueberschriften werden nicht gegen die Liste abgeglichen oder ersetzt: Zeile bleibt, wie sie ist."""
        e = einlesen()
        seiten = {1: [z("K1", "section_header"), z("Einleitung."), z("Bonusw rfel", "section_header"), z("Text.")]}
        abschnitte = e.baue_abschnitte(seiten, [eintrag("K1", 1)], layout={"klasse": "section_header"},
                                       protokoll=e.Protokoll())
        self.assertEqual([a["abschnittspfad"] for a in abschnitte], [["K1"], ["K1", "Bonusw rfel"]])


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
