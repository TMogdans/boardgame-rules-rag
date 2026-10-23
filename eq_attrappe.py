# -*- coding: utf-8 -*-
"""
Testhilfen fuer Spec 2 (.specify/specs/einlese-qualitaet/spec.md) -- nur synthetische Daten
(REQ-EQ-17/-18): Bestand "testwelt", Buecher "nord"/"sued", Fassungen alpha/beta, frei erfundene
Woerter. Kein echtes Buch, kein Lesen von DATA_DIR.

Baut auf docling_attrappe.py auf (Enum-Labels, bbox mit Ursprung unten links, weitere_kaesten) und
ergaenzt, was Spec 2 an Docling-Struktur braucht:
  - Element(label, ...) mit zusaetzlichem Label "list_item" (enumerated, marker wie
    docling_core.ListItem) und Tabellen-Raster (item.data wie docling_core.TableData:
    table_cells, num_rows, num_cols, grid; je Zelle text, column_header, row_header,
    start_/end_row_offset_idx, start_/end_col_offset_idx, row_span, col_span)
  - tabelle(zeilen, kopf, lage): Docling-Tabelle mit Raster und Markdown-Export (Zeile 0 ist die
    Markdown-Kopfzeile, dann die Trennzeile, wie Docling/tabulate "github")
  - Zeichnung: reportlab-PDF mit Textzeilen an festen Grundlinien (ab OBERER Kante, wie
    pdfplumber); block() liefert den Docling-Kasten (x0, oben, x1, unten) passend zum Text
  - alte_module(): einlesen.py und rag.py vom Stand vor Spec 2 (BASIS_COMMIT, per `git show`, nur
    lesend) als eigene Module -- der echte alte Weg, keine Nachbildung (REQ-EQ-16)
  - EQTest: Bestand anlegen, Docling-Weg (lies_pdf_ein) mit Attrappe laufen lassen, Buchdatei lesen
"""
import contextlib
import enum
import importlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from unittest import mock

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402
import docling_attrappe as da  # noqa: E402
import test_mehrbuch as mb  # noqa: E402

HOEHE, BREITE = da.HOEHE, da.BREITE
SPEC2 = os.path.join(BASE, ".specify", "specs", "einlese-qualitaet")
VORABMESSUNG_EQ = os.path.join(SPEC2, "vorabmessung.json")
VORABMESSUNG_MB = os.path.join(BASE, ".specify", "specs", "mehrbuch-bestand", "vorabmessung.json")
# Letzter Stand von einlesen.py/rag.py vor Spec 2 (main nach dem Spec-PR, Code = Spec-1-Stand). Bewusst
# ein fester Commit: "HEAD von main" waere nach dem Merge schon der neue Code.
BASIS_COMMIT = "af85b7939c79246ed726abfedc6263839a889f61"
SHY = "­"

# Spaltenraster wie im Zielbuch gemessen (Daten, nicht Code; REQ-EQ-17)
SPALTEN = [[35, 292], [304, 560]]
LESEFOLGE = {"spalten": SPALTEN, "toleranz": 4, "waechter": 0.8}
KONJUNKTIONEN = ["und", "oder", "bis", "sowie", "bzw", "als", "beziehungsweise"]
ALLE_REGELN = {"lesefolge": LESEFOLGE, "striche": {"zeilenenden": True, "strichrest": True},
               "zeichen": {"zierumlaut": True, "steuerzeichen": True, "listennummern": True},
               "tabellenkopf": {}}


def einlesen():
    """Spaet importiert, wie in den Spec-1-Tests."""
    return importlib.import_module("einlesen")


def versionen():
    """Docling-/pdfplumber-Version aus der Spec-2-Vorab-Messung -- dieselben, die das Einlesen verlangt."""
    with open(VORABMESSUNG_EQ, encoding="utf-8") as f:
        m = json.load(f)
    return {"docling": m["docling_version"], "pdfplumber": m["pdfplumber_version"]}


# ---------- Docling-Struktur ----------
class Label(str, enum.Enum):
    TEXT = "text"
    SECTION_HEADER = "section_header"
    TABLE = "table"
    PICTURE = "picture"
    CAPTION = "caption"
    PAGE_HEADER = "page_header"
    PAGE_FOOTER = "page_footer"
    LIST_ITEM = "list_item"
    FOOTNOTE = "footnote"
    CHART = "chart"


class Element(da.Element):
    """da.Element mit Spec-2-Feldern. lage = (x0, oben, x1, unten) ab OBEN links; gespeichert wie bei
    Docling mit Ursprung unten links (da.Element._setze_seite)."""

    def __init__(self, label, text="", lage=None, kinder=(), markdown=None, weitere_kaesten=(),
                 enumerated=None, marker=None, daten=None):
        super().__init__("text", text, lage, kinder, markdown, weitere_kaesten)
        self.label = Label(label)
        if self.label == Label.LIST_ITEM:
            self.enumerated = bool(enumerated)
            self.marker = marker or ""
        if daten is not None:
            self.data = daten


