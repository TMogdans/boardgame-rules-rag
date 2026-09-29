#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Eval pro Spiel: `rag.py eval <spiel_id>` und `rag.py eval --alle` -- ohne Ollama.

    python test_eval_spiele.py

Die Wertungslogik (bewerte_frage, fasse_zusammen, formatiere_zusammenfassung)
ist unveraendert und in test_wertung.py abgesichert. Hier geht es um die
Verdrahtung: welches Golden Set gegen welchen Index laeuft und dass ein
Spiel nicht mit den Seiten eines anderen gewertet wird.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import rag  # noqa: E402

ACHSEN = ("geld", "kette", "kanal", "rest")


def fake_embed(texte):
    out = []
    for t in texte:
        t = t.lower()
        v = [float(t.count(a)) for a in ACHSEN[:-1]]
        out.append(v + [0.1 if any(v) else 1.0])
    return np.array(out, dtype=np.float32)


def c(sid, name, i, seite, text, typ="regel"):
    return {"id": i, "seite": seite, "typ": typ, "text": text, "spiel": name, "spiel_id": sid}


A, AN = "food-chain-magnate", "Food Chain Magnate"
B, BN = "brass-birmingham", "Brass: Birmingham"
FCM = [c(A, AN, 1, 11, "Geld verdient man in Phase 4."),
       c(A, AN, 2, 6, "Die Kette wird am Anfang gebaut."),
       c(A, AN, 3, 2, "Werbung auf dem Deckblatt.", "flavor")]
# Brass ist fuer "Geld" der staerkere Treffer -- auf Seite 11, wie die FCM-Erwartung.
BRASS = [c(B, BN, 1, 11, "Geld Geld Geld Geld."),
         c(B, BN, 2, 3, "Der Kanal wird zuerst gebaut.")]

GS_A = {"spiel_id": A, "fragen": [
    {"id": 1, "frage": "Wie verdiene ich Geld?", "typ": "fakt", "erwartet": "Phase 4",
     "keywords": ["Phase 4"], "seiten": [11]},
    {"id": 2, "frage": "Wann wird die Kette gebaut?", "typ": "fakt", "erwartet": "am Anfang",
     "keywords": ["am Anfang"], "seiten": [6]},
    {"id": 3, "frage": "Wie funktioniert der Kanal?", "typ": "leerstelle", "erwartet": "keine Angabe",
     "keywords": ["keine Angabe"], "seiten": [3]},          # Seite 3 gibt es nur in Brass
    {"id": 4, "frage": "Gibt es einen Solo-Modus?", "typ": "leerstelle", "erwartet": "keine Angabe",
     "erwartet_verweigerung": True, "keywords": ["keine Angabe"], "seiten": []}]}
GS_B = {"spiel_id": B, "fragen": [
    {"id": 1, "frage": "Wie funktioniert der Kanal?", "typ": "fakt", "erwartet": "zuerst",
     "keywords": ["zuerst"], "seiten": [3]}]}


class EvalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.antworten = []

        def fake_answer(frage, hits):
            self.antworten.append((frage, [h["text"] for h, _ in hits]))
            return "Das geschieht in Phase 4, am Anfang."
        self.patches = [mock.patch.object(rag, "DATA_DIR", self.data),
                        mock.patch.object(rag, "INDEX_PATH", os.path.join(self.data, "index.sqlite")),
                        mock.patch.object(rag, "embed", fake_embed),
                        mock.patch.object(rag, "answer", fake_answer),
                        # TOP_K nicht patchen: retrieve bindet k=TOP_K beim Import (wie bisher)
                        mock.patch.multiple(rag, CHUNK_SIZE=400, CHUNK_OVERLAP=150, HYBRID=False, RERANK=False),
                        mock.patch.dict(os.environ, {"DROP_TYPES": "flavor"})]
        for p in self.patches:
            p.start()
        for name, chunks, gs in ((AN, FCM, GS_A), (BN, BRASS, GS_B)):
            meta = rag.lege_spiel_an(name)
            rag.schreibe_jsonl(rag.knowledge_pfad(meta["spiel_id"]), chunks)
            if gs:
                self.schreibe_gs(meta["spiel_id"], gs)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def schreibe_gs(self, sid, gs):
        with open(os.path.join(self.data, sid, "golden_set.json"), "w", encoding="utf-8") as f:
            json.dump(gs, f)

    def lauf(self, *args):
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer):
            saetze = rag.cmd_eval_spiele(list(args))
        return saetze, puffer.getvalue()


