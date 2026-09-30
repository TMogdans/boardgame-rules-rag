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
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
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

    def test_key_nicht_in_fehlermeldungen(self):
        # Kritiker J2/J3: Netz- und HTTP-Fehler duerfen die Header (x-api-key) nicht zeigen
        geheim = "sk-ant-GEHEIMER-TESTWERT"
        with open(self.key_pfad, "w") as f:
            f.write(geheim)

        def netzfehler(url, **kw):
            raise judge.requests.ConnectionError(f"weg {kw}")

        for post in (netzfehler, lambda url, **kw: FakeAntwort({"error": "invalid x-api-key"}, status=401)):
            with self.subTest(post=post), mock.patch.object(judge, "ANTHROPIC_KEY_DATEI", self.key_pfad), \
                    mock.patch.object(judge.requests, "post", post):
                with self.assertRaises(judge.JudgeAbbruch) as cm:
                    judge.bewerte("anthropic", judge.ANTHROPIC_DEFAULT, FRAME_OK(), "x")
                self.assertNotIn(geheim, str(cm.exception))
                self.assertIn(judge.ANTHROPIC_URL, str(cm.exception))

    def test_key_nur_aus_der_datei(self):
        # Kritiker J4: ein ANTHROPIC_API_KEY in der Umgebung wird nie gelesen -- weder statt
        # der fehlenden noch statt der vorhandenen Key-Datei
        with mock.patch.dict(os.environ, ANTHROPIC_API_KEY="sk-ant-AUS-DER-UMGEBUNG"), \
                mock.patch.object(judge, "ANTHROPIC_KEY_DATEI", self.key_pfad):
            with self.assertRaises(judge.ModusNichtVerfuegbar):
                judge.lies_anthropic_key()
            with open(self.key_pfad, "w") as f:
                f.write("sk-ant-AUS-DER-DATEI")
            self.assertEqual(judge.lies_anthropic_key(), "sk-ant-AUS-DER-DATEI")


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


# ---------------------------------------------------------------------------
# kern/zusatz, falsch nicht erkannt, Tokens, Overrides
# ---------------------------------------------------------------------------
# Der Prompt fuer Fragen OHNE kern, so wie er vor der kern/zusatz-Aenderung war.
# Bewusst als Wortlaut hier hinterlegt (nicht aus judge.py abgeleitet).
ALTER_PROMPT_FREI = """\
Du bist Prüfer für ein Brettspiel-Regel-Assistenzsystem. Du bewertest eine Antwort des Systems gegen die Musterlösung aus dem Golden Set. Die Seitenangabe prüfst du nicht.

Klassen:
- richtig: inhaltlich korrekt und vollständig genug für den Spieltisch (Umformulierung, andere Sprache für Spielbegriffe, Zahlwort statt Ziffer ok). Ist laut Golden Set Verweigern richtig (erwartet_verweigerung: true), ist eine ehrliche Aussage „steht nicht im Heft“ richtig.
- teilweise: korrekt, lässt aber einen für die Entscheidung wesentlichen Teil weg (z. B. Ausnahme), ohne Falsches zu behaupten.
- falsch: enthält eine falsche Regelaussage (auch neben richtigen Teilen) oder erfindet bei einer Leerstelle eine Regel/Zahl. Vorsichtig formuliert, aber inhaltlich falsch = falsch.
- unsicher: sagt ehrlich, dass es die Antwort nicht sicher weiß/gefunden hat, ohne Falsches zu behaupten.

Frage: Was kostet eine Ware?
Erwartet (Musterlösung): 10 Dollar
Beleg aus dem Regelheft: Seite 11: Stueckpreis 10 Dollar
Verweigern ist laut Golden Set die richtige Antwort (erwartet_verweigerung): nein

Antwort des Systems:
\"\"\"
Zehn Dollar.
\"\"\"

Begründe dein Urteil kurz (höchstens fünf Sätze) und schreibe als letzte Zeile genau:
URTEIL: <klasse>
wobei <klasse> eines von richtig, teilweise, falsch, unsicher ist."""

FRAGE_KERN = dict(FRAGE, kern="10 Dollar je Ware", zusatz=["gilt nur im Basisspiel", "Rabatt ab 5 Stück"])


