"""
title: Brettspiel-Regeln (RAG)
description: Beantwortet Regelfragen aus dem Index (viele Spiele) oder knowledge.jsonl mit derselben Retrieval-Logik wie rag.py.
version: 0.4.0

Open-WebUI-Pipe: erscheint in der Modellauswahl als eigenes Modell. Die Logik
(Chunking, Embedding, Retrieval, Prompt) kommt aus rag.py -- diese Datei laedt
rag.py zur Laufzeit aus RAG_DIR und reicht nur durch. Mit denselben Werten fuer
CHUNK_SIZE, CHUNK_OVERLAP, DROP_TYPES und TOP_K misst `rag.py eval` also dieselbe
Pipeline, die im Chat antwortet.

Zwei Betriebsarten, per Valve INDEX_PATH gewaehlt:
  - INDEX_PATH leer (Default): der alte Ein-Spiel-Weg. Die Pipe liest
    KNOWLEDGE_PATH und bettet selbst ein; das Spiel steht in den Valves SPIEL/SPIEL_ALIASE.
  - INDEX_PATH gesetzt: der persistente Index aus `rag.py index` (read-only).
    Gesucht wird nur im zugeordneten Spiel; die Zuordnung laeuft gegen Name und
    Aliase ALLER Spiele im Index. Die Pipe bettet nur noch die Frage ein.

Bewusst async: Open WebUI ruft eine synchrone Pipe direkt im Event-Loop auf,
eine blockierende Pipe wuerde die Oberflaeche fuer alle einfrieren, solange das
Modell rechnet. Die requests-basierten rag.py-Funktionen laufen deshalb per
asyncio.to_thread, die Antwort streamt ueber httpx.
"""
import asyncio
import importlib.util
import json
import os
import re
import threading

import httpx
from pydantic import BaseModel, Field

FUSSZEILE_START = "\n\n---\n*Abgerufen: "
# Am Antwortende verankert -- Nutzertext, der so aussieht, bleibt unangetastet.
# Das fuehrende "\n\n" ist optional: Open WebUI strippt den letzten Textteil, bei
# leerer Modellantwort steht die Fusszeile dann ohne Leerzeilen da.
_FUSSZEILE = re.compile(r"(?:\n\n)?---\n\*Abgerufen: [^\n]*\*\s*\Z")
_FEHLERZEILE = re.compile(r"(?:\n\n)?\*\*Fehler in der RAG-Pipe:\*\*.*\Z", re.S)


# ---------- reine Helfer (ohne Netz, testbar) ----------
def text_von(inhalt):
    """Nachrichteninhalt als Text -- Open WebUI schickt bei Anhaengen eine Liste von Teilen."""
    if isinstance(inhalt, list):
        return " ".join(t.get("text", "") for t in inhalt if isinstance(t, dict) and t.get("type") == "text")
    return inhalt or ""


def ohne_fusszeile(text):
    """Eigene Fundstellen- oder Fehlerzeile vom Ende einer frueheren Antwort entfernen.

    Open WebUI speichert sie als Teil der Assistant-Antwort. Ginge die Fusszeile im
    Verlauf mit, saehe das Modell Seitenzahlen ohne deren Text -- der Systemprompt
    verlangt aber, nur bereitgestellte Quellen zu zitieren.
    """
    return _FEHLERZEILE.sub("", _FUSSZEILE.sub("", text))


def zerlege_verlauf(messages):
    """(frage, verlauf): letzte Nutzernachricht und die Wortwechsel davor.

    Retrieval laeuft nur auf der letzten Frage. Der Verlauf geht ohne seine alten
    Quellen mit, damit Rueckfragen ("und bei zwei Spielern?") verstanden werden.
    System-Nachrichten (Systemprompt aus Modell- oder Nutzereinstellungen) fallen
    weg: Der Regel-Systemprompt aus rag.py gilt allein.
    """
    letzte = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=None)
    if letzte is None:
        return "", []
    verlauf = []
    for m in messages[:letzte]:
        if m.get("role") == "user":
            verlauf.append({"role": "user", "content": text_von(m.get("content"))})
        elif m.get("role") == "assistant":
            verlauf.append({"role": "assistant", "content": ohne_fusszeile(text_von(m.get("content")))})
    return text_von(messages[letzte].get("content")).strip(), verlauf


