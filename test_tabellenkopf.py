#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tabellenkopf je Haeppchen (Spec .specify/specs/einlese-qualitaet/spec.md, Abschnitt C2): REQ-EQ-21.

    python test_tabellenkopf.py

Spec-PR: jeder Test einzeln @unittest.skip("devloop: REQ-EQ-21 ..."), [REQ-EQ-21] im Docstring.
implement entfernt NUR das skip.

Kette im Test: Docling-Weg (einlesen.lies_pdf_ein mit Attrappe, Tabellen mit Raster und Markdown wie
Docling) -> Buchdatei -> rag.aktualisiere_index mit kleinem CHUNK_SIZE -> rag.lade_spiel. Sollwerte:
rag.zerteile auf dem Abschnittstext (zeichengenau, O-12) und der Kopftext nach dem Wortlaut der Spec.
Die Zeichenbereiche der Tabellen im Abschnittstext bestimmt der Test aus seinen eigenen, eindeutigen
synthetischen Tabellen (Orakel), nicht der Pruefling.

Vom Test erwartete Schnittstellen (aus der Spec abgeleitet, Namen hier festgelegt):
  Buchdeklaration "tabellenkopf": {} bzw. {"ausnahmen": [physische Seite, ...]}
  Buchdatei-Eintrag (Abschnitt) "tabellen": [{"bereich": [start, ende], "kopfbereich": [start, ende],
      "kopftext": str}, ...] in Tabellenreihenfolge -- Zeichenbereiche im Abschnittstext ("text"),
      nur fuer Tabellen mit Tabellenkopf ausserhalb der Ausnahmeseiten
  Haeppchentext = rag.titelvorsatz(pfad) + Tabellenkopf-Vorsaetze (Tabellenreihenfolge) + Stueck aus
      rag.zerteile(Abschnittstext, CHUNK_SIZE, CHUNK_OVERLAP) -- eingebettet und im Prompt (baue_kontext)
  Protokoll.tabellen_ohne_kopf = {"anzahl": n, "seiten": [gedruckt, sonst physisch]}
Lesart (Spec "Lesarten", EQ-21): Kopfbereich = die ersten zwei Markdown-Zeilen; "ganz enthalten" =
  beide Zeilen liegen im Haeppchen. Die Tests waehlen die Schnitte so, dass es nicht darauf ankommt,
  ob der Zeilenumbruch nach der Trennzeile zum Kopfbereich zaehlt.
