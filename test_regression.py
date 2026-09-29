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
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402
import regression_referenz as ref  # noqa: E402
from regression_referenz import WISSEN, GOLDEN, FRAGEN, RASTER, achsen_embed, hash_embed  # noqa: E402

# REGRESSION_REFERENZ=<pfad> prueft gegen eine anders erzeugte Referenz (andere Plattform,
# --gleichstand-umgekehrt) -- der Vergleich muss fuer jede gueltige ed36f99-Ausgabe bestehen.
with open(os.environ.get("REGRESSION_REFERENZ") or ref.JSON_PFAD, encoding="utf-8") as _f:
    SOLL = json.load(_f)
TOL = 1e-6


def voller_schluessel(key):
    """Schluessel des k=alle-Falls derselben Frage/Konfiguration."""
    teile = key.split("|")
    teile[3] = "k=alle"
    return "|".join(teile)


def gleichstandsbewusst_gleich(ist, soll, voll):
    """(gleich?, Grund). ist/soll: Top-k-Signaturen, voll: alle Chunks der Referenz.

    - gleiche Laenge, Score je Platz gleich (Toleranz)
    - je Scorewert: liegt die ganze Gleichstandsgruppe (laut voll) im Top-k, muessen
      dieselben Treffer (Position, Seite, Hash) drin sein -- in beliebiger Folge;
      schneidet die Gruppe die k-Grenze, nur gleich viele Mitglieder DIESER Gruppe.
    Gruppen der Groesse 1 heissen damit: exakt derselbe Treffer.
    """
    from collections import Counter
    if len(ist) != len(soll):
        return False, f"Laenge {len(ist)} statt {len(soll)}"
    for i, (a, b) in enumerate(zip(ist, soll)):
        if abs(a[3] - b[3]) >= TOL:
            return False, f"Platz {i}: Score {a[3]} statt {b[3]}"
    werte = []
    for e in soll:
        if not any(abs(e[3] - w) < TOL for w in werte):
            werte.append(e[3])
    for w in werte:
        ist_g = Counter(tuple(e[:3]) for e in ist if abs(e[3] - w) < TOL)
        soll_g = Counter(tuple(e[:3]) for e in soll if abs(e[3] - w) < TOL)
        voll_g = Counter(tuple(e[:3]) for e in voll if abs(e[3] - w) < TOL)
        if sum(voll_g.values()) == sum(soll_g.values()):
            if ist_g != soll_g:
                return False, f"Score {w}: {sorted(ist_g)} statt {sorted(soll_g)}"
        elif ist_g - voll_g or sum(ist_g.values()) != sum(soll_g.values()):
            return False, f"Score {w}: {sorted(ist_g)} nicht aus der Gruppe {sorted(voll_g)}"
    return True, ""


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

    def vergleiche_topk(self, ist, wo):
        soll = SOLL["topk"]
        self.assertEqual(sorted(ist), sorted(soll), f"{wo}: andere Faelle als in der Referenz")
        abweichend = []
        for key in soll:
            gleich, grund = gleichstandsbewusst_gleich(ist[key], soll[key], soll[voller_schluessel(key)])
            if not gleich:
                abweichend.append((key, grund))
        self.assertEqual(abweichend[:3], [], f"{wo}: {len(abweichend)} von {len(soll)} Faellen weichen von "
                                             f"{ref.REFERENZ_COMMIT} ab")

    def vergleiche_rerank(self, ist, wo):
        # Hash-Attrappe: Gleichstaende nur zwischen identischen Duplikaten (siehe
        # test_hash_gleichstaende_nur_duplikate) -> Seite/Hash/Score-Folge ist
        # plattformunabhaengig; nur die Position zwischen Duplikaten nicht.
        soll = SOLL["rerank"]
        self.assertEqual(sorted(ist), sorted(soll))
        for key in soll:
            self.assertEqual([e[1:3] for e in ist[key]], [e[1:3] for e in soll[key]], f"{wo}: {key}")
            for a, b in zip(ist[key], soll[key]):
                self.assertLess(abs(a[3] - b[3]), TOL, f"{wo}: {key}")


