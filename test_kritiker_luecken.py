#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kritiker-Luecken: Tests zu bereits spezifizierten Anforderungen der Spec mehrbuch-bestand, die
bisher kein Test sah (Review der Implementierung, Fassung 7). Jeder Test faengt eine benannte
Mutation (im Docstring: "Faengt: ...").

    python test_kritiker_luecken.py

Spec-PR: jeder Test einzeln @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-<n>"), [REQ-MB-<n>] im
Docstring. Nur synthetische Daten. Der Docling-Weg laeuft mit der Attrappe docling_attrappe.py
(sys.modules) und echtem pdfplumber auf einem per reportlab erzeugten PDF.

Vom Test benutzte Schnittstellen der Implementierung (aus einlesen.py gelesen):
  einlesen.lies_pdf_ein(spiel_id, buch_id, pdf=..., ueberschreiben=..., ausgabe=...) -> Protokoll
  einlesen.VORABMESSUNG (Pfad des Messergebnisses, im Test auf eine Temp-Datei gelegt)
"""
import contextlib
import importlib
import io
import json
import os
import sqlite3
import sys
import unittest
from unittest import mock

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402
import test_mehrbuch as mb  # noqa: E402
import test_zerschneiden as zs  # noqa: E402
import docling_attrappe as da  # noqa: E402
from test_einlesen_reparatur import z, eintrag as listeneintrag, S1, FT, STUFEN, SEITENHOEHE  # noqa: E402

SID, NAME = mb.SID, mb.NAME


def einlesen():
    return importlib.import_module("einlesen")


def zahl(index, sql, *a):
    con = sqlite3.connect(index)
    try:
        return con.execute(sql, a).fetchone()[0]
    finally:
        con.close()


# ===================================================================================
# 1. Wechsel Mehrbuch <-> Altbestand, Buch entfernen, Deklarationsaenderung (REQ-MB-1, -8, -9)
# ===================================================================================
ALT_TW = [{"id": i, "seite": 40 + i, "typ": "regel", "text": f"Altregel altmarke{i} Wasser.", "spiel": NAME,
           "spiel_id": SID} for i in range(1, 4)]


class TestBestandWechsel(mb.ZweiBuecher):
    def als_altbestand(self):
        with open(os.path.join(self.data, SID, "spiel.json"), "w", encoding="utf-8") as f:
            json.dump({"spiel_id": SID, "name": NAME, "aliase": [], "sprache": "de", "quelle_pdf": None}, f)
        rag.schreibe_jsonl(rag.knowledge_pfad(SID), ALT_TW)

    def kennungen(self):
        chunks, _ = rag.lade_spiel(self.oeffne(), SID)
        return sorted(mb.kennung(c, mb.NORD_K + mb.SUED_K + [f"altmarke{i}" for i in range(1, 4)]) for c in chunks)

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-8")
    def test_req_mb_8_wechsel_mehrbuch_alt_mehrbuch_ohne_verlust(self):
        """[REQ-MB-8] Mehrbuch -> Altbestand -> Mehrbuch: jeweils genau die Haeppchen des Stands, keine Altbestand-Zeile (buch_id NULL) bleibt, FTS deckungsgleich. Faengt: Altbestand-Zeilen beim Wechsel nicht loeschen; Buecher nach dem Zurueckwechseln als "aktuell" stehen lassen."""
        self.lege_zwei_an()
        self.baue()
        self.als_altbestand()
        self.baue()
        self.assertEqual(self.kennungen(), ["altmarke1", "altmarke2", "altmarke3"])
        self.assertEqual(zahl(self.index, "SELECT count(*) FROM chunks WHERE spiel_id=? AND buch_id IS NOT NULL", SID), 0)
        self.lege_zwei_an()
        self.baue()
        self.assertEqual(self.kennungen(), sorted(mb.NORD_K + mb.SUED_K))
        self.assertEqual(zahl(self.index, "SELECT count(*) FROM chunks WHERE spiel_id=? AND buch_id IS NULL", SID), 0)
        self.assertEqual(zahl(self.index, "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH '\"altmarke1\"'"), 0)
        self.assertEqual(zahl(self.index, "SELECT count(*) FROM chunks_fts"), zahl(self.index, "SELECT count(*) FROM chunks"))

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-9")
    def test_req_mb_9_buch_entfernen(self):
        """[REQ-MB-9] Buch aus der Deklaration entfernt -> seine Haeppchen (auch FTS) sind weg, das andere wird nicht neu eingebettet. Faengt: nicht mehr deklarierte Buecher im Index stehen lassen."""
        self.lege_zwei_an()
        self.baue()
        self.bestand([mb.buch("nord", "Buch Nord", "alpha")])
        _, eingebettet = self.baue()
        self.assertEqual(eingebettet, [])
        self.assertEqual(self.kennungen(), sorted(mb.NORD_K))
        self.assertEqual(zahl(self.index, "SELECT count(*) FROM chunks WHERE buch_id='sued'"), 0)
        self.assertEqual(zahl(self.index, "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH '\"suedeins\"'"), 0)

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-1")
    def test_req_mb_1_reine_deklarationsaenderung_erreicht_die_zeilen(self):
        """[REQ-MB-1] Nur sprache/fassung/Inhaltsart-Zuweisung von nord geaendert -> Zeilen und lade_spiel tragen die neuen Werte, Filter greift, 0 Einbettungen. Faengt: Deklarationsaenderung ohne Dateiaenderung nicht nachziehen."""
        self.lege_zwei_an()
        self.baue()
        self.bestand([mb.buch("nord", "Buch Nord", "gamma", sprache="en", inhaltsarten=[(("K2",), "welt")]),
                      mb.buch("sued", "Buch Sued", "beta", sprache="en", inhaltsart="welt")])
        _, eingebettet = self.baue()
        self.assertEqual(eingebettet, [])
        chunks, _ = rag.lade_spiel(self.oeffne(), SID)
        nord = {mb.kennung(c, mb.NORD_K): c for c in chunks if c["buch_id"] == "nord"}
        self.assertEqual({(c["fassung"], c["sprache"]) for c in nord.values()}, {("gamma", "en")})
        self.assertEqual(nord["norddrei"]["inhaltsart"], "welt")
        self.assertEqual(nord["nordeins"]["inhaltsart"], "regel")
        self.assertEqual(zahl(self.index, "SELECT count(*) FROM chunks WHERE buch_id='nord' AND sprache='de'"), 0)
        hits = self.suche("Feuer", 20, filter={"fassung": "gamma"})
        self.assertEqual({h["buch_id"] for h, _ in hits}, {"nord"})


# ===================================================================================
# 2. Slug-Pruefung beobachtbar (REQ-MB-10)
# ===================================================================================
class TestSlugBeobachtbar(mb.ZweiBuecher):
    def kaputte_datei(self, bid, pfad):
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        rag.schreibe_jsonl(pfad, [mb.eintrag(bid, 1, 10, "Feuer kaputtmarke")])

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-10")
    def test_req_mb_10_buch_id_ohne_slug_trotz_vorhandener_datei(self):
        """[REQ-MB-10] Buchdatei liegt unter dem kaputten Namen ("Buch A" bzw. ueber "../x") -> trotzdem KonfigFehler, Index unveraendert. Faengt: Slug-Pruefung der buch_id aus (der Fehler kam bisher nur ueber die fehlende Datei)."""
        self.lege_zwei_an()
        self.baue()
        vorher = self.zeilen()
        for bid, pfad in (("Buch A", os.path.join(self.data, SID, "buecher", "Buch A", "knowledge.jsonl")),
                          ("../x", os.path.join(self.data, SID, "x", "knowledge.jsonl"))):
            with self.subTest(buch_id=bid):
                self.kaputte_datei(bid, pfad)
                self.bestand([mb.buch("nord", "Buch Nord", "alpha"), mb.buch(bid, "Kaputt", "beta", quelle="k.pdf")])
                with self.assertRaises(rag.KonfigFehler):
                    rag.aktualisiere_index([SID], ausgabe=lambda *_: None)
                self.assertEqual(self.zeilen(), vorher)

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-10")
    def test_req_mb_10_einlesen_unter_pfadausbruch_schreibt_nichts(self):
        """[REQ-MB-10] lies_buch_ein fuer buch_id "../x" -> KonfigFehler, ausserhalb von buecher/ entsteht nichts. Faengt: Slug-Pruefung aus (Pfadausbruch)."""
        self.bestand([mb.buch("nord", "Buch Nord", "alpha"),
                      mb.buch("../x", "Kaputt", "beta", quelle="k.pdf", ueberschriften={"quelle": "lesezeichen"},
                              seitenzahlen={"quelle": "versatz", "versatz": 0})])
        vorher = mb.hashes(self.data)
        with self.assertRaises(rag.KonfigFehler):
            einlesen().lies_buch_ein(SID, "../x", {1: [z("Kapitel", "section_header"), z("Text.")]},
                                     lesezeichen=[listeneintrag("Kapitel", 1)])
        self.assertEqual(mb.hashes(self.data), vorher)
        self.assertFalse(os.path.exists(os.path.join(self.data, SID, "x")))


# ===================================================================================
# 3. Docling-Adapter (REQ-MB-20, -23, -27, -29) mit Attrappe und echtem pdfplumber
# ===================================================================================
def zeichne(pfad, seiten):
    """reportlab-PDF; seiten: {n: [(text, x0, oben, font, groesse)]} -- oben = Abstand von der oberen Kante."""
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(pfad, pagesize=(da.BREITE, da.HOEHE))
    for n in range(1, max(seiten) + 1):
        for text, x0, oben, font, groesse in seiten.get(n, []):
            c.setFont(font, groesse)
            c.drawString(x0, da.HOEHE - (oben + groesse), text)
        c.showPage()
    c.save()
    return pfad


def kasten(text, x0, oben, groesse, font):
    """Docling-Lage passend zum gezeichneten Text: (x0, oben, x1, unten) ab oben links."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    return (x0 - 1, oben, x0 + stringWidth(text, font, groesse) + 1, oben + groesse + 3)


