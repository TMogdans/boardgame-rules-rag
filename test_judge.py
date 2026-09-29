#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests des Bewertungsmodells (judge.py) -- laeuft OHNE Ollama und ohne Netz.

    python test_judge.py            # oder: python -m unittest test_judge -v

Die HTTP-Aufrufe werden durch Fakes ersetzt (judge.requests.post). Die Metriken
werden an handgebauten Mengen mit von Hand ausgezaehlter Soll-Matrix geprueft.
"""
import contextlib, io, json, math, os, sys, tempfile, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judge


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
class FakeAntwort:
    def __init__(self, daten, status=200):
        self._daten, self.status_code, self.text = daten, status, json.dumps(daten)

    def json(self):
        return self._daten


def lp_antwort(tokens):
    """Ollama-Antwort mit logprobs; tokens = [(token, wahrscheinlichkeit), ...]."""
    top = [{"token": t, "logprob": math.log(p)} for t, p in tokens]
    return {"message": {"content": tokens[0][0]},
            "logprobs": [{"token": tokens[0][0], "logprob": top[0]["logprob"], "top_logprobs": top}]}


class FakeHTTP:
    """Ersetzt requests.post; merkt sich alle Aufrufe, antwortet je nach URL."""
    def __init__(self, ollama=None, anthropic=None):
        self.aufrufe, self.ollama, self.anthropic = [], ollama, anthropic

    def __call__(self, url, **kw):
        self.aufrufe.append((url, kw))
        quelle = self.anthropic if "anthropic" in url else self.ollama
        antwort = quelle(kw) if callable(quelle) else quelle
        return FakeAntwort(antwort)


FRAGE = {"id": 1, "frage": "Was kostet eine Ware?", "erwartet": "10 Dollar",
         "beleg": "Seite 11: Stueckpreis 10 Dollar", "erwartet_verweigerung": False}


def eintrag(spiel, label, urteil, fehlerart=None, strittig=False, probs=None, sek=1.0):
    return {"spiel_id": spiel, "frage_id": 1, "label": label, "urteil": urteil,
            "fehlerart": fehlerart, "strittig": strittig, "probs": probs, "sekunden": sek}


# Handgebaute Eichmenge, von Hand ausgezaehlt (Zeilen = Label, Spalten = Urteil):
#   s1: falsch/erfunden->richtig, falsch/erfunden->falsch, falsch/halb->richtig,
#       richtig->richtig, richtig->falsch, richtig->unsicher
#   s2: falsch/erfunden->falsch, falsch/halb->falsch, richtig->richtig,
#       unsicher->falsch, unsicher->unsicher, teilweise->unparsebar
#   strittig (s2): falsch/erfunden->richtig  -- darf in keiner Hauptzahl vorkommen
EICH = [
    eintrag("s1", "falsch", "richtig", "erfunden"),
    eintrag("s1", "falsch", "falsch", "erfunden"),
    eintrag("s1", "falsch", "richtig", "halbwahrheit"),
    eintrag("s1", "richtig", "richtig"),
    eintrag("s1", "richtig", "falsch"),
    eintrag("s1", "richtig", "unsicher"),
    eintrag("s2", "falsch", "falsch", "erfunden"),
    eintrag("s2", "falsch", "falsch", "halbwahrheit"),
    eintrag("s2", "richtig", "richtig"),
    eintrag("s2", "unsicher", "falsch"),
    eintrag("s2", "unsicher", "unsicher"),
    eintrag("s2", "teilweise", "unparsebar"),
    eintrag("s2", "falsch", "richtig", "erfunden", strittig=True),
]


def probs_fuer(urteil, p):
    rest = (1 - p) / 3
    return {k: (p if k == urteil else rest) for k in judge.KLASSEN}


# label, urteil, max. Wahrscheinlichkeit -- Bins/Schwellen von Hand ausgezaehlt
LP = [
    eintrag("s1", "richtig", "richtig", probs=probs_fuer("richtig", 0.98)),
    eintrag("s1", "falsch", "falsch", probs=probs_fuer("falsch", 0.95)),
    eintrag("s1", "falsch", "richtig", probs=probs_fuer("richtig", 0.92)),
    eintrag("s1", "richtig", "richtig", probs=probs_fuer("richtig", 0.75)),
    eintrag("s1", "richtig", "falsch", probs=probs_fuer("falsch", 0.75)),
    eintrag("s1", "unsicher", "unsicher", probs=probs_fuer("unsicher", 0.6)),
    eintrag("s1", "teilweise", "falsch", probs=probs_fuer("falsch", 0.4)),
]


# ---------------------------------------------------------------------------
class TestLogprobExtraktion(unittest.TestCase):
    def test_buchstaben_werden_den_klassen_zugeordnet(self):
        # vier verschiedene Massen: eine Vertauschung faellt sofort auf
        j = lp_antwort([("A", 0.4), ("B", 0.3), ("C", 0.2), ("D", 0.05)])
        probs, _ = judge.extrahiere_logprobs(j)
        self.assertAlmostEqual(probs["richtig"], 0.4 / 0.95)
        self.assertAlmostEqual(probs["teilweise"], 0.3 / 0.95)
        self.assertAlmostEqual(probs["falsch"], 0.2 / 0.95)
        self.assertAlmostEqual(probs["unsicher"], 0.05 / 0.95)

    def test_normierung_auf_summe_eins_und_restmasse(self):
        j = lp_antwort([("A", 0.4), ("B", 0.3), ("C", 0.2), ("D", 0.05)])
        probs, rest = judge.extrahiere_logprobs(j)
        self.assertAlmostEqual(sum(probs.values()), 1.0)
        self.assertAlmostEqual(rest, 0.05)

    def test_token_varianten_werden_zusammengefasst(self):
        j = lp_antwort([("A", 0.3), (" A", 0.2), ("a", 0.05), ("C", 0.2), (" C)", 0.05),
                        ("Ich", 0.1), ("\n", 0.02)])
        probs, rest = judge.extrahiere_logprobs(j)
        self.assertAlmostEqual(probs["richtig"], 0.55 / 0.80)
        self.assertAlmostEqual(probs["falsch"], 0.25 / 0.80)
        self.assertAlmostEqual(probs["teilweise"], 0.0)
        self.assertAlmostEqual(rest, 0.20)   # Ich + \n + unerfasste Masse

    def test_wort_mit_a_am_anfang_ist_kein_buchstabe(self):
        j = lp_antwort([("Aber", 0.5), ("B", 0.4)])
        probs, rest = judge.extrahiere_logprobs(j)
        self.assertAlmostEqual(probs["teilweise"], 1.0)
        self.assertAlmostEqual(rest, 0.6)   # "Aber" 0.5 + unerfasst 0.1

    def test_fehlendes_logprobs_bricht_ab(self):
        with self.assertRaises(judge.JudgeAbbruch) as cm:
            judge.extrahiere_logprobs({"message": {"content": "A"}})
        self.assertIn("logprobs", str(cm.exception))

    def test_kein_buchstabe_unter_den_top_logprobs_bricht_ab(self):
        with self.assertRaises(judge.JudgeAbbruch):
            judge.extrahiere_logprobs(lp_antwort([("Ich", 0.6), ("Die", 0.2)]))


class TestFreitextParser(unittest.TestCase):
    def test_saubere_letzte_zeile(self):
        self.assertEqual(judge.parse_urteil("Die Zahl stimmt.\nURTEIL: richtig"), "richtig")

    def test_tolerant_bei_formatierung_und_gross_klein(self):
        for text, soll in (("**URTEIL:** Teilweise.", "teilweise"),
                           ("urteil = falsch", "falsch"),
                           ("URTEIL:   `unsicher`\n", "unsicher"),
                           ("Urteil: \"Richtig\"", "richtig")):
            with self.subTest(text=text):
                self.assertEqual(judge.parse_urteil(text), soll)

    def test_letzte_urteilszeile_gilt(self):
        self.assertEqual(judge.parse_urteil("URTEIL: richtig\nAber halt:\nURTEIL: falsch"), "falsch")

    def test_think_block_wird_ignoriert(self):
        self.assertEqual(judge.parse_urteil("<think>URTEIL: falsch</think>\nURTEIL: richtig"), "richtig")

    def test_unparsebar(self):
        for text in ("", None, "Die Antwort ist korrekt.", "URTEIL: vielleicht",
                     "URTEIL: nicht richtig", "URTEIL:"):
            with self.subTest(text=text):
                self.assertEqual(judge.parse_urteil(text), judge.UNPARSEBAR)


class TestMetriken(unittest.TestCase):
    def setUp(self):
        self.m = judge.berechne_metriken(EICH)

    def test_matrix(self):
        soll = {
            "richtig":   {"richtig": 2, "teilweise": 0, "falsch": 1, "unsicher": 1, "unparsebar": 0},
            "teilweise": {"richtig": 0, "teilweise": 0, "falsch": 0, "unsicher": 0, "unparsebar": 1},
            "falsch":    {"richtig": 2, "teilweise": 0, "falsch": 3, "unsicher": 0, "unparsebar": 0},
            "unsicher":  {"richtig": 0, "teilweise": 0, "falsch": 1, "unsicher": 1, "unparsebar": 0},
        }
        self.assertEqual(self.m["matrix"], soll)

    def test_strittig_getrennt_ausgewiesen(self):
        self.assertEqual(self.m["anzahl_haupt"], 12)
        self.assertEqual(self.m["anzahl_strittig"], 1)
        self.assertEqual(self.m["matrix_strittig"]["falsch"]["richtig"], 1)
        # in den Hauptzahlen nur die 2 echten Durchgewunkenen, nicht 3
        self.assertEqual(self.m["durchgewunken"]["gesamt"]["zaehler"], 2)

    def test_durchgewunken_mit_richtigem_nenner(self):
        d = self.m["durchgewunken"]
        self.assertEqual((d["gesamt"]["zaehler"], d["gesamt"]["nenner"]), (2, 5))
        self.assertAlmostEqual(d["gesamt"]["quote"], 0.4)
        self.assertEqual((d["je_fehlerart"]["erfunden"]["zaehler"], d["je_fehlerart"]["erfunden"]["nenner"]), (1, 3))
        self.assertEqual((d["je_fehlerart"]["halbwahrheit"]["zaehler"], d["je_fehlerart"]["halbwahrheit"]["nenner"]), (1, 2))
        self.assertEqual((d["je_spiel"]["s1"]["zaehler"], d["je_spiel"]["s1"]["nenner"]), (2, 3))
        self.assertEqual((d["je_spiel"]["s2"]["zaehler"], d["je_spiel"]["s2"]["nenner"]), (0, 2))
        self.assertEqual(d["schlechtestes_spiel"]["spiel_id"], "s1")

    def test_abgelehnt_mit_richtigem_nenner(self):
        a = self.m["abgelehnt"]
        self.assertEqual((a["gesamt"]["zaehler"], a["gesamt"]["nenner"]), (1, 4))
        self.assertEqual((a["je_spiel"]["s1"]["zaehler"], a["je_spiel"]["s1"]["nenner"]), (1, 3))
        self.assertEqual((a["je_spiel"]["s2"]["zaehler"], a["je_spiel"]["s2"]["nenner"]), (0, 1))
        self.assertEqual(a["schlechtestes_spiel"]["spiel_id"], "s1")
        self.assertIn("-", a["je_fehlerart"])   # richtig-Labels ohne fehlerart

    def test_unsicher_trennung(self):
        u = self.m["unsicher_trennung"]
        z = lambda k: (u[k]["zaehler"], u[k]["nenner"])
        self.assertEqual(z("unsicher_als_falsch"), (1, 2))
        self.assertEqual(z("unsicher_als_richtig"), (0, 2))
        self.assertEqual(z("falsch_als_unsicher"), (0, 5))
        self.assertEqual(z("richtig_als_unsicher"), (1, 4))

    def test_unparsebar_zaehlt_als_fehler_und_bleibt_sichtbar(self):
        self.assertEqual((self.m["unparsebar"]["zaehler"], self.m["unparsebar"]["nenner"]), (1, 12))

    def test_leere_nenner_ergeben_none_statt_division(self):
        m = judge.berechne_metriken([eintrag("s1", "richtig", "richtig")])
        self.assertIsNone(m["durchgewunken"]["gesamt"]["quote"])
        self.assertIsNone(m["durchgewunken"]["schlechtestes_spiel"])

    def test_laufzeit_median_und_maximum(self):
        einzel = [eintrag("s1", "richtig", "richtig", sek=s) for s in (1.0, 2.0, 3.0, 40.0)]
        lz = judge.laufzeit(einzel)
        self.assertEqual((lz["median"], lz["max"], lz["n"]), (2.5, 40.0, 4))

    def test_kein_kalibrierungsblock_ohne_wahrscheinlichkeiten(self):
        self.assertNotIn("kalibrierung", self.m)


class TestKalibrierung(unittest.TestCase):
    def setUp(self):
        self.m = judge.berechne_metriken(LP)

    def test_bins(self):
        soll = {"<0.5": (1, 0), "0.5-0.7": (1, 1), "0.7-0.9": (2, 1),
                "0.9-0.97": (2, 1), ">0.97": (1, 1)}
        ist = {b["bin"]: (b["n"], b["treffer"]) for b in self.m["kalibrierung"]}
        self.assertEqual(ist, soll)

    def test_schwellen_eskalation_und_fehler_oberhalb(self):
        soll = {0.7: ((2, 7), (2, 5)), 0.8: ((4, 7), (1, 3)),
                0.9: ((4, 7), (1, 3)), 0.95: ((5, 7), (0, 2))}
        for s in self.m["schwellen"]:
            e, f = soll[s["schwelle"]]
            with self.subTest(schwelle=s["schwelle"]):
                self.assertEqual((s["eskalation"]["zaehler"], s["eskalation"]["nenner"]), e)
                self.assertEqual((s["fehler_oberhalb"]["zaehler"], s["fehler_oberhalb"]["nenner"]), f)


class TestPrompt(unittest.TestCase):
    def test_logprob_prompt_endet_mit_optionen(self):
        p = judge.baue_prompt(FRAGE, "Zehn Dollar.", "logprob")
        self.assertTrue(p.endswith("A) richtig B) teilweise C) falsch D) unsicher — antworte nur mit dem Buchstaben"))

    def test_frei_prompt_verlangt_urteilszeile(self):
        p = judge.baue_prompt(FRAGE, "Zehn Dollar.", "frei")
        self.assertIn("URTEIL: <klasse>", p)
        self.assertNotIn("antworte nur mit dem Buchstaben", p)

    def test_eingaben_erscheinen_im_prompt(self):
        f = dict(FRAGE, erwartet_verweigerung=True)
        p = judge.baue_prompt(f, "Steht nicht im Heft.", "frei")
        for teil in (f["frage"], f["erwartet"], f["beleg"], "Steht nicht im Heft."):
            self.assertIn(teil, p)
        self.assertIn("(erwartet_verweigerung): ja", p)
        self.assertIn("(erwartet_verweigerung): nein", judge.baue_prompt(FRAGE, "x", "frei"))


class TestAufrufe(unittest.TestCase):
    def test_logprob_anfrage_und_urteil(self):
        http = FakeHTTP(ollama=lp_antwort([("C", 0.7), ("A", 0.2), ("D", 0.05)]))
        with mock.patch.object(judge.requests, "post", http):
            r = judge.bewerte("logprob", "gemma3:12b-it-qat", FRAME_OK(), "Antwort")
        self.assertEqual(r["urteil"], "falsch")
        self.assertAlmostEqual(r["probs"]["falsch"], 0.7 / 0.95)
        self.assertGreaterEqual(r["sekunden"], 0)
        url, kw = http.aufrufe[0]
        self.assertTrue(url.endswith("/api/chat"))
        b = kw["json"]
        self.assertIs(b["think"], False)
        self.assertIs(b["logprobs"], True)
        self.assertEqual(b["top_logprobs"], 20)
        self.assertEqual(b["options"], {"num_predict": 1, "temperature": 0})
        self.assertEqual(b["model"], "gemma3:12b-it-qat")

    def test_logprob_ohne_logprobs_bricht_ab_ohne_freitext_fallback(self):
        http = FakeHTTP(ollama={"message": {"content": "C"}})
        with mock.patch.object(judge.requests, "post", http):
            with self.assertRaises(judge.JudgeAbbruch):
                judge.bewerte("logprob", "gemma3:12b-it-qat", FRAME_OK(), "Antwort")
        self.assertEqual(len(http.aufrufe), 1)   # kein zweiter Versuch im Freitext

    def test_frei_parst_und_verlangt_keine_logprobs(self):
        http = FakeHTTP(ollama={"message": {"content": "Passt.\nURTEIL: teilweise"}})
        with mock.patch.object(judge.requests, "post", http):
            r = judge.bewerte("frei", "m", FRAME_OK(), "Antwort")
        self.assertEqual(r["urteil"], "teilweise")
        self.assertIsNone(r["probs"])
        self.assertNotIn("logprobs", http.aufrufe[0][1]["json"])

    def test_frei_unparsebar_wird_als_kategorie_gefuehrt(self):
        http = FakeHTTP(ollama={"message": {"content": "Keine Ahnung."}})
        with mock.patch.object(judge.requests, "post", http):
            r = judge.bewerte("frei", "m", FRAME_OK(), "Antwort")
        self.assertEqual(r["urteil"], judge.UNPARSEBAR)

    def test_http_fehler_bricht_ab(self):
        def post(url, **kw):
            return FakeAntwort({"error": "model not found"}, status=404)
        with mock.patch.object(judge.requests, "post", post):
            with self.assertRaises(judge.JudgeAbbruch) as cm:
                judge.bewerte("frei", "m", FRAME_OK(), "x")
        self.assertIn("404", str(cm.exception))


def FRAME_OK():
    return dict(FRAGE)


class TestAnthropic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key_pfad = os.path.join(self.tmp.name, "api_key")

    def test_ohne_key_datei_nicht_verfuegbar_und_kein_netzaufruf(self):
        http = FakeHTTP()
        with mock.patch.object(judge, "ANTHROPIC_KEY_DATEI", self.key_pfad), \
             mock.patch.object(judge.requests, "post", http):
            with self.assertRaises(judge.ModusNichtVerfuegbar) as cm:
                judge.bewerte("anthropic", judge.ANTHROPIC_DEFAULT, FRAME_OK(), "x")
        self.assertIn("api_key", str(cm.exception))
        self.assertEqual(http.aufrufe, [])

    def test_cli_meldet_fehlenden_key_klar(self):
        err = io.StringIO()
        with mock.patch.object(judge, "ANTHROPIC_KEY_DATEI", self.key_pfad), \
             contextlib.redirect_stderr(err):
            rc = judge.main(["eichen", "--eichmenge", "gibt-es-nicht", "--golden-dir", "x",
                             "--modus", "anthropic"])
        self.assertEqual(rc, 2)
        self.assertIn("nicht verfuegbar", err.getvalue())

    def test_mit_key_aufruf_und_key_taucht_nirgends_auf(self):
        geheim = "sk-ant-GEHEIMER-TESTWERT"
        with open(self.key_pfad, "w") as f:
            f.write(geheim + "\n")
        http = FakeHTTP(anthropic={"content": [{"type": "text", "text": "ok\nURTEIL: richtig"}]})
        with mock.patch.object(judge, "ANTHROPIC_KEY_DATEI", self.key_pfad), \
             mock.patch.object(judge.requests, "post", http):
            r = judge.bewerte("anthropic", judge.ANTHROPIC_DEFAULT, FRAME_OK(), "x")
        self.assertEqual(r["urteil"], "richtig")
        url, kw = http.aufrufe[0]
        self.assertEqual(url, judge.ANTHROPIC_URL)
        self.assertEqual(kw["headers"]["x-api-key"], geheim)   # gesendet ...
        self.assertEqual(kw["json"]["model"], "claude-haiku-4-5-20251001")
        self.assertNotIn(geheim, json.dumps(r))                # ... aber nicht im Ergebnis


class TestEichlaufEndeZuEnde(unittest.TestCase):
    """Ganzer CLI-Lauf mit gefaktem Ollama: Datei rein, Datei raus."""
    def test_lauf_schreibt_einzelurteile_mit_wahrscheinlichkeit_und_laufzeit(self):
        with tempfile.TemporaryDirectory() as d:
            gd = os.path.join(d, "golden")
            os.mkdir(gd)
            with open(os.path.join(gd, "s1.korrigiert.json"), "w") as f:
                json.dump({"fragen": [FRAGE]}, f)
            eich = os.path.join(d, "eich.jsonl")
            basis = {"spiel_id": "s1", "frage_id": 1, "antwort": "Zehn Dollar.",
                     "fehlerart": None, "nennt_seite": True, "seite_korrekt": True,
                     "quelle": "test", "begruendung": "x"}
            with open(eich, "w") as f:
                f.write(json.dumps(dict(basis, label="richtig")) + "\n")
                f.write(json.dumps(dict(basis, label="falsch", fehlerart="erfunden", strittig=True)) + "\n")
            aus = os.path.join(d, "aus.json")
            http = FakeHTTP(ollama=lp_antwort([("A", 0.9), ("C", 0.05)]))
            out = io.StringIO()
            with mock.patch.object(judge.requests, "post", http), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = judge.main(["eichen", "--eichmenge", eich, "--golden-dir", gd,
                                 "--modus", "logprob", "--modell", "m", "--ausgabe", aus])
            self.assertEqual(rc, 0)
            with open(aus) as f:
                daten = json.load(f)
            self.assertEqual(len(daten["einzelurteile"]), 2)
            e0 = daten["einzelurteile"][0]
            self.assertIn("sekunden", e0)
            self.assertAlmostEqual(sum(e0["probs"].values()), 1.0)
            self.assertIn("rest", e0)
            self.assertEqual(daten["metriken"]["anzahl_strittig"], 1)
            self.assertIn("Maximum", out.getvalue())
            self.assertIn("Konfusionsmatrix", out.getvalue())

    def test_frage_id_fehlt_im_golden_set(self):
        with self.assertRaises(judge.JudgeAbbruch):
            judge.eichen([{"spiel_id": "s1", "frage_id": 99, "antwort": "x", "label": "richtig"}],
                         {"s1": {1: FRAGE}}, "frei", "m", bewerter=None)


if __name__ == "__main__":
    unittest.main()
