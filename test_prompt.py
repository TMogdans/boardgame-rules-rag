#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prompt-Version v1/v2: waehlbar, Default bleibt v1.

    python test_prompt.py

Was hier festgehalten wird:
  - v1 ist byte-gleich zum Bestand (Wortlaut unten hinterlegt, nicht aus rag.py abgeleitet)
  - v2 ist v1 mit ersetzter Regel 6 und neuer Regel 9 -- sonst nichts
  - der Default ist v1 (Modul-Konstante UND frischer Import ohne Umgebung)
  - PROMPT_VERSION per Umgebung wirkt bei rag.py; in der Pipe gilt das Valve, auch ueber
    eine Umgebungsvariable des Containers (Open WebUI setzt eigene Variablen)
  - unbekannte Version bricht ab (KonfigFehler bzw. sichtbarer Fehler im Chat)
  - Konfig-Zeile der Eval nennt prompt=... nur bei v2 (sonst aendern sich Referenzen)
  - die Verweigerungs-Saetze von v2 zaehlen bei Verweigerungsfragen als Signalwort
  - der Judge (kern-Prompt) wertet diese Saetze nicht als falsche Aussage
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import judge  # noqa: E402
import openwebui_pipe as op  # noqa: E402
import rag  # noqa: E402
import test_openwebui_pipe as tpipe  # noqa: E402
import test_pipe_index as tindex  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))

# v1 so, wie er vor der Prompt-Version im Repo stand (508737a). Bewusst als Wortlaut hier.
V1 = """Du bist ein Regel-Assistent, der Fragen ausschliesslich auf Basis der dir bereitgestellten Quellen (Regelwerke) beantwortet.

Regeln:
1. Antworte immer auf Deutsch.
2. Stuetze jede sachliche Aussage ausschliesslich auf die bereitgestellten Quellen. Verlasse dich fuer konkrete Werte (Zahlen, Betraege, Kartennamen, Dauer, Reichweiten) NIEMALS auf dein Gedaechtnis - uebernimm sie woertlich aus der Quelle.
3. Nenne zu jeder Aussage die Fundstelle (Seite). Pruefe VOR jeder Aussage, ob die zitierte Stelle sie wirklich stuetzt. Wenn nicht, triff die Aussage nicht.
4. Wenn mehrere aehnliche Elemente existieren (z.B. verschiedene Karten), vergewissere dich, dass Wert UND Name aus derselben Fundstelle stammen. Ordne eine Zahl nie der falschen Karte zu.
5. Interpretiere jede Frage im Kontext der bereitgestellten Dokumente (es geht um ein Brettspiel, nicht um die reale Welt).
6. Ist eine Frage nicht durch die Quellen gedeckt, sage ausdruecklich "Dazu enthaelt das Dokument keine Angaben." und rate NICHT.
7. Kein externes Wissen einbauen.
8. Lieber knapp und korrekt als ausfuehrlich und unsicher."""

REGEL_6_V2 = ('6. Steht die Antwort nicht eindeutig in den Quellen, rate NICHT. Sage dann: "In den gefundenen Stellen '
              'steht das nicht eindeutig." und nenne die Seiten der Quellen, die dem Thema am naechsten kommen '
              '("Schau auf Seite X nach."). Beruehren die Quellen das Thema gar nicht, sage: "In den gefundenen '
              'Stellen steht dazu nichts."')
REGEL_9_V2 = ('9. Nennen die Quellen eine Ausnahme oder widersprechen sie sich, gib beide Stellen mit Seite an, '
              'statt dich fuer eine zu entscheiden.')

HITS = [({"doc": "regeln.pdf", "seite": 5, "text": "Text."}, 0.9)]


def system_von(nachrichten):
    assert nachrichten[0]["role"] == "system"
    return nachrichten[0]["content"]