class TestEvalProSpiel(EvalTest):
    def test_wertung_fuer_ein_spiel(self):
        saetze, text = self.lauf(A)
        self.assertEqual([s["kategorie"] for s in saetze],
                         [rag.KAT_GETROFFEN, rag.KAT_GETROFFEN, rag.KAT_VERFEHLT, rag.KAT_VERWEIGERUNG])
        self.assertIn("getroffen : 2/3", text)
        self.assertIn("Verweigerungsfragen: 1/4", text)
        self.assertIn("Spiel: Food Chain Magnate (food-chain-magnate)  Index: 2 Chunks", text)
        # Nur FCM-Texte beim Modell, obwohl Brass fuer "Geld" staerker waere
        eigene = {x["text"] for x in FCM}
        for _, texte in self.antworten:
            self.assertTrue(set(texte) <= eigene, texte)

    def test_wertung_gleich_der_direkten_rechnung(self):
        # Verdrahtung: dieselben Saetze wie bewerte_frage auf denselben Treffern.
        saetze, _ = self.lauf(A)
        con = rag.oeffne_index()
        self.addCleanup(con.close)
        chunks, embs = rag.lade_spiel(con, A, {"flavor"})
        erwartet = []
        for f in GS_A["fragen"]:
            hits = rag.retrieve(f["frage"], chunks, embs, spiel_id=A, index=con)
            erwartet.append(rag.bewerte_frage(f, [h["seite"] for h, _ in hits],
                                              "Das geschieht in Phase 4, am Anfang."))
        self.assertEqual(saetze, erwartet)

    def test_fremdes_spiel_aendert_die_wertung_nicht(self):
        vorher, _ = self.lauf(A)
        meta = rag.lege_spiel_an("Geld Geld Geld")
        rag.schreibe_jsonl(rag.knowledge_pfad(meta["spiel_id"]),
                           [c(meta["spiel_id"], meta["name"], 1, 6, "Geld Kette Geld Kette")])
        rag.aktualisiere_index(ausgabe=lambda *_: None)
        nachher, _ = self.lauf(A)
        self.assertEqual(nachher, vorher)

    def test_alle_mit_gesamtblock_und_benannten_luecken(self):
        rag.lege_spiel_an("Ohne Golden Set")
        rag.schreibe_jsonl(rag.knowledge_pfad("ohne-golden-set"),
                           [c("ohne-golden-set", "Ohne Golden Set", 1, 1, "Regel.")])
        saetze, text = self.lauf("--alle")
        self.assertIn("Ohne Golden Set, nicht gewertet: ohne-golden-set", text)
        self.assertEqual(len(saetze), len(GS_A["fragen"]) + len(GS_B["fragen"]))
        self.assertIn("Gesamt ueber 2 Spiele", text)
        gesamt = text.split("Gesamt ueber 2 Spiele")[1]
        self.assertIn("getroffen : 3/4", gesamt)       # A 2/3 + B 1/1
        self.assertIn("Fragen im Golden Set: 5", gesamt)

    def test_golden_set_muss_zum_spiel_gehoeren(self):
        self.schreibe_gs(B, dict(GS_B, spiel_id=A))
        with self.assertRaises(rag.KonfigFehler):
            self.lauf(B)
        self.schreibe_gs(B, {"fragen": GS_B["fragen"]})
        with self.assertRaises(rag.KonfigFehler):
            self.lauf(B)

    def test_fehlendes_golden_set(self):
        os.remove(os.path.join(self.data, B, "golden_set.json"))
        with self.assertRaises(rag.KonfigFehler):
            self.lauf(B)

    def test_eval_bringt_den_index_auf_stand(self):
        self.lauf(A)
        rag.schreibe_jsonl(rag.knowledge_pfad(A), FCM + [c(A, AN, 4, 3, "Der Kanal gehoert nicht zu FCM.")])
        saetze, _ = self.lauf(A)
        self.assertEqual(saetze[2]["kategorie"], rag.KAT_GETROFFEN)   # neue Seite 3 ist jetzt da


if __name__ == "__main__":
    unittest.main(verbosity=2)
