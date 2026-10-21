#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mehr-Buecher-Bestand (Spec .specify/specs/mehrbuch-bestand/spec.md) -- Datenmodell, Filter,
Fassungsregel, Fundstelle, Messung, Ersetzen/Inkrementell, Schutz, Performance.

    python test_mehrbuch.py

Spec-PR: jeder Test ist einzeln mit @unittest.skip("devloop: REQ-MB-<n> ...") markiert und
traegt [REQ-MB-<n>] in der ersten Docstring-Zeile. implement entfernt NUR das skip.

Testdaten ausschliesslich synthetisch (REQ-MB-17/-18): Bestand "testwelt", Fassungen
alpha/beta/gamma, kein Lesen von DATA_DIR-Inhalten oder echten PDFs.

Embeddings kommen aus festen Themenachsen ueber eine requests.post-Attrappe -- dieselbe fuer
rag.py und fuer das rag.py, das die Pipe selbst laedt. Gezaehlt wird, was WIRKLICH an
/api/embed geht (Wirkung), nicht ein Etikett.

Vom Test erwartete Schnittstellen (aus der Spec abgeleitet, Namen hier festgelegt):
  spiel.json  "buecher": [{"buch_id", "titel", "fassung", "sprache", "quelle", "inhaltsart",
                           "inhaltsarten": [{"praefix": [...], "inhaltsart": ...}], ...}]
              "fassungsregeln": {<inhaltsart>: {"massgeblich": [<fassung>, ...],
                                                "gekennzeichnet": {<fassung>: <Hinweistext>}}}
  data/<spiel_id>/buecher/<buch_id>/knowledge.jsonl   (REQ-MB-1, Pfad aus der Spec)
              Eintrag: {"id", "seite", "text", "typ", "spiel", "spiel_id", "buch_id",
                        "abschnittspfad": [...]}  -- wie heute plus buch_id/abschnittspfad
  Tabelle chunks: Spalten buch_id, fassung, sprache, seite, abschnittspfad (JSON), inhaltsart
  rag.lade_spiel -> Chunks mit buch_id, fassung, sprache, seite, abschnittspfad, inhaltsart
  rag.lies_buecher(spiel_id, data_dir=None) -> [ {"buch_id": ...}, ... ]
  rag.retrieve(..., filter={"buch_id"|"fassung"|"sprache"|"inhaltsart": wert, ...})
  rag.fundstelle(chunk) -> str        Kopf/Fusszeile/Entscheid-Seiten (REQ-MB-6, -21, -22)
  rag.fassungs_hinweis(chunk) -> str  Hinweis gekennzeichneter Fassungen, sonst "" (REQ-MB-21)
  golden_set.json eines Mehr-Buecher-Bestands: "seiten": [{"buch_id": ..., "seite": n}]
  einlesen.lies_buch_ein(...)         siehe test_einlesen_reparatur.py
  .specify/specs/mehrbuch-bestand/vorabmessung.json   (REQ-MB-23)
  Pipe: veralteter Mehr-Buecher-Bestand (irgendeine Buchdatei nach dem Bau geaendert) -> Meldung
        mit "veraltet", kein LLM-Aufruf (REQ-MB-26)
  REQ-MB-19 Basis: rag.py aus BASIS_COMMIT (letzter Stand vor der Spec, per git show) im selben Lauf
