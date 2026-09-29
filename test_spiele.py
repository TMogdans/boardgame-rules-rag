#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests fuer "Spiel als Dimension": Datenlayout data/<spiel_id>/ und die
Ingestion-Skripte im Mehr-Spiele-Betrieb.

    python test_spiele.py

Laeuft ohne PDF, ohne Ollama, ohne docling/pymupdf (Attrappen). Geprueft wird
die WIRKUNG: welche Dateien geschrieben werden, was darin steht und was beim
Modell ankommt -- nicht der Quelltext.

Kern: test_zweites_spiel_laesst_das_erste_unberuehrt -- frueher hat
auto_ingest.py die eine knowledge.jsonl mit jedem neuen Heft ueberschrieben.
"""
import contextlib
import io as _io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

# docling und pymupdf gehoeren in die Ingest-venv; hier Attrappen.
for _name in ("docling", "docling.document_converter", "pymupdf"):
    if _name not in sys.modules:
        try:  # pragma: no cover
            __import__(_name)
        except ImportError:
            _m = types.ModuleType(_name)
            if _name == "docling.document_converter":
                _m.DocumentConverter = object
                sys.modules["docling"].document_converter = _m
            sys.modules[_name] = _m

import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag            # noqa: E402
import auto_ingest    # noqa: E402
import ingest         # noqa: E402
import vision_ingest  # noqa: E402
import classify       # noqa: E402


class Prov:
    def __init__(self, p):
        self.page_no = p


class Text:
    def __init__(self, text, p):
        self.text, self.prov = text, [Prov(p)]


class Doc:
    def __init__(self, items):
        self._items = items

    def iterate_items(self):
        return [(i, 0) for i in self._items]


def konverter(doc):
    return lambda: types.SimpleNamespace(convert=lambda pfad: types.SimpleNamespace(document=doc))


def lies(pfad):
    with open(pfad, encoding="utf-8") as f:
        return [json.loads(z) for z in f if z.strip()]


class DataDirTest(unittest.TestCase):
    """Jeder Test bekommt ein eigenes data/ -- rag.DATA_DIR wird umgebogen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.p = mock.patch.object(rag, "DATA_DIR", self.data)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()


# ---------------------------------------------------------------------------
# spiel_id, spiel.json
# ---------------------------------------------------------------------------
class TestSpielId(unittest.TestCase):
    def test_slug(self):
        for name, slug in (("Food Chain Magnate", "food-chain-magnate"),
                           ("Brass: Birmingham", "brass-birmingham"),
                           ("Die Siedler von Catan", "die-siedler-von-catan"),
                           ("Kämpfer & Größe", "kaempfer-groesse"),
                           ("  7 Wonders  ", "7-wonders")):
            self.assertEqual(rag.spiel_slug(name), slug, name)

    def test_slug_transliteriert(self):
        for name, slug in (("Café Łódź", "cafe-lodz"), ("Château Roquefort", "chateau-roquefort"),
                           ("Ørsted & Æbleskiver", "orsted-aebleskiver"), ("Große Straße", "grosse-strasse"),
                           ("Ｆｕｌｌｗｉｄｔｈ ﬁ", "fullwidth-fi"), ("Dvořák", "dvorak"), ("Ölsardinen", "oelsardinen")):
            self.assertEqual(rag.spiel_slug(name), slug, name)
        with self.assertRaises(rag.KonfigFehler):
            rag.spiel_slug("囲碁")

    def test_slug_aus_nichts_ist_fehler(self):
        for name in ("", "  ", "!!!", None):
            with self.assertRaises(rag.KonfigFehler):
                rag.spiel_slug(name)

    def test_spiel_id_kommt_nicht_aus_dem_verzeichnis_heraus(self):
        # Die spiel_id wandert aus Aufrufen von aussen in einen Pfad.
        for boese in ("../etc", "a/b", "A", "fcm/", "", "-fcm", "fcm--x", "fcm ", None, 3):
            with self.assertRaises(rag.KonfigFehler, msg=repr(boese)):
                rag.spiel_verzeichnis(boese, "/tmp/x")