FETT, NORMAL = "Helvetica-Bold", "Helvetica"
TABELLE_MD = "| Stufe | Wert |\n|---|---|\n| 1 | 5 |"
ADAPTER_ZEILEN = [  # (Label, Text, oben, Font, Groesse)
    ("text", "Kolumne Kopfmarke", 20, NORMAL, 10),            # Mitte ~28 < Kopfrand 50
    ("section_header", "Kapitel", 100, FETT, 14),
    ("text", "Talent Alpha", 140, FETT, 14),                 # Stufe 1 nur ueber die pdfplumber-Schrift
    ("text", "Fliesstext alphamarke dazu.", 170, NORMAL, 10),
]
KIND = ("text", "Kastentext bildmarke.", 260, NORMAL, 10)


class TestDoclingAdapter(mb.BestandTest):
    VERSIONEN = {"docling": "2.131.0", "pdfplumber": "0.11.10"}

    def setUp(self):
        super().setUp()
        self.messung = os.path.join(self.tmp.name, "vorabmessung.json")
        with open(self.messung, "w", encoding="utf-8") as f:
            json.dump({"docling_version": "2.131.0", "pdfplumber_version": "0.11.10"}, f)
        p = mock.patch.object(einlesen(), "VORABMESSUNG", self.messung)
        p.start()
        self.addCleanup(p.stop)
        self.bestand([mb.buch("nord", "Buch Nord", "alpha", ueberschriften={"quelle": "inhaltsverzeichnis",
                                                                           "eintraege": [listeneintrag("Kapitel", 1)]},
                              seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True,
                              layout={"klasse": "section_header", "stufen": STUFEN}, rand={"kopf": 50})])
        elemente = [da.Element(lab, t, kasten(t, 50, o, g, f)) for lab, t, o, f, g in ADAPTER_ZEILEN]
        elemente.append(da.Element("table", "", (50, 200, 300, 240), markdown=TABELLE_MD))
        lab, t, o, f, g = KIND
        elemente.append(da.Element("picture", "", (40, 250, 400, 300), kinder=[da.Element(lab, t, kasten(t, 50, o, g, f))]))
        self.elemente = {1: elemente}
        self.pdf = zeichne(os.path.join(self.tmp.name, "buch.pdf"),
                           {1: [(t, 50, o, f, g) for _, t, o, f, g in ADAPTER_ZEILEN + [KIND]]})

    def lies(self, versionen=None):
        with da.installiere(self.elemente, versionen or self.VERSIONEN):
            return einlesen().lies_pdf_ein(SID, "nord", pdf=self.pdf, ausgabe=lambda *_: None)

    def buchtext(self):
        return [json.loads(z) for z in open(self.buchdatei("nord"), encoding="utf-8")]

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-23")
    def test_req_mb_23_versionen_werden_durchgereicht_und_geprueft(self):
        """[REQ-MB-23] Docling-/pdfplumber-Version des Adapters stehen im Protokoll; abweichende Version -> KonfigFehler, keine Buchdatei. Faengt: Adapter reicht die Versionen nicht durch (MBB23d/e)."""
        for falsch in ({"docling": "2.200.0", "pdfplumber": "0.11.10"}, {"docling": "2.131.0", "pdfplumber": "0.12.0"}):
            with self.subTest(versionen=falsch):
                with self.assertRaises(rag.KonfigFehler):
                    self.lies(falsch)
                self.assertFalse(os.path.exists(self.buchdatei("nord")))
        p = self.lies()
        self.assertEqual((p.docling_version, p.pdfplumber_version), ("2.131.0", "0.11.10"))
        protokoll = json.load(open(os.path.join(os.path.dirname(self.buchdatei("nord")), "einlese_protokoll.json")))
        self.assertEqual((protokoll["docling_version"], protokoll["pdfplumber_version"]), ("2.131.0", "0.11.10"))

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-23")
    def test_req_mb_23_tabellen_roh(self):
        """[REQ-MB-23] Tabellen-Elemente gehen roh (Markdown-Export) in den Text, nicht leer oder verbalisiert. Faengt: Tabelle ueber item.text statt export_to_markdown (X15)."""
        self.lies()
        alles = "\n".join(e["text"] for e in self.buchtext())
        self.assertIn("| Stufe | Wert |", alles)
        self.assertIn("| 1 | 5 |", alles)

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-28")
    def test_req_mb_28_docling_lage_nach_oben_links_umgerechnet(self):
        """[REQ-MB-28] Docling-bbox (Ursprung unten links) wird nach oben links umgerechnet: Kolumnentitel oben auf der Seite liegt im Kopfrand und wird verworfen. Faengt: bbox ohne Umrechnung (X16)."""
        p = self.lies()
        alles = "\n".join(e["text"] for e in self.buchtext())
        self.assertNotIn("Kopfmarke", alles)
        self.assertEqual(p.randzeilen, 1)
        self.assertIn("alphamarke", alles)

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-27")
    def test_req_mb_27_bild_kinder_im_adapter(self):
        """[REQ-MB-27] Text-Kind eines Bild-Elements kommt genau einmal in den Buchtext, Protokoll aus_bildern 1. Faengt: Adapter ohne traverse_pictures."""
        p = self.lies()
        alles = "\n".join(e["text"] for e in self.buchtext())
        self.assertEqual(alles.count("bildmarke"), 1)
        self.assertEqual(p.aus_bildern, 1)

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-20")
    def test_req_mb_20_schriftstufe_aus_pdfplumber_im_adapter(self):
        """[REQ-MB-20] "Talent Alpha" (Klasse text, 14 pt fett im PDF) wird ueber die pdfplumber-Schrift Ueberschrift der Stufe 1: Pfad Kapitel > Talent Alpha. Faengt: Adapter ruft ordne_schrift_zu nicht bzw. mit falscher Lage."""
        self.lies()
        pfade = [e["abschnittspfad"] for e in self.buchtext()]
        self.assertIn(["Kapitel", "Talent Alpha"], pfade)
        talent = next(e for e in self.buchtext() if e["abschnittspfad"] == ["Kapitel", "Talent Alpha"])
        self.assertIn("alphamarke", talent["text"])