class TestKernZusatzPrompt(unittest.TestCase):
    def test_ohne_kern_bleibt_der_prompt_exakt_der_alte(self):
        self.assertEqual(judge.baue_prompt(FRAGE, "Zehn Dollar.", "frei"), ALTER_PROMPT_FREI)

    def test_ohne_kern_auch_mit_leerem_kern_oder_stray_zusatz(self):
        # zusatz ohne kern darf den Prompt nicht veraendern; kern="" zaehlt als nicht vorhanden
        for f in (dict(FRAGE, zusatz=["x"]), dict(FRAGE, kern=""), dict(FRAGE, kern=None, zusatz=["x"])):
            with self.subTest(f=f):
                self.assertEqual(judge.baue_prompt(f, "Zehn Dollar.", "frei"), ALTER_PROMPT_FREI)

    def test_ohne_kern_logprob_endet_wie_bisher(self):
        p = judge.baue_prompt(FRAGE, "Zehn Dollar.", "logprob")
        self.assertIn("Erwartet (Musterlösung): 10 Dollar", p)
        self.assertNotIn("Kern (", p)
        self.assertNotIn("Zusatz (", p)

    def test_mit_kern_ersetzt_erwartet_zeile(self):
        p = judge.baue_prompt(FRAGE_KERN, "Zehn Dollar.", "frei")
        self.assertNotIn("Erwartet (Musterlösung)", p)
        self.assertNotIn("Erwartet", p)
        self.assertIn("Kern (muss in der Antwort stehen, sonst höchstens teilweise): 10 Dollar je Ware\n", p)
        self.assertIn("Zusatz (darf fehlen, ohne Abzug; falsch wiedergegeben = falsch):\n"
                      "- gilt nur im Basisspiel\n- Rabatt ab 5 Stück\n", p)

    def test_zusatz_leer_oder_fehlend_ergibt_keiner(self):
        for f in (dict(FRAGE, kern="k", zusatz=[]), dict(FRAGE, kern="k")):
            with self.subTest(f=f):
                p = judge.baue_prompt(f, "x", "frei")
                self.assertIn("falsch wiedergegeben = falsch): (keiner)\n", p)

    def test_klassendefinitionen_praezisiert(self):
        p = judge.baue_prompt(FRAGE_KERN, "x", "frei")
        self.assertIn("Fehlende Zusätze sind KEIN Grund für teilweise", p)
        self.assertIn("ein falsch wiedergegebener Zusatz", p)
        self.assertIn("Der Kern steht nur unvollständig", p)
        # und die alten Definitionen sind dort NICHT mehr
        self.assertNotIn("inhaltlich korrekt und vollständig genug", p)
        self.assertNotIn("Fehlende Zusätze", judge.baue_prompt(FRAGE, "x", "frei"))

    def test_kern_prompt_behaelt_rest_und_enden(self):
        pl = judge.baue_prompt(FRAGE_KERN, "Antwort-Text", "logprob")
        pf = judge.baue_prompt(FRAGE_KERN, "Antwort-Text", "frei")
        for p in (pl, pf):
            self.assertIn(FRAGE["frage"], p)
            self.assertIn(FRAGE["beleg"], p)
            self.assertIn("Antwort-Text", p)
            self.assertIn("(erwartet_verweigerung): nein", p)
        self.assertTrue(pl.endswith("antworte nur mit dem Buchstaben"))
        self.assertIn("URTEIL: <klasse>", pf)


class TestGoldenSuffix(unittest.TestCase):
    def _golden_dir(self, d):
        gd = os.path.join(d, "golden")
        os.mkdir(gd)
        with open(os.path.join(gd, "s1.korrigiert.json"), "w") as f:
            json.dump({"fragen": [dict(FRAGE, erwartet="ALT")]}, f)
        with open(os.path.join(gd, "s1.v2.json"), "w") as f:
            json.dump({"fragen": [FRAGE_KERN]}, f)
        return gd

    def test_default_ist_korrigiert_und_suffix_waehlt_andere_datei(self):
        with tempfile.TemporaryDirectory() as d:
            gd = self._golden_dir(d)
            self.assertEqual(judge.lade_golden(gd, ["s1"])["s1"][1]["erwartet"], "ALT")
            self.assertEqual(judge.lade_golden(gd, ["s1"], ".v2.json")["s1"][1]["kern"],
                             "10 Dollar je Ware")
            with self.assertRaises(judge.JudgeAbbruch):
                judge.lade_golden(gd, ["s1"], ".gibtsnicht.json")

    def test_cli_golden_suffix_bringt_kern_in_den_gesendeten_prompt(self):
        with tempfile.TemporaryDirectory() as d:
            gd = self._golden_dir(d)
            eich = os.path.join(d, "eich.jsonl")
            with open(eich, "w") as f:
                f.write(json.dumps({"spiel_id": "s1", "frage_id": 1, "antwort": "Zehn.",
                                    "label": "richtig"}) + "\n")
            for suffix, erwartet_kern in ((None, False), (".v2.json", True)):
                http = FakeHTTP(ollama={"message": {"content": "URTEIL: richtig"}})
                argv = ["eichen", "--eichmenge", eich, "--golden-dir", gd, "--modus", "frei",
                        "--modell", "m", "--ausgabe", os.path.join(d, "aus.json")]
                if suffix:
                    argv += ["--golden-suffix", suffix]
                with mock.patch.object(judge.requests, "post", http), \
                     contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(judge.main(argv), 0)
                prompt = http.aufrufe[0][1]["json"]["messages"][0]["content"]
                with self.subTest(suffix=suffix):
                    self.assertEqual("Kern (muss in der Antwort stehen" in prompt, erwartet_kern)
                    self.assertEqual("Erwartet (Musterlösung): ALT" in prompt, not erwartet_kern)