class Spanne:
    """Zelle, die ueber `breite` Spalten reicht (Titelzeile)."""

    def __init__(self, text, breite):
        self.text, self.breite = text, breite


class Zelle:
    def __init__(self, text, zeile, spalte, breite, kopf):
        self.text = text
        self.start_row_offset_idx, self.end_row_offset_idx = zeile, zeile + 1
        self.start_col_offset_idx, self.end_col_offset_idx = spalte, spalte + breite
        self.row_span, self.col_span = 1, breite
        self.column_header, self.row_header, self.row_section = kopf, False, False
        self.bbox = None


class TabellenDaten:
    """Wie docling_core TableData: table_cells (jede Zelle einmal), grid (Spannzellen je Spalte
    wiederholt), num_rows, num_cols."""

    def __init__(self, zeilen, kopf):
        self.table_cells, self.grid = [], []
        for r, zeile in enumerate(zeilen):
            reihe, c = [], 0
            for z in zeile:
                text, breite = (z.text, z.breite) if isinstance(z, Spanne) else (z, 1)
                zelle = Zelle(text, r, c, breite, r in kopf)
                self.table_cells.append(zelle)
                reihe += [zelle] * breite
                c += breite
            self.grid.append(reihe)
        self.num_rows, self.num_cols = len(self.grid), len(self.grid[0])


def markdown(daten):
    """Markdown wie Docling (tabulate "github"): Zeile 0 = Kopfzeile, dann die Trennzeile; Spannzellen
    stehen in jeder Spalte; Zellen auf Spaltenbreite aufgefuellt."""
    zeilen = [[z.text for z in reihe] for reihe in daten.grid]
    breiten = [max(3, max(len(r[i]) for r in zeilen)) for i in range(daten.num_cols)]

    def zeile(r):
        return "| " + " | ".join(t.ljust(b) for t, b in zip(r, breiten)) + " |"
    return "\n".join([zeile(zeilen[0]), "|" + "|".join("-" * (b + 2) for b in breiten) + "|"]
                     + [zeile(r) for r in zeilen[1:]])


def tabelle(zeilen, kopf=(), lage=None):
    """Docling-Tabelle. zeilen: [[Zelle, ...]], Zelle = Text oder Spanne; kopf: Zeilenindizes, deren
    Zellen column_header tragen."""
    d = TabellenDaten(zeilen, set(kopf))
    return Element("table", "", lage, markdown=markdown(d), daten=d)


def kopfbereich(md):
    """Die ersten zwei Zeilen des Tabellen-Markdowns (Begriffe: Kopfbereich), ohne Zeilenumbruch danach."""
    a, b = md.split("\n")[:2]
    return a + "\n" + b


# ---------- PDF ----------
class Zeichnung:
    """Textzeilen fuer ein reportlab-PDF; grund = Grundlinie ab der OBEREN Seitenkante."""
    FONT, GROESSE = "Helvetica", 10

    def __init__(self):
        self.seiten = {}
        self.linien = {}

    def linie(self, seite, x0, y, x1, staerke=1):
        """Vektorlinie (kein Text, kein Docling-Element) in Hoehe y ab der OBEREN Kante."""
        self.linien.setdefault(seite, []).append((x0, y, x1, staerke))

    @staticmethod
    def breite(text, font=None, groesse=None):
        from reportlab.pdfbase.pdfmetrics import stringWidth
        return stringWidth(text, font or Zeichnung.FONT, groesse or Zeichnung.GROESSE)

    def zeile(self, seite, x, grund, text, font=None, groesse=None):
        self.seiten.setdefault(seite, []).append((x, grund, text, font or self.FONT, groesse or self.GROESSE))
        return self.breite(text, font, groesse)

    def stuecke(self, seite, x, grund, teile, font=None, groesse=None):
        """Eine Zeile aus Stuecken mit eigener Grundlinie: teile = [(text, versatz_pt)], lueckenlos
        nebeneinander. Rueckgabe: Breite."""
        w = 0.0
        for text, versatz in teile:
            w += self.zeile(seite, x + w, grund + versatz, text, font, groesse)
        return w

    def block(self, seite, x, grund, zeilen, abstand=12, font=None, groesse=None):
        """Zeilen untereinander; Rueckgabe: Docling-Kasten (x0, oben, x1, unten) um den Text."""
        groesse = groesse or self.GROESSE
        w = max(self.zeile(seite, x, grund + i * abstand, t, font, groesse) for i, t in enumerate(zeilen))
        return (x - 2, grund - groesse - 1, x + w + 2, grund + (len(zeilen) - 1) * abstand + 4)

    def speichere(self, pfad, seiten=None):
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(pfad, pagesize=(BREITE, HOEHE))
        for s in range(1, (seiten or max(list(self.seiten) + list(self.linien), default=1)) + 1):
            for x, grund, text, font, groesse in self.seiten.get(s, []):
                c.setFont(font, groesse)
                c.drawString(x, HOEHE - grund, text)
            for x0, y, x1, staerke in self.linien.get(s, []):
                c.setLineWidth(staerke)
                c.line(x0, HOEHE - y, x1, HOEHE - y)
            c.showPage()
        c.save()
        return pfad


