#!/usr/bin/env python3
"""
Alter Weg der Pipe (ohne INDEX_PATH) byte-gleich zu ed36f99 -- 806 Werte von
regelfrage.spiel gegen die eingefrorenen Ausgaben in pipe_referenz.json.

    python test_pipe_alt.py

Zur Testzeit ohne git. Neu erzeugen: python pipe_referenz.py --erzeuge
"""
import json
import os
import unittest

import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import openwebui_pipe as op  # noqa: E402
import pipe_referenz as ref  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
with open(ref.JSON_PFAD, encoding="utf-8") as _f:
    SOLL = json.load(_f)


class TestAlterWegWieEd36f99(unittest.TestCase):
    def test_806_werte_byte_gleich(self):
        werte = [w for w, _ in SOLL["faelle"]]
        ist = ref.antworten(ref.pipe_mit_attrappen(op, BASE), werte)
        abweichend = [(w, a, s) for w, a, (_, s) in zip(werte, ist, SOLL["faelle"]) if a != s]
        self.assertEqual(abweichend[:3], [], f"{len(abweichend)} von {len(werte)} Faellen weichen von ed36f99 ab")

    def test_referenz_ist_vollstaendig(self):
        self.assertEqual(len(SOLL["faelle"]), 806)
        self.assertEqual([w for w, _ in SOLL["faelle"]][:800], ref.werte())
        treffer = sum(1 for _, a in SOLL["faelle"] if a.startswith("ANTWORT"))
        self.assertTrue(50 < treffer < 800, treffer)     # beide Ausgaenge kommen vor
        self.assertIn(ref.REFERENZ_COMMIT, SOLL["_erzeugt_mit"])

    def test_600_verlaeufe_wie_ed36f99(self):
        # Kritiker 4 (c_diff.py): Verlaeufe mit Fusszeilen/Fehlerzeilen, Listen, System,
        # task, sprache -- Ausgabe und LLM-Nutzlast wie ed36f99 (stabil sortiert)
        with open(ref.VERLAUF_PFAD, encoding="utf-8") as f:
            soll = json.load(f)["faelle"]
        wissen = os.path.join(testumgebung.TMP, "knowledge_verlauf.jsonl")
        with open(wissen, "w", encoding="utf-8") as f:
            for z in ref.wissen_zeilen():
                f.write(json.dumps(z, ensure_ascii=False) + "\n")
        faelle = ref.verlauf_faelle()
        ist = ref.lauf_verlaeufe(op, BASE, wissen, faelle)
        self.assertEqual(len(ist), 600)
        abweichend = [(i, faelle[i][0], a[0][:120], s[0][:120]) for i, (a, s) in enumerate(zip(ist, soll)) if a != s]
        self.assertEqual(abweichend[:2], [], f"{len(abweichend)}/600 Verlaeufe weichen von ed36f99 ab")
        # die Faelle decken, was sie decken sollen
        texte = json.dumps([b for b, _ in faelle], ensure_ascii=False)
        for stueck in ("*Quelle: Food Chain Magnate", "Fehler in der RAG-Pipe", '"image_url"', '"system"', '"sprache"'):
            self.assertIn(stueck, texte)

    def test_ohne_rag_dir_bleibt_kein_regelheft(self):
        # Deployment: fehlt der Clone im Mount, antwortet der alte Weg auf ein unbekanntes
        # Spiel weiter mit "kein Regelheft" -- wie ed36f99, ohne rag.py zu laden.
        p = ref.pipe_mit_attrappen(op, "/gibt/es/nicht")
        text = ref.antworten(p, ["Terraforming Mars"])[0]
        self.assertTrue(text.startswith("Zu „Terraforming Mars“ habe ich kein Regelheft."), text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
