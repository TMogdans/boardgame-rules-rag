#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
messung/lauf.py -- hookt rag.answer, schreibt antworten.jsonl + meta.json. Ohne Ollama.

    python test_messung_lauf.py

Zwei Ebenen: eine Fake-Eval (die nur rag.cmd_eval_spiel/werte_fragen/answer ruft) prueft die
Haken und das Protokoll; ein Durchlauf ueber das echte rag.cmd_eval_spiele mit Fake-Embedding
und Fake-Antwort prueft, dass die Haken in der echten Verdrahtung greifen.
"""
import contextlib
import io
import itertools
import json
import os
import subprocess
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
from messung import lauf as m  # noqa: E402

FRAGEN = [
    {"id": 1, "frage": "Wie verdiene ich Geld?", "typ": "fakt", "erwartet": "Phase 4", "keywords": ["Phase 4"],
     "seiten": [11]},
    {"id": 2, "frage": "Gibt es Solo?", "typ": "leerstelle", "erwartet": "keine Angabe",
     "erwartet_verweigerung": True, "keywords": [], "seiten": []}]


def lies(pfad):
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def schreibe(pfad, text):
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(text)


def still(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **k)


class FakeEvalTest(unittest.TestCase):
    """Fake-Eval: zwei Spiele, feste Treffer, feste Antworten -- Haken und Protokoll."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.aus = os.path.join(self.tmp.name, "lauf-a")
        self.echte = (rag.cmd_eval_spiel, rag.answer, rag.werte_fragen)

        def fake_answer(frage, hits):
            rag.LETZTER_ENTSCHEID = ("B", {"A": 0.1, "B": 0.8, "C": 0.1}) if "Geld" in frage else None
            return f"Antwort auf: {frage}"

        def fake_spiel(sid, data_dir=None):
            hits = [({"seite": 11, "text": "t"}, 0.91234567), ({"seite": 6, "text": "u"}, 0.5)]
            return rag.werte_fragen(FRAGEN, lambda frage: hits)

        def fake_eval(args, data_dir=None):
            for sid in ("spiel-a", "spiel-b"):
                rag.cmd_eval_spiel(sid, data_dir)

        self.fake_eval = fake_eval
        for p in (mock.patch.object(rag, "answer", fake_answer), mock.patch.object(rag, "cmd_eval_spiel", fake_spiel)):
            p.start()
            self.addCleanup(p.stop)

    def lauf(self, **k):
        return still(m.fuehre_aus, self.aus, ("--alle",), eval_fn=self.fake_eval, **k)

    def zeilen(self):
        with open(os.path.join(self.aus, "antworten.jsonl"), encoding="utf-8") as f:
            return [json.loads(z) for z in f]

    def meta(self):
        with open(os.path.join(self.aus, "meta.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_protokoll_je_frage(self):
        self.assertEqual(self.lauf(), 4)
        z = self.zeilen()
        self.assertEqual([(x["spiel_id"], x["frage_id"]) for x in z],
                         [("spiel-a", 1), ("spiel-a", 2), ("spiel-b", 1), ("spiel-b", 2)])
        self.assertEqual(z[0]["antwort"], "Antwort auf: Wie verdiene ich Geld?")
        self.assertEqual(z[0]["abgerufen"], [11, 6])
        self.assertEqual(z[0]["scores"], [0.9123, 0.5])
        self.assertEqual((z[0]["entscheid"], z[0]["probs"]), ("B", {"A": 0.1, "B": 0.8, "C": 0.1}))
        self.assertEqual((z[1]["entscheid"], z[1]["probs"]), (None, None))
        self.assertIsInstance(z[0]["t_antwort"], float)

    def test_laufzeit_wird_um_die_antwort_gemessen(self):
        uhr = itertools.chain([10.0, 14.5], itertools.repeat(20.0))
        with mock.patch.object(m.time, "perf_counter", lambda: next(uhr)):
            self.lauf()
        self.assertEqual(self.zeilen()[0]["t_antwort"], 4.5)

    def test_meta_json_mit_modell_und_konfiguration(self):
        with mock.patch.object(rag, "LLM_MODEL", "test-modell:7b"), mock.patch.object(rag, "TOP_K", 6), \
                mock.patch.dict(os.environ, {"LLM_MODEL": "test-modell:7b", "TOP_K": "6", "GEHEIM_TOKEN": "x"}):
            self.lauf()
        meta = self.meta()
        self.assertEqual(meta["modell"], "test-modell:7b")
        self.assertEqual(meta["konfiguration"]["TOP_K"], 6)
        self.assertEqual(meta["env"]["LLM_MODEL"], "test-modell:7b")
        self.assertNotIn("GEHEIM_TOKEN", meta["env"])            # feste Liste, nie die ganze Umgebung
        self.assertNotIn("x", json.dumps(meta).replace("test-modell", ""))
        self.assertEqual(meta["antworten"], 4)
        self.assertTrue(meta["start"] and meta["ende"])
        self.assertEqual(meta["argumente"], ["--alle"])
        for schluessel in ("konfiguration", "drop_types", "entscheidung_an", "rag_commit", "python"):
            self.assertIn(schluessel, meta)

    def test_meta_json_steht_auch_nach_abbruch(self):
        def kaputt(args, data_dir=None):
            rag.cmd_eval_spiel("spiel-a", data_dir)
            raise RuntimeError("Ollama weg")
        with self.assertRaises(RuntimeError):
            still(m.fuehre_aus, self.aus, ("--alle",), eval_fn=kaputt)
        self.assertEqual(self.meta()["antworten"], 2)
        self.assertEqual(self.meta()["modell"], rag.LLM_MODEL)

    def test_haken_werden_zurueckgenommen(self):
        vorher = (rag.cmd_eval_spiel, rag.answer, rag.werte_fragen)
        self.lauf()
        self.assertEqual((rag.cmd_eval_spiel, rag.answer, rag.werte_fragen), vorher)

    def test_vorhandener_lauf_wird_nicht_ueberschrieben(self):
        self.lauf()
        vorher = lies(os.path.join(self.aus, "antworten.jsonl"))
        with self.assertRaises(m.MessFehler):
            self.lauf()
        self.assertEqual(lies(os.path.join(self.aus, "antworten.jsonl")), vorher)
        self.lauf(ueberschreiben=True)

    def test_main_meldet_fehler_ohne_traceback(self):
        self.lauf()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = m.main([self.aus])
        self.assertEqual(rc, 1)
        self.assertIn("enthaelt schon einen Lauf", err.getvalue())


class TestGitStand(unittest.TestCase):
    def git(self, verz, *a):
        subprocess.run(["git", "-C", verz, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                       check=True, capture_output=True)

    def test_commit_und_geaendert(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "rag.py")
            schreibe(pfad, "x = 1\n")
            self.git(d, "init", "-q")
            self.git(d, "add", "rag.py")
            self.git(d, "commit", "-q", "-m", "a")
            commit, geaendert = m.git_stand(pfad)
            self.assertEqual(len(commit), 40)
            self.assertFalse(geaendert)
            schreibe(pfad, "x = 2\n")
            self.assertTrue(m.git_stand(pfad)[1])

    def test_ausserhalb_eines_git_baums(self):
        with tempfile.TemporaryDirectory() as d:
            pfad = os.path.join(d, "rag.py")
            schreibe(pfad, "x = 1\n")
            with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": os.path.dirname(d)}):
                self.assertEqual(m.git_stand(pfad), (None, None))


class TestEchteVerdrahtung(unittest.TestCase):
    """rag.cmd_eval_spiele mit Fake-Embedding und Fake-Antwort: die Haken muessen dort greifen."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = os.path.join(self.tmp.name, "data")
        patches = [mock.patch.object(rag, "DATA_DIR", self.data),
                   mock.patch.object(rag, "INDEX_PATH", os.path.join(self.data, "index.sqlite")),
                   mock.patch.object(rag, "embed", tes.fake_embed),
                   mock.patch.object(rag, "answer", lambda frage, hits: "Das geschieht in Phase 4."),
                   mock.patch.multiple(rag, CHUNK_SIZE=400, CHUNK_OVERLAP=150, HYBRID=False, RERANK=False),
                   mock.patch.dict(os.environ, {"DROP_TYPES": "flavor"})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        for name, chunks, gs in ((tes.AN, tes.FCM, tes.GS_A), (tes.BN, tes.BRASS, tes.GS_B)):
            meta = rag.lege_spiel_an(name)
            rag.schreibe_jsonl(rag.knowledge_pfad(meta["spiel_id"]), chunks)
            with open(os.path.join(self.data, meta["spiel_id"], "golden_set.json"), "w", encoding="utf-8") as f:
                json.dump(gs, f)

    def test_alle_spiele_werden_protokolliert(self):
        aus = os.path.join(self.tmp.name, "lauf")
        n = still(m.fuehre_aus, aus, ("--alle",))
        self.assertEqual(n, len(tes.GS_A["fragen"]) + len(tes.GS_B["fragen"]))
        with open(os.path.join(aus, "antworten.jsonl"), encoding="utf-8") as f:
            z = [json.loads(x) for x in f]
        self.assertEqual({x["spiel_id"] for x in z}, {tes.A, tes.B})
        # Frage 1 von FCM: erwartete Seite 11 wurde abgerufen; fremde Spiele fliessen nicht ein
        self.assertIn(11, next(x for x in z if x["spiel_id"] == tes.A and x["frage_id"] == 1)["abgerufen"])
        self.assertTrue(all(x["antwort"] == "Das geschieht in Phase 4." for x in z))
        meta = json.loads(lies(os.path.join(aus, "meta.json")))
        self.assertEqual((meta["modell"], meta["antworten"]), (rag.LLM_MODEL, n))
        self.assertEqual(meta["drop_types"], ["flavor"])

    def test_einzelnes_spiel_und_datenverzeichnis_als_argument(self):
        aus = os.path.join(self.tmp.name, "lauf")
        n = still(m.fuehre_aus, aus, (tes.B,), data_dir=self.data)
        self.assertEqual(n, len(tes.GS_B["fragen"]))
        self.assertEqual(json.loads(lies(os.path.join(aus, "meta.json")))["daten"], self.data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
