#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests des persistenten Index (data/index.sqlite) -- ohne Ollama.

    python test_index.py

Embeddings kommen aus einer deterministischen Attrappe, die jeden eingebetteten
Text mitzaehlt. Die Invalidierung wird deshalb an ihrer WIRKUNG geprueft: wie
viele Texte tatsaechlich neu eingebettet wurden -- nicht an einem Etikett, das
dieselbe Aenderung mitverschieben koennte.
"""
import hashlib
import json
import shutil
import os
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402

DIM = 8


def hash_vektor(text):
    """Deterministischer Pseudo-Vektor je Text (unabhaengig vom Batch)."""
    d = hashlib.sha256(text.encode()).digest()
    return [b / 255.0 - 0.5 for b in d[:DIM]]


class Zaehler:
    def __init__(self):
        self.texte = []
        self.modelle = []

    def __call__(self, texte):
        self.texte.extend(texte)
        self.modelle.append(rag.EMBED_MODEL)
        return np.array([hash_vektor(t) for t in texte], dtype=np.float32)


def chunk(spiel_id, name, i, seite, text, typ="regel"):
    return {"id": i, "seite": seite, "typ": typ, "text": text, "spiel": name, "spiel_id": spiel_id}


FCM = [chunk("food-chain-magnate", "Food Chain Magnate", 1, 2, "Werbung auf dem Deckblatt.", "flavor"),
       chunk("food-chain-magnate", "Food Chain Magnate", 2, 11, "Geld verdient man in Phase 4. " * 5),
       chunk("food-chain-magnate", "Food Chain Magnate", 3, 6, "Der Truck Driver hat Reichweite 3.")]
BRASS = [chunk("brass-birmingham", "Brass: Birmingham", 1, 4, "Canal era comes first. " * 4),
         chunk("brass-birmingham", "Brass: Birmingham", 2, 9, "Rail era follows.")]


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.index = os.path.join(self.data, "index.sqlite")
        self.embed = Zaehler()
        self.patches = [mock.patch.object(rag, "DATA_DIR", self.data),
                        mock.patch.object(rag, "INDEX_PATH", self.index),
                        mock.patch.object(rag, "embed", self.embed),
                        mock.patch.multiple(rag, CHUNK_SIZE=60, CHUNK_OVERLAP=10, EMBED_MODEL="bge-m3",
                                            EMBED_BATCH=3)]
        for p in self.patches:
            p.start()
        self.lege_an("Food Chain Magnate", FCM, aliase=["FCM"])
        self.lege_an("Brass: Birmingham", BRASS, sprache="en")

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def oeffne(self):
        con = rag.oeffne_index()
        self.addCleanup(con.close)
        return con

    def lege_an(self, name, chunks, **kw):
        meta = rag.lege_spiel_an(name, **kw)
        rag.schreibe_jsonl(rag.knowledge_pfad(meta["spiel_id"]), chunks)
        return meta

    def baue(self, ids=None):
        vorher = len(self.embed.texte)
        erg = rag.aktualisiere_index(ids, ausgabe=lambda *_: None)
        return erg, len(self.embed.texte) - vorher

    def stuecke(self, chunks):
        return len(rag.indexiere_stuecke(chunks))


class TestFingerprint(IndexTest):
    def test_erster_bau_bettet_alles_ein_zweiter_nichts(self):
        erg, n = self.baue()
        self.assertEqual(n, self.stuecke(FCM) + self.stuecke(BRASS))
        self.assertEqual({k: v[0] for k, v in erg.items()},
                         {"food-chain-magnate": "neu", "brass-birmingham": "neu"})
        erg, n = self.baue()
        self.assertEqual(n, 0)
        self.assertEqual({k: v[0] for k, v in erg.items()},
                         {"food-chain-magnate": "aktuell", "brass-birmingham": "aktuell"})

    def test_geaenderte_datei_nur_dieses_spiel_neu(self):
        self.baue()
        neu = BRASS + [chunk("brass-birmingham", "Brass: Birmingham", 3, 10, "Neue Regel.")]
        rag.schreibe_jsonl(rag.knowledge_pfad("brass-birmingham"), neu)
        erg, n = self.baue()
        self.assertEqual(n, self.stuecke(neu))
        self.assertEqual(erg["food-chain-magnate"][0], "aktuell")
        self.assertEqual(erg["brass-birmingham"], ("neu", self.stuecke(neu)))

    def test_neuer_inhalt_mit_alter_mtime_und_gleicher_groesse(self):
        # cp -p / Restore: mtime und Groesse gleich, Inhalt anders
        self.baue()
        pfad = rag.knowledge_pfad("food-chain-magnate")
        st = os.stat(pfad)
        with open(pfad, encoding="utf-8") as f:
            inhalt = f.read()
        getauscht = inhalt.replace("Reichweite 3", "Reichweite 4")
        self.assertEqual(len(getauscht), len(inhalt))
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(getauscht)
        os.utime(pfad, ns=(st.st_atime_ns, st.st_mtime_ns))
        _, n = self.baue(["food-chain-magnate"])
        self.assertEqual(n, self.stuecke(FCM))
        con = self.oeffne()
        chunks, _ = rag.lade_spiel(con, "food-chain-magnate")
        self.assertIn("Der Truck Driver hat Reichweite 4.", [c["text"] for c in chunks])

    def test_aenderung_hinter_dem_ersten_kibibyte(self):
        # Kritiker I1: der Hash muss die GANZE Datei sehen, nicht nur den Anfang
        pfad = os.path.join(self.tmp.name, "gross.jsonl")
        anfang = b"x" * 5000
        with open(pfad, "wb") as f:
            f.write(anfang + b"A")
        vorher = rag.fingerprint(pfad, "k")
        with open(pfad, "wb") as f:
            f.write(anfang + b"B")
        self.assertNotEqual(rag.fingerprint(pfad, "k"), vorher)
        # Kritiker I2: die Konfiguration gehoert zum Fingerprint
        self.assertNotEqual(rag.fingerprint(pfad, "k"), rag.fingerprint(pfad, "k2"))
        # und im Index: eine Aenderung am Ende einer grossen knowledge.jsonl wird neu eingebettet
        viele = FCM + [chunk("food-chain-magnate", "Food Chain Magnate", 100 + i, 20, f"Fuellregel {i} " * 5)
                       for i in range(30)]
        wissen = rag.knowledge_pfad("food-chain-magnate")
        rag.schreibe_jsonl(wissen, viele)
        self.assertGreater(os.path.getsize(wissen), 4096)
        self.baue()
        rag.schreibe_jsonl(wissen, viele[:-1] + [dict(viele[-1], text="Letzte Regel geaendert.")])
        erg, n = self.baue(["food-chain-magnate"])
        self.assertEqual(erg["food-chain-magnate"][0], "neu")
        self.assertGreater(n, 0)

    def test_anderes_embed_modell_ist_ein_eigener_stand(self):
        self.baue()
        with mock.patch.object(rag, "EMBED_MODEL", "anderes-modell"):
            _, n = self.baue(["food-chain-magnate"])
            self.assertEqual(n, self.stuecke(FCM))
            self.assertEqual(self.embed.modelle[-1], "anderes-modell")
        # der alte Stand ist noch da -> zurueck zu bge-m3 kostet nichts
        _, n = self.baue(["food-chain-magnate"])
        self.assertEqual(n, 0)

    def test_chunk_konfiguration_invalidiert(self):
        self.baue()
        for feld, wert in (("CHUNK_SIZE", 40), ("CHUNK_OVERLAP", 5)):
            with self.subTest(feld=feld), mock.patch.object(rag, feld, wert):
                _, n = self.baue(["food-chain-magnate"])
                self.assertEqual(n, self.stuecke(FCM))
                con = self.oeffne()
                chunks, _ = rag.lade_spiel(con, "food-chain-magnate")
                erwartet = [s for _, _, s in rag.indexiere_stuecke(FCM)]
                self.assertEqual([c["text"] for c in chunks], erwartet)

    def test_schema_version_invalidiert(self):
        self.baue()
        with mock.patch.object(rag, "INDEX_SCHEMA", rag.INDEX_SCHEMA + 1):
            _, n = self.baue()
        self.assertEqual(n, self.stuecke(FCM) + self.stuecke(BRASS))

    def test_drop_types_braucht_kein_neues_embedding(self):
        self.baue()
        vorher = len(self.embed.texte)
        con = self.oeffne()
        alle, _ = rag.lade_spiel(con, "food-chain-magnate")
        ohne, embs = rag.lade_spiel(con, "food-chain-magnate", {"flavor"})
        self.assertEqual(len(self.embed.texte), vorher)
        self.assertEqual(len(alle) - len(ohne), self.stuecke(FCM[:1]))
        self.assertNotIn(2, [c["seite"] for c in ohne])
        self.assertEqual(embs.shape, (len(ohne), DIM))

    def test_neuer_alias_ohne_neues_embedding(self):
        self.baue()
        rag.lege_spiel_an("Food Chain Magnate", aliase=["FCM", "Fast Food"])
        _, n = self.baue()
        self.assertEqual(n, 0)
        con = self.oeffne()
        fcm = [s for s in rag.spiele_im_index(con) if s["spiel_id"] == "food-chain-magnate"][0]
        self.assertEqual(fcm["aliase"], ["FCM", "Fast Food"])

    def test_abbruch_beim_einbetten_laesst_alten_stand_stehen(self):
        self.baue()
        rag.schreibe_jsonl(rag.knowledge_pfad("food-chain-magnate"), FCM[:2])

        def kaputt(texte):
            raise RuntimeError("Ollama weg")
        with mock.patch.object(rag, "embed", kaputt), self.assertRaises(RuntimeError):
            self.baue(["food-chain-magnate"])
        con = self.oeffne()
        chunks, _ = rag.lade_spiel(con, "food-chain-magnate")
        self.assertEqual(len(chunks), self.stuecke(FCM))    # alter Stand, vollstaendig
        # und beim naechsten Lauf wird nachgeholt
        _, n = self.baue(["food-chain-magnate"])
        self.assertEqual(n, self.stuecke(FCM[:2]))


class TestSpieleImIndex(IndexTest):
    def test_einzelaufruf_fasst_fremde_spiele_nicht_an(self):
        self.baue()
        import shutil
        shutil.rmtree(os.path.join(self.data, "brass-birmingham"))
        self.baue(["food-chain-magnate"])
        con = self.oeffne()
        self.assertEqual([s["spiel_id"] for s in rag.spiele_im_index(con)],
                         ["brass-birmingham", "food-chain-magnate"])
        erg, _ = self.baue()   # --alle raeumt auf
        self.assertEqual(erg["brass-birmingham"], ("entfernt", 0))
        con = self.oeffne()
        self.assertEqual([s["spiel_id"] for s in rag.spiele_im_index(con)], ["food-chain-magnate"])
        self.assertEqual(con.execute("SELECT count(*) FROM chunks WHERE spiel_id='brass-birmingham'").fetchone()[0], 0)

    def test_kaputtes_spiel_haelt_den_rest_nicht_auf(self):
        self.baue()
        import shutil
        shutil.rmtree(os.path.join(self.data, "brass-birmingham"))       # verschwunden
        rag.lege_spiel_an("Ohne Wissen")                                   # spiel.json ohne knowledge.jsonl
        rag.lege_spiel_an("Leer")
        open(rag.knowledge_pfad("leer"), "w").close()                      # leere knowledge.jsonl
        neu = FCM + [chunk("food-chain-magnate", "Food Chain Magnate", 4, 3, "Neue Regel.")]
        rag.schreibe_jsonl(rag.knowledge_pfad("food-chain-magnate"), neu)
        meldungen = []
        with self.assertRaises(rag.KonfigFehler) as ctx:
            rag.aktualisiere_index(ausgabe=meldungen.append)
        text = str(ctx.exception)
        self.assertIn("2 von 3 Spielen", text)
        self.assertIn("leer", text)
        self.assertIn("ohne-wissen", text)
        self.assertEqual(ctx.exception.ergebnis["food-chain-magnate"], ("neu", self.stuecke(neu)))
        self.assertEqual(ctx.exception.ergebnis["brass-birmingham"], ("entfernt", 0))
        self.assertTrue(any("leer: FEHLER" in m for m in meldungen))
        con = self.oeffne()
        self.assertEqual([s["spiel_id"] for s in rag.spiele_im_index(con)], ["food-chain-magnate"])
        chunks, _ = rag.lade_spiel(con, "food-chain-magnate")
        self.assertIn("Neue Regel.", [c["text"] for c in chunks])

    def test_einzelnes_kaputtes_spiel_meldet_seinen_eigenen_fehler(self):
        rag.lege_spiel_an("Ohne Wissen")
        with self.assertRaises(rag.KonfigFehler) as ctx:
            rag.aktualisiere_index(["ohne-wissen"], ausgabe=lambda *_: None)
        self.assertIn("knowledge.jsonl fehlt", str(ctx.exception))

    def test_metadaten(self):
        self.baue()
        con = self.oeffne()
        self.assertEqual(rag.spiele_im_index(con), [
            {"spiel_id": "brass-birmingham", "name": "Brass: Birmingham", "aliase": [], "sprache": "en",
             "quelle_pdf": None},
            {"spiel_id": "food-chain-magnate", "name": "Food Chain Magnate", "aliase": ["FCM"],
             "sprache": "de", "quelle_pdf": None}])

    def test_lade_spiel_liefert_nur_dieses_spiel(self):
        self.baue()
        con = self.oeffne()
        for sid, quelle in (("food-chain-magnate", FCM), ("brass-birmingham", BRASS)):
            chunks, embs = rag.lade_spiel(con, sid)
            self.assertEqual({c["spiel_id"] for c in chunks}, {sid})
            self.assertEqual([c["text"] for c in chunks], [s for _, _, s in rag.indexiere_stuecke(quelle)])
            self.assertEqual([c["seite"] for c in chunks], [s for s, _, _ in rag.indexiere_stuecke(quelle)])
            np.testing.assert_array_equal(embs, rag.l2norm(np.array([hash_vektor(c["text"]) for c in chunks],
                                                                     dtype=np.float32)))

    def test_fehlender_stand_ist_klarer_fehler(self):
        self.baue(["food-chain-magnate"])
        con = self.oeffne()
        with self.assertRaises(rag.KonfigFehler):
            rag.lade_spiel(con, "brass-birmingham")
        with mock.patch.object(rag, "CHUNK_SIZE", 500), self.assertRaises(rag.KonfigFehler) as ctx:
            rag.lade_spiel(con, "food-chain-magnate")
        self.assertIn("rag.py index food-chain-magnate", str(ctx.exception))

    def test_drop_types_ohne_typ_feld_ist_fehler(self):
        ohne_typ = [{k: v for k, v in c.items() if k != "typ"} for c in BRASS]
        rag.schreibe_jsonl(rag.knowledge_pfad("brass-birmingham"), ohne_typ)
        self.baue()
        con = self.oeffne()
        with self.assertRaises(rag.KonfigFehler):
            rag.lade_spiel(con, "brass-birmingham", {"flavor"})
        self.assertEqual(len(rag.lade_spiel(con, "brass-birmingham")[0]), self.stuecke(BRASS))

    def test_lesend_ist_wirklich_nur_lesend(self):
        self.baue()
        con = self.oeffne()
        with self.assertRaises(sqlite3.OperationalError):
            con.execute("DELETE FROM chunks")

    def test_sonderzeichen_im_indexpfad(self):
        # "?", "#", "%" und Leerzeichen duerfen in der file:-URI nicht als URI-Syntax wirken
        for name in ("mit leer zeichen", "frage?mode=rw", "raute#frag", "prozent%20x", "alles ? # % zu"):
            with self.subTest(name=name):
                verz = os.path.join(self.tmp.name, name)
                pfad = os.path.join(verz, "index.sqlite")
                with mock.patch.object(rag, "INDEX_PATH", pfad):
                    rag.aktualisiere_index(ausgabe=lambda *_: None, pfad=pfad)
                    con = rag.oeffne_index(pfad)
                    self.addCleanup(con.close)
                    self.assertEqual([s["spiel_id"] for s in rag.spiele_im_index(con)],
                                     ["brass-birmingham", "food-chain-magnate"])
                    with self.assertRaises(sqlite3.OperationalError):
                        con.execute("DELETE FROM chunks")       # wirklich read-only
                    self.assertEqual(sorted(os.listdir(verz)), ["index.sqlite"])   # keine Nebendatei

    def test_heisses_journal_klare_meldung(self):
        # Nachgebaut: Schreibtransaktion offen, Datei + -journal mitten darin kopiert,
        # Kopie in einem read-only Verzeichnis (wie der Pipe-Mount)
        self.baue()
        kopie = os.path.join(self.tmp.name, "kopie")
        os.mkdir(kopie)
        con = sqlite3.connect(self.index)
        con.execute("CREATE TABLE ballast (x TEXT)")         # genug Seiten, damit SQLite sie
        con.executemany("INSERT INTO ballast VALUES (?)", [("a" * 1000,)] * 2000)   # vor dem Commit schreibt
        con.commit()
        # synchronous=OFF: der Journal-Kopf traegt dann "Eintraege aus der Dateigroesse" --
        # mit NORMAL/FULL ist er unter SQLite 3.51 zum Kopierzeitpunkt noch leer (gemessen)
        con.execute("PRAGMA synchronous=OFF")
        con.execute("PRAGMA cache_size=1")
        con.execute("BEGIN")
        con.execute("UPDATE ballast SET x = 'b'")
        self.assertTrue(os.path.exists(self.index + "-journal"))
        shutil.copy(self.index, kopie)
        shutil.copy(self.index + "-journal", kopie)
        con.rollback()
        con.close()
        os.chmod(kopie, 0o555)
        try:
            with self.assertRaises(rag.KonfigFehler) as ctx:
                rag.oeffne_index(os.path.join(kopie, "index.sqlite"))
        finally:
            os.chmod(kopie, 0o755)
        self.assertIn("unvollstaendiges Journal", str(ctx.exception))
        self.assertIn("rag.py index --alle", str(ctx.exception))
        # auf dem Host (schreibend) rollt SQLite es zurueck, danach geht lesen wieder
        rag.oeffne_index(os.path.join(kopie, "index.sqlite"), schreibend=True).close()
        rag.oeffne_index(os.path.join(kopie, "index.sqlite")).close()

    def test_fehlender_index(self):
        with self.assertRaises(rag.KonfigFehler):
            rag.oeffne_index(os.path.join(self.tmp.name, "gibts-nicht.sqlite"))

    def test_seite_kommt_unveraendert_zurueck(self):
        # Seiten sind im Golden Set Zahlen; "11" (String) waere dort kein Treffer.
        rag.schreibe_jsonl(rag.knowledge_pfad("brass-birmingham"),
                           [chunk("brass-birmingham", "Brass: Birmingham", 1, 11, "x")])
        self.baue()
        con = self.oeffne()
        (c,), _ = rag.lade_spiel(con, "brass-birmingham")
        self.assertIs(type(c["seite"]), int)


if __name__ == "__main__":
    unittest.main(verbosity=2)