class TestSpielJson(DataDirTest):
    def test_anlegen_und_ergaenzen(self):
        meta = rag.lege_spiel_an("Food Chain Magnate", sprache="de", aliase=["Food Chain", "FCM"],
                                 quelle_pdf="/x/pdfs/FCM_Rules_DE_v3.pdf")
        self.assertEqual(meta["spiel_id"], "food-chain-magnate")
        gespeichert = rag.lies_spiel("food-chain-magnate")
        self.assertEqual(gespeichert, {"spiel_id": "food-chain-magnate", "name": "Food Chain Magnate",
                                       "aliase": ["Food Chain", "FCM"], "sprache": "de",
                                       "quelle_pdf": "FCM_Rules_DE_v3.pdf"})
        # zweiter Lauf ohne Aliase/Sprache: Gepflegtes bleibt stehen
        rag.lege_spiel_an("Food Chain Magnate", quelle_pdf="neu.pdf")
        gespeichert = rag.lies_spiel("food-chain-magnate")
        self.assertEqual(gespeichert["aliase"], ["Food Chain", "FCM"])
        self.assertEqual(gespeichert["quelle_pdf"], "neu.pdf")

    def test_kollision_verschiedener_namen_wird_gemeldet(self):
        rag.lege_spiel_an("Brass: Birmingham")
        rag.lege_spiel_an("Brass Birmingham")          # dasselbe Spiel, andere Schreibweise -> ok
        rag.lege_spiel_an("Café")
        with self.assertRaises(rag.KonfigFehler) as ctx:
            rag.lege_spiel_an("Cafe")                    # anderer Name, gleiche id "cafe"
        self.assertIn("gehoert schon zu 'Café'", str(ctx.exception))
        self.assertEqual(rag.lies_spiel("cafe")["name"], "Café")
        # eigene id loest es
        self.assertEqual(rag.lege_spiel_an("Cafe", "cafe-2")["spiel_id"], "cafe-2")

    def test_unbekannte_sprache_ist_fehler(self):
        with self.assertRaises(rag.KonfigFehler):
            rag.lege_spiel_an("X", sprache="klingonisch")

    def test_liste_spiele_nur_mit_spiel_json(self):
        rag.lege_spiel_an("Brass: Birmingham", sprache="en")
        rag.lege_spiel_an("Food Chain Magnate")
        os.makedirs(os.path.join(self.data, "leer"))              # ohne spiel.json
        os.makedirs(os.path.join(self.data, "Grossbuchstaben"))    # kein gueltiger Slug
        self.assertEqual(rag.liste_spiele(), ["brass-birmingham", "food-chain-magnate"])

    def test_fremder_chunk_im_spielverzeichnis_ist_fehler(self):
        rag.lege_spiel_an("Food Chain Magnate")
        rag.schreibe_jsonl(rag.knowledge_pfad("food-chain-magnate"), [
            {"id": 1, "seite": 1, "text": "a", "spiel": "Food Chain Magnate", "spiel_id": "food-chain-magnate"},
            {"id": 2, "seite": 1, "text": "b", "spiel": "Brass", "spiel_id": "brass-birmingham"}])
        with self.assertRaises(rag.KonfigFehler) as ctx:
            rag.lies_spiel_chunks("food-chain-magnate")
        self.assertIn("fremder spiel_id", str(ctx.exception))

    def test_argumente(self):
        rest, opt = rag.spiel_argumente(["a.pdf", "--spiel", "Brass: Birmingham", "--sprache=en",
                                         "--aliase", "Brass, BB", "7"])
        self.assertEqual(rest, ["a.pdf", "7"])
        self.assertEqual(opt, {"name": "Brass: Birmingham", "sprache": "en", "aliase": ["Brass", " BB"]})
        self.assertEqual(rag.spiel_argumente(["a.pdf"]), (["a.pdf"], None))
        with self.assertRaises(rag.KonfigFehler):
            rag.spiel_argumente(["a.pdf", "--spiel"])


