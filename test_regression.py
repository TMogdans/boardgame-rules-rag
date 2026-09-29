#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression gegen den Stand VOR dem Umbau (ed36f99), modellfrei.

    python test_regression.py

Referenz ist regression_referenz.json: Top-k, Reranker-Folge und eval-Ausgabe,
erzeugt mit dem rag.py von ed36f99 (`python regression_referenz.py --erzeuge`).
Gegen sie laufen BEIDE heutigen Wege:
  - alter Weg: SOURCE=knowledge, knowledge.jsonl neben rag.py (build_index, In-Memory)
  - neuer Weg: `rag.py migriere` -> data/food-chain-magnate/, Index in SQLite,
    retrieve(spiel_id=...)

Die erste Fassung verglich HEAD gegen HEAD. Eine Aenderung an der gemeinsamen
Rangfolge-Zeile (Mutation K2: Gleichstaende umdrehen) zog dann beide Seiten mit
und alles blieb gruen, obwohl sich die Top-k gegenueber ed36f99 aenderten. Die
Referenz haengt jetzt an keinem Code dieses Branches.

Die Daten sind absichtlich voller Gleichstaende (Duplikat-Chunks, ganzzahlige
Themenachsen): genau dort unterschied sich sqlite-vec, genau dort faellt eine
veraenderte Reihenfolge auf. Verglichen werden Position, Seite, Text-Hash exakt
und der Score auf 1e-6 (BLAS-Rundung kann zwischen Maschinen um ein ulp abweichen).

Was dieser Test NICHT zeigt: ob Ollama batch-unabhaengig einbettet. Das misst
`python rag.py vergleiche <spiel_id>` auf der Zielmaschine mit echten Embeddings.
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
import regression_referenz as ref  # noqa: E402
from regression_referenz import WISSEN, GOLDEN, FRAGEN, RASTER, achsen_embed, hash_embed  # noqa: E402

with open(ref.JSON_PFAD, encoding="utf-8") as _f:
    SOLL = json.load(_f)


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

    def stellschrauben(self, embed_name, size, overlap, drop, rerank=False):
        return [mock.patch.object(rag, "embed", ref.EMBEDS[embed_name]),
                mock.patch.multiple(rag, CHUNK_SIZE=size, CHUNK_OVERLAP=overlap, EMBED_MODEL=embed_name,
                                    RERANK=rerank, CANDIDATES=6, get_reranker=lambda: ref._FakeReranker,
                                    answer=ref.fake_answer),
                mock.patch.dict(os.environ, {"SOURCE": "knowledge", "DROP_TYPES": drop})]

    def mit(self, *args, **kw):
        st = contextlib.ExitStack()
        for p in self.stellschrauben(*args, **kw):
            st.enter_context(p)
        return st

    # Beide heutigen Wege in der Form, die regression_referenz.berechne erwartet.
    # Jede Attrappe unter eigenem Modellnamen: der Fingerprint kennt nur den NAMEN.
    def alter_weg(self, embed_name, size, overlap, drop, rerank):
        with self.mit(embed_name, size, overlap, drop, rerank):
            chunks, embs = rag.build_index()

        def finde(frage, k):
            with self.mit(embed_name, size, overlap, drop, rerank):
                return rag.retrieve(frage, chunks, embs, k=k)
        return chunks, finde

    def neuer_weg(self, embed_name, size, overlap, drop, rerank):
        with self.mit(embed_name, size, overlap, drop, rerank):
            rag.aktualisiere_index(["food-chain-magnate"], ausgabe=lambda *_: None)
            con = rag.oeffne_index()
            self.addCleanup(con.close)
            chunks, embs = rag.lade_spiel(con, "food-chain-magnate", rag.drop_fuer_index())

        def finde(frage, k):
            with self.mit(embed_name, size, overlap, drop, rerank):
                return rag.retrieve(frage, chunks, embs, k=k, spiel_id="food-chain-magnate", index=con)
        return chunks, finde

    def eval_alt(self, embed_name, size, overlap, drop):
        puffer = io.StringIO()
        with self.mit(embed_name, size, overlap, drop), contextlib.redirect_stdout(puffer):
            rag.cmd_eval()
        return puffer.getvalue()

    def eval_neu(self, embed_name, size, overlap, drop):
        puffer = io.StringIO()
        with self.mit(embed_name, size, overlap, drop), contextlib.redirect_stdout(puffer):
            rag.cmd_eval_spiele(["food-chain-magnate"])
        return puffer.getvalue()

    def vergleiche_mit_soll(self, ist, soll, wo):
        self.assertEqual(sorted(ist), sorted(soll), f"{wo}: andere Faelle als in der Referenz")
        abweichend = []
        for key in soll:
            a, b = ist[key], soll[key]
            gleich = len(a) == len(b) and all(x[:3] == y[:3] and abs(x[3] - y[3]) < 1e-6 for x, y in zip(a, b))
            if not gleich:
                abweichend.append(key)
        self.assertEqual(abweichend[:5], [], f"{wo}: {len(abweichend)} von {len(soll)} Faellen weichen von "
                                             f"{ref.REFERENZ_COMMIT} ab, z.B. {abweichend[:1]}: "
                                             f"ist {ist[abweichend[0]] if abweichend else ''} "
                                             f"soll {soll[abweichend[0]] if abweichend else ''}")