# ===================================================================================
# 5. Keine geteilten Listen zwischen Chunks (REQ-MB-2)
# ===================================================================================
class TestGeteilteListen(mb.BestandTest):
    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-2")
    def test_req_mb_2_aenderung_an_einem_chunk_aendert_keinen_anderen(self):
        """[REQ-MB-2] Zwei Haeppchen mit gleichem Pfad und gleichen Seiten: append an abschnittspfad/seiten des einen laesst das andere unveraendert. Faengt: geparste JSON-Listen zwischen Chunks teilen."""
        self.bestand([mb.buch("nord", "Buch Nord", "alpha")])
        self.schreibe_buch("nord", [mb.eintrag("nord", 1, 10, "Feuer eins"), mb.eintrag("nord", 2, 10, "Wasser zwei")])
        self.baue()
        a, b = rag.lade_spiel(self.oeffne(), SID)[0]
        self.assertEqual((a["abschnittspfad"], a["seiten"]), (b["abschnittspfad"], b["seiten"]))
        a["abschnittspfad"].append("FREMD")
        a["seiten"].append(999)
        self.assertEqual(b["abschnittspfad"], ["K1"])
        self.assertEqual(b["seiten"], [10])


# ===================================================================================
# 7. Weitere Kritiker-Mutationen (Seitengrenzen, Zaehler, Schnitt)
# ===================================================================================
class TestSeitengrenzen(zs.ZerschneideTest):
    def erstes_haeppchen(self, seiten, liste, size, pfad):
        self.lies_ein(seiten, liste)
        return self.je_pfad(self.chunks(size, 10))[pfad]

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-16")
    def test_req_mb_16_haeppchen_endet_genau_vor_der_seitengrenze(self):
        """[REQ-MB-16] Stueck endet unmittelbar vor dem ersten Zeichen von Seite 5 -> traegt nur [4]; ein Zeichen weiter -> [4, 5]. Faengt: Seitengrenze inklusiv statt exklusiv (X10)."""
        seiten = {4: [z("Grenzfall", "section_header"), z("Vier vier vier vier vier vier vier vier.")],
                  5: [z("Fuenf fuenf fuenf fuenf fuenf.")]}
        (a,) = self.lies_ein(seiten, [listeneintrag("Grenzfall", 4)])
        o = a["text"].index("Fuenf")
        erstes = self.je_pfad(self.chunks(o, 10))[("Grenzfall",)][0]
        self.assertEqual(erstes["seiten"], [4])
        os.remove(self.buchdatei("nord"))
        erstes = self.erstes_haeppchen(seiten, [listeneintrag("Grenzfall", 4)], o + 1, ("Grenzfall",))[0]
        self.assertEqual(erstes["seiten"], [4, 5])

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-16")
    def test_req_mb_16_seite_der_ueberschriftenzeile(self):
        """[REQ-MB-16] Ueberschrift unten auf Seite 5, Text auf Seite 6 -> Haeppchen traegt [5, 6], Fundstelle Seite 5. Faengt: Seite der Ueberschriftenzeile nicht mitgezaehlt (X11)."""
        seiten = {5: [z("Anfang", "section_header"), z("Text am Anfang."), z("Spaeter", "section_header")],
                  6: [z("Text auf Seite sechs.")]}
        self.lies_ein(seiten, [listeneintrag("Anfang", 5), listeneintrag("Spaeter", 5)])
        (c,) = self.je_pfad(self.chunks(400, 150))[("Spaeter",)]
        self.assertEqual((c["seite"], c["seiten"], c["seite_pdf"]), (5, [5, 6], 5))

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-16")
    def test_req_mb_16_seitenwechsel_in_der_trennfuge(self):
        """[REQ-MB-16] "Akti-" (S. 4) + "onswuerfel" (S. 5) -> "Aktionswuerfel"; Seite 5 beginnt bei "ons": Stueck bis vor "o" -> [4], mit "o" -> [4, 5]. Faengt: Offset nach der Trennfuge um eins verschoben (X12)."""
        seiten = {4: [z("Trennfall", "section_header"), z("Hier steht ein Akti-")],
                  5: [z("onswürfel und noch mehr Text auf Seite fuenf.")]}
        (a,) = self.lies_ein(seiten, [listeneintrag("Trennfall", 4)])
        self.assertIn("Aktionswürfel", a["text"])
        o = a["text"].index("onswürfel")
        erstes = self.je_pfad(self.chunks(o, 10))[("Trennfall",)][0]
        self.assertEqual(erstes["seiten"], [4])
        os.remove(self.buchdatei("nord"))
        erstes = self.erstes_haeppchen(seiten, [listeneintrag("Trennfall", 4)], o + 1, ("Trennfall",))[0]
        self.assertEqual(erstes["seiten"], [4, 5])


