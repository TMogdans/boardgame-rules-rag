#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Striche und Zeichen (Spec .specify/specs/einlese-qualitaet/spec.md, Abschnitt C): REQ-EQ-5
Zeilenend-Striche aus der Quelle, REQ-EQ-6 Strichrest mit Quellnachweis, REQ-EQ-7 Zierschrift-Umlaut,
REQ-EQ-8 Steuerzeichen, REQ-EQ-10 Listennummern.

    python test_striche_zeichen.py

Spec-PR: jeder Test einzeln @unittest.skip("devloop: REQ-EQ-<n> ..."), [REQ-EQ-<n>] im Docstring.
implement entfernt NUR das skip.

Weg: Docling-Weg einlesen.lies_pdf_ein mit Docling-Attrappe (eq_attrappe.py) und einem im Test mit
reportlab erzeugten PDF (echtes pdfplumber, wie REQ-MB-29). Die Docling-Texte sind bewusst so
gewaehlt, wie Docling sie liefert (Striche verloren, "Akti- onswürfel"), die PDF-Zeilen sind die
Quelle. Alle Woerter frei erfunden.

Vom Test erwartete Schnittstellen (aus der Spec abgeleitet, Namen hier festgelegt):
  Buchdeklaration "striche": {"zeilenenden": bool, "strichrest": bool}
                  "zeichen":  {"zierumlaut": bool, "steuerzeichen": bool, "listennummern": bool}
                  "reparatur": {"an": true, "konjunktionen": [...]}  Konjunktionsliste (REQ-MB-11)
  Protokoll.zeilenenden = {"geaendert": {"strich": n, "trennung": n, "konjunktion": n},
                           "gesichert": n, "unveraendert": n, "mehrdeutig": n, "nicht_gefunden": n}  (REQ-EQ-5)
  Protokoll.strich_vor_grossbuchstabe = {"anzahl": n, "seiten": [gedruckt, sonst physisch]}       (REQ-EQ-6)
  Docling list_item: item.enumerated (bool), item.marker (str), item.text ohne Nummer          (REQ-EQ-10)