# Falsch/richtig nicht erkannt: von Hand ausgezaehlt.
#   s1: falsch/erfunden->teilweise, falsch/erfunden->falsch, falsch/halb->richtig,
#       falsch/halb->unsicher, richtig->richtig
#   s2: falsch/halb->falsch, falsch/erfunden->unparsebar, richtig->richtig,
#       richtig->teilweise, richtig->falsch, richtig->unsicher
#   strittig (s2): falsch/erfunden->teilweise -- in keiner Hauptzahl
#   falsch nicht erkannt: 4/6 (s1 3/4, s2 1/2; erfunden 2/3, halbwahrheit 2/3)
#   durchgewunken (nur ->richtig): 1/6
#   richtig nicht erkannt: 3/5 (s1 0/1, s2 3/4); abgelehnt (->falsch): 1/5
NE = [
    eintrag("s1", "falsch", "teilweise", "erfunden"),
    eintrag("s1", "falsch", "falsch", "erfunden"),
    eintrag("s1", "falsch", "richtig", "halbwahrheit"),
    eintrag("s1", "falsch", "unsicher", "halbwahrheit"),
    eintrag("s1", "richtig", "richtig"),
    eintrag("s2", "falsch", "falsch", "halbwahrheit"),
    eintrag("s2", "falsch", "unparsebar", "erfunden"),
    eintrag("s2", "richtig", "richtig"),
    eintrag("s2", "richtig", "teilweise"),
    eintrag("s2", "richtig", "falsch"),
    eintrag("s2", "richtig", "unsicher"),
    eintrag("s2", "falsch", "teilweise", "erfunden", strittig=True),
]


class TestNichtErkannt(unittest.TestCase):
    def setUp(self):
        self.m = judge.berechne_metriken(NE)

    @staticmethod
    def z(q):
        return (q["zaehler"], q["nenner"])

    def test_falsch_nicht_erkannt_gesamt_art_spiel(self):
        d = self.m["falsch_nicht_erkannt"]
        self.assertEqual(self.z(d["gesamt"]), (4, 6))
        self.assertEqual(self.z(d["je_fehlerart"]["erfunden"]), (2, 3))
        self.assertEqual(self.z(d["je_fehlerart"]["halbwahrheit"]), (2, 3))
        self.assertEqual(self.z(d["je_spiel"]["s1"]), (3, 4))
        self.assertEqual(self.z(d["je_spiel"]["s2"]), (1, 2))
        self.assertEqual(d["schlechtestes_spiel"]["spiel_id"], "s1")
        self.assertAlmostEqual(d["schlechtestes_spiel"]["quote"], 0.75)

    def test_unterscheidet_sich_von_durchgewunken(self):
        # Der Sinn der Kennzahl: teilweise/unsicher/unparsebar mildern ab, ohne durchzuwinken.
        self.assertEqual(self.z(self.m["durchgewunken"]["gesamt"]), (1, 6))
        self.assertEqual(self.z(self.m["falsch_nicht_erkannt"]["gesamt"]), (4, 6))

    def test_richtig_nicht_erkannt(self):
        d = self.m["richtig_nicht_erkannt"]
        self.assertEqual(self.z(d["gesamt"]), (3, 5))
        self.assertEqual(self.z(d["je_spiel"]["s1"]), (0, 1))
        self.assertEqual(self.z(d["je_spiel"]["s2"]), (3, 4))
        self.assertEqual(d["schlechtestes_spiel"]["spiel_id"], "s2")
        self.assertEqual(self.z(self.m["abgelehnt"]["gesamt"]), (1, 5))

    def test_strittig_zaehlt_nicht_mit(self):
        self.assertEqual(self.m["falsch_nicht_erkannt"]["gesamt"]["nenner"], 6)

    def test_leerer_nenner_und_ausgabe(self):
        m = judge.berechne_metriken([eintrag("s1", "unsicher", "unsicher")])
        self.assertIsNone(m["falsch_nicht_erkannt"]["gesamt"]["quote"])
        self.assertIsNone(m["richtig_nicht_erkannt"]["schlechtestes_spiel"])
        text = judge.formatiere(self.m, "frei", "m")
        self.assertIn("Falsch nicht erkannt (falsch, Urteil != falsch): 66.7% (4/6)", text)
        self.assertIn("Richtig nicht erkannt (richtig, Urteil != richtig): 60.0% (3/5)", text)
        self.assertIn("Durchgewunken (falsch als richtig): 16.7% (1/6)", text)