"""
import contextlib
import hashlib
import importlib
import io
import json
import os
import sqlite3
import gc
import importlib.util
import statistics
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import httpx
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402
import openwebui_pipe as op  # noqa: E402
from test_openwebui_pipe import sammle, ollama_ndjson  # noqa: E402

SID, NAME = "testwelt", "Testwelt"
ACHSEN = ("feuer", "wasser", "erde")
HINWEIS = "Fassung beta -- fuer die massgebliche Fassung umrechnen"


def achsen_vektor(text):
    """Themenachsen: Anzahl der Achsenwoerter, letzte Komponente 0,1 (bzw. 1,0 ohne Achse).

    Pfad-Vorsaetze (REQ-MB-15), Buchtitel und Kennwoerter enthalten keine Achsenwoerter --
    sie veraendern den Vektor nicht. "Feuer <kennung>" liegt deshalb genau auf der Frage "Feuer"
    (Score 1,0)."""
    t = text.lower()
    v = [float(t.count(a)) for a in ACHSEN]
    return v + [0.1 if any(v) else 1.0]


class _Antwort:
    def __init__(self, daten):
        self._daten = daten

    def raise_for_status(self):
        pass

    def json(self):
        return self._daten


class Netz:
    """requests.post-Attrappe: zaehlt jeden eingebetteten Text."""

    def __init__(self):
        self.eingebettet = []

    def __call__(self, url, json=None, timeout=None):
        if url.endswith("/api/embed"):
            self.eingebettet.extend(json["input"])
            return _Antwort({"embeddings": [achsen_vektor(t) for t in json["input"]]})
        if url.endswith("/api/chat"):
            return _Antwort({"message": {"content": "Antwort."}})
        raise AssertionError(f"unerwartete URL {url}")


def eintrag(bid, i, seite, text, pfad=("K1",), sid=SID, name=NAME, typ="regel"):
    return {"id": i, "seite": seite, "typ": typ, "text": text, "spiel": name, "spiel_id": sid,
            "buch_id": bid, "abschnittspfad": list(pfad)}


def buch(bid, titel, fassung, sprache="de", quelle=None, inhaltsart="regel", inhaltsarten=None, **extra):
    d = {"buch_id": bid, "titel": titel, "fassung": fassung, "sprache": sprache,
         "quelle": quelle or f"{bid}.pdf", "inhaltsart": inhaltsart}
    if inhaltsarten:
        d["inhaltsarten"] = [{"praefix": list(p), "inhaltsart": a} for p, a in inhaltsarten]
    d.update(extra)
    return d


def hashes(verz):
    """{relativer Pfad: sha256} aller Dateien unter verz."""
    out = {}
    for wurzel, _, dateien in os.walk(verz):
        for d in dateien:
            p = os.path.join(wurzel, d)
            with open(p, "rb") as f:
                out[os.path.relpath(p, verz)] = hashlib.sha256(f.read()).hexdigest()
    return out


def kennung(h, kennungen):
    """Welche der Kennungen steckt im Text des Treffers (genau eine)."""
    gefunden = [k for k in kennungen if k in h["text"]]
    assert len(gefunden) == 1, (h["text"], gefunden)
    return gefunden[0]


class Aufzeichner:
    """Reranker-Attrappe: alle gleich gut (Kandidatenfolge zaehlt), merkt sich das Kandidatenfeld."""

    def __init__(self):
        self.paare = []

    def predict(self, paare):
        self.paare.extend(paare)
        return np.zeros(len(paare))


class BestandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data = os.path.join(self.tmp.name, "data")
        self.index = os.path.join(self.data, "index.sqlite")
        self.netz = Netz()
        patches = [mock.patch("requests.post", side_effect=self.netz),
                   mock.patch.multiple(rag, DATA_DIR=self.data, INDEX_PATH=self.index, OLLAMA="http://stub",
                                       EMBED_MODEL="bge-m3", CHUNK_SIZE=400, CHUNK_OVERLAP=150, EMBED_BATCH=64,
                                       HYBRID=False, RERANK=False, CANDIDATES=20),
                   mock.patch.dict(os.environ)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("DROP_TYPES", None)

    # ---------- Daten ----------
    def bestand(self, buecher, fassungsregeln=None, sid=SID, name=NAME):
        verz = os.path.join(self.data, sid)
        os.makedirs(verz, exist_ok=True)
        meta = {"spiel_id": sid, "name": name, "aliase": [], "sprache": "de", "quelle_pdf": None,
                "buecher": buecher}
        if fassungsregeln is not None:
            meta["fassungsregeln"] = fassungsregeln
        with open(os.path.join(verz, "spiel.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta

    def buchdatei(self, bid, sid=SID):
        return os.path.join(self.data, sid, "buecher", bid, "knowledge.jsonl")

    def schreibe_buch(self, bid, eintraege, sid=SID):
        pfad = self.buchdatei(bid, sid)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        rag.schreibe_jsonl(pfad, eintraege)

    def schreibe_golden(self, fragen, sid=SID):
        with open(os.path.join(self.data, sid, "golden_set.json"), "w", encoding="utf-8") as f:
            json.dump({"spiel_id": sid, "fragen": fragen}, f, ensure_ascii=False)

    # ---------- Ablauf ----------
    def baue(self, ids=None, ausgabe=None):
        vorher = len(self.netz.eingebettet)
        erg = rag.aktualisiere_index(ids, ausgabe=ausgabe or (lambda *_: None))
        return erg, self.netz.eingebettet[vorher:]

    def oeffne(self):
        con = rag.oeffne_index(self.index)
        self.addCleanup(con.close)
        return con

    def suche(self, frage, k, sid=SID, filter=None):
        kw = {} if filter is None else {"filter": filter}
        return rag.retrieve(frage, k=k, spiel_id=sid, index=self.oeffne(), **kw)

    def zeilen(self, sid=SID):
        con = sqlite3.connect(self.index)
        try:
            return con.execute("SELECT buch_id, fassung, sprache, seite, abschnittspfad, inhaltsart, text "
                               "FROM chunks WHERE spiel_id=? ORDER BY id", (sid,)).fetchall()
        finally:
            con.close()

    # ---------- Pipe (Index-Weg, read-only wie im Betrieb) ----------
    def pipe(self, top_k):
        p = op.Pipe()
        p.valves = op.Pipe.Valves(RAG_DIR=BASE, INDEX_PATH=self.index, OLLAMA_URL="http://stub", TOP_K=top_k,
                                  DROP_TYPES="", CHUNK_SIZE=400, CHUNK_OVERLAP=150, EMBED_MODEL="bge-m3")
        self.llm_bekam = []

        def handler(req):
            self.llm_bekam.append(json.loads(req.content))
            return httpx.Response(200, text=ollama_ndjson("Ant", "wort"))
        echter_client = httpx.AsyncClient
        patch = mock.patch.object(op.httpx, "AsyncClient",
                                  lambda **kw: echter_client(transport=httpx.MockTransport(handler), **kw))
        patch.start()
        self.addCleanup(patch.stop)
        return p

    def frage_pipe(self, p, text, spiel=NAME):
        return "".join(sammle(p.pipe({"messages": [{"role": "user", "content": text}],
                                      "regelfrage": {"spiel": spiel}})))

    def cli(self, frage, spiel=SID):
        """rag.py ask --spiel ...: (stdout, hits beim Antwortmodell)."""
        bekam = []

        def antwort(q, hits, verlauf=None):
            bekam.append(hits)
            return "ANTWORT"
        puffer = io.StringIO()
        with mock.patch.object(rag, "answer", antwort), contextlib.redirect_stdout(puffer):
            rag.cmd_ask(frage, spiel)
        return puffer.getvalue(), bekam[0]


# ===================================================================================
# A. Datenmodell
# ===================================================================================
def nord(sid=SID, name=NAME):
    return [eintrag("nord", 1, 10, "Feuer Feuer Wasser nordeins", ("K1",), sid, name),
            eintrag("nord", 2, 11, "Feuer Wasser Wasser nordzwei", ("K1", "A"), sid, name),
            eintrag("nord", 3, 12, "Feuer Erde norddrei", ("K2",), sid, name),
            eintrag("nord", 4, 13, "Wasser Erde nordvier", ("K2", "X"), sid, name),
            eintrag("nord", 5, 14, "Feuer Feuer Feuer Erde nordfuenf", ("K2X",), sid, name),
            eintrag("nord", 6, 15, "Erde nordsechs", ("K2", "X", "Y"), sid, name)]


def sued(sid=SID, name=NAME):
    return [eintrag("sued", 1, 10, "Feuer suedeins", ("K1",), sid, name),
            eintrag("sued", 2, 11, "Feuer Feuer Feuer Feuer Feuer Feuer suedzwei", ("K1",), sid, name),
            eintrag("sued", 3, 12, "Wasser sueddrei", ("K1",), sid, name)]


NORD_K = ["nordeins", "nordzwei", "norddrei", "nordvier", "nordfuenf", "nordsechs"]
SUED_K = ["suedeins", "suedzwei", "sueddrei"]

ALT = [{"id": 1, "seite": 11, "typ": "regel", "text": "Feuer verdient man in Phase 4.", "spiel": "Altspiel",
        "spiel_id": "altspiel"},
       {"id": 2, "seite": 6, "typ": "regel", "text": "Wasser wird am Anfang gebaut. " * 20, "spiel": "Altspiel",
        "spiel_id": "altspiel"},
       {"id": 3, "seite": 2, "typ": "flavor", "text": "Erde auf dem Deckblatt.", "spiel": "Altspiel",
        "spiel_id": "altspiel"}]


class ZweiBuecher(BestandTest):
    def lege_zwei_an(self, nord_arten=None):
        self.bestand([buch("nord", "Buch Nord", "alpha", inhaltsarten=nord_arten),
                      buch("sued", "Buch Sued", "beta", sprache="en", inhaltsart="welt")])
        self.schreibe_buch("nord", nord())
        self.schreibe_buch("sued", sued())

    def lege_alt_an(self):
        meta = rag.lege_spiel_an("Altspiel")
        rag.schreibe_jsonl(rag.knowledge_pfad(meta["spiel_id"]), ALT)
        return meta["spiel_id"]


class TestDatenmodell(ZweiBuecher):
    @unittest.skip("devloop: REQ-MB-1 noch nicht implementiert")
    def test_req_mb_1_zwei_buecher_im_index(self):
        """[REQ-MB-1] Bestand mit zwei Buechern -> index legt Haeppchen beider Buecher an, je Buch eigene Datei."""
        self.lege_zwei_an()
        _, eingebettet = self.baue()
        self.assertEqual(len(eingebettet), len(nord()) + len(sued()))
        self.assertEqual([b["buch_id"] for b in rag.lies_buecher(SID)], ["nord", "sued"])
        chunks, _ = rag.lade_spiel(self.oeffne(), SID)
        self.assertEqual(sorted(kennung(c, NORD_K + SUED_K) for c in chunks), sorted(NORD_K + SUED_K))
        self.assertEqual({c["buch_id"] for c in chunks}, {"nord", "sued"})

    @unittest.skip("devloop: REQ-MB-1 noch nicht implementiert")
    def test_req_mb_1_eigener_fingerprint_je_buch(self):
        """[REQ-MB-1] Jedes Buch hat seinen eigenen Fingerprint: Aenderung an sued bettet nur sued neu ein."""
        self.lege_zwei_an()
        self.baue()
        neu = sued()[:2] + [eintrag("sued", 9, 19, "Wasser Erde suedneun")]
        self.schreibe_buch("sued", neu)
        _, eingebettet = self.baue()
        self.assertEqual(len(eingebettet), len(neu))
        self.assertTrue(all(any(k in t for k in SUED_K + ["suedneun"]) for t in eingebettet), eingebettet)

    @unittest.skip("devloop: REQ-MB-1 noch nicht implementiert")
    def test_req_mb_1_praefix_zuweisung_laengstes_gewinnt(self):
        """[REQ-MB-1] Standard regel, ["K2"]->welt, ["K2","X","Y"]->regel: laengstes Pfad-Praefix gewinnt."""
        self.lege_zwei_an(nord_arten=[(("K2",), "welt"), (("K2", "X", "Y"), "regel")])
        self.baue()
        chunks, _ = rag.lade_spiel(self.oeffne(), SID)
        art = {kennung(c, NORD_K + SUED_K): c["inhaltsart"] for c in chunks}
        self.assertEqual(art, {"nordeins": "regel",       # K1
                               "nordzwei": "regel",       # K1 > A
                               "norddrei": "welt",        # K2
                               "nordvier": "welt",        # K2 > X
                               "nordfuenf": "regel",      # "K2X" ist kein Pfad-Praefix K2
                               "nordsechs": "regel",      # K2 > X > Y: laengeres Praefix
                               "suedeins": "welt", "suedzwei": "welt", "sueddrei": "welt"})   # Standard von sued

    @unittest.skip("devloop: REQ-MB-1 noch nicht implementiert")
    def test_req_mb_1_altbestand_ein_buch_und_byte_gleich(self):
        """[REQ-MB-1] Altbestand gilt als genau ein Buch; sein Verzeichnis ist nach index byte-gleich."""
        self.lege_zwei_an()
        alt = self.lege_alt_an()
        vorher = hashes(os.path.join(self.data, alt))
        self.baue()
        self.assertEqual(hashes(os.path.join(self.data, alt)), vorher)
        self.assertEqual(sorted(vorher), ["knowledge.jsonl", "spiel.json"])      # keine neue Datei
        self.assertEqual(len(rag.lies_buecher(alt)), 1)
        chunks, _ = rag.lade_spiel(self.oeffne(), alt)
        self.assertEqual([(c["seite"], c["text"]) for c in chunks],
                         [(s, t) for s, _, t in rag.indexiere_stuecke(ALT)])


class TestFelderJeHaeppchen(ZweiBuecher):
    @unittest.skip("devloop: REQ-MB-2 noch nicht implementiert")
    def test_req_mb_2_felder_im_index_und_in_lade_spiel(self):
        """[REQ-MB-2] Index-Zeile und lade_spiel-Chunk tragen buch_id, fassung, sprache, seite, abschnittspfad, inhaltsart."""
        self.lege_zwei_an(nord_arten=[(("K2",), "welt")])
        self.baue()
        soll = {"nordeins": ("nord", "alpha", "de", 10, ["K1"], "regel"),
                "nordzwei": ("nord", "alpha", "de", 11, ["K1", "A"], "regel"),
                "norddrei": ("nord", "alpha", "de", 12, ["K2"], "welt"),
                "nordvier": ("nord", "alpha", "de", 13, ["K2", "X"], "welt"),
                "nordfuenf": ("nord", "alpha", "de", 14, ["K2X"], "regel"),
                "nordsechs": ("nord", "alpha", "de", 15, ["K2", "X", "Y"], "welt"),
                "suedeins": ("sued", "beta", "en", 10, ["K1"], "welt"),
                "suedzwei": ("sued", "beta", "en", 11, ["K1"], "welt"),
                "sueddrei": ("sued", "beta", "en", 12, ["K1"], "welt")}
        zeilen = {}
        for b, f, s, seite, pfad, art, text in self.zeilen():
            zeilen[kennung({"text": text}, list(soll))] = (b, f, s, json.loads(seite), json.loads(pfad), art)
        self.assertEqual(zeilen, soll)
        chunks, _ = rag.lade_spiel(self.oeffne(), SID)
        geladen = {kennung(c, list(soll)): (c["buch_id"], c["fassung"], c["sprache"], c["seite"],
                                            c["abschnittspfad"], c["inhaltsart"]) for c in chunks}
        self.assertEqual(geladen, soll)

    @unittest.skip("devloop: REQ-MB-2 noch nicht implementiert")
    def test_req_mb_2_werte_kommen_aus_der_zeile(self):
        """[REQ-MB-2] Falsche Deklaration (spiel.json nach dem Bau verfaelscht, ohne index) -> lade_spiel liefert die Zeilenwerte."""
        self.lege_zwei_an()
        self.baue()
        self.bestand([buch("nord", "Buch Nord", "gamma", sprache="en", inhaltsart="welt"),
                      buch("sued", "Buch Sued", "alpha", sprache="de", inhaltsart="regel")])
        chunks, _ = rag.lade_spiel(self.oeffne(), SID)
        for c in chunks:
            with self.subTest(text=c["text"]):
                if c["buch_id"] == "nord":
                    self.assertEqual((c["fassung"], c["sprache"], c["inhaltsart"]), ("alpha", "de", "regel"))
                else:
                    self.assertEqual((c["fassung"], c["sprache"], c["inhaltsart"]), ("beta", "en", "welt"))


# ---------- REQ-MB-3: alter Index-Stand (Code vor dieser Spec, hier eingefroren) ----------
_ALT_SCHEMA_SQL = """
CREATE TABLE spiele (spiel_id TEXT PRIMARY KEY, name TEXT NOT NULL, aliase TEXT NOT NULL, sprache TEXT,
                     quelle_pdf TEXT);
CREATE TABLE staende (spiel_id TEXT NOT NULL, konfig TEXT NOT NULL, fingerprint TEXT NOT NULL,
                      chunks INTEGER NOT NULL, dim INTEGER NOT NULL, PRIMARY KEY (spiel_id, konfig));
CREATE TABLE chunks (id INTEGER PRIMARY KEY, spiel_id TEXT NOT NULL, konfig TEXT NOT NULL, pos INTEGER NOT NULL,
                     seite TEXT NOT NULL, typ TEXT, text TEXT NOT NULL, emb BLOB NOT NULL,
                     UNIQUE (spiel_id, konfig, pos));