"""
import os
import sys
import unittest

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import eq_attrappe as eqa  # noqa: E402

E = eqa.Element
SHY = eqa.SHY
NULL = {"geaendert": {"strich": 0, "trennung": 0, "konjunktion": 0}, "gesichert": 0, "unveraendert": 0,
        "mehrdeutig": 0, "nicht_gefunden": 0}


def zaehler(**werte):
    """Erwartete Zeilenend-Zaehler; geaendert_strich=2 usw. fuer die Unterzaehler."""
    z = {"geaendert": dict(NULL["geaendert"]), **{k: v for k, v in NULL.items() if k != "geaendert"}}
    for k, v in werte.items():
        if k.startswith("geaendert_"):
            z["geaendert"][k[len("geaendert_"):]] = v
        else:
            z[k] = v
    return z


class SeitenBau:
    """Elemente in der linken Spalte untereinander (je Block 40 pt), PDF-Zeilen passend dazu."""

    def __init__(self):
        self.z = eqa.Zeichnung()
        self.elemente = {}
        self.naechst = {}

    def kopf(self, seite, text):
        self.z.zeile(seite, 40, 45, text, "Helvetica-Bold", 12)
        self.elemente.setdefault(seite, []).append(E("section_header", text, (38, 30, 555, 50)))
        self.naechst[seite] = 100

    def element(self, seite, zeilen, text, label="text", x=40, grund=None):
        grund = grund if grund is not None else self.naechst.get(seite, 100)
        lage = self.z.block(seite, x, grund, zeilen)
        self.elemente.setdefault(seite, []).append(E(label, text, lage))
        self.naechst[seite] = grund + 12 * len(zeilen) + 28
        return lage


def spec_faelle(mit_throals_anderswo=True, shy=False):
    """Die Zeilenenden des Detektors von REQ-EQ-5 (Docling-Texte ohne die Striche der Quelle)."""
    b = SeitenBau()
    b.kopf(1, "Kapitel")
    b.element(1, ["Das Novizen-", "Talent wirkt."], f"Das Novizen{SHY}Talent wirkt." if shy else "Das NovizenTalent wirkt.")
    b.element(1, ["Ein W8-", "Würfel rollt."], "Ein W8Würfel rollt.")
    b.element(1, ["Im Nah-", "und Fernkampf."], "Im Nahund Fernkampf.")
    b.element(1, ["Die Akti-", "onswürfel fallen."], "Die Akti- onswürfel fallen.")
    b.element(1, ["Aus Bur-", "gund kommt Wein."], "Aus Burgund kommt Wein.")
    b.element(1, ["Nach Thro-", "als Mauern."], "Nach Throals Mauern.")
    if mit_throals_anderswo:
        b.element(1, ["Die Feste Throals steht."], "Die Feste Throals steht.")
    return b


class StrichTest(eqa.EQTest):
    def lies_bau(self, bau, **spec2):
        self.deklariere(**spec2)
        return self.lies(bau.elemente, self.pdf_aus(bau.z, max(bau.elemente)))


ZEILENENDEN = {"striche": {"zeilenenden": True}}


# ===================================================================================
# REQ-EQ-5: Zeilenend-Striche aus der Quelle
# ===================================================================================
class TestZeilenenden(StrichTest):
    @unittest.skip("devloop: REQ-EQ-5 noch nicht implementiert")
    def test_req_eq_5_faelle_der_spec_und_zaehler(self):
        """[REQ-EQ-5] Novizen-⏎Talent, W8-⏎Würfel, Nah-⏎und, Akti-⏎onswürfel, Bur-⏎gund, Thro-⏎als (Throals anderswo im Buch) -> Novizen-Talent, W8-Würfel, Nah- und, Aktionswürfel, Burgund, Throals; Zaehler exakt. Mutationen "Sicherung aus" und "Konjunktion ignorieren" -> rot."""
        p = self.lies_bau(spec_faelle(), **ZEILENENDEN)
        text = self.gesamttext()
        for soll in ("Das Novizen-Talent wirkt.", "Ein W8-Würfel rollt.", "Im Nah- und Fernkampf.",
                     "Die Aktionswürfel fallen.", "Aus Burgund kommt Wein.", "Nach Throals Mauern."):
            self.assertIn(soll, text)
        for falsch in ("NovizenTalent", "W8Würfel", "Nahund", "Akti- onswürfel", "Bur-gund", "Bur- gund", "Thro- als"):
            self.assertNotIn(falsch, text)
        self.assertEqual(p.zeilenenden, zaehler(geaendert_strich=2, geaendert_trennung=1, geaendert_konjunktion=1,
                                                gesichert=1, unveraendert=1))
        self.assertEqual(self.protokoll_datei()["zeilenenden"], p.zeilenenden)

    @unittest.skip("devloop: REQ-EQ-5 noch nicht implementiert")
    def test_req_eq_5_sicherung_zaehlt_das_eigene_element_nicht(self):
        """[REQ-EQ-5] Thro-⏎als ohne weiteres "Throals" im Buch: das eigene Vorkommen zaehlt nicht -> Sollform "Thro- als", geaendert (Konjunktion), nicht gesichert."""
        p = self.lies_bau(spec_faelle(mit_throals_anderswo=False), **ZEILENENDEN)
        self.assertIn("Nach Thro- als Mauern.", self.gesamttext())
        self.assertEqual(p.zeilenenden, zaehler(geaendert_strich=2, geaendert_trennung=1, geaendert_konjunktion=2,
                                                unveraendert=1))

    @unittest.skip("devloop: REQ-EQ-5 noch nicht implementiert")
    def test_req_eq_5_zweimal_im_element_ist_mehrdeutig(self):
        """[REQ-EQ-5] "NovizenTalent" zweimal im selben Element -> mehrdeutig = 1, Text unveraendert."""
        b = SeitenBau()
        b.kopf(1, "Kapitel")
        b.element(1, ["Ein Novizen-", "Talent und ein NovizenTalent."], "Ein NovizenTalent und ein NovizenTalent.")
        p = self.lies_bau(b, **ZEILENENDEN)
        self.assertIn("Ein NovizenTalent und ein NovizenTalent.", self.gesamttext())
        self.assertEqual(p.zeilenenden, zaehler(mehrdeutig=1))

    @unittest.skip("devloop: REQ-EQ-5 noch nicht implementiert")
    def test_req_eq_5_weicher_trennstrich_wird_vorher_entfernt(self):
        """[REQ-EQ-5] Elementtext "Novizen·Talent" (U+00AD): Arbeitsbasis ohne U+00AD -> gefunden, "Novizen-Talent". Mutation "U+00AD nach EQ-5 entfernen" -> rot."""
        b = SeitenBau()
        b.kopf(1, "Kapitel")
        b.element(1, ["Das Novizen-", "Talent wirkt."], f"Das Novizen{SHY}Talent wirkt.")
        p = self.lies_bau(b, **ZEILENENDEN)
        text = self.gesamttext()
        self.assertIn("Das Novizen-Talent wirkt.", text)
        self.assertNotIn(SHY, text)
        self.assertEqual(p.zeilenenden, zaehler(geaendert_strich=1))

    @unittest.skip("devloop: REQ-EQ-5 noch nicht implementiert")
    def test_req_eq_5_keine_folgezeile_ueber_kasten_und_elementgrenze(self):
        """[REQ-EQ-5] Letzte Zeile eines Kastens "...Feuer-", der naechste Kasten (anderes Element) beginnt "Kraft"; ebenso zwei Kaesten EINES Elements ("Eis-" / "Zapfen") -> kein Fall, Texte unveraendert, alle Zaehler 0. Mutation "Folgezeile ueber Kastengrenze hinweg" -> rot ("Feuer-Kraft", "Eis-Zapfen")."""
        b = SeitenBau()
        b.kopf(1, "Kapitel")
        b.element(1, ["Die Feuer Kraft ist", "groß im Feuer-"], "Die Feuer Kraft ist groß im Feuer-")
        b.element(1, ["Kraft wirkt hier."], "Kraft wirkt hier.")
        k1 = b.z.block(1, 40, 400, ["Die Eis Zapfen sind", "kalt im Eis-"])
        k2 = b.z.block(1, 310, 100, ["Zapfen fallen."])
        b.elemente[1].append(E("text", "Die Eis Zapfen sind kalt. Sie fallen.", k1, weitere_kaesten=[k2]))
        p = self.lies_bau(b, **ZEILENENDEN)
        text = self.gesamttext()
        self.assertIn("Die Feuer Kraft ist groß im Feuer- Kraft wirkt hier.", text)
        self.assertIn("Die Eis Zapfen sind kalt. Sie fallen.", text)
        self.assertEqual(p.zeilenenden, NULL)

    @unittest.skip("devloop: REQ-EQ-5 noch nicht implementiert")
    def test_req_eq_5_grundlinien_als_kette(self):
        """[REQ-EQ-5] Zeile "Das Novizen-" aus Stuecken mit Grundlinie +0/+1/+2 pt: Kette (Abstand zum LETZTEN Wert der Gruppe) -> eine Zeile, Fall gefunden; mit Anker (erster Wert) waere "-" eine eigene Zeile. Faengt: Anker-Lesart (Fassung 3)."""
        b = SeitenBau()
        b.kopf(1, "Kapitel")
        w = b.z.stuecke(1, 40, 100, [("Das Novi", 0), ("zen", 1), ("-", 2)])
        w = max(w, b.z.zeile(1, 40, 112, "Talent wirkt."))
        b.elemente[1].append(E("text", "Das NovizenTalent wirkt.", (38, 89, 40 + w + 2, 118)))
        p = self.lies_bau(b, **ZEILENENDEN)
        self.assertIn("Das Novizen-Talent wirkt.", self.gesamttext())
        self.assertEqual(p.zeilenenden, zaehler(geaendert_strich=1))

    @unittest.skip("devloop: REQ-EQ-5 noch nicht implementiert")
    def test_req_eq_5_zeichen_gehen_an_den_kleinsten_kasten(self):
        """[REQ-EQ-5] Zweite Zeile liegt auch im kleineren Kasten einer Bildunterschrift -> sie gehoert dorthin; das grosse Element hat nur "Ein Novizen-" ohne Folgezeile -> unveraendert, Zaehler 0. Faengt: erster statt kleinster Kasten."""
        b = SeitenBau()
        b.kopf(1, "Kapitel")
        b.z.zeile(1, 40, 100, "Ein Novizen-")
        w = b.z.zeile(1, 40, 112, "Talent hier.")
        b.elemente[1] += [E("text", "Ein NovizenTalent hier.", (38, 89, 300, 130)),
                          E("caption", "Talent hier.", (38, 102, 40 + w + 2, 116))]
        p = self.lies_bau(b, **ZEILENENDEN)
        self.assertIn("Ein NovizenTalent hier.", self.gesamttext())
        self.assertEqual(p.zeilenenden, NULL)

    @unittest.skip("devloop: REQ-EQ-5 noch nicht implementiert")
    def test_req_eq_5_form_nicht_im_element_ist_nicht_gefunden(self):
        """[REQ-EQ-5] Quelle "Feuer-⏎ball", Docling-Text ohne eine der vier Formen -> nicht_gefunden = 1, Text unveraendert."""
        b = SeitenBau()
        b.kopf(1, "Kapitel")
        b.element(1, ["Ein Feuer-", "ball fliegt."], "Ein Flammenball fliegt.")
        p = self.lies_bau(b, **ZEILENENDEN)
        self.assertIn("Ein Flammenball fliegt.", self.gesamttext())
        self.assertEqual(p.zeilenenden, zaehler(nicht_gefunden=1))

    @unittest.skip("devloop: REQ-EQ-5 noch nicht implementiert")
    def test_req_eq_5_tabellen_werden_nicht_bearbeitet(self):
        """[REQ-EQ-5] Tabellenkasten mit den Quellzeilen "Feuer-" / "ball Wert", Markdown "| Feuer ball |" -> Tabellentext unveraendert; derselbe Fall in einem Text-Element daneben wird bearbeitet."""
        b = SeitenBau()
        b.kopf(1, "Kapitel")
        lage = b.z.block(1, 40, 100, ["Feuer-", "ball Wert"])
        b.elemente[1].append(eqa.tabelle([["Feuer ball", "Wert"], ["1", "2"]], kopf=[0], lage=lage))
        b.element(1, ["Ein Feuer-", "ball fliegt."], "Ein Feuer ball fliegt.", grund=200)
        self.lies_bau(b, **ZEILENENDEN)
        self.assertIn("| Feuer ball |", self.gesamttext())
        self.assertIn("Ein Feuerball fliegt.", self.gesamttext())

    @unittest.skip("devloop: REQ-EQ-5 noch nicht implementiert")
    def test_req_eq_5_ohne_striche_byte_gleich(self):
        """[REQ-EQ-5] Ohne "striche" -> Buchdatei byte-gleich zum Stand vor der Spec; "zeilenenden": false ebenso."""
        b = spec_faelle()
        pdf = self.pdf_aus(b.z)
        self.deklariere()
        self.lies_alt(b.elemente, pdf)
        alt = self.roh()
        self.lies(b.elemente, pdf)
        self.assertEqual(self.roh(), alt)
        self.deklariere(striche={"zeilenenden": False})
        self.lies(b.elemente, pdf)
        self.assertEqual(self.roh(), alt)


# ===================================================================================
# REQ-EQ-6: Strichrest mit Quellnachweis
# ===================================================================================
STRICHREST = {"lesefolge": eqa.LESEFOLGE, "striche": {"strichrest": True}}


def spalten_fall(links_letzte, rechts_erste, rechts_text, links_davor="Erste Zeile links."):
    """Links: Block, dessen letzte Quellzeile links_letzte ist (Docling-Text endet darauf); rechts oben:
    Quellzeile rechts_erste, Docling-Text rechts_text."""
    b = SeitenBau()
    b.kopf(1, "Kapitel")
    b.element(1, [links_davor, links_letzte], f"{links_davor} {links_letzte}")
    b.element(1, [rechts_erste], rechts_text, x=310, grund=100)
    return b


class TestStrichrest(StrichTest):
    @unittest.skip("devloop: REQ-EQ-6 noch nicht implementiert")
    def test_req_eq_6_verteidi_gung_ueber_die_spalten_mit_nachweis(self):
        """[REQ-EQ-6] Links unten endet eine Quellzeile auf "Verteidi-", rechts oben beginnt eine mit "gung"; Docling: Element 1 endet "Verteidi-", Element 2 beginnt "gung" -> "Verteidigung"."""
        self.lies_bau(spalten_fall("Die Verteidi-", "gung hält stand.", "gung hält stand."), **STRICHREST)
        text = self.gesamttext()
        self.assertIn("Die Verteidigung hält stand.", text)
        self.assertNotIn("Verteidi- gung", text)

    @unittest.skip("devloop: REQ-EQ-6 noch nicht implementiert")
    def test_req_eq_6_ohne_nachweis_unveraendert(self):
        """[REQ-EQ-6] Dieselbe Quelle, aber Element 2 beginnt mit "durch" (die Fortsetzung steht anderswo) -> "Verteidi- durch" unveraendert, kein strich_vor_grossbuchstabe. Mutation "Nachweis aus" -> rot."""
        p = self.lies_bau(spalten_fall("Die Verteidi-", "gung hält stand.", "durch die Mauer."), **STRICHREST)
        text = self.gesamttext()
        self.assertIn("Die Verteidi- durch die Mauer.", text)
        self.assertNotIn("Verteididurch", text)
        self.assertEqual(p.strich_vor_grossbuchstabe, {"anzahl": 0, "seiten": []})

    @unittest.skip("devloop: REQ-EQ-6 noch nicht implementiert")
    def test_req_eq_6_konjunktion_aus_der_liste_bleibt(self):
        """[REQ-EQ-6] "Fertigkeits- als auch" mit Nachweis, Liste mit "als" -> unveraendert; dieselbe Quelle mit einer Liste ohne "als" -> "Fertigkeitsals" (die Liste ist Datum der Buchdeklaration)."""
        bau = spalten_fall("Die Fertigkeits-", "als auch Talente.", "als auch Talente.")
        self.lies_bau(bau, **STRICHREST)
        self.assertIn("Die Fertigkeits- als auch Talente.", self.gesamttext())
        self.deklariere(eqa.buchdekl(konjunktionen=["und", "oder"], **STRICHREST))
        self.lies(bau.elemente, self.pdf_aus(bau.z))
        self.assertIn("Die Fertigkeitsals auch Talente.", self.gesamttext())

    @unittest.skip("devloop: REQ-EQ-6 noch nicht implementiert")
    def test_req_eq_6_grossbuchstabe_nie_auch_mit_nachweis(self):
        """[REQ-EQ-6] "Karma- Modifikator" mit Quellzeilen "Der Karma-" / "Modifikator wirkt." -> unveraendert, strich_vor_grossbuchstabe = 1 (S. 1). Mutationen "Grossbuchstabe zusammenfuegen" und "belegter Grossbuchstabe -> X-Y" -> rot."""
        b = SeitenBau()
        b.kopf(1, "Kapitel")
        b.element(1, ["Der Karma-", "Modifikator wirkt."], "Der Karma- Modifikator wirkt.")
        p = self.lies_bau(b, **STRICHREST)
        text = self.gesamttext()
        self.assertIn("Der Karma- Modifikator wirkt.", text)
        self.assertNotIn("KarmaModifikator", text)
        self.assertNotIn("Karma-Modifikator", text)
        self.assertEqual(p.strich_vor_grossbuchstabe, {"anzahl": 1, "seiten": [1]})
        self.assertEqual(self.protokoll_datei()["strich_vor_grossbuchstabe"], {"anzahl": 1, "seiten": [1]})

    @unittest.skip("devloop: REQ-EQ-6 noch nicht implementiert")
    def test_req_eq_6_flussbruch_vor_grossbuchstabe_nur_gezaehlt(self):
        """[REQ-EQ-6] Flussbruch "beispiels- Die" (rechts oben beginnt ein Block mit "Die") -> unveraendert, gezaehlt (strich_vor_grossbuchstabe = 1). Faengt: lockerer Nachweis ueber den Blockanfang ("beispiels-Die")."""
        p = self.lies_bau(spalten_fall("zum beispiels-", "Die Regel gilt.", "Die Regel gilt."), **STRICHREST)
        text = self.gesamttext()
        self.assertIn("zum beispiels- Die Regel gilt.", text)
        self.assertNotIn("beispiels-Die", text)
        self.assertNotIn("beispielsDie", text)
        self.assertEqual(p.strich_vor_grossbuchstabe, {"anzahl": 1, "seiten": [1]})

    @unittest.skip("devloop: REQ-EQ-6 noch nicht implementiert")
    def test_req_eq_6_gro_sser_nur_mit_der_neuen_folge(self):
        """[REQ-EQ-6] Passionsseite, Docling setzt "durch …" (links unter Kopf B) hinter "gro-": mit Lesefolge (EQ-3) folgt "ßer …" (rechts oben) -> "großer"; auf einer Lesefolge-Ausnahmeseite bleibt "gro- durch" (kein Nachweis)."""
        z = eqa.Zeichnung()
        z.zeile(1, 40, 45, "Kapitel", "Helvetica-Bold", 12)
        ka = z.block(1, 40, 112, ["Passion Alpha"])
        a1 = z.block(1, 40, 140, ["Alpha Text eins.", "Der Wert ist gro-"])
        kb = z.block(1, 40, 412, ["Passion Beta"])
        b1 = z.block(1, 40, 428, ["durch Magie stark."])
        a2 = z.block(1, 310, 112, ["ßer als sonst."])
        b2 = z.block(1, 310, 440, ["Beta rechts Text."])
        elemente = {1: [E("section_header", "Kapitel", (38, 30, 555, 50)), E("section_header", "Passion Alpha", ka),
                        E("text", "Alpha Text eins. Der Wert ist gro-", a1), E("text", "durch Magie stark.", b1),
                        E("section_header", "Passion Beta", kb), E("text", "ßer als sonst.", a2),
                        E("text", "Beta rechts Text.", b2)]}
        pdf = self.pdf_aus(z)
        self.deklariere(**STRICHREST)
        self.lies(elemente, pdf)
        self.assertIn("Der Wert ist großer als sonst.", self.abschnitt_von("Alpha Text")["text"])
        self.deklariere(**dict(STRICHREST, lesefolge=dict(eqa.LESEFOLGE, ausnahmen=[1])))
        self.lies(elemente, pdf)
        self.assertIn("Der Wert ist gro- durch Magie stark.", self.gesamttext())

    @unittest.skip("devloop: REQ-EQ-6 noch nicht implementiert")
    def test_req_eq_6_rechte_spalte_unten_blockanfang_der_naechsten_seite(self):
        """[REQ-EQ-6] Rechte Spalte endet unten auf "Verteidi-", die naechste Seite beginnt links oben mit "gung" -> "Verteidigung"; das Haeppchen traegt beide Seiten."""
        b = SeitenBau()
        b.kopf(1, "Kapitel")
        b.element(1, ["Linker Text eins."], "Linker Text eins.")
        b.element(1, ["Rechts unten die Verteidi-"], "Rechts unten die Verteidi-", x=310, grund=700)
        b.element(2, ["gung hält stand."], "gung hält stand.", grund=100)
        self.lies_bau(b, **STRICHREST)
        a = self.abschnitt_von("Rechts unten")
        self.assertIn("die Verteidigung hält stand.", a["text"])
        self.assertEqual(a["seite_pdf"], 1)
        self.assertEqual([w[2] for w in a["seitenwechsel"]], [1, 2])
        self.assertTrue(all(0 <= w[0] <= len(a["text"]) for w in a["seitenwechsel"]))

    @unittest.skip("devloop: REQ-EQ-6 noch nicht implementiert")
    def test_req_eq_6_ohne_strichrest_byte_gleich(self):
        """[REQ-EQ-6] Ohne Spec-2-Deklaration byte-gleich zum Stand vor der Spec; mit lesefolge allein und mit "strichrest": false byte-gleich zueinander ("Verteidi- gung" bleibt)."""
        b = spalten_fall("Die Verteidi-", "gung hält stand.", "gung hält stand.")
        pdf = self.pdf_aus(b.z)
        self.deklariere()
        self.lies_alt(b.elemente, pdf)
        alt = self.roh()
        self.lies(b.elemente, pdf)
        self.assertEqual(self.roh(), alt)
        self.deklariere(lesefolge=eqa.LESEFOLGE)
        self.lies(b.elemente, pdf)
        nur_lesefolge = self.roh()
        self.assertIn("Die Verteidi- gung hält stand.", self.gesamttext())
        self.deklariere(lesefolge=eqa.LESEFOLGE, striche={"strichrest": False})
        self.lies(b.elemente, pdf)
        self.assertEqual(self.roh(), nur_lesefolge)


# ===================================================================================
# REQ-EQ-7 / -8 / -10: Zeichen
# ===================================================================================
def T(text, n):
    """Text-Element n in der linken Spalte (Lage ohne PDF-Text, Docling-Weg mit leerer PDF)."""
    return E("text", text, (40, 100 + 30 * n, 290, 120 + 30 * n))


UMLAUT_FAELLE = [("Fu . . r den Test.", "Für den Test."),               # Leerzeichen nach den Punkten faellt mit weg (K3)
                 ("Gru. . n ohne Leerzeichen davor", "Grün ohne Leerzeichen davor"),
                 ("Bla . .tter ohne Leerzeichen danach", "Blätter ohne Leerzeichen danach"),
                 ("Stufen/Aktionswu . . rfel", "Stufen/Aktionswürfel"),
                 ("A . . rger und O . . l", "Ärger und Öl"),
                 ("scho . . n und Ma . . rchen", "schön und Märchen")]


def umlaut_seite():
    return {1: [E("section_header", "U . . ber dies", (40, 30, 555, 50))]
            + [T(roh, n) for n, (roh, _) in enumerate(UMLAUT_FAELLE)] + [T("Punkt. . Ende", 9)]}


class TestZierumlaut(eqa.EQTest):
    @unittest.skip("devloop: REQ-EQ-7 noch nicht implementiert")
    def test_req_eq_7_zierumlaut_vor_dem_listenabgleich(self):
        """[REQ-EQ-7] "U . . ber dies", "Fu . . r den", "Stufen/Aktionswu . . rfel" (und a/o/A/O, Leerzeichen vor bzw. nach den Punkten optional) -> Umlaute, das Leerzeichen nach den Punkten faellt mit weg (K3: "Über", nicht "Ü ber"); Lesezeichen "Über dies" -> gefunden, Abschnitt "Über dies"."""
        self.deklariere(liste=(("Über dies", 1, 1),), zeichen={"zierumlaut": True})
        p = self.lies(umlaut_seite())
        text = self.gesamttext()
        for roh, soll in UMLAUT_FAELLE:
            self.assertIn(soll, text)
            self.assertNotIn(roh, text)
        for falsch in ("Ü ber", "Fü r", "Grü n", "Aktionswü rfel"):
            self.assertNotIn(falsch, text)
        self.assertIn(("Über dies", 1), [tuple(g) for g in p.gefunden])
        self.assertEqual(p.nicht_gefunden, [])
        self.assertTrue(self.abschnitt_von("Für den Test.")["text"].startswith("Über dies"))
        self.assertEqual(self.pfad_von("Für den Test."), ["Über dies"])

    @unittest.skip("devloop: REQ-EQ-7 noch nicht implementiert")
    def test_req_eq_7_punkte_ohne_vokal_davor_unveraendert(self):
        """[REQ-EQ-7] "Punkt. . Ende" (kein Vokal vor den Punkten) -> unveraendert, waehrend "Fu . . r" auf derselben Seite ersetzt wird."""
        self.deklariere(liste=(("Über dies", 1, 1),), zeichen={"zierumlaut": True})
        self.lies(umlaut_seite())
        self.assertIn("Punkt. . Ende", self.gesamttext())
        self.assertIn("Für den Test.", self.gesamttext())

    @unittest.skip("devloop: REQ-EQ-7 noch nicht implementiert")
    def test_req_eq_7_ohne_schalter_byte_gleich(self):
        """[REQ-EQ-7] Ohne Schalter (und mit "zierumlaut": false) -> Buchdatei byte-gleich zum Stand vor der Spec; "Über dies" nicht gefunden."""
        pdf = self.pdf_leer(1)
        self.deklariere(liste=(("Über dies", 1, 1),))
        self.lies_alt(umlaut_seite(), pdf)
        alt = self.roh()
        p = self.lies(umlaut_seite(), pdf)
        self.assertEqual(self.roh(), alt)
        self.assertIn(("Über dies", 1), [tuple(g) for g in p.nicht_gefunden])
        self.deklariere(liste=(("Über dies", 1, 1),), zeichen={"zierumlaut": False})
        self.lies(umlaut_seite(), pdf)
        self.assertEqual(self.roh(), alt)


def steuer_seite():
    return {1: [E("section_header", "Kapitel", (40, 30, 555, 50)), T("Wirkung: \x07WIL + 5", 0),
                T("Zeile eins\nZeile zwei", 1), T("Spalte\teins", 2), T("Kontroll\x01zeichen\x7fhier", 3)]}


class TestSteuerzeichen(eqa.EQTest):
    @unittest.skip("devloop: REQ-EQ-8 noch nicht implementiert")
    def test_req_eq_8_steuerzeichen_werden_leerzeichen(self):
        """[REQ-EQ-8] "Wirkung: \\x07WIL + 5" -> "Wirkung: WIL + 5" (Leerraum zusammengefasst); \\x01, \\x7f -> Leerzeichen; \\n und \\t bleiben."""
        self.deklariere(zeichen={"steuerzeichen": True})
        self.lies(steuer_seite())
        text = self.gesamttext()
        self.assertIn("Wirkung: WIL + 5", text)
        self.assertIn("Zeile eins\nZeile zwei", text)
        self.assertIn("Spalte\teins", text)
        self.assertIn("Kontroll zeichen hier", text)
        for ch in "\x07\x01\x7f":
            self.assertNotIn(ch, text)

    @unittest.skip("devloop: REQ-EQ-8 noch nicht implementiert")
    def test_req_eq_8_ohne_schalter_byte_gleich(self):
        """[REQ-EQ-8] Ohne Schalter (und mit "steuerzeichen": false) -> byte-gleich zum Stand vor der Spec, U+0007 bleibt."""
        pdf = self.pdf_leer(1)
        self.deklariere()
        self.lies_alt(steuer_seite(), pdf)
        alt = self.roh()
        self.lies(steuer_seite(), pdf)
        self.assertEqual(self.roh(), alt)
        self.assertIn("\x07", self.gesamttext())
        self.deklariere(zeichen={"steuerzeichen": False})
        self.lies(steuer_seite(), pdf)
        self.assertEqual(self.roh(), alt)


def listen_seite():
    return {1: [E("section_header", "Kapitel", (40, 30, 555, 50)),
                E("list_item", "Erster Punkt.", (40, 100, 290, 112), enumerated=True, marker="1."),
                E("list_item", "Zweiter Punkt.", (40, 115, 290, 127), enumerated=True, marker="2."),
                E("list_item", "Aufzählung ohne Nummer.", (40, 130, 290, 142), enumerated=False, marker="-"),
                E("list_item", "Leerer Marker.", (40, 145, 290, 157), enumerated=True, marker="")]}


class TestListennummern(eqa.EQTest):
    @unittest.skip("devloop: REQ-EQ-10 noch nicht implementiert")
    def test_req_eq_10_nummerierte_elemente_beginnen_mit_der_nummer(self):
        """[REQ-EQ-10] list_item mit enumerated und Marker "1." / "2." -> "1. Erster Punkt.", "2. Zweiter Punkt."; Aufzaehlungspunkt (nicht enumerated) und leerer Marker unveraendert."""
        self.deklariere(zeichen={"listennummern": True})
        self.lies(listen_seite())
        text = self.gesamttext()
        self.assertIn("1. Erster Punkt.", text)
        self.assertIn("2. Zweiter Punkt.", text)
        self.assertIn("Aufzählung ohne Nummer.", text)
        self.assertNotIn("- Aufzählung", text)
        self.assertIn("2. Zweiter Punkt. Aufzählung ohne Nummer. Leerer Marker.", text)   # dazwischen nichts eingefuegt

    @unittest.skip("devloop: REQ-EQ-10 noch nicht implementiert")
    def test_req_eq_10_ohne_schalter_byte_gleich(self):
        """[REQ-EQ-10] Ohne Schalter (und mit "listennummern": false) -> byte-gleich zum Stand vor der Spec, keine Nummer im Text."""
        pdf = self.pdf_leer(1)
        self.deklariere()
        self.lies_alt(listen_seite(), pdf)
        alt = self.roh()
        self.lies(listen_seite(), pdf)
        self.assertEqual(self.roh(), alt)
        self.assertNotIn("1. Erster", self.gesamttext())
        self.deklariere(zeichen={"listennummern": False})
        self.lies(listen_seite(), pdf)
        self.assertEqual(self.roh(), alt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