class TestGegenEd36f99(RegressionsTest):
    def test_alter_weg_gleich_ed36f99(self):
        ist = ref.berechne(self.alter_weg, self.eval_alt)
        self.vergleiche_topk(ist["topk"], "alter Weg")
        self.vergleiche_rerank(ist["rerank"], "alter Weg")
        self.assertEqual(ist["eval"], SOLL["eval"])

    def test_neuer_weg_gleich_ed36f99(self):
        self.migriere()
        ist = ref.berechne(self.neuer_weg, self.eval_neu)
        self.vergleiche_topk(ist["topk"], "Index-Weg")
        self.vergleiche_rerank(ist["rerank"], "Index-Weg")
        self.assertEqual(ist["eval"], SOLL["eval"])

    def test_hash_gleichstaende_nur_duplikate(self):
        # Voraussetzung fuer den exakten Reranker-/eval-Vergleich: bei der Hash-Attrappe
        # haben alle Chunks gleichen Scores denselben Text auf derselben Seite.
        for key, liste in SOLL["topk"].items():
            if not key.startswith("fake-hash|") or "|k=alle|" not in key:
                continue
            for e in liste:
                gruppe = {(x[1], x[2]) for x in liste if abs(x[3] - e[3]) < TOL}
                self.assertEqual(len(gruppe), 1, f"{key}: verschiedene Chunks gleichen Scores {gruppe}")

    def test_vergleich_ist_ein_detektor(self):
        # Gegenprobe zum gleichstandsbewussten Vergleich: echte Abweichungen fallen auf.
        key = next(k for k, v in SOLL["topk"].items() if "|k=4|" in k and len(v) == 4
                   and len({round(e[3], 6) for e in v}) == 4)          # vier verschiedene Scores
        soll, voll = SOLL["topk"][key], SOLL["topk"][voller_schluessel(key)]
        self.assertTrue(gleichstandsbewusst_gleich(soll, soll, voll)[0])
        self.assertFalse(gleichstandsbewusst_gleich(soll[::-1], soll, voll)[0])      # Reihenfolge
        anders = [list(e) for e in soll]
        anders[0][2] = "0000000000000000"
        self.assertFalse(gleichstandsbewusst_gleich(anders, soll, voll)[0])          # anderer Treffer
        # Gleichstand an der Grenze: Tausch innerhalb der Gruppe ok, fremder Chunk nicht
        key = next(k for k, v in SOLL["topk"].items() if "|k=4|" in k and len(v) == 4 and
                   sum(1 for e in SOLL["topk"][voller_schluessel(k)] if abs(e[3] - v[-1][3]) < TOL)
                   > sum(1 for e in v if abs(e[3] - v[-1][3]) < TOL))
        soll, voll = SOLL["topk"][key], SOLL["topk"][voller_schluessel(key)]
        draussen = next(e for e in voll if abs(e[3] - soll[-1][3]) < TOL and e not in soll)
        self.assertTrue(gleichstandsbewusst_gleich(soll[:-1] + [draussen], soll, voll)[0])
        fremd = next(e for e in voll if abs(e[3] - soll[-1][3]) >= TOL and e not in soll)
        self.assertFalse(gleichstandsbewusst_gleich(soll[:-1] + [fremd[:3] + [soll[-1][3]]], soll, voll)[0])

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