class TestPromptTexte(unittest.TestCase):
    def test_v1_ist_byte_gleich_zum_bestand(self):
        self.assertEqual(rag.SYSTEM_PROMPTS["v1"], V1)
        self.assertEqual(rag.SYSTEM_PROMPT, V1)

    def test_v2_ist_v1_mit_regel_6_ersetzt_und_regel_9(self):
        zeilen_v1 = V1.split("\n")
        zeilen_v2 = rag.SYSTEM_PROMPTS["v2"].split("\n")
        self.assertEqual(zeilen_v2[:len(zeilen_v1)][:7], zeilen_v1[:7])       # Kopf, Regeln 1-5 unveraendert
        i6 = next(i for i, z in enumerate(zeilen_v1) if z.startswith("6. "))
        self.assertEqual(zeilen_v2[i6], REGEL_6_V2)
        self.assertEqual(zeilen_v2[i6 + 1:len(zeilen_v1)], zeilen_v1[i6 + 1:])  # Regeln 7, 8 unveraendert
        self.assertEqual(zeilen_v2[len(zeilen_v1):], [REGEL_9_V2])
        self.assertEqual(len(zeilen_v2), len(zeilen_v1) + 1)

    def test_nur_diese_zwei_versionen(self):
        self.assertEqual(sorted(rag.SYSTEM_PROMPTS), ["v1", "v2"])


class TestVersionWahl(unittest.TestCase):
    def test_default_ist_v1(self):
        self.assertEqual(rag.PROMPT_VERSION, "v1")
        self.assertEqual(system_von(rag.baue_nachrichten("Frage?", HITS)), V1)

    def test_default_ohne_umgebung_im_frischen_prozess(self):
        # der Default steht im Code, nicht in der Umgebung dieses Tests
        env = {k: v for k, v in os.environ.items() if k != "PROMPT_VERSION"}
        env.update(DATA_DIR=os.path.join(testumgebung.TMP, "data"), HOME=testumgebung.HOME)
        code = "import rag; print(rag.PROMPT_VERSION)"
        p = subprocess.run([sys.executable, "-c", code], cwd=BASE, env=env, capture_output=True, text=True)
        self.assertEqual(p.stdout.strip(), "v1", p.stderr)

    def test_umgebung_waehlt_v2_im_frischen_prozess(self):
        env = dict(os.environ, PROMPT_VERSION="v2", DATA_DIR=os.path.join(testumgebung.TMP, "data"),
                   HOME=testumgebung.HOME)
        code = ("import rag, json; print(json.dumps(rag.baue_nachrichten('F?', "
                "[({'doc': 'd', 'seite': 1, 'text': 't'}, 1.0)])[0]['content']))")
        p = subprocess.run([sys.executable, "-c", code], cwd=BASE, env=env, capture_output=True, text=True)
        self.assertEqual(json.loads(p.stdout), rag.SYSTEM_PROMPTS["v2"], p.stderr)

    def test_baue_nachrichten_folgt_der_version(self):
        with mock.patch.object(rag, "PROMPT_VERSION", "v2"):
            nachrichten = rag.baue_nachrichten("Frage?", HITS)
        self.assertEqual(system_von(nachrichten), rag.SYSTEM_PROMPTS["v2"])
        self.assertIn("Quellen:\n[regeln.pdf, Seite 5]\nText.\n\nFrage: Frage?", nachrichten[1]["content"])

    def test_unbekannte_version_bricht_ab(self):
        with self.assertRaises(rag.KonfigFehler) as ctx:
            rag.system_prompt("v3")
        self.assertIn("v3", str(ctx.exception))
        with mock.patch.object(rag, "PROMPT_VERSION", "v3"):
            with self.assertRaises(rag.KonfigFehler):
                rag.baue_nachrichten("Frage?", HITS)
            with self.assertRaises(rag.KonfigFehler):
                rag._konfig_zeile("pdf")

    def test_konfig_zeile_nennt_prompt_nur_bei_v2(self):
        v1 = rag._konfig_zeile("pdf")
        self.assertNotIn("prompt=", v1)
        with mock.patch.object(rag, "PROMPT_VERSION", "v2"):
            v2 = rag._konfig_zeile("pdf")
        self.assertIn("  prompt=v2", v2)
        self.assertEqual(v2.replace("  prompt=v2", ""), v1)      # sonst bleibt alles wie heute