class TestZaehlerGenau(unittest.TestCase):
    LISTE = [listeneintrag("K1", 1)]

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-20")
    def test_req_mb_20_rand_zaehler_nur_wenn_sonst_ueberschrift(self):
        """[REQ-MB-20] Rand-Zaehler zaehlt nur Randzeilen, fuer die 5(a) oder 5(b) zutraefe (2 von 3); randzeilen zaehlt alle (3). Faengt: Rand-Zaehler zaehlt jede Randzeile (X17)."""
        e = einlesen()
        seiten = {1: [z("Kopf stufe", "text", S1, oben=10), z("Kopf fliess", "text", FT, oben=20),
                      z("Kopf klasse", "section_header", oben=30),
                      z("K1", "section_header", S1, oben=100), z("Text.", schrift=FT, oben=120)]}
        p = e.Protokoll()
        e.baue_abschnitte(seiten, self.LISTE, layout={"klasse": "section_header", "stufen": STUFEN},
                          rand={"kopf": 50}, seitenhoehe=SEITENHOEHE, protokoll=p)
        self.assertEqual((p.randzeilen, p.rand_verhindert), (3, 2))

    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-20")
    def test_req_mb_20_veto_zaehler_nur_wenn_5a_zutraefe(self):
        """[REQ-MB-20] Veto-Zaehler zaehlt nur Veto-Zeilen, deren Schrift eine Stufe trifft (1 von 3). Faengt: Veto-Zaehler zaehlt jede Veto-Zeile (X18)."""
        e = einlesen()
        seiten = {1: [z("K1", "section_header", S1), z("Text.", schrift=FT),
                      z("Zeta", "table", S1), z("Tabellenzeile", "table", FT), z("Bildunterschrift", "caption")]}
        p = e.Protokoll()
        e.baue_abschnitte(seiten, self.LISTE, layout={"klasse": "section_header", "stufen": STUFEN}, protokoll=p)
        self.assertEqual(p.veto_verhindert, 1)