def leeres_pdf(pfad, seiten):
    """PDF ohne Textebene (Docling-Weg ohne pdfplumber-Inhalt)."""
    import pypdf
    w = pypdf.PdfWriter()
    for _ in range(seiten):
        w.add_blank_page(width=BREITE, height=HOEHE)
    w.write(pfad)
    return pfad


# ---------- Stand vor Spec 2 ----------
_ALT = {}


def alte_module():
    """(rag, einlesen) aus BASIS_COMMIT, je Prozess einmal geladen. Das alte einlesen bekommt das alte
    rag als "rag"; sys.path und sys.modules bleiben danach wie vorher."""
    if "module" in _ALT:
        return _ALT["module"]
    verz = tempfile.mkdtemp(prefix="eq-basis-")

    def lade(datei, name):
        p = subprocess.run(["git", "-C", BASE, "show", f"{BASIS_COMMIT}:{datei}"], capture_output=True, text=True)
        if p.returncode:
            raise AssertionError(f"{datei} aus {BASIS_COMMIT} nicht lesbar (Clone ohne Historie?): {p.stderr.strip()}")
        pfad = os.path.join(verz, name + ".py")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(p.stdout)
        spec = importlib.util.spec_from_file_location(name, pfad)
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        return modul
    pfad_vorher = list(sys.path)
    alt_rag = lade("rag.py", "rag_vor_eq")
    with mock.patch.dict(sys.modules, {"rag": alt_rag}):
        alt_einlesen = lade("einlesen.py", "einlesen_vor_eq")
    sys.path[:] = pfad_vorher
    alt_einlesen.VORABMESSUNG = VORABMESSUNG_MB        # Spec-1-Messergebnis liegt im Repo, nicht im Temp-Verzeichnis
    alt_rag.DATA_DIR, alt_rag.INDEX_PATH, alt_rag.PDF_DIR = rag.DATA_DIR, rag.INDEX_PATH, rag.PDF_DIR
    _ALT["module"] = (alt_rag, alt_einlesen)
    return _ALT["module"]


def ist_leer(w):
    """Leerwert fuer neue Protokollfelder (REQ-EQ-16): None, 0, "", leere Liste/Objekt, "nicht_gemessen",
    oder ein Objekt/eine Liste nur aus Leerwerten."""
    if w is None or w == "" or w == "nicht_gemessen" or (isinstance(w, (int, float)) and not isinstance(w, bool) and w == 0):
        return True
    if isinstance(w, dict):
        return all(ist_leer(v) for v in w.values())
    if isinstance(w, (list, tuple)):
        return all(ist_leer(v) for v in w)
    return False


# ---------- Testbasis ----------
def buchdekl(bid="nord", titel="Buch Nord", fassung="alpha", quelle=None, liste=(("Kapitel", 1, 1),),
             konjunktionen=KONJUNKTIONEN, layout=None, **spec2):
    """Buchdeklaration: Liste aus dem Inhaltsverzeichnis (gedruckt = physisch), Layout-Rueckfall
    section_header, Reparatur mit Konjunktionsliste; dazu die Spec-2-Schluessel."""
    return mb.buch(bid, titel, fassung, quelle=quelle or f"{bid}.pdf",
                   ueberschriften={"quelle": "inhaltsverzeichnis",
                                   "eintraege": [{"titel": t, "ebene": e, "seite": s} for t, s, e in liste]},
                   seitenzahlen={"quelle": "versatz", "versatz": 0},
                   reparatur={"an": True, "konjunktionen": list(konjunktionen)},
                   layout=layout or {"klasse": "section_header"}, **spec2)


