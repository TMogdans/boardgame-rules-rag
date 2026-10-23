#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Einlesequalitaet, uebergreifende Kriterien (Spec .specify/specs/einlese-qualitaet/spec.md):
REQ-EQ-1 Format der Regel-Messung, REQ-EQ-2 Wirkungszaehler, REQ-EQ-9 Zahlenprotokoll und
Textverlust, REQ-EQ-15 Schema, REQ-EQ-16 Abschaltbarkeit, REQ-EQ-17 generisch, REQ-EQ-18
Urheberrecht/Schreibpfade, REQ-EQ-19 Versionen, REQ-EQ-20 Performance.

    python test_einlese_qualitaet.py

Spec-PR: jeder Test einzeln @unittest.skip("devloop: REQ-EQ-<n> ..."), [REQ-EQ-<n>] im Docstring.
implement entfernt NUR das skip. Messtor (EQ-1, Review ueber die Git-Historie) und Messgleichheit
am echten Buch (EQ-2) sind Review-Schritte und hier NICHT getestet; EQ-1 prueft nur das Format.

Vom Test erwartete Schnittstellen (aus der Spec abgeleitet, Namen hier festgelegt; dazu die in
test_lesefolge.py, test_striche_zeichen.py, test_tabellenkopf.py):
  .specify/specs/einlese-qualitaet/vorabmessung.json "regeln": {"REQ-EQ-<n>": {"faelle": n,
      "faelle_art": {"menge", "folge", "beides"}, "seiten": [...], "ausnahmen": {"anzahl": n,
      "seiten": [...]}, "urteil": {"besser", "gleichwertig", "schlechter", "strittig"}}}     (REQ-EQ-1)
  Protokoll.wirkung = {"REQ-EQ-<n>": {"abschnittsaenderungen": n, "textaenderungen": n,
      "seiten": [...]}} je eingeschalteter Text-Regel (EQ-3, -5, -6, -7, -8, -10), inkrementell gegen
      den Lauf mit allen vorangehenden Regeln (K1); Regel ohne Fall mit Nullwerten (U2)    (REQ-EQ-2)
  Ausgabe von rag.aktualisiere_index: je Buch eine Zeile mit buch_id und der Zahl der Haeppchen mit
      Tabellenkopf-Vorsatz neben dem Wort "Vorsatz"/"Vorsaetze" (U1, wie REQ-MB-14)             (REQ-EQ-2/-21)
  Protokoll.zahlenprotokoll = {"quelle": n, "fehlend": {"gar_nicht", "seltener"},
      "zusaetzlich": {"erfunden", "vervielfacht"}, "textverlust": n,
      "seiten": {physische Seite: {"gar_nicht", "seltener", "erfunden", "vervielfacht", "textverlust"}}}
      oder "nicht_gemessen" (ohne PDF bzw. ohne Textebene); nur mit Spec-2-Deklaration (K4), sonst
      fehlt es (oder Leerwert) und pdfplumber wird dafuer nicht geoeffnet; gezaehlt je Seite und Wert (\\d+):
      gar_nicht/seltener/erfunden/vervielfacht = Anzahl verschiedener Werte              (REQ-EQ-9)
  einlesen.lies_buch_ein(..., vorabmessung_eq=None)  Pfad der Spec-2-Vorab-Messung (Default
      .specify/specs/einlese-qualitaet/vorabmessung.json), Versionen injiziert wie REQ-MB-23  (REQ-EQ-19)
