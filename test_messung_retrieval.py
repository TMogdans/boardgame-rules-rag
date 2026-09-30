#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
messung/retrieval.py -- Trefferquote je Spiel und Verzeichnis-Anteil, mit Fake-Embedding, ohne Ollama.

    python test_messung_retrieval.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402
import test_eval_spiele as tes  # noqa: E402  -- nur seine Testdaten (Fake-Embedding, Chunks, Golden Sets)
from messung import retrieval as r  # noqa: E402


class RetrievalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = os.path.join(self.tmp.name, "data")
        patches = [mock.patch.object(rag, "DATA_DIR", self.data),
                   mock.patch.object(rag, "INDEX_PATH", os.path.join(self.data, "index.sqlite")),
                   mock.patch.object(rag, "embed", tes.fake_embed),
                   mock.patch.multiple(rag, CHUNK_SIZE=400, CHUNK_OVERLAP=150, HYBRID=False, RERANK=False),
                   mock.patch.dict(os.environ, {"DROP_TYPES": "flavor"})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        inhalt = dict(tes.c(tes.A, tes.AN, 4, 9, "Inhalt\nGeld ..... 3\nKette ..... 5"), route="vision")
        for name, chunks, gs in ((tes.AN, tes.FCM + [inhalt], tes.GS_A), (tes.BN, tes.BRASS, tes.GS_B)):
            meta = rag.lege_spiel_an(name)
            rag.schreibe_jsonl(rag.knowledge_pfad(meta["spiel_id"]), chunks)
            with open(os.path.join(self.data, meta["spiel_id"], "golden_set.json"), "w", encoding="utf-8") as f:
                json.dump(gs, f)

    def test_trefferquote_je_spiel_ohne_verweigerungsfragen(self):
        zeilen = []
        with contextlib.redirect_stdout(io.StringIO()):
            erg = r.trefferquote(ausgabe=zeilen.append)
        # FCM: Geld (11) und Kette (6) getroffen, Kanal (Seite 3) gibt es nur bei Brass; Frage 4 ist eine
        # Verweigerungsfrage und zaehlt nicht. Brass: Kanal (3) getroffen.
        self.assertEqual(erg["je_spiel"], {tes.A: (2, 3), tes.B: (1, 1)})
        self.assertEqual(erg["gesamt"], (3, 4))
        self.assertEqual(erg["verfehlt"], [f"{tes.A}/3"])
        self.assertIn("GESAMT 3/4", zeilen[-1])

    def test_verzeichnis_anteil_und_keine_regelheft_texte_in_der_ausgabe(self):
        aus = os.path.join(self.tmp.name, "vz.jsonl")
        with contextlib.redirect_stdout(io.StringIO()):
            summe = r.verzeichnis_anteil(aus, ausgabe=lambda *_: None)
        # FCM: 4 Fragen x 3 Chunks (flavor ist im Index gedroppt); der Inhalt-Chunk (Vision, 2 von 3 Zeilen
        # enden auf eine Zahl) ist bei jeder Frage dabei.
        self.assertEqual(summe[tes.A], {"treffer": 12, "vision": 4, "verzeichnis": 4})
        self.assertEqual(summe[tes.B]["vision"], 0)
        with open(aus, encoding="utf-8") as f:
            zeilen = [json.loads(z) for z in f]
        self.assertEqual(len(zeilen), 14)
        self.assertNotIn("text", zeilen[0])
        self.assertNotIn("anfang", zeilen[0])
        # hoehere Schwelle: 0.67 < 0.9 -> kein Verzeichnis-Treffer mehr
        with contextlib.redirect_stdout(io.StringIO()):
            summe = r.verzeichnis_anteil(aus, schwelle=0.9, ausgabe=lambda *_: None)
        self.assertEqual(summe[tes.A]["verzeichnis"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