class TestSchnittImMehrheitsschluessel(unittest.TestCase):
    @unittest.skip("devloop: Kritiker-Luecke, REQ-MB-29")
    def test_req_mb_29_gleiche_groesse_verschiedener_schnitt_ist_keine_mehrheit(self):
        """[REQ-MB-29] 5 Zeichen 14 pt fett + 5 Zeichen 14 pt normal -> keine eindeutige Mehrheit, keine Schrift; 6 fett + 4 normal -> fett. Faengt: Mehrheit nur nach Groesse (X27)."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            from reportlab.pdfgen import canvas
            pfad = os.path.join(tmp, "schnitt.pdf")
            c = canvas.Canvas(pfad, pagesize=(da.BREITE, da.HOEHE))
            for oben, fett, normal in ((100, "AAAAA", " bbbbb"), (200, "AAAAAA", " bbbb")):
                t = c.beginText(50, da.HOEHE - oben - 14)
                t.setFont(FETT, 14)
                t.textOut(fett)
                t.setFont(NORMAL, 14)
                t.textOut(normal)
                c.drawText(t)
            c.showPage()
            c.save()
            zeilen = {1: [{"text": "AAAAA bbbbb", "klasse": "text", "x0": 45, "x1": 300, "oben": 100, "unten": 117},
                          {"text": "AAAAAA bbbb", "klasse": "text", "x0": 45, "x1": 300, "oben": 200, "unten": 217}]}
            gleich, mehr = einlesen().ordne_schrift_zu(pfad, zeilen)[1]
        self.assertIsNone(gleich.get("schrift"))
        self.assertTrue(mehr["schrift"]["fett"])
        self.assertAlmostEqual(mehr["schrift"]["groesse"], 14, delta=0.1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
