#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entscheidungsschritt vor der Antwort (ENTSCHEIDUNG / Valve ENTSCHEIDUNG), ohne Modell.

    python test_entscheidung.py

Was hier festgehalten wird:
  - Default aus (Modul-Konstante, frischer Import ohne Umgebung, Valve); unbekannter Wert bricht ab
  - aus: answer() macht genau den einen LLM-Aufruf wie bisher, Payload unveraendert
  - Prompt der Optionswahl woertlich wie gemessen (System- und Fragetext hier als Wortlaut),
    dieselben Quellenkoepfe wie baue_nachrichten, Payload mit logprobs/num_predict 1/temperature 0
  - nur die gewaehlte Option zaehlt (argmax), keine Schwelle; Token-Varianten wie im judge
  - fehlt logprobs: KonfigFehler, nie still "A"; keine Option unter top_logprobs: "A" mit probs None
  - C: KEIN Antwort-Aufruf, fester Text mit den abgerufenen Seiten (Rangfolge, ohne Duplikate)
  - B: normale Antwort plus Hinweis mit denselben Seiten; A: normale Antwort unveraendert
  - der C-Satz zaehlt als Verweigerungs-Signalwort und faellt unter die judge-Regel
  - Konfig-Zeile nennt entscheidung=1 nur, wenn an
  - Pipe (alter und Index-Weg): Valve wirkt und schlaegt die Container-Umgebung in beide
    Richtungen; bei C kein LLM-Stream; Sprachmodus ohne "S." und ohne Markdown, Fusszeile im
    Chat bleibt; B-Hinweis faellt aus dem Verlauf