# ---------------------------------------------------------------------------
# auto_ingest.py
# ---------------------------------------------------------------------------
class TestAutoIngest(DataDirTest):
    def lauf(self, argv, doc):
        gesendet = []

        def verb(text, sprache="de"):
            gesendet.append(("verb", sprache))
            return "verbalisiert"

        def vis(pdf, p, prompt=None):
            gesendet.append(("vision", prompt))
            return "Karte A: Kosten 3\nKarte B: Kosten 4"
        with mock.patch.object(auto_ingest, "DocumentConverter", konverter(doc)), \
             mock.patch.object(auto_ingest, "verbalize", verb), \
             mock.patch.object(auto_ingest, "vision", vis), \
             mock.patch.object(auto_ingest, "KNOW", os.path.join(self.tmp.name, "knowledge.jsonl")), \
             contextlib.redirect_stdout(_io.StringIO()):
            auto_ingest.main(argv)
        return gesendet

    def test_schreibt_ins_spielverzeichnis_mit_spielfeldern(self):
        self.lauf(["fcm.pdf", "--spiel", "Food Chain Magnate", "--aliase", "FCM"],
                  Doc([Text("Regel eins.", 1), Text("Regel zwei.", 2)]))
        chunks = lies(os.path.join(self.data, "food-chain-magnate", "knowledge.jsonl"))
        self.assertEqual([c["seite"] for c in chunks], [1, 2])
        for c in chunks:
            self.assertEqual((c["spiel"], c["spiel_id"]), ("Food Chain Magnate", "food-chain-magnate"))
        self.assertEqual(rag.lies_spiel("food-chain-magnate")["quelle_pdf"], "fcm.pdf")
        # und rag.py nimmt es als Chunks dieses Spiels an
        self.assertEqual(len(rag.lies_spiel_chunks("food-chain-magnate")), 2)

    def test_zweites_spiel_laesst_das_erste_unberuehrt(self):
        self.lauf(["fcm.pdf", "--spiel", "Food Chain Magnate"], Doc([Text("FCM-Regel.", 1)]))
        fcm = os.path.join(self.data, "food-chain-magnate", "knowledge.jsonl")
        with open(fcm, "rb") as f:
            vorher = f.read()
        self.lauf(["brass.pdf", "--spiel", "Brass: Birmingham", "--sprache", "en"],
                  Doc([Text("Brass rule.", 1), Text("Canal era.", 2)]))
        with open(fcm, "rb") as f:
            self.assertEqual(f.read(), vorher)
        brass = lies(os.path.join(self.data, "brass-birmingham", "knowledge.jsonl"))
        self.assertEqual([c["spiel_id"] for c in brass], ["brass-birmingham"] * 2)

    def test_mit_spiel_ueberschreibt_nur_auf_ausdruecklichen_wunsch(self):
        self.lauf(["fcm.pdf", "--spiel", "Food Chain Magnate"], Doc([Text("Alt.", 1)]))
        fcm = os.path.join(self.data, "food-chain-magnate", "knowledge.jsonl")
        with open(fcm, "rb") as f:
            vorher = f.read()
        with self.assertRaises(rag.KonfigFehler) as ctx:
            self.lauf(["fcm.pdf", "--spiel-id", "food-chain-magnate"], Doc([Text("Neu.", 1)]))
        self.assertIn("--ueberschreiben", str(ctx.exception))
        with open(fcm, "rb") as f:
            self.assertEqual(f.read(), vorher)
        self.lauf(["fcm.pdf", "--spiel-id", "food-chain-magnate", "--ueberschreiben"], Doc([Text("Neu.", 1)]))
        self.assertEqual([c["text"] for c in lies(fcm)], ["Neu."])

    def test_ohne_spiel_ueberschreibt_keine_vorhandene_datei(self):
        alt = os.path.join(self.tmp.name, "knowledge.jsonl")
        with open(alt, "w") as f:
            f.write('{"id": 1, "seite": 1, "text": "FCM"}\n')
        with self.assertRaises(rag.KonfigFehler):
            self.lauf(["brass.pdf"], Doc([Text("Brass rule.", 1)]))
        self.assertEqual(lies(alt), [{"id": 1, "seite": 1, "text": "FCM"}])

    def test_ohne_spiel_und_ohne_datei_wie_frueher(self):
        self.lauf(["x.pdf"], Doc([Text("Regel.", 3)]))
        chunks = lies(os.path.join(self.tmp.name, "knowledge.jsonl"))
        self.assertEqual([(c["seite"], c["text"]) for c in chunks], [(3, "Regel.")])

    def test_prompts_tragen_spiel_und_sprache(self):
        class Tabelle:
            prov = [Prov(1)]

            def export_to_markdown(self):
                return "| a | b |"
        viele = [Text(f"f{i}", 2) for i in range(auto_ingest.FRAGMENT_THRESHOLD + 1)]
        Tabelle.__name__ = "TableItem"
        gesendet = self.lauf(["brass.pdf", "--spiel", "Brass: Birmingham", "--sprache", "en"],
                             Doc([Tabelle()] + viele))
        self.assertIn(("verb", "en"), gesendet)
        vision = [p for art, p in gesendet if art == "vision"]
        self.assertEqual(len(vision), 1)
        self.assertIn("„Brass: Birmingham“", vision[0])
        self.assertIn("Antworte auf Englisch", vision[0])
        self.assertNotIn("Mitarbeiterkarten", vision[0])

    def test_leeres_heft_bricht_ab(self):
        with self.assertRaises(rag.KonfigFehler):
            self.lauf(["scan.pdf", "--spiel", "Scan"], Doc([]))
        self.assertFalse(os.path.exists(os.path.join(self.data, "scan", "knowledge.jsonl")))