# Tokens: Eingabe 1000/2000/6000, Ausgabe 10/20/90
#   Summe 9000 / 120; typisch (Median) 2000 / 20; Maximum 6000 / 90
#   Kosten je Aufruf (1 $/MTok ein, 5 $/MTok aus): 0.00105, 0.0021, 0.00645; Summe 0.0096
def tok(spiel, i, o, label="richtig", urteil="richtig"):
    return dict(eintrag(spiel, label, urteil), input_tokens=i, output_tokens=o)


TOK = [tok("s1", 1000, 10), tok("s1", 2000, 20), tok("s2", 6000, 90, "falsch", "falsch")]


class TestTokens(unittest.TestCase):
    def test_summen_typisch_maximum(self):
        t = judge.berechne_metriken(TOK)["tokens"]
        self.assertEqual((t["input_summe"], t["output_summe"]), (9000, 120))
        self.assertEqual((t["input_typisch"], t["output_typisch"]), (2000, 20))
        self.assertEqual((t["input_max"], t["output_max"]), (6000, 90))
        self.assertEqual((t["n"], t["aufrufe_gesamt"]), (3, 3))

    def test_kosten_aus_konstanten(self):
        self.assertEqual((judge.PREIS_INPUT_USD_MTOK, judge.PREIS_OUTPUT_USD_MTOK), (1.0, 5.0))
        t = judge.berechne_metriken(TOK)["tokens"]
        self.assertAlmostEqual(t["kosten_usd_summe"], 0.0096)
        self.assertAlmostEqual(t["kosten_usd_typisch"], 0.0021)
        self.assertAlmostEqual(t["kosten_usd_max"], 0.00645)
        with mock.patch.object(judge, "PREIS_INPUT_USD_MTOK", 3.0), \
             mock.patch.object(judge, "PREIS_OUTPUT_USD_MTOK", 15.0):
            self.assertAlmostEqual(judge.berechne_metriken(TOK)["tokens"]["kosten_usd_summe"], 0.0288)

    def test_strittige_aufrufe_kosten_trotzdem(self):
        # Kosten fallen an, auch wenn der Eintrag aus den Hauptzahlen faellt
        einzel = TOK + [dict(tok("s1", 4000, 40), strittig=True)]
        t = judge.berechne_metriken(einzel)["tokens"]
        self.assertEqual(t["input_summe"], 13000)

    def test_ohne_usage_kein_tokenblock(self):
        self.assertNotIn("tokens", judge.berechne_metriken(EICH))
        self.assertNotIn("tokens", judge.berechne_metriken(LP))

    def test_teilweise_fehlende_usage_wird_offen_ausgewiesen(self):
        einzel = TOK + [eintrag("s1", "richtig", "richtig")]
        t = judge.berechne_metriken(einzel)["tokens"]
        self.assertEqual((t["n"], t["aufrufe_gesamt"]), (3, 4))
        self.assertEqual(t["input_summe"], 9000)

    def test_ausgabe_nennt_typisch_maximum_summe_und_preise(self):
        text = judge.formatiere(judge.berechne_metriken(TOK), "anthropic", "m")
        self.assertIn("Input 9000, Output 120", text)
        self.assertIn("typisch (Median) 2000, Maximum 6000", text)
        self.assertIn("typisch (Median) 20, Maximum 90", text)
        self.assertIn("Stand 2026-09", text)
        self.assertIn("Summe $0.0096", text)
        self.assertNotIn("Tokens (", judge.formatiere(judge.berechne_metriken(EICH), "frei", "m"))

    def test_anthropic_aufruf_liefert_usage(self):
        with tempfile.TemporaryDirectory() as d:
            kp = os.path.join(d, "api_key")
            with open(kp, "w") as f:
                f.write("sk-test\n")
            http = FakeHTTP(anthropic={"content": [{"type": "text", "text": "URTEIL: falsch"}],
                                       "usage": {"input_tokens": 812, "output_tokens": 37}})
            with mock.patch.object(judge, "ANTHROPIC_KEY_DATEI", kp), \
                 mock.patch.object(judge.requests, "post", http):
                r = judge.bewerte("anthropic", judge.ANTHROPIC_DEFAULT, FRAME_OK(), "x")
        self.assertEqual((r["input_tokens"], r["output_tokens"]), (812, 37))

    def test_ollama_modi_haben_keine_tokens(self):
        http = FakeHTTP(ollama={"message": {"content": "URTEIL: richtig"}})
        with mock.patch.object(judge.requests, "post", http):
            r = judge.bewerte("frei", "m", FRAME_OK(), "x")
        self.assertIsNone(r.get("input_tokens"))

    def test_cli_anthropic_lauf_summiert_tokens_in_datei(self):
        with tempfile.TemporaryDirectory() as d:
            kp = os.path.join(d, "api_key")
            with open(kp, "w") as f:
                f.write("sk-test\n")
            gd = os.path.join(d, "golden")
            os.mkdir(gd)
            with open(os.path.join(gd, "s1.korrigiert.json"), "w") as f:
                json.dump({"fragen": [FRAGE]}, f)
            eich = os.path.join(d, "eich.jsonl")
            with open(eich, "w") as f:
                for _ in range(3):
                    f.write(json.dumps({"spiel_id": "s1", "frage_id": 1, "antwort": "x",
                                        "label": "richtig"}) + "\n")
            usages = iter([(1000, 10), (2000, 20), (6000, 90)])

            def anthropic(kw):
                i, o = next(usages)
                return {"content": [{"type": "text", "text": "URTEIL: richtig"}],
                        "usage": {"input_tokens": i, "output_tokens": o}}
            aus = os.path.join(d, "aus.json")
            out = io.StringIO()
            with mock.patch.object(judge, "ANTHROPIC_KEY_DATEI", kp), \
                 mock.patch.object(judge.requests, "post", FakeHTTP(anthropic=anthropic)), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = judge.main(["eichen", "--eichmenge", eich, "--golden-dir", gd,
                                 "--modus", "anthropic", "--ausgabe", aus])
            self.assertEqual(rc, 0)
            with open(aus) as f:
                daten = json.load(f)
            self.assertEqual([(e["input_tokens"], e["output_tokens"]) for e in daten["einzelurteile"]],
                             [(1000, 10), (2000, 20), (6000, 90)])
            t = daten["metriken"]["tokens"]
            self.assertEqual((t["input_summe"], t["output_summe"]), (9000, 120))
            self.assertAlmostEqual(t["kosten_usd_summe"], 0.0096)
            self.assertIn("Kosten", out.getvalue())