Erwartete Texte stehen hier als Wortlaut, nicht aus rag.py abgeleitet.
"""
import contextlib
import io
import json
import math
import os
import re
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

# Wortlaut der Messung vom 2026-09-30 (entscheid_messen.py)
SYSTEM_GEMESSEN = "Du pruefst nuechtern, ob bereitgestellte Regelheft-Auszuege eine Frage zu einem Brettspiel beantworten."
FRAGE_GEMESSEN = ("Enthalten die Quellen die Antwort auf die Frage?\n"
                  "A) ja, vollstaendig  B) nur teilweise  C) nein, die Antwort steht nicht in den Quellen\n"
                  "Antworte nur mit dem Buchstaben.")

HITS = [({"doc": "regeln.pdf", "seite": 14, "text": "Text A."}, 0.9),
        ({"doc": "regeln.pdf", "seite": 12, "text": "Text B."}, 0.8),
        ({"doc": "regeln.pdf", "seite": 14, "text": "Text C."}, 0.7)]
C_CHAT = "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: S. 14, S. 12."
C_SPRACHE = "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: Seite 14 und Seite 12."
B_CHAT = "\n\nHinweis: nur teilweise belegt -- pruef S. 14, S. 12."
B_SPRACHE = "\n\nHinweis: nur teilweise belegt, pruef Seite 14 und Seite 12."


def logprob_antwort(verteilung, erstes=None):
    """Ollama-Antwort mit logprobs; verteilung: [(token, p), ...] in Rangfolge."""
    top = [{"token": t, "logprob": math.log(p)} for t, p in verteilung]
    kopf = dict(top[0]) if top else {"token": erstes or "?", "logprob": 0.0}
    return {"message": {"content": kopf["token"]}, "logprobs": [dict(kopf, top_logprobs=top)]}


def verteilung_fuer(option):
    """Klare Wahl der Option, Rest verteilt (Konfidenz wie gemessen fast immer > 0,99)."""
    rest = [o for o in "ABC" if o != option]
    return [(option, 0.995), (rest[0], 0.004), (rest[1], 0.001)]


class FakeOllama:
    """requests.post-Attrappe: Embeddings wie test_openwebui_pipe, /api/chat unterscheidet
    Optionswahl (logprobs im Payload) und Antwort."""

    def __init__(self, option="A", antwort=None):
        self.option = option
        self.antwort = antwort          # ganze Ollama-Antwort der Optionswahl (uebersteuert option)
        self.entscheid = []             # (url, payload) der Optionswahl
        self.antworten = []             # (url, payload) der Antwort-Aufrufe

    def __call__(self, url, json=None, timeout=None):
        if url.endswith("/api/chat") and json.get("logprobs"):
            self.entscheid.append((url, json))
            return tpipe.FakeAntwort(self.antwort if self.antwort is not None
                                     else logprob_antwort(verteilung_fuer(self.option)))
        if url.endswith("/api/chat"):
            self.antworten.append((url, json))
            return tpipe.FakeAntwort({"message": {"content": "CLI-Antwort"}})
        return tpipe.fake_post(url, json=json, timeout=timeout)


def frischer_prozess(code, **env_extra):
    env = {k: v for k, v in os.environ.items() if k != "ENTSCHEIDUNG"}
    env.update(DATA_DIR=os.path.join(testumgebung.TMP, "data"), HOME=testumgebung.HOME, **env_extra)
    return subprocess.run([sys.executable, "-c", code], cwd=BASE, env=env, capture_output=True, text=True)


# ---------------------------------------------------------------- rag.py
class TestSchalter(unittest.TestCase):
    def test_default_ist_aus(self):
        self.assertEqual(rag.ENTSCHEIDUNG, "0")
        self.assertFalse(rag.entscheidung_an())

    def test_default_ohne_umgebung_im_frischen_prozess(self):
        p = frischer_prozess("import rag; print(rag.ENTSCHEIDUNG, rag.entscheidung_an())")
        self.assertEqual(p.stdout.strip(), "0 False", p.stderr)

    def test_umgebung_schaltet_an_im_frischen_prozess(self):
        p = frischer_prozess("import rag; print(rag.entscheidung_an())", ENTSCHEIDUNG="1")
        self.assertEqual(p.stdout.strip(), "True", p.stderr)

    def test_unbekannter_wert_bricht_ab(self):
        for wert in ("ja", "true", "2", "", " 1", "an"):
            with self.subTest(wert=wert):
                with self.assertRaises(rag.KonfigFehler) as ctx:
                    rag.entscheidung_an(wert)
                self.assertIn("ENTSCHEIDUNG", str(ctx.exception))
                with mock.patch.object(rag, "ENTSCHEIDUNG", wert):
                    with self.assertRaises(rag.KonfigFehler):
                        rag.answer("F?", HITS)
                    with self.assertRaises(rag.KonfigFehler):
                        rag._konfig_zeile("pdf")

    def test_unbekannter_wert_bricht_die_eval_vor_dem_ersten_aufruf_ab(self):
        p = frischer_prozess("import rag, sys\ntry:\n    rag._konfig_zeile('pdf')\nexcept rag.KonfigFehler as e:\n"
                             "    print('ABBRUCH', e)", ENTSCHEIDUNG="true")
        self.assertIn("ABBRUCH ENTSCHEIDUNG 'true' unbekannt", p.stdout, p.stderr)


class TestAusWieBisher(unittest.TestCase):
    def test_aus_genau_ein_llm_aufruf_mit_unveraendertem_payload(self):
        fake = FakeOllama(option="C")
        with mock.patch("requests.post", side_effect=fake) as p:
            text = rag.answer("F?", HITS)
        self.assertEqual(text, "CLI-Antwort")
        self.assertEqual(fake.entscheid, [])
        self.assertEqual(p.call_count, 1)
        self.assertEqual(p.call_args.kwargs["json"], {"model": rag.LLM_MODEL, "messages": rag.baue_nachrichten("F?", HITS),
                                                      "think": rag.THINK, "stream": False})
        self.assertEqual(p.call_args.kwargs["timeout"], 600)

    def test_quellenkoepfe_von_baue_nachrichten_unveraendert(self):
        n = rag.baue_nachrichten("F?", HITS[:2])
        self.assertEqual(n[1]["content"], "Quellen:\n[regeln.pdf, Seite 14]\nText A.\n\n[regeln.pdf, Seite 12]\nText B.\n\nFrage: F?")


class TestOptionswahlPrompt(unittest.TestCase):
    def test_nachrichten_woertlich_wie_gemessen(self):
        n = rag.entscheid_nachrichten("Wer beginnt?", HITS[:2])
        self.assertEqual(n, [
            {"role": "system", "content": SYSTEM_GEMESSEN},
            {"role": "user", "content": "Quellen:\n[regeln.pdf, Seite 14]\nText A.\n\n[regeln.pdf, Seite 12]\nText B."
                                        "\n\nFrage: Wer beginnt?\n\n" + FRAGE_GEMESSEN}])

    def test_gleiche_quellen_wie_die_antwort(self):
        antwort = rag.baue_nachrichten("F?", HITS)[1]["content"]
        entscheid = rag.entscheid_nachrichten("F?", HITS)[1]["content"]
        self.assertEqual(entscheid, antwort + "\n\n" + FRAGE_GEMESSEN)

    def test_payload_wie_gemessen(self):
        fake = FakeOllama(option="A")
        with mock.patch("requests.post", side_effect=fake):
            rag.entscheide("F?", HITS)
        url, payload = fake.entscheid[0]
        self.assertEqual(url, f"{rag.OLLAMA}/api/chat")
        self.assertEqual(payload, {"model": rag.LLM_MODEL, "messages": rag.entscheid_nachrichten("F?", HITS),
                                   "stream": False, "think": False, "logprobs": True, "top_logprobs": 20,
                                   "options": {"num_predict": 1, "temperature": 0}})

    def test_modell_und_ollama_uebersteuerbar(self):
        fake = FakeOllama(option="A")
        with mock.patch("requests.post", side_effect=fake):
            rag.entscheide("F?", HITS, modell="gemma3:12b", ollama="http://anders")
        self.assertEqual(fake.entscheid[0][0], "http://anders/api/chat")
        self.assertEqual(fake.entscheid[0][1]["model"], "gemma3:12b")


class TestOptionAuswerten(unittest.TestCase):
    def test_argmax_ohne_schwelle(self):
        # niedrige Konfidenz aendert nichts: gewaehlt ist, was vorne liegt
        for verteilung, erwartet in (([("C", 0.4), ("A", 0.35), ("B", 0.25)], "C"),
                                     ([("B", 0.5), ("C", 0.3), ("A", 0.2)], "B"),
                                     ([("C", 0.34), ("B", 0.33), ("A", 0.33)], "C"),
                                     ([("A", 0.6), ("C", 0.4)], "A")):
            with self.subTest(verteilung=verteilung):
                option, probs = rag.werte_entscheid(logprob_antwort(verteilung))
                self.assertEqual(option, erwartet)
                self.assertAlmostEqual(sum(probs.values()), 1.0)

    def test_token_varianten_werden_zusammengezaehlt(self):
        # "C" 0,3 + " C" 0,2 + "c)" 0,1 = 0,6 gegen A 0,4
        option, probs = rag.werte_entscheid(logprob_antwort([("A", 0.4), ("C", 0.3), (" C", 0.2), ("c)", 0.1)]))
        self.assertEqual(option, "C")
        self.assertAlmostEqual(probs["C"], 0.6)
        for token in (" B", "B)", "b.", "B:", "\nB"):
            with self.subTest(token=token):
                self.assertEqual(rag.werte_entscheid(logprob_antwort([(token, 0.9), ("A", 0.1)]))[0], "B")

    def test_andere_token_zaehlen_nicht(self):
        option, probs = rag.werte_entscheid(logprob_antwort([("Die", 0.9), ("B", 0.06), ("A", 0.04)]))
        self.assertEqual(option, "B")
        self.assertAlmostEqual(probs["B"], 0.6)

    def test_ohne_top_logprobs_zaehlt_das_erste_token(self):
        j = {"logprobs": [{"token": "C", "logprob": -0.01}]}
        self.assertEqual(rag.werte_entscheid(j)[0], "C")

    def test_keine_option_unter_top_logprobs_ist_A_und_kenntlich(self):
        option, probs = rag.werte_entscheid(logprob_antwort([("Die", 0.7), ("Ja", 0.3)]))
        self.assertEqual((option, probs), ("A", None))

    def test_fehlendes_logprobs_bricht_ab_statt_still_A(self):
        for j in ({"message": {"content": "C"}}, {"message": {"content": "A"}, "logprobs": []},
                  {"message": {"content": "A"}, "logprobs": None}):
            with self.subTest(j=j):
                with self.assertRaises(rag.KonfigFehler) as ctx:
                    rag.werte_entscheid(j)
                self.assertIn("logprobs", str(ctx.exception))
        with mock.patch("requests.post", side_effect=FakeOllama(antwort={"message": {"content": "A"}})):
            with mock.patch.object(rag, "ENTSCHEIDUNG", "1"):
                with self.assertRaises(rag.KonfigFehler):
                    rag.answer("F?", HITS)


class TestAntwortMitEntscheid(unittest.TestCase):
    def antworte(self, option=None, antwort=None):
        fake = FakeOllama(option=option or "A", antwort=antwort)
        with mock.patch("requests.post", side_effect=fake), mock.patch.object(rag, "ENTSCHEIDUNG", "1"):
            text = rag.answer("F?", HITS)
        return text, fake

    def test_C_kein_antwort_aufruf_fester_text(self):
        text, fake = self.antworte("C")
        self.assertEqual(text, C_CHAT)
        self.assertEqual(len(fake.entscheid), 1)
        self.assertEqual(fake.antworten, [])

    def test_C_seiten_in_rangfolge_ohne_duplikate(self):
        hits = [({"doc": "d", "seite": s, "text": "t"}, 1.0) for s in (3, 9, 3, 1, 9)]
        self.assertEqual(rag.entscheid_text_nichts(hits),
                         "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: S. 3, S. 9, S. 1.")
        self.assertEqual(rag.entscheid_text_nichts([]), "In den gefundenen Stellen steht dazu nichts.")

    def test_B_antwort_plus_hinweis(self):
        text, fake = self.antworte("B")
        self.assertEqual(text, "CLI-Antwort" + B_CHAT)
        self.assertEqual(len(fake.antworten), 1)

    def test_A_und_keine_option_normale_antwort(self):
        for kwargs in ({"option": "A"}, {"antwort": logprob_antwort([("Die", 0.9), ("Ja", 0.1)])}):
            with self.subTest(**{k: str(v)[:20] for k, v in kwargs.items()}):
                text, fake = self.antworte(**kwargs)
                self.assertEqual(text, "CLI-Antwort")
                self.assertEqual(len(fake.entscheid), 1)
                self.assertEqual(len(fake.antworten), 1)

    def test_antwort_aufruf_mit_entscheid_gleich_dem_ohne(self):
        _, mit = self.antworte("B")
        fake = FakeOllama()
        with mock.patch("requests.post", side_effect=fake):
            rag.answer("F?", HITS)
        self.assertEqual(mit.antworten, fake.antworten)

    def test_beantworte_liefert_die_option(self):
        with mock.patch("requests.post", side_effect=FakeOllama(option="C")):
            text, (option, probs) = rag.beantworte("F?", HITS)
        self.assertEqual((text, option), (C_CHAT, "C"))
        self.assertGreater(probs["C"], 0.99)


class TestSprachtexte(unittest.TestCase):
    def test_wortlaut(self):
        self.assertEqual(rag.entscheid_text_nichts(HITS, sprache=True), C_SPRACHE)
        self.assertEqual(rag.entscheid_hinweis(HITS, sprache=True), B_SPRACHE)
        self.assertEqual(rag.entscheid_hinweis(HITS), B_CHAT)
        drei = HITS + [({"doc": "d", "seite": 9, "text": "t"}, 0.1)]
        self.assertEqual(rag.entscheid_text_nichts(drei, sprache=True),
                         "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: "
                         "Seite 14, Seite 12 und Seite 9.")
        self.assertEqual(rag.entscheid_hinweis(HITS[:1], sprache=True),
                         "\n\nHinweis: nur teilweise belegt, pruef Seite 14.")

    def test_ohne_abkuerzung_und_ohne_markdown(self):
        for text in (rag.entscheid_text_nichts(HITS, sprache=True), rag.entscheid_hinweis(HITS, sprache=True)):
            self.assertNotRegex(text, r"\bS\.")
            for zeichen in ("*", "_", "`", "#", "--", "[", "|"):
                self.assertNotIn(zeichen, text)


class TestEvalUndSignalwort(unittest.TestCase):
    VERWEIGERUNG = {"id": 8, "typ": "leerstelle", "frage": "Solo?", "erwartet": "keine Angabe",
                    "erwartet_verweigerung": True, "keywords": ["nein"], "seiten": []}

    def test_C_satz_ist_verweigerungs_signal(self):
        self.assertIn(rag.ENTSCHEID_NICHTS.rstrip("."), rag.VERWEIGERUNGS_SAETZE)
        for text in (C_CHAT, C_SPRACHE):
            satz = rag.bewerte_frage(self.VERWEIGERUNG, [14, 12], text)
            self.assertTrue(satz["keywords_getroffen"], text)

    def test_judge_regel_nennt_den_C_satz_mit_seitenhinweis(self):
        prompt = judge.baue_prompt(dict(self.VERWEIGERUNG, kern="Kein Solo-Modus"), C_CHAT, "logprob")
        klassen = prompt.split("Klassen:")[1].split("Frage:")[0]
        self.assertIn("„In den gefundenen Stellen steht dazu nichts“", klassen)
        self.assertIn("mit Seitenhinweis) sind KEINE falsche Aussage", klassen)
        self.assertTrue(C_CHAT.startswith("In den gefundenen Stellen steht dazu nichts"))

    def test_konfig_zeile_nennt_entscheidung_nur_wenn_an(self):
        aus = rag._konfig_zeile("index")
        self.assertNotIn("entscheidung", aus)
        with mock.patch.object(rag, "ENTSCHEIDUNG", "1"):
            an = rag._konfig_zeile("index")
        self.assertIn("  entscheidung=1  source=index", an)
        self.assertEqual(an.replace("  entscheidung=1", ""), aus)

    def test_werte_fragen_mit_entscheid(self):
        fragen = [dict(self.VERWEIGERUNG), {"id": 1, "typ": "fakt", "frage": "Geld?", "erwartet": "x",
                                            "keywords": ["CLI-Antwort"], "seiten": [14]}]
        ausgabe = io.StringIO()
        fake = FakeOllama(option="C")
        with mock.patch("requests.post", side_effect=fake), mock.patch.object(rag, "ENTSCHEIDUNG", "1"), \
             contextlib.redirect_stdout(ausgabe):
            saetze = rag.werte_fragen(fragen, lambda q: HITS)
        self.assertEqual(fake.antworten, [])
        self.assertTrue(saetze[0]["keywords_getroffen"])
        self.assertEqual(saetze[1]["keywords_getroffen"], [])
        self.assertIn(f"    Antwort  : {C_CHAT}", ausgabe.getvalue())
        self.assertEqual(ausgabe.getvalue().count("    Entscheid: C (A="), 2)

    def test_werte_fragen_laeuft_ueber_rag_answer(self):
        # Mess-Skripte (lauf-6spiele/lauf.py) haengen rag.answer um -- auch mit Entscheidung muss
        # jede Frage dort durch, und die Option steht danach in LETZTER_ENTSCHEID.
        gesehen = []
        echt = rag.answer

        def haken(frage, hits):
            text = echt(frage, hits)
            gesehen.append((text, rag.LETZTER_ENTSCHEID[0]))
            return text
        with mock.patch("requests.post", side_effect=FakeOllama(option="B")), \
             mock.patch.object(rag, "ENTSCHEIDUNG", "1"), mock.patch.object(rag, "answer", haken), \
             contextlib.redirect_stdout(io.StringIO()):
            rag.werte_fragen([dict(self.VERWEIGERUNG)], lambda q: HITS)
        self.assertEqual(gesehen, [("CLI-Antwort" + B_CHAT, "B")])

    def test_letzter_entscheid_aus_ist_none(self):
        with mock.patch("requests.post", side_effect=FakeOllama(option="C")):
            with mock.patch.object(rag, "ENTSCHEIDUNG", "1"):
                rag.answer("F?", HITS)
            self.assertEqual(rag.LETZTER_ENTSCHEID[0], "C")
            rag.answer("F?", HITS)
        self.assertIsNone(rag.LETZTER_ENTSCHEID)

    def test_werte_fragen_aus_ohne_entscheid_zeile(self):
        ausgabe = io.StringIO()
        with mock.patch("requests.post", side_effect=FakeOllama(option="C")), contextlib.redirect_stdout(ausgabe):
            rag.werte_fragen([dict(self.VERWEIGERUNG)], lambda q: HITS)
        self.assertNotIn("Entscheid", ausgabe.getvalue())
        self.assertIn("    Antwort  : CLI-Antwort", ausgabe.getvalue())


# ---------------------------------------------------------------- Pipe
def seiten_im_entscheid(payload):
    """Seiten aus den Quellenkoepfen des Optionswahl-Prompts, in Rangfolge, ohne Duplikate."""
    return list(dict.fromkeys(re.findall(r"\[[^\]]*, Seite (\d+)\]", payload["messages"][1]["content"])))


def c_chat(seiten):
    return "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: " + ", ".join(f"S. {s}" for s in seiten) + "."


def c_sprache(seiten):
    t = [f"Seite {s}" for s in seiten]
    liste = t[0] if len(t) == 1 else ", ".join(t[:-1]) + " und " + t[-1]
    return f"In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: {liste}."


class PipeEntscheidMixin:
    """Gemeinsame Pipe-Tests fuer alten und Index-Weg; fussnote(text) trennt die Fusszeile ab."""
    FUSS = None      # Anfang der Fusszeile

    def fake(self, option):
        self.ollama = FakeOllama(option=option)
        self.post_mock.side_effect = self.ollama

    def teile(self, text):
        i = text.find(self.FUSS)
        return (text, "") if i < 0 else (text[:i], text[i:])

    def test_valve_default_aus_und_ohne_optionswahl(self):
        self.assertIs(op.Pipe.Valves().ENTSCHEIDUNG, False)
        self.fake("C")
        text = self.stelle("Geld")
        self.assertEqual(self.ollama.entscheid, [])
        self.assertEqual(self.teile(text)[0], "Antwort")
        self.assertEqual(len(self.llm_bekam), 1)

    def test_C_kein_stream_fester_text_und_fusszeile(self):
        self.fake("C")
        self.pipe.valves.ENTSCHEIDUNG = True
        for stream in (True, False):
            with self.subTest(stream=stream):
                self.ollama.entscheid.clear()
                text = self.stelle("Geld", stream=stream)
                self.assertEqual(self.llm_bekam, [])
                self.assertEqual(len(self.ollama.entscheid), 1)
                seiten = seiten_im_entscheid(self.ollama.entscheid[0][1])
                self.assertTrue(seiten)
                antwort, fuss = self.teile(text)
                self.assertEqual(antwort, c_chat(seiten))
                self.assertTrue(fuss)                                   # Fusszeile wie heute

    def test_C_sprachmodus_aussprechbar_ohne_fusszeile(self):
        self.fake("C")
        self.pipe.valves.ENTSCHEIDUNG = True
        text = self.stelle("Geld", sprache=True)
        self.assertEqual(self.llm_bekam, [])
        self.assertEqual(text, c_sprache(seiten_im_entscheid(self.ollama.entscheid[0][1])))

    def test_B_antwort_hinweis_fusszeile(self):
        self.fake("B")
        self.pipe.valves.ENTSCHEIDUNG = True
        text = self.stelle("Geld")
        seiten = seiten_im_entscheid(self.ollama.entscheid[0][1])
        antwort, fuss = self.teile(text)
        self.assertEqual(antwort, "Antwort\n\nHinweis: nur teilweise belegt -- pruef "
                         + ", ".join(f"S. {s}" for s in seiten) + ".")
        self.assertTrue(fuss)
        self.assertEqual(len(self.llm_bekam), 1)

    def test_B_sprachmodus(self):
        self.fake("B")
        self.pipe.valves.ENTSCHEIDUNG = True
        text = self.stelle("Geld", sprache=True)
        seiten = seiten_im_entscheid(self.ollama.entscheid[0][1])
        self.assertEqual(text, "Antwort\n\nHinweis: nur teilweise belegt, pruef "
                         + c_sprache(seiten).split("Fundstellen: ")[1])
        self.assertNotRegex(text, r"\bS\.")

    def test_A_wie_ohne_valve(self):
        self.fake("A")
        ohne = self.stelle("Geld")
        self.pipe.valves.ENTSCHEIDUNG = True
        mit = self.stelle("Geld")
        self.assertEqual(mit, ohne)
        self.assertEqual(len(self.ollama.entscheid), 1)
        self.assertEqual(self.llm_bekam[0], self.llm_bekam[1])

    def test_optionswahl_mit_valves_und_gleichen_quellen(self):
        self.fake("A")
        self.pipe.valves.ENTSCHEIDUNG = True
        self.pipe.valves.LLM_MODEL = "gemma3:12b"
        self.stelle("Geld")
        url, payload = self.ollama.entscheid[0]
        self.assertEqual(url, "http://stub/api/chat")
        self.assertEqual(payload["model"], "gemma3:12b")
        self.assertEqual(payload["messages"][0]["content"], SYSTEM_GEMESSEN)
        quellen = self.llm_bekam[0]["messages"][-1]["content"]
        self.assertEqual(payload["messages"][1]["content"], quellen + "\n\n" + FRAGE_GEMESSEN)

    def test_valve_schlaegt_die_container_umgebung(self):
        self.fake("C")
        with mock.patch.dict(os.environ, {"ENTSCHEIDUNG": "1"}):
            self.stelle("Geld")                                  # Valve aus gegen Umgebung an
        self.assertEqual(self.ollama.entscheid, [])
        self.assertEqual(len(self.llm_bekam), 1)
        self.pipe = self.neue_pipe(ENTSCHEIDUNG=True)
        with mock.patch.dict(os.environ, {"ENTSCHEIDUNG": "0"}):
            text = self.stelle("Geld")                           # Valve an gegen Umgebung aus
        self.assertEqual(len(self.ollama.entscheid), 1)
        self.assertTrue(text.startswith("In den gefundenen Stellen steht dazu nichts."), text)
        self.assertEqual(len(self.llm_bekam), 1)                 # kein zweiter LLM-Stream

    def test_valve_setzt_rag_global(self):
        self.pipe.valves.ENTSCHEIDUNG = True
        self.assertEqual(self.pipe._rag_fuer(self.pipe.valves).ENTSCHEIDUNG, "1")
        self.pipe.valves.ENTSCHEIDUNG = False
        with mock.patch.dict(os.environ, {"ENTSCHEIDUNG": "1"}):
            self.assertEqual(self.pipe._rag_fuer(self.pipe.valves).ENTSCHEIDUNG, "0")

    def test_fehlendes_logprobs_sichtbar_ohne_stream(self):
        self.ollama = FakeOllama(antwort={"message": {"content": "A"}})
        self.post_mock.side_effect = self.ollama
        self.pipe.valves.ENTSCHEIDUNG = True
        text = self.stelle("Geld")
        self.assertIn("Fehler in der RAG-Pipe", text)
        self.assertIn("logprobs", text)
        self.assertEqual(self.llm_bekam, [])

    def test_B_hinweis_faellt_aus_dem_verlauf(self):
        self.fake("A")
        frueher = "Alte Antwort (S. 11)." + B_CHAT + self.FUSS + "S. 11 (0.900)*"
        self.stelle("Geld", verlauf=[{"role": "user", "content": "Vorher?"},
                                     {"role": "assistant", "content": frueher}])
        assistent = [m for m in self.llm_bekam[0]["messages"] if m["role"] == "assistant"]
        self.assertEqual([m["content"] for m in assistent], ["Alte Antwort (S. 11)."])


class TestPipeAlterWeg(PipeEntscheidMixin, tpipe.PipeTestBasis):
    FUSS = "\n\n---\n*Abgerufen: "

    def stelle(self, text, verlauf=(), stream=None, **rf):
        body = {"messages": list(verlauf) + [{"role": "user", "content": text}]}
        if stream is not None:
            body["stream"] = stream
        if rf:
            body["regelfrage"] = rf
        return "".join(tpipe.sammle(self.pipe.pipe(body)))

    def neue_pipe(self, **valves):
        p = op.Pipe()
        p.valves = op.Pipe.Valves(RAG_DIR=BASE, KNOWLEDGE_PATH=self.wissen, OLLAMA_URL="http://stub",
                                  TOP_K=2, DROP_TYPES="flavor", **valves)
        return p

    def test_mit_regelfrage_spiel(self):
        self.fake("C")
        self.pipe.valves.ENTSCHEIDUNG = True
        text = self.stelle("Geld", spiel="FCM", sprache=True)
        self.assertEqual(text, c_sprache(seiten_im_entscheid(self.ollama.entscheid[0][1])))
        self.assertEqual(self.llm_bekam, [])

    def test_task_ohne_optionswahl(self):
        self.fake("C")
        self.pipe.valves.ENTSCHEIDUNG = True
        text = "".join(tpipe.sammle(self.pipe.pipe({"messages": [{"role": "user", "content": "Titel"}]},
                                                   __task__="title_generation")))
        self.assertEqual(text, "Antwort")
        self.assertEqual(self.ollama.entscheid, [])


class TestPipeIndexWeg(PipeEntscheidMixin, tindex.PipeIndexBasis):
    FUSS = "\n\n---\n*Quelle: "

    def stelle(self, text, verlauf=(), stream=None, **rf):
        rf.setdefault("spiel", "FCM")
        body = {"messages": list(verlauf) + [{"role": "user", "content": text}], "regelfrage": rf}
        if stream is not None:
            body["stream"] = stream
        return "".join(tindex.sammle(self.pipe.pipe(body)))

    def neue_pipe(self, **valves):
        p = op.Pipe()
        p.valves = op.Pipe.Valves(RAG_DIR=BASE, INDEX_PATH=self.index, OLLAMA_URL="http://stub",
                                  TOP_K=2, DROP_TYPES="flavor", **valves)
        return p

    def test_C_fusszeile_nennt_das_spiel(self):
        self.fake("C")
        self.pipe.valves.ENTSCHEIDUNG = True
        text = self.stelle("Geld")
        self.assertIn("\n\n---\n*Quelle: Food Chain Magnate, Seite", text)

    def test_chat_ohne_regelfrage(self):
        self.fake("C")
        self.pipe.valves.ENTSCHEIDUNG = True
        body = {"messages": [{"role": "user", "content": "Spiel: FCM: Geld"}]}
        text = "".join(tindex.sammle(self.pipe.pipe(body)))
        self.assertTrue(text.startswith(c_chat(seiten_im_entscheid(self.ollama.entscheid[0][1]))), text)
        self.assertEqual(self.llm_bekam, [])


class TestPipeMitAltemRag(unittest.TestCase):
    def test_valve_an_ohne_entscheidung_im_rag_bricht_ab(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "rag.py"), "w", encoding="utf-8") as f:
                f.write("SYSTEM_PROMPTS = {}\n" + "".join(f"def {n}(*a, **k):\n    return None\n" for n in op._RAG_ALTER_WEG))
            p = op.Pipe()
            p.valves = op.Pipe.Valves(RAG_DIR=d, ENTSCHEIDUNG=True)
            with self.assertRaises(RuntimeError) as ctx:
                p._lade_rag(p.valves)
            self.assertIn("ENTSCHEIDUNG", str(ctx.exception))
            p.valves = op.Pipe.Valves(RAG_DIR=d)                 # aus bleibt mit altem rag.py moeglich
            self.assertIsNotNone(p._lade_rag(p.valves))


if __name__ == "__main__":
    unittest.main(verbosity=2)