class TestGegenEd36f99(RegressionsTest):
    def test_alter_weg_gleich_ed36f99(self):
        ist = ref.berechne(self.alter_weg, self.eval_alt)
        self.vergleiche_mit_soll(ist["topk"], SOLL["topk"], "alter Weg, Top-k")
        self.vergleiche_mit_soll(ist["rerank"], SOLL["rerank"], "alter Weg, Reranker")
        self.assertEqual(ist["eval"], SOLL["eval"])

    def test_neuer_weg_gleich_ed36f99(self):
        self.migriere()
        ist = ref.berechne(self.neuer_weg, self.eval_neu)
        self.vergleiche_mit_soll(ist["topk"], SOLL["topk"], "Index-Weg, Top-k")
        self.vergleiche_mit_soll(ist["rerank"], SOLL["rerank"], "Index-Weg, Reranker")
        self.assertEqual(ist["eval"], SOLL["eval"])

    def test_referenz_ist_vollstaendig(self):
        self.assertEqual(len(SOLL["topk"]), len(ref.EMBEDS) * len(RASTER) * len(ref.KS) * len(FRAGEN))
        self.assertEqual(len(SOLL["rerank"]), len(FRAGEN))
        self.assertTrue(all(any("getroffen :" in z for z in v) for v in SOLL["eval"].values()))
        self.assertIn(ref.REFERENZ_COMMIT, SOLL["_erzeugt_mit"])

    def test_gleichstaende_sind_wirklich_da(self):
        # Gegenprobe zur Konstruktion: ohne Gleichstand an einer k-Grenze bewiese der
        # Vergleich nichts ueber die Reihenfolge bei Gleichstand. Gemessen je
        # Konfiguration 10 bis 35 Faelle (Frage, k) mit Gleichstand genau an der Grenze.
        for size, overlap, drop in RASTER:
            with self.subTest(chunk=(size, overlap), drop=drop), self.mit("fake-achsen", size, overlap, drop):
                _, embs = rag.build_index()
                grenze = 0
                for frage in FRAGEN:
                    sims = embs @ rag.l2norm(achsen_embed([frage]))[0]
                    o = np.argsort(-sims)
                    grenze += sum(1 for k in (1, 4, 8) if k < len(o) and sims[o[k - 1]] == sims[o[k]])
                self.assertGreaterEqual(grenze, 10)

    def test_indexweg_direkt_geladen_wie_vorab_geladen(self):
        # Pipe-/ask-Weg (retrieve laedt selbst) == eval-Weg (vorab geladen)
        self.migriere()
        with self.mit("fake-achsen", 400, 150, "flavor"):
            rag.aktualisiere_index(["food-chain-magnate"], ausgabe=lambda *_: None)
            con = rag.oeffne_index()
            self.addCleanup(con.close)
            chunks, embs = rag.lade_spiel(con, "food-chain-magnate", rag.drop_fuer_index())
            for frage in FRAGEN:
                a = rag.retrieve(frage, chunks, embs, k=4, spiel_id="food-chain-magnate", index=con)
                b = rag.retrieve(frage, k=4, spiel_id="food-chain-magnate", index=con)
                self.assertEqual([(h["chunk_id"], s) for h, s in a], [(h["chunk_id"], s) for h, s in b])


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
        with self.mit("fake-hash", 400, 150, "flavor"):
            chunks, _ = rag.build_index()
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
