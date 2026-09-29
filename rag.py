#!/usr/bin/env python3
"""
Schlankes RAG-Labor fuer Brettspiel-Regelfragen.

Alle PDFs im Ordner pdfs/ werden automatisch indiziert -> neues Spiel = PDF reinlegen.
Die Stellschrauben (Chunking, Embedding-Modell, top_k, Reranker) stehen oben in der
Konfiguration und sind der eigentliche Gegenstand des Experiments. Alle per env setzbar.

Nutzung:
    python rag.py ask "Wie verdiene ich Geld?"   # eine Frage
    python rag.py eval                            # Golden Set durchlaufen
    RERANK=1 CHUNK_SIZE=400 python rag.py eval    # mit Reranker + kleineren Chunks

Mehrere Spiele liegen je in einem eigenen Verzeichnis data/<spiel_id>/ (knowledge.jsonl,
spiel.json, golden_set.json). Die Einzeldatei knowledge.jsonl neben rag.py ist der
alte Ein-Spiel-Weg und funktioniert unveraendert weiter.

Grundsatz der Auswertung: Die Messlatte haengt an der Natur der Frage, nie an der
Konfiguration des Laufs. Keine Stellschraube (DROP_TYPES, SOURCE, CHUNK_SIZE) darf
einen Nenner verschieben -- sonst zieht dieselbe Einstellung, die das Retrieval
veraendert, auch den Beobachtungspunkt mit.
"""
import sys, json, glob, re, os, sqlite3
import numpy as np
import requests
# pypdf wird erst im PDF-Zweig von load_chunks importiert. Die Wissensbasis-Route
# (SOURCE=knowledge) und die komplette Wertungslogik brauchen es nicht -- ohne
# Top-Level-Import laesst sich die Auswertung ohne Ingestion-Abhaengigkeiten
# und ohne laufende Modelle testen (siehe test_wertung.py).

# ---------- Konfiguration: hier drehen wir fuer das Experiment (alles per env) ----------
OLLAMA        = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL   = os.environ.get("EMBED_MODEL", "bge-m3")   # deutsches/multilinguales Embedding
LLM_MODEL     = os.environ.get("LLM_MODEL", "qwen3:14b")  # Modell fix halten, Retrieval variieren
CHUNK_SIZE    = int(os.environ.get("CHUNK_SIZE", 800))    # Zeichen pro Chunk
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", 150)) # Zeichen Ueberlappung zwischen Chunks
TOP_K         = int(os.environ.get("TOP_K", 4))           # wie viele Chunks in den Kontext wandern
THINK         = os.environ.get("THINK", "0") == "1"       # Qwen3-Reasoning an/aus (langsamer, gruendlicher)
RERANK        = os.environ.get("RERANK", "0") == "1"      # zweite Stufe: Cross-Encoder-Reranking
RERANK_MODEL  = os.environ.get("RERANK_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")
CANDIDATES    = int(os.environ.get("CANDIDATES", 20))     # so viele grob abrufen, bevor der Reranker auf TOP_K eindampft
PDF_DIR       = os.path.join(os.path.dirname(__file__), "pdfs")
DATA_DIR      = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))

# Vokabular des Klassifikators (classify.py): nur diese drei Chunk-Typen werden
# ueberhaupt vergeben. DROP_TYPES darf nichts anderes nennen -- die Frage-Typen des
# Golden Sets (fakt/falle/flavor/leerstelle/tabelle) sind eine ANDERE Taxonomie,
# Schnittmenge ist allein "flavor". Genau diese Verwechslung hat einmal einen
# Nenner verschoben.
CHUNK_TYPEN = ("regel", "flavor", "meta")

SYSTEM_PROMPT = """Du bist ein Regel-Assistent, der Fragen ausschliesslich auf Basis der dir bereitgestellten Quellen (Regelwerke) beantwortet.

Regeln:
1. Antworte immer auf Deutsch.
2. Stuetze jede sachliche Aussage ausschliesslich auf die bereitgestellten Quellen. Verlasse dich fuer konkrete Werte (Zahlen, Betraege, Kartennamen, Dauer, Reichweiten) NIEMALS auf dein Gedaechtnis - uebernimm sie woertlich aus der Quelle.
3. Nenne zu jeder Aussage die Fundstelle (Seite). Pruefe VOR jeder Aussage, ob die zitierte Stelle sie wirklich stuetzt. Wenn nicht, triff die Aussage nicht.
4. Wenn mehrere aehnliche Elemente existieren (z.B. verschiedene Karten), vergewissere dich, dass Wert UND Name aus derselben Fundstelle stammen. Ordne eine Zahl nie der falschen Karte zu.
5. Interpretiere jede Frage im Kontext der bereitgestellten Dokumente (es geht um ein Brettspiel, nicht um die reale Welt).
6. Ist eine Frage nicht durch die Quellen gedeckt, sage ausdruecklich "Dazu enthaelt das Dokument keine Angaben." und rate NICHT.
7. Kein externes Wissen einbauen.
8. Lieber knapp und korrekt als ausfuehrlich und unsicher."""


class KonfigFehler(RuntimeError):
    """Die Lauf-Konfiguration ist in sich widerspruechlich.

    Lieber laut abbrechen als still eine Zahl produzieren, die etwas anderes
    misst als ihr Etikett behauptet.
    """


# ---------- Guards ----------
def pruefe_chunk_konfiguration(size=None, overlap=None):
    """CHUNK_SIZE muss echt groesser als CHUNK_OVERLAP sein.

    Sonst ist die Schrittweite <= 0 und die Chunk-Schleife kommt nie voran
    (gemessen bei CHUNK_SIZE=150 gegen den festen Overlap 150: start waechst
    nicht mehr, der Prozess haengt ohne Fehlermeldung).
    """
    size = CHUNK_SIZE if size is None else size
    overlap = CHUNK_OVERLAP if overlap is None else overlap
    if size <= overlap:
        raise KonfigFehler(
            f"CHUNK_SIZE={size} muss groesser als CHUNK_OVERLAP={overlap} sein. "
            f"Schrittweite waere {size - overlap} (<= 0) -> Endlosschleife beim Chunken. "
            f"Also CHUNK_SIZE erhoehen oder CHUNK_OVERLAP senken."
        )
    return size, overlap