class TestOverrides(unittest.TestCase):
    BASIS = [
        {"spiel_id": "s1", "frage_id": 1, "antwort": "a0", "label": "falsch", "fehlerart": "erfunden"},
        {"spiel_id": "s1", "frage_id": 1, "antwort": "a1", "label": "falsch", "fehlerart": "halbwahrheit"},
        {"spiel_id": "s1", "frage_id": 1, "antwort": "a2", "label": "richtig", "fehlerart": None},
    ]

    def test_ueberschreibt_genau_die_genannte_zeile_null_basiert(self):
        neu = judge.wende_overrides(self.BASIS, [{"zeile": 1, "neu": "teilweise"}])
        self.assertEqual([e["label"] for e in neu], ["falsch", "teilweise", "richtig"])
        self.assertEqual(neu[1]["label_original"], "falsch")
        self.assertTrue(neu[1]["override"])
        for i in (0, 2):
            self.assertNotIn("override", neu[i])
            self.assertNotIn("label_original", neu[i])

    def test_eingabe_bleibt_unveraendert(self):
        vorher = json.dumps(self.BASIS)
        judge.wende_overrides(self.BASIS, [{"zeile": 0, "neu": "richtig"}])
        self.assertEqual(json.dumps(self.BASIS), vorher)

    def test_fehlerart_entfaellt_wenn_neues_label_nicht_falsch(self):
        neu = judge.wende_overrides(self.BASIS, [{"zeile": 0, "neu": "richtig"},
                                                 {"zeile": 2, "neu": "falsch", "fehlerart": "erfunden"}])
        self.assertIsNone(neu[0]["fehlerart"])
        self.assertEqual(neu[2]["fehlerart"], "erfunden")

    def test_ungueltige_overrides_brechen_ab(self):
        for ov in ([{"zeile": 3, "neu": "falsch"}], [{"zeile": -1, "neu": "falsch"}],
                   [{"zeile": 0, "neu": "falsch"}, {"zeile": 0, "neu": "richtig"}]):
            with self.subTest(ov=ov), self.assertRaises(judge.JudgeAbbruch):
                judge.wende_overrides(self.BASIS, ov)

    def test_lade_overrides_prueft_label_und_zeile(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "ov.jsonl")
            for inhalt in ('{"zeile": 0, "neu": "vielleicht"}\n', '{"zeile": "0", "neu": "falsch"}\n'):
                with open(p, "w") as f:
                    f.write(inhalt)
                with self.subTest(inhalt=inhalt), self.assertRaises(judge.JudgeAbbruch):
                    judge.lade_overrides(p)
            with open(p, "w") as f:
                f.write('{"zeile": 2, "neu": "teilweise"}\n\n')
            self.assertEqual(judge.lade_overrides(p), [{"zeile": 2, "neu": "teilweise"}])

    def _lauf(self, d, overrides, extra=()):
        gd = os.path.join(d, "golden")
        os.makedirs(gd, exist_ok=True)
        with open(os.path.join(gd, "s1.korrigiert.json"), "w") as f:
            json.dump({"fragen": [FRAGE]}, f)
        eich = os.path.join(d, "eich.jsonl")
        with open(eich, "w") as f:
            for e in self.BASIS:
                f.write(json.dumps(e) + "\n")
        ov = os.path.join(d, "ov.jsonl")
        with open(ov, "w") as f:
            for o in overrides:
                f.write(json.dumps(o) + "\n")
        aus = os.path.join(d, "aus.json")
        http = FakeHTTP(ollama={"message": {"content": "URTEIL: richtig"}})
        out = io.StringIO()
        with mock.patch.object(judge.requests, "post", http), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            rc = judge.main(["eichen", "--eichmenge", eich, "--golden-dir", gd, "--modus", "frei",
                             "--modell", "m", "--ausgabe", aus, "--eichmenge-overrides", ov, *extra])
        with open(eich) as f:
            eich_danach = f.read()
        with open(aus) as f:
            return rc, json.load(f), out.getvalue(), eich_danach, [json.dumps(e) + "\n" for e in self.BASIS]

    def test_cli_override_wirkt_im_lauf_und_wird_vermerkt(self):
        with tempfile.TemporaryDirectory() as d:
            rc, daten, out, eich_danach, eich_vorher = self._lauf(d, [{"zeile": 1, "neu": "richtig"}])
        self.assertEqual(rc, 0)
        e = daten["einzelurteile"]
        self.assertEqual([x["label"] for x in e], ["falsch", "richtig", "richtig"])
        self.assertTrue(e[1]["override"])
        self.assertEqual(e[1]["label_original"], "falsch")
        self.assertNotIn("override", e[0])
        self.assertEqual(daten["overrides"], [{"zeile": 1, "neu": "richtig"}])
        # Fake-Judge sagt immer richtig: falsch-Labels = nur noch Zeile 0
        self.assertEqual(daten["metriken"]["durchgewunken"]["gesamt"]["nenner"], 1)
        self.assertIn("Overrides: 1 Label(s)", out)
        self.assertEqual(eich_danach, "".join(eich_vorher))   # Eichmenge unangetastet

    def test_cli_zeilennummer_gilt_fuer_die_datei_auch_mit_limit(self):
        with tempfile.TemporaryDirectory() as d:
            rc, daten, _, _, _ = self._lauf(d, [{"zeile": 0, "neu": "unsicher"}], extra=("--limit", "2"))
        self.assertEqual(rc, 0)
        self.assertEqual([x["label"] for x in daten["einzelurteile"]], ["unsicher", "falsch"])

    def test_cli_override_hinter_dem_limit_ist_gueltig(self):
        # Zeile 2 existiert in der Datei; --limit schneidet erst danach ab (kein Abbruch)
        with tempfile.TemporaryDirectory() as d:
            rc, daten, _, _, _ = self._lauf(d, [{"zeile": 2, "neu": "falsch"}], extra=("--limit", "2"))
        self.assertEqual(rc, 0)
        self.assertEqual(len(daten["einzelurteile"]), 2)



