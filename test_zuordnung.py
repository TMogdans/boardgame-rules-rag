#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spielzuordnung (rag.ordne_spiel) und ihre Nutzung auf der Kommandozeile.

    python test_zuordnung.py

Grundsatz: lieber "kein Regelheft" als die Regeln des falschen Spiels. Mit vielen
Spielen im Index wird jeder kurze Name sonst zum Auffangbecken -- Befund aus dem
Review: "Fujian" traf "Fuji" (difflib 2*4/10 = 0,8, genau die Schwelle).
"""
import contextlib
import io
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

FCM = {"spiel_id": "food-chain-magnate", "name": "Food Chain Magnate", "aliase": ["Food Chain", "FCM"]}
FUJI = {"spiel_id": "fuji", "name": "Fuji", "aliase": []}


class TestStrengeZuordnung(unittest.TestCase):
    K = rag.katalog_aus_index([FCM, FUJI])[0]

    def test_kurzer_name_ist_kein_auffangbecken(self):
        # SOLLTE-3: auch kein Vorschlag Fuji (Laenge 0,667 < VORSCHLAG_LAENGE 0,7)
        self.assertEqual(rag.ordne_spiel("Fujian", self.K), ("unbekannt", []))

    def test_laengengrenze(self):
        # 0,8 ist die Grenze: "Carcassonne Big" hat Ratio 0,88, aber Laenge 11/14 = 0,786
        k = rag.katalog_aus_index([{"spiel_id": "carcassonne", "name": "Carcassonne", "aliase": []}, FUJI])[0]
        self.assertEqual(rag.ordne_spiel("Carcassonne Big", k)[0], "unbekannt")
        self.assertEqual(rag.ordne_spiel("Fujix", k), ("treffer", "Fuji"))            # 4/5 = 0,8: noch drin
        self.assertEqual(rag.ordne_spiel("Fujixy", k)[0], "unbekannt")               # 4/6 = 0,67

    def test_ein_spiel_verhaelt_sich_wie_ed36f99(self):
        # Entscheidung: Laengenregel nur bei mehr als einem Spiel
        k1 = rag.katalog_aus("Food Chain Magnate", "Food Chain, FCM")
        for q in ("Food Chain Magnate Regeln", "Food Chain Magnate Spiel", "Food chain magnate bitte",
                  "Food Chain Magnate Ketchup"):
            with self.subTest(q=q):
                self.assertEqual(rag.ordne_spiel(q, k1), ("treffer", "Food Chain Magnate"))
                self.assertEqual(rag.ordne_spiel(q, self.K)[0], "unbekannt")         # mit zwei Spielen streng
        self.assertEqual(rag.ordne_spiel("Fujian", rag.katalog_aus("Fuji", "")), ("treffer", "Fuji"))
        self.assertEqual(rag.ordne_spiel("Fudschein Magnat", k1), ("unbekannt", ["Food Chain Magnate"]))

    def test_ein_spiel_grenzbaender(self):
        # Kritiker-Mutanten C3 (Vorschlaege ab 0,6 statt 0,5) und C5 (Schwelle 0,85): die
        # Baender [0,5; 0,6) und [0,8; 0,85) muessen bei einem Spiel belegt sein.
        k1 = rag.katalog_aus("Food Chain Magnate", "Food Chain, FCM")
        for q in ("Magnate Food", "Chain Food", "Food Truck"):          # 0,519 / 0,556 / 0,556
            with self.subTest(q=q):
                self.assertEqual(rag.ordne_spiel(q, k1), ("unbekannt", ["Food Chain Magnate"]))
        for q in ("Food Magnate", "Fut Chain Magnate", "Food Chain Magnate Magnate"):   # 0,815 / 0,839 / 0,821
            with self.subTest(q=q):
                self.assertEqual(rag.ordne_spiel(q, k1), ("treffer", "Food Chain Magnate"))
        self.assertEqual(rag.ordne_spiel("Magnaten Kette", k1), ("unbekannt", []))   # 0,483

    def test_vorschlaege_bei_mehreren_spielen(self):
        tm = {"spiel_id": "terraforming-mars", "name": "Terraforming Mars", "aliase": []}
        k = rag.katalog_aus_index([FCM, FUJI, tm])[0]
        self.assertEqual(rag.ordne_spiel("Foodsharing Magnet", k), ("unbekannt", ["Food Chain Magnate"]))
        self.assertEqual(rag.ordne_spiel("Terraforming", k), ("unbekannt", ["Terraforming Mars"]))

    def test_hoerfehler_treffen_weiter(self):
        for q in ("Food Chain Magnet", "Foodchain Magnet", "food-chain magnate", "FCM", "Fudji"):
            with self.subTest(q=q):
                self.assertEqual(rag.ordne_spiel(q, self.K)[0], "treffer")
        self.assertEqual(rag.ordne_spiel("Food Chain Magnet", self.K), ("treffer", "Food Chain Magnate"))
        self.assertEqual(rag.ordne_spiel("Foodchain Magnet", self.K), ("treffer", "Food Chain Magnate"))

    def test_fremdes_bleibt_unbekannt_mit_vorschlag(self):
        self.assertEqual(rag.ordne_spiel("Foodsharing Magnet", self.K), ("unbekannt", ["Food Chain Magnate"]))

    def test_deutlich_besserer_treffer_gewinnt(self):
        # "Carcasonne": 0,952 gegen Carcassonne, 0,857 gegen Carcassonna -- beide
        # ueber der Schwelle, Abstand 0,095 > MEHRDEUTIG_ABSTAND -> eindeutig.
        k = rag.katalog_aus_index([{"spiel_id": "carcassonne", "name": "Carcassonne", "aliase": []},
                                   {"spiel_id": "carcassonna", "name": "Carcassonna", "aliase": []}])[0]
        self.assertEqual(rag.ordne_spiel("Carcasonne", k), ("treffer", "Carcassonne"))

    def test_spiel_id_zaehlt_als_schreibweise(self):
        # Name und id normalisieren verschieden -> nur ueber die id erreichbar
        crew = {"spiel_id": "the-crew", "name": "Die Crew", "aliase": []}
        k = rag.katalog_aus_index([crew, FCM])[0]
        self.assertEqual(rag.ordne_spiel("the crew", k), ("treffer", "Die Crew"))
        self.assertEqual(rag.ordne_spiel("the-crew", k), ("treffer", "Die Crew"))


class TestKommandozeile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(rag, "DATA_DIR", os.path.join(self.tmp.name, "data"))
        self.p.start()
        for meta in (FCM, FUJI, {"spiel_id": "the-crew", "name": "Die Crew", "aliase": []}):
            rag.lege_spiel_an(meta["name"], meta["spiel_id"], aliase=meta["aliase"])

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_loese_spiel_nimmt_id_name_alias_hoerfehler(self):
        for angabe, sid in (("food-chain-magnate", "food-chain-magnate"), ("Food Chain Magnate", "food-chain-magnate"),
                            ("FCM", "food-chain-magnate"), ("Food Chain Magnet", "food-chain-magnate"),
                            ("fuji", "fuji"), ("Die Crew", "the-crew"), ("the crew", "the-crew")):
            with self.subTest(angabe=angabe):
                self.assertEqual(rag.loese_spiel(angabe), sid)

    def test_loese_spiel_unbekannt(self):
        with self.assertRaises(rag.KonfigFehler) as ctx:
            rag.loese_spiel("Fujian")
        self.assertNotIn("Meintest du", str(ctx.exception))
        with self.assertRaises(rag.KonfigFehler) as ctx:
            rag.loese_spiel("Foodsharing Magnet")
        self.assertIn("Meintest du Food Chain Magnate?", str(ctx.exception))

    def test_ask_argumente(self):
        for args, soll in ((["--spiel", "FCM", "Wie", "geht", "das?"], ("FCM", "Wie geht das?")),
                           (["--spiel=Food Chain Magnate", "Wie?"], ("Food Chain Magnate", "Wie?")),
                           (["Wie", "--spiel=fuji", "geht", "das?"], ("fuji", "Wie geht das?")),
                           (["Nur", "Frage"], (None, "Nur Frage"))):
            with self.subTest(args=args):
                self.assertEqual(rag.ask_argumente(args), soll)
        with self.assertRaises(rag.KonfigFehler):
            rag.ask_argumente(["--spiel"])
        with self.assertRaises(rag.KonfigFehler):
            rag.ask_argumente(["--spiel=fuji"])

    def test_ask_und_eval_verstehen_namen(self):
        gesehen = []
        with mock.patch.object(rag, "aktualisiere_index", lambda ids, **kw: gesehen.append(("index", ids))), \
             mock.patch.object(rag, "oeffne_index", lambda *a, **k: mock.MagicMock()), \
             mock.patch.object(rag, "retrieve", lambda q, **kw: gesehen.append(("suche", kw["spiel_id"])) or []), \
             mock.patch.object(rag, "answer", lambda q, hits: "A"), \
             contextlib.redirect_stdout(io.StringIO()):
            rag.cmd_ask("Wie?", "Food Chain Magnet")
        self.assertEqual(gesehen, [("index", ["food-chain-magnate"]), ("suche", "food-chain-magnate")])
        mit = []
        with mock.patch.object(rag, "cmd_eval_spiel", lambda sid, d=None: mit.append(sid) or []), \
             contextlib.redirect_stdout(io.StringIO()):
            rag.cmd_eval_spiele(["Die Crew", "fuji"])
        self.assertEqual(mit, ["the-crew", "fuji"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
