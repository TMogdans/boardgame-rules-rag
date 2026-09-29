#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Suche pro Spiel: retrieve(query, spiel_id=...) und die Hybrid-Option (HYBRID=1).

    python test_suche.py

Ohne Ollama: Embeddings kommen aus festen Themenachsen. Das fremde Spiel ist so
gebaut, dass es fuer jede Testfrage die BESSEREN Treffer haette -- ein Filter,
der erst nach dem Ranking greift oder gar nicht, faellt dadurch auf.
"""
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

ACHSEN = ("geld", "kette", "werbung", "rest")


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
FCM = [c(A, AN, 1, 2, "Werbung Werbung Geld! Das beste Spiel.", "flavor"),
       c(A, AN, 2, 11, "Geld verdient man in Phase 4."),
       c(A, AN, 3, 12, "Geld aus der Bank, Geld zahlt die Kette."),
       c(A, AN, 4, 13, "Mit Geld kauft man Geld-Marker."),
       c(A, AN, 5, 6, "Die Kette wird am Anfang gebaut."),
       c(A, AN, 6, 14, "Die Waitress bringt 3 Dollar.")]
# Das fremde Spiel ist fuer "Geld" und "Waitress" jeweils der staerkere Treffer.
BRASS = [c(B, BN, 1, 99, "Geld Geld Geld Geld Geld."),
         c(B, BN, 2, 98, "Waitress Waitress Waitress Geld."),
         c(B, BN, 3, 97, "Waitress rule, Waitress again."),
         c(B, BN, 4, 96, "Waitress Waitress.")]


class SucheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = os.path.join(self.tmp.name, "data")
        self.patches = [mock.patch.object(rag, "DATA_DIR", data),
                        mock.patch.object(rag, "INDEX_PATH", os.path.join(data, "index.sqlite")),
                        mock.patch.object(rag, "embed", fake_embed),
                        mock.patch.multiple(rag, CHUNK_SIZE=400, CHUNK_OVERLAP=150, HYBRID=False, RERANK=False,
                                            CANDIDATES=20)]
        for p in self.patches:
            p.start()
        for name, chunks in ((AN, FCM), (BN, BRASS)):
            meta = rag.lege_spiel_an(name)
            rag.schreibe_jsonl(rag.knowledge_pfad(meta["spiel_id"]), chunks)
        rag.aktualisiere_index(ausgabe=lambda *_: None)
        self.con = rag.oeffne_index()

    def tearDown(self):
        self.con.close()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def suche(self, frage, spiel_id, k=3, **env):
        with mock.patch.dict(os.environ, env):
            return rag.retrieve(frage, k=k, spiel_id=spiel_id, index=self.con)

    @staticmethod
    def texte(hits):
        return [h["text"] for h, _ in hits]


class TestSpielfilter(SucheTest):
    def test_nur_chunks_des_spiels(self):
        eigene = {x["text"] for x in FCM}
        for frage in ("Geld", "Waitress", "Kette", "Wie verdiene ich Geld?"):
            with self.subTest(frage=frage):
                hits = self.suche(frage, A, k=10)
                self.assertTrue(set(self.texte(hits)) <= eigene, self.texte(hits))
                self.assertNotIn(99, [h["seite"] for h, _ in hits])

    def test_filter_vor_dem_ranking_liefert_volle_k(self):
        # Das fremde Spiel haette die besten Treffer. Wuerde erst danach gefiltert,
        # blieben von k=3 weniger als drei uebrig.
        hits = self.suche("Geld", A, k=3)
        self.assertEqual(len(hits), 3)
        # (1,0,0,.1) liegt genau auf der Frage, (2,0,0,.1) knapp daneben, (2,1,0,.1) weiter weg
        self.assertEqual([h["seite"] for h, _ in hits], [11, 13, 12])

    def test_ergebnis_wie_ohne_das_fremde_spiel(self):
        # Die Suche in A darf von B nichts wissen: gleiches Ergebnis wie der
        # In-Memory-Weg ueber A allein (gleiche Scores, gleiche Reihenfolge).
        roh = [x for x in FCM]
        chunks = rag.baue_knowledge_chunks(roh, set())
        embs = rag.l2norm(fake_embed([x["text"] for x in chunks]))
        for frage in ("Geld", "Kette", "Waitress"):
            with self.subTest(frage=frage):
                alt = rag.retrieve(frage, chunks, embs, k=4)
                neu = self.suche(frage, A, k=4)
                self.assertEqual([(h["seite"], h["text"], s) for h, s in alt],
                                 [(h["seite"], h["text"], s) for h, s in neu])

    def test_drop_types_wirkt_auf_dem_index_weg(self):
        mit = self.suche("Werbung", A, k=10)
        self.assertIn(2, [h["seite"] for h, _ in mit])
        ohne = self.suche("Werbung", A, k=10, DROP_TYPES="flavor")
        self.assertNotIn(2, [h["seite"] for h, _ in ohne])
        with self.assertRaises(rag.KonfigFehler):
            self.suche("Werbung", A, DROP_TYPES="falle")

    def test_fremde_vorab_geladene_chunks_werden_abgelehnt(self):
        chunks, embs = rag.lade_spiel(self.con, B)
        with self.assertRaises(rag.KonfigFehler):
            rag.retrieve("Geld", chunks, embs, spiel_id=A, index=self.con)

    def test_unbekanntes_oder_boeses_spiel(self):
        with self.assertRaises(rag.KonfigFehler):
            self.suche("Geld", "gibts-nicht")
        with self.assertRaises(rag.KonfigFehler):
            self.suche("Geld", "../brass-birmingham")


class TestHybrid(SucheTest):
    def test_default_ist_reine_vektorsuche(self):
        # HYBRID ist aus, solange niemand es einschaltet. Gemessen in einem frischen
        # Prozess -- setUp patcht HYBRID, ein Blick auf rag.HYBRID hier wuesste nichts.
        import subprocess
        env = {k: v for k, v in os.environ.items() if k != "HYBRID"}
        for wert, erwartet in ((None, "False"), ("0", "False"), ("1", "True")):
            if wert is not None:
                env["HYBRID"] = wert
            p = subprocess.run([sys.executable, "-c", "import rag; print(rag.HYBRID)"],
                               cwd=BASE, env=env, capture_output=True, text=True)
            self.assertEqual(p.stdout.strip(), erwartet, (wert, p.stderr))
        vektor = self.suche("Wie viel Geld bringt eine Waitress?", A, k=3)
        self.assertEqual([h["seite"] for h, _ in vektor], [11, 13, 12])

    def test_bm25_holt_das_stichwort_nach_vorn(self):
        frage = "Wie viel Geld bringt eine Waitress?"
        vektor = self.suche(frage, A, k=3)
        self.assertNotIn(14, [h["seite"] for h, _ in vektor])   # Vektor kennt "Waitress" nicht
        with mock.patch.object(rag, "HYBRID", True):
            hybrid = self.suche(frage, A, k=3)
        # Vektor [11,13,12,2,14,6], BM25 [14,13,12,2,11], RRF_K=60:
        # 13: 2/62=.03226, 11 und 14: 1/61+1/65=.03178 (Gleichstand -> Vektorfolge), 12: 2/63=.03175
        self.assertEqual([h["seite"] for h, _ in hybrid], [13, 11, 14])
        self.assertAlmostEqual(hybrid[0][1], 2 / 62)
        self.assertTrue(set(self.texte(hybrid)) <= {x["text"] for x in FCM})

    def test_bm25_nur_im_spiel_auch_wenn_fremde_mehr_treffer_haben(self):
        # B hat drei Waitress-Chunks mit mehr Treffern als A. Bei CANDIDATES=2 und
        # einem Filter erst NACH dem LIMIT kaeme A's Waitress-Chunk nie in BM25.
        chunks, _ = rag.lade_spiel(self.con, A)
        with mock.patch.object(rag, "CANDIDATES", 2):
            folge = rag.bm25_rangfolge(self.con, "Waitress", chunks, 2)
        self.assertEqual([chunks[i]["seite"] for i in folge], [14])

    def test_bm25_holt_fuer_ausgelassene_typen_nach(self):
        # Zwei flavor-Chunks desselben Spiels tragen "Waitress" oefter als der
        # Regel-Chunk (Seite 14). Mit DROP_TYPES=flavor und n=1 muss trotzdem
        # Seite 14 kommen -- ein LIMIT ohne Nachholen lieferte nichts.
        C = "crew"
        meta = rag.lege_spiel_an("Crew")
        rag.schreibe_jsonl(rag.knowledge_pfad(C), [
            c(C, "Crew", 1, 1, "Waitress Waitress Waitress! Werbespruch.", "flavor"),
            c(C, "Crew", 2, 3, "Waitress Waitress, noch ein Werbespruch.", "flavor"),
            c(C, "Crew", 3, 14, "Die Waitress bringt 3 Dollar."),
            c(C, "Crew", 4, 5, "Die Kette wird gebaut.")])
        self.assertEqual(meta["spiel_id"], C)
        rag.aktualisiere_index([C], ausgabe=lambda *_: None)
        chunks, _ = rag.lade_spiel(self.con, C, {"flavor"})
        self.assertEqual([chunks[i]["seite"] for i in rag.bm25_rangfolge(self.con, "Waitress", chunks, 1)], [14])
        alle, _ = rag.lade_spiel(self.con, C)
        self.assertEqual([alle[i]["seite"] for i in rag.bm25_rangfolge(self.con, "Waitress", alle, 3)], [1, 3, 14])

    def test_bm25_ohne_filter_wuerde_fremde_liefern(self):
        # Gegenprobe zur Konstruktion: ungefiltert gewinnen die Brass-Chunks.
        roh = self.con.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? "
                               "ORDER BY bm25(chunks_fts) LIMIT 2", ('"waitress"',)).fetchall()
        spiele = {self.con.execute("SELECT spiel_id FROM chunks WHERE id=?", r).fetchone()[0] for r in roh}
        self.assertEqual(spiele, {B})

    def test_scharfes_s_findet_etwas(self):
        C = "strasse"
        meta = rag.lege_spiel_an("Strasse")
        rag.schreibe_jsonl(rag.knowledge_pfad(C), [
            c(C, "Strasse", 1, 2, "Die Straße ist lang und groß."),
            c(C, "Strasse", 2, 3, "Das Maß aller Dinge."),
            c(C, "Strasse", 3, 4, "Nichts davon.")])
        self.assertEqual(meta["spiel_id"], C)
        rag.aktualisiere_index([C], ausgabe=lambda *_: None)
        chunks, _ = rag.lade_spiel(self.con, C)
        for frage, seite in (("Straße", 2), ("Wie groß?", 2), ("Maß", 3)):
            with self.subTest(frage=frage):
                self.assertEqual([chunks[i]["seite"] for i in rag.bm25_rangfolge(self.con, frage, chunks, 5)], [seite])

    def test_bm25_gleichstand_in_chunk_folge(self):
        # Identische Texte -> gleicher BM25-Wert; Reihenfolge = Folge im Heft (rowid aufsteigend)
        C = "doppelt"
        meta = rag.lege_spiel_an("Doppelt")
        rag.schreibe_jsonl(rag.knowledge_pfad(C), [
            c(C, "Doppelt", 1, 7, "Die Waitress bringt Geld."),
            c(C, "Doppelt", 2, 8, "Die Waitress bringt Geld."),
            c(C, "Doppelt", 3, 9, "Die Waitress bringt Geld.")])
        self.assertEqual(meta["spiel_id"], C)
        rag.aktualisiere_index([C], ausgabe=lambda *_: None)
        chunks, _ = rag.lade_spiel(self.con, C)
        self.assertEqual([chunks[i]["seite"] for i in rag.bm25_rangfolge(self.con, "Waitress", chunks, 2)], [7, 8])

    def test_nutzertext_ist_keine_abfragesprache(self):
        chunks, _ = rag.lade_spiel(self.con, A)
        for frage in ('Was kostet "Waitress"?', "(Geld) AND OR NOT *", "NEAR(a b)", "", "???", 'a"b'):
            with self.subTest(frage=frage):
                rag.bm25_rangfolge(self.con, frage, chunks, 5)   # darf nicht werfen
        self.assertEqual(rag.fts_abfrage("Geld? Geld!"), '"geld"')

    def test_hybrid_braucht_den_index(self):
        chunks = rag.baue_knowledge_chunks(FCM, set())
        embs = rag.l2norm(fake_embed([x["text"] for x in chunks]))
        with mock.patch.object(rag, "HYBRID", True), self.assertRaises(rag.KonfigFehler):
            rag.retrieve("Geld", chunks, embs)

    def test_rrf_rechnet_wie_beschrieben(self):
        erg = rag.rrf([[0, 1, 2], [2, 0]], k=60)
        self.assertEqual([i for i, _ in erg], [0, 2, 1])
        self.assertAlmostEqual(erg[0][1], 1 / 61 + 1 / 62)
        self.assertAlmostEqual(erg[1][1], 1 / 63 + 1 / 61)
        self.assertAlmostEqual(erg[2][1], 1 / 62)
        # Gleichstand: Reihenfolge der Vektor-Rangfolge
        self.assertEqual([i for i, _ in rag.rrf([[5, 7], [7, 5]])], [5, 7])
        self.assertEqual([i for i, _ in rag.rrf([[7, 5], [5, 7]])], [7, 5])


class TestGleichstandsregel(SucheTest):
    """Definierte Regel: bei exakt gleichem Score die niedrigere Chunk-Position zuerst.

    30 identische Chunks (Seiten 101..130): mehr als 16, weil numpy fuer bis zu 16
    Elemente ohnehin stabil sortiert -- ein kleinerer Test saehe eine instabile
    Sortierung nicht (gemessen: ab n=17 weicht der Default in 200/200 Faellen ab).
    """
    N = 30

    def setUp(self):
        super().setUp()
        self.G = "gleich"
        meta = rag.lege_spiel_an("Gleich")
        self.roh = [c(self.G, "Gleich", i, 100 + i, "Geld Geld.") for i in range(1, self.N + 1)]
        rag.schreibe_jsonl(rag.knowledge_pfad(self.G), self.roh)
        self.assertEqual(meta["spiel_id"], self.G)
        rag.aktualisiere_index([self.G], ausgabe=lambda *_: None)

    def seiten(self, hits):
        return [h["seite"] for h, _ in hits]

    def test_rangfolge(self):
        sims = np.array([0.5] * 20 + [0.9] + [0.5] * 20 + [0.9], dtype=np.float32)
        self.assertEqual(list(rag.rangfolge(sims)[:5]), [20, 41, 0, 1, 2])

    def test_alter_und_index_weg(self):
        chunks = rag.baue_knowledge_chunks(self.roh, set())
        embs = rag.l2norm(fake_embed([x["text"] for x in chunks]))
        for k in (1, 5, 17, self.N):
            with self.subTest(k=k):
                soll = list(range(101, 101 + k))
                self.assertEqual(self.seiten(rag.retrieve("Geld", chunks, embs, k=k)), soll)
                self.assertEqual(self.seiten(rag.retrieve("Geld", k=k, spiel_id=self.G, index=self.con)), soll)

    def test_reranker_kandidaten(self):
        class Konstant:                      # alle Kandidaten gleich gut -> Kandidatenfolge zaehlt
            @staticmethod
            def predict(paare):
                return np.zeros(len(paare))
        with mock.patch.multiple(rag, RERANK=True, CANDIDATES=20, get_reranker=lambda: Konstant):
            self.assertEqual(self.seiten(rag.retrieve("Geld", k=5, spiel_id=self.G, index=self.con)),
                             [101, 102, 103, 104, 105])

    def test_hybrid_vektorliste(self):
        with mock.patch.multiple(rag, HYBRID=True, CANDIDATES=20):
            self.assertEqual(self.seiten(rag.retrieve("Geld", k=5, spiel_id=self.G, index=self.con)),
                             [101, 102, 103, 104, 105])


if __name__ == "__main__":
    unittest.main(verbosity=2)