# ---------------------------------------------------------------------------
# Deterministische Vorstufe: feste Verweigerungssaetze ohne Modell
# ---------------------------------------------------------------------------
FRAGE_VERW = dict(FRAGE, erwartet_verweigerung=True)
# Wortlaut der erkannten Formen (nicht aus judge.py abgeleitet)
FESTE_ANTWORTEN = (
    "Dazu enthaelt das Dokument keine Angaben.",
    "In den gefundenen Stellen steht das nicht eindeutig.",
    "In den gefundenen Stellen steht das nicht eindeutig. Schau auf Seite 14 nach.",
    "In den gefundenen Stellen steht dazu nichts.",
    "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: S. 14, S. 12, S. 4.",
    "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: S. 14.",
    "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: Seite 14.",
    "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: Seite 14 und Seite 12.",
    "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: Seite 14, Seite 12 und Seite 4.",
    "Dazu enthaelt das Dokument keine Angaben. Naechste Fundstellen: S. 3, S. 5.",
)
# Antworten mit weiterem Inhalt: duerfen NICHT deterministisch gewertet werden
MIT_ZUSATZ = (
    "In den gefundenen Stellen steht dazu nichts. Es sind aber 5 Karten.",
    "Man zieht 3 Karten. In den gefundenen Stellen steht dazu nichts.",
    "Zehn Dollar. Dazu enthaelt das Dokument keine Angaben.",
    "Dazu enthaelt das Dokument keine Angaben. Die Regel lautet: 10 Dollar.",
    "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: S. 14. Es sind 5.",
    "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: S. 14 und S. 12.",
    "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: Seite 14 Seite 12.",
    "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: S. 14, Seite 12.",
    "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen:",
    "Dazu enthaelt das Dokument keine Angaben. Schau auf Seite 14 nach.",
    "Antwort.\n\nHinweis: nur teilweise belegt -- pruef S. 14.",
    "In den gefundenen Stellen steht dazu nichts. Hinweis: nur teilweise belegt.",
    "",
)