def zerteile(text, size=None, overlap=None):
    """Text in ueberlappende Stuecke schneiden. Prueft die Schrittweite an der Schleife selbst."""
    size, overlap = pruefe_chunk_konfiguration(size, overlap)
    schritt = size - overlap
    return [text[start:start + size] for start in range(0, len(text), schritt)]


def chunk_seite(c):
    """Seitenzahl eines knowledge.jsonl-Eintrags -- ohne stillen Fallback.

    Frueher stand hier c.get("seite", c["id"]): fehlte das Feld, wanderte die
    Chunk-ID in das Feld "seite" und der Systemprompt druckte sie als
    "Fundstelle (Seite)" aus. Gemessen auf einer ingest.py-Basis mit 79
    Eintraegen: Seitenangaben bis 79 bei einem 15-seitigen Heft.
    """
    if "seite" not in c:
        raise KonfigFehler(
            f"knowledge.jsonl-Eintrag {c.get('id', '?')!r} hat kein Feld 'seite'. "
            "Ohne Seite gibt es keine zitierfaehige Fundstelle -- frueher rutschte "
            "hier die Chunk-ID ins Feld 'seite' und wurde als Seitenzahl ausgegeben. "
            "Die Datei muss von einem Skript geschrieben sein, das 'seite' mitschreibt: "
            "auto_ingest.py tut das in allen Zweigen; ingest.py und vision_ingest.py "
            "muessen es ebenfalls tun. Kein Fallback, weil eine erfundene Seitenzahl "
            "schlimmer ist als ein Abbruch."
        )
    return c["seite"]


def lies_drop_types(env=None):
    """DROP_TYPES lesen und validieren -- oder hart abbrechen.

    DROP_TYPES ist ein INDEX-Filter (welche Chunks gar nicht erst eingebettet
    werden). Auf die Wertung wirkt es bewusst nirgends mehr. Damit es nicht
    still ins Leere greift, wird jede Konstellation abgelehnt, in der es gesetzt
    ist, aber nicht wirken kann.
    """
    env = os.environ if env is None else env
    drop = [x.strip() for x in env.get("DROP_TYPES", "").split(",") if x.strip()]
    if not drop:
        return set()
    unbekannt = [x for x in drop if x not in CHUNK_TYPEN]
    if unbekannt:
        raise KonfigFehler(
            f"DROP_TYPES nennt unbekannte Werte: {', '.join(unbekannt)}. "
            f"classify.py vergibt ausschliesslich {', '.join(CHUNK_TYPEN)}. "
            "Die Frage-Typen des Golden Sets (fakt, falle, leerstelle, tabelle) sind "
            "eine andere Taxonomie und hier nicht zulaessig."
        )
    quelle = env.get("SOURCE")
    if quelle != "knowledge":
        raise KonfigFehler(
            f"DROP_TYPES={','.join(drop)} gesetzt, aber SOURCE={quelle!r}. "
            "Der Typ-Filter greift nur auf knowledge.jsonl (SOURCE=knowledge); "
            "auf dem pypdf-Weg gibt es keine Typen und der Filter wuerde nichts tun. "
            "Also SOURCE=knowledge setzen oder DROP_TYPES weglassen."
        )
    return set(drop)


def pruefe_typ_feld(rohchunks, drop):
    """DROP_TYPES ohne vorherigen classify.py-Lauf ist ein Irrtum, kein No-op."""
    if drop and not any("typ" in c for c in rohchunks):
        raise KonfigFehler(
            f"DROP_TYPES={','.join(sorted(drop))} gesetzt, aber kein Eintrag in "
            "knowledge.jsonl hat ein Feld 'typ' -- classify.py zuerst laufen lassen. "
            "Ohne Typen filtert der Filter nichts und die Zahl waere eine andere, "
            "als das Etikett behauptet."
        )


# ---------- Spiele: ein Verzeichnis pro Spiel unter data/ ----------
# data/<spiel_id>/knowledge.jsonl  -- Chunks, jeder mit 'spiel' und 'spiel_id'
# data/<spiel_id>/spiel.json       -- Name, Aliase, Sprache, Quell-PDF
# data/<spiel_id>/golden_set.json  -- optional, Format wie golden_set.example.json
# Die spiel_id ist ein Slug und zugleich Verzeichnisname. Sie wird streng geprueft,
# weil sie aus Aufrufen von aussen (Pipe, CLI) in einen Pfad wandert.
SPIEL_ID_MUSTER = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# Sprache des Regelhefts -> Wort fuer die Ingestion-Prompts. Neue Sprachen hier ergaenzen.
SPRACHEN = {"de": ("deutsche", "Deutsch"), "en": ("englische", "Englisch")}


def spiel_slug(name):
    """Anzeigename -> stabile spiel_id ("Brass: Birmingham" -> "brass-birmingham").

    Umlaute werden ausgeschrieben statt zu Bindestrichen ("Kämpfer" -> "kaempfer",
    nicht "k-mpfer"); ß wird zu ss (APFS faltet ohnehin so).
    """
    s = (name or "").casefold()
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(alt, neu)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        raise KonfigFehler(f"Aus dem Spielnamen {name!r} laesst sich keine spiel_id bilden.")
    return s


def pruefe_spiel_id(spiel_id):
    if not isinstance(spiel_id, str) or not SPIEL_ID_MUSTER.fullmatch(spiel_id):
        raise KonfigFehler(
            f"Ungueltige spiel_id {spiel_id!r}: erlaubt sind Kleinbuchstaben, Ziffern und "
            "einzelne Bindestriche (z.B. food-chain-magnate).")
    return spiel_id


def spiel_verzeichnis(spiel_id, data_dir=None):
    return os.path.join(data_dir or DATA_DIR, pruefe_spiel_id(spiel_id))


