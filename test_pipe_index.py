#!/usr/bin/env python3
"""
Open-WebUI-Pipe auf dem Index-Weg (Valve INDEX_PATH) -- ohne Ollama, ohne Open WebUI.

    python test_pipe_index.py

Der Index wird mit der CLI-Seite (rag.aktualisiere_index) gebaut, die Pipe liest
ihn read-only -- wie im Betrieb: Host baut, Container liest. Netz-Attrappen
kommen aus test_openwebui_pipe.py.

Kern: test_pipe_gleich_cli_index_weg (gleiche Chunks, gleicher Prompt wie
`rag.py` mit spiel_id) und die Spielzuordnung gegen ALLE Spiele im Index.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import httpx

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402
import openwebui_pipe as op  # noqa: E402
from test_openwebui_pipe import fake_post, sammle, ollama_ndjson  # noqa: E402


def c(sid, name, i, seite, text, typ="regel"):
    return {"id": i, "seite": seite, "typ": typ, "text": text, "spiel": name, "spiel_id": sid}


A, AN = "food-chain-magnate", "Food Chain Magnate"
B, BN = "brass-birmingham", "Brass: Birmingham"
FCM = [c(A, AN, 1, 2, "Werbung Werbung Geld! Das beste Spiel.", "flavor"),
       c(A, AN, 2, 11, "Geld verdient man in Phase 5. Geld Geld."),
       c(A, AN, 3, 6, "Die Kette wird am Anfang gebaut."),
       c(A, AN, 4, 14, "Geld aus der Bank, Kette zahlt.")]
BRASS = [c(B, BN, 1, 41, "Geld Geld Geld Geld Geld."),
         c(B, BN, 2, 42, "Die Kette der Kanaele wird zuerst gebaut.")]


class PipeIndexBasis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = os.path.join(self.tmp.name, "data")
        self.index = os.path.join(self.data, "index.sqlite")
        self.post = mock.patch("requests.post", side_effect=fake_post)
        self.post_mock = self.post.start()
        self.spiele = {AN: (FCM, ["FCM", "Food Chain"]), BN: (BRASS, ["Brass"])}
        for name, (chunks, aliase) in self.spiele.items():
            self.lege_an(name, chunks, aliase)
        self.baue()
        self.pipe = op.Pipe()
        self.pipe.valves = op.Pipe.Valves(RAG_DIR=BASE, INDEX_PATH=self.index, OLLAMA_URL="http://stub",
                                          TOP_K=2, DROP_TYPES="flavor", CHUNK_SIZE=400, CHUNK_OVERLAP=150)
        self.llm_bekam = []
        self.llm_antwort = lambda req: httpx.Response(200, text=ollama_ndjson("Ant", "wort"))

        def handler(req):
            self.llm_bekam.append({"url": str(req.url), **json.loads(req.content)})
            return self.llm_antwort(req)
        echter_client = httpx.AsyncClient
        self.client = mock.patch.object(op.httpx, "AsyncClient",
                                        lambda **kw: echter_client(transport=httpx.MockTransport(handler), **kw))
        self.client.start()
        self.post_mock.reset_mock()

    def tearDown(self):
        self.client.stop()
        self.post.stop()
        self.tmp.cleanup()

    def lege_an(self, name, chunks, aliase=None):
        with mock.patch.object(rag, "DATA_DIR", self.data):
            meta = rag.lege_spiel_an(name, aliase=aliase)
            rag.schreibe_jsonl(rag.knowledge_pfad(meta["spiel_id"]), chunks)
        return meta

    def baue(self, **stellschrauben):
        """CLI-Seite: Index bauen (Host)."""
        werte = dict(OLLAMA="http://stub", CHUNK_SIZE=400, CHUNK_OVERLAP=150, EMBED_MODEL="bge-m3")
        werte.update(stellschrauben)
        with mock.patch.multiple(rag, DATA_DIR=self.data, INDEX_PATH=self.index, **werte):
            rag.aktualisiere_index(ausgabe=lambda *_: None)

    def frage(self, text, verlauf=(), **rf):
        body = {"messages": list(verlauf) + [{"role": "user", "content": text}]}
        if rf:
            body["regelfrage"] = rf
        return "".join(sammle(self.pipe.pipe(body)))

    def embed_aufrufe(self):
        return [x for x in self.post_mock.call_args_list if x.args[0].endswith("/api/embed")]

    def quellen(self, i=-1):
        """Texte, die im Prompt der i-ten LLM-Anfrage als Quellen standen."""
        return self.llm_bekam[i]["messages"][-1]["content"]


class TestZuordnungGegenIndex(PipeIndexBasis):
    def test_spiel_aus_dem_index_nur_dessen_quellen(self):
        text = self.frage("Geld", spiel="Brass")
        self.assertIn("S. 41 ", text)
        self.assertNotIn("S. 11 ", text)
        self.assertIn("Geld Geld Geld Geld Geld.", self.quellen())
        self.assertNotIn("Phase 5", self.quellen())
        text = self.frage("Geld", spiel="Food Chain Magnate")
        self.assertNotIn("S. 41 ", text)
        self.assertNotIn("Geld Geld Geld Geld Geld.", self.quellen())

    def test_aliase_aus_spiel_json_und_hoerfehler(self):
        for anfrage in ("FCM", "food chain", "Food Chain Magnet", "food-chain-magnate"):
            with self.subTest(anfrage=anfrage):
                self.assertIn("S. 11 ", self.frage("Geld", spiel=anfrage))
        self.assertIn("S. 41 ", self.frage("Geld", spiel="brass birmingham"))

    def test_valves_spiel_gilt_auf_dem_index_weg_nicht(self):
        self.pipe.valves.SPIEL, self.pipe.valves.SPIEL_ALIASE = "Terraforming Mars", "TM"
        self.assertIn("kein Regelheft", self.frage("Geld", spiel="TM"))
        self.assertIn("S. 11 ", self.frage("Geld", spiel="FCM"))

    def test_unbekannt_ohne_suche_und_ohne_llm(self):
        text = self.frage("Geld", spiel="Terraforming Mars")
        self.assertIn("Zu „Terraforming Mars“ habe ich kein Regelheft", text)
        self.assertIn("Verfuegbar: Brass: Birmingham, Food Chain Magnate", text)
        self.assertEqual(self.embed_aufrufe(), [])
        self.assertEqual(self.llm_bekam, [])

    def test_vorschlag_bei_aehnlichkeit(self):
        text = self.frage("Geld", spiel="Fudschein Magnat")
        self.assertIn("Meintest du Food Chain Magnate?", text)
        self.assertEqual(self.llm_bekam, [])

    def test_gemeinsamer_alias_ist_mehrdeutig(self):
        self.lege_an("Brass: Lancashire", [c("brass-lancashire", "Brass: Lancashire", 1, 7, "Geld.")], ["Brass"])
        self.baue()
        text = self.frage("Geld", spiel="Brass")
        self.assertIn("kein Regelheft", text)
        self.assertIn("Meintest du Brass: Birmingham oder Brass: Lancashire?", text)
        self.assertEqual(self.llm_bekam, [])
        self.assertIn("S. 7 ", self.frage("Geld", spiel="Brass Lancashire"))

    def test_neues_spiel_im_index_ohne_neustart(self):
        self.assertIn("kein Regelheft", self.frage("Geld", spiel="Terraforming Mars"))
        self.lege_an("Terraforming Mars", [c("terraforming-mars", "Terraforming Mars", 1, 9, "Geld ist Megacredits.")])
        self.baue()
        self.assertIn("S. 9 ", self.frage("Geld", spiel="Terraforming Mars"))


class TestOhneSpielangabe(PipeIndexBasis):
    def test_mehrere_spiele_ohne_standard_fragt_nach(self):
        text = self.frage("Geld")
        self.assertIn("Zu welchem Spiel ist die Frage?", text)
        self.assertEqual(self.embed_aufrufe(), [])
        self.assertEqual(self.llm_bekam, [])

    def test_standard_spiel(self):
        self.pipe.valves.STANDARD_SPIEL = B
        self.assertIn("S. 41 ", self.frage("Geld"))
        self.pipe.valves.STANDARD_SPIEL = "gibts-nicht"
        self.assertIn("nicht im Index", self.frage("Geld"))

    def test_einziges_spiel_braucht_keine_angabe(self):
        shutil.rmtree(os.path.join(self.data, B))
        self.baue()
        self.assertIn("S. 11 ", self.frage("Geld"))


class TestGleichheitUndStellschrauben(PipeIndexBasis):
    def test_pipe_gleich_cli_index_weg(self):
        frage = "Wie verdiene ich Geld?"
        self.frage(frage, spiel="FCM")
        with mock.patch.multiple(rag, OLLAMA="http://stub", CHUNK_SIZE=400, CHUNK_OVERLAP=150,
                                 EMBED_MODEL="bge-m3", HYBRID=False), \
             mock.patch.dict(os.environ, {"DROP_TYPES": "flavor"}):
            con = rag.oeffne_index(self.index)
            self.addCleanup(con.close)
            hits = rag.retrieve(frage, k=2, spiel_id=A, index=con)
        self.assertEqual(self.llm_bekam[0]["messages"], rag.baue_nachrichten(frage, hits))

    def test_pipe_bettet_nur_die_frage_ein(self):
        self.frage("Geld", spiel="FCM")
        self.frage("Kette", spiel="Brass")
        self.assertEqual([len(x.kwargs["json"]["input"]) for x in self.embed_aufrufe()], [1, 1])

    def test_container_umgebung_schlaegt_nicht_durch(self):
        # Open WebUI setzt CHUNK_SIZE/CHUNK_OVERLAP selbst; HYBRID koennte dort auch stehen.
        with mock.patch.dict(os.environ, {"CHUNK_SIZE": "1000", "CHUNK_OVERLAP": "100", "HYBRID": "1",
                                          "RERANK": "1"}):
            text = self.frage("Geld", spiel="FCM")
        self.assertNotIn("Fehler", text)
        self.assertFalse(self.pipe._rag.HYBRID)
        self.assertIn("S. 11 ", text)

    def test_geaenderte_valves_nach_cache_treffer(self):
        # Erst mit passendem Stand (Cache gefuellt), dann Valves ohne Stand im Index:
        # das muss auffallen, statt still den alten Cache-Eintrag weiterzuliefern.
        self.assertIn("S. 11 ", self.frage("Geld", spiel="FCM"))
        for feld, wert in (("CHUNK_SIZE", 800), ("CHUNK_OVERLAP", 100), ("EMBED_MODEL", "anderes")):
            with self.subTest(feld=feld):
                alt = getattr(self.pipe.valves, feld)
                setattr(self.pipe.valves, feld, wert)
                text = self.frage("Geld", spiel="FCM")
                self.assertIn("rag.py index food-chain-magnate", text)
                setattr(self.pipe.valves, feld, alt)

    def test_wal_index_wird_laut_abgelehnt(self):
        import sqlite3
        con = sqlite3.connect(self.index)
        self.assertEqual(con.execute("PRAGMA journal_mode=WAL").fetchone()[0], "wal")
        con.close()
        text = self.frage("Geld", spiel="FCM")
        self.assertIn("WAL-Modus", text)
        self.assertIn("journal_mode=DELETE", text)
        self.assertEqual(self.llm_bekam, [])

    def test_valves_passen_nicht_zum_index(self):
        self.pipe.valves.CHUNK_SIZE = 800
        text = self.frage("Geld", spiel="FCM")
        self.assertIn("Fehler in der RAG-Pipe", text)
        self.assertIn("rag.py index food-chain-magnate", text)
        # richtige Diagnose: kein Stand fuer diese Konfiguration -- NICHT "veraltet"
        # (die knowledge.jsonl hat sich ja nicht geaendert)
        self.assertIn("nicht im Index", text)
        self.assertNotIn("veraltet", text)
        self.assertEqual(self.llm_bekam, [])

    def test_hybrid_valve(self):
        # "Phase" kennt die Vektor-Attrappe nicht, BM25 schon (nur Seite 11):
        # reine Vektorsuche liefert [6, 14], hybrid [11, 6] -- die MENGE aendert sich.
        ohne = self.frage("Phase", spiel="FCM")
        self.assertNotIn("S. 11 ", ohne)
        self.pipe.valves.HYBRID = True
        mit = self.frage("Phase", spiel="FCM")
        self.assertNotIn("Fehler", mit)
        with mock.patch.multiple(rag, OLLAMA="http://stub", CHUNK_SIZE=400, CHUNK_OVERLAP=150,
                                 EMBED_MODEL="bge-m3", HYBRID=True), \
             mock.patch.dict(os.environ, {"DROP_TYPES": "flavor"}):
            con = rag.oeffne_index(self.index)
            self.addCleanup(con.close)
            hits = rag.retrieve("Phase", k=2, spiel_id=A, index=con)
        self.assertEqual([h["seite"] for h, _ in hits], [11, 6])
        self.assertEqual(self.llm_bekam[-1]["messages"], rag.baue_nachrichten("Phase", hits))
        self.assertIn("S. 11 ", mit)

    def test_drop_types_valve(self):
        self.pipe.valves.TOP_K = 10
        self.assertNotIn("S. 2 ", self.frage("Werbung", spiel="FCM"))
        self.pipe.valves.DROP_TYPES = ""
        self.assertIn("S. 2 ", self.frage("Werbung", spiel="FCM"))

    def test_sprache_ohne_fusszeile(self):
        self.assertEqual(self.frage("Geld", spiel="FCM", sprache=True), "Antwort")


class TestAktualitaet(PipeIndexBasis):
    def test_veralteter_index_ist_sichtbarer_fehler(self):
        self.frage("Geld", spiel="FCM")
        self.lege_an(AN, FCM + [c(A, AN, 5, 15, "Neue Regel zu Geld.")])
        text = self.frage("Geld", spiel="FCM")
        self.assertIn("veraltet", text)
        self.assertIn("python rag.py index food-chain-magnate", text)
        self.assertEqual(len(self.llm_bekam), 1)          # zweite Frage ging nicht ans LLM
        self.baue()
        self.assertIn("S. 15 ", self.frage("Geld", spiel="FCM"))

    def test_andere_spiele_bleiben_nutzbar_wenn_eines_veraltet(self):
        self.lege_an(AN, FCM + [c(A, AN, 5, 15, "Neue Regel.")])
        self.assertIn("S. 41 ", self.frage("Geld", spiel="Brass"))

    def test_nur_index_ohne_knowledge_dateien(self):
        # Wer nur die Indexdatei mountet, bekommt keine Veraltet-Pruefung, aber Antworten.
        nur = os.path.join(self.tmp.name, "nur-index")
        os.mkdir(nur)
        shutil.copy(self.index, nur)
        self.pipe.valves.INDEX_PATH = os.path.join(nur, "index.sqlite")
        self.assertIn("S. 11 ", self.frage("Geld", spiel="FCM"))
        # ohne knowledge-Dateien unterscheidet allein die spiel_id die Cache-Eintraege
        self.assertIn("S. 41 ", self.frage("Geld", spiel="Brass"))

    def test_read_only_indexdatei(self):
        os.chmod(self.index, 0o444)   # wie ein :ro-Mount; Loeschen im tearDown geht trotzdem
        self.assertIn("S. 11 ", self.frage("Geld", spiel="FCM"))

    def test_cache_je_spiel(self):
        self.pipe.valves.CACHE_SPIELE = 1
        self.assertIn("S. 11 ", self.frage("Geld", spiel="FCM"))
        self.assertIn("S. 41 ", self.frage("Geld", spiel="Brass"))
        self.assertIn("S. 11 ", self.frage("Geld", spiel="FCM"))
        self.assertEqual(len(self.pipe._spiel_cache), 1)

    def test_fehlender_index_sichtbar(self):
        self.pipe.valves.INDEX_PATH = os.path.join(self.tmp.name, "fehlt.sqlite")
        text = self.frage("Geld", spiel="FCM")
        self.assertIn("Fehler in der RAG-Pipe", text)


class TestChatVerlauf(PipeIndexBasis):
    """Chat ohne regelfrage.spiel, Spec D': Spiel nur explizit ("Spiel: X" oder Name als
    Antwort auf die Rueckfrage); die Fusszeile nennt das Spiel. Einzelregeln: test_chat.py."""

    def chat(self, *wechsel, **rf):
        """wechsel: abwechselnd Nutzer-/Assistent-Texte, der letzte ist die neue Nutzernachricht."""
        rollen = ("user", "assistant")
        msgs = [{"role": rollen[i % 2], "content": t} for i, t in enumerate(wechsel)]
        body = {"messages": msgs}
        if rf:
            body["regelfrage"] = rf
        return "".join(sammle(self.pipe.pipe(body)))

    def frage_embeds(self):
        return [x.kwargs["json"]["input"] for x in self.embed_aufrufe()]

    def test_frage_rueckfrage_name_antwort_auf_die_frage(self):
        rueckfrage = self.chat("Wie verdiene ich Geld?")
        self.assertTrue(rueckfrage.startswith("Zu welchem Spiel ist die Frage?"), rueckfrage)
        self.assertIn("„Spiel: ", rueckfrage)                     # nennt die Form als Beispiel
        self.assertEqual(self.llm_bekam, [])
        text = self.chat("Wie verdiene ich Geld?", rueckfrage, "Brass")
        self.assertIn("S. 41 ", text)
        self.assertIn("*Quelle: Brass: Birmingham, Seite", text)
        # gesucht wurde mit der eigentlichen Frage, nicht mit dem Namen
        self.assertEqual(self.frage_embeds(), [["Wie verdiene ich Geld?"]])
        n = self.llm_bekam[-1]["messages"]
        self.assertTrue(n[-1]["content"].endswith("Frage: Wie verdiene ich Geld?"))
        self.assertEqual(len(n), 2)                     # Rueckfrage-Runde geht nicht in den Verlauf
        self.assertIn("S. 11 ", self.chat("Wie verdiene ich Geld?", rueckfrage, "Food Chain Magnate bitte"))
        # keine Unschaerfe: ein Hoerfehler fuehrt erneut zur Rueckfrage
        self.assertTrue(self.chat("Wie verdiene ich Geld?", rueckfrage, "Fudschein Magnat").startswith(
            "Zu welchem Spiel ist die Frage?"))

    def test_spielname_im_freitext_legt_nichts_fest(self):
        text = self.chat("Wie verdiene ich Geld in Food Chain Magnate?")
        self.assertTrue(text.startswith("Zu welchem Spiel ist die Frage?"), text)
        self.assertEqual(self.llm_bekam, [])

    def test_spiel_x_frage(self):
        text = self.chat("Spiel: Brass: Wie viel Geld?")
        self.assertIn("S. 41 ", text)
        self.assertEqual(self.frage_embeds(), [["Wie viel Geld?"]])
        self.assertTrue(self.llm_bekam[-1]["messages"][-1]["content"].endswith("Frage: Wie viel Geld?"))

    def test_wahl_gilt_bis_zur_naechsten(self):
        a1 = "Geld gibt es in Phase 5."
        self.assertEqual(self.chat("Spiel: Food Chain Magnate"), "Ok, ab jetzt Food Chain Magnate.")
        start = ("Spiel: Food Chain Magnate", "Ok, ab jetzt Food Chain Magnate.")
        text = self.chat(*start, "Wie verdiene ich Geld?")
        self.assertIn("S. 11 ", text)
        self.assertIn("*Quelle: Food Chain Magnate, Seite", text)
        # Name in der Folgefrage oder reine Namensnachricht wechselt NICHT -- die Fusszeile zeigt FCM
        for f in ("Und bei Brass?", "Brass", "Wie viel Geld gibt es bei Brass Birmingham?"):
            with self.subTest(f=f):
                weiter = self.chat(*start, "Wie verdiene ich Geld?", a1, f)
                self.assertIn("*Quelle: Food Chain Magnate,", weiter)
                self.assertNotIn("S. 41 ", weiter)
        # explizit: nur Bestaetigung, keine Suche
        n_llm = len(self.llm_bekam)
        self.assertEqual(self.chat(*start, "Wie verdiene ich Geld?", a1, "Wechsel zu Brass"),
                         "Ok, ab jetzt Brass: Birmingham.")
        self.assertEqual(len(self.llm_bekam), n_llm)
        text = self.chat(*start, "Wie verdiene ich Geld?", a1, "Spiel Brass", "Ok, ab jetzt Brass: Birmingham.",
                         "Und wieviel Geld?")
        self.assertIn("S. 41 ", text)
        self.assertIn("*Quelle: Brass: Birmingham,", text)

    def test_fusszeile_geht_nicht_in_den_verlauf(self):
        erste = self.chat("Spiel: Food Chain Magnate: Wie verdiene ich Geld?")
        self.assertIn("*Quelle: Food Chain Magnate,", erste)
        self.chat("Spiel: Food Chain Magnate: Wie verdiene ich Geld?", erste, "Und die Kette?")
        n = self.llm_bekam[-1]["messages"]
        self.assertEqual(n[2], {"role": "assistant", "content": "Antwort"})

    def test_fusszeile_nicht_im_sprachmodus(self):
        self.assertEqual(self.frage("Geld", spiel="FCM", sprache=True), "Antwort")
        self.assertIn("*Quelle: Food Chain Magnate,", self.frage("Geld", spiel="FCM"))

    def test_standard_spiel_steht_in_der_fusszeile(self):
        self.pipe.valves.STANDARD_SPIEL = B
        self.assertIn("*Quelle: Brass: Birmingham, Seite", self.chat("Geld"))

    def test_mehrdeutig_fragt_nach(self):
        self.lege_an("Brass: Lancashire", [c("brass-lancashire", "Brass: Lancashire", 1, 7, "Geld.")], ["Brass"])
        self.baue()
        text = self.chat("Spiel: Brass: Wie viel Geld?")
        self.assertIn("Meintest du Brass: Birmingham oder Brass: Lancashire?", text)
        self.assertEqual(self.llm_bekam, [])
        self.assertIn("S. 7 ", self.chat("Spiel: Brass Lancashire: Wie viel Geld?"))
        # Antwort auf die Rueckfrage: die urspruengliche Frage wird im gewaehlten Spiel beantwortet
        text = self.chat("Spiel: Brass: Wie viel Geld?", text, "Brass: Lancashire")
        self.assertIn("S. 7 ", text)
        self.assertTrue(self.llm_bekam[-1]["messages"][-1]["content"].endswith("Frage: Wie viel Geld?"))

    def test_nur_ein_name_ohne_rueckfrage(self):
        # keine Wahl, keine Erkennung -> ohne Spiel die Rueckfrage
        self.assertTrue(self.chat("Brass").startswith("Zu welchem Spiel ist die Frage?"))
        self.assertEqual(self.llm_bekam, [])

    def test_regelfrage_feld_hat_vorrang(self):
        self.assertIn("S. 41 ", self.chat("Spiel: Food Chain Magnate: Wie verdiene ich Geld?", spiel="Brass"))

    def test_kurzer_name_kein_auffangbecken(self):
        self.lege_an("Fuji", [c("fuji", "Fuji", 1, 3, "Geld am Vulkan.")])
        self.baue()
        self.assertTrue(self.chat("Spiel: Fujian").startswith("Zu welchem Spiel ist die Frage?"))
        self.assertIn("S. 3 ", self.chat("Spiel: Fuji: Wie spielt man?"))


class TestDeployment(PipeIndexBasis):
    """Passt das rag.py im Mount nicht zur Pipe, kommt eine klare Meldung statt AttributeError."""

    def clone_mit(self, alt, neu):
        verz = os.path.join(self.tmp.name, "clone")
        os.makedirs(verz, exist_ok=True)
        with open(os.path.join(BASE, "rag.py"), encoding="utf-8") as f:
            quelle = f.read()
        self.assertEqual(quelle.count(alt), 1)
        with open(os.path.join(verz, "rag.py"), "w", encoding="utf-8") as f:
            f.write(quelle.replace(alt, neu))
        self.pipe.valves.RAG_DIR = verz

    def test_zu_alte_schnittstelle(self):
        self.clone_mit("SCHNITTSTELLE = 5", "SCHNITTSTELLE = 4")
        text = self.frage("Geld", spiel="FCM")
        self.assertIn("passt nicht zu dieser Pipe", text)
        self.assertIn("Schnittstelle 4", text)
        self.assertNotIn("AttributeError", text)

    def test_fehlende_funktion(self):
        self.clone_mit("def spiel_im_chat(nachrichten, wb):", "def _weg(nachrichten, wb):")
        text = self.frage("Geld")
        self.assertIn("fehlt: spiel_im_chat", text)
        self.assertNotIn("AttributeError", text)

    def test_fehlendes_rag_dir(self):
        self.pipe.valves.RAG_DIR = os.path.join(self.tmp.name, "gibt-es-nicht")
        text = self.frage("Geld", spiel="FCM")
        self.assertIn("rag.py nicht gefunden", text)
        self.assertNotIn("FileNotFoundError", text)


class TestKatalog(unittest.TestCase):
    def test_gleicher_name_zweimal_ist_fehler(self):
        with self.assertRaises(ValueError):
            rag.katalog_aus_index([{"spiel_id": "a", "name": "X", "aliase": []},
                                  {"spiel_id": "b", "name": "X", "aliase": []}])

    def test_unscharf_fast_gleichauf_ist_mehrdeutig(self):
        k, _ = rag.katalog_aus_index([{"spiel_id": "brass-birmingham", "name": "Brass Birmingham", "aliase": []},
                                     {"spiel_id": "brass-birminghan", "name": "Brass Birminghan", "aliase": []}])
        # "brassbirminghal" teilt mit beiden 14 Zeichen -> je 0,875
        status, vorschlaege = rag.ordne_spiel("Brass Birminghal", k)
        self.assertEqual(status, "unbekannt")
        self.assertEqual(sorted(vorschlaege), ["Brass Birmingham", "Brass Birminghan"])

    def test_unscharf_eindeutig_trifft(self):
        k, _ = rag.katalog_aus_index([{"spiel_id": "food-chain-magnate", "name": "Food Chain Magnate", "aliase": []},
                                     {"spiel_id": "brass-birmingham", "name": "Brass: Birmingham", "aliase": []}])
        self.assertEqual(rag.ordne_spiel("Food Chain Magnet", k), ("treffer", "Food Chain Magnate"))


if __name__ == "__main__":
    unittest.main()