class TestVorstufe(unittest.TestCase):
    def _bewerte_ohne_netz(self, modus, frage, antwort):
        http = FakeHTTP()
        with mock.patch.object(judge.requests, "post", http):
            r = judge.bewerte(modus, "m", frage, antwort)
        return r, http

    def test_feste_saetze_richtig_bei_verweigerung_in_allen_modi_ohne_modellaufruf(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        key = os.path.join(tmp.name, "api_key")   # bewusst: keine Key-Datei noetig
        for modus in ("logprob", "frei", "anthropic"):
            for a in FESTE_ANTWORTEN:
                with self.subTest(modus=modus, antwort=a), \
                     mock.patch.object(judge, "ANTHROPIC_KEY_DATEI", key):
                    r, http = self._bewerte_ohne_netz(modus, FRAGE_VERW, a)
                    self.assertEqual(r["urteil"], "richtig")
                    self.assertEqual(http.aufrufe, [])
                    self.assertIs(r["deterministisch"], True)
                    self.assertEqual(r["rohtext"], "fester Verweigerungssatz")
                    self.assertEqual((r["input_tokens"], r["output_tokens"]), (0, 0))
                    self.assertLess(r["sekunden"], 0.01)

    def test_feste_saetze_unsicher_wenn_antwort_im_heft_steht(self):
        for a in FESTE_ANTWORTEN:
            with self.subTest(antwort=a):
                r, http = self._bewerte_ohne_netz("frei", FRAGE, a)
                self.assertEqual(r["urteil"], "unsicher")
                self.assertEqual(http.aufrufe, [])
                self.assertIs(r["deterministisch"], True)
        # fehlt erwartet_verweigerung ganz, gilt es als "nein"
        r, _ = self._bewerte_ohne_netz("frei", {"frage": "?"}, FESTE_ANTWORTEN[0])
        self.assertEqual(r["urteil"], "unsicher")

    def test_normalisierung_gross_klein_whitespace_umlaute(self):
        varianten = (
            "  DAZU ENTHAELT DAS DOKUMENT KEINE ANGABEN.  ",
            "dazu enthält das dokument keine angaben.",
            "Dazu enthaelt das\n  Dokument\tkeine Angaben.\n",
            "In den gefundenen Stellen steht dazu nichts.\n\nNaechste Fundstellen: S. 14,\nS. 12.",
            "In den gefundenen Stellen steht dazu nichts. Nächste Fundstellen: S. 14.",
            "In den gefundenen Stellen steht dazu nichts. NAECHSTE FUNDSTELLEN: SEITE 14 UND SEITE 12.",
            "In den gefundenen Stellen steht das nicht eindeutig. Schau auf Seite 7 nach.",
        )
        for a in varianten:
            with self.subTest(antwort=a):
                r, http = self._bewerte_ohne_netz("frei", FRAGE_VERW, a)
                self.assertEqual(r["urteil"], "richtig")
                self.assertEqual(http.aufrufe, [])
        # ss/ß und oe/ö, ue/ü gelten gleich (Normalisierung beidseitig)
        self.assertEqual(judge._normalisiere("Straße Größe Fuß für Mönch"),
                         judge._normalisiere("Strasse Groesse Fuss fuer Moench"))

    def test_zusatzinhalt_geht_ans_modell(self):
        for a in MIT_ZUSATZ:
            with self.subTest(antwort=a):
                http = FakeHTTP(ollama={"message": {"content": "Passt.\nURTEIL: falsch"}})
                with mock.patch.object(judge.requests, "post", http):
                    r = judge.bewerte("frei", "m", FRAGE_VERW, a)
                self.assertEqual(len(http.aufrufe), 1)
                self.assertEqual(r["urteil"], "falsch")
                self.assertNotIn("deterministisch", r)

    def test_anthropic_fragt_das_modell_nur_bei_zusatz(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        key = os.path.join(tmp.name, "api_key")
        with open(key, "w") as f:
            f.write("sk-test\n")
        antwort = {"content": [{"type": "text", "text": "URTEIL: richtig"}],
                   "usage": {"input_tokens": 100, "output_tokens": 10}}
        http = FakeHTTP(anthropic=antwort)
        with mock.patch.object(judge, "ANTHROPIC_KEY_DATEI", key), \
             mock.patch.object(judge.requests, "post", http):
            judge.bewerte("anthropic", "m", FRAGE_VERW, FESTE_ANTWORTEN[3])
            self.assertEqual(http.aufrufe, [])
            r = judge.bewerte("anthropic", "m", FRAGE_VERW, MIT_ZUSATZ[0])
        self.assertEqual(len(http.aufrufe), 1)
        self.assertEqual(r["urteil"], "richtig")

    def test_satzliste_stimmt_mit_rag_ueberein(self):
        """Wirkung, nicht Quelltext: rags Funktionen erzeugen die festen Texte, judge wertet sie
        deterministisch -- C-Text in Chat- und Sprachform, bei 0, 1 und mehreren Seiten."""
        import rag
        hitsets = ([], [({"seite": 14}, 0.5)],
                   [({"seite": 14}, 0.5), ({"seite": 12}, 0.4), ({"seite": 14}, 0.3), ({"seite": 4}, 0.2)])
        for hits in hitsets:
            for sprache in (False, True):
                text = rag.entscheid_text_nichts(hits, sprache=sprache)
                with self.subTest(text=text):
                    r, http = self._bewerte_ohne_netz("frei", FRAGE_VERW, text)
                    self.assertEqual(r["urteil"], "richtig")
                    self.assertEqual(http.aufrufe, [])
        # der B-Hinweis hinter einer Antwort ist kein reiner Verweigerungssatz -> Modell
        b = "Zehn Dollar." + rag.entscheid_hinweis(hitsets[1])
        self.assertFalse(judge.ist_fester_verweigerungssatz(b))
        # die v2-Saetze der Eval und der v1-Satz aus dem Prompt werden deterministisch gewertet
        for satz in rag.VERWEIGERUNGS_SAETZE:
            self.assertTrue(judge.ist_fester_verweigerungssatz(satz + "."), satz)
        self.assertTrue(judge.ist_fester_verweigerungssatz("Dazu enthaelt das Dokument keine Angaben."))
        self.assertIn('"Dazu enthaelt das Dokument keine Angaben."', rag.SYSTEM_PROMPTS["v1"])

    def test_eichlauf_nutzt_vorstufe_und_metriken_weisen_sie_aus(self):
        eintraege = [
            {"spiel_id": "s1", "frage_id": 1, "antwort": FESTE_ANTWORTEN[4], "label": "richtig"},
            {"spiel_id": "s1", "frage_id": 1, "antwort": "Zehn Dollar.", "label": "richtig"},
            {"spiel_id": "s1", "frage_id": 2, "antwort": FESTE_ANTWORTEN[0], "label": "unsicher"},
        ]
        golden = {"s1": {1: FRAGE_VERW, 2: dict(FRAGE, id=2)}}
        http = FakeHTTP(ollama=lp_antwort([("A", 0.9), ("C", 0.05)]))
        with mock.patch.object(judge.requests, "post", http):
            einzel = judge.eichen(eintraege, golden, "logprob", "m")
        self.assertEqual(len(http.aufrufe), 1)   # nur die Antwort mit Inhalt
        self.assertEqual([u["urteil"] for u in einzel], ["richtig", "richtig", "unsicher"])
        self.assertEqual([bool(u.get("deterministisch")) for u in einzel], [True, False, True])
        m = judge.berechne_metriken(einzel)
        self.assertEqual((m["deterministisch"]["zaehler"], m["deterministisch"]["nenner"]), (2, 3))
        # Laufzeit zaehlt nur den echten Modellaufruf
        self.assertEqual(m["laufzeit"]["n"], 1)
        self.assertIn("Deterministisch", judge.formatiere(m, "logprob", "m"))

    def test_metriken_ohne_deterministische_urteile(self):
        m = judge.berechne_metriken([eintrag("s1", "richtig", "richtig")])
        self.assertEqual((m["deterministisch"]["zaehler"], m["deterministisch"]["nenner"]), (0, 1))

    def test_tokens_mitteln_nicht_ueber_deterministische_nullen(self):
        einzel = [tok("s1", 100, 10), tok("s1", 300, 30),
                  dict(tok("s1", 0, 0), deterministisch=True, sekunden=0.0)]
        t = judge.berechne_metriken(einzel)["tokens"]
        self.assertEqual(t["n"], 2)
        self.assertEqual(t["aufrufe_gesamt"], 3)
        self.assertEqual(t["input_typisch"], 200)


if __name__ == "__main__":
    unittest.main()