def setze_verlauf_ein(nachrichten, verlauf):
    """Verlauf zwischen Systemprompt und die Quellen-Frage schieben."""
    return nachrichten[:1] + verlauf + nachrichten[1:]


def fundstellen(hits):
    """Fusszeile wie bei `rag.py ask`: welche Seiten wirklich im Kontext lagen."""
    teile = [f"S. {h['seite']} ({s:.3f})" for h, s in hits]
    return FUSSZEILE_START + ", ".join(teile) + "*"


def ollama_zeile(zeile):
    """Eine NDJSON-Zeile von /api/chat -> Textstueck ('' wenn keins)."""
    if not zeile.strip():
        return ""
    d = json.loads(zeile)
    if "error" in d:
        raise RuntimeError(f"Ollama: {d['error']}")
    return (d.get("message") or {}).get("content", "")


# Spielzuordnung (normalisiere, katalog_aus, katalog_aus_index, ordne_spiel) liegt in
# rag.py: dieselbe Zuordnung fuer Pipe und CLI (`rag.py ask --spiel`, `eval`).


def datei_stand(pfad):
    """Aenderungsmerkmal einer Datei. mtime allein reicht nicht: `cp -p` oder ein
    Restore schreiben neuen Inhalt mit alter mtime."""
    st = os.stat(pfad)
    return (st.st_mtime_ns, st.st_size, st.st_ino)