def knowledge_pfad(spiel_id, data_dir=None):
    return os.path.join(spiel_verzeichnis(spiel_id, data_dir), "knowledge.jsonl")


def lies_spiel(spiel_id, data_dir=None):
    """spiel.json eines Spiels -- fehlt es, ist das Verzeichnis kein Spiel."""
    pfad = os.path.join(spiel_verzeichnis(spiel_id, data_dir), "spiel.json")
    if not os.path.exists(pfad):
        raise KonfigFehler(f"{pfad} fehlt -- {spiel_id!r} ist kein angelegtes Spiel.")
    with open(pfad, encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("spiel_id") != spiel_id:
        raise KonfigFehler(f"{pfad}: spiel_id {meta.get('spiel_id')!r} passt nicht zum Verzeichnis {spiel_id!r}.")
    if not meta.get("name"):
        raise KonfigFehler(f"{pfad}: Feld 'name' fehlt.")
    return meta


def liste_spiele(data_dir=None):
    """Alle spiel_ids unter data/ (Verzeichnisse mit spiel.json), sortiert."""
    data_dir = data_dir or DATA_DIR
    if not os.path.isdir(data_dir):
        return []
    return sorted(d for d in os.listdir(data_dir)
                  if SPIEL_ID_MUSTER.fullmatch(d)
                  and os.path.exists(os.path.join(data_dir, d, "spiel.json")))


def lege_spiel_an(name, spiel_id=None, sprache=None, aliase=None, quelle_pdf=None, data_dir=None):
    """Verzeichnis + spiel.json anlegen oder ergaenzen; gibt die Metadaten zurueck.

    Vorhandene Angaben bleiben stehen, wenn der Aufruf sie nicht nennt -- ein
    zweiter Ingestion-Lauf ohne --aliase loescht also keine gepflegten Aliase.
    """
    spiel_id = pruefe_spiel_id(spiel_id or spiel_slug(name))
    verz = spiel_verzeichnis(spiel_id, data_dir)
    os.makedirs(verz, exist_ok=True)
    pfad = os.path.join(verz, "spiel.json")
    meta = {"spiel_id": spiel_id, "name": name, "aliase": [], "sprache": "de", "quelle_pdf": None}
    if os.path.exists(pfad):
        with open(pfad, encoding="utf-8") as f:
            meta.update(json.load(f))
        meta["name"] = name or meta["name"]
    if aliase is not None:
        meta["aliase"] = [a.strip() for a in aliase if a and a.strip()]
    if sprache is not None:
        meta["sprache"] = sprache
    if quelle_pdf is not None:
        meta["quelle_pdf"] = os.path.basename(quelle_pdf)
    if meta["sprache"] not in SPRACHEN:
        raise KonfigFehler(f"Sprache {meta['sprache']!r} unbekannt; bekannt: {', '.join(SPRACHEN)}. "
                           "Neue Sprachen in rag.SPRACHEN ergaenzen.")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return meta


def vision_prompt(spiel=None, sprache="de"):
    """Vision-Prompt fuer auto_ingest.py und vision_ingest.py.

    Frueher stand dort fest "Diagramm von Mitarbeiterkarten" (Food Chain Magnate).
    Das Spiel geht nur als Name ein, die Art der Elemente wird nicht vorgegeben.
    """
    wo = f"des Brettspiels „{spiel}“" if spiel else "eines Brettspiels"
    return (f"Auf dem Bild ist eine Seite aus dem Regelheft {wo} mit Grafiken "
            "(z.B. Karten, Plaettchen, Tabellen oder Diagramme). "
            "Liste JEDES dargestellte Element einzeln auf, ein Eintrag pro Zeile im Format "
            "'Name: Effekt und alle Werte'. Uebernimm alle Zahlen (z.B. Reichweite, "
            "Dauer, Kosten) exakt vom Bild. Erfinde nichts. "
            f"Antworte auf {SPRACHEN[sprache][1]}.")


def spiel_felder(meta):
    """Die zwei Felder, die jeder Chunk eines Spiels traegt."""
    return {"spiel": meta["name"], "spiel_id": meta["spiel_id"]}


def spiel_argumente(argv):
    """--spiel NAME [--spiel-id ID] [--sprache de] [--aliase "a,b"] aus argv loesen.

    Gibt (restliche Argumente, Optionen-dict oder None) zurueck. Ohne --spiel und
    --spiel-id bleibt es beim alten Ein-Datei-Weg. Bewusst ohne argparse, weil die
    Skripte ihre Positionsargumente weiter selbst lesen (Tests rufen main() direkt).
    """
    rest, opt = [], {}
    namen = {"--spiel": "name", "--spiel-id": "spiel_id", "--sprache": "sprache", "--aliase": "aliase"}
    i = 0
    argv = list(argv)
    while i < len(argv):
        a = argv[i]
        schluessel, wert = (a.split("=", 1) + [None])[:2] if a.startswith("--") else (a, None)
        if schluessel in namen:
            if wert is None:
                if i + 1 >= len(argv):
                    raise KonfigFehler(f"{schluessel} braucht einen Wert.")
                wert = argv[i + 1]
                i += 1
            opt[namen[schluessel]] = wert
        else:
            rest.append(a)
        i += 1
    if not opt:
        return rest, None
    if "aliase" in opt:
        opt["aliase"] = opt["aliase"].split(",")
    if "name" not in opt:
        # Nur --spiel-id: das Spiel muss schon angelegt sein, der Name kommt aus spiel.json.
        if "spiel_id" not in opt:
            raise KonfigFehler("--spiel NAME oder --spiel-id ID angeben.")
        opt["name"] = None
    return rest, opt


def bereite_spiel_vor(opt, quelle_pdf=None, data_dir=None):
    """Optionen aus spiel_argumente -> (meta, Pfad der knowledge.jsonl des Spiels)."""
    if opt.get("name") is None:
        meta_alt = lies_spiel(pruefe_spiel_id(opt["spiel_id"]), data_dir)
        opt = dict(opt, name=meta_alt["name"])
    meta = lege_spiel_an(opt["name"], opt.get("spiel_id"), opt.get("sprache"),
                         opt.get("aliase"), quelle_pdf, data_dir)
    return meta, knowledge_pfad(meta["spiel_id"], data_dir)


def lies_jsonl(pfad):
    with open(pfad, encoding="utf-8") as f:
        return [json.loads(z) for z in f if z.strip()]


def schreibe_jsonl(pfad, eintraege):
    with open(pfad, "w", encoding="utf-8") as f:
        for e in eintraege:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def lies_spiel_chunks(spiel_id, data_dir=None):
    """knowledge.jsonl eines Spiels -- jeder Eintrag muss zu diesem Spiel gehoeren.

    Ein Chunk mit fremder oder fehlender spiel_id ist ein Kopierfehler: er wuerde
    im Index unter dem falschen Spiel stehen und Regeln eines anderen Spiels
    zitieren. Deshalb Abbruch statt stiller Uebernahme.
    """
    pfad = knowledge_pfad(spiel_id, data_dir)
    if not os.path.exists(pfad):
        raise KonfigFehler(f"{pfad} fehlt -- fuer {spiel_id!r} wurde noch nichts eingelesen.")
    roh = lies_jsonl(pfad)
    falsch = [c.get("id", "?") for c in roh if c.get("spiel_id") != spiel_id]
    if falsch:
        raise KonfigFehler(
            f"{pfad}: {len(falsch)} Eintrag/Eintraege ohne oder mit fremder spiel_id "
            f"(z.B. id {falsch[0]!r}). Einlesen mit --spiel wiederholen oder "
            "`python rag.py migriere` benutzen.")
    return roh


# ---------- PDF -> Chunks (seitenbewusst, damit Zitate eine Seite haben) ----------
def baue_knowledge_chunks(rohchunks, drop):
    pruefe_typ_feld(rohchunks, drop)
    chunks = []
    for c in rohchunks:
        if c.get("typ") in drop:   # z.B. DROP_TYPES="flavor,meta"
            continue
        seite = chunk_seite(c)
        for stueck in zerteile(c["text"]):
            chunks.append({"doc": "knowledge", "seite": seite, "text": stueck})
    return chunks


def load_chunks():
    pruefe_chunk_konfiguration()
    # DROP_TYPES unbedingt validieren, auch auf dem PDF-Weg: die Variable wurde
    # bisher immer gelesen, wirkte aber nur bei SOURCE=knowledge.
    drop = lies_drop_types()
    # Verbalisierte Wissensbasis (Docling -> Qwen) statt roher pypdf-Extraktion?
    if os.environ.get("SOURCE") == "knowledge":
        with open(os.path.join(os.path.dirname(__file__), "knowledge.jsonl")) as kf:
            rohchunks = [json.loads(line) for line in kf if line.strip()]
        return baue_knowledge_chunks(rohchunks, drop)
    from pypdf import PdfReader
    chunks = []
    for path in sorted(glob.glob(os.path.join(PDF_DIR, "*.pdf"))):
        doc = os.path.basename(path)
        for pageno, page in enumerate(PdfReader(path).pages, start=1):
            text = re.sub(r"\s+", " ", page.extract_text() or "").strip()
            if not text:
                continue
            for stueck in zerteile(text):
                chunks.append({"doc": doc, "seite": pageno, "text": stueck})
    return chunks


# ---------- Embeddings via Ollama ----------
def embed(texts):
    r = requests.post(f"{OLLAMA}/api/embed", json={"model": EMBED_MODEL, "input": texts}, timeout=300)
    r.raise_for_status()
    return np.array(r.json()["embeddings"], dtype=np.float32)


def l2norm(v):
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


def build_index():
    chunks = load_chunks()
    embs = l2norm(embed([c["text"] for c in chunks]))
    return chunks, embs


# ---------- Persistenter Index (SQLite) ----------
# Eine Datei data/index.sqlite fuer alle Spiele. Vektoren liegen als float32-BLOB
# (little endian) in einer normalen Tabelle, gesucht wird mit numpy; BM25 kommt
# aus FTS5. sqlite-vec wird bewusst NICHT benutzt, obwohl es auf der Zielmaschine
# laedt (Wheel 0.1.9 fuer py3.14/manylinux, enable_load_extension vorhanden):
#   1. Gleichstaende: bei identischen Vektoren liefert vec0 die umgekehrte
#      rowid-Reihenfolge wie np.argsort (gemessen: [6,4,3,1] statt [1,3,4,6]).
#      Duplikat-Chunks sind real (Ueberlappung, wiederholte Vision-Zeilen), und
#      an der top_k-Grenze aendert das die MENGE, nicht nur die Reihenfolge --
#      der Default-Pfad waere fuer FCM nicht mehr zahlengleich.
#   2. Gesucht wird immer innerhalb EINES Spiels (Filter vor dem Ranking). Das
#      sind hunderte bis wenige tausend Vektoren; vec0 ist in 0.1.x ohnehin
#      Brute-Force. Gemessen bei 47k x 1024, 250 Spielen, k=4, 200 Fragen:
#      pro Spiel numpy typisch 0,07 ms (max 0,12), sqlite-vec 0,29 ms (max 0,37).
#   3. Die Pipe laeuft im Open-WebUI-Container: numpy ist dort vorhanden,
#      sqlite-vec waere eine weitere Abhaengigkeit samt load_extension.
# Das BLOB-Format ist genau das, was sqlite-vec als vec_f32 liest -- ein spaeterer
# Wechsel (etwa auf ANN) ist eine Abfrage-Aenderung, kein Neu-Embedden.
INDEX_PATH   = os.environ.get("INDEX_PATH", os.path.join(DATA_DIR, "index.sqlite"))
EMBED_BATCH  = int(os.environ.get("EMBED_BATCH", 64))  # Texte pro /api/embed-Aufruf beim Indexbau
# Hochzaehlen, wenn sich zerteile() oder das Chunk-Format aendert: dann ist jeder
# gespeicherte Stand ungueltig, auch bei gleicher Datei und gleichen Stellschrauben.
INDEX_SCHEMA = 1

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS spiele (
    spiel_id   TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    aliase     TEXT NOT NULL,          -- JSON-Liste
    sprache    TEXT,
    quelle_pdf TEXT
);
-- Ein Stand je Spiel UND Konfiguration: ein eval-Lauf mit CHUNK_SIZE=800 ueberschreibt
-- nicht den 400er-Stand, den die Pipe benutzt.
CREATE TABLE IF NOT EXISTS staende (
    spiel_id    TEXT NOT NULL,
    konfig      TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    chunks      INTEGER NOT NULL,
    dim         INTEGER NOT NULL,
    PRIMARY KEY (spiel_id, konfig)
);
CREATE TABLE IF NOT EXISTS chunks (
    id       INTEGER PRIMARY KEY,
    spiel_id TEXT NOT NULL,
    konfig   TEXT NOT NULL,
    pos      INTEGER NOT NULL,         -- Reihenfolge wie beim In-Memory-Weg
    seite    TEXT NOT NULL,            -- JSON, damit der Wert unveraendert zurueckkommt
    typ      TEXT,
    text     TEXT NOT NULL,
    emb      BLOB NOT NULL,
    UNIQUE (spiel_id, konfig, pos)
);
"""
_FTS_SQL = ("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
            "text, tokenize='unicode61 remove_diacritics 2')")   # rowid = chunks.id


def index_konfig(embed_model=None, size=None, overlap=None):
    """Alles, was die gespeicherten Vektoren bestimmt -- ausser der Datei selbst.

    DROP_TYPES gehoert NICHT dazu: der Index enthaelt alle Chunks, gefiltert wird
    beim Laden. Ein anderer Typ-Filter braucht also kein neues Embedding.
    """
    size, overlap = pruefe_chunk_konfiguration(size, overlap)
    return json.dumps({"schema": INDEX_SCHEMA, "embed_model": embed_model or EMBED_MODEL,
                       "chunk_size": size, "chunk_overlap": overlap}, sort_keys=True)


def fingerprint(pfad, konfig):
    """Datei-Hash + Konfiguration. mtime taugt nicht (cp -p, Restore)."""
    import hashlib
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    h.update(b"\0" + konfig.encode())
    return h.hexdigest()


def fts5_verfuegbar(con):
    try:
        con.execute("CREATE VIRTUAL TABLE temp._fts_probe USING fts5(x)")
        con.execute("DROP TABLE temp._fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


def oeffne_index(pfad=None, schreibend=False):
    """Verbindung zum Index. Lesend mit mode=ro: die Pipe hat den Index read-only gemountet."""
    pfad = pfad or INDEX_PATH
    if schreibend:
        os.makedirs(os.path.dirname(os.path.abspath(pfad)), exist_ok=True)
        con = sqlite3.connect(pfad, timeout=30)
        con.executescript(_SCHEMA_SQL)
        if fts5_verfuegbar(con):
            con.execute(_FTS_SQL)
        con.commit()
        return con
    if not os.path.exists(pfad):
        raise KonfigFehler(f"Index {pfad} fehlt -- zuerst `python rag.py index --alle` laufen lassen.")
    return sqlite3.connect(f"file:{pfad}?mode=ro", uri=True, timeout=30)


def _hat_fts(con):
    return con.execute("SELECT 1 FROM sqlite_master WHERE name='chunks_fts'").fetchone() is not None


def indexiere_stuecke(rohchunks, size=None, overlap=None):
    """[(seite, typ, stueck)] in genau der Reihenfolge von baue_knowledge_chunks.

    Anders als dort ohne DROP_TYPES: der Index nimmt alle Typen auf.
    """
    out = []
    for c in rohchunks:
        seite = chunk_seite(c)
        for stueck in zerteile(c["text"], size, overlap):
            out.append((seite, c.get("typ"), stueck))
    return out


def embed_gebatcht(texte, batch=None):
    batch = batch or EMBED_BATCH
    teile = [embed(texte[i:i + batch]) for i in range(0, len(texte), batch)]
    return np.concatenate(teile) if teile else np.zeros((0, 0), dtype=np.float32)


def aktualisiere_spiel(con, spiel_id, data_dir=None):
    """Stand eines Spiels fuer die aktuelle Konfiguration herstellen.

    Neu eingebettet wird nur, wenn sich der Fingerprint geaendert hat. Die
    Metadaten aus spiel.json (Name, Aliase) werden immer uebernommen -- das
    kostet nichts und macht einen neuen Alias ohne Neu-Embedding wirksam.
    Rueckgabe: ("aktuell" | "neu", Anzahl Chunks).
    """
    meta = lies_spiel(spiel_id, data_dir)
    roh = lies_spiel_chunks(spiel_id, data_dir)
    konfig = index_konfig()
    fp = fingerprint(knowledge_pfad(spiel_id, data_dir), konfig)
    con.execute("INSERT OR REPLACE INTO spiele VALUES (?,?,?,?,?)",
                (spiel_id, meta["name"], json.dumps(meta.get("aliase") or [], ensure_ascii=False),
                 meta.get("sprache"), meta.get("quelle_pdf")))
    alt = con.execute("SELECT fingerprint, chunks FROM staende WHERE spiel_id=? AND konfig=?",
                      (spiel_id, konfig)).fetchone()
    if alt and alt[0] == fp:
        con.commit()
        return "aktuell", alt[1]
    stuecke = indexiere_stuecke(roh)
    if not stuecke:
        raise KonfigFehler(f"{spiel_id}: knowledge.jsonl ergibt keinen einzigen Chunk.")
    # Erst einbetten, dann schreiben: bricht Ollama ab, bleibt der alte Stand stehen.
    embs = l2norm(embed_gebatcht([s for _, _, s in stuecke])).astype("<f4")
    if len(embs) != len(stuecke):
        raise RuntimeError(f"{spiel_id}: {len(stuecke)} Texte, aber {len(embs)} Embeddings.")
    fts = _hat_fts(con)
    with con:
        if fts:
            con.execute("DELETE FROM chunks_fts WHERE rowid IN "
                        "(SELECT id FROM chunks WHERE spiel_id=? AND konfig=?)", (spiel_id, konfig))
        con.execute("DELETE FROM chunks WHERE spiel_id=? AND konfig=?", (spiel_id, konfig))
        for pos, ((seite, typ, text), e) in enumerate(zip(stuecke, embs)):
            cur = con.execute("INSERT INTO chunks (spiel_id, konfig, pos, seite, typ, text, emb) "
                              "VALUES (?,?,?,?,?,?,?)",
                              (spiel_id, konfig, pos, json.dumps(seite), typ, text, e.tobytes()))
            if fts:
                con.execute("INSERT INTO chunks_fts (rowid, text) VALUES (?,?)", (cur.lastrowid, text))
        con.execute("INSERT OR REPLACE INTO staende VALUES (?,?,?,?,?)",
                    (spiel_id, konfig, fp, len(stuecke), int(embs.shape[1])))
    return "neu", len(stuecke)


def entferne_spiel(con, spiel_id):
    """Spiel samt allen Staenden aus dem Index (Verzeichnis unter data/ ist weg)."""
    with con:
        if _hat_fts(con):
            con.execute("DELETE FROM chunks_fts WHERE rowid IN (SELECT id FROM chunks WHERE spiel_id=?)",
                        (spiel_id,))
        for tabelle in ("chunks", "staende", "spiele"):
            con.execute(f"DELETE FROM {tabelle} WHERE spiel_id=?", (spiel_id,))


def aktualisiere_index(spiel_ids=None, pfad=None, data_dir=None, ausgabe=print):
    """Index fuer die genannten Spiele (None = alle unter data/) auf Stand bringen.

    Nur bei "alle" werden Spiele entfernt, deren Verzeichnis verschwunden ist --
    ein Einzelaufruf fasst fremde Spiele nie an.
    """
    alle = spiel_ids is None
    spiel_ids = liste_spiele(data_dir) if alle else [pruefe_spiel_id(s) for s in spiel_ids]
    con = oeffne_index(pfad, schreibend=True)
    try:
        ergebnis = {}
        for sid in spiel_ids:
            ergebnis[sid] = aktualisiere_spiel(con, sid, data_dir)
            ausgabe(f"  {sid}: {ergebnis[sid][0]} ({ergebnis[sid][1]} Chunks)")
        if alle:
            weg = [r[0] for r in con.execute("SELECT spiel_id FROM spiele")]
            for sid in sorted(set(weg) - set(spiel_ids)):
                entferne_spiel(con, sid)
                ergebnis[sid] = ("entfernt", 0)
                ausgabe(f"  {sid}: entfernt (kein Verzeichnis mehr unter data/)")
        return ergebnis
    finally:
        con.close()


def stand_im_index(con, spiel_id, konfig=None):
    """(fingerprint, chunks) des gespeicherten Stands oder None."""
    return con.execute("SELECT fingerprint, chunks FROM staende WHERE spiel_id=? AND konfig=?",
                       (spiel_id, konfig or index_konfig())).fetchone()


def lade_spiel(con, spiel_id, drop=frozenset(), konfig=None):
    """(chunks, embs) EINES Spiels, gefiltert vor jedem Ranking.

    Reihenfolge und Werte entsprechen dem In-Memory-Weg: gleiche Chunk-Folge
    (pos), gleiche float32-Vektoren. Deshalb liefert dieselbe Rangfolge-Rechnung
    dieselben Top-k -- inklusive Gleichstaenden.
    """
    konfig = konfig or index_konfig()
    stand = con.execute("SELECT dim FROM staende WHERE spiel_id=? AND konfig=?", (spiel_id, konfig)).fetchone()
    if stand is None:
        raise KonfigFehler(
            f"{spiel_id!r} ist fuer diese Konfiguration nicht im Index ({konfig}). "
            f"`python rag.py index {spiel_id}` mit denselben EMBED_MODEL/CHUNK_SIZE/CHUNK_OVERLAP laufen lassen.")
    zeilen = con.execute("SELECT id, seite, typ, text, emb FROM chunks "
                         "WHERE spiel_id=? AND konfig=? ORDER BY pos", (spiel_id, konfig)).fetchall()
    pruefe_typ_feld([{"typ": z[2]} for z in zeilen if z[2] is not None], drop)
    zeilen = [z for z in zeilen if z[2] not in drop]
    chunks = [{"doc": "knowledge", "seite": json.loads(z[1]), "text": z[3],
               "spiel_id": spiel_id, "chunk_id": z[0]} for z in zeilen]
    embs = np.frombuffer(b"".join(z[4] for z in zeilen), dtype="<f4").reshape(len(zeilen), stand[0])
    return chunks, embs.astype(np.float32, copy=False)


def spiele_im_index(con):
    """[{spiel_id, name, aliase, sprache, quelle_pdf}] aus der Tabelle spiele."""
    return [{"spiel_id": r[0], "name": r[1], "aliase": json.loads(r[2]), "sprache": r[3], "quelle_pdf": r[4]}
            for r in con.execute("SELECT spiel_id, name, aliase, sprache, quelle_pdf FROM spiele ORDER BY spiel_id")]


# ---------- Reranker (lazy geladen) ----------
_reranker = None
def get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder(RERANK_MODEL, trust_remote_code=True)
    return _reranker


def retrieve(query, chunks, embs, k=TOP_K):
    q = l2norm(embed([query]))[0]
    sims = embs @ q
    if RERANK:
        # 1. Stufe: grob CANDIDATES per Embedding holen
        cand = [int(i) for i in np.argsort(-sims)[:CANDIDATES]]
        # 2. Stufe: Cross-Encoder bewertet jedes Frage-Chunk-Paar einzeln
        scores = get_reranker().predict([[query, chunks[i]["text"]] for i in cand])
        ranked = sorted(zip(cand, scores), key=lambda x: -x[1])[:k]
        return [(chunks[i], float(s)) for i, s in ranked]
    order = np.argsort(-sims)[:k]
    return [(chunks[i], float(sims[i])) for i in order]


# ---------- Antwort vom LLM ----------
def baue_nachrichten(query, hits):
    """Systemprompt + Quellen + Frage -- die eine Stelle, an der der Prompt entsteht.

    Die CLI (answer) und die Open-WebUI-Pipe (openwebui_pipe.py) bauen ihn beide
    hier, damit das Golden Set auch das misst, was im Chat ankommt.
    """
    kontext = "\n\n".join(f"[{h['doc']}, Seite {h['seite']}]\n{h['text']}" for h, _ in hits)
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Quellen:\n{kontext}\n\nFrage: {query}"},
    ]


def answer(query, hits):
    r = requests.post(f"{OLLAMA}/api/chat", json={
        "model": LLM_MODEL,
        "messages": baue_nachrichten(query, hits),
        "think": THINK,
        "stream": False,
    }, timeout=600)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


# ---------- Wertung ----------
KAT_GETROFFEN    = "getroffen"
KAT_VERFEHLT     = "verfehlt"
KAT_VERWEIGERUNG = "verweigerung"


def _keyword_muster(kw):
    r"""Regex fuer ein Keyword mit Wortgrenzen, soweit die Randzeichen Wortzeichen sind.

    Reines Substring-Matching hat gemessen Falsch-Positive erzeugt: "nicht" steckt
    in "nichts". \b laesst sich aber nicht blind anhaengen -- Keywords wie "50 %"
    oder "#12" beginnen bzw. enden mit Nicht-Wortzeichen, dort wuerde \b nie passen.
    Deshalb Lookarounds nur an den Seiten, an denen ein Wortzeichen steht.
    """
    links  = r"(?<!\w)" if kw[:1].isalnum() or kw[:1] == "_" else ""
    rechts = r"(?!\w)"  if kw[-1:].isalnum() or kw[-1:] == "_" else ""
    # Deutsche Flexion: bei MEHRWORTIGEN Keywords darf das letzte Wort eine Endung
    # tragen ("keine Angabe" trifft auch "keine Angaben"). Gemessen aufgefallen:
    # das Modell verweigert mit "keine Angaben", das Golden Set nennt "keine Angabe",
    # und die reine Wortgrenze erzeugte dadurch ein Falsch-NEGATIV.
    # Bei EINWORTIGEN Keywords bleibt es strikt -- sonst traefe "nicht" wieder
    # "nichts", genau das Falsch-Positiv, das die Wortgrenze beseitigen sollte.
    # Endet das Keyword auf einer Ziffer, bleibt es ebenfalls strikt: Zahlen
    # flektieren nicht, und "2 bis 5" darf nicht "2 bis 555" treffen.
    if rechts and len(kw.split()) > 1 and kw[-1:].isalpha():
        rechts = r"\w{0,3}(?!\w)"
    return links + re.escape(kw) + rechts


def keyword_treffer(keywords, antwort):
    """Welche erwarteten Stichwoerter stehen woertlich (auf Wortgrenze) in der Antwort?

    ACHTUNG, Grundsatz: Das ist ein REGRESSIONSWARNER, kein Korrektheitsmass.
    Der Warner sagt, ob ein erwartetes Stichwort vorkommt. Er kann nicht sagen,
    ob eine Antwort richtig ist -- und schon gar nicht, ob eine falsch ist. Eine
    faktenfreie Antwort kann Stichwoerter treffen, eine korrekt umformulierte
    Antwort kann sie verfehlen. Wer aus dieser Zahl "keine einzige falsch" liest,
    liest etwas, das dieses Skript nicht erhebt.
    """
    return [k for k in (keywords or []) if k and re.search(_keyword_muster(k), antwort, re.IGNORECASE)]


def bewerte_retrieval(frage, abgerufene_seiten):
    """Dreiteilung: getroffen / verfehlt / Verweigerungsfrage.

    Die Zuordnung haengt AUSSCHLIESSLICH an der Frage selbst -- nie an DROP_TYPES,
    SOURCE, CHUNK_SIZE oder irgendeiner anderen Stellschraube des Laufs. Vorher
    hing sie am Frage-Typ gegen DROP_TYPES; gemessen hat DROP_TYPES=falle damit
    die Quote von 5/9 auf 5/7 gehoben, ohne einen einzigen Chunk aus dem Index zu
    nehmen, und DROP_TYPES=fakt,falle,flavor,tabelle meldete 0/0 ohne Warnung.

    Verweigerungsfragen (erwartet_verweigerung: true im Golden Set) sind eine
    eigene Kategorie, kein stiller Abzug vom Nenner: bei ihnen ist Verweigern die
    richtige Antwort, eine Retrieval-Quote ist auf sie nicht anwendbar.
    """
    if frage.get("erwartet_verweigerung"):
        return KAT_VERWEIGERUNG
    erwartete = frage.get("seiten") or []
    if not erwartete:
        raise KonfigFehler(
            f"Frage {frage.get('id', '?')} hat weder 'seiten' noch "
            "'erwartet_verweigerung': true. Damit ist unklar, was sie messen soll, "
            "und sie wuerde still aus dem Nenner fallen. Golden Set ergaenzen."
        )
    return KAT_GETROFFEN if any(s in abgerufene_seiten for s in erwartete) else KAT_VERFEHLT


def bewerte_frage(frage, abgerufene_seiten, antwort):
    """Ein Wertungssatz pro Frage. Liest keine Umgebungsvariablen."""
    return {
        "id": frage.get("id"),
        "typ": frage.get("typ"),
        "kategorie": bewerte_retrieval(frage, abgerufene_seiten),
        "erwartete_seiten": list(frage.get("seiten") or []),
        "abgerufene_seiten": list(abgerufene_seiten),
        "keywords_getroffen": keyword_treffer(frage.get("keywords"), antwort),
    }


def fasse_zusammen(saetze):
    """Aggregat mit ausgeschriebenen Nennern -- keine Quote ohne Bezugsgroesse."""
    verweigerung = [s for s in saetze if s["kategorie"] == KAT_VERWEIGERUNG]
    getroffen    = [s for s in saetze if s["kategorie"] == KAT_GETROFFEN]
    verfehlt     = [s for s in saetze if s["kategorie"] == KAT_VERFEHLT]
    return {
        "fragen": len(saetze),
        "retrieval_nenner": len(getroffen) + len(verfehlt),
        "getroffen": len(getroffen),
        "verfehlt": len(verfehlt),
        "verweigerungsfragen": len(verweigerung),
        "verweigerung_signal": sum(1 for s in verweigerung if s["keywords_getroffen"]),
        "kw_nenner": len(saetze),
        "kw_treffer": sum(1 for s in saetze if s["keywords_getroffen"]),
    }


def formatiere_zusammenfassung(z):
    """Beide Metriken mit explizitem Nenner und ehrlichem Etikett."""
    return [
        "== Zusammenfassung ==",
        f"Fragen im Golden Set: {z['fragen']}",
        f"  davon in der Retrieval-Wertung (erwartete Fundstelle vorhanden): {z['retrieval_nenner']}",
        f"  davon Verweigerungsfragen (Verweigern IST die richtige Antwort):  {z['verweigerungsfragen']}",
        "",
        f"Retrieval, erwartete Seite unter top_k={TOP_K}:",
        f"  getroffen : {z['getroffen']}/{z['retrieval_nenner']}",
        f"  verfehlt  : {z['verfehlt']}/{z['retrieval_nenner']}",
        f"  Nenner {z['retrieval_nenner']} haengt allein am Golden Set und aendert sich mit keiner Stellschraube.",
        "",
        f"Verweigerungsfragen: {z['verweigerungsfragen']}/{z['fragen']} -- nicht Teil der Retrieval-Quote.",
        f"  mit Verweigerungs-Signalwort in der Antwort: {z['verweigerung_signal']}/{z['verweigerungsfragen']}",
        "  Das ist ein Indiz, kein Urteil: ob tatsaechlich korrekt verweigert wurde,",
        "  entscheidet nur der Mensch beim Lesen der Antworten.",
        "",
        f"Keyword-Regressionswarner: {z['kw_treffer']}/{z['kw_nenner']} Fragen mit mindestens einem Stichworttreffer.",
        "  KEIN Korrektheitsmass. Der Warner prueft nur, ob ein erwartetes Stichwort",
        "  woertlich vorkommt. Er erkennt keine falsche Antwort und belegt kein",
        "  'keine einzige falsch' -- diese Kategorie erhebt das Skript nicht.",
    ]


# ---------- Modi ----------
def cmd_index(args):
    """python rag.py index [spiel_id ...|--alle] -- nur Geaendertes wird neu eingebettet."""
    ids = [a for a in args if a != "--alle"]
    print(f"Index {INDEX_PATH}  Konfiguration {index_konfig()}")
    aktualisiere_index(ids or None)


def cmd_ask(query):
    chunks, embs = build_index()
    hits = retrieve(query, chunks, embs)
    print(answer(query, hits))
    print("\nAbgerufen:", [(h["doc"], f"S.{h['seite']}", round(s, 3)) for h, s in hits])


def cmd_eval(golden_set_pfad=None):
    # Pfad als Parameter, damit der komplette Wertungsdurchlauf mit einem
    # Beispiel-Golden-Set testbar ist (siehe test_wertung.py, TestCmdEval).
    gs = json.load(open(golden_set_pfad
                        or os.path.join(os.path.dirname(__file__), "golden_set.json")))
    chunks, embs = build_index()
    print(f"Config: chunk={CHUNK_SIZE}/{CHUNK_OVERLAP}  top_k={TOP_K}  rerank={RERANK}"
          f"{'(' + RERANK_MODEL + ', cand=' + str(CANDIDATES) + ')' if RERANK else ''}"
          f"  embed={EMBED_MODEL}  llm={LLM_MODEL}  think={THINK}"
          f"  source={os.environ.get('SOURCE', 'pdf')}  drop_types={os.environ.get('DROP_TYPES', '') or '-'}")
    print(f"Index: {len(chunks)} Chunks aus {len(set(c['doc'] for c in chunks))} PDF(s)\n")
    saetze = []
    for f in gs["fragen"]:
        hits = retrieve(f["frage"], chunks, embs)
        ans = answer(f["frage"], hits)
        satz = bewerte_frage(f, [h["seite"] for h, _ in hits], ans)
        saetze.append(satz)
        print(f"[{f['id']}] ({f['typ']}) {f['frage']}")
        print(f"    erwartet : {f['erwartet']}")
        if satz["kategorie"] == KAT_VERWEIGERUNG:
            print(f"    Wertung  : Verweigerungsfrage -- Retrieval-Quote nicht anwendbar "
                  f"(abgerufen={satz['abgerufene_seiten']})")
        else:
            print(f"    Wertung  : {satz['kategorie']} (erwartet={satz['erwartete_seiten']} "
                  f"abgerufen={satz['abgerufene_seiten']})")
        print(f"    Keywords : {satz['keywords_getroffen'] or 'KEINE getroffen'}   (Regressionswarner)")
        print(f"    Antwort  : {ans[:280]}")
        print()
    for zeile in formatiere_zusammenfassung(fasse_zusammen(saetze)):
        print(zeile)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "eval"
    try:
        if mode == "ask" and len(sys.argv) > 2:
            cmd_ask(" ".join(sys.argv[2:]))
        elif mode == "index":
            cmd_index(sys.argv[2:])
        else:
            cmd_eval()
    except KonfigFehler as e:
        print(f"ABBRUCH (Konfiguration): {e}", file=sys.stderr)
        sys.exit(2)
