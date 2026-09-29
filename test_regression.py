#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression alter Weg -> neuer Weg, modellfrei.

    python test_regression.py

Alter Weg: SOURCE=knowledge mit einer knowledge.jsonl neben rag.py (build_index,
In-Memory). Neuer Weg: `rag.py migriere` nach data/food-chain-magnate/, Index in
SQLite, retrieve(spiel_id=...). Mit gleichen Chunks und gleichen (gefakten,
deterministischen) Embeddings muessen beide dieselben Top-k liefern -- gleiche
Chunks, gleiche Reihenfolge, gleiche Scores.

Die Daten sind absichtlich voller Gleichstaende (Duplikat-Chunks, ganzzahlige
Themenachsen): genau dort unterschied sich sqlite-vec (umgekehrte rowid-Folge),
und genau dort faellt eine veraenderte Speicherreihenfolge auf.

Was dieser Test NICHT zeigt: ob Ollama batch-unabhaengig einbettet. Das misst
`python rag.py vergleiche <spiel_id>` auf der Zielmaschine mit echten Embeddings.
"""
import contextlib
import hashlib
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

with open(os.path.join(BASE, "golden_set.example.json"), encoding="utf-8") as _f:
    GOLDEN = json.load(_f)

# FCM-aehnliche Wissensbasis: Seiten wie im Golden Set, Duplikate, lange Texte
# (werden zerteilt), flavor/meta-Typen und ein Eintrag ohne typ. Die Vision-Chunks
# von Seite 6 stehen am ENDE, wie vision_ingest.py sie anhaengt -- die Datei ist
# also nicht nach Seiten sortiert, und ein Umsortieren faellt auf.
WISSEN = [
    {"id": 1, "seite": 1, "typ": "meta", "route": "text-roh", "text": "Food Chain Magnate Regelheft Inhaltsverzeichnis"},
    {"id": 2, "seite": 2, "typ": "flavor", "route": "text-roh",
     "text": "Gleicher Mist, doppelter Preis! Werbung fuer die beste Kette der Stadt."},
    {"id": 3, "seite": 5, "typ": "regel", "route": "table",
     "text": "Bei 2 Spielern werden die Reklametafeln 12, 15 und 16 entfernt. Bei 4 Spielern ist der Spielplan 4x4 gross. " * 6},
    {"id": 4, "seite": 10, "typ": "regel", "route": "text-roh", "text": "Die Reichweite zaehlt Strassenfelder. " * 12},
    {"id": 5, "seite": 11, "typ": "regel", "route": "text-roh",
     "text": "In Phase 4, der Essenszeit, wird Geld verdient. Eine Ware kostet 10 Dollar. Der CFO bringt 50 % Bonus. " * 5},
    {"id": 6, "seite": 11, "route": "text-roh", "text": "Eine Waitress bringt 3 Dollar Geld."},       # ohne typ
    {"id": 7, "seite": 14, "typ": "regel", "route": "table", "text": "Meilenstein First waitress played: 5 Dollar Geld."},
    {"id": 8, "seite": 14, "typ": "regel", "route": "table", "text": "Meilenstein First waitress played: 5 Dollar Geld."},
    {"id": 9, "seite": 15, "typ": "meta", "route": "text-roh", "text": "Impressum und Credits"},
    {"id": 10, "seite": 6, "typ": "regel", "quelle": "vision:seite_6.png", "text": "Truck Driver: Reichweite 3"},
    {"id": 11, "seite": 6, "typ": "regel", "quelle": "vision:seite_6.png", "text": "Campaign Manager: Kampagne maximale Dauer 3"},
    {"id": 12, "seite": 6, "typ": "regel", "quelle": "vision:seite_6.png", "text": "Truck Driver: Reichweite 3"},  # Duplikat
]

ACHSEN = ("geld", "reichweite", "kampagne", "dauer", "phase", "spieler", "waitress", "reklametafel", "dollar")


def achsen_embed(texte):
    """Ganzzahlige Themenachsen -> sehr viele exakte Gleichstaende."""
    out = []
    for t in texte:
        t = t.lower()
        v = [float(t.count(a)) for a in ACHSEN]
        out.append(v + [0.1 if any(v) else 1.0])
    return np.array(out, dtype=np.float32)


def hash_embed(texte):
    """Pseudozufaellig, gleiche Texte -> gleiche Vektoren (Gleichstand nur bei Duplikaten)."""
    return np.array([[b / 255.0 - 0.5 for b in hashlib.sha256(t.encode()).digest()[:16]] for t in texte],
                    dtype=np.float32)


def fake_rerank_predict(paare):
    """Deterministischer 'Cross-Encoder': gemeinsame Woerter, dann Laenge."""
    out = []
    for frage, text in paare:
        gemeinsam = len(set(frage.lower().split()) & set(text.lower().split()))
        out.append(gemeinsam + 1.0 / (1 + len(text)))
    return np.array(out)


class RegressionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.basis = os.path.join(self.tmp.name, "clone")          # "neben rag.py"
        os.mkdir(self.basis)
        self.data = os.path.join(self.basis, "data")
        rag.schreibe_jsonl(os.path.join(self.basis, "knowledge.jsonl"), WISSEN)
        with open(os.path.join(self.basis, "golden_set.json"), "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in GOLDEN.items() if k != "spiel_id"}, f)
        self.patches = [mock.patch.object(rag, "__file__", os.path.join(self.basis, "rag.py")),
                        mock.patch.object(rag, "DATA_DIR", self.data),
                        mock.patch.object(rag, "INDEX_PATH", os.path.join(self.data, "index.sqlite")),
                        mock.patch.multiple(rag, HYBRID=False, RERANK=False, EMBED_BATCH=5)]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def migriere(self):
        with contextlib.redirect_stdout(io.StringIO()):
            rag.cmd_migriere(["--spiel", "Food Chain Magnate", "--aliase", "Food Chain,FCM"])

    def alter_weg(self, drop_types):
        with mock.patch.dict(os.environ, {"SOURCE": "knowledge", "DROP_TYPES": drop_types}):
            return rag.build_index()

    def neuer_weg(self, drop_types):
        rag.aktualisiere_index(["food-chain-magnate"], ausgabe=lambda *_: None)
        con = rag.oeffne_index()
        self.addCleanup(con.close)
        with mock.patch.dict(os.environ, {"DROP_TYPES": drop_types}):
            chunks, embs = rag.lade_spiel(con, "food-chain-magnate", rag.drop_fuer_index())
        return chunks, embs, con

    @staticmethod
    def signatur(hits):
        return [(h["seite"], h["text"], s) for h, s in hits]


FRAGEN = [f["frage"] for f in GOLDEN["fragen"]] + ["Geld", "Reichweite", "Waitress Dollar", "xyz"]
RASTER = [(size, overlap, drop) for size, overlap in ((800, 150), (400, 150), (60, 10))
          for drop in ("", "flavor", "flavor,meta")]


class TestGleicheTopK(RegressionsTest):
    def test_gleiche_top_k_ueber_alle_stellschrauben(self):
        self.migriere()
        verglichen = 0
        # Jede Attrappe unter eigenem Modellnamen: der Fingerprint kennt nur den
        # NAMEN. Zwei Funktionen unter einem Namen waeren fuer den Index dasselbe
        # Modell (im Betrieb: `ollama pull` mit neuen Gewichten unter altem Tag).
        for embed_name, embed in (("fake-achsen", achsen_embed), ("fake-hash", hash_embed)):
            for size, overlap, drop in RASTER:
                with mock.patch.object(rag, "embed", embed), \
                     mock.patch.multiple(rag, CHUNK_SIZE=size, CHUNK_OVERLAP=overlap, EMBED_MODEL=embed_name):
                    alt_c, alt_e = self.alter_weg(drop)
                    neu_c, neu_e, con = self.neuer_weg(drop)
                    np.testing.assert_array_equal(alt_e, neu_e)
                    for k in (1, 4, 8, len(alt_c)):
                        for frage in FRAGEN:
                            with self.subTest(embed=embed_name, chunk=(size, overlap), drop=drop, k=k, frage=frage):
                                alt = rag.retrieve(frage, alt_c, alt_e, k=k)
                                neu = rag.retrieve(frage, neu_c, neu_e, k=k, spiel_id="food-chain-magnate", index=con)
                                self.assertEqual(self.signatur(alt), self.signatur(neu))
                                # und direkt aus dem Index geladen (Pipe-/ask-Weg)
                                with mock.patch.dict(os.environ, {"DROP_TYPES": drop}):
                                    direkt = rag.retrieve(frage, k=k, spiel_id="food-chain-magnate", index=con)
                                self.assertEqual(self.signatur(alt), self.signatur(direkt))
                                verglichen += 1
        self.assertEqual(verglichen, 2 * len(RASTER) * 4 * len(FRAGEN))

    def test_gleichstaende_sind_wirklich_da(self):
        # Gegenprobe zur Konstruktion: ohne Gleichstand an einer k-Grenze bewiese der
        # Test oben nichts ueber die Reihenfolge bei Gleichstand. Gemessen je
        # Konfiguration 10 bis 35 Faelle (Frage, k) mit Gleichstand genau an der Grenze.
        for size, overlap, drop in RASTER:
            with self.subTest(chunk=(size, overlap), drop=drop), mock.patch.object(rag, "embed", achsen_embed), \
                 mock.patch.multiple(rag, CHUNK_SIZE=size, CHUNK_OVERLAP=overlap):
                _, embs = self.alter_weg(drop)
                grenze = 0
                for frage in FRAGEN:
                    sims = embs @ rag.l2norm(achsen_embed([frage]))[0]
                    o = np.argsort(-sims)
                    grenze += sum(1 for k in (1, 4, 8) if k < len(o) and sims[o[k - 1]] == sims[o[k]])
                self.assertGreaterEqual(grenze, 10)

    def test_mit_reranker_ebenso(self):
        self.migriere()

        class FakeRR:
            predict = staticmethod(fake_rerank_predict)
        with mock.patch.object(rag, "embed", achsen_embed), mock.patch.object(rag, "get_reranker", lambda: FakeRR), \
             mock.patch.multiple(rag, CHUNK_SIZE=400, CHUNK_OVERLAP=150, RERANK=True, CANDIDATES=6):
            alt_c, alt_e = self.alter_weg("flavor,meta")
            neu_c, neu_e, con = self.neuer_weg("flavor,meta")
            for f in GOLDEN["fragen"]:
                with self.subTest(frage=f["id"]):
                    self.assertEqual(self.signatur(rag.retrieve(f["frage"], alt_c, alt_e, k=4)),
                                     self.signatur(rag.retrieve(f["frage"], neu_c, neu_e, k=4,
                                                                spiel_id="food-chain-magnate", index=con)))


class TestEvalGleich(RegressionsTest):
    def test_eval_alter_und_neuer_weg_gleich(self):
        """`SOURCE=knowledge DROP_TYPES=flavor rag.py eval` gegen `rag.py eval food-chain-magnate`."""
        self.migriere()

        def answer(frage, hits):
            return "Antwort: " + " | ".join(h["text"][:40] for h, _ in hits)

        def ausgabe(lauf):
            puffer = io.StringIO()
            with mock.patch.object(rag, "embed", achsen_embed), mock.patch.object(rag, "answer", answer), \
                 mock.patch.multiple(rag, CHUNK_SIZE=400, CHUNK_OVERLAP=150), \
                 mock.patch.dict(os.environ, {"SOURCE": "knowledge", "DROP_TYPES": "flavor"}), \
                 contextlib.redirect_stdout(puffer):
                lauf()
            # Kopfzeilen (Config/Index/Spiel) unterscheiden sich gewollt, der Rest nicht
            return [z for z in puffer.getvalue().splitlines()
                    if not z.startswith(("Config:", "Index:", "Spiel:", "===="))]
        alt = ausgabe(lambda: rag.cmd_eval())
        neu = ausgabe(lambda: rag.cmd_eval_spiele(["food-chain-magnate"]))
        self.assertEqual([z for z in alt if z.strip()], [z for z in neu if z.strip()])
        self.assertTrue(any("getroffen :" in z for z in alt))


class TestMigration(RegressionsTest):
    def test_inhalt_und_reihenfolge_bleiben(self):
        self.migriere()
        neu = rag.lies_jsonl(os.path.join(self.data, "food-chain-magnate", "knowledge.jsonl"))
        self.assertEqual(len(neu), len(WISSEN))
        for alt_e, neu_e in zip(WISSEN, neu):
            self.assertEqual({k: v for k, v in neu_e.items() if k not in ("spiel", "spiel_id")}, alt_e)
            self.assertEqual((neu_e["spiel"], neu_e["spiel_id"]), ("Food Chain Magnate", "food-chain-magnate"))
        meta = rag.lies_spiel("food-chain-magnate")
        self.assertEqual(meta["aliase"], ["Food Chain", "FCM"])
        gs = rag.lade_golden_set("food-chain-magnate")
        self.assertEqual(gs["fragen"], GOLDEN["fragen"])

    def test_alte_datei_bleibt_und_alter_weg_geht_weiter(self):
        with open(os.path.join(self.basis, "knowledge.jsonl"), "rb") as f:
            vorher = f.read()
        self.migriere()
        with open(os.path.join(self.basis, "knowledge.jsonl"), "rb") as f:
            self.assertEqual(f.read(), vorher)
        with mock.patch.object(rag, "embed", hash_embed), mock.patch.multiple(rag, CHUNK_SIZE=400, CHUNK_OVERLAP=150):
            chunks, _ = self.alter_weg("flavor")
        self.assertTrue(chunks)

    def test_zweimal_migrieren_ist_harmlos_abweichung_wird_nicht_ueberschrieben(self):
        self.migriere()
        self.migriere()          # identisch -> ok
        ziel = os.path.join(self.data, "food-chain-magnate", "knowledge.jsonl")
        with open(ziel, "a", encoding="utf-8") as f:
            f.write(json.dumps({"id": 99, "seite": 3, "text": "neu", "spiel": "Food Chain Magnate",
                                "spiel_id": "food-chain-magnate"}) + "\n")
        with self.assertRaises(rag.KonfigFehler):
            self.migriere()
        self.assertEqual(len(rag.lies_jsonl(ziel)), len(WISSEN) + 1)

    def test_datei_ohne_seite_wird_nicht_migriert(self):
        rag.schreibe_jsonl(os.path.join(self.basis, "knowledge.jsonl"), [{"id": 1, "text": "x"}])
        with self.assertRaises(rag.KonfigFehler):
            self.migriere()
        self.assertFalse(os.path.exists(os.path.join(self.data, "food-chain-magnate", "knowledge.jsonl")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
