#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Praxisfragen und Ketten (zweites Golden-Set-Format) -- ohne Ollama, ohne Netz, ohne Regelheft-Text.

    python test_ketten.py

Alle Fragen und Chunks hier sind synthetisch. Geprueft wird die Wirkung:
  - Ketten werden live beantwortet wie in der Pipe (Retrieval nur auf der letzten Nachricht, Verlauf
    zwischen Systemprompt und Quellen-Frage, alte Antworten ohne Hinweis); Eval und Pipe bauen
    denselben Modell-Prompt, weil sie dieselbe Funktion benutzen (rag.setze_verlauf_ein)
  - GOLDEN_DATEI waehlt die Golden-Set-Datei; Lauf und Bewerten bleiben bei derselben Datei
  - antworten.jsonl protokolliert die Zwischenschritte, bewertet wird nur die letzte Antwort
  - vergleiche.py / rag eval schluesseln je Typ auf
Prompt des Judge: test_judge.py (TestPraxisPrompt).
"""
import contextlib
import io
import json
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
import judge  # noqa: E402
import openwebui_pipe as op  # noqa: E402
import test_eval_spiele as tes  # noqa: E402  -- Testdaten (Fake-Embedding, Chunks) und Basisklasse
import test_openwebui_pipe as top  # noqa: E402  -- Pipe-Testbasis
from messung import lauf as m_lauf  # noqa: E402
from messung import bewerte as m_bewerte  # noqa: E402
from messung import vergleiche as m_vergleiche  # noqa: E402
from messung import retrieval as m_retrieval  # noqa: E402

Q1, Q2 = "Wie verdiene ich Geld?", "und die Kette?"
KETTE = {"id": 102, "frage": Q2, "typ": "kette", "erwartet": "am Anfang", "kern": ["am Anfang"],
         "verlauf": [Q1, Q2], "seiten": [6], "beleg": {"6": "Die Kette wird am Anfang gebaut."}}
SEITE_ZU = {Q1: 11, Q2: 6}


def treffer(seite, text=None):
    return [({"doc": "doc", "seite": seite, "text": text or f"Text von Seite {seite}"}, 0.9)]


class Chat:
    """Ersetzt requests.post: Embeddings aus der Fake-Tabelle, Chat-Aufrufe werden mitgeschrieben."""

    def __init__(self, antwort=None):
        self.payloads = []
        self.antwort = antwort or (lambda n: f"Antwort {n}")

    def __call__(self, url, json=None, timeout=None):
        if url.endswith("/api/embed"):
            return top.FakeAntwort({"embeddings": tes.fake_embed(json["input"]).tolist()})
        if url.endswith("/api/chat"):
            self.payloads.append(json)
            return top.FakeAntwort({"message": {"content": self.antwort(len(self.payloads))}})
        raise AssertionError(f"unerwartete URL {url}")


class TestKetteLive(unittest.TestCase):
    """rag.antworte_frage: die Kette wird Schritt fuer Schritt vom System selbst beantwortet."""

    def setUp(self):
        self.chat = Chat()
        p = mock.patch("requests.post", side_effect=self.chat)
        p.start()
        self.addCleanup(p.stop)
        self.suchen = []

    def suche(self, q):
        self.suchen.append(q)
        return treffer(SEITE_ZU[q])          # KeyError, sobald mit etwas anderem als einer Nachricht gesucht wird

    def test_verlauf_steht_zwischen_systemprompt_und_quellen_frage(self):
        erg = rag.antworte_frage(KETTE, self.suche)
        self.assertEqual(len(self.chat.payloads), 2)
        erste, zweite = (p["messages"] for p in self.chat.payloads)
        self.assertEqual([x["role"] for x in erste], ["system", "user"])          # noch kein Verlauf
        self.assertEqual([x["role"] for x in zweite], ["system", "user", "assistant", "user"])
        self.assertEqual(zweite[1]["content"], Q1)                                 # Nutzerfrage OHNE Quellen
        self.assertEqual(zweite[2]["content"], "Antwort 1")                        # die eigene Antwort
        self.assertTrue(zweite[3]["content"].endswith(f"Frage: {Q2}"))
        self.assertIn("Text von Seite 6", zweite[3]["content"])
        self.assertNotIn("Text von Seite 11", zweite[3]["content"])                # alte Quellen gehen nicht mit
        self.assertEqual(erg["antwort"], "Antwort 2")

    def test_retrieval_nur_auf_der_jeweils_letzten_nachricht(self):
        rag.antworte_frage(KETTE, self.suche)
        self.assertEqual(self.suchen, [Q1, Q2])

    def test_zwischenschritte_werden_protokolliert(self):
        erg = rag.antworte_frage(KETTE, self.suche)
        self.assertEqual(len(erg["verlauf"]), 1)
        z = erg["verlauf"][0]
        self.assertEqual((z["frage"], z["antwort"], z["abgerufen"]), (Q1, "Antwort 1", [11]))
        self.assertEqual([h["seite"] for h, _ in erg["hits"]], [6])                # bewertet: die letzte

    def test_die_letzte_frage_wird_nicht_zweimal_beantwortet(self):
        # das Golden Set fuehrt die letzte Frage auch als letztes Element von "verlauf"
        rag.antworte_frage(KETTE, self.suche)
        self.assertEqual(len(self.chat.payloads), 2)
        self.assertEqual(rag.fruehere_fragen(KETTE), [Q1])
        # ohne die letzte Frage im Verlauf bleibt alles stehen
        self.assertEqual(rag.fruehere_fragen(dict(KETTE, verlauf=[Q1])), [Q1])
        self.assertEqual(rag.fruehere_fragen({"frage": Q1}), [])

    def test_dreistufige_kette_reicht_den_ganzen_verlauf_durch(self):
        f = dict(KETTE, verlauf=["a1?", "a2?", Q2])
        suche = lambda q: treffer(6)  # noqa: E731
        rag.antworte_frage(f, suche)
        letzte = self.chat.payloads[-1]["messages"]
        self.assertEqual([(x["role"], x["content"]) for x in letzte[1:5]],
                         [("user", "a1?"), ("assistant", "Antwort 1"), ("user", "a2?"), ("assistant", "Antwort 2")])

    def test_frage_ohne_verlauf_ist_genau_ein_retrieval_und_eine_antwort(self):
        f = {"id": 1, "frage": Q1, "typ": "fakt"}
        erg = rag.antworte_frage(f, self.suche)
        self.assertEqual((self.suchen, len(self.chat.payloads), erg["verlauf"]), ([Q1], 1, []))
        self.assertEqual([x["role"] for x in self.chat.payloads[0]["messages"]], ["system", "user"])

    def test_answer_ohne_verlaufsparameter_bleibt_moeglich(self):
        # Attrappen mit der alten Signatur (frage, hits) muessen fuer Fragen ohne Verlauf weiter greifen
        with mock.patch.object(rag, "answer", lambda frage, hits: "alt"):
            self.assertEqual(rag.antworte_frage({"frage": Q1}, self.suche)["antwort"], "alt")

    def test_suchanfrage_ist_die_stelle_fuer_die_umformulierung(self):
        self.assertEqual(rag.suchanfrage(Q2, [{"role": "user", "content": Q1}]), Q2)   # heute: unveraendert
        with mock.patch.object(rag, "suchanfrage", lambda frage, verlauf: f"[{len(verlauf)}] {frage}"):
            rag.antworte_frage(KETTE, lambda q: treffer(6))
            # gesucht wird mit der Umformulierung, beantwortet wird die echte Nutzerfrage
            letzte = self.chat.payloads[-1]["messages"][-1]["content"]
        self.assertTrue(letzte.endswith(f"Frage: {Q2}"))
        gesucht = []
        with mock.patch.object(rag, "suchanfrage", lambda frage, verlauf: f"[{len(verlauf)}] {frage}"):
            rag.antworte_frage(KETTE, lambda q: gesucht.append(q) or treffer(6))
        self.assertEqual(gesucht, [f"[0] {Q1}", f"[2] {Q2}"])


class TestHinweisImVerlauf(unittest.TestCase):
    def test_pipe_und_eval_entfernen_denselben_hinweis(self):
        hits = treffer(11) + treffer(6)
        for sprache in (False, True):
            for basis in ("Antwort", "Antwort\nmit zweiter Zeile."):
                text = basis + rag.entscheid_hinweis(hits, sprache=sprache)
                with self.subTest(sprache=sprache, basis=basis):
                    self.assertEqual(rag.verlauf_antwort(text), basis)
                    self.assertEqual(op.ohne_fusszeile(text), rag.verlauf_antwort(text))
        self.assertEqual(rag.verlauf_antwort("Der Hinweis: steht so im Text."), "Der Hinweis: steht so im Text.")

    def test_kette_mit_entscheidungsschritt_schiebt_den_hinweis_nicht_in_den_verlauf(self):
        chat = Chat()
        with mock.patch("requests.post", side_effect=chat), \
                mock.patch.object(rag, "ENTSCHEIDUNG", "1"), \
                mock.patch.object(rag, "entscheide", lambda q, h, **k: ("B", {"A": 0.1, "B": 0.8, "C": 0.1})):
            erg = rag.antworte_frage(KETTE, lambda q: treffer(SEITE_ZU[q]))
        self.assertIn(rag.ENTSCHEID_TEILWEISE, erg["verlauf"][0]["antwort"])   # protokolliert wie ausgegeben
        self.assertEqual(chat.payloads[1]["messages"][2]["content"], "Antwort 1")   # ... aber ohne Hinweis
        self.assertEqual(erg["verlauf"][0]["entscheid"][0], "B")


class TestKetteWieDiePipe(top.PipeTestBasis):
    """Dieselbe Unterhaltung durch die Pipe und durch den Eval: derselbe Prompt beim Antwortmodell."""

    def test_eval_und_pipe_schicken_dem_modell_dieselben_nachrichten(self):
        frage1, frage2 = "Wie verdiene ich Geld?", "Und die Kette dazu?"
        text1 = self.frage(frage1)
        self.assertIn("*Abgerufen:", text1)                     # die Antwort der Pipe hat eine Fusszeile ...
        self.frage(frage2, verlauf=[{"role": "user", "content": frage1},
                                    {"role": "assistant", "content": text1}])
        pipe_nachrichten = self.nachrichten(1)
        self.assertEqual(pipe_nachrichten[2], {"role": "assistant", "content": "Antwort"})   # ... im Verlauf nicht

        with mock.patch.dict(os.environ, {"SOURCE": "knowledge", "DROP_TYPES": "flavor"}), \
                mock.patch.multiple(rag, OLLAMA="http://stub", CHUNK_SIZE=400, CHUNK_OVERLAP=150), \
                mock.patch("os.path.dirname", return_value=self.tmp.name):
            chunks, embs = rag.build_index()
        aufrufe = []

        def post(url, json=None, timeout=None):
            if url.endswith("/api/chat"):
                aufrufe.append(json)
                return top.FakeAntwort({"message": {"content": "Antwort"}})
            return top.fake_post(url, json=json, timeout=timeout)
        f = {"id": 1, "frage": frage2, "typ": "kette", "verlauf": [frage1, frage2]}
        with mock.patch("requests.post", side_effect=post), mock.patch.multiple(rag, OLLAMA="http://stub"):
            rag.antworte_frage(f, lambda q: rag.retrieve(q, chunks, embs, k=2))
        self.assertEqual(aufrufe[1]["messages"], pipe_nachrichten)

    def test_pipe_benutzt_rag_setze_verlauf_ein(self):
        # keine zweite Kopie in der Pipe: ein rag.py im Mount mit anderem Einsetzen aendert, was ans Modell geht
        clone = os.path.join(self.tmp.name, "clone")
        os.makedirs(clone)
        with open(os.path.join(BASE, "rag.py"), encoding="utf-8") as f:
            quelle = f.read()
        alt = "    return nachrichten[:1] + verlauf + nachrichten[1:]"
        self.assertEqual(quelle.count(alt), 1)
        neu = '    return nachrichten[:1] + [{"role": "user", "content": "MARKE"}] + verlauf + nachrichten[1:]'
        with open(os.path.join(clone, "rag.py"), "w", encoding="utf-8") as f:
            f.write(quelle.replace(alt, neu))
        self.pipe.valves.RAG_DIR = clone
        self.frage("Und die Kette?", verlauf=[{"role": "user", "content": "Geld?"},
                                              {"role": "assistant", "content": "Antwort"}])
        self.assertEqual([x["content"] for x in self.nachrichten()[1:3]], ["MARKE", "Geld?"])


# ---------------------------------------------------------------------------
# Golden-Datei waehlbar, Lauf, Bewerten
# ---------------------------------------------------------------------------
PRAXIS_A = {"spiel_id": tes.A, "fragen": [
    {"id": 101, "frage": Q1, "typ": "ablauf", "erwartet": "Phase 4", "kern": ["Phase 4"], "zusatz": [],
     "seiten": [11], "beleg": {"11": "Geld verdient man in Phase 4."}},
    {"id": 102, "frage": Q2, "typ": "kette", "erwartet": "am Anfang", "kern": ["am Anfang"], "zusatz": [],
     "verlauf": ["Was ist mit Werbung?", Q2], "seiten": [6], "beleg": {"6": "Die Kette wird am Anfang gebaut."}},
    {"id": 103, "frage": "Gibt es einen Solo-Modus?", "typ": "leerstelle", "erwartet": "steht nicht drin",
     "kern": ["keine Angabe"], "erwartet_verweigerung": True, "seiten": [], "beleg": {}},
    {"id": 104, "frage": "Wie funktioniert der Kanal?", "typ": "leerstelle", "erwartet": "teils", "teil_leerstelle": True,
     "erwartet_verweigerung": False, "kern": ["nicht ausdruecklich geregelt"], "seiten": [6], "beleg": {}},
]}


class PraxisBasis(tes.EvalTest):
    def setUp(self):
        super().setUp()
        self.schreibe_datei(tes.A, "golden_praxis.json", PRAXIS_A)
        self.abgefragt = []

        def antwort(frage, hits, verlauf=None):
            self.abgefragt.append((frage, [(x["role"], x["content"]) for x in (verlauf or [])]))
            return "GEHEIME-ZWISCHENANTWORT" if frage == "Was ist mit Werbung?" else "Das ist am Anfang, Phase 4."
        self.antwort_patch = mock.patch.object(rag, "answer", antwort)
        self.antwort_patch.start()

    def tearDown(self):
        self.antwort_patch.stop()      # vor den Patches der Basis, sonst bleibt deren Attrappe stehen
        super().tearDown()

    def schreibe_datei(self, sid, name, inhalt):
        with open(os.path.join(self.data, sid, name), "w", encoding="utf-8") as f:
            json.dump(inhalt, f)

    def mit_datei(self, name="golden_praxis.json"):
        p = mock.patch.dict(os.environ, {"GOLDEN_DATEI": name})
        p.start()
        self.addCleanup(p.stop)


class TestGoldenDatei(PraxisBasis):
    def test_ohne_umgebungsvariable_gilt_golden_set_json(self):
        saetze, text = self.lauf(tes.A)
        self.assertEqual([s["id"] for s in saetze], [1, 2, 3, 4])
        self.assertNotIn("golden=", text)
        self.assertNotIn("je Typ", text)                       # reines Faktenset: Ausgabe wie bisher

    def test_golden_datei_waehlt_die_praxisfragen(self):
        self.mit_datei()
        saetze, text = self.lauf(tes.A)
        self.assertEqual([s["id"] for s in saetze], [101, 102, 103, 104])
        self.assertIn("golden=golden_praxis.json", text)

    def test_nur_ein_dateiname_kein_pfad(self):
        for schlecht in ("../golden_set.json", "unter/golden.json", ".."):
            with self.subTest(name=schlecht):
                with mock.patch.dict(os.environ, {"GOLDEN_DATEI": schlecht}):
                    with self.assertRaises(rag.KonfigFehler):
                        rag.golden_datei()

    def test_alle_nimmt_nur_spiele_mit_dieser_datei_und_nennt_die_uebrigen(self):
        self.mit_datei()
        saetze, text = self.lauf("--alle")
        self.assertEqual(len(saetze), 4)
        self.assertIn(f"Ohne Golden Set, nicht gewertet: {tes.B}", text)

    def test_fehlt_die_datei_beim_spiel_bricht_der_eval_ab(self):
        self.mit_datei("gibt-es-nicht.json")
        with self.assertRaises(rag.KonfigFehler):
            self.lauf(tes.A)

    def test_praxisfragen_teil_leerstelle_und_leerstelle_werden_wie_bisher_eingeordnet(self):
        self.mit_datei()
        saetze, _ = self.lauf(tes.A)
        kat = {s["id"]: s["kategorie"] for s in saetze}
        self.assertEqual(kat[103], rag.KAT_VERWEIGERUNG)       # seiten [] + erwartet_verweigerung: wie golden-v2
        self.assertEqual(kat[104], rag.KAT_GETROFFEN)          # teil_leerstelle: erwartete Seite zaehlt normal
        self.assertEqual(kat[101], rag.KAT_GETROFFEN)

    def test_kette_sucht_je_nachricht_und_wertet_nur_die_letzte(self):
        self.mit_datei()
        echt = rag.retrieve
        anfragen = []
        with mock.patch.object(rag, "retrieve", lambda q, *a, **k: anfragen.append(q) or echt(q, *a, **k)):
            saetze, _ = self.lauf(tes.A)
        self.assertEqual(anfragen, [Q1, "Was ist mit Werbung?", Q2, "Gibt es einen Solo-Modus?",
                                    "Wie funktioniert der Kanal?"])
        self.assertEqual(sum(1 for s in saetze if s["typ"] == "kette"), 1)     # genau ein Satz je Kette
        self.assertIn(("Was ist mit Werbung?", []), self.abgefragt)             # erste Antwort ohne Verlauf
        self.assertIn((Q2, [("user", "Was ist mit Werbung?"), ("assistant", "GEHEIME-ZWISCHENANTWORT")]),
                      self.abgefragt)

    def test_je_typ_aufschluesselung_im_eval(self):
        self.mit_datei()
        _, text = self.lauf(tes.A)
        block = text.split("== je Typ (Retrieval) ==")[1]
        self.assertRegex(block, r"kette\s+Fragen\s+1\s+getroffen 1/1")
        self.assertRegex(block, r"leerstelle\s+Fragen\s+2\s+getroffen 1/1")
        self.assertIn("Verweigerungsfragen 1", block)

    def test_retrieval_werkzeug_liest_die_gewaehlte_datei(self):
        self.assertEqual(m_retrieval.spiele_mit_golden_set(self.data), sorted([tes.A, tes.B]))
        self.mit_datei()
        self.assertEqual(m_retrieval.spiele_mit_golden_set(self.data), [tes.A])


def still(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*a, **k)


def lies_jsonl(pfad):
    with open(pfad, encoding="utf-8") as f:
        return [json.loads(z) for z in f if z.strip()]


class TestLaufUndBewerten(PraxisBasis):
    def setUp(self):
        super().setUp()
        self.aus = os.path.join(self.tmp.name, "lauf")

    def lauf_praxis(self):
        self.mit_datei()
        return still(m_lauf.fuehre_aus, self.aus, (tes.A,), data_dir=self.data)

    def test_meta_haelt_die_gewaehlte_datei_fest(self):
        self.lauf_praxis()
        with open(os.path.join(self.aus, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        self.assertEqual(meta["golden_datei"], "golden_praxis.json")
        self.assertEqual(meta["env"]["GOLDEN_DATEI"], "golden_praxis.json")
        aus2 = os.path.join(self.tmp.name, "lauf2")
        with mock.patch.dict(os.environ):
            os.environ.pop("GOLDEN_DATEI", None)
            still(m_lauf.fuehre_aus, aus2, (tes.A,), data_dir=self.data)
        with open(os.path.join(aus2, "meta.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["golden_datei"], "golden_set.json")

    def test_antworten_protokollieren_zwischenfragen_der_kette(self):
        n = self.lauf_praxis()
        z = {x["frage_id"]: x for x in lies_jsonl(os.path.join(self.aus, "antworten.jsonl"))}
        self.assertEqual(n, 4)                                        # eine Zeile je Golden-Frage, nicht je Antwort
        self.assertEqual(z[102]["antwort"], "Das ist am Anfang, Phase 4.")
        self.assertEqual(len(z[102]["verlauf"]), 1)
        zw = z[102]["verlauf"][0]
        self.assertEqual((zw["frage"], zw["antwort"]), ("Was ist mit Werbung?", "GEHEIME-ZWISCHENANTWORT"))
        self.assertIsInstance(zw["abgerufen"], list)
        self.assertIsInstance(zw["t_antwort"], float)
        for fid in (101, 103, 104):
            self.assertNotIn("verlauf", z[fid])                       # nur Ketten tragen den Zusatz

    def test_bewerten_nimmt_die_datei_aus_meta_und_bewertet_nur_die_letzte_antwort(self):
        self.lauf_praxis()
        prompts = []

        def modell(m, prompt, optionen, extra=None):
            prompts.append(prompt)
            return {"message": {"content": "URTEIL: richtig"}}
        with mock.patch.object(judge, "_ollama_chat", modell):
            rc = still(m_bewerte.main, ["--golden", self.data, "--modus", "frei", "--modell", "m", self.aus])
        self.assertEqual(rc, 0)
        u = {x["frage_id"]: x for x in lies_jsonl(os.path.join(self.aus, "urteile.jsonl"))}
        self.assertEqual([u[i]["typ"] for i in (101, 102, 103, 104)], ["ablauf", "kette", "leerstelle", "leerstelle"])
        kette = next(p for p in prompts if "Bisheriger Gesprächsverlauf" in p)
        self.assertIn("- Was ist mit Werbung?", kette)                # frueheren Nutzerfragen: ja
        self.assertNotIn("GEHEIME-ZWISCHENANTWORT", "".join(prompts))  # Zwischenantworten des Systems: nie
        self.assertIn("Das ist am Anfang, Phase 4.", kette)           # die letzte Antwort: ja

    def test_explizite_golden_datei_ueberstimmt_meta(self):
        self.lauf_praxis()
        with mock.patch.object(judge, "bewerte", side_effect=AssertionError("nicht erreicht")):
            rc = still(m_bewerte.main, ["--golden", self.data, "--golden-datei", "golden_set.json", self.aus])
        self.assertEqual(rc, 1)                                       # Frage 101 steht nicht in golden_set.json
        self.assertFalse(os.path.exists(os.path.join(self.aus, "urteile.jsonl")))

    def test_altes_meta_ohne_golden_datei_gilt_als_golden_set_json(self):
        self.lauf_praxis()
        with open(os.path.join(self.aus, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        del meta["golden_datei"]
        with open(os.path.join(self.aus, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)
        self.assertEqual(m_bewerte.golden_datei_des_laufs(os.path.join(self.aus, "antworten.jsonl")),
                         "golden_set.json")


# ---------------------------------------------------------------------------
# Vergleichen je Typ
# ---------------------------------------------------------------------------
# Von Hand ausgezaehlt (ein Lauf, 8 Fragen):
#   fakt   : richtig richtig falsch          -> Treffsicherheit 2/3
#   ablauf : richtig unsicher                -> 1/(2-1) = 1/1
#   kette  : falsch unsicher teilweise       -> 0/(3-1) = 0/2
#   gesamt : 3 richtig, 2 falsch, 2 unsicher, 1 teilweise -> 3/(8-2) = 3/6
TYPEN = ["fakt"] * 3 + ["ablauf"] * 2 + ["kette"] * 3
URTEILE = ["richtig", "richtig", "falsch", "richtig", "unsicher", "falsch", "unsicher", "teilweise"]


def schreibe_lauf(wurzel, name, urteile, typen=TYPEN):
    verz = os.path.join(wurzel, name)
    os.makedirs(verz)
    with open(os.path.join(verz, "urteile.jsonl"), "w", encoding="utf-8") as f:
        for i, (u, t) in enumerate(zip(urteile, typen), 1):
            z = {"spiel_id": "s", "frage_id": i, "antwort": "x", "urteil": u, "t_antwort": 1.0}
            if t:
                z["typ"] = t
            f.write(json.dumps(z) + "\n")
    return verz


class TestVergleicheJeTyp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def lauf(self, name, urteile=URTEILE, typen=TYPEN):
        return m_vergleiche.lies_lauf(schreibe_lauf(self.tmp.name, name, urteile, typen))

    def test_treffsicherheit_je_typ_von_hand_ausgezaehlt(self):
        erg = m_vergleiche.vergleiche({"A": [self.lauf("a1")]})
        s = erg["settings"]["A"]
        ts = {t: k["je_lauf"][0]["treffsicherheit"] for t, k in s["je_typ"].items()}
        self.assertEqual(ts["fakt"], {"zaehler": 2, "nenner": 3, "quote": 2 / 3})
        self.assertEqual(ts["ablauf"], {"zaehler": 1, "nenner": 1, "quote": 1.0})
        self.assertEqual(ts["kette"], {"zaehler": 0, "nenner": 2, "quote": 0.0})
        self.assertEqual(s["je_lauf"][0]["treffsicherheit"], {"zaehler": 3, "nenner": 6, "quote": 0.5})
        self.assertEqual({t: k["n"] for t, k in s["je_typ"].items()}, {"fakt": 3, "ablauf": 2, "kette": 3})

    def test_praxis_typen_schalten_die_aufschluesselung_von_selbst_ein(self):
        text = m_vergleiche.formatiere(m_vergleiche.vergleiche({"A": [self.lauf("a1")]}))
        block = text.split("-- je Typ --")[1]
        self.assertRegex(block, r"kette\s+1\s+3\s+0\s+1\s+1\s+1\s+0\s+0\.000")
        self.assertRegex(block, r"fakt\s+1\s+3\s+2\s+0\s+1\s+0\s+0\s+0\.667")

    def test_reines_faktenset_bleibt_wie_bisher_ohne_flag(self):
        fakt = self.lauf("f1", URTEILE, ["fakt"] * 8)
        self.assertNotIn("je Typ", m_vergleiche.formatiere(m_vergleiche.vergleiche({"A": [fakt]})))
        self.assertIn("-- je Typ --", m_vergleiche.formatiere(m_vergleiche.vergleiche({"A": [fakt]}, je_typ=True)))

    def test_alte_urteile_ohne_typ_zaehlen_unter_fragezeichen(self):
        alt = self.lauf("o1", URTEILE, [None] * 8)
        erg = m_vergleiche.vergleiche({"A": [alt]}, je_typ=True)
        self.assertEqual(list(erg["settings"]["A"]["je_typ"]), ["?"])
        self.assertNotIn("je Typ", m_vergleiche.formatiere(m_vergleiche.vergleiche({"A": [alt]})))

    def test_flag_je_typ_auf_der_kommandozeile(self):
        fakt = schreibe_lauf(self.tmp.name, "f2", URTEILE, ["fakt"] * 8)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(m_vergleiche.main([fakt, "--je-typ"]), 0)
        self.assertIn("-- je Typ --", out.getvalue())

    def test_min_max_je_typ_ueber_zwei_laeufe(self):
        zweit = ["richtig", "falsch", "falsch", "richtig", "richtig", "richtig", "richtig", "falsch"]
        erg = m_vergleiche.vergleiche({"A": [self.lauf("a1"), self.lauf("a2", zweit)]})
        k = erg["settings"]["A"]["je_typ"]["kette"]
        self.assertEqual((k["treffsicherheit_min"], k["treffsicherheit_max"]), (0.0, 2 / 3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