# ---------- Pipe ----------
class Pipe:
    class Valves(BaseModel):
        RAG_DIR: str = Field("/rag/code", description="Ordner mit rag.py (Repo-Clone, read-only gemountet)")
        KNOWLEDGE_PATH: str = Field("/rag/data/knowledge.jsonl", description="Wissensbasis, gemountet")
        OLLAMA_URL: str = Field("http://ollama:11434", description="Ollama aus Sicht des Containers")
        EMBED_MODEL: str = "bge-m3"
        LLM_MODEL: str = "qwen3:14b"
        # Defaults = die in der README gemessene Konfiguration
        CHUNK_SIZE: int = Field(400, ge=1, description="Zeichen pro Chunk (wie CHUNK_SIZE bei rag.py)")
        CHUNK_OVERLAP: int = Field(150, ge=0, description="Ueberlappung (wie CHUNK_OVERLAP bei rag.py)")
        TOP_K: int = Field(4, ge=1)
        DROP_TYPES: str = Field("flavor,meta", description="Chunk-Typen, die nicht in den Index gehen (regel, flavor, meta)")
        THINK: bool = False
        # Welches Spiel knowledge.jsonl beschreibt -- fuer Anfragen mit "regelfrage.spiel"
        # (Home Assistant). Solange es eine Wissensbasis gibt, ist das ein Eintrag.
        SPIEL: str = "Food Chain Magnate"
        SPIEL_ALIASE: str = Field("Food Chain, FCM", description="Kurzformen, kommagetrennt")
        # Viele Spiele: persistenter Index aus `rag.py index`. Gesetzt schaltet er die
        # Pipe auf den Index-Weg; SPIEL/SPIEL_ALIASE und KNOWLEDGE_PATH gelten dann nicht.
        INDEX_PATH: str = Field("", description="z.B. /rag/data/index.sqlite; leer = Ein-Spiel-Weg ueber KNOWLEDGE_PATH")
        STANDARD_SPIEL: str = Field("", description="spiel_id fuer Anfragen ohne regelfrage.spiel; leer = nur bei genau einem Spiel im Index")
        HYBRID: bool = Field(False, description="Vektor + BM25 (nur Index-Weg), wie HYBRID=1 bei rag.py")
        CACHE_SPIELE: int = Field(16, ge=1, description="so viele Spiele haelt die Pipe im Speicher")

    def __init__(self):
        self.valves = self.Valves()
        self._lock = threading.Lock()
        self._rag = None
        self._rag_key = None
        self._index = None
        self._index_key = None
        self._spiel_cache = {}      # key -> (chunks, embs), Einfuegereihenfolge = LRU
        self._katalog = None
        self._katalog_key = None

    # rag.py neu laden, wenn es sich geaendert hat (git pull im gemounteten Clone)
    def _lade_rag(self, v):
        pfad = os.path.join(v.RAG_DIR, "rag.py")
        key = (pfad, datei_stand(pfad))
        if key != self._rag_key:
            spec = importlib.util.spec_from_file_location("boardgame_rag", pfad)
            modul = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modul)
            self._rag, self._rag_key, self._index_key = modul, key, None
        # rag.py liest seine Konfiguration beim Import aus os.environ -- das ist hier
        # die Umgebung von Open WebUI, die CHUNK_SIZE/CHUNK_OVERLAP fuer ihre eigene
        # Dokumentsuche benutzt. Deshalb alles, was wirkt, explizit aus den Valves.
        rag = self._rag
        rag.OLLAMA = v.OLLAMA_URL
        rag.EMBED_MODEL = v.EMBED_MODEL
        rag.CHUNK_SIZE = v.CHUNK_SIZE
        rag.CHUNK_OVERLAP = v.CHUNK_OVERLAP
        rag.RERANK = False  # braucht torch, das im Open-WebUI-Image fehlt
        rag.HYBRID = v.HYBRID  # nie aus der Container-Umgebung
        return rag

    def _lade_index(self, rag, v):
        key = (self._rag_key, v.KNOWLEDGE_PATH, datei_stand(v.KNOWLEDGE_PATH),
               v.DROP_TYPES, v.EMBED_MODEL, v.OLLAMA_URL, v.CHUNK_SIZE, v.CHUNK_OVERLAP)
        if key != self._index_key:
            # Gleiche Validierung wie die CLI mit SOURCE=knowledge
            drop = rag.lies_drop_types({"SOURCE": "knowledge", "DROP_TYPES": v.DROP_TYPES})
            with open(v.KNOWLEDGE_PATH) as f:
                roh = [json.loads(z) for z in f if z.strip()]
            chunks = rag.baue_knowledge_chunks(roh, drop)
            if not chunks:
                raise ValueError(f"Index leer: {v.KNOWLEDGE_PATH} enthaelt nach DROP_TYPES={v.DROP_TYPES!r} keinen Chunk.")
            embs = rag.l2norm(rag.embed([c["text"] for c in chunks]))
            self._index, self._index_key = (chunks, embs), key
        return self._index

    def _suche(self, frage, v):
        # Auch retrieve gehoert unter den Lock: es bettet die Frage mit den Modul-
        # Globalen OLLAMA/EMBED_MODEL ein, die _lade_rag fuer die Valves DIESER
        # Anfrage gesetzt hat. Ausserhalb koennte eine parallele Anfrage mit anderen
        # Valves sie umsetzen -> Frage mit Modell B gegen Index aus Modell A.
        with self._lock:
            rag = self._lade_rag(v)
            chunks, embs = self._lade_index(rag, v)
            hits = rag.retrieve(frage, chunks, embs, k=v.TOP_K)
        return rag.baue_nachrichten(frage, hits), hits

    def _rag_fuer(self, v):
        with self._lock:
            return self._lade_rag(v)

    # ---------- Index-Weg (viele Spiele) ----------
    def _lade_katalog(self, rag, v):
        """Katalog aller Spiele im Index, neu gelesen, wenn sich die Indexdatei aendert."""
        key = (self._rag_key, v.INDEX_PATH, datei_stand(v.INDEX_PATH))
        if key != self._katalog_key:
            con = rag.oeffne_index(v.INDEX_PATH)
            try:
                spiele = rag.spiele_im_index(con)
            finally:
                con.close()
            katalog, ids = rag.katalog_aus_index(spiele)
            self._katalog, self._katalog_key = (spiele, katalog, ids, rag.chat_woerterbuch(katalog)), key
        return self._katalog

    def _waehle_spiel(self, anfrage, v):
        """(spiel_id, None) oder (None, Meldung) -- ohne Suche und ohne LLM."""
        with self._lock:
            rag = self._lade_rag(v)
            spiele, katalog, ids, _ = self._lade_katalog(rag, v)
        if not spiele:
            return None, "Im Index ist noch kein Spiel. Erst `python rag.py index --alle` laufen lassen."
        namen = [s["name"] for s in spiele]
        verfuegbar = ", ".join(namen) if len(namen) <= 10 else f"{len(namen)} Spiele"
        if anfrage is None:
            if v.STANDARD_SPIEL:
                if v.STANDARD_SPIEL not in ids.values():
                    return None, f"STANDARD_SPIEL {v.STANDARD_SPIEL!r} ist nicht im Index."
                return v.STANDARD_SPIEL, None
            if len(spiele) == 1:
                return spiele[0]["spiel_id"], None
            return None, f"{rag.RUECKFRAGE} Im Index: {verfuegbar}."
        status, ergebnis = rag.ordne_spiel(anfrage, katalog)
        if status == "treffer":
            return ids[ergebnis], None
        vorschlag = f" Meintest du {' oder '.join(ergebnis[:3])}?" if ergebnis else ""
        return None, f"Zu „{anfrage}“ habe ich kein Regelheft.{vorschlag} Verfuegbar: {verfuegbar}."

    def _lade_spiel(self, rag, v, spiel_id, con):
        """(chunks, embs) eines Spiels aus dem Index, mit Cache und Veraltet-Pruefung.

        Liegt die knowledge.jsonl des Spiels neben dem Index (data/ gemountet), wird
        ihr Fingerprint gegen den gespeicherten Stand geprueft: ein veralteter Index
        ist ein sichtbarer Fehler, keine stille Antwort aus altem Material.
        """
        data_dir = os.path.dirname(os.path.abspath(v.INDEX_PATH))
        wissen = rag.knowledge_pfad(spiel_id, data_dir)
        stand_wissen = datei_stand(wissen) if os.path.exists(wissen) else None
        key = (self._rag_key, v.INDEX_PATH, datei_stand(v.INDEX_PATH), spiel_id, stand_wissen,
               v.DROP_TYPES, v.EMBED_MODEL, v.CHUNK_SIZE, v.CHUNK_OVERLAP)
        if key in self._spiel_cache:
            self._spiel_cache[key] = self._spiel_cache.pop(key)   # zuletzt benutzt nach hinten
            return self._spiel_cache[key]
        konfig = rag.index_konfig()
        if stand_wissen is not None:
            stand = rag.stand_im_index(con, spiel_id, konfig)
            if stand and stand[0] != rag.fingerprint(wissen, konfig):
                raise rag.KonfigFehler(
                    f"Index fuer {spiel_id!r} ist veraltet: {wissen} hat sich seit dem letzten "
                    f"`rag.py index` geaendert. Auf dem Host `CHUNK_SIZE={v.CHUNK_SIZE} "
                    f"CHUNK_OVERLAP={v.CHUNK_OVERLAP} EMBED_MODEL={v.EMBED_MODEL} "
                    f"python rag.py index {spiel_id}` laufen lassen.")
        drop = rag.lies_drop_types({"SOURCE": "knowledge", "DROP_TYPES": v.DROP_TYPES})
        chunks, embs = rag.lade_spiel(con, spiel_id, drop, konfig)
        if not chunks:
            raise ValueError(f"Index leer: {spiel_id} enthaelt nach DROP_TYPES={v.DROP_TYPES!r} keinen Chunk.")
        self._spiel_cache[key] = (chunks, embs)
        while len(self._spiel_cache) > v.CACHE_SPIELE:
            self._spiel_cache.pop(next(iter(self._spiel_cache)))
        return chunks, embs

    def _suche_spiel(self, frage, v, spiel_id):
        # Unter dem Lock aus demselben Grund wie _suche: Modul-Globale gehoeren zu DIESER Anfrage.
        with self._lock:
            rag = self._lade_rag(v)
            con = rag.oeffne_index(v.INDEX_PATH)
            try:
                chunks, embs = self._lade_spiel(rag, v, spiel_id, con)
                hits = rag.retrieve(frage, chunks, embs, k=v.TOP_K, spiel_id=spiel_id, index=con)
            finally:
                con.close()
        return rag.baue_nachrichten(frage, hits), hits

    async def _stream(self, nachrichten):
        v = self.valves
        payload = {"model": v.LLM_MODEL, "messages": nachrichten, "think": v.THINK, "stream": True}
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10)) as client:
            async with client.stream("POST", f"{v.OLLAMA_URL}/api/chat", json=payload) as r:
                if r.status_code >= 400:
                    body = (await r.aread()).decode(errors="replace")
                    try:
                        grund = json.loads(body).get("error", body)
                    except ValueError:
                        grund = body
                    raise RuntimeError(f"Ollama antwortet {r.status_code}: {grund}")
                async for zeile in r.aiter_lines():
                    stueck = ollama_zeile(zeile)
                    if stueck:
                        yield stueck

    async def pipe(self, body: dict, __task__=None):
        # Ein async-Generator wird von Open WebUI erst ausserhalb seines
        # Fehler-Handlers iteriert -- was hier entkommt, erreicht den Chat nicht.
        # Deshalb jeder Fehler als sichtbarer Text.
        try:
            async for stueck in self._antworte(body, __task__):
                yield stueck
        except Exception as e:
            yield f"\n\n**Fehler in der RAG-Pipe:** {type(e).__name__}: {e}"

    async def _antworte(self, body, task):
        messages = body.get("messages", [])
        if task:
            # Titel, Tags, Folgefragen: Open WebUI fragt dafuer das gewaehlte Modell.
            # Ohne Retrieval durchreichen -- sonst sucht die Pipe Regeln zu "Erzeuge einen Titel".
            async for stueck in self._stream([{"role": m["role"], "content": text_von(m.get("content"))}
                                              for m in messages]):
                yield stueck
            return
        # Optionales Feld fuer Aufrufer wie Home Assistant:
        #   "regelfrage": {"spiel": "Food Chain Magnate", "sprache": true}
        # Ohne das Feld (Chat in Open WebUI) aendert sich nichts.
        rf = body.get("regelfrage") if isinstance(body.get("regelfrage"), dict) else {}
        if self.valves.INDEX_PATH:
            async for stueck in self._antworte_index(messages, rf):
                yield stueck
            return
        if rf.get("spiel") is not None:
            v = self.valves
            rag = await asyncio.to_thread(self._rag_fuer, v)
            status, ergebnis = rag.ordne_spiel(rf["spiel"], rag.katalog_aus(v.SPIEL, v.SPIEL_ALIASE))
            if status != "treffer":
                vorschlag = f" Meintest du {' oder '.join(ergebnis)}?" if ergebnis else ""
                yield (f"Zu „{rf['spiel']}“ habe ich kein Regelheft.{vorschlag} "
                       f"Verfuegbar: {v.SPIEL}.")
                return
        frage, verlauf = zerlege_verlauf(messages)
        if not frage:
            yield "Keine Frage gefunden."
            return
        nachrichten, hits = await asyncio.to_thread(self._suche, frage, self.valves)
        async for stueck in self._stream(setze_verlauf_ein(nachrichten, verlauf)):
            yield stueck
        # Fuer Sprache keine Fusszeile -- Scores wuerden sonst vorgelesen. Der Prompt
        # bleibt derselbe wie bei der CLI, damit das Golden Set weiter gilt.
        if not rf.get("sprache"):
            yield fundstellen(hits)

    def _spiel_aus_verlauf(self, messages, v):
        """(spiel_id, Nachrichten bis zur eigentlichen Frage, Meldung) fuer den Chat.

        Regeln in rag.spiel_im_chat: nur exakte Namen, das erste genannte Spiel gilt,
        gewechselt wird nur explizit (Namensnachricht, "Spiel: X", "Zu X: ...").
        Hoechstens die letzten rag.CHAT_FENSTER Nutzer-Nachrichten.
        """
        with self._lock:
            rag = self._lade_rag(v)
            spiele, katalog, ids, wb = self._lade_katalog(rag, v)
        if not spiele:
            spiel_id, meldung = self._waehle_spiel(None, v)
            return spiel_id, messages, meldung
        als_text = [{"role": m.get("role"), "content": text_von(m.get("content"))} for m in messages]
        art, erg, bis = rag.spiel_im_chat(als_text, wb)
        if art == "gewechselt":
            return None, messages, f"Ok, ab jetzt {erg}."
        if art == "mehrdeutig":
            return None, messages, f"{rag.RUECKFRAGE} Meintest du {' oder '.join(erg[:3])}?"
        teil = messages if bis is None else messages[:bis + 1]
        if erg is None:
            spiel_id, meldung = self._waehle_spiel(None, v)
            return spiel_id, teil, meldung
        return ids[erg], teil, None

    async def _antworte_index(self, messages, rf):
        v = self.valves
        if rf.get("spiel") is not None:
            spiel_id, meldung = await asyncio.to_thread(self._waehle_spiel, rf["spiel"], v)
        else:
            spiel_id, messages, meldung = await asyncio.to_thread(self._spiel_aus_verlauf, messages, v)
        if meldung:
            yield meldung
            return
        frage, verlauf = zerlege_verlauf(messages)
        if not frage:
            yield "Keine Frage gefunden."
            return
        nachrichten, hits = await asyncio.to_thread(self._suche_spiel, frage, v, spiel_id)
        async for stueck in self._stream(setze_verlauf_ein(nachrichten, verlauf)):
            yield stueck
        if not rf.get("sprache"):
            yield fundstellen(hits)