"""
import builtins
import gc
import json
import os
import statistics
import sys
import tempfile
import time
import unittest
from unittest import mock

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402
import docling_attrappe as da  # noqa: E402
import eq_attrappe as eqa  # noqa: E402
import test_mehrbuch as mb  # noqa: E402

E = eqa.Element
TEXTREGELN = ("REQ-EQ-3", "REQ-EQ-5", "REQ-EQ-6", "REQ-EQ-7", "REQ-EQ-8", "REQ-EQ-10")
MIT_AUS = {"REQ-EQ-3": {"REQ-EQ-6"}}           # EQ-3 aus erzwingt EQ-6 aus (K2)
SEITE_DER_REGEL = {"REQ-EQ-3": 1, "REQ-EQ-5": 2, "REQ-EQ-6": 3, "REQ-EQ-7": 4, "REQ-EQ-8": 5, "REQ-EQ-10": 6,
                   "REQ-EQ-21": 7}
KAPITEL = ("Lesefolge", "Striche", "Rest", "Umlaut", "Steuer", "Liste", "Tabelle")
LISTE = tuple((t, s, 1) for s, t in enumerate(KAPITEL, 1))


def ohne(regel):
    """ALLE_REGELN mit dieser Regel aus (fehlender Schluessel = aus, Begriffe). EQ-3 aus heisst ohne
    "lesefolge"; damit muss EQ-6 mit aus, denn strichrest ohne lesefolge ist ein Schemafehler (K2)."""
    d = json.loads(json.dumps(eqa.ALLE_REGELN))
    if regel == "REQ-EQ-3":
        del d["lesefolge"]
        del d["striche"]["strichrest"]
    elif regel == "REQ-EQ-5":
        del d["striche"]["zeilenenden"]
    elif regel == "REQ-EQ-6":
        del d["striche"]["strichrest"]
    elif regel == "REQ-EQ-7":
        del d["zeichen"]["zierumlaut"]
    elif regel == "REQ-EQ-8":
        del d["zeichen"]["steuerzeichen"]
    elif regel == "REQ-EQ-10":
        del d["zeichen"]["listennummern"]
    elif regel == "REQ-EQ-21":
        del d["tabellenkopf"]
    return d


def alle_regeln_buch():
    """Je Regel genau ein Fall auf eigener Seite unter eigenem Listeneintrag (Seiten 1-7, KAPITEL)."""
    z = eqa.Zeichnung()
    el = {}

    def kopf(s):
        z.zeile(s, 40, 45, KAPITEL[s - 1], "Helvetica-Bold", 12)
        el[s] = [E("section_header", KAPITEL[s - 1], (38, 30, 555, 50))]

    def element(s, x, grund, zeilen, text, label="text", **kw):
        el[s].append(E(label, text, z.block(s, x, grund, zeilen), **kw))
    for s in range(1, 8):
        kopf(s)
    element(1, 310, 100, ["Rechte Spalte zwei."], "Rechte Spalte zwei.")              # EQ-3: Docling rechts vor links
    element(1, 40, 100, ["Linke Spalte eins."], "Linke Spalte eins.")
    element(2, 40, 100, ["Das Novizen-", "Talent wirkt."], "Das NovizenTalent wirkt.")   # EQ-5
    element(3, 40, 100, ["Die Verteidi-"], "Die Verteidi-")                            # EQ-6 (Folgezeile derselben Spalte)
    element(3, 40, 112, ["gung hält stand."], "gung hält stand.")
    element(4, 40, 100, ["Für den Test."], "Fu . . r den Test.")                       # EQ-7
    element(5, 40, 100, ["Wirkung: WIL + 5"], "Wirkung: \x07WIL + 5")                  # EQ-8
    element(6, 40, 100, ["1. Erster Punkt."], "Erster Punkt.", label="list_item", enumerated=True, marker="1.")
    tab = eqa.tabelle([[eqa.Spanne("Würfeltabelle", 2)], ["Stufe", "Würfel"]]
                      + [[str(i), f"W{4 + 2 * (i % 5)}"] for i in range(1, 31)], kopf=[1], lage=(40, 100, 290, 400))
    el[7].append(tab)                                                                  # EQ-21
    element(7, 40, 700, ["Nachtext."], "Nachtext.")
    return z, el


ERWARTET_TEXT = {"REQ-EQ-3": "Linke Spalte eins. Rechte Spalte zwei.", "REQ-EQ-5": "Das Novizen-Talent wirkt.",
                 "REQ-EQ-6": "Die Verteidigung hält stand.", "REQ-EQ-7": "Für den Test.",
                 "REQ-EQ-8": "Wirkung: WIL + 5", "REQ-EQ-10": "1. Erster Punkt."}


class BuchTest(eqa.EQTest):
    def lies_alle(self, bid="nord", sid=None):
        z, el = alle_regeln_buch()
        if not getattr(self, "_pdf_alle", None):
            self._pdf_alle = self.pdf_aus(z, 7)
        return self.lies(el, self._pdf_alle, bid=bid, sid=sid)

    def texte(self, bid="nord", sid=None):
        return {tuple(e["abschnittspfad"]): e["text"] for e in self.eintraege(bid, sid)}


# ===================================================================================
# REQ-EQ-1: Format der Regel-Messung (Messtor selbst = Review)
# ===================================================================================
REGELN_2A = {"REQ-EQ-3", "REQ-EQ-5", "REQ-EQ-6", "REQ-EQ-7", "REQ-EQ-8", "REQ-EQ-10", "REQ-EQ-21"}
REGELN_ALLE = {f"REQ-EQ-{n}" for n in range(3, 15)} | {"REQ-EQ-21"}


def blaetter(x):
    if isinstance(x, dict):
        for v in x.values():
            yield from blaetter(v)
    elif isinstance(x, list):
        for v in x:
            yield from blaetter(v)
    else:
        yield x


def pruefe_messung(m, test):
    """Format von vorabmessung.json (REQ-EQ-1) und REQ-EQ-18 (nur Zahlen, Versionen, kurze Stichworte)."""
    for v in ("docling_version", "pdfplumber_version"):
        test.assertRegex(m[v], r"^\d+(\.\d+)+$")
    for b in blaetter(m):
        if isinstance(b, str):
            test.assertLessEqual(len(b), 40, f"Textfeld ueber 40 Zeichen: {b!r}")
    regeln = m["regeln"]
    test.assertLessEqual(REGELN_2A, set(regeln))
    test.assertLessEqual(set(regeln), REGELN_ALLE)
    for rid, r in regeln.items():
        with test.subTest(regel=rid):
            test.assertTrue({"faelle", "faelle_art", "seiten", "ausnahmen", "urteil"} <= set(r), sorted(r))
            for b in blaetter(r):
                test.assertIs(type(b), int, (rid, b))
                test.assertGreaterEqual(b, 0, (rid, b))
            test.assertEqual(set(r["faelle_art"]), {"menge", "folge", "beides"})
            test.assertEqual(sum(r["faelle_art"].values()), r["faelle"])
            test.assertEqual(set(r["urteil"]), {"besser", "gleichwertig", "schlechter", "strittig"})
            test.assertEqual(sum(r["urteil"].values()), r["faelle"])
            test.assertIsInstance(r["seiten"], list)
            test.assertTrue(all(s >= 1 for s in r["seiten"]))
            test.assertEqual(set(r["ausnahmen"]), {"anzahl", "seiten"})
            test.assertTrue(all(s >= 1 for s in r["ausnahmen"]["seiten"]))


class TestMessformat(unittest.TestCase):
    @unittest.skip("devloop: REQ-EQ-1 noch nicht implementiert")
    def test_req_eq_1_regel_messung_im_spec_ordner_hat_das_format(self):
        """[REQ-EQ-1] vorabmessung.json: "regeln" fuer alle Regeln von 2a (EQ-3, -5, -6, -7, -8, -10, -21) mit faelle, faelle_art, seiten, ausnahmen, urteil; nur nichtnegative ganze Zahlen; Summe der Urteile = Zahl der Faelle; Textfelder <= 40 Zeichen (REQ-EQ-18)."""
        with open(eqa.VORABMESSUNG_EQ, encoding="utf-8") as f:
            pruefe_messung(json.load(f), self)

    @unittest.skip("devloop: REQ-EQ-1 noch nicht implementiert")
    def test_req_eq_1_formatpruefung_weist_verstoesse_zurueck(self):
        """[REQ-EQ-1] Die Formatpruefung selbst greift: Urteilssumme != Faelle, negative Zahl, Text statt Zahl, Textfeld mit 41 Zeichen (REQ-EQ-18), fehlende Regel von 2a -> jeweils rot; die gueltige Messung -> gruen."""
        r = {"faelle": 3, "faelle_art": {"menge": 1, "folge": 1, "beides": 1}, "seiten": [5, 9],
             "ausnahmen": {"anzahl": 1, "seiten": [9]}, "urteil": {"besser": 2, "gleichwertig": 1, "schlechter": 0,
                                                                    "strittig": 0}}
        gut = {"docling_version": "2.131.0", "pdfplumber_version": "0.11.10", "stichwort": "kurz",
               "regeln": {k: json.loads(json.dumps(r)) for k in REGELN_2A}}
        pruefe_messung(gut, self)

        def kaputt(f):
            m = json.loads(json.dumps(gut))
            f(m)
            return m
        verstoesse = {
            "urteilssumme": kaputt(lambda m: m["regeln"]["REQ-EQ-3"]["urteil"].update(besser=5)),
            "negativ": kaputt(lambda m: m["regeln"]["REQ-EQ-5"]["seiten"].append(-1)),
            "text statt zahl": kaputt(lambda m: m["regeln"]["REQ-EQ-6"].update(faelle="3")),
            "textfeld 41": kaputt(lambda m: m.update(stichwort="x" * 41)),
            "regel fehlt": kaputt(lambda m: m["regeln"].pop("REQ-EQ-21")),
            "fremde regel": kaputt(lambda m: m["regeln"].update({"REQ-EQ-99": r})),
        }
        class Streng(unittest.TestCase):
            """assert-Methoden ohne subTest-Sammeln: der erste Verstoss wirft AssertionError."""

            def subTest(self, *a, **k):
                import contextlib
                return contextlib.nullcontext()
        for name, m in verstoesse.items():
            with self.subTest(verstoss=name):
                with self.assertRaises(AssertionError):
                    pruefe_messung(m, Streng("subTest"))


# ===================================================================================
# REQ-EQ-2: Wirkungszaehler (Messgleichheit am echten Buch = Review)
# ===================================================================================
class TestWirkungszaehler(BuchTest):
    def soll(self, regeln):
        return {r: {"abschnittsaenderungen": 0, "textaenderungen": 1, "seiten": [SEITE_DER_REGEL[r]]} for r in regeln}

    @unittest.skip("devloop: REQ-EQ-2 noch nicht implementiert")
    def test_req_eq_2_je_regel_ein_fall_zaehler_eins_mit_seite(self):
        """[REQ-EQ-2] Synthetisches Buch mit je einem Fall pro Text-Regel (je eigene Seite, je eine Textaenderung), alle Regeln an -> jeder Regelzaehler = 1 mit der richtigen Seite; die Texte zeigen die Wirkung."""
        self.deklariere(eqa.buchdekl(liste=LISTE, **eqa.ALLE_REGELN))
        p = self.lies_alle()
        self.assertEqual({r: p.wirkung[r] for r in TEXTREGELN}, self.soll(TEXTREGELN))
        self.assertEqual({r: self.protokoll_datei()["wirkung"][r] for r in TEXTREGELN}, self.soll(TEXTREGELN))
        text = self.gesamttext()
        for r, soll in ERWARTET_TEXT.items():
            self.assertIn(soll, text, r)
        mit = self.texte()                                   # inkrementell: die Zaehler addieren sich (K1)
        self.deklariere(eqa.buchdekl(liste=LISTE))
        self.lies_alle()
        ohne_alle = self.texte()
        geaendert = sum(mit[k] != ohne_alle[k] for k in mit)
        self.assertEqual(geaendert, sum(p.wirkung[r]["textaenderungen"] + p.wirkung[r]["abschnittsaenderungen"]
                                        for r in TEXTREGELN))

    @unittest.skip("devloop: REQ-EQ-2 noch nicht implementiert")
    def test_req_eq_2_eine_regel_aus_ihr_zaehler_fehlt(self):
        """[REQ-EQ-2] Je eine Regel aus (Schluessel fehlt) -> ihr Zaehler fehlt im Protokoll, die Zaehler der anderen bleiben unveraendert; EQ-3 aus nimmt EQ-6 mit (K2); EQ-21 aus -> sein Zaehler fehlt."""
        for regel in TEXTREGELN + ("REQ-EQ-21",):
            with self.subTest(aus=regel):
                self.deklariere(eqa.buchdekl(liste=LISTE, **ohne(regel)))
                p = self.lies_alle()
                aus = {regel} | MIT_AUS.get(regel, set())
                for r in aus:
                    self.assertNotIn(r, p.wirkung)
                andere = [r for r in TEXTREGELN if r not in aus]
                self.assertEqual({r: p.wirkung.get(r) for r in andere}, self.soll(andere))

    @unittest.skip("devloop: REQ-EQ-2 noch nicht implementiert")
    def test_req_eq_2_tabellenkopf_zaehlt_die_haeppchen_mit_vorsatz(self):
        """[REQ-EQ-2] U1: EQ-21 zaehlt die Haeppchen mit Vorsatz in der Ausgabe des Index-Laufs je Buch (wie die Haeppchenzahl, REQ-MB-14), nicht im Einlese-Protokoll. Sollzahl aus dem Wortlaut-Orakel (test_tabellenkopf.soll_vorsatz); Buch ohne tabellenkopf meldet keine Vorsaetze."""
        import re
        import test_tabellenkopf as tk
        self.deklariere(eqa.buchdekl("nord", "Buch Nord", quelle="nord.pdf", liste=LISTE, **eqa.ALLE_REGELN),
                        eqa.buchdekl("sued", "Buch Sued", quelle="sued.pdf", liste=LISTE, **ohne("REQ-EQ-21")))
        p = self.lies_alle(bid="nord")
        self.lies_alle(bid="sued")
        self.assertNotIn("REQ-EQ-21", getattr(p, "wirkung", {}))          # das Einlesen kennt CHUNK_SIZE nicht
        _, el = alle_regeln_buch()
        kopftext = "Würfeltabelle\nStufe | Würfel\n"
        (a,) = [e for e in self.eintraege("nord") if e["abschnittspfad"] == ["Tabelle"]]
        tabellen = [(b, kopftext) for b in tk.bereiche(a["text"], el[7][1]._markdown)]
        stuecke = rag.zerteile(a["text"], 120, 20)
        soll = sum(bool(tk.soll_vorsatz(tabellen, i * 100, i * 100 + len(st), a["text"])) for i, st in enumerate(stuecke))
        self.assertGreater(soll, 0)
        meldungen = []
        with mock.patch.multiple(rag, CHUNK_SIZE=120, CHUNK_OVERLAP=20):
            self.baue(ausgabe=meldungen.append)
            chunks, _ = rag.lade_spiel(self.oeffne(), mb.SID)
        kopf = rag.titelvorsatz(["Tabelle"]) + kopftext
        self.assertEqual(sum(c["text"].startswith(kopf) for c in chunks if c["buch_id"] == "nord"), soll)
        self.assertNotEqual(sum(c["buch_id"] == "nord" for c in chunks), soll)   # nicht mit der Haeppchenzahl verwechselbar

        def zeile_mit(bid, n):
            vors = r"Vors(?:atz|ätze|aetze)"
            return re.compile(rf"(?<![\w-]){bid}(?![\w-]).*(?:(?<!\d){n}(?!\d)[^\d\n]{{0,25}}{vors}"
                              rf"|{vors}[^\d\n]{{0,25}}(?<!\d){n}(?!\d))")
        self.assertTrue(any(zeile_mit("nord", soll).search(m) for m in meldungen), meldungen)
        for m in meldungen:                                               # Buch ohne tabellenkopf: kein Vorsatz gemeldet
            treffer = re.search(r"(?<![\w-])sued(?![\w-]).*?(\d+)[^\d\n]{0,25}Vors(?:atz|ätze|aetze)", m)
            self.assertTrue(treffer is None or treffer.group(1) == "0", m)

    @unittest.skip("devloop: REQ-EQ-2 noch nicht implementiert")
    def test_req_eq_2_zwei_regeln_auf_derselben_seite(self):
        """[REQ-EQ-2] Inkrementell (K1): EQ-8 (Abschnitt 1) und EQ-5 (Abschnitt 2) auf derselben Seite -> je 1; EQ-5 eingeschaltet ohne eigenen Fall -> 0, obwohl der Text gegen den Lauf ohne alle Regeln abweicht. Mutation "Zaehler gegen den Lauf ohne alle Regeln" -> EQ-5 zaehlt 2 bzw. 1, rot."""
        z = eqa.Zeichnung()
        z.zeile(1, 40, 45, "Kapitel", "Helvetica-Bold", 12)
        el = {1: [E("section_header", "Kapitel", (38, 30, 555, 50)),
                  E("section_header", "Erster Teil", z.block(1, 40, 100, ["Erster Teil"])),
                  E("text", "Wirkung: \x07WIL + 5", z.block(1, 40, 140, ["Wirkung: WIL + 5"])),
                  E("section_header", "Zweiter Teil", z.block(1, 40, 180, ["Zweiter Teil"])),
                  E("text", "Das NovizenTalent wirkt.", z.block(1, 40, 220, ["Das Novizen-", "Talent wirkt."]))]}
        self.deklariere(zeichen={"steuerzeichen": True}, striche={"zeilenenden": True})
        p = self.lies(el, self.pdf_aus(z))
        self.assertEqual({r: p.wirkung[r] for r in ("REQ-EQ-8", "REQ-EQ-5")},
                         {r: {"abschnittsaenderungen": 0, "textaenderungen": 1, "seiten": [1]}
                          for r in ("REQ-EQ-8", "REQ-EQ-5")})
        el[1][4] = E("text", "Das Talent wirkt.", el[1][4]._lage)      # EQ-5-Fall weg (Quelle bleibt, Form fehlt)
        p = self.lies(el, self.pdf_aus(z))
        self.assertEqual(p.wirkung["REQ-EQ-8"], {"abschnittsaenderungen": 0, "textaenderungen": 1, "seiten": [1]})
        self.assertEqual(p.wirkung["REQ-EQ-5"], {"abschnittsaenderungen": 0, "textaenderungen": 0, "seiten": []})


# ===================================================================================
# REQ-EQ-9: Zahlenprotokoll und Textverlust
# ===================================================================================
def zahlen_buch(texte, fremdes_zeichen=False, randzahl=False):
    """Quelle: "Stufe 3", "Probe 12", "12" in je einem Kasten; texte = Docling-Texte der drei Elemente."""
    z = eqa.Zeichnung()
    z.zeile(1, 40, 45, "Kapitel", "Helvetica-Bold", 12)
    el = [E("section_header", "Kapitel", (38, 30, 555, 50))]
    for (quelle, grund), t in zip((("Stufe 3", 100), ("Probe 12", 140), ("12", 180)), texte):
        el.append(E("text", t, z.block(1, 40, grund, [quelle])))
    if fremdes_zeichen:
        z.zeile(1, 400, 600, "Q")                       # in keinem Docling-Kasten
    if randzahl:
        el.insert(0, E("page_header", "99", z.block(1, 40, 20, ["99"])))
    return z, {1: el}


def werte(zp):
    return {"gar_nicht": zp["fehlend"]["gar_nicht"], "seltener": zp["fehlend"]["seltener"],
            "erfunden": zp["zusaetzlich"]["erfunden"], "vervielfacht": zp["zusaetzlich"]["vervielfacht"],
            "textverlust": zp["textverlust"]}


def null(**k):
    d = {"gar_nicht": 0, "seltener": 0, "erfunden": 0, "vervielfacht": 0, "textverlust": 0}
    d.update(k)
    return d


class TestZahlenprotokoll(eqa.EQTest):
    def zaehle(self, texte, **kw):
        z, el = zahlen_buch(texte, **kw)
        rand = {"rand": {"kopf": 30}} if kw.get("randzahl") else {}
        self.deklariere(lesefolge=eqa.LESEFOLGE, **rand)        # Spec-2-Deklaration (K4); die Lesefolge hat hier keinen Fall
        p = self.lies(el, self.pdf_aus(z))
        return p.zahlenprotokoll

    @unittest.skip("devloop: REQ-EQ-9 noch nicht implementiert")
    def test_req_eq_9_faelle_der_spec(self):
        """[REQ-EQ-9] Quelle "Stufe 3", "Probe 12", "12": Buchtext ohne die 12 -> gar_nicht 1; "Stufe 3, Probe 12, 12, 12" -> vervielfacht 1; "Stufe 7" -> gar_nicht 2, erfunden 1; eine 12 -> seltener 1; alles da -> 0. Summe und Seite 1 gleich."""
        faelle = [(("Stufe 3", "Probe 12", "12"), null()),
                  (("Stufe 3", "Probe", "Wert"), null(gar_nicht=1)),
                  (("Stufe 3,", "Probe 12, 12,", "12"), null(vervielfacht=1)),
                  (("Stufe 7", "Probe", "Wert"), null(gar_nicht=2, erfunden=1)),
                  (("Stufe 3", "Probe 12", "Wert"), null(seltener=1))]
        for texte, soll in faelle:
            with self.subTest(texte=texte):
                zp = self.zaehle(texte)
                self.assertEqual(werte(zp), soll)
                self.assertEqual(zp["seiten"][1], soll)
                self.assertIs(type(zp["quelle"]), int)
                datei = self.protokoll_datei()["zahlenprotokoll"]
                self.assertEqual(werte(datei), soll)

    @unittest.skip("devloop: REQ-EQ-9 noch nicht implementiert")
    def test_req_eq_9_zeichen_ausserhalb_aller_kaesten_ist_textverlust(self):
        """[REQ-EQ-9] Ein Zeichen der Quelle ausserhalb aller Docling-Kaesten -> Textverlust = 1 (sonst 0)."""
        self.assertEqual(werte(self.zaehle(("Stufe 3", "Probe 12", "12"), fremdes_zeichen=True)), null(textverlust=1))

    @unittest.skip("devloop: REQ-EQ-9 noch nicht implementiert")
    def test_req_eq_9_rand_zaehlt_nicht(self):
        """[REQ-EQ-9] Seitenzahl "99" im deklarierten Kopfrand (Randzeile verworfen) -> weder fehlend noch Textverlust."""
        self.assertEqual(werte(self.zaehle(("Stufe 3", "Probe 12", "12"), randzahl=True)), null())

    @unittest.skip("devloop: REQ-EQ-9 noch nicht implementiert")
    def test_req_eq_9_text_aendert_sich_nicht(self):
        """[REQ-EQ-9] Das Zahlenprotokoll aendert keinen Text: Buch mit Spec-2-Deklaration (lesefolge ohne Fall) -> Buchdatei byte-gleich zum Stand vor der Spec (mit und ohne fehlende Zahl)."""
        for texte in (("Stufe 3", "Probe 12", "12"), ("Stufe 7", "Probe", "Wert")):
            with self.subTest(texte=texte):
                z, el = zahlen_buch(texte)
                pdf = self.pdf_aus(z)
                self.deklariere()
                self.lies_alt(el, pdf)
                alt = self.roh()
                self.deklariere(lesefolge=eqa.LESEFOLGE)       # deklarierte Regel ohne Fall (U4)
                p = self.lies(el, pdf)
                self.assertEqual(self.roh(), alt)
                self.assertIn("zahlenprotokoll", self.protokoll_datei())    # im Einlese-Protokoll, nicht in der Buchdatei
                self.assertNotEqual(p.zahlenprotokoll, "nicht_gemessen")

    @unittest.skip("devloop: REQ-EQ-9 noch nicht implementiert")
    def test_req_eq_9_ohne_pdf_oder_textebene_nicht_gemessen(self):
        """[REQ-EQ-9] Buch mit Spec-2-Deklaration: Zeilenweg ohne PDF und Docling-Weg mit PDF ohne Textebene -> "nicht_gemessen" statt 0 (Objekt und Datei)."""
        self.deklariere(lesefolge=eqa.LESEFOLGE)
        p = eqa.einlesen().lies_buch_ein(mb.SID, "nord", {1: [{"text": "Kapitel", "klasse": "section_header"},
                                                             {"text": "Stufe 3", "klasse": "text"}]})
        self.assertEqual(p.zahlenprotokoll, "nicht_gemessen")
        self.assertEqual(self.protokoll_datei()["zahlenprotokoll"], "nicht_gemessen")
        _, el = zahlen_buch(("Stufe 3", "Probe 12", "12"))
        p = self.lies(el, self.pdf_leer(1))
        self.assertEqual(p.zahlenprotokoll, "nicht_gemessen")


    @unittest.skip("devloop: REQ-EQ-9 noch nicht implementiert")
    def test_req_eq_9_ohne_spec2_deklaration_kein_zahlenprotokoll(self):
        """[REQ-EQ-9] Buch ohne Spec-2-Deklaration (K4): kein Zahlenprotokoll (fehlt oder Leerwert), pdfplumber wird nicht geoeffnet, pdfplumber_version bleibt None."""
        import pdfplumber
        z, el = zahlen_buch(("Stufe 7", "Probe", "Wert"))
        pdf = self.pdf_aus(z)
        self.deklariere()
        with mock.patch.object(pdfplumber, "open", side_effect=AssertionError("pdfplumber geoeffnet")):
            p = self.lies(el, pdf)
        self.assertTrue(eqa.ist_leer(getattr(p, "zahlenprotokoll", None)))
        self.assertTrue(eqa.ist_leer(self.protokoll_datei().get("zahlenprotokoll")))
        self.assertIsNone(p.pdfplumber_version)


# ===================================================================================
# REQ-EQ-15: Schema der Spec-2-Deklaration
# ===================================================================================
GUELTIG = {"lesefolge": {"spalten": [[35, 292], [304, 560]], "toleranz": 4, "waechter": 0.8, "ausnahmen": [2]},
           "striche": {"zeilenenden": True, "strichrest": True},
           "zeichen": {"zierumlaut": True, "steuerzeichen": True, "listennummern": False},
           "tabellenkopf": {"ausnahmen": [3]}, "tabellen": {"form": "markdown"},
           "werteblock": {"schluessel": ["Stufe:", "Aktion:"]}}
SP = [[35, 292], [304, 560]]
VERSTOESSE = [  # (Name, Deklaration, Schluessel in der Meldung)
    ("Tippfehler spalte", {"lesefolge": {"spalte": SP}}, "spalte"),
    ("Bereich verkehrt", {"lesefolge": {"spalten": [[292, 35]]}}, "spalten"),
    ("Spalten ueberlappen", {"lesefolge": {"spalten": [[35, 300], [290, 560]]}}, "spalten"),
    ("Spalten absteigend", {"lesefolge": {"spalten": [[304, 560], [35, 292]]}}, "spalten"),
    ("Spalten leer", {"lesefolge": {"spalten": []}}, "spalten"),
    ("Bereich ein Wert", {"lesefolge": {"spalten": [[35]]}}, "spalten"),
    ("Bereich Text", {"lesefolge": {"spalten": [["35", "292"]]}}, "spalten"),
    ("toleranz negativ", {"lesefolge": {"spalten": SP, "toleranz": -1}}, "toleranz"),
    ("toleranz Text", {"lesefolge": {"spalten": SP, "toleranz": "4"}}, "toleranz"),
    ("waechter 0", {"lesefolge": {"spalten": SP, "waechter": 0}}, "waechter"),
    ("waechter ueber 1", {"lesefolge": {"spalten": SP, "waechter": 1.5}}, "waechter"),
    ("waechter Wahrheitswert", {"lesefolge": {"spalten": SP, "waechter": True}}, "waechter"),
    ("ausnahmen 0", {"lesefolge": {"spalten": SP, "ausnahmen": [0]}}, "ausnahmen"),
    ("ausnahmen Text", {"lesefolge": {"spalten": SP, "ausnahmen": ["3"]}}, "ausnahmen"),
    ("ausnahmen Kommazahl", {"lesefolge": {"spalten": SP, "ausnahmen": [2.5]}}, "ausnahmen"),
    ("ausnahmen keine Liste", {"lesefolge": {"spalten": SP, "ausnahmen": 3}}, "ausnahmen"),
    ("lesefolge fremder Schluessel", {"lesefolge": {"spalten": SP, "breite": 3}}, "breite"),
    ("lesefolge kein Objekt", {"lesefolge": "ja"}, "lesefolge"),
    ("tabellenkopf ausnahmen 0", {"tabellenkopf": {"ausnahmen": [0]}}, "ausnahmen"),
    ("tabellenkopf fremder Schluessel", {"tabellenkopf": {"kopfzeilen": 2}}, "kopfzeilen"),
    ("tabellenkopf kein Objekt", {"tabellenkopf": True}, "tabellenkopf"),
    ("zeilenenden Text", {"striche": {"zeilenenden": "ja"}}, "zeilenenden"),
    ("strichrest Zahl", {"striche": {"strichrest": 1}}, "strichrest"),
    ("strichrest ohne lesefolge", {"striche": {"strichrest": True}}, "strichrest"),            # K2
    ("strichrest ohne lesefolge mit Zeichen", {"striche": {"zeilenenden": True, "strichrest": True},
                                               "zeichen": {"steuerzeichen": True}}, "strichrest"),
    ("striche fremder Schluessel", {"striche": {"trennung": True}}, "trennung"),
    ("zierumlaut ja", {"zeichen": {"zierumlaut": "ja"}}, "zierumlaut"),
    ("steuerzeichen Zahl", {"zeichen": {"steuerzeichen": 1}}, "steuerzeichen"),
    ("listennummern null", {"zeichen": {"listennummern": None}}, "listennummern"),
    ("zeichen fremder Schluessel", {"zeichen": {"umlaut": True}}, "umlaut"),
    ("form md", {"tabellen": {"form": "md"}}, "form"),
    ("tabellen fremder Schluessel", {"tabellen": {"form": "markdown", "kopf": 1}}, "kopf"),
    ("schluessel leer", {"werteblock": {"schluessel": []}}, "schluessel"),
    ("schluessel leere Zeichenkette", {"werteblock": {"schluessel": [""]}}, "schluessel"),
    ("schluessel Zeichenkette", {"werteblock": {"schluessel": "Stufe:"}}, "schluessel"),
    ("schluessel Zahl", {"werteblock": {"schluessel": [3]}}, "schluessel"),
    ("werteblock fremder Schluessel", {"werteblock": {"schluessel": ["Stufe:"], "trenner": ";"}}, "trenner"),
]
SCHEMA_ELEMENTE = {1: [E("section_header", "Kapitel", (40, 30, 555, 50)), E("text", "Text eins.", (40, 100, 290, 120))]}


class TestSchema(eqa.EQTest):
    @unittest.skip("devloop: REQ-EQ-15 noch nicht implementiert")
    def test_req_eq_15_verstoesse_brechen_ab_ohne_zu_schreiben(self):
        """[REQ-EQ-15] Je Schemaverstoss jedes neuen Schluessels (u. a. Tippfehler "spalte", [292, 35], ueberlappende Spalten, form "md", zierumlaut "ja") -> KonfigFehler mit dem Schluessel, keine Buchdatei bzw. die alte byte-gleich. Mutation "Schemapruefung aus" -> rot."""
        pdf = self.pdf_leer(1)
        for name, dekl, schluessel in VERSTOESSE:
            with self.subTest(fall=name):
                self.deklariere(**dekl)
                if os.path.exists(self.buchdatei_pfad()):
                    os.remove(self.buchdatei_pfad())
                with self.assertRaises(rag.KonfigFehler) as ctx:
                    self.lies(SCHEMA_ELEMENTE, pdf)
                self.assertIn(schluessel, str(ctx.exception))
                self.assertFalse(os.path.exists(self.buchdatei_pfad()))
                self.deklariere()
                self.lies(SCHEMA_ELEMENTE, pdf)
                vorher = mb.hashes(os.path.dirname(self.buchdatei_pfad()))
                self.deklariere(**dekl)
                with self.assertRaises(rag.KonfigFehler):
                    self.lies(SCHEMA_ELEMENTE, pdf)
                self.assertEqual(mb.hashes(os.path.dirname(self.buchdatei_pfad())), vorher)

    @unittest.skip("devloop: REQ-EQ-15 noch nicht implementiert")
    def test_req_eq_15_gueltige_vollstaendige_deklaration_liest_ein(self):
        """[REQ-EQ-15] Gueltige Deklaration mit allen sechs Schluesseln (auch Defaults weggelassen: toleranz/waechter fehlen) liest ein; strichrest false ohne lesefolge ist zulaessig (K2)."""
        for dekl in (GUELTIG, {"lesefolge": {"spalten": [[35, 560]]}}, {"striche": {"zeilenenden": True, "strichrest": False}}):
            with self.subTest(dekl=sorted(dekl)):
                self.deklariere(**dekl)
                self.lies(SCHEMA_ELEMENTE, self.pdf_leer(1))
                self.assertIn("Text eins.", self.gesamttext())


# ===================================================================================
# REQ-EQ-16: Abschaltbarkeit und Rueckwaertskompatibilitaet
# ===================================================================================
class TestAbschaltbar(BuchTest):
    @unittest.skip("devloop: REQ-EQ-16 noch nicht implementiert")
    def test_req_eq_16_buch_ohne_deklaration_byte_gleich_und_protokoll_behaelt_felder(self):
        """[REQ-EQ-16] Zwei-Buecher-Bestand, nur Buch A mit Spec-2-Deklaration: Buch B byte-gleich zum Einlesen mit dem Stand vor der Spec (BASIS_COMMIT); B-Protokoll behaelt alle bisherigen Felder mit gleichen Werten (auch pdfplumber_version), neue nur mit Leerwerten (auch zahlenprotokoll, K4); fuer B wird pdfplumber nicht geoeffnet; A weicht ab."""
        z, el = alle_regeln_buch()
        pdf = self.pdf_aus(z, 7)
        self.deklariere(eqa.buchdekl("a", "Buch A", quelle="a.pdf", liste=LISTE, **eqa.ALLE_REGELN),
                        eqa.buchdekl("b", "Buch B", quelle="b.pdf", liste=LISTE))
        p_alt = self.lies_alt(el, pdf, bid="b")
        alt = self.roh("b")
        self.lies(el, pdf, bid="a")
        import pdfplumber
        with mock.patch.object(pdfplumber, "open", side_effect=AssertionError("pdfplumber fuer Buch B geoeffnet")):
            p = self.lies(el, pdf, bid="b")
        self.assertEqual(self.roh("b"), alt)
        self.assertNotEqual([e["text"] for e in self.eintraege("a")], [e["text"] for e in self.eintraege("b")])
        neu, vorher = p.als_dict(), p_alt.als_dict()
        for feld, wert in vorher.items():
            with self.subTest(feld=feld):
                self.assertEqual(neu[feld], wert)
        self.assertIsNone(neu["pdfplumber_version"])
        for feld in set(neu) - set(vorher):
            with self.subTest(neues_feld=feld):
                self.assertTrue(eqa.ist_leer(neu[feld]), (feld, neu[feld]))

    @unittest.skip("devloop: REQ-EQ-16 noch nicht implementiert")
    def test_req_eq_16_alle_schalter_aus_gilt_wie_keine_deklaration(self):
        """[REQ-EQ-16] U3: Spec-2-Deklaration mit allen Schaltern false (striche, zeichen) -> wie keine Deklaration: Buchdatei byte-gleich zum Stand vor der Spec, pdfplumber nicht geoeffnet, kein Zahlenprotokoll, pdfplumber_version None, keine Wirkungszaehler."""
        import pdfplumber
        z, el = alle_regeln_buch()
        pdf = self.pdf_aus(z, 7)
        self.deklariere(eqa.buchdekl(liste=LISTE))
        self.lies_alt(el, pdf)
        alt = self.roh()
        aus = {"striche": {"zeilenenden": False, "strichrest": False},
               "zeichen": {"zierumlaut": False, "steuerzeichen": False, "listennummern": False}}
        self.deklariere(eqa.buchdekl(liste=LISTE, **aus))
        with mock.patch.object(pdfplumber, "open", side_effect=AssertionError("pdfplumber geoeffnet")):
            p = self.lies(el, pdf)
        self.assertEqual(self.roh(), alt)
        self.assertTrue(eqa.ist_leer(getattr(p, "zahlenprotokoll", None)))
        self.assertTrue(eqa.ist_leer(self.protokoll_datei().get("zahlenprotokoll")))
        self.assertIsNone(p.pdfplumber_version)
        self.assertTrue(eqa.ist_leer(getattr(p, "wirkung", None)))

    @unittest.skip("devloop: REQ-EQ-16 noch nicht implementiert")
    def test_req_eq_16_je_regel_aus_aendert_sich_nur_deren_fall(self):
        """[REQ-EQ-16] Je Regel ein Lauf mit nur dieser Regel aus -> nur der Abschnitt ihres Falls aendert sich (Buchdatei; fuer EQ-21 die Haeppchen); EQ-3 aus nimmt EQ-6 mit (K2) -> deren beide Abschnitte."""
        self.deklariere(eqa.buchdekl(liste=LISTE, **eqa.ALLE_REGELN))
        self.lies_alle()
        alle = self.texte()
        buch = rag.lies_buecher(mb.SID)[0]
        alle_st = rag.buch_stuecke(self.eintraege(), buch, 120, 20)
        for regel, seite in SEITE_DER_REGEL.items():
            with self.subTest(aus=regel):
                self.deklariere(eqa.buchdekl(liste=LISTE, **ohne(regel)))
                self.lies_alle()
                texte = self.texte()
                self.assertEqual(set(texte), set(alle))
                anders = {pfad for pfad in alle if texte[pfad] != alle[pfad]}
                if regel == "REQ-EQ-21":
                    self.assertEqual(anders, set())
                    st = rag.buch_stuecke(self.eintraege(), buch, 120, 20)
                    self.assertEqual(len(st), len(alle_st))
                    anders = {tuple(a["abschnittspfad"]) for a, b in zip(st, alle_st) if a["text"] != b["text"]}
                seiten = [seite] + [SEITE_DER_REGEL[r] for r in MIT_AUS.get(regel, ())]
                self.assertEqual(anders, {(KAPITEL[s - 1],) for s in seiten})

    @unittest.skip("devloop: REQ-EQ-16 noch nicht implementiert")
    def test_req_eq_16_altbestand_und_spec1_buchdatei_im_index_unveraendert(self):
        """[REQ-EQ-16] Altbestand (eine knowledge.jsonl) und eine Buchdatei vom Stand vor der Spec ergeben im Index dieselben Haeppchen wie mit rag.py aus BASIS_COMMIT."""
        alt_rag, _ = eqa.alte_module()
        roh = [{"id": j, "seite": j + 1, "typ": "regel", "text": f"Regel {j} Stufe {j} " * 30, "spiel": "Alt",
                "spiel_id": "alt"} for j in range(5)]
        for size, overlap in ((120, 20), (400, 150)):
            with self.subTest(size=size):
                self.assertEqual(rag.indexiere_stuecke(roh, size, overlap), alt_rag.indexiere_stuecke(roh, size, overlap))
        _, el = alle_regeln_buch()
        self.deklariere(eqa.buchdekl(liste=LISTE))
        self.lies_alt(el, self.pdf_leer(7))
        eintraege, buch = self.eintraege(), rag.lies_buecher(mb.SID)[0]
        self.assertEqual(rag.buch_stuecke(eintraege, buch, 120, 20), alt_rag.buch_stuecke(eintraege, buch, 120, 20))


# ===================================================================================
# REQ-EQ-17: generisch -- Umbenennen der Bezeichner aendert kein Ergebnis
# ===================================================================================
class TestGenerisch(BuchTest):
    @unittest.skip("devloop: REQ-EQ-17 noch nicht implementiert")
    def test_req_eq_17_umbenennen_aendert_kein_ergebnis(self):
        """[REQ-EQ-17] Dasselbe synthetische Buch mit allen Regeln als testwelt/nord/alpha und als andere-welt/sued/beta (anderer Titel, andere Quelle) -> gleiche Abschnitte, Texte, Seitenwechsel und gleiche Spec-2-Protokollzaehler."""
        self.deklariere(eqa.buchdekl(liste=LISTE, **eqa.ALLE_REGELN))
        p1 = self.lies_alle()
        self.bestand([eqa.buchdekl("sued", "Fremdes Werk", "beta", quelle="fremd.pdf", liste=LISTE, **eqa.ALLE_REGELN)],
                     sid="andere-welt", name="Andere Welt")
        p2 = self.lies_alle(bid="sued", sid="andere-welt")

        def kern(eintraege):
            return [(e["abschnittspfad"], e["text"], e["seitenwechsel"], e.get("tabellen")) for e in eintraege]
        self.assertEqual(kern(self.eintraege("sued", "andere-welt")), kern(self.eintraege()))
        for feld in ("wirkung", "zeilenenden", "strich_vor_grossbuchstabe", "zahlenprotokoll", "tabellen_ohne_kopf",
                     "lesefolge_ausnahmen"):
            with self.subTest(feld=feld):
                self.assertEqual(getattr(p2, feld), getattr(p1, feld))
        self.assertIn("Das Novizen-Talent wirkt.", "\n".join(e["text"] for e in self.eintraege("sued", "andere-welt")))


# ===================================================================================
# REQ-EQ-18: kein Lesen echter Buecher, Schreiben nur im Temp-Bestand
# ===================================================================================
class TestSchutz(BuchTest):
    @unittest.skip("devloop: REQ-EQ-18 noch nicht implementiert")
    def test_req_eq_18_einlesen_mit_allen_regeln_liest_und_schreibt_nur_temp_und_spec_ordner(self):
        """[REQ-EQ-18] Einlesen mit allen Spec-2-Regeln + Index: jede geoeffnete Datei liegt im Temp-Verzeichnis, im Spec-Ordner oder ausserhalb des Repos (Bibliotheken); keine PDF ausserhalb des Temp-Verzeichnisses; geschrieben wird nur unter dem Temp-DATA_DIR (auch die neuen Protokollfelder)."""
        z, el = alle_regeln_buch()
        pdf = self.pdf_aus(z, 7)
        self.deklariere(eqa.buchdekl(liste=LISTE, **eqa.ALLE_REGELN))
        geoeffnet = []
        echt = builtins.open

        def protokollierend(datei, modus="r", *a, **k):
            if isinstance(datei, (str, bytes, os.PathLike)):
                geoeffnet.append((os.path.realpath(os.fsdecode(datei)), modus))
            return echt(datei, modus, *a, **k)
        with mock.patch("builtins.open", protokollierend):
            p = self.lies(el, pdf)
            with mock.patch.multiple(rag, CHUNK_SIZE=120, CHUNK_OVERLAP=20):
                self.baue()
        self.assertTrue(p.wirkung)
        temp = {os.path.realpath(d) for d in (self.tmp.name, tempfile.gettempdir(), testumgebung.TMP)}
        repo, spec = os.path.realpath(BASE), os.path.realpath(os.path.join(BASE, ".specify", "specs"))
        daten = os.path.realpath(self.data)

        def unter(pfad, wurzel):
            return pfad == wurzel or pfad.startswith(wurzel + os.sep)
        self.assertTrue(geoeffnet)
        for pfad, modus in geoeffnet:
            with self.subTest(pfad=pfad):
                im_temp = any(unter(pfad, t) for t in temp)
                self.assertTrue(im_temp or unter(pfad, spec) or not unter(pfad, repo), pfad)
                if pfad.lower().endswith(".pdf"):
                    self.assertTrue(im_temp, pfad)
                if any(m in modus for m in "wax+"):
                    self.assertTrue(unter(pfad, daten), pfad)
        self.assertIn(os.path.realpath(pdf), [g for g, _ in geoeffnet])          # die Pruefung sah die PDF wirklich


# ===================================================================================
# REQ-EQ-19: Versionen gegen die Spec-2-Vorab-Messung
# ===================================================================================
ZEILEN = {1: [{"text": "Kapitel", "klasse": "section_header"}, {"text": "Text \x07eins.", "klasse": "text"}]}


class TestVersionen(eqa.EQTest):
    def setUp(self):
        super().setUp()
        self.mb_messung = os.path.join(self.tmp.name, "mb.json")
        self.eq_messung = os.path.join(self.tmp.name, "eq.json")
        with open(self.mb_messung, "w", encoding="utf-8") as f:
            json.dump({"docling_version": "2.5.1", "pdfplumber_version": "0.11.4"}, f)

    def schreibe_eq(self, **felder):
        with open(self.eq_messung, "w", encoding="utf-8") as f:
            json.dump(felder, f)

    def lies_zeilen(self, docling="2.5.1", pdfplumber=None, **kw):
        return eqa.einlesen().lies_buch_ein(mb.SID, "nord", ZEILEN, docling_version=docling,
                                            pdfplumber_version=pdfplumber, vorabmessung=self.mb_messung,
                                            vorabmessung_eq=self.eq_messung, **kw)

    def pruefe_abbruch(self, **versionen):
        with self.assertRaises(rag.KonfigFehler):
            self.lies_zeilen(**versionen)
        self.assertFalse(os.path.exists(self.buchdatei_pfad()))
        self.deklariere()
        self.lies_zeilen()                                                # ohne Spec-2-Deklaration: laeuft
        vorher = mb.hashes(os.path.dirname(self.buchdatei_pfad()))
        self.deklariere(zeichen={"steuerzeichen": True})
        with self.assertRaises(rag.KonfigFehler):
            self.lies_zeilen(ueberschreiben=True, **versionen)
        self.assertEqual(mb.hashes(os.path.dirname(self.buchdatei_pfad())), vorher)

    @unittest.skip("devloop: REQ-EQ-19 noch nicht implementiert")
    def test_req_eq_19_gleiche_versionen_laufen(self):
        """[REQ-EQ-19] Spec-2-Deklaration, Docling- und pdfplumber-Version gleich der Spec-2-Messung -> laeuft, Regel wirkt."""
        self.schreibe_eq(docling_version="2.5.1", pdfplumber_version="0.11.4")
        self.deklariere(zeichen={"steuerzeichen": True})
        self.lies_zeilen(pdfplumber="0.11.4")
        self.assertIn("Text eins.", self.gesamttext())

    @unittest.skip("devloop: REQ-EQ-19 noch nicht implementiert")
    def test_req_eq_19_abweichende_docling_version(self):
        """[REQ-EQ-19] Docling-Version passt zu Spec 1, weicht aber von der Spec-2-Messung ab -> KonfigFehler, keine Buchdatei bzw. die alte unveraendert."""
        self.schreibe_eq(docling_version="2.5.2", pdfplumber_version="0.11.4")
        self.deklariere(zeichen={"steuerzeichen": True})
        self.pruefe_abbruch()

    @unittest.skip("devloop: REQ-EQ-19 noch nicht implementiert")
    def test_req_eq_19_abweichende_pdfplumber_version(self):
        """[REQ-EQ-19] Buch ohne Schriftstufen (Spec 1 prueft pdfplumber nicht), Spec-2-Deklaration, pdfplumber-Version weicht von der Spec-2-Messung ab -> KonfigFehler."""
        self.schreibe_eq(docling_version="2.5.1", pdfplumber_version="0.11.9")
        self.deklariere(zeichen={"steuerzeichen": True})
        self.pruefe_abbruch(pdfplumber="0.11.4")

    @unittest.skip("devloop: REQ-EQ-19 noch nicht implementiert")
    def test_req_eq_19_fehlende_messung_oder_version(self):
        """[REQ-EQ-19] Spec-2-Messung fehlt bzw. nennt keine docling_version -> KonfigFehler, keine Buchdatei bzw. die alte unveraendert."""
        self.deklariere(zeichen={"steuerzeichen": True})
        self.assertFalse(os.path.exists(self.eq_messung))
        self.pruefe_abbruch()
        self.schreibe_eq(pdfplumber_version="0.11.4")
        self.deklariere(zeichen={"steuerzeichen": True})
        os.remove(self.buchdatei_pfad())
        self.pruefe_abbruch()

    @unittest.skip("devloop: REQ-EQ-19 noch nicht implementiert")
    def test_req_eq_19_buch_ohne_spec2_deklaration_braucht_die_datei_nicht(self):
        """[REQ-EQ-19] Buch ohne Spec-2-Deklaration liest trotz fehlender Spec-2-Messung ein (nur Spec-1-Pruefung)."""
        self.deklariere()
        self.assertFalse(os.path.exists(self.eq_messung))
        self.lies_zeilen(pdfplumber="0.11.4")
        self.assertTrue(os.path.exists(self.buchdatei_pfad()))


# ===================================================================================
# REQ-EQ-20: Performance (Zeittests zaehlen in Mutationsproben nicht als Fang)
# ===================================================================================
def perf_seite(dicht=False):
    """Eine Seite wie das Zielbuch (8.174 Elemente / 314 Seiten ~ 26 je Seite; dicht: 52): zwei Spalten,
    Ueberschriften, Zeilenend-Striche, Steuerzeichen, Zierumlaute, Listen, eine Tabelle; Docling-Folge
    im Zickzack ueber die Spalten (die Lesefolge hat zu tun)."""
    z = eqa.Zeichnung()
    groesse, abstand, luecke, je_spalte = (7, 8, 6, 26) if dicht else (10, 12, 10, 13)
    z.zeile(1, 40, 45, "Kapitel", "Helvetica-Bold", 12)
    kopf = E("section_header", "Kapitel", (38, 30, 555, 50))
    spalten = []
    for s, x in enumerate((40, 310)):
        liste, grund = [], 80
        for k in range(je_spalte):
            i = s * je_spalte + k
            if k % 6 == 0:
                zeilen, t, kw = [f"Abschnitt {i}"], f"Abschnitt {i}", {"label": "section_header"}
            elif k % 6 == 2:
                zeilen, t, kw = [f"Probe {i} mit Akti-", "onswürfel und Rang."], f"Probe {i} mit Akti- onswürfel und Rang.", {}
            elif k % 6 == 3:
                zeilen, t, kw = [f"{i}. Punkt der Liste."], "Punkt der Liste.", {"label": "list_item", "enumerated": True,
                                                                                "marker": f"{i}."}
            elif k % 6 == 4:
                zeilen, t, kw = [f"Wirkung: WIL + {i}", "Für den Rest."], f"Wirkung: \x07WIL + {i} Fu . . r den Rest.", {}
            else:
                zeilen, t, kw = [f"Regeltext {i} mit Novizen-", "Talent und Stufe."], f"Regeltext {i} mit NovizenTalent und Stufe.", {}
            label = kw.pop("label", "text")
            lage = z.block(1, x, grund, zeilen, abstand, groesse=groesse)
            liste.append(E(label, t, lage, **kw))
            grund += abstand * len(zeilen) + luecke
        spalten.append(liste)
    zickzack = [e for paar in zip(*spalten) for e in paar]
    tab = eqa.tabelle([[eqa.Spanne("Tabelle", 2)], ["Stufe", "Wert"]] + [[str(i), str(i + 3)] for i in range(8)],
                      kopf=[1], lage=(310, 700, 555, 790))
    return z, {1: [kopf] + zickzack + [tab]}


class TestPerformance(eqa.EQTest):
    WDH = 5

    def setUp(self):
        super().setUp()
        self.deklariere(eqa.buchdekl("mit", "Buch Mit", quelle="mit.pdf", **eqa.ALLE_REGELN),
                        eqa.buchdekl("ohne", "Buch Ohne", quelle="ohne.pdf"))
        self.seiten = []
        for n in range(15):
            z, el = perf_seite(dicht=n >= 12)
            self.seiten.append((el, self.pdf_aus(z, 1)))

    def lauf(self, bid, pdf):
        t = time.perf_counter()
        eqa.einlesen().lies_pdf_ein(mb.SID, bid, pdf=pdf, ueberschreiben=True, ausgabe=lambda *_: None)
        return (time.perf_counter() - t) * 1000

    def messe(self, el, pdf, gecacht):
        """(Zusatzzeit Median ms, Zeit mit Regeln Median ms) einer Seite; abwechselnde Reihenfolge, GC aus."""
        import contextlib
        with da.installiere(el, eqa.versionen()), (eqa.vorgeparst(pdf) if gecacht else contextlib.nullcontext()):
            self.lauf("mit", pdf)
            self.lauf("ohne", pdf)
            diffs, mit = [], []
            gc.collect()
            gc.disable()
            try:
                for w in range(self.WDH):
                    if w % 2 == 0:
                        a = self.lauf("mit", pdf)
                        b = self.lauf("ohne", pdf)
                    else:
                        b = self.lauf("ohne", pdf)
                        a = self.lauf("mit", pdf)
                    diffs.append(a - b)
                    mit.append(a)
            finally:
                gc.enable()
        return statistics.median(diffs), statistics.median(mit)

    @unittest.skip("devloop: REQ-EQ-20 noch nicht implementiert")
    def test_req_eq_20_zusatzzeit_je_seite_typisch_20_max_200_ms(self):
        """[REQ-EQ-20] Zusatzzeit aller Spec-2-Regeln je Seite (ohne Docling, PDF vorab in pdfplumber geoeffnet), 15 Seiten mit 27/53 Elementen: typisch (Median) <= 20 ms, Maximum <= 200 ms; Mittel <= 10 % der Zielbuch-Einlesezeit je Seite (177 s / 314 = 56 ms, Wirkungszaehler inklusive)."""
        zusatz = [self.messe(el, pdf, gecacht=True)[0] for el, pdf in self.seiten]
        typ, mx, mittel = statistics.median(zusatz), max(zusatz), statistics.mean(zusatz)
        print(f"\n  REQ-EQ-20 Zusatzzeit je Seite (15 Seiten): typisch {typ:.2f} ms, Maximum {mx:.2f} ms, "
              f"Mittel {mittel:.2f} ms")
        self.assertLessEqual(typ, 20.0)
        self.assertLessEqual(mx, 200.0)
        self.assertLessEqual(mittel, 0.1 * 177000 / 314)

    @unittest.skip("devloop: REQ-EQ-20 noch nicht implementiert")
    def test_req_eq_20_pdfplumber_je_seite_typisch_0_1_max_0_5_s(self):
        """[REQ-EQ-20] pdfplumber-Anteil je Seite (Einlesen mit Regeln, echtes Oeffnen minus vorab geoeffnet): typisch <= 0,1 s, Maximum <= 0,5 s."""
        anteile = []
        for el, pdf in self.seiten:
            _, gecacht = self.messe(el, pdf, gecacht=True)
            _, echt = self.messe(el, pdf, gecacht=False)
            anteile.append(echt - gecacht)
        typ, mx = statistics.median(anteile), max(anteile)
        print(f"\n  REQ-EQ-20 pdfplumber je Seite: typisch {typ:.1f} ms, Maximum {mx:.1f} ms")
        self.assertLessEqual(typ, 100.0)
        self.assertLessEqual(mx, 500.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
