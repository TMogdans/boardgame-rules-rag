# -*- coding: utf-8 -*-
"""
Attrappe des Docling-Pakets fuer Tests des Docling-Wegs (REQ-MB-11, -23, -27, -32) -- ohne echtes
Docling, nach dessen API:

  DocumentConverter().convert(pdf, page_range=(von, bis)).document -> Dokument
  Dokument.iterate_items(traverse_pictures=False) -> (item, ebene); Text-Kinder eines Bild-Elements
      nur mit traverse_pictures=True, direkt hinter ihm, eine Ebene tiefer
  Dokument.pages[n].size.height / .width
  item.label (Enum wie DocItemLabel, .value = "text", "section_header", "table", "picture", ...)
  item.text; item.prov[0].page_no, item.prov[0].bbox (l, t, r, b, coord_origin; Docling liefert
      PDF-Koordinaten mit Ursprung UNTEN links, to_top_left_origin(page_height) rechnet um)
  Tabellen: item.export_to_markdown(doc=...) liefert die Tabelle roh als Markdown

Gebrauch:
    with installiere(elemente, versionen={"docling": "2.131.0", "pdfplumber": "0.11.10"}):
        einlesen.lies_pdf_ein(...)
elemente: {seite: [Element, ...]} in Extraktionsfolge.
"""
import contextlib
import enum
import importlib.metadata
import sys
import types
from unittest import mock

HOEHE, BREITE = 800.0, 600.0


class Label(str, enum.Enum):
    TEXT = "text"
    SECTION_HEADER = "section_header"
    TABLE = "table"
    PICTURE = "picture"
    CAPTION = "caption"
    PAGE_HEADER = "page_header"
    PAGE_FOOTER = "page_footer"


class CoordOrigin(str, enum.Enum):
    TOPLEFT = "TOPLEFT"
    BOTTOMLEFT = "BOTTOMLEFT"


class BoundingBox:
    def __init__(self, l, t, r, b, coord_origin=CoordOrigin.BOTTOMLEFT):
        self.l, self.t, self.r, self.b, self.coord_origin = l, t, r, b, coord_origin

    def to_top_left_origin(self, page_height):
        if self.coord_origin == CoordOrigin.TOPLEFT:
            return self
        return BoundingBox(self.l, page_height - self.t, self.r, page_height - self.b, CoordOrigin.TOPLEFT)


class Prov:
    def __init__(self, page_no, bbox=None):
        self.page_no, self.bbox = page_no, bbox


class Element:
    """Ein Docling-Item. lage = (x0, oben, x1, unten) in Punkten ab OBEN links (wie pdfplumber);
    gespeichert wird es wie bei Docling mit Ursprung unten links."""

    def __init__(self, label, text="", lage=None, kinder=(), markdown=None, weitere_kaesten=()):
        self.label = Label(label)
        self._weitere = list(weitere_kaesten)          # weitere Kaesten (prov) auf derselben Seite
        self.text = text
        self.kinder = list(kinder)
        self._markdown = markdown
        self._lage = lage
        self.prov = []

    def _setze_seite(self, seite):
        def bbox(lage):
            x0, oben, x1, unten = lage
            return BoundingBox(x0, HOEHE - oben, x1, HOEHE - unten, CoordOrigin.BOTTOMLEFT)
        self.prov = [Prov(seite, bbox(self._lage) if self._lage is not None else None)]
        self.prov += [Prov(seite, bbox(lage)) for lage in self._weitere]
        for k in self.kinder:
            k._setze_seite(seite)

    def export_to_markdown(self, doc=None):
        if self._markdown is None:
            raise AttributeError("kein Tabellen-Element")
        return self._markdown


class Dokument:
    def __init__(self, elemente):
        self.elemente = elemente           # [(seite, Element)]
        seiten = sorted({s for s, _ in elemente})
        self.pages = {s: types.SimpleNamespace(size=types.SimpleNamespace(height=HOEHE, width=BREITE))
                      for s in seiten}

    def iterate_items(self, traverse_pictures=False, **_):
        for _, e in self.elemente:
            yield e, 1
            if traverse_pictures:
                for k in e.kinder:
                    yield k, 2


def _module(elemente, aufrufe):
    def konverter_klasse():
        class DocumentConverter:
            def __init__(self, *a, **k):
                pass

            def convert(self, source, page_range=None, **k):
                aufrufe.append((str(source), page_range))
                von, bis = page_range if page_range else (1, 10 ** 9)
                liste = [(s, e) for s in sorted(elemente) if von <= s <= bis for e in elemente[s]]
                return types.SimpleNamespace(document=Dokument(liste))
        return DocumentConverter
    for s, liste in elemente.items():
        for e in liste:
            e._setze_seite(s)
    docling = types.ModuleType("docling")
    dc = types.ModuleType("docling.document_converter")
    dc.DocumentConverter = konverter_klasse()
    docling.document_converter = dc
    return {"docling": docling, "docling.document_converter": dc}


@contextlib.contextmanager
def installiere(elemente, versionen=None):
    """docling-Attrappe in sys.modules, importlib.metadata.version liefert die Versionen.
    Rueckgabe: Liste der convert-Aufrufe (Quelle, page_range)."""
    aufrufe = []
    versionen = dict(versionen or {})
    echte_version = importlib.metadata.version

    def version(name):
        return versionen[name] if name in versionen else echte_version(name)
    with mock.patch.dict(sys.modules, _module(elemente, aufrufe)), \
            mock.patch("importlib.metadata.version", version):
        yield aufrufe