class TestPipeAlterWeg(tpipe.PipeTestBasis):
    def prompt(self, i=-1):
        return self.llm_bekam[i]["messages"][0]["content"]

    def test_default_valve_ist_v1_und_payload_unveraendert(self):
        self.assertEqual(op.Pipe.Valves().PROMPT_VERSION, "v1")
        self.frage("Geld")
        self.assertEqual(self.prompt(), V1)

    def test_valve_v2_wirkt(self):
        self.pipe.valves.PROMPT_VERSION = "v2"
        self.frage("Geld")
        self.assertEqual(self.prompt(), rag.SYSTEM_PROMPTS["v2"])

    def test_valve_wirkt_pro_anfrage_in_beide_richtungen(self):
        self.frage("Geld")
        self.pipe.valves.PROMPT_VERSION = "v2"
        self.frage("Geld")
        self.pipe.valves.PROMPT_VERSION = "v1"
        self.frage("Geld")
        self.assertEqual([self.prompt(i) for i in range(3)], [V1, rag.SYSTEM_PROMPTS["v2"], V1])

    def test_valve_schlaegt_die_container_umgebung(self):
        # Open WebUI setzt eigene Umgebungsvariablen; rag.py liest PROMPT_VERSION beim Import
        # (die Pipe laedt es frisch). Das Valve gilt trotzdem -- in beide Richtungen.
        with mock.patch.dict(os.environ, {"PROMPT_VERSION": "v2"}):
            self.frage("Geld")                                    # Valve v1 (Default) gegen Umgebung v2
            self.assertEqual(self.prompt(), V1)
        self.pipe = op.Pipe()
        self.pipe.valves = op.Pipe.Valves(RAG_DIR=BASE, KNOWLEDGE_PATH=self.wissen, OLLAMA_URL="http://stub",
                                          TOP_K=2, DROP_TYPES="flavor", PROMPT_VERSION="v2")
        with mock.patch.dict(os.environ, {"PROMPT_VERSION": "v1"}):
            self.frage("Geld")                                    # Valve v2 gegen Umgebung v1
        self.assertEqual(self.prompt(), rag.SYSTEM_PROMPTS["v2"])

    def test_sprachmodus_unveraendert(self):
        body = {"messages": [{"role": "user", "content": "Geld"}], "regelfrage": {"sprache": True}}
        self.pipe.valves.PROMPT_VERSION = "v2"
        text = "".join(tpipe.sammle(self.pipe.pipe(body)))
        self.assertEqual(text, "Antwort")                        # ohne Fusszeile
        self.assertEqual(self.prompt(), rag.SYSTEM_PROMPTS["v2"])

    def test_unbekannte_version_ist_im_chat_sichtbar(self):
        self.pipe.valves.PROMPT_VERSION = "v3"
        text = self.frage("Geld")
        self.assertIn("Fehler in der RAG-Pipe", text)
        self.assertIn("v3", text)
        self.assertEqual(self.llm_bekam, [])

    def test_task_bekommt_keinen_regelprompt(self):
        self.pipe.valves.PROMPT_VERSION = "v2"
        self.frage("Erzeuge einen Titel", task="title_generation")
        self.assertEqual([m["role"] for m in self.nachrichten()], ["user"])