class TestVerbPromptSprache(unittest.TestCase):
    def test_auto_ingest_und_ingest_sprechen_die_heftsprache(self):
        self.assertIn("deutsche Saetze", auto_ingest.verb_prompt("de"))
        self.assertIn("englische Saetze", auto_ingest.verb_prompt("en"))
        self.assertIn("englische Saetze", ingest.verb_prompt("en"))
        self.assertIn("deutsche Saetze", ingest.verb_prompt("de"))


# ---------------------------------------------------------------------------
# ingest.py
# ---------------------------------------------------------------------------
class TestIngest(DataDirTest):
    def lauf(self, argv, doc):
        gesendet = []

        def fake_post(url, json=None, timeout=None):
            gesendet.append(json["messages"][0]["content"])
            return types.SimpleNamespace(raise_for_status=lambda: None,
                                         json=lambda: {"message": {"content": "v"}})
        alt = sys.argv
        try:
            sys.argv = ["ingest.py"] + argv
            with mock.patch.object(ingest, "DocumentConverter", konverter(doc)), \
                 mock.patch.object(ingest.requests, "post", fake_post), \
                 mock.patch.object(ingest, "OUT", os.path.join(self.tmp.name, "knowledge.jsonl")), \
                 mock.patch.object(ingest, "SPRACHE", "de"), \
                 contextlib.redirect_stdout(_io.StringIO()):
                ingest.main()
        finally:
            sys.argv = alt
        return gesendet

    def test_spiel_verzeichnis_und_felder(self):
        gesendet = self.lauf(["brass.pdf", "--spiel", "Brass: Birmingham", "--sprache", "en"],
                             Doc([Text("Canal era.", 4)]))
        chunks = lies(os.path.join(self.data, "brass-birmingham", "knowledge.jsonl"))
        self.assertEqual([(c["seite"], c["spiel_id"], c["spiel"]) for c in chunks],
                         [(4, "brass-birmingham", "Brass: Birmingham")])
        self.assertIn("englische Saetze", gesendet[0])
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "knowledge.jsonl")))

    def test_mit_spiel_ueberschreibt_nicht_ungefragt(self):
        self.lauf(["brass.pdf", "--spiel", "Brass: Birmingham"], Doc([Text("Alt.", 4)]))
        with self.assertRaises(rag.KonfigFehler):
            self.lauf(["brass.pdf", "--spiel", "Brass: Birmingham"], Doc([Text("Neu.", 4)]))
        self.lauf(["brass.pdf", "--spiel", "Brass: Birmingham", "--ueberschreiben"], Doc([Text("Neu.", 4)]))
        self.assertEqual(len(lies(os.path.join(self.data, "brass-birmingham", "knowledge.jsonl"))), 1)

    def test_ohne_spiel_ueberschreibt_nicht(self):
        alt = os.path.join(self.tmp.name, "knowledge.jsonl")
        with open(alt, "w") as f:
            f.write("{}\n")
        with self.assertRaises(rag.KonfigFehler):
            self.lauf(["x.pdf"], Doc([Text("t", 1)]))
        with open(alt) as f:
            self.assertEqual(f.read(), "{}\n")