class TestVergleiche(RegressionsTest):
    """`rag.py vergleiche` im Aufbau von Drachenhort: Symlinks im Clone, data/ migriert."""

    def setUp(self):
        super().setUp()
        lab = os.path.join(self.tmp.name, "rag-lab")
        os.mkdir(lab)
        for name in ("knowledge.jsonl", "golden_set.json"):
            os.replace(os.path.join(self.basis, name), os.path.join(lab, name))
            os.symlink(os.path.join(lab, name), os.path.join(self.basis, name))
        self.lab = lab
        self.migriere()

    def lauf(self, *args):
        puffer = io.StringIO()
        with self.mit("fake-hash", 400, 150, "flavor,meta"), contextlib.redirect_stdout(puffer):
            rag.aktualisiere_index(None, ausgabe=lambda *_: None)
            rag.cmd_vergleiche(list(args))
        return puffer.getvalue()

    def test_mit_name_und_mit_id(self):
        for angabe in ("Food Chain Magnate", "food-chain-magnate", "FCM"):
            with self.subTest(angabe=angabe):
                text = self.lauf(angabe)
                self.assertIn(f"{len(GOLDEN['fragen'])}/{len(GOLDEN['fragen'])} Fragen mit identischer", text)
                self.assertIn(os.path.join(self.lab, "knowledge.jsonl"), text)   # aufgeloester Symlink

    def test_quelle_per_umgebung_statt_symlink(self):
        # Ersatz fuer den Symlink neben rag.py: KNOWLEDGE_JSONL/GOLDEN_SET (nur lesend)
        for name in ("knowledge.jsonl", "golden_set.json"):
            os.remove(os.path.join(self.basis, name))
        env = {"KNOWLEDGE_JSONL": os.path.join(self.lab, "knowledge.jsonl"),
               "GOLDEN_SET": os.path.join(self.lab, "golden_set.json")}
        with mock.patch.dict(os.environ, env):
            text = self.lauf("Food Chain Magnate")
            self.assertIn(f"{len(GOLDEN['fragen'])}/{len(GOLDEN['fragen'])} Fragen mit identischer", text)
            puffer = io.StringIO()
            with self.mit("fake-hash", 400, 150, "flavor,meta"), contextlib.redirect_stdout(puffer):
                os.environ.update(env)
                rag.cmd_eval()
            self.assertIn("getroffen :", puffer.getvalue())

    def test_leere_quelle_bricht_laut_ab(self):
        open(os.path.join(self.lab, "knowledge.jsonl"), "w").close()
        with self.assertRaises(rag.KonfigFehler) as ctx:
            self.lauf("Food Chain Magnate")
        self.assertIn("Alter Weg ohne Chunks", str(ctx.exception))
        self.assertIn("0 Eintraege", str(ctx.exception))

    def test_nach_drop_types_leere_quelle_bricht_laut_ab(self):
        rag.schreibe_jsonl(os.path.join(self.lab, "knowledge.jsonl"), [e for e in WISSEN if e.get("typ") == "meta"])
        with self.assertRaises(rag.KonfigFehler) as ctx:
            self.lauf("food-chain-magnate")
        self.assertIn("nach DROP_TYPES=flavor,meta bleibt keiner", str(ctx.exception))

    def test_kaputter_symlink(self):
        os.remove(os.path.join(self.lab, "knowledge.jsonl"))
        with self.assertRaises(rag.KonfigFehler) as ctx:
            self.lauf("food-chain-magnate")
        self.assertIn("Symlink kaputt", str(ctx.exception))

    def test_ollama_liefert_keine_embeddings(self):
        antwort = mock.Mock(**{"json.return_value": {"embeddings": []}})
        with mock.patch("requests.post", return_value=antwort), self.assertRaises(RuntimeError) as ctx:
            rag.embed(["a", "b"])
        self.assertIn("fuer 2 Texte", str(ctx.exception))

    def test_retrieve_ohne_embeddings_ist_kein_matmul_traceback(self):
        chunks = [{"doc": "knowledge", "seite": 1, "text": "x"}]
        for embs in (np.zeros((0,), dtype=np.float32), np.zeros((1, 0), dtype=np.float32), None):
            with self.subTest(embs=None if embs is None else embs.shape), self.mit("fake-hash", 400, 150, ""):
                with self.assertRaises(rag.KonfigFehler):
                    rag.retrieve("Geld", chunks if embs is not None and len(embs) else [], embs, k=1)


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