class TestPipeIndexWeg(tindex.PipeIndexBasis):
    def prompt(self, i=-1):
        return self.llm_bekam[i]["messages"][0]["content"]

    def test_default_v1_und_v2_per_valve(self):
        self.frage("Geld", spiel="Brass")
        self.pipe.valves.PROMPT_VERSION = "v2"
        self.frage("Geld", spiel="Brass")
        self.pipe.valves.PROMPT_VERSION = "v1"
        self.frage("Geld", spiel="Brass")
        self.assertEqual([self.prompt(i) for i in range(3)], [V1, rag.SYSTEM_PROMPTS["v2"], V1])

    def test_valve_schlaegt_die_container_umgebung(self):
        with mock.patch.dict(os.environ, {"PROMPT_VERSION": "v2"}):
            self.frage("Geld", spiel="Brass")
        self.assertEqual(self.prompt(), V1)
        self.pipe = op.Pipe()
        self.pipe.valves = op.Pipe.Valves(RAG_DIR=BASE, INDEX_PATH=self.index, OLLAMA_URL="http://stub",
                                          TOP_K=2, DROP_TYPES="flavor", PROMPT_VERSION="v2")
        with mock.patch.dict(os.environ, {"PROMPT_VERSION": "v1"}):
            self.frage("Geld", spiel="Brass")
        self.assertEqual(self.prompt(), rag.SYSTEM_PROMPTS["v2"])

    def test_sprachmodus_unveraendert(self):
        self.pipe.valves.PROMPT_VERSION = "v2"
        text = self.frage("Geld", spiel="Brass", sprache=True)
        self.assertNotIn("*Quelle:", text)
        self.assertEqual(self.prompt(), rag.SYSTEM_PROMPTS["v2"])

    def test_unbekannte_version_ist_im_chat_sichtbar(self):
        self.pipe.valves.PROMPT_VERSION = "v3"
        text = self.frage("Geld", spiel="Brass")
        self.assertIn("v3", text)
        self.assertEqual(self.llm_bekam, [])


class TestPipeMitAltemRag(unittest.TestCase):
    def test_v2_ohne_prompt_versionen_im_rag_bricht_ab(self):
        # Ein aelterer Clone im Mount kennt PROMPT_VERSION nicht -- v2 waere still wirkungslos.
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "rag.py"), "w", encoding="utf-8") as f:
                f.write("".join(f"def {n}(*a, **k):\n    return None\n" for n in op._RAG_ALTER_WEG))
            p = op.Pipe()
            p.valves = op.Pipe.Valves(RAG_DIR=d, PROMPT_VERSION="v2")
            with self.assertRaises(RuntimeError) as ctx:
                p._lade_rag(p.valves)
            self.assertIn("PROMPT_VERSION", str(ctx.exception))
            p.valves = op.Pipe.Valves(RAG_DIR=d)              # v1 bleibt mit altem rag.py moeglich
            self.assertIsNotNone(p._lade_rag(p.valves))


def werte(frage, antwort, seiten=(2,)):
    return rag.bewerte_frage(frage, list(seiten), antwort)


VERWEIGERUNGSFRAGE = {"id": 8, "typ": "leerstelle", "erwartet": "keine Angabe", "erwartet_verweigerung": True,
                      "keywords": ["keine Angabe", "keine Angaben"], "seiten": []}
NORMALFRAGE = {"id": 1, "typ": "fakt", "erwartet": "10 Dollar", "keywords": ["10 Dollar"], "seiten": [2]}