CREATE VIRTUAL TABLE chunks_fts USING fts5(text, tag, tokenize='unicode61 remove_diacritics 2');
"""


def _norm(v):
    v = np.asarray(v, dtype=np.float32)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


def baue_alten_index(pfad, spiel_id, meta, wissen_pfad, size, overlap, embed_model="bge-m3"):
    """Index genau so, wie ihn rag.py VOR dieser Spec schrieb (Schema 1, Konfig-String, Fingerprint)."""
    konfig = json.dumps({"schema": 1, "embed_model": embed_model, "chunk_size": size, "chunk_overlap": overlap},
                        sort_keys=True)
    with open(wissen_pfad, "rb") as f:
        roh_bytes = f.read()
    fp = hashlib.sha256(roh_bytes + b"\0" + konfig.encode()).hexdigest()
    stuecke = []
    for c in rag.lies_jsonl(wissen_pfad):
        for start in range(0, len(c["text"]), size - overlap):
            stuecke.append((c["seite"], c.get("typ"), c["text"][start:start + size]))
    embs = _norm([achsen_vektor(t) for _, _, t in stuecke]).astype("<f4")
    tag = "t" + hashlib.sha1(f"{spiel_id}\0{konfig}".encode()).hexdigest()[:24]
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    con = sqlite3.connect(pfad)
    con.executescript(_ALT_SCHEMA_SQL)
    con.execute("INSERT INTO spiele VALUES (?,?,?,?,?)",
                (spiel_id, meta["name"], json.dumps(meta.get("aliase") or []), meta.get("sprache"), None))
    for pos, ((seite, typ, text), e) in enumerate(zip(stuecke, embs)):
        cur = con.execute("INSERT INTO chunks (spiel_id, konfig, pos, seite, typ, text, emb) VALUES (?,?,?,?,?,?,?)",
                          (spiel_id, konfig, pos, json.dumps(seite), typ, text, e.tobytes()))
        con.execute("INSERT INTO chunks_fts (rowid, text, tag) VALUES (?,?,?)", (cur.lastrowid, text, tag))
    con.execute("INSERT INTO staende VALUES (?,?,?,?,?)", (spiel_id, konfig, fp, len(stuecke), embs.shape[1]))
    con.commit()
    con.close()


def alte_suche(pfad, spiel_id, frage, k):
    """Top-k direkt aus dem alten Index gerechnet (Vektor, stabile Gleichstandsregel)."""
    con = sqlite3.connect(pfad)
    try:
        zeilen = con.execute("SELECT seite, text, emb FROM chunks WHERE spiel_id=? ORDER BY pos", (spiel_id,)).fetchall()
    finally:
        con.close()
    embs = np.frombuffer(b"".join(z[2] for z in zeilen), dtype="<f4").reshape(len(zeilen), -1)
    q = _norm([achsen_vektor(frage)])[0]
    sims = embs @ q
    return [(json.loads(zeilen[i][0]), zeilen[i][1], float(sims[i])) for i in np.argsort(-sims, kind="stable")[:k]]


class TestRueckwaertskompatibel(ZweiBuecher):
    @unittest.skip("devloop: REQ-MB-3 noch nicht implementiert")
    def test_req_mb_3_migration_alter_index_ohne_neu_einbetten(self):
        """[REQ-MB-3] Index vom Stand vor der Spec -> nach Migration 0 Einbettungen, gleiche Zeilen und Suchergebnisse."""
        alt = self.lege_alt_an()
        meta = rag.lies_spiel(alt)
        baue_alten_index(self.index, alt, meta, rag.knowledge_pfad(alt), 400, 150)
        fragen = ("Feuer", "Wasser", "Erde", "Feuer Wasser")
        vorher_suche = {f: alte_suche(self.index, alt, f, 2) for f in fragen}
        con = sqlite3.connect(self.index)
        vorher_zeilen = con.execute("SELECT pos, seite, typ, text, emb FROM chunks ORDER BY pos").fetchall()
        con.close()
        verz_vorher = hashes(os.path.join(self.data, alt))

        _, eingebettet = self.baue([alt])
        self.assertEqual(eingebettet, [], "ein gueltiger alter Stand wurde neu eingebettet")
        _, eingebettet = self.baue()               # auch --alle bettet nichts ein
        self.assertEqual(eingebettet, [])
        self.assertEqual(hashes(os.path.join(self.data, alt)), verz_vorher)
        con = sqlite3.connect(self.index)
        self.assertEqual(con.execute("SELECT pos, seite, typ, text, emb FROM chunks ORDER BY pos").fetchall(),
                         vorher_zeilen)
        con.close()
        for f in fragen:
            with self.subTest(frage=f):
                neu = self.suche(f, 2, sid=alt)
                self.assertEqual([(h["seite"], h["text"]) for h, _ in neu],
                                 [(s, t) for s, t, _ in vorher_suche[f]])
                for (_, s), (_, _, s_alt) in zip(neu, vorher_suche[f]):
                    self.assertAlmostEqual(s, s_alt, places=6)

    @unittest.skip("devloop: REQ-MB-3 noch nicht implementiert")
    def test_req_mb_3_altbestand_neben_mehrbuch_bestand_unveraendert(self):
        """[REQ-MB-3] Altbestand im selben Index wie ein Mehr-Buecher-Bestand: Retrieval, Quellenkopf, Entscheid-Text wie vorher."""
        self.lege_zwei_an()
        alt = self.lege_alt_an()
        self.baue()
        chunks = rag.baue_knowledge_chunks(ALT, set())
        embs = _norm([achsen_vektor(c["text"]) for c in chunks])
        for frage in ("Feuer", "Wasser", "Erde"):
            with self.subTest(frage=frage):
                vorher = rag.retrieve(frage, chunks, embs, k=3)       # In-Memory-Weg = Stand vor der Spec
                neu = self.suche(frage, 3, sid=alt)
                self.assertEqual([(h["seite"], h["text"], round(s, 6)) for h, s in neu],
                                 [(h["seite"], h["text"], round(s, 6)) for h, s in vorher])
                # Quellenkopf und Entscheid-Text des Altbestands: das eingefrorene Format von heute
                self.assertEqual(rag.baue_kontext(neu),
                                 "\n\n".join(f"[knowledge, Seite {h['seite']}]\n{h['text']}" for h, _ in neu))
                seiten = list(dict.fromkeys(h["seite"] for h, _ in neu))
                self.assertEqual(rag.entscheid_text_nichts(neu),
                                 "In den gefundenen Stellen steht dazu nichts. Naechste Fundstellen: "
                                 + ", ".join(f"S. {s}" for s in seiten) + ".")


# ===================================================================================
# REQ-MB-4: Filter vor dem Ranking
# ===================================================================================
class TestFilter(ZweiBuecher):
    """nord: alpha/de/regel; sued: beta/en/welt. sued hat "Feuer suedeins" (Score 1,0 zur Frage
    "Feuer") und "suedzwei" (staerkster BM25-Treffer). Vergleich: Bestand "nurnord" mit genau den
    passenden Haeppchen, im selben Index."""
    FILTER = ({"buch_id": "nord"}, {"fassung": "alpha"}, {"sprache": "de"}, {"inhaltsart": "regel"},
              {"fassung": "alpha", "inhaltsart": "regel"})

    def setUp(self):
        super().setUp()
        self.lege_zwei_an()
        self.bestand([buch("nord", "Buch Nord", "alpha")], sid="nurnord", name="Nurnord")
        self.schreibe_buch("nord", nord("nurnord", "Nurnord"), sid="nurnord")
        self.baue()

    @staticmethod
    def schluessel(hits):
        return [(h["buch_id"], h["seite"], h["text"], round(s, 6)) for h, s in hits]

    @unittest.skip("devloop: REQ-MB-4 noch nicht implementiert")
    def test_req_mb_4_vektor_score_eins_verdraengt_nichts(self):
        """[REQ-MB-4] Vektorsuche: nicht passendes Haeppchen mit Score 1,0 erscheint nicht; Top-k = Bestand nur mit passenden."""
        ungefiltert = self.suche("Feuer", 3)
        self.assertIn("suedeins", [kennung(h, NORD_K + SUED_K) for h, _ in ungefiltert])   # Gegenprobe
        self.assertAlmostEqual(max(s for _, s in ungefiltert), 1.0, places=5)
        soll = self.schluessel(self.suche("Feuer", 3, sid="nurnord"))
        for f in self.FILTER:
            with self.subTest(filter=f):
                hits = self.suche("Feuer", 3, filter=f)
                self.assertEqual(len(hits), 3)
                self.assertEqual({h["buch_id"] for h, _ in hits}, {"nord"})
                self.assertEqual(self.schluessel(hits), soll)

    @unittest.skip("devloop: REQ-MB-4 noch nicht implementiert")
    def test_req_mb_4_bm25_treffer_verdraengt_nichts(self):
        """[REQ-MB-4] HYBRID=1: der staerkste BM25-Treffer (fremdes Buch) erscheint nicht; Top-k = Bestand nur mit passenden."""
        with mock.patch.object(rag, "HYBRID", True):
            con = self.oeffne()
            alle, _ = rag.lade_spiel(con, SID)
            erster = rag.bm25_rangfolge(con, "Feuer", alle, 1)
            self.assertEqual(kennung(alle[erster[0]], NORD_K + SUED_K), "suedzwei")     # Gegenprobe
            soll = self.schluessel(self.suche("Feuer", 3, sid="nurnord"))
            for f in self.FILTER:
                with self.subTest(filter=f):
                    hits = self.suche("Feuer", 3, filter=f)
                    self.assertEqual({h["buch_id"] for h, _ in hits}, {"nord"})
                    self.assertEqual(self.schluessel(hits), soll)

    @unittest.skip("devloop: REQ-MB-4 noch nicht implementiert")
    def test_req_mb_4_reranker_kandidatenfeld_nur_passende(self):
        """[REQ-MB-4] RERANK=1 (mit und ohne HYBRID): im Kandidatenfeld des Rerankers nur passende Haeppchen."""
        for hybrid in (False, True):
            soll_rec = Aufzeichner()
            with mock.patch.multiple(rag, RERANK=True, HYBRID=hybrid, get_reranker=lambda: soll_rec):
                soll = self.schluessel(self.suche("Feuer", 3, sid="nurnord"))
            for f in self.FILTER:
                with self.subTest(filter=f, hybrid=hybrid):
                    rec = Aufzeichner()
                    with mock.patch.multiple(rag, RERANK=True, HYBRID=hybrid, get_reranker=lambda: rec):
                        hits = self.suche("Feuer", 3, filter=f)
                    self.assertTrue(rec.paare, "Reranker wurde nicht gefragt")
                    self.assertEqual([k for _, t in rec.paare for k in SUED_K if k in t], [])
                    self.assertEqual(self.schluessel(hits), soll)

    @unittest.skip("devloop: REQ-MB-4 noch nicht implementiert")
    def test_req_mb_4_unbekannter_filterwert_ist_konfigfehler(self):
        """[REQ-MB-4] Filter auf einen Wert, den der Bestand nicht hat -> KonfigFehler statt leerer Suche."""
        for f in ({"buch_id": "west"}, {"fassung": "gamma"}, {"sprache": "fr"}, {"inhaltsart": "kosmos"},
                  {"fassung": "alpha", "buch_id": "sued-x"}):
            with self.subTest(filter=f), self.assertRaises(rag.KonfigFehler):
                self.suche("Feuer", 3, filter=f)


# ===================================================================================
# REQ-MB-5 / REQ-MB-21: Fassungsregel und Hinweis gekennzeichneter Fassungen
# ===================================================================================
REGELN = {"regel": {"massgeblich": ["alpha"], "gekennzeichnet": {"beta": HINWEIS}}}
ROLLEN = ["mkar", "mkaw", "mkbr", "mkbw", "mkgr", "mkgw"]      # Fassung a/b/g x Inhaltsart regel/welt
# Score 1,0 fuer alle sechs; mkgr ist der kuerzeste Text -> staerkster BM25-Treffer
GLEICH = {"mkar": "Feuer mkar fuell fuell fuell", "mkaw": "Feuer mkaw fuell fuell fuell",
          "mkbr": "Feuer mkbr fuell fuell fuell", "mkbw": "Feuer mkbw fuell fuell fuell",
          "mkgr": "Feuer mkgr", "mkgw": "Feuer mkgw fuell fuell fuell"}
# verschiedene Scores zur Frage "Feuer": gr 1,0 > br .947 > ar .894 > gw .830 > aw .709 > bw .449
VERSCHIEDEN = {"mkar": "Feuer Feuer Wasser mkar", "mkaw": "Feuer Wasser mkaw",
               "mkbr": "Feuer Feuer Feuer Wasser mkbr", "mkbw": "Feuer Erde Erde mkbw",
               "mkgr": "Feuer mkgr", "mkgw": "Feuer Feuer Feuer Erde Erde mkgw"}
SEITE = {"mkar": 10, "mkaw": 11, "mkbr": 20, "mkbw": 21, "mkgr": 30, "mkgw": 31}


class FassungsTest(BestandTest):
    def lege_fassungen_an(self, texte, regeln=REGELN, ohne_gr=False, sid=SID, name=NAME, hinweis=None):
        if hinweis is not None:
            regeln = {"regel": {"massgeblich": ["alpha"], "gekennzeichnet": {"beta": hinweis}}}
        self.bestand([buch("ba", "Erstes Testbuch", "alpha", inhaltsarten=[(("Welt",), "welt")]),
                      buch("bb", "Zweites Testbuch", "beta", inhaltsarten=[(("Welt",), "welt")]),
                      buch("bg", "Drittes Testbuch", "gamma", inhaltsarten=[(("Welt",), "welt")])],
                     regeln, sid=sid, name=name)
        for bid, r, w in (("ba", "mkar", "mkaw"), ("bb", "mkbr", "mkbw"), ("bg", "mkgr", "mkgw")):
            eintraege = [eintrag(bid, 1, SEITE[r], texte[r], ("Regeln",), sid, name),
                         eintrag(bid, 2, SEITE[w], texte[w], ("Welt",), sid, name)]
            if ohne_gr and r == "mkgr":
                eintraege = eintraege[1:]
            self.schreibe_buch(bid, eintraege, sid=sid)

    @staticmethod
    def rollen(hits):
        return [kennung(h, ROLLEN) for h, _ in hits]


class TestFassungsregel(FassungsTest):
    @unittest.skip("devloop: REQ-MB-5 noch nicht implementiert")
    def test_req_mb_5_erreichbar_und_ausgeschlossen_vektor(self):
        """[REQ-MB-5] Score 1,0 ueberall: erreichbar regel@alpha, regel@beta, welt@alle; regel@gamma nie (Vektor)."""
        self.lege_fassungen_an(GLEICH)
        self.baue()
        hits = self.suche("Feuer", 10)
        self.assertEqual(sorted(self.rollen(hits)), ["mkar", "mkaw", "mkbr", "mkbw", "mkgw"])
        self.assertTrue(all(abs(s - 1.0) < 1e-5 for _, s in hits))
        art = {kennung(h, ROLLEN): (h["fassung"], h["inhaltsart"]) for h, _ in hits}
        self.assertEqual(art["mkbr"], ("beta", "regel"))
        self.assertEqual(art["mkgw"], ("gamma", "welt"))

    @unittest.skip("devloop: REQ-MB-5 noch nicht implementiert")
    def test_req_mb_5_ausgeschlossen_im_bm25_kandidatenfeld(self):
        """[REQ-MB-5] HYBRID=1: regel@gamma (staerkster BM25-Treffer) steht in keiner BM25-Rangfolge und in keinem Ergebnis."""
        self.lege_fassungen_an(GLEICH, regeln={}, sid="testwelt-ohne", name="Testwelt ohne")
        self.lege_fassungen_an(GLEICH)
        self.baue()
        con = self.oeffne()
        ohne, _ = rag.lade_spiel(con, "testwelt-ohne")
        self.assertEqual(kennung(ohne[rag.bm25_rangfolge(con, "Feuer", ohne, 1)[0]], ROLLEN), "mkgr")   # Gegenprobe
        gesehen = []
        echt = rag.bm25_rangfolge

        def zeichne_auf(con_, query, chunks, n):
            folge = echt(con_, query, chunks, n)
            gesehen.extend(kennung(chunks[i], ROLLEN) for i in folge)
            return folge
        with mock.patch.multiple(rag, HYBRID=True, bm25_rangfolge=zeichne_auf):
            hits = self.suche("Feuer", 10)
        self.assertTrue(gesehen, "BM25 wurde nicht gefragt")
        self.assertNotIn("mkgr", gesehen)
        self.assertEqual(sorted(self.rollen(hits)), ["mkar", "mkaw", "mkbr", "mkbw", "mkgw"])

    @unittest.skip("devloop: REQ-MB-5 noch nicht implementiert")
    def test_req_mb_5_ausgeschlossen_im_reranker_kandidatenfeld(self):
        """[REQ-MB-5] RERANK=1 (mit/ohne HYBRID): regel@gamma nie im Kandidatenfeld des Rerankers."""
        self.lege_fassungen_an(GLEICH)
        self.baue()
        for hybrid in (False, True):
            with self.subTest(hybrid=hybrid):
                rec = Aufzeichner()
                with mock.patch.multiple(rag, RERANK=True, HYBRID=hybrid, get_reranker=lambda: rec):
                    hits = self.suche("Feuer", 10)
                self.assertTrue(rec.paare)
                self.assertEqual(sorted({kennung({"text": t}, ROLLEN) for _, t in rec.paare}),
                                 ["mkar", "mkaw", "mkbr", "mkbw", "mkgw"])
                self.assertNotIn("mkgr", self.rollen(hits))

    @unittest.skip("devloop: REQ-MB-5 noch nicht implementiert")
    def test_req_mb_5_ranking_gleichbehandlung(self):
        """[REQ-MB-5] Top-k-Reihenfolge = Bestand ohne Regel, aus dem regel@gamma entfernt ist (kein Bonus/Malus fuer beta)."""
        for name, texte in (("gleich", GLEICH), ("verschieden", VERSCHIEDEN)):
            with self.subTest(texte=name):
                self.lege_fassungen_an(texte)
                self.lege_fassungen_an(texte, regeln={}, ohne_gr=True, sid="testwelt-ohne", name="Testwelt ohne")
                self.baue()
                for hybrid in (False, True):
                    with mock.patch.object(rag, "HYBRID", hybrid):
                        mit = self.suche("Feuer", 5)
                        ohne = self.suche("Feuer", 5, sid="testwelt-ohne")
                    self.assertEqual(self.rollen(mit), self.rollen(ohne), (name, hybrid))
                    self.assertEqual([round(s, 6) for _, s in mit], [round(s, 6) for _, s in ohne])
        self.assertEqual(self.rollen(self.suche("Feuer", 5)), ["mkbr", "mkar", "mkgw", "mkaw", "mkbw"])

    @unittest.skip("devloop: REQ-MB-5 noch nicht implementiert")
    def test_req_mb_5_gilt_in_eval_cli_und_pipe(self):
        """[REQ-MB-5] Die Regel gilt bei jeder Suche des Bestands: Eval, CLI (ask) und Pipe sehen regel@gamma nie."""
        self.lege_fassungen_an(VERSCHIEDEN)
        self.schreibe_golden([
            {"id": 1, "frage": "Feuer", "typ": "fakt", "erwartet": "-", "keywords": [],
             "seiten": [{"buch_id": "bg", "seite": 30}]},           # regel@gamma waere Rang 1
            {"id": 2, "frage": "Feuer", "typ": "fakt", "erwartet": "-", "keywords": [],
             "seiten": [{"buch_id": "ba", "seite": 10}]}])          # regel@alpha, Rang 2
        antworten = []
        with mock.patch.object(rag, "answer", lambda q, hits, *a: antworten.append(hits) or "x"), \
                contextlib.redirect_stdout(io.StringIO()):
            saetze = rag.cmd_eval_spiele([SID])
        self.assertEqual([s["kategorie"] for s in saetze], [rag.KAT_VERFEHLT, rag.KAT_GETROFFEN])
        self.assertTrue(antworten)
        self.assertNotIn("mkgr", [kennung(h, ROLLEN) for hits in antworten for h, _ in hits])
        _, hits = self.cli("Feuer")
        self.assertNotIn("mkgr", self.rollen(hits))
        p = self.pipe(top_k=6)
        self.frage_pipe(p, "Feuer")
        prompt = self.llm_bekam[-1]["messages"][-1]["content"]
        self.assertIn("mkbr", prompt)
        self.assertNotIn("mkgr", prompt)


class TestHinweis(FassungsTest):
    def setUp(self):
        super().setUp()
        self.lege_fassungen_an(VERSCHIEDEN)
        self.baue()

    def bloecke_mit_hinweis(self, kontext, hinweis=HINWEIS):
        """Kennungen der Quellenbloecke im Prompt, die den Hinweistext tragen."""
        return sorted(kennung({"text": b}, ROLLEN) for b in kontext.split("\n\n")
                      if hinweis in b and any(r in b for r in ROLLEN))

    @unittest.skip("devloop: REQ-MB-21 noch nicht implementiert")
    def test_req_mb_21_hinweis_genau_bei_gekennzeichneter_fassung(self):
        """[REQ-MB-21] Prompt, CLI-Quellenausgabe und Pipe-Fusszeile tragen den Hinweistext genau bei regel@beta."""
        hits = self.suche("Feuer", 5)
        self.assertEqual(sorted(self.rollen(hits)), ["mkar", "mkaw", "mkbr", "mkbw", "mkgw"])
        inhalt = rag.baue_nachrichten("Feuer", hits)[-1]["content"]
        self.assertEqual(inhalt.count(HINWEIS), 1)
        self.assertEqual(self.bloecke_mit_hinweis(rag.baue_kontext(hits)), ["mkbr"])
        for h, _ in hits:
            with self.subTest(rolle=kennung(h, ROLLEN)):
                self.assertEqual(HINWEIS in rag.fundstelle(h), kennung(h, ROLLEN) == "mkbr")
                self.assertEqual(rag.fassungs_hinweis(h), HINWEIS if kennung(h, ROLLEN) == "mkbr" else "")
        aus, _ = self.cli("Feuer")
        self.assertEqual(aus.count(HINWEIS), 1, aus)
        p = self.pipe(top_k=5)
        text = self.frage_pipe(p, "Feuer")
        self.assertEqual(text.count(HINWEIS), 1, text)
        self.assertEqual(self.llm_bekam[-1]["messages"][-1]["content"].count(HINWEIS), 1)

    @unittest.skip("devloop: REQ-MB-21 noch nicht implementiert")
    def test_req_mb_21_mutation_der_hinweis_funktion_aendert_cli_und_pipe(self):
        """[REQ-MB-21] fassungs_hinweis liefert einen Marker -> Prompt, CLI- und Pipe-Ausgabe zeigen ihn (eine Funktion)."""
        p = self.pipe(top_k=5)
        self.frage_pipe(p, "Feuer")                        # laedt das rag.py der Pipe
        marker = "MARKER-HINWEIS-7f3"
        with mock.patch.object(rag, "fassungs_hinweis", lambda *a, **k: marker), \
                mock.patch.object(p._rag, "fassungs_hinweis", lambda *a, **k: marker):
            p._spiel_cache.clear()
            hits = self.suche("Feuer", 5)
            self.assertIn(marker, rag.baue_nachrichten("Feuer", hits)[-1]["content"])
            aus, _ = self.cli("Feuer")
            self.assertIn(marker, aus)
            text = self.frage_pipe(p, "Feuer")
            self.assertIn(marker, text)
            self.assertIn(marker, self.llm_bekam[-1]["messages"][-1]["content"])

    @unittest.skip("devloop: REQ-MB-21 noch nicht implementiert")
    def test_req_mb_21_hinweistext_ist_daten(self):
        """[REQ-MB-21] Anderer Hinweistext in spiel.json -> beide Ausgaben aendern sich, ohne Code-Aenderung."""
        neu = "Achtung: aeltere Ausgabe, Werte pruefen"
        self.lege_fassungen_an(VERSCHIEDEN, hinweis=neu)
        self.baue()
        hits = self.suche("Feuer", 5)
        inhalt = rag.baue_nachrichten("Feuer", hits)[-1]["content"]
        self.assertNotIn(HINWEIS, inhalt)
        self.assertEqual(self.bloecke_mit_hinweis(rag.baue_kontext(hits), neu), ["mkbr"])
        text = self.frage_pipe(self.pipe(top_k=5), "Feuer")
        self.assertNotIn(HINWEIS, text)
        self.assertEqual(text.count(neu), 1)


# ===================================================================================
# REQ-MB-6: Fundstelle (Buch, Fassung, gedruckte Seite)
# ===================================================================================
class TestFundstelle(BestandTest):
    """Zwei Buecher, beide mit Seite 12 unter den Top-2."""

    def setUp(self):
        super().setUp()
        self.bestand([buch("nord", "Buch Nord", "alpha"), buch("sued", "Buch Sued", "beta")])
        self.schreibe_buch("nord", [eintrag("nord", 1, 12, "Feuer Feuer Wasser nordzwoelf"),
                                    eintrag("nord", 2, 30, "Wasser Erde nordfueller")])
        self.schreibe_buch("sued", [eintrag("sued", 1, 12, "Feuer suedzwoelf"),
                                    eintrag("sued", 2, 31, "Erde suedfueller")])
        self.baue()
        self.hits = self.suche("Feuer", 2)
        self.assertEqual([(h["buch_id"], h["seite"]) for h, _ in self.hits], [("sued", 12), ("nord", 12)])

    @staticmethod
    def kopf(kontext, text):
        """Was im Quellenblock vor dem Haeppchentext steht."""
        block = next(b for b in kontext.split("\n\n") if text in b)
        return block[:block.index(text)]

    @unittest.skip("devloop: REQ-MB-6 noch nicht implementiert")
    def test_req_mb_6_quellenkopf_nennt_buch_fassung_seite(self):
        """[REQ-MB-6] Quellenkopf im Prompt: Buch, Fassung und Seite je Fundstelle -- gleiche Seite 12 unterscheidbar."""
        kontext = rag.baue_kontext(self.hits)
        self.assertIn(kontext, rag.baue_nachrichten("Feuer", self.hits)[-1]["content"])
        koepfe = {h["buch_id"]: self.kopf(kontext, h["text"]) for h, _ in self.hits}
        for bid, titel, fassung in (("nord", "Buch Nord", "alpha"), ("sued", "Buch Sued", "beta")):
            with self.subTest(buch=bid):
                self.assertIn(titel, koepfe[bid])
                self.assertIn(fassung, koepfe[bid])
                self.assertRegex(koepfe[bid], r"(?<!\d)12(?!\d)")
                self.assertIn(rag.fundstelle(next(h for h, _ in self.hits if h["buch_id"] == bid)), koepfe[bid])
        self.assertNotEqual(koepfe["nord"], koepfe["sued"])

    @unittest.skip("devloop: REQ-MB-6 noch nicht implementiert")
    def test_req_mb_6_cli_und_pipe_aus_derselben_funktion(self):
        """[REQ-MB-6] CLI-Quellenausgabe, Pipe-Fusszeile und Pipe-Prompt nennen dieselben Fundstellen wie fundstelle()."""
        fundstellen = [rag.fundstelle(h) for h, _ in self.hits]
        self.assertEqual(len(set(fundstellen)), 2)
        for f, (bid, titel, fassung) in zip(fundstellen, (("sued", "Buch Sued", "beta"), ("nord", "Buch Nord", "alpha"))):
            self.assertIn(titel, f)
            self.assertIn(fassung, f)
            self.assertRegex(f, r"(?<!\d)12(?!\d)")
        aus, _ = self.cli("Feuer")
        p = self.pipe(top_k=2)
        text = self.frage_pipe(p, "Feuer")
        for f in fundstellen:
            self.assertIn(f, aus)
            self.assertIn(f, text)                     # die Modellantwort ist nur "Antwort"
        self.assertEqual(self.llm_bekam[-1]["messages"], rag.baue_nachrichten("Feuer", self.hits))

    @unittest.skip("devloop: REQ-MB-6 noch nicht implementiert")
    def test_req_mb_6_entscheidungsschritt_nennt_buch_und_fassung(self):
        """[REQ-MB-6] C-Text, B-Hinweis und Sprachmodus nennen je Fundstelle Buch, Fassung und Seite."""
        for sprache in (False, True):
            for name, text in (("C", rag.entscheid_text_nichts(self.hits, sprache=sprache)),
                               ("B", rag.entscheid_hinweis(self.hits, sprache=sprache))):
                with self.subTest(teil=name, sprache=sprache):
                    for t in ("Buch Nord", "Buch Sued", "alpha", "beta"):
                        self.assertIn(t, text)
                    self.assertRegex(text, r"(?<!\d)12(?!\d)")
        # zwei Fundstellen auf "Seite 12" -- bei Seiten ohne Buch fielen sie zu einer zusammen
        self.assertEqual(rag.entscheid_text_nichts(self.hits).count("Buch "), 2)

    @unittest.skip("devloop: REQ-MB-6 noch nicht implementiert")
    def test_req_mb_6_mutation_der_kopf_funktion_aendert_cli_und_pipe(self):
        """[REQ-MB-6] fundstelle liefert einen Marker -> Prompt, CLI-Ausgabe, Entscheid-Text, Pipe-Fusszeile und -Prompt zeigen ihn."""
        p = self.pipe(top_k=2)
        self.frage_pipe(p, "Feuer")                        # laedt das rag.py der Pipe
        marker = "MARKER-KOPF-2c9"
        with mock.patch.object(rag, "fundstelle", lambda *a, **k: marker), \
                mock.patch.object(p._rag, "fundstelle", lambda *a, **k: marker):
            p._spiel_cache.clear()
            hits = self.suche("Feuer", 2)
            self.assertIn(marker, rag.baue_nachrichten("Feuer", hits)[-1]["content"])
            self.assertIn(marker, rag.entscheid_text_nichts(hits))
            aus, _ = self.cli("Feuer")
            self.assertIn(marker, aus)
            text = self.frage_pipe(p, "Feuer")
            self.assertIn(marker, text)
            self.assertIn(marker, self.llm_bekam[-1]["messages"][-1]["content"])


# ===================================================================================
# REQ-MB-7: Messung -- Treffer nur bei passendem Buch
# ===================================================================================
class TestMessung(BestandTest):
    """Seite 12 gibt es in beiden Buechern; die Top-4 kommen alle aus sued (nord 12 ist Rang 5)."""

    def setUp(self):
        super().setUp()
        self.bestand([buch("nord", "Buch Nord", "alpha"), buch("sued", "Buch Sued", "beta")])
        self.schreibe_buch("nord", [eintrag("nord", 1, 12, "Feuer Wasser Wasser nordzwoelf")])
        self.schreibe_buch("sued", [eintrag("sued", 1, 12, "Feuer suedzwoelf"),
                                    eintrag("sued", 2, 13, "Feuer Feuer Feuer Erde suedx"),
                                    eintrag("sued", 3, 14, "Feuer Feuer Wasser suedy"),
                                    eintrag("sued", 4, 15, "Feuer Feuer Feuer Erde Erde suedz")])
        self.fragen = [
            {"id": 1, "frage": "Feuer", "typ": "fakt", "erwartet": "-", "keywords": [],
             "seiten": [{"buch_id": "nord", "seite": 12}]},
            {"id": 2, "frage": "Feuer", "typ": "fakt", "erwartet": "-", "keywords": [],
             "seiten": [{"buch_id": "sued", "seite": 12}]},
            {"id": 3, "frage": "Gibt es Eis?", "typ": "leerstelle", "erwartet": "-", "keywords": [],
             "erwartet_verweigerung": True, "seiten": []}]

    def eval(self):
        with mock.patch.object(rag, "answer", lambda *a: "x"), contextlib.redirect_stdout(io.StringIO()):
            return rag.cmd_eval_spiele([SID])

    @unittest.skip("devloop: REQ-MB-7 noch nicht implementiert")
    def test_req_mb_7_treffer_nur_bei_passendem_buch(self):
        """[REQ-MB-7] Erwartet Seite 12 in nord, Treffer auf Seite 12 in sued -> verfehlt (Eval und messung/retrieval)."""
        self.schreibe_golden(self.fragen)
        saetze = self.eval()
        self.assertEqual([s["kategorie"] for s in saetze],
                         [rag.KAT_VERFEHLT, rag.KAT_GETROFFEN, rag.KAT_VERWEIGERUNG])
        retrieval = importlib.import_module("messung.retrieval")
        with contextlib.redirect_stdout(io.StringIO()):
            erg = retrieval.trefferquote(ausgabe=lambda *_: None)
        self.assertEqual(erg["je_spiel"], {SID: (1, 2)})
        self.assertEqual(erg["verfehlt"], [f"{SID}/1"])

    @unittest.skip("devloop: REQ-MB-7 noch nicht implementiert")
    def test_req_mb_7_seite_ohne_buch_ist_konfigfehler(self):
        """[REQ-MB-7] Golden Set eines Mehr-Buecher-Bestands mit Seite ohne Buch -> KonfigFehler in eval und messung."""
        fragen = [dict(self.fragen[1], seiten=[12])]
        self.schreibe_golden(fragen)
        with self.assertRaises(rag.KonfigFehler):
            self.eval()
        retrieval = importlib.import_module("messung.retrieval")
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(rag.KonfigFehler):
            retrieval.trefferquote(ausgabe=lambda *_: None)


# ===================================================================================
# B. Quelle ersetzen und inkrementell einbetten
# ===================================================================================
def lesezeichen_buch(bid, titel, fassung, quelle=None):
    """Buchdeklaration fuer einlesen.lies_buch_ein: Lesezeichen-Liste, gedruckt = physisch."""
    return buch(bid, titel, fassung, quelle=quelle, ueberschriften={"quelle": "lesezeichen"},
                seitenzahlen={"quelle": "versatz", "versatz": 0}, reparatur=True)


def seiten_eines_buchs(wort):
    return {1: [{"text": "Kapitel Eins", "klasse": "section_header"}, {"text": f"Feuer {wort} eins.", "klasse": "text"}],
            2: [{"text": "Kapitel Zwei", "klasse": "section_header"}, {"text": f"Wasser {wort} zwei.", "klasse": "text"}]}


LESEZEICHEN = [{"titel": "Kapitel Eins", "ebene": 1, "seite": 1}, {"titel": "Kapitel Zwei", "ebene": 1, "seite": 2}]


class TestErsetzen(ZweiBuecher):
    @unittest.skip("devloop: REQ-MB-8 noch nicht implementiert")
    def test_req_mb_8_ersetzte_fassung_nur_neue_haeppchen(self):
        """[REQ-MB-8] Neue Fassung fuer nord -> nur noch deren Haeppchen (auch FTS), genau diese eingebettet, sued nicht."""
        self.bestand([buch("nord", "Buch Nord", "alpha"), buch("sued", "Buch Sued", "beta")])
        self.schreibe_buch("nord", [eintrag("nord", i, 10 + i, f"Feuer altmarke nord{i}") for i in range(1, 4)])
        self.schreibe_buch("sued", sued())
        self.baue()
        sued_vorher = [z for z in self.zeilen() if z[0] == "sued"]
        self.bestand([buch("nord", "Buch Nord", "beta", quelle="nord-v2.pdf"), buch("sued", "Buch Sued", "beta")])
        neu = [eintrag("nord", i, 10 + i, f"Feuer neumarke nord{i}") for i in range(1, 5)]
        self.schreibe_buch("nord", neu)
        _, eingebettet = self.baue()
        self.assertEqual(len(eingebettet), len(neu))
        self.assertTrue(all("neumarke" in t for t in eingebettet), eingebettet)
        con = sqlite3.connect(self.index)
        self.addCleanup(con.close)

        def zahl(sql, *a):
            return con.execute(sql, a).fetchone()[0]
        self.assertEqual(zahl("SELECT count(*) FROM chunks WHERE buch_id='nord' AND fassung='alpha'"), 0)
        self.assertEqual(zahl("SELECT count(*) FROM chunks WHERE buch_id='nord' AND fassung='beta'"), len(neu))
        self.assertEqual(zahl("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH '\"altmarke\"'"), 0)
        self.assertEqual(zahl("SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH '\"neumarke\"'"), len(neu))
        self.assertEqual(zahl("SELECT count(*) FROM chunks_fts"), zahl("SELECT count(*) FROM chunks"))
        self.assertEqual([z for z in self.zeilen() if z[0] == "sued"], sued_vorher)

    @unittest.skip("devloop: REQ-MB-8 noch nicht implementiert")
    def test_req_mb_8_ueberschreiben_wirkt_nur_auf_das_genannte_buch(self):
        """[REQ-MB-8] Einlesen von nord ohne --ueberschreiben bricht ab; mit wirkt es nur auf nord (sued byte-gleich)."""
        einlesen = importlib.import_module("einlesen")
        self.bestand([lesezeichen_buch("nord", "Buch Nord", "alpha"), lesezeichen_buch("sued", "Buch Sued", "beta")])
        einlesen.lies_buch_ein(SID, "nord", seiten_eines_buchs("nordalt"), lesezeichen=LESEZEICHEN)
        einlesen.lies_buch_ein(SID, "sued", seiten_eines_buchs("suedwort"), lesezeichen=LESEZEICHEN)
        sued_vorher = hashes(os.path.join(self.data, SID, "buecher", "sued"))
        nord_vorher = hashes(os.path.join(self.data, SID, "buecher", "nord"))
        with self.assertRaises(rag.KonfigFehler):
            einlesen.lies_buch_ein(SID, "nord", seiten_eines_buchs("nordneu"), lesezeichen=LESEZEICHEN)
        self.assertEqual(hashes(os.path.join(self.data, SID, "buecher", "nord")), nord_vorher)
        einlesen.lies_buch_ein(SID, "nord", seiten_eines_buchs("nordneu"), lesezeichen=LESEZEICHEN,
                               ueberschreiben=True)
        self.assertEqual(hashes(os.path.join(self.data, SID, "buecher", "sued")), sued_vorher)
        with open(self.buchdatei("nord"), encoding="utf-8") as f:
            inhalt = f.read()
        self.assertIn("nordneu", inhalt)
        self.assertNotIn("nordalt", inhalt)

    @unittest.skip("devloop: REQ-MB-9 noch nicht implementiert")
    def test_req_mb_9_neues_buch_nur_dieses_eingebettet_dann_nichts(self):
        """[REQ-MB-9] Neues Buch -> nur dessen Haeppchen eingebettet; Lauf ohne Aenderung bettet nichts ein."""
        self.lege_zwei_an()
        self.baue()
        _, eingebettet = self.baue()
        self.assertEqual(eingebettet, [])
        self.bestand([buch("nord", "Buch Nord", "alpha"), buch("sued", "Buch Sued", "beta", sprache="en",
                                                              inhaltsart="welt"),
                      buch("west", "Buch West", "gamma")])
        west = [eintrag("west", 1, 3, "Feuer westeins"), eintrag("west", 2, 4, "Erde westzwei")]
        self.schreibe_buch("west", west)
        _, eingebettet = self.baue()
        self.assertEqual(len(eingebettet), len(west))
        self.assertTrue(all("west" in t for t in eingebettet), eingebettet)
        _, eingebettet = self.baue()
        self.assertEqual(eingebettet, [])

    @unittest.skip("devloop: REQ-MB-9 noch nicht implementiert")
    def test_req_mb_9_einlesen_laesst_andere_buecher_byte_gleich(self):
        """[REQ-MB-9] Einlesen eines Buchs laesst die Dateien der anderen Buecher byte-gleich."""
        einlesen = importlib.import_module("einlesen")
        self.bestand([lesezeichen_buch("nord", "Buch Nord", "alpha"), lesezeichen_buch("sued", "Buch Sued", "beta"),
                      lesezeichen_buch("west", "Buch West", "gamma")])
        einlesen.lies_buch_ein(SID, "nord", seiten_eines_buchs("nordwort"), lesezeichen=LESEZEICHEN)
        einlesen.lies_buch_ein(SID, "sued", seiten_eines_buchs("suedwort"), lesezeichen=LESEZEICHEN)
        vorher = {b: hashes(os.path.join(self.data, SID, "buecher", b)) for b in ("nord", "sued")}
        self.assertTrue(all(vorher.values()))
        einlesen.lies_buch_ein(SID, "west", seiten_eines_buchs("westwort"), lesezeichen=LESEZEICHEN)
        for b in ("nord", "sued"):
            self.assertEqual(hashes(os.path.join(self.data, SID, "buecher", b)), vorher[b], b)
        self.assertTrue(os.path.exists(self.buchdatei("west")))
        _, eingebettet = self.baue()
        self.assertTrue(eingebettet)
        _, eingebettet = self.baue()
        self.assertEqual(eingebettet, [])


class TestKaputteDeklaration(ZweiBuecher):
    def kaputt(self, deklaration, dateien=None):
        """Gueltigen Stand bauen, Deklaration verderben -> index bricht ab, Index-Inhalt bleibt."""
        self.lege_zwei_an()
        alt = self.lege_alt_an()
        self.baue()
        vorher = self.zeilen()
        self.bestand(deklaration)
        for bid, eintraege in (dateien or {}).items():
            self.schreibe_buch(bid, eintraege)
        with self.assertRaises(rag.KonfigFehler):
            rag.aktualisiere_index([SID], ausgabe=lambda *_: None)
        self.assertEqual(self.zeilen(), vorher)
        # wie heute bei kaputten Spielen: --alle meldet ihn, die uebrigen laufen weiter
        rag.schreibe_jsonl(rag.knowledge_pfad(alt), ALT + [dict(ALT[0], id=4, seite=40, text="Neue Altregel.")])
        with self.assertRaises(rag.KonfigFehler) as ctx:
            rag.aktualisiere_index(ausgabe=lambda *_: None)
        self.assertEqual(ctx.exception.ergebnis[SID][0], "fehler")
        self.assertEqual(ctx.exception.ergebnis[alt][0], "neu")
        self.assertEqual(self.zeilen(), vorher)

    @unittest.skip("devloop: REQ-MB-10 noch nicht implementiert")
    def test_req_mb_10_doppelte_buch_id(self):
        """[REQ-MB-10] Doppelte buch_id in der Deklaration -> KonfigFehler, alter Stand bleibt."""
        self.kaputt([buch("nord", "Buch Nord", "alpha"), buch("nord", "Buch Nord Zwei", "beta", quelle="anders.pdf"),
                     buch("sued", "Buch Sued", "beta", sprache="en", inhaltsart="welt")])

    @unittest.skip("devloop: REQ-MB-10 noch nicht implementiert")
    def test_req_mb_10_gleiche_quelldatei(self):
        """[REQ-MB-10] Zwei Buecher nennen dieselbe Quelldatei -> KonfigFehler, alter Stand bleibt."""
        self.kaputt([buch("nord", "Buch Nord", "alpha", quelle="gemeinsam.pdf"),
                     buch("sued", "Buch Sued", "beta", sprache="en", inhaltsart="welt", quelle="gemeinsam.pdf")])

    @unittest.skip("devloop: REQ-MB-10 noch nicht implementiert")
    def test_req_mb_10_nicht_deklarierte_buch_id_im_haeppchen(self):
        """[REQ-MB-10] Haeppchen mit nicht deklarierter buch_id -> KonfigFehler, alter Stand bleibt."""
        self.kaputt([buch("nord", "Buch Nord", "alpha"), buch("sued", "Buch Sued", "beta", sprache="en",
                                                             inhaltsart="welt")],
                    {"nord": nord() + [eintrag("west", 7, 70, "Feuer fremd")]})

    @unittest.skip("devloop: REQ-MB-10 noch nicht implementiert")
    def test_req_mb_10_buch_id_ohne_slug(self):
        """[REQ-MB-10] buch_id bildet keinen Slug (gleiche Regel wie spiel_id): "Buch A", "../x" -> KonfigFehler, alter Stand bleibt."""
        for schlecht in ("Buch A", "../x"):
            with self.subTest(buch_id=schlecht):
                self.kaputt([buch("nord", "Buch Nord", "alpha"),
                             buch(schlecht, "Buch Sued", "beta", sprache="en", inhaltsart="welt", quelle="sued.pdf")])
                self.assertFalse(os.path.exists(os.path.join(self.data, "x")))
                self.assertFalse(os.path.exists(os.path.join(self.data, SID, "buecher", "Buch A")))

    @unittest.skip("devloop: REQ-MB-10 noch nicht implementiert")
    def test_req_mb_10_sprache_nicht_in_sprachen(self):
        """[REQ-MB-10] sprache "xx" (nicht in rag.SPRACHEN) -> KonfigFehler, alter Stand bleibt."""
        self.assertNotIn("xx", rag.SPRACHEN)
        self.kaputt([buch("nord", "Buch Nord", "alpha"), buch("sued", "Buch Sued", "beta", sprache="xx",
                                                             inhaltsart="welt")])


class TestPipeVeraltet(ZweiBuecher):
    @unittest.skip("devloop: REQ-MB-26 noch nicht implementiert")
    def test_req_mb_26_geaenderte_zweite_buchdatei_meldet_veraltet(self):
        """[REQ-MB-26] Index gebaut; Buchdatei sued (nicht die erste) geaendert -> Pipe meldet veraltet; unveraendert -> nicht."""
        self.lege_zwei_an()
        self.baue()
        p = self.pipe(top_k=2)
        text = self.frage_pipe(p, "Feuer")
        self.assertNotIn("veraltet", text)
        self.assertNotIn("Fehler", text)
        self.assertEqual(len(self.llm_bekam), 1)
        self.schreibe_buch("sued", sued() + [eintrag("sued", 9, 19, "Wasser suedneu")])     # nach dem Bau
        text = self.frage_pipe(p, "Feuer")
        self.assertIn("veraltet", text)
        self.assertEqual(len(self.llm_bekam), 1, "aus veraltetem Index geantwortet")
        self.baue()
        text = self.frage_pipe(p, "Feuer")
        self.assertNotIn("veraltet", text)
        self.assertEqual(len(self.llm_bekam), 2)


# ===================================================================================
# E. Nicht-funktional
# ===================================================================================
class TestSynthetisch(FassungsTest):
    """REQ-MB-17: dasselbe Szenario mit umbenannten Bezeichnern liefert dasselbe Ergebnis."""
    NAMEN_A = {"sid": "testwelt", "name": "Testwelt", "buecher": ("ba", "bb", "bg"),
               "titel": ("Erstes Testbuch", "Zweites Testbuch", "Drittes Testbuch"),
               "fassungen": ("alpha", "beta", "gamma"), "hinweis": HINWEIS, "pfade": ("Regeln", "Welt"),
               "arten": ("regel", "welt")}
    NAMEN_B = {"sid": "andere-welt", "name": "Andere Welt", "buecher": ("rot", "gruen", "blau"),
               "titel": ("Rotes Heft", "Gruenes Heft", "Blaues Heft"),
               "fassungen": ("v7", "v8", "v9"), "hinweis": "Ausgabe v8 -- bitte umrechnen", "pfade": ("Satzung", "Kunde"),
               "arten": ("satzung", "kunde")}                        # Inhaltsart-Vokabular ist frei (Lesart)

    def szenario(self, n):
        verz = os.path.join(self.tmp.name, n["sid"])
        index = os.path.join(verz, "index.sqlite")
        with mock.patch.multiple(rag, DATA_DIR=verz, INDEX_PATH=index):
            self.data, self.index = verz, index
            regeln = {n["arten"][0]: {"massgeblich": [n["fassungen"][0]],
                                      "gekennzeichnet": {n["fassungen"][1]: n["hinweis"]}}}
            self.bestand([buch(b, t, f, inhaltsart=n["arten"][0], inhaltsarten=[((n["pfade"][1],), n["arten"][1])])
                          for b, t, f in zip(n["buecher"], n["titel"], n["fassungen"])], regeln,
                         sid=n["sid"], name=n["name"])
            for b, (r, w) in zip(n["buecher"], (("mkar", "mkaw"), ("mkbr", "mkbw"), ("mkgr", "mkgw"))):
                self.schreibe_buch(b, [eintrag(b, 1, SEITE[r], VERSCHIEDEN[r], (n["pfade"][0],), n["sid"], n["name"]),
                                       eintrag(b, 2, SEITE[w], VERSCHIEDEN[w], (n["pfade"][1],), n["sid"], n["name"])],
                                   sid=n["sid"])
            self.baue()
            erg = {}
            for hybrid in (False, True):
                with mock.patch.object(rag, "HYBRID", hybrid):
                    hits = self.suche("Feuer", 6, sid=n["sid"])
                    gefiltert = self.suche("Feuer", 6, sid=n["sid"], filter={"buch_id": n["buecher"][1]})
                    art = self.suche("Feuer", 6, sid=n["sid"], filter={"inhaltsart": n["arten"][1]})
                erg[hybrid] = ([(kennung(h, ROLLEN), round(s, 6), n["hinweis"] in rag.fundstelle(h)) for h, s in hits],
                               [kennung(h, ROLLEN) for h, _ in gefiltert], [kennung(h, ROLLEN) for h, _ in art])
            return erg

    @unittest.skip("devloop: REQ-MB-17 noch nicht implementiert")
    def test_req_mb_17_umbenennen_aendert_kein_ergebnis(self):
        """[REQ-MB-17] Bestand, Buecher, Titel, Fassungen, Hinweis, Pfade, Inhaltsarten umbenannt -> gleiche Treffer, Scores, Hinweise, Filter."""
        a = self.szenario(self.NAMEN_A)
        b = self.szenario(self.NAMEN_B)
        self.assertEqual(a, b)
        self.assertEqual([r for r, _, _ in a[False][0]], ["mkbr", "mkar", "mkgw", "mkaw", "mkbw"])
        self.assertEqual([r for r, _, h in a[False][0] if h], ["mkbr"])
        self.assertEqual(a[False][1], ["mkbr", "mkbw"])
        self.assertEqual(a[False][2], ["mkgw", "mkaw", "mkbw"])


class TestSchutzBuecher(unittest.TestCase):
    """REQ-MB-18: Einlesen + Indexbau eines Buchs unter testumgebung schreibt nichts neben den Code.

    In einer Repo-Kopie (Mechanik aus test_schutz.py): das Skript liest ein Buch ein und baut den
    Index. Geprueft wird die Wirkung -- jede Datei der Kopie vorher/nachher. Gegenprobe: ohne
    testumgebung landen die Buecherdateien in der Kopie, und genau das sieht der Detektor."""
    SKRIPT = r'''
import json, os, sys
import numpy as np
import testumgebung
import rag, einlesen
rag.embed = lambda texte: np.array([[1.0, float(len(t) % 7), 0.5] for t in texte], dtype=np.float32)
sid = "testwelt"
verz = os.path.join(rag.DATA_DIR, sid)
os.makedirs(verz, exist_ok=True)
with open(os.path.join(verz, "spiel.json"), "w", encoding="utf-8") as f:
    json.dump({"spiel_id": sid, "name": "Testwelt", "aliase": [], "sprache": "de", "quelle_pdf": None,
               "buecher": [{"buch_id": "nord", "titel": "Buch Nord", "fassung": "alpha", "sprache": "de",
                            "quelle": "nord.pdf", "inhaltsart": "regel", "ueberschriften": {"quelle": "lesezeichen"},
                            "seitenzahlen": {"quelle": "versatz", "versatz": 0}, "reparatur": True}]}, f)
seiten = {1: [{"text": "Kapitel Eins", "klasse": "section_header"}, {"text": "Ein Satz.", "klasse": "text"}]}
einlesen.lies_buch_ein(sid, "nord", seiten, lesezeichen=[{"titel": "Kapitel Eins", "ebene": 1, "seite": 1}])
rag.aktualisiere_index([sid], ausgabe=lambda *_: None)
print(os.path.exists(os.path.join(verz, "buecher", "nord", "knowledge.jsonl")))
'''

    def setUp(self):
        import test_schutz
        self.kopie = test_schutz.Kopie("setUp")
        self.kopie.setUp()
        self.addCleanup(self.kopie.doCleanups)

    def stand(self):
        out = {}
        for wurzel, verze, dateien in os.walk(self.kopie.repo):
            verze[:] = [v for v in verze if v != "__pycache__"]
            for d in dateien:
                p = os.path.join(wurzel, d)
                with open(p, "rb") as f:
                    out[os.path.relpath(p, self.kopie.repo)] = hashlib.sha256(f.read()).hexdigest()
        return out

    @unittest.skip("devloop: REQ-MB-18 noch nicht implementiert")
    def test_req_mb_18_buecherdateien_nie_neben_dem_code(self):
        """[REQ-MB-18] Einlesen + index unter testumgebung: Repo-Kopie unveraendert; ohne testumgebung sieht der Detektor die Schreibzugriffe."""
        vorher = self.stand()
        p = self.kopie.lauf("-c", self.SKRIPT)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "True", "Buchdatei nicht im Temp-DATA_DIR -- Skript hat nichts eingelesen")
        self.assertEqual(self.stand(), vorher, "Einlesen/Index schrieb neben den Code")
        # Gegenprobe (Mutation: Schutzschicht testumgebung aus) -- dann landen Buecherdateien in der Kopie
        self.kopie.ohne_testumgebung()
        vorher = self.stand()
        p = self.kopie.lauf("-c", self.SKRIPT)
        self.assertEqual(p.returncode, 0, p.stderr)
        neu = sorted(set(self.stand()) - set(vorher))
        self.assertTrue(any(n.startswith(os.path.join("data", "testwelt", "buecher")) for n in neu), neu)


# Letzter Stand von rag.py vor dieser Spec (merge-base des Spec-Branches mit main). Bewusst ein
# fester Commit: "HEAD von main" waere nach dem Merge schon der neue Code.
BASIS_COMMIT = "7bf921215086e43420060d2ebbe6e43a148c083b"


def lade_basis_rag(verz):
    """rag.py aus BASIS_COMMIT als eigenes Modul -- der echte alte Ladepfad, keine Nachbildung."""
    p = subprocess.run(["git", "-C", BASE, "show", f"{BASIS_COMMIT}:rag.py"], capture_output=True, text=True)
    if p.returncode:
        raise AssertionError(f"Basis {BASIS_COMMIT} nicht lesbar (Clone ohne Historie?): {p.stderr.strip()}")
    pfad = os.path.join(verz, "rag_vor_spec.py")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(p.stdout)
    spec = importlib.util.spec_from_file_location("rag_vor_spec", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class TestPerformance(BestandTest):
    """REQ-MB-19: Laden + Vektorsuche je Frage, 5 Buecher / 3.000 Haeppchen / 1.024 Dimensionen,
    Filter und Fassungsregel aktiv. Ausgabe: typisch (Median) und Maximum ueber 200 Fragen
    (nach einer nicht gezaehlten Aufwaerm-Frage)."""
    DIM = 1024

    def setUp(self):
        super().setUp()

        def zufall(texte):
            out = []
            for t in texte:
                seed = int.from_bytes(hashlib.sha256(t.encode()).digest()[:8], "little")
                out.append(np.random.default_rng(seed).standard_normal(self.DIM).astype(np.float32))
            return np.array(out, dtype=np.float32)
        p = mock.patch.object(rag, "embed", zufall)
        p.start()
        self.addCleanup(p.stop)

    @staticmethod
    def miss(fn, n=200):
        fn(-1)
        zeiten = []
        for i in range(n):
            t = time.perf_counter()
            fn(i)
            zeiten.append((time.perf_counter() - t) * 1000)
        return statistics.median(zeiten), max(zeiten)

    @unittest.skip("devloop: REQ-MB-19 noch nicht implementiert")
    def test_req_mb_19_mehrbuch_bestand_typisch_15_max_45_ms(self):
        """[REQ-MB-19] 5 Buecher, 3.000 Haeppchen, 1.024 Dim., Filter + Fassungsregel: typisch <= 15 ms, Maximum <= 45 ms."""
        fassungen = ("alpha", "alpha", "beta", "gamma", "gamma")
        self.bestand([buch(f"buch{i}", f"Testbuch {i}", f, inhaltsarten=[(("Welt",), "welt")])
                      for i, f in enumerate(fassungen)], REGELN)
        for i in range(5):
            self.schreibe_buch(f"buch{i}", [eintrag(f"buch{i}", j, j // 3 + 1, f"Regeltext {i}-{j} " * 8,
                                                    ("Welt",) if j % 2 else ("Regeln",)) for j in range(600)])
        self.baue()
        con = self.oeffne()
        self.assertEqual(con.execute("SELECT count(*) FROM chunks WHERE spiel_id=?", (SID,)).fetchone()[0], 3000)
        filt = {"sprache": "de"}
        hits = rag.retrieve("Frage 0", k=4, spiel_id=SID, index=con, filter=filt)
        self.assertEqual(len(hits), 4)
        self.assertTrue(all(not (h["fassung"] == "gamma" and h["inhaltsart"] == "regel") for h, _ in hits))
        typ, mx = self.miss(lambda i: rag.retrieve(f"Frage {i}", k=4, spiel_id=SID, index=con, filter=filt))
        print(f"\n  REQ-MB-19 Mehr-Buecher (3000 Haeppchen, 1024 Dim.): typisch {typ:.2f} ms, max {mx:.2f} ms")
        self.assertLessEqual(typ, 15.0)
        self.assertLessEqual(mx, 45.0)

    @unittest.skip("devloop: REQ-MB-19 noch nicht implementiert")
    def test_req_mb_19_altbestand_hoechstens_20_prozent_ueber_dem_stand_vor_der_spec(self):
        """[REQ-MB-19] Altbestand 2.000 Haeppchen, 1.024 Dim.: typisch und Maximum <= 1,2 x Basis (rag.py vor der Spec, selber Lauf)."""
        meta = rag.lege_spiel_an("Altspiel")
        rag.schreibe_jsonl(rag.knowledge_pfad(meta["spiel_id"]),
                           [{"id": j, "seite": j // 10 + 1, "typ": "regel", "text": f"Regel {j} " * 20,
                             "spiel": "Altspiel", "spiel_id": "altspiel"} for j in range(2000)])
        self.baue()
        con = self.oeffne()
        basis = lade_basis_rag(self.tmp.name)
        with mock.patch.multiple(basis, embed=rag.embed, CHUNK_SIZE=400, CHUNK_OVERLAP=150, EMBED_MODEL="bge-m3",
                                 HYBRID=False, RERANK=False, OLLAMA="http://stub"):
            def alt(i):
                return basis.retrieve(f"Frage {i}", k=4, spiel_id="altspiel", index=con)

            def neu(i):
                return rag.retrieve(f"Frage {i}", k=4, spiel_id="altspiel", index=con)
            for i in range(3):          # gleiche Treffer -- sonst waere der Vergleich keiner
                self.assertEqual([(h["seite"], h["text"], round(s, 6)) for h, s in neu(i)],
                                 [(h["seite"], h["text"], round(s, 6)) for h, s in alt(i)])
            (typ_a, max_a), (typ_n, max_n) = self.miss_paar(alt, neu)
        print(f"\n  REQ-MB-19 Altbestand (2000 Haeppchen, 1024 Dim.): Basis typisch {typ_a:.2f} ms, max {max_a:.2f} ms;"
              f" neu typisch {typ_n:.2f} ms, max {max_n:.2f} ms")
        self.assertLessEqual(typ_n, 1.2 * typ_a)
        self.assertLessEqual(max_n, 1.2 * max_a)

    @staticmethod
    def miss_paar(fa, fb, n=200):
        """Basis und neuer Code abwechselnd (Reihenfolge je Frage getauscht), GC aus: Drift und
        Aufwaermen treffen beide gleich. Rueckgabe: ((typisch, max) Basis, (typisch, max) neu)."""
        fa(-1)
        fb(-1)
        ta, tb = [], []
        gc.collect()
        gc.disable()
        try:
            for i in range(n):
                for f, t in (((fa, ta), (fb, tb)) if i % 2 == 0 else ((fb, tb), (fa, ta))):
                    s = time.perf_counter()
                    f(i)
                    t.append((time.perf_counter() - s) * 1000)
        finally:
            gc.enable()
        return (statistics.median(ta), max(ta)), (statistics.median(tb), max(tb))

class TestVorabmessung(unittest.TestCase):
    """REQ-MB-23: Messergebnis der Extraktion liegt im Spec-Ordner -- nur Zahlen, kein Buchtext."""
    PFAD = os.path.join(BASE, ".specify", "specs", "mehrbuch-bestand", "vorabmessung.json")
    SCHLUESSEL = {"docling_version", "seiten", "zweispalten_mit_tabelle", "talentseiten", "L", "T", "H"}

    @unittest.skip("devloop: REQ-MB-23 noch nicht implementiert")
    def test_req_mb_23_messergebnis_strukturell(self):
        """[REQ-MB-23] vorabmessung.json: 10 Seiten (>= 3 zweispaltig mit Tabelle, >= 2 Talentseiten), L/T/H, Docling-Version, nur Zahlen."""
        with open(self.PFAD, encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(set(m), self.SCHLUESSEL)
        self.assertRegex(m["docling_version"], r"^\d+\.\d+(\.\d+)?$")
        seiten = m["seiten"]
        self.assertEqual(len(seiten), 10)
        self.assertEqual(len(set(seiten)), 10)
        self.assertTrue(all(type(s) is int and s > 0 for s in seiten))
        self.assertGreaterEqual(len(m["zweispalten_mit_tabelle"]), 3)
        self.assertGreaterEqual(len(m["talentseiten"]), 2)
        self.assertLessEqual(set(m["zweispalten_mit_tabelle"]), set(seiten))
        self.assertLessEqual(set(m["talentseiten"]), set(seiten))
        self.assertEqual(set(m["L"]), {"richtig", "absaetze"})
        self.assertLessEqual(m["L"]["richtig"], m["L"]["absaetze"])
        self.assertIs(type(m["T"]), int)
        self.assertEqual(set(m["H"]), {"erkannt", "vorhanden", "fehltreffer"})
        self.assertLessEqual(m["H"]["erkannt"], m["H"]["vorhanden"])

        def blaetter(x):
            if isinstance(x, dict):
                for v in x.values():
                    yield from blaetter(v)
            elif isinstance(x, list):
                for v in x:
                    yield from blaetter(v)
            else:
                yield x
        # Kein Buchtext (REQ-MB-18): ausser der Versionsangabe nur ganze Zahlen
        rest = dict(m)
        rest.pop("docling_version")
        self.assertTrue(all(type(b) is int for b in blaetter(rest)), list(blaetter(rest)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