# ---------------------------------------------------------------------------
# vision_ingest.py
# ---------------------------------------------------------------------------
class TestVisionIngest(DataDirTest):
    def lauf(self, argv, antwort="Karte A: Kosten 3\nKarte B: Kosten 4"):
        prompts = []

        def fake_post(url, json=None, timeout=None):
            prompts.append(json["prompt"])
            return types.SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"response": antwort})
        bild = os.path.join(self.tmp.name, os.path.basename(argv[0]))
        with open(bild, "wb") as f:
            f.write(b"png")
        with mock.patch.object(vision_ingest.requests, "post", fake_post), \
             mock.patch.object(vision_ingest, "KNOW", os.path.join(self.tmp.name, "knowledge.jsonl")), \
             mock.patch.object(vision_ingest, "PROMPT", vision_ingest.PROMPT), \
             mock.patch.dict(os.environ, {}, clear=False), \
             contextlib.redirect_stdout(_io.StringIO()):
            os.environ.pop("SEITE", None)
            vision_ingest.main([bild] + argv[1:])
        return prompts

    def test_schreibt_nur_ins_eigene_spiel(self):
        rag.lege_spiel_an("Brass: Birmingham", sprache="en")
        rag.lege_spiel_an("Food Chain Magnate")
        fcm = rag.knowledge_pfad("food-chain-magnate")
        rag.schreibe_jsonl(fcm, [{"id": 1, "seite": 2, "text": "FCM", "spiel": "Food Chain Magnate",
                                  "spiel_id": "food-chain-magnate"}])
        with open(fcm, "rb") as f:
            vorher = f.read()
        prompts = self.lauf(["seite_6.png", "--spiel-id", "brass-birmingham"])
        with open(fcm, "rb") as f:
            self.assertEqual(f.read(), vorher)
        brass = lies(rag.knowledge_pfad("brass-birmingham"))
        self.assertEqual([(c["seite"], c["spiel_id"]) for c in brass], [(6, "brass-birmingham")] * 2)
        self.assertIn("„Brass: Birmingham“", prompts[0])
        self.assertIn("Englisch", prompts[0])
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "knowledge.jsonl")))

    def test_zweite_grafikseite_loescht_die_erste_nicht(self):
        rag.lege_spiel_an("Brass: Birmingham", sprache="en")
        self.lauf(["seite_6.png", "--spiel-id", "brass-birmingham"])
        self.lauf(["seite_7.png", "--spiel-id", "brass-birmingham"])
        self.assertEqual([c["seite"] for c in lies(rag.knowledge_pfad("brass-birmingham"))], [6, 6, 7, 7])
        # dieselbe Seite erneut: nur deren Chunks werden ersetzt
        self.lauf(["seite_6.png", "--spiel-id", "brass-birmingham"], antwort="Karte C: Kosten 9")
        chunks = lies(rag.knowledge_pfad("brass-birmingham"))
        self.assertEqual(sorted(c["seite"] for c in chunks), [6, 7, 7])
        self.assertIn("Karte C: Kosten 9", [c["text"] for c in chunks])

    def test_spiel_id_ohne_angelegtes_spiel_ist_fehler(self):
        with self.assertRaises(rag.KonfigFehler):
            self.lauf(["seite_6.png", "--spiel-id", "gibts-nicht"])


# ---------------------------------------------------------------------------
# classify.py
# ---------------------------------------------------------------------------
class TestClassify(DataDirTest):
    def test_taggt_nur_das_genannte_spiel(self):
        for name in ("Food Chain Magnate", "Brass: Birmingham"):
            meta = rag.lege_spiel_an(name)
            rag.schreibe_jsonl(rag.knowledge_pfad(meta["spiel_id"]),
                               [{"id": 1, "seite": 1, "text": "t", **rag.spiel_felder(meta)}])
        fcm = rag.knowledge_pfad("food-chain-magnate")
        with open(fcm, "rb") as f:
            vorher = f.read()
        fake = types.SimpleNamespace(post=lambda *a, **k: types.SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: {"message": {"content": "flavor"}}))
        with mock.patch.object(classify, "requests", fake), contextlib.redirect_stdout(_io.StringIO()):
            classify.main(["brass-birmingham"])
        with open(fcm, "rb") as f:
            self.assertEqual(f.read(), vorher)
        brass = lies(rag.knowledge_pfad("brass-birmingham"))
        self.assertEqual([(c["typ"], c["spiel_id"]) for c in brass], [("flavor", "brass-birmingham")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