class TestSignalwortV2(unittest.TestCase):
    def test_v2_saetze_zaehlen_bei_verweigerungsfragen(self):
        for antwort in ("In den gefundenen Stellen steht das nicht eindeutig. Schau auf Seite 5 nach.",
                        "In den gefundenen Stellen steht dazu nichts.",
                        "in den gefundenen stellen steht dazu nichts",
                        "In den gefundenen\nStellen steht das nicht eindeutig."):
            with self.subTest(antwort=antwort):
                satz = werte(VERWEIGERUNGSFRAGE, antwort)
                self.assertEqual(satz["kategorie"], rag.KAT_VERWEIGERUNG)
                self.assertTrue(satz["keywords_getroffen"], "v2-Verweigerung nicht als Signal erkannt")

    def test_v2_saetze_ohne_keywords_im_golden_set(self):
        # das Golden Set nennt das Signalwort nicht -- der Satz selbst genuegt
        frage = dict(VERWEIGERUNGSFRAGE, keywords=["nein"])
        self.assertTrue(werte(frage, "In den gefundenen Stellen steht dazu nichts.")["keywords_getroffen"])
        _, z = self._lauf(frage, "In den gefundenen Stellen steht das nicht eindeutig. Schau auf Seite 3 nach.")
        self.assertEqual((z["verweigerungsfragen"], z["verweigerung_signal"]), (1, 1))

    def test_kein_signal_ohne_den_satz(self):
        for antwort in ("In den gefundenen Stellen steht: es gibt einen Solo-Modus.",
                        "Der Solo-Modus steht dazu nichts",
                        "Das steht nicht eindeutig im Heft."):
            with self.subTest(antwort=antwort):
                self.assertEqual(werte(dict(VERWEIGERUNGSFRAGE, keywords=["nein"]), antwort)["keywords_getroffen"], [])

    def test_bei_normalfragen_ist_verweigern_kein_treffer(self):
        satz = werte(NORMALFRAGE, "In den gefundenen Stellen steht dazu nichts.")
        self.assertEqual(satz["kategorie"], rag.KAT_GETROFFEN)
        self.assertEqual(satz["keywords_getroffen"], [])

    def test_v1_satz_und_keywords_wie_bisher(self):
        satz = werte(VERWEIGERUNGSFRAGE, "Dazu enthaelt das Dokument keine Angaben.")
        self.assertEqual(satz["keywords_getroffen"], ["keine Angabe", "keine Angaben"])   # nur Golden-Set-Keywords
        self.assertEqual(werte(VERWEIGERUNGSFRAGE, "Es gibt einen Solo-Modus.")["keywords_getroffen"], [])

    def test_keine_doppelte_zaehlung(self):
        satz = werte(dict(VERWEIGERUNGSFRAGE, keywords=["In den gefundenen Stellen steht dazu nichts"]),
                     "In den gefundenen Stellen steht dazu nichts.")
        self.assertEqual(satz["keywords_getroffen"], ["In den gefundenen Stellen steht dazu nichts"])

    def _lauf(self, frage, antwort):
        satz = werte(frage, antwort)
        return satz, rag.fasse_zusammen([satz])


class TestJudgeRegel(unittest.TestCase):
    FRAGE = {"frage": "Wie funktioniert der Solo-Modus?", "erwartet": "keine Angabe", "beleg": "Seite 2",
             "erwartet_verweigerung": True}
    SAETZE = ("Dazu enthaelt das Dokument keine Angaben", "In den gefundenen Stellen steht das nicht eindeutig",
              "In den gefundenen Stellen steht dazu nichts")

    def test_kern_prompt_nennt_die_drei_saetze_und_die_folge(self):
        prompt = judge.baue_prompt(dict(self.FRAGE, kern="Kein Solo-Modus", zusatz=[]), "x", "frei")
        for satz in self.SAETZE:
            self.assertIn(f"„{satz}“", prompt)
        self.assertIn("(auch mit Umlauten, mit Seitenhinweis) sind KEINE falsche Aussage", prompt)
        self.assertIn("Steht die Antwort im Heft, ist eine solche Antwort unsicher; ist Verweigern richtig "
                      "(erwartet_verweigerung), ist sie richtig. Nur wenn daneben eine falsche Regel behauptet "
                      "wird, ist sie falsch.", prompt)

    def test_prompt_ohne_kern_bleibt_ohne_die_regel(self):
        for modus in ("frei", "logprob"):
            prompt = judge.baue_prompt(self.FRAGE, "x", modus)
            self.assertNotIn("KEINE falsche Aussage", prompt)
            self.assertNotIn("nicht eindeutig", prompt)
            self.assertNotIn("steht dazu nichts", prompt)

    def test_regel_steht_in_den_klassen_und_in_beiden_modi(self):
        for modus in ("frei", "logprob"):
            prompt = judge.baue_prompt(dict(self.FRAGE, kern="k"), "x", modus)
            klassen = prompt.split("Klassen:")[1].split("Frage:")[0]
            self.assertIn("steht dazu nichts", klassen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