class EQTest(mb.BestandTest):
    BID = "nord"

    def setUp(self):
        super().setUp()
        self.n_pdf = 0

    # ----- Bestand -----
    def deklariere(self, *buecher, **spec2):
        """deklariere(**spec2): ein Buch "nord"; deklariere(buchdekl(...), buchdekl(...)): mehrere."""
        self.bestand(list(buecher) if buecher else [buchdekl(**spec2)])

    def pdf_leer(self, seiten):
        self.n_pdf += 1
        return leeres_pdf(os.path.join(self.tmp.name, f"leer{self.n_pdf}.pdf"), seiten)

    def pdf_aus(self, zeichnung, seiten=None):
        self.n_pdf += 1
        return zeichnung.speichere(os.path.join(self.tmp.name, f"buch{self.n_pdf}.pdf"), seiten)

    # ----- Einlesen -----
    def lies(self, elemente, pdf=None, bid=None, sid=None, modul=None):
        """Docling-Weg (lies_pdf_ein) mit Attrappe; Rueckgabe: Protokoll."""
        pdf = pdf or self.pdf_leer(max(elemente))
        with da.installiere(elemente, versionen()):
            return (modul or einlesen()).lies_pdf_ein(sid or mb.SID, bid or self.BID, pdf=pdf, ueberschreiben=True,
                                                      ausgabe=lambda *_: None)

    def lies_alt(self, elemente, pdf=None, bid=None):
        """Derselbe Docling-Weg mit einlesen.py/rag.py vom Stand vor Spec 2."""
        alt_rag, alt_einlesen = alte_module()
        with mock.patch.multiple(alt_rag, DATA_DIR=self.data, INDEX_PATH=self.index, PDF_DIR=rag.PDF_DIR):
            return self.lies(elemente, pdf, bid, modul=alt_einlesen)

    # ----- Buchdatei -----
    def buchdatei_pfad(self, bid=None, sid=None):
        return self.buchdatei(bid or self.BID, sid or mb.SID)

    def roh(self, bid=None, sid=None):
        with open(self.buchdatei_pfad(bid, sid), "rb") as f:
            return f.read()

    def eintraege(self, bid=None, sid=None):
        with open(self.buchdatei_pfad(bid, sid), encoding="utf-8") as f:
            return [json.loads(z) for z in f]

    def protokoll_datei(self, bid=None, sid=None):
        with open(os.path.join(os.path.dirname(self.buchdatei_pfad(bid, sid)), "einlese_protokoll.json"),
                  encoding="utf-8") as f:
            return json.load(f)

    def gesamttext(self, bid=None):
        return "\n".join(e["text"] for e in self.eintraege(bid))

    def folge(self, *marken, bid=None):
        """Marken nach ihrer Stelle im Buchtext (Eintraege in Dateifolge). Jede Marke genau einmal."""
        text = self.gesamttext(bid)
        for m in marken:
            self.assertEqual(text.count(m), 1, (m, text))
        return sorted(marken, key=text.index)

    def pfad_von(self, marke, bid=None):
        treffer = [e["abschnittspfad"] for e in self.eintraege(bid) if marke in e["text"]]
        self.assertEqual(len(treffer), 1, (marke, treffer))
        return treffer[0]

    def abschnitt_von(self, marke, bid=None):
        treffer = [e for e in self.eintraege(bid) if marke in e["text"]]
        self.assertEqual(len(treffer), 1, (marke, [e["abschnittspfad"] for e in treffer]))
        return treffer[0]

    # ----- Index -----
    def haeppchen(self, size, overlap, bid=None):
        """Index bauen (rag.aktualisiere_index) und die Haeppchen des Buchs in Indexfolge laden."""
        with mock.patch.multiple(rag, CHUNK_SIZE=size, CHUNK_OVERLAP=overlap):
            self.baue()
            chunks, _ = rag.lade_spiel(self.oeffne(), mb.SID)
        return [c for c in chunks if c["buch_id"] == (bid or self.BID)]


@contextlib.contextmanager
def vorgeparst(pdf_pfad):
    """pdfplumber.open(pdf_pfad) liefert ein schon geoeffnetes und geparstes PDF (Zeichen je Seite im
    Cache): misst die Spec-2-Regeln ohne das Oeffnen/Parsen der PDF (REQ-EQ-20). Andere Pfade wie gehabt."""
    import pdfplumber
    echt = pdfplumber.open
    pdf = echt(pdf_pfad)
    for seite in pdf.pages:
        _ = seite.chars

    class Offen:
        def __enter__(self):
            return pdf

        def __exit__(self, *a):
            return False

        def close(self):
            pass

        def __getattr__(self, name):
            return getattr(pdf, name)

    def oeffne(pfad, *a, **k):
        if os.path.abspath(str(pfad)) == os.path.abspath(pdf_pfad):
            return Offen()
        return echt(pfad, *a, **k)
    try:
        with mock.patch.object(pdfplumber, "open", oeffne):
            yield
    finally:
        pdf.close()