"""
import os
import sys
import unittest
from unittest import mock

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402
import eq_attrappe as eqa  # noqa: E402

E = eqa.Element
SHY = eqa.SHY
KOPF_WUERFEL = "Würfeltabelle\nStufe | Würfel\n"


def kapitel(titel="Kapitel"):
    return E("section_header", titel, (40, 30, 555, 50))


def text(t, oben):
    return E("text", t, (40, oben, 290, oben + 20))


def wuerfeltabelle(n=30, titel="Würfeltabelle", oben=100):
    """Zeile 0 Titel (Spannzelle ueber beide Spalten), Zeile 1 column_header "Stufe | Würfel", n Datenzeilen."""
    zeilen = [[eqa.Spanne(titel, 2)], ["Stufe", "Würfel"]] + [[str(i), f"W{4 + 2 * (i % 5)}"] for i in range(1, n + 1)]
    return eqa.tabelle(zeilen, kopf=[1], lage=(40, oben, 290, oben + 300))


def bereiche(abschnittstext, md, anzahl=1):
    """Orakel: die Zeichenbereiche der (im Test eindeutigen) Tabelle md im Abschnittstext, in Reihenfolge."""
    out, ab = [], 0
    for _ in range(anzahl):
        ts = abschnittstext.index(md, ab)
        out.append((ts, ts + len(eqa.kopfbereich(md)), ts + len(md)))
        ab = ts + len(md)
    return out


def soll_vorsatz(tabellen, start, ende, abschnittstext):
    """Wortlaut REQ-EQ-21: Vorsatz je Tabelle, deren Bereich das Haeppchen [start, ende) mit mindestens
    einem Buchstaben oder einer Ziffer ueberlappt, ohne ihren Kopfbereich ganz zu enthalten."""
    out = ""
    for (ts, ke, te), kopftext in tabellen:
        teil = abschnittstext[max(start, ts):min(ende, te)]
        if any(ch.isalnum() for ch in teil) and not (start <= ts and ke <= ende):
            out += kopftext
    return out


class KopfTest(eqa.EQTest):
    def lies_tabellen(self, elemente, **spec2):
        self.deklariere(liste=tuple((e[0].text, s, 1) for s, e in sorted(elemente.items())), tabellenkopf={}, **spec2)
        return self.lies(elemente)

    def stuecke_pruefen(self, abschnitt, chunks, size, overlap, tabellen):
        """Jedes Haeppchen des Abschnitts == Titelvorsatz + Soll-Vorsatz + zerteile-Stueck; Rueckgabe: Vorsaetze."""
        text = abschnitt["text"]
        stuecke = rag.zerteile(text, size, overlap)
        eigene = [c for c in chunks if c["abschnittspfad"] == abschnitt["abschnittspfad"]]
        self.assertEqual(len(eigene), len(stuecke))
        vorsaetze = []
        for i, (c, stueck) in enumerate(zip(eigene, stuecke)):
            start = i * (size - overlap)
            soll = soll_vorsatz(tabellen, start, start + len(stueck), text)
            with self.subTest(haeppchen=i):
                self.assertEqual(c["text"], rag.titelvorsatz(abschnitt["abschnittspfad"]) + soll + stueck)
            vorsaetze.append(soll)
        return vorsaetze

    def vorsatz_im_rumpf(self, tab, md_im_text=None, **spec2):
        """Eine Tabelle; das 2. Haeppchen beginnt 5 Zeichen hinter ihrem Kopfbereich (im Rumpf). Rueckgabe:
        (Vorsatz des 2. Haeppchens, Protokoll, Abschnitt)."""
        p = self.lies_tabellen({1: [kapitel(), text("Vortext zur Tabelle.", 60), tab, text("Nachtext.", 700)]}, **spec2)
        md = md_im_text or tab._markdown
        a = self.abschnitt_von("Vortext")
        (ts, ke, te), = bereiche(a["text"], md)
        schritt, overlap = ke + 5, 40
        self.assertLess(schritt + 3, te)                                   # Vorbedingung: Haeppchen 2 beginnt im Rumpf
        chunks = self.haeppchen(schritt + overlap, overlap)
        stuecke = rag.zerteile(a["text"], schritt + overlap, overlap)
        c = [c for c in chunks if c["abschnittspfad"] == a["abschnittspfad"]][1]["text"]
        vor = rag.titelvorsatz(a["abschnittspfad"])
        self.assertTrue(c.startswith(vor) and c.endswith(stuecke[1]), c)
        return c[len(vor):len(c) - len(stuecke[1])], p, a


class TestTabellenkopf(KopfTest):
    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_titel_und_spaltenkopf_in_haeppchen_2_und_3(self):
        """[REQ-EQ-21] Titel (Spannzelle) + column_header "Stufe | Würfel" + 30 Datenzeilen ueber 3 Haeppchen: Haeppchen 2 und 3 tragen nach dem Titelvorsatz "Würfeltabelle⏎Stufe | Würfel⏎", Haeppchen 1 (mit Kopfbereich) nicht; ohne Vorsaetze == zerteile; eingebettet und im Prompt. Mutation "Vorsatz zaehlt zu CHUNK_SIZE" -> rot."""
        tab = wuerfeltabelle()
        self.lies_tabellen({1: [kapitel(), text("Vortext zur Tabelle.", 60), tab, text("Nachtext ohne Tabelle.", 700)]})
        a = self.abschnitt_von("Vortext")
        (ts, ke, te), = bereiche(a["text"], tab._markdown)
        overlap = 30
        size = len(a["text"]) // 3 + 1 + overlap
        stuecke = rag.zerteile(a["text"], size, overlap)
        self.assertEqual(len(stuecke), 3)                                  # Vorbedingungen der Konstruktion
        self.assertLessEqual(ke + 1, size)
        self.assertTrue(ke < size - overlap < te and 2 * (size - overlap) < te)
        chunks = self.haeppchen(size, overlap)
        vorsaetze = self.stuecke_pruefen(a, chunks, size, overlap, [((ts, ke, te), KOPF_WUERFEL)])
        self.assertEqual(vorsaetze, ["", KOPF_WUERFEL, KOPF_WUERFEL])
        eigene = [c["text"] for c in chunks]
        self.assertTrue(set(eigene) <= set(self.netz.eingebettet))        # so eingebettet
        self.assertIn(KOPF_WUERFEL, rag.baue_kontext([(chunks[1], 1.0)]))  # so im Prompt
        (t,) = a["tabellen"]                                               # Buchdatei: Bereich, Kopfbereich, Kopftext
        self.assertEqual(t["bereich"], [ts, te])
        self.assertEqual(t["kopfbereich"][0], ts)
        self.assertEqual(a["text"][t["kopfbereich"][0]:t["kopfbereich"][1]].rstrip("\n"), eqa.kopfbereich(tab._markdown))
        self.assertEqual(t["kopftext"], KOPF_WUERFEL)

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_unmarkierte_zeile_0_kein_kopf_auch_mit_titelzeile_in_zeile_2(self):
        """[REQ-EQ-21] Zeile 0 unmarkiert (Datenzeile), Titelzeile (alle Zellen gleich) in Zeile 2 -> kein Vorsatz, tabellen_ohne_kopf = 1 (S. 1). Mutation "Titelzeile mitten in der Tabelle als Kopf" -> rot."""
        zeilen = [["1", "W4"], ["2", "W6"], [eqa.Spanne("Zwischentitel", 2)]] + [[str(i), "W8"] for i in range(3, 30)]
        tab = eqa.tabelle(zeilen, kopf=[], lage=(40, 100, 290, 400))
        vorsatz, p, a = self.vorsatz_im_rumpf(tab)
        self.assertEqual(vorsatz, "")
        self.assertEqual(p.tabellen_ohne_kopf, {"anzahl": 1, "seiten": [1]})
        self.assertEqual(a.get("tabellen") or [], [])

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_leere_markierte_zeile_entfaellt(self):
        """[REQ-EQ-21] Zeile 0 column_header "Stufe | Würfel", Zeile 1 markiert, aber ohne Text -> Vorsatz nur aus Zeile 0."""
        zeilen = [["Stufe", "Würfel"], ["", ""]] + [[str(i), "W6"] for i in range(1, 30)]
        vorsatz, p, _ = self.vorsatz_im_rumpf(eqa.tabelle(zeilen, kopf=[0, 1], lage=(40, 100, 290, 400)))
        self.assertEqual(vorsatz, "Stufe | Würfel\n")
        self.assertEqual(p.tabellen_ohne_kopf, {"anzahl": 0, "seiten": []})

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_keine_datenzeile_im_kopf(self):
        """[REQ-EQ-21] Kopf endet an der ersten unmarkierten Zeile: column_header in Zeile 0, Datenzeile 1, Titelzeile in Zeile 2 -> Vorsatz nur "Stufe | Würfel⏎"."""
        zeilen = [["Stufe", "Würfel"], ["1", "W4"], [eqa.Spanne("Mittelteil", 2)]] + [[str(i), "W6"] for i in range(2, 30)]
        vorsatz, _, _ = self.vorsatz_im_rumpf(eqa.tabelle(zeilen, kopf=[0], lage=(40, 100, 290, 400)))
        self.assertEqual(vorsatz, "Stufe | Würfel\n")

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_weicher_trennstrich_im_kopf(self):
        """[REQ-EQ-21] Kopfzellen "Stu·fe", "Wür·fel" (U+00AD) -> Vorsatz ohne U+00AD; die Tabelle wird im Abschnittstext (ohne U+00AD, REQ-MB-11) gefunden."""
        zeilen = [[f"Stu{SHY}fe", f"Wür{SHY}fel"]] + [[str(i), "W6"] for i in range(1, 30)]
        tab = eqa.tabelle(zeilen, kopf=[0], lage=(40, 100, 290, 400))
        vorsatz, _, a = self.vorsatz_im_rumpf(tab, md_im_text=tab._markdown.replace(SHY, ""))
        self.assertEqual(vorsatz, "Stufe | Würfel\n")
        self.assertNotIn(SHY, a["text"])
        (t,) = a["tabellen"]
        self.assertEqual(a["text"][t["bereich"][0]:t["bereich"][1]], tab._markdown.replace(SHY, ""))

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_steuerzeichen_im_kopf_wird_leerzeichen(self):
        """[REQ-EQ-21] Kopfzelle "Wurf·Stufe" mit U+0007, Buch mit zeichen.steuerzeichen -> Vorsatz "Wurf Stufe | Würfel⏎", kein Steuerzeichen. Mutation "EQ-8 im Kopftext aus" -> rot."""
        zeilen = [["Wurf\x07Stufe", "Würfel"]] + [[str(i), "W6"] for i in range(1, 30)]
        tab = eqa.tabelle(zeilen, kopf=[0], lage=(40, 100, 290, 400))
        vorsatz, _, _ = self.vorsatz_im_rumpf(tab, md_im_text=tab._markdown.replace("\x07", " "),
                                              zeichen={"steuerzeichen": True})
        self.assertEqual(vorsatz, "Wurf Stufe | Würfel\n")
        self.assertFalse(any(ord(ch) < 32 and ch != "\n" for ch in vorsatz))

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_steuerzeichen_im_kopf_folgt_dem_schalter(self):
        """[REQ-EQ-21] K5: ohne zeichen.steuerzeichen (fehlend und false) wird auch im Kopftext nichts ersetzt -> Vorsatz "Wurf·Stufe | Würfel⏎" mit U+0007, wie im Tabellentext. Faengt: EQ-8 im Kopftext unabhaengig vom Schalter."""
        zeilen = [["Wurf\x07Stufe", "Würfel"]] + [[str(i), "W6"] for i in range(1, 30)]
        for zeichen in ({}, {"zeichen": {"steuerzeichen": False}}):
            with self.subTest(zeichen=zeichen):
                tab = eqa.tabelle(zeilen, kopf=[0], lage=(40, 100, 290, 400))
                vorsatz, _, a = self.vorsatz_im_rumpf(tab, **zeichen)
                self.assertEqual(vorsatz, "Wurf\x07Stufe | Würfel\n")
                self.assertIn("Wurf\x07Stufe", a["text"])

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_ausnahmeseite_kein_vorsatz(self):
        """[REQ-EQ-21] Tabelle mit Kopf auf einer Ausnahmeseite (tabellenkopf.ausnahmen = [1]) -> kein Vorsatz; dieselbe Tabelle auf Seite 2 (keine Ausnahme) -> Vorsatz."""
        self.deklariere(liste=(("Kapitel", 1, 1), ("Anhang", 2, 1)), tabellenkopf={"ausnahmen": [1]})
        elemente = {1: [kapitel(), text("Vortext zur Tabelle.", 60), wuerfeltabelle(), text("Nachtext.", 700)],
                    2: [kapitel("Anhang"), text("Anhangtext zur Tabelle.", 60), wuerfeltabelle(), text("Schluss.", 700)]}
        self.lies(elemente)
        chunks = self.haeppchen(120, 20)
        a = self.abschnitt_von("Vortext")
        self.stuecke_pruefen(a, chunks, 120, 20, [])
        self.assertTrue(len([c for c in chunks if c["abschnittspfad"] == a["abschnittspfad"]]) > 3)
        b = self.abschnitt_von("Anhangtext")
        vorsaetze = self.stuecke_pruefen(b, chunks, 120, 20,
                                         [(x, KOPF_WUERFEL) for x in bereiche(b["text"], elemente[2][2]._markdown)])
        self.assertIn(KOPF_WUERFEL, vorsaetze)

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_fuellzeichen_am_rand_kein_vorsatz(self):
        """[REQ-EQ-21] Haeppchen, das die Tabelle nur mit Fuellzeichen am Ende (Leerzeichen, "|") ueberlappt -> kein Vorsatz; beginnt es ein Zeichen frueher (letzte Ziffer/Buchstabe der Tabelle) -> Vorsatz. Mutation "Fuellzeichen-Bedingung aus" -> rot."""
        tab = wuerfeltabelle(n=12)
        self.lies_tabellen({1: [kapitel(), text("Vortext zur Tabelle.", 60), tab, text("Nachtext.", 700)]})
        a = self.abschnitt_von("Vortext")
        (ts, ke, te), = bereiche(a["text"], tab._markdown)
        letzte = max(i for i, ch in enumerate(tab._markdown) if ch.isalnum())
        self.assertTrue(set(tab._markdown[letzte + 1:]) <= set(" |"))      # Vorbedingung: nur Fuellzeichen dahinter
        for schritt, soll in ((ts + letzte + 1, ""), (ts + letzte, KOPF_WUERFEL)):
            with self.subTest(schritt=schritt - ts):
                chunks = self.haeppchen(schritt + 20, 20)
                vorsaetze = self.stuecke_pruefen(a, chunks, schritt + 20, 20, [((ts, ke, te), KOPF_WUERFEL)])
                self.assertEqual(vorsaetze[:2], ["", soll])

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_zwei_tabellen_in_einem_haeppchen_in_tabellenreihenfolge(self):
        """[REQ-EQ-21] Haeppchen ueber den Rumpf von Tabelle 1 und den Anfang des Kopfbereichs von Tabelle 2 (Kopfzeile, nicht ganz) -> zwei Vorsaetze in Tabellenreihenfolge. Mutation "nur erste Tabelle je Haeppchen" -> rot."""
        t1, t2 = wuerfeltabelle(n=10, titel="Erste Tabelle"), wuerfeltabelle(n=10, titel="Zweite Tabelle", oben=420)
        self.lies_tabellen({1: [kapitel(), text("Vortext zur Tabelle.", 60), t1, text("Zwischentext.", 405), t2,
                                text("Nachtext.", 740)]})
        a = self.abschnitt_von("Vortext")
        (b1,), (b2,) = bereiche(a["text"], t1._markdown), bereiche(a["text"], t2._markdown)
        schritt = b1[1] + 5
        ende = b2[0] + len(t2._markdown.split("\n")[0]) + 3                # in der Trennzeile von Tabelle 2
        size = ende - schritt
        self.assertTrue(b1[1] < schritt < b1[2] and b2[0] < ende < b2[1] and size > schritt)
        kopf1, kopf2 = "Erste Tabelle\nStufe | Würfel\n", "Zweite Tabelle\nStufe | Würfel\n"
        chunks = self.haeppchen(size, size - schritt)
        vorsaetze = self.stuecke_pruefen(a, chunks, size, size - schritt, [(b1, kopf1), (b2, kopf2)])
        self.assertEqual(vorsaetze[1], kopf1 + kopf2)

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_textgleiche_tabellen_ueber_die_lage_zugeordnet(self):
        """[REQ-EQ-21] Dieselbe Tabelle in zwei Abschnitten und zweimal in einem dritten -> jeder Abschnitt hat genau seine Tabellen (1, 1, 2), kein doppelter und kein fehlender Vorsatz. Mutation "Zuordnung ueber Textsuche statt Lage" -> rot."""
        def tab(oben):
            return wuerfeltabelle(n=8, oben=oben)
        elemente = {1: [kapitel("Erster Teil"), tab(100)], 2: [kapitel("Zweiter Teil"), tab(100)],
                    3: [kapitel("Dritter Teil"), tab(100), text("Zwischen den Tabellen.", 405), tab(430)]}
        self.lies_tabellen(elemente)
        md = elemente[1][1]._markdown
        size, overlap = 90, 15
        chunks = self.haeppchen(size, overlap)
        for titel, anzahl in (("Erster Teil", 1), ("Zweiter Teil", 1), ("Dritter Teil", 2)):
            with self.subTest(abschnitt=titel):
                (a,) = [e for e in self.eintraege() if e["abschnittspfad"] == [titel]]
                tabellen = [(b, KOPF_WUERFEL) for b in bereiche(a["text"], md, anzahl)]
                self.assertEqual(len(a["tabellen"]), anzahl)
                self.assertEqual([t["bereich"] for t in a["tabellen"]], [[b[0], b[2]] for b, _ in tabellen])
                vorsaetze = self.stuecke_pruefen(a, chunks, size, overlap, tabellen)
                self.assertTrue(any(vorsaetze))
                self.assertTrue(all(v.count(KOPF_WUERFEL) <= anzahl for v in vorsaetze))

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_bereich_folgt_spaeteren_textaenderungen(self):
        """[REQ-EQ-21] "Verteidi- gung" vor der Tabelle wird durch EQ-6 zu "Verteidigung" (2 Zeichen kuerzer) -> Bereich und Kopfbereich verschieben mit: Haeppchen 1 endet direkt hinter dem Kopfbereich und bekommt keinen Vorsatz, Haeppchen 2 bekommt ihn."""
        z = eqa.Zeichnung()
        z.zeile(1, 40, 45, "Kapitel", "Helvetica-Bold", 12)
        e1 = z.block(1, 40, 100, ["Die Verteidi-"])
        e2 = z.block(1, 40, 112, ["gung hält stand."])
        tab = wuerfeltabelle(oben=200)
        elemente = {1: [kapitel(), E("text", "Die Verteidi-", e1), E("text", "gung hält stand.", e2), tab]}
        self.deklariere(tabellenkopf={}, lesefolge=eqa.LESEFOLGE, striche={"strichrest": True})
        self.lies(elemente, self.pdf_aus(z))
        a = self.abschnitt_von("Verteidigung")
        (ts, ke, te), = bereiche(a["text"], tab._markdown)
        (t,) = a["tabellen"]
        self.assertEqual(t["bereich"], [ts, te])
        size, overlap = ke + 1, 10
        chunks = self.haeppchen(size, overlap)
        vorsaetze = self.stuecke_pruefen(a, chunks, size, overlap, [((ts, ke, te), KOPF_WUERFEL)])
        self.assertEqual(vorsaetze[:2], ["", KOPF_WUERFEL])

    @unittest.skip("devloop: REQ-EQ-21 noch nicht implementiert")
    def test_req_eq_21_ohne_tabellenkopf_index_inhalt_byte_gleich(self):
        """[REQ-EQ-21] Ohne "tabellenkopf": Buchdatei und Haeppchen (rag.buch_stuecke) byte-gleich zum Stand vor der Spec (einlesen.py und rag.py aus BASIS_COMMIT)."""
        elemente = {1: [kapitel(), text("Vortext zur Tabelle.", 60), wuerfeltabelle(), text("Nachtext.", 700)]}
        pdf = self.pdf_leer(1)
        alt_rag, _ = eqa.alte_module()
        self.deklariere()
        self.lies_alt(elemente, pdf)
        alt_roh, alt_eintraege = self.roh(), self.eintraege()
        buch = rag.lies_buecher(eqa.mb.SID)[0]
        self.lies(elemente, pdf)
        self.assertEqual(self.roh(), alt_roh)
        for size, overlap in ((120, 20), (400, 150)):
            with self.subTest(size=size):
                self.assertEqual(rag.buch_stuecke(self.eintraege(), buch, size, overlap),
                                 alt_rag.buch_stuecke(alt_eintraege, buch, size, overlap))
        with mock.patch.multiple(rag, CHUNK_SIZE=120, CHUNK_OVERLAP=20):
            self.baue()
        self.assertFalse(any(KOPF_WUERFEL in t for t in self.netz.eingebettet))


if __name__ == "__main__":
    unittest.main(verbosity=2)
