#!/usr/bin/env python3
"""
Schlankes RAG-Labor fuer Brettspiel-Regelfragen.

Alle PDFs im Ordner pdfs/ werden automatisch indiziert -> neues Spiel = PDF reinlegen.
Die Stellschrauben (Chunking, Embedding-Modell, top_k, Reranker) stehen oben in der
Konfiguration und sind der eigentliche Gegenstand des Experiments. Alle per env setzbar.

Nutzung:
    python rag.py ask "Wie verdiene ich Geld?"   # eine Frage
    python rag.py ask --spiel food-chain-magnate "Wie verdiene ich Geld?"
    HYBRID=1 python rag.py ask --spiel ...        # Vektor + BM25 (nur mit Index)
    python rag.py eval                            # Golden Set durchlaufen (Einzeldatei-Weg)
    python rag.py eval food-chain-magnate         # Golden Set eines Spiels gegen den Index
    python rag.py eval --alle                     # alle Spiele mit golden_set.json
    python rag.py index --alle                    # persistenten Index auf Stand bringen
    python rag.py migriere --spiel "Food Chain Magnate" --aliase "Food Chain,FCM"
    python rag.py vergleiche food-chain-magnate   # alter gegen neuen Weg, echte Embeddings, ohne LLM
    RERANK=1 CHUNK_SIZE=400 python rag.py eval    # mit Reranker + kleineren Chunks

Mehrere Spiele liegen je in einem eigenen Verzeichnis data/<spiel_id>/ (knowledge.jsonl,
spiel.json, golden_set.json). Die Einzeldatei knowledge.jsonl neben rag.py ist der
alte Ein-Spiel-Weg und funktioniert unveraendert weiter.

Grundsatz der Auswertung: Die Messlatte haengt an der Natur der Frage, nie an der
Konfiguration des Laufs. Keine Stellschraube (DROP_TYPES, SOURCE, CHUNK_SIZE) darf
einen Nenner verschieben -- sonst zieht dieselbe Einstellung, die das Retrieval
veraendert, auch den Beobachtungspunkt mit.
"""
import sys, json, glob, re, os, sqlite3, difflib, unicodedata
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
HYBRID        = os.environ.get("HYBRID", "0") == "1"      # Vektor + BM25 (FTS5) per Reciprocal Rank Fusion; nur mit Index
RRF_K         = int(os.environ.get("RRF_K", 60))          # Daempfung der Rangfusion (Cormack et al.: 60)
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


# Buchstaben, die NFKD nicht in Grundbuchstabe + Akzent zerlegt (oder die deutsch
# ausgeschrieben werden sollen). Alles andere erledigt NFKD: é->e, â->a, ó->o, Ｆ->f, ﬁ->fi.
_TRANSLIT = (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"), ("ł", "l"), ("ø", "o"), ("æ", "ae"),
             ("œ", "oe"), ("đ", "d"), ("ð", "d"), ("þ", "th"), ("ı", "i"))


def spiel_slug(name):
    """Anzeigename -> stabile spiel_id ("Brass: Birmingham" -> "brass-birmingham").

    Umlaute werden ausgeschrieben statt zu Bindestrichen ("Kämpfer" -> "kaempfer",
    nicht "k-mpfer"); ß wird zu ss (APFS faltet ohnehin so); sonstige Akzente
    fallen per NFKD weg ("Café Łódź" -> "cafe-lodz"). Was dann noch kein ASCII
    ist (etwa CJK), faellt weg -- bleibt nichts, ist das ein Fehler.
    """
    s = (name or "").casefold()
    for alt, neu in _TRANSLIT:
        s = s.replace(alt, neu)
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", "-", s.casefold()).strip("-")
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
        # Zwei verschiedene Spiele, eine spiel_id ("Die Crew" / "Die Crew?" waeren
        # dasselbe, "Café" / "Cafe!" auch -- aber "Brass" und "Brass!!" eines anderen
        # Verlags nicht unterscheidbar): laut statt still zusammenzulegen.
        if name and normalisiere(name) != normalisiere(meta["name"]):
            raise KonfigFehler(
                f"spiel_id {spiel_id!r} gehoert schon zu {meta['name']!r}, nicht zu {name!r}. "
                "Fuer ein anderes Spiel eine eigene --spiel-id waehlen; fuer eine Umbenennung "
                f"{pfad} von Hand aendern.")
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


# ---------- Spielzuordnung: Name/Alias/Hoerfehler -> Spiel (Pipe und CLI) ----------
def normalisiere(name):
    """Spielname fuer den Vergleich: klein, ohne Satzzeichen und Leerraum.

    "Brass: Birmingham" und "brass birmingham" sollen gleich aussehen; Whisper
    und Haiku liefern Titel in wechselnder Schreibweise.
    """
    return re.sub(r"[\W_]+", "", (name or "").casefold())


def katalog_aus(name, aliase):
    """{kanonischer Name: [normalisierte Schreibweisen]} aus den Valves."""
    formen = [name] + [a for a in (aliase or "").split(",") if a.strip()]
    return {name: sorted({normalisiere(f) for f in formen if normalisiere(f)})}


# Liegen die zwei besten unscharfen Treffer naeher beieinander, ist die Zuordnung
# ein Muenzwurf -- dann lieber nachfragen. Mit vielen Spielen im Index real
# ("Brass: Lancashire" / "Brass: Birmingham").
MEHRDEUTIG_ABSTAND = 0.05


# Unscharfe Treffer nur zwischen aehnlich langen Schreibweisen. Ohne diese Bedingung
# wurde ein kurzer Name zum Auffangbecken: "Fujian" -> "Fuji" liegt bei difflib genau
# auf der Schwelle 0,8 (2*4/10), obwohl zwei Buchstaben fehlen. Laengen 4 zu 6 = 0,67.
# Hoerfehler aendern die Laenge kaum ("Food Chain Magnet" 15 zu 16 Zeichen).
MIN_LAENGENVERHAELTNIS = 0.8


def _treffer_wert(n, f, schwelle, matcher=None):
    """difflib-Ratio fuer einen TREFFER; 0, wenn Laenge oder Schnelltest ausschliessen.

    matcher: {Schreibweise: SequenceMatcher} -- difflib bereitet die ZWEITE Sequenz
    vor und cached das; bei vielen Wortfolgen gegen dieselben Namen der Hauptkosten-
    punkt (nenne_spiele).
    """
    if min(len(n), len(f)) < MIN_LAENGENVERHAELTNIS * max(len(n), len(f)):
        return 0.0
    if matcher is None:
        m = difflib.SequenceMatcher(None, n, f)
    else:
        m = matcher.get(f)
        if m is None:
            m = matcher[f] = difflib.SequenceMatcher(None, "", f)
        m.set_seq1(n)
    if m.real_quick_ratio() < schwelle or m.quick_ratio() < schwelle:
        return 0.0
    return m.ratio()


def ordne_spiel(anfrage, katalog, schwelle=0.8, vorschlaege=True, _matcher=None):
    """("treffer", Name) oder ("unbekannt", [Vorschlaege]).

    Exakt nach Normalisierung, sonst unscharf (difflib) gegen jede Schreibweise --
    fuer Hoerfehler wie "Food Chain Magnet". Unterhalb der Schwelle kein Treffer:
    lieber "kein Regelheft" als die Regeln des falschen Spiels. Ebenso kein
    Treffer, wenn die Anfrage mehrdeutig ist (exakt bei mehreren Spielen, etwa
    ein gemeinsamer Alias, oder zwei unscharfe Treffer fast gleichauf), und kein
    unscharfer Treffer zwischen deutlich verschieden langen Schreibweisen.
    Vorschlaege bleiben grosszuegig (Ratio >= 0,5, ohne Laengenbedingung).
    """
    n = normalisiere(anfrage)
    if not n:
        return "unbekannt", []
    exakt = sorted(kanon for kanon, formen in katalog.items() if n in formen)
    if len(exakt) == 1:
        return "treffer", exakt[0]
    if exakt:
        return "unbekannt", exakt
    bewertet = []
    for kanon, formen in katalog.items():
        bewertet.append((max(_treffer_wert(n, f, schwelle, _matcher) for f in formen), kanon))
    bewertet.sort(reverse=True)
    if bewertet and bewertet[0][0] >= schwelle:
        knapp = [k for r, k in bewertet if r >= schwelle and bewertet[0][0] - r < MEHRDEUTIG_ABSTAND]
        if len(knapp) > 1:
            return "unbekannt", knapp
        return "treffer", bewertet[0][1]
    if not vorschlaege:          # nenne_spiele fragt hunderte Wortfolgen ab
        return "unbekannt", []
    roh = sorted(((max(difflib.SequenceMatcher(None, n, f).ratio() for f in formen), kanon)
                  for kanon, formen in katalog.items()), reverse=True)
    return "unbekannt", [k for r, k in roh if r >= 0.5]


def nenne_spiele(text, katalog, max_woerter=6):
    """Welche Spiele nennt ein Nutzertext? -> sortierte Liste kanonischer Namen.

    Fuer den Chat, in dem es kein Feld regelfrage.spiel gibt. Genannt ist ein Spiel,
    wenn der ganze Text ein Spielname ist oder eine Wortfolge (1..max_woerter
    Woerter) nach derselben strengen Zuordnung wie ordne_spiel trifft. Eine
    Wortfolge, die in einer laengeren getroffenen liegt, zaehlt nicht ("Brass" in
    "Brass Birmingham"). Mehrdeutige Wortfolgen bringen alle Kandidaten mit --
    mehr als ein Name heisst fuer den Aufrufer: nachfragen.
    """
    matcher = {}
    status, erg = ordne_spiel(text, katalog, vorschlaege=False, _matcher=matcher)
    if status == "treffer":
        return [erg]
    woerter = re.findall(r"\w+", text or "")
    # Nach Laenge vorsortiert: fuer eine Wortfolge kommen nur Schreibweisen in Frage,
    # die die Laengenbedingung erfuellen koennen -- alle anderen liefern ohnehin 0.
    # Zusammen mit den wiederverwendeten Matchern: gemessen bei 250 Spielen und
    # 29 Woertern 101 ms -> siehe README.
    nach_laenge = {}
    for kanon, formen in katalog.items():
        for f in formen:
            nach_laenge.setdefault(len(f), []).append((kanon, f))

    def teilkatalog(n):
        tk = {}
        for laenge in range(int(len(n) * MIN_LAENGENVERHAELTNIS), int(len(n) / MIN_LAENGENVERHAELTNIS) + 2):
            for kanon, f in nach_laenge.get(laenge, ()):
                tk.setdefault(kanon, []).append(f)
        return tk

    spannen = []
    for i in range(len(woerter)):
        for j in range(i + 1, min(len(woerter), i + max_woerter) + 1):
            folge = " ".join(woerter[i:j])
            status, erg = ordne_spiel(folge, teilkatalog(normalisiere(folge)), vorschlaege=False, _matcher=matcher)
            if status == "treffer":
                spannen.append((i, j, {erg}))
            elif erg:                                    # exakt mehrdeutig (gemeinsamer Alias)
                spannen.append((i, j, set(erg)))
    offen = [s for s in spannen
             if not any(o[0] <= s[0] and s[1] <= o[1] and (o[0], o[1]) != (s[0], s[1]) for o in spannen)]
    return sorted(set().union(*(s[2] for s in offen))) if offen else []


def nur_spielname(text, katalog):
    """Kanonischer Name, wenn der ganze Text nur ein Spielname ist (Antwort auf die Rueckfrage)."""
    status, erg = ordne_spiel(text, katalog, vorschlaege=False)
    return erg if status == "treffer" else None


def katalog_aus_index(spiele):
    """({Name: [Schreibweisen]}, {Name: spiel_id}) aus rag.spiele_im_index.

    Name, Aliase aus spiel.json und die spiel_id selbst zaehlen als Schreibweise.
    Zwei Spiele mit gleichem Namen waeren nicht unterscheidbar -> Fehler.
    """
    katalog, ids = {}, {}
    for s in spiele:
        if s["name"] in katalog:
            raise ValueError(f"Zwei Spiele im Index heissen {s['name']!r} ({ids[s['name']]}, {s['spiel_id']}) "
                             "-- Namen in spiel.json eindeutig machen.")
        formen = [s["name"], s["spiel_id"]] + list(s.get("aliase") or [])
        katalog[s["name"]] = sorted({normalisiere(f) for f in formen if normalisiere(f)})
        ids[s["name"]] = s["spiel_id"]
    return katalog, ids


def loese_spiel(anfrage, data_dir=None):
    """spiel_id zu einer Angabe auf der Kommandozeile: spiel_id ODER Name/Alias.

    Dieselbe Zuordnung wie die Pipe, damit --spiel ueberall dasselbe bedeutet.
    """
    ids = liste_spiele(data_dir)
    if anfrage in ids:
        return anfrage
    katalog, zu_id = katalog_aus_index([lies_spiel(s, data_dir) for s in ids])
    status, ergebnis = ordne_spiel(anfrage, katalog)
    if status == "treffer":
        return zu_id[ergebnis]
    vorschlag = f" Meintest du {' oder '.join(ergebnis[:3])}?" if ergebnis else ""
    raise KonfigFehler(f"Kein Spiel {anfrage!r} unter {data_dir or DATA_DIR}.{vorschlag} "
                       f"Vorhanden: {', '.join(ids) or '-'}")


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
    embs = np.array(r.json()["embeddings"], dtype=np.float32)
    # Liefert Ollama weniger (oder keine) Vektoren als Texte, liefe das sonst erst
    # spaeter als unverstaendlicher matmul-Fehler auf.
    if len(texts) and (embs.ndim != 2 or len(embs) != len(texts)):
        raise RuntimeError(f"Ollama ({EMBED_MODEL}) lieferte Embeddings der Form {embs.shape} "
                           f"fuer {len(texts)} Texte.")
    return embs


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
# rowid = chunks.id. Die Spalte tag traegt ein Token je (Spiel, Konfiguration): der
# Spielfilter steht damit IM MATCH-Ausdruck und FTS5 schneidet Posting-Listen. Die
# erste Fassung filterte mit rowid IN (json_each(...)) -- gemessen wuchs das mit
# (passende Zeilen gesamt) x (Chunks des Spiels): 100 Spiele x 181 Chunks 235 ms,
# 5 x 1000 schon 407 ms pro Frage; bei 47k Zeilen und einem 2000er-Heft Sekunden.
_FTS_SQL = ("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5("
            "text, tag, tokenize='unicode61 remove_diacritics 2')")


def fts_tag(spiel_id, konfig):
    """Ein FTS-Token je (Spiel, Konfiguration) -- nur Buchstaben/Ziffern, damit der
    Tokenizer es nicht zerlegt."""
    import hashlib
    return "t" + hashlib.sha1(f"{spiel_id}\0{konfig}".encode()).hexdigest()[:24]


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
    with open(pfad, "rb") as f:
        kopf = f.read(20)
    # Byte 18/19 des SQLite-Kopfs = 2: WAL-Modus. Lesen braucht dann -shm/-wal neben der
    # Datei -- auf dem read-only-Mount der Pipe scheitert das, und zwar nicht sofort.
    if len(kopf) == 20 and kopf[18] == 2 and kopf[19] == 2:
        raise KonfigFehler(f"Index {pfad} ist im WAL-Modus; read-only (Pipe-Mount) geht das nicht. "
                           f"Auf dem Host: sqlite3 {pfad} 'PRAGMA journal_mode=DELETE'")
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
                con.execute("INSERT INTO chunks_fts (rowid, text, tag) VALUES (?,?,?)",
                            (cur.lastrowid, text, fts_tag(spiel_id, konfig)))
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

    Ein kaputtes Spiel (spiel.json ohne oder mit leerer knowledge.jsonl, Ollama-
    Fehler ...) bricht nicht mehr alles ab: es wird gemeldet, sein alter Stand
    bleibt, die uebrigen laufen weiter, und am Ende kommt ein KonfigFehler mit
    allen Fehlern (Exit-Code 2). Wer genau ein Spiel anfordert, bekommt dessen
    eigenen Fehler.
    """
    alle = spiel_ids is None
    spiel_ids = liste_spiele(data_dir) if alle else [pruefe_spiel_id(s) for s in spiel_ids]
    con = oeffne_index(pfad, schreibend=True)
    try:
        ergebnis, fehler = {}, {}
        for sid in spiel_ids:
            try:
                ergebnis[sid] = aktualisiere_spiel(con, sid, data_dir)
            except Exception as e:
                con.rollback()
                if len(spiel_ids) == 1 and not alle:
                    raise
                fehler[sid] = e
                ergebnis[sid] = ("fehler", 0)
                ausgabe(f"  {sid}: FEHLER {type(e).__name__}: {e}")
                continue
            ausgabe(f"  {sid}: {ergebnis[sid][0]} ({ergebnis[sid][1]} Chunks)")
        if alle:
            weg = [r[0] for r in con.execute("SELECT spiel_id FROM spiele")]
            for sid in sorted(set(weg) - set(spiel_ids)):
                entferne_spiel(con, sid)
                ergebnis[sid] = ("entfernt", 0)
                ausgabe(f"  {sid}: entfernt (kein Verzeichnis mehr unter data/)")
        if fehler:
            e = KonfigFehler(f"{len(fehler)} von {len(spiel_ids)} Spielen nicht indexiert (alter Stand bleibt): "
                             + "; ".join(f"{s}: {type(x).__name__}: {x}" for s, x in list(fehler.items())[:5])
                             + (" ..." if len(fehler) > 5 else ""))
            e.ergebnis = ergebnis
            raise e
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
    # spiel_id kommt aus der ZEILE, nicht aus dem Aufruf: sonst truege ein Chunk
    # eines fremden Spiels, der durch einen kaputten Filter rutscht, das richtige Etikett.
    zeilen = con.execute("SELECT id, spiel_id, seite, typ, text, emb FROM chunks "
                         "WHERE spiel_id=? AND konfig=? ORDER BY pos", (spiel_id, konfig)).fetchall()
    pruefe_typ_feld([{"typ": z[3]} for z in zeilen if z[3] is not None], drop)
    zeilen = [z for z in zeilen if z[3] not in drop]
    chunks = [{"doc": "knowledge", "seite": json.loads(z[2]), "text": z[4],
               "spiel_id": z[1], "chunk_id": z[0]} for z in zeilen]
    embs = np.frombuffer(b"".join(z[5] for z in zeilen), dtype="<f4").reshape(len(zeilen), stand[0])
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


def fts_abfrage(query):
    """Frage -> FTS5-Ausdruck: jedes Wort als Phrase, ODER-verknuepft.

    Die Frage direkt als MATCH-Ausdruck zu geben, bricht an Anfuehrungszeichen,
    Klammern, AND/OR/NOT und '*' -- Nutzertext ist keine Abfragesprache.
    """
    # lower, NICHT casefold: casefold macht aus "Straße" "strasse", der FTS5-Tokenizer
    # unicode61 behaelt ß -- "Straße", "Maß", "groß" faenden sonst nichts.
    woerter = re.findall(r"\w+", query.lower())
    return " OR ".join('"' + w.replace('"', '""') + '"' for w in dict.fromkeys(woerter))


def bm25_rangfolge(con, query, chunks, n):
    """Positionen in `chunks` nach BM25, beste zuerst -- nur unter DIESEN Chunks.

    Der Spielfilter steht im MATCH-Ausdruck selbst (tag-Token des Stands), also
    vor ORDER BY/LIMIT: ein Nachfilter liesse Treffer anderer Spiele die eigenen
    aus den ersten n verdraengen. Per DROP_TYPES ausgelassene Chunks desselben
    Spiels koennen noch darunter sein; deshalb wird um genau deren Anzahl mehr
    geholt und danach auf die geladenen Chunks beschraenkt -- das ist exakt das
    Top-n der geladenen. Die tag-Spalte hat BM25-Gewicht 0. Die IDF-Statistik von
    FTS5 bleibt tabellenweit (alle Spiele, alle Staende): sie gewichtet Woerter,
    waehlt aber keine fremden Chunks aus.
    """
    ausdruck = fts_abfrage(query)
    if not ausdruck or not chunks:
        return []
    if not _hat_fts(con):
        raise KonfigFehler("HYBRID=1, aber der Index hat keine FTS5-Tabelle (SQLite ohne FTS5?).")
    pos = {c["chunk_id"]: i for i, c in enumerate(chunks)}
    spiel_id, konfig = con.execute("SELECT spiel_id, konfig FROM chunks WHERE id=?",
                                   (chunks[0]["chunk_id"],)).fetchone()
    gesamt = con.execute("SELECT chunks FROM staende WHERE spiel_id=? AND konfig=?", (spiel_id, konfig)).fetchone()[0]
    ausgelassen = gesamt - len(chunks)
    zeilen = con.execute(
        "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? "
        "ORDER BY bm25(chunks_fts, 1.0, 0.0), rowid LIMIT ?",
        (f'tag : "{fts_tag(spiel_id, konfig)}" AND text : ({ausdruck})', n + ausgelassen)).fetchall()
    return [pos[r[0]] for r in zeilen if r[0] in pos][:n]


def rrf(rangfolgen, k=None):
    """Reciprocal Rank Fusion: [(position, score)], beste zuerst.

    Gleichstand faellt auf die Reihenfolge der ersten Rangfolge (Vektor) zurueck,
    damit das Ergebnis deterministisch ist.
    """
    k = RRF_K if k is None else k
    score, erster = {}, {}
    for folge in rangfolgen:
        for rang, i in enumerate(folge, 1):
            score[i] = score.get(i, 0.0) + 1.0 / (k + rang)
            erster.setdefault(i, (len(erster), rang))
    return sorted(score.items(), key=lambda x: (-x[1], erster[x[0]]))


def drop_fuer_index(env=None):
    """DROP_TYPES fuer den Index-Weg: dort ist die Quelle immer die Wissensbasis."""
    env = dict(os.environ if env is None else env)
    env["SOURCE"] = "knowledge"
    return lies_drop_types(env)


def rangfolge(sims):
    """Positionen nach absteigendem Score; bei exaktem Gleichstand die niedrigere zuerst.

    Die eine Stelle, an der beide Wege (Einzeldatei, Index) ranken. Frueher
    np.argsort(-sims) -- quicksort, nicht stabil: bei Gleichstand (Duplikat-Chunks)
    hing die Reihenfolge und an der top_k-Grenze die Menge von der Plattform ab
    (gemessen: numpy 2.5.3 auf macOS/arm64 weicht ab n=17 in 200/200 Faellen von
    stabil ab; Linux/x86_64 mit anderem SIMD-Sort lieferte andere Top-k als macOS).
    """
    return np.argsort(-sims, kind="stable")


def retrieve(query, chunks=None, embs=None, k=TOP_K, spiel_id=None, index=None):
    """Top-k (chunk, score) zur Frage.

    Ohne spiel_id der alte In-Memory-Weg ueber (chunks, embs). Mit spiel_id kommen
    Kandidaten ausschliesslich aus diesem Spiel -- der Filter wirkt VOR dem
    Ranking, weil lade_spiel nur dessen Zeilen liefert. chunks/embs duerfen dann
    vorab mit lade_spiel geladen sein (eval: einmal pro Spiel statt pro Frage).
    Die Rangfolge-Rechnung ist fuer beide Wege dieselbe Zeile Code.
    """
    con = None
    if spiel_id is not None:
        pruefe_spiel_id(spiel_id)
        con = index if index is not None else oeffne_index()
        if chunks is None:
            chunks, embs = lade_spiel(con, spiel_id, drop_fuer_index())
        fremd = {c.get("spiel_id") for c in chunks} - {spiel_id}
        if fremd:
            raise KonfigFehler(f"retrieve(spiel_id={spiel_id!r}) mit Chunks von {sorted(fremd)}.")
    elif HYBRID:
        raise KonfigFehler("HYBRID=1 braucht den Index (spiel_id); der Einzeldatei-Weg hat kein BM25.")
    if embs is None or getattr(embs, "ndim", 0) != 2 or len(embs) == 0 or len(embs) != len(chunks):
        raise KonfigFehler(f"Keine durchsuchbaren Chunks: {len(chunks or [])} Chunks, Embeddings "
                           f"{getattr(embs, 'shape', None)}. Quelle leer oder nach DROP_TYPES leer?")
    q = l2norm(embed([query]))[0]
    if embs.shape[1] != q.shape[0]:
        raise KonfigFehler(f"Embedding-Dimension passt nicht: Chunks {embs.shape[1]}, Frage {q.shape[0]} "
                           f"({EMBED_MODEL}). Index mit anderem Modell gebaut?")
    sims = embs @ q
    if HYBRID:
        vektor = [int(i) for i in rangfolge(sims)[:CANDIDATES]]
        fusion = rrf([vektor, bm25_rangfolge(con, query, chunks, CANDIDATES)])
        if not RERANK:
            return [(chunks[i], float(s)) for i, s in fusion[:k]]
        cand = [i for i, _ in fusion[:CANDIDATES]]
        scores = get_reranker().predict([[query, chunks[i]["text"]] for i in cand])
        ranked = sorted(zip(cand, scores), key=lambda x: -x[1])[:k]
        return [(chunks[i], float(s)) for i, s in ranked]
    if RERANK:
        # 1. Stufe: grob CANDIDATES per Embedding holen
        cand = [int(i) for i in rangfolge(sims)[:CANDIDATES]]
        # 2. Stufe: Cross-Encoder bewertet jedes Frage-Chunk-Paar einzeln
        scores = get_reranker().predict([[query, chunks[i]["text"]] for i in cand])
        ranked = sorted(zip(cand, scores), key=lambda x: -x[1])[:k]
        return [(chunks[i], float(s)) for i, s in ranked]
    order = rangfolge(sims)[:k]
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


# ---------- Migration: alte Einzeldatei -> data/<spiel_id>/ ----------
def _schreibe_oder_pruefe(pfad, inhalt):
    """Neu schreiben oder -- falls schon da -- nur bestaetigen, dass es dasselbe ist.

    Nie ueberschreiben: eine abweichende Datei im Spielverzeichnis ist ein
    neuerer Stand (z.B. nach classify.py) und kein Migrationsrest.
    """
    if os.path.exists(pfad):
        with open(pfad, encoding="utf-8") as f:
            if f.read() == inhalt:
                return "unveraendert"
        raise KonfigFehler(f"{pfad} existiert schon mit anderem Inhalt -- nicht ueberschrieben. "
                           "Zum erneuten Migrieren die Datei vorher selbst entfernen.")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(inhalt)
    return "geschrieben"


def migriere(quelle, name, spiel_id=None, sprache="de", aliase=None, quelle_pdf=None,
             golden=None, data_dir=None):
    """Einzeldatei knowledge.jsonl (+ golden_set.json) in data/<spiel_id>/ ueberfuehren.

    Kopiert, verschiebt nicht: die alte Datei bleibt liegen, der alte Weg (und eine
    Pipe, die sie noch gemountet hat) funktioniert weiter. Inhalt und Reihenfolge
    jedes Eintrags bleiben, dazu kommen nur 'spiel' und 'spiel_id' -- deshalb
    liefert der Index danach dieselben Chunks in derselben Folge.
    """
    roh = lies_jsonl(quelle)
    if not roh:
        raise KonfigFehler(f"{quelle} ist leer.")
    for c in roh:
        chunk_seite(c)   # ohne 'seite' keine zitierfaehige Fundstelle -> erst neu einlesen
    spiel_id = pruefe_spiel_id(spiel_id or spiel_slug(name))
    fremd = sorted({c["spiel_id"] for c in roh if c.get("spiel_id") not in (None, spiel_id)})
    if fremd:
        raise KonfigFehler(f"{quelle} enthaelt Chunks anderer Spiele: {fremd}.")
    meta = lege_spiel_an(name, spiel_id, sprache, aliase, quelle_pdf, data_dir)
    felder = spiel_felder(meta)
    zeilen = "".join(json.dumps({**c, **felder}, ensure_ascii=False) + "\n" for c in roh)
    ergebnis = {"knowledge.jsonl": _schreibe_oder_pruefe(knowledge_pfad(spiel_id, data_dir), zeilen)}
    if golden:
        with open(golden, encoding="utf-8") as f:
            gs = json.load(f)
        if gs.get("spiel_id") not in (None, spiel_id):
            raise KonfigFehler(f"{golden} gehoert zu {gs['spiel_id']!r}, nicht zu {spiel_id!r}.")
        gs = {"spiel_id": spiel_id, **{k: v for k, v in gs.items() if k != "spiel_id"}}
        ergebnis["golden_set.json"] = _schreibe_oder_pruefe(
            os.path.join(spiel_verzeichnis(spiel_id, data_dir), "golden_set.json"),
            json.dumps(gs, ensure_ascii=False, indent=2) + "\n")
    return spiel_id, len(roh), ergebnis


def cmd_migriere(args):
    """python rag.py migriere --spiel NAME [--spiel-id ID] [--sprache de] [--aliase "a,b"]
                             [--quelle knowledge.jsonl] [--golden golden_set.json] [--pdf heft.pdf]"""
    basis = os.path.dirname(os.path.abspath(__file__))
    rest, opt = spiel_argumente(args)
    extra = {"--quelle": os.path.join(basis, "knowledge.jsonl"), "--pdf": None,
             "--golden": os.path.join(basis, "golden_set.json")}
    i = 0
    while i < len(rest):
        if rest[i] in extra and i + 1 < len(rest):
            extra[rest[i]] = rest[i + 1]
            i += 2
        else:
            raise KonfigFehler(f"Unbekanntes Argument {rest[i]!r}. {cmd_migriere.__doc__}")
    if not opt or not opt.get("name"):
        raise KonfigFehler(f"--spiel NAME fehlt. {cmd_migriere.__doc__}")
    golden = extra["--golden"] if os.path.exists(extra["--golden"]) else None
    sid, n, erg = migriere(extra["--quelle"], opt["name"], opt.get("spiel_id"), opt.get("sprache") or "de",
                           opt.get("aliase"), extra["--pdf"], golden)
    print(f"{n} Eintraege aus {extra['--quelle']} -> data/{sid}/  ({erg})")
    if golden is None:
        print(f"Kein Golden Set unter {extra['--golden']} -- data/{sid}/golden_set.json von Hand anlegen.")
    print(f"Die alte Datei bleibt liegen. Weiter mit:\n  python rag.py index {sid}\n"
          f"  python rag.py vergleiche {sid}     # alter gegen neuen Weg, ohne LLM")


def cmd_vergleiche(args):
    """python rag.py vergleiche <spiel_id> [--quelle knowledge.jsonl]

    Regressionspruefung mit ECHTEN Embeddings, ohne LLM: fuer jede Frage des
    Golden Sets Top-k ueber den alten In-Memory-Weg (Einzeldatei) und ueber den
    Index. Misst mit, ob Ollama batch-unabhaengig einbettet -- der Index bettet in
    Stuecken von EMBED_BATCH und inklusive gefilterter Typen ein, der alte Weg in
    einem Aufruf ohne sie. Exit-Code 1 bei jeder Abweichung in der Rangfolge.
    """
    if not args:
        raise KonfigFehler(cmd_vergleiche.__doc__)
    sid = loese_spiel(args[0])
    quelle = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge.jsonl")
    if "--quelle" in args[1:-1]:
        quelle = args[args.index("--quelle") + 1]
    drop = drop_fuer_index()
    gs = lade_golden_set(sid)
    if not os.path.exists(quelle):
        raise KonfigFehler(f"Quelle des alten Wegs {quelle} fehlt (Symlink kaputt?). --quelle angeben.")
    roh = lies_jsonl(quelle)
    alt_chunks = baue_knowledge_chunks(roh, drop) if roh else []
    if not alt_chunks:
        raise KonfigFehler(f"Alter Weg ohne Chunks: {quelle} (-> {os.path.realpath(quelle)}) hat {len(roh)} "
                           f"Eintraege, nach DROP_TYPES={','.join(sorted(drop)) or '-'} bleibt keiner.")
    alt_embs = l2norm(embed([c["text"] for c in alt_chunks]))
    aktualisiere_index([sid], ausgabe=lambda *_: None)
    con = oeffne_index()
    try:
        neu_chunks, neu_embs = lade_spiel(con, sid, drop)
        print(f"{_konfig_zeile('vergleich')}  hybrid={HYBRID}")
        print(f"alt: {len(alt_chunks)} Chunks aus {quelle} (-> {os.path.realpath(quelle)})   "
              f"neu: {len(neu_chunks)} Chunks aus dem Index\n")
        abweichend, max_diff = [], 0.0
        for f in gs["fragen"]:
            alt = retrieve(f["frage"], alt_chunks, alt_embs)
            neu = retrieve(f["frage"], neu_chunks, neu_embs, spiel_id=sid, index=con)
            gleich = [(h["seite"], h["text"]) for h, _ in alt] == [(h["seite"], h["text"]) for h, _ in neu]
            diff = max((abs(a - b) for (_, a), (_, b) in zip(alt, neu)), default=0.0)
            max_diff = max(max_diff, diff)
            if not gleich:
                abweichend.append(f["id"])
            print(f"[{f['id']}] {'gleich    ' if gleich else 'ABWEICHEND'} max|dScore|={diff:.2e}  "
                  f"alt={[h['seite'] for h, _ in alt]} neu={[h['seite'] for h, _ in neu]}")
    finally:
        con.close()
    print(f"\n{len(gs['fragen']) - len(abweichend)}/{len(gs['fragen'])} Fragen mit identischer Top-{TOP_K}-Folge, "
          f"max|dScore| ueber alle {max_diff:.2e}")
    if abweichend:
        print(f"ABWEICHEND: Fragen {abweichend}")
        sys.exit(1)


# ---------- Modi ----------
def cmd_index(args):
    """python rag.py index [spiel_id ...|--alle] -- nur Geaendertes wird neu eingebettet."""
    ids = [loese_spiel(a) for a in args if a != "--alle"]
    print(f"Index {INDEX_PATH}  Konfiguration {index_konfig()}")
    aktualisiere_index(ids or None)


def ask_argumente(args):
    """(spiel oder None, Frage) aus `ask [--spiel X | --spiel=X] Frage...` -- --spiel an beliebiger Stelle."""
    spiel, rest, i = None, [], 0
    while i < len(args):
        a = args[i]
        if a == "--spiel":
            if i + 1 >= len(args):
                raise KonfigFehler("--spiel braucht einen Wert (Name oder spiel_id).")
            spiel, i = args[i + 1], i + 2
            continue
        if a.startswith("--spiel="):
            spiel = a.split("=", 1)[1]
        else:
            rest.append(a)
        i += 1
    if not " ".join(rest).strip():
        raise KonfigFehler("Keine Frage angegeben.")
    return spiel, " ".join(rest)


def cmd_ask(query, spiel=None):
    """spiel: Name, Alias oder spiel_id -- dieselbe Zuordnung wie in der Pipe."""
    spiel_id = None if spiel is None else loese_spiel(spiel)
    if spiel_id is None:
        chunks, embs = build_index()
        hits = retrieve(query, chunks, embs)
    else:
        aktualisiere_index([spiel_id], ausgabe=lambda *_: None)   # nur Geaendertes wird eingebettet
        con = oeffne_index()
        try:
            hits = retrieve(query, spiel_id=spiel_id, index=con)
        finally:
            con.close()
    print(answer(query, hits))
    print("\nAbgerufen:", [(h["doc"], f"S.{h['seite']}", round(s, 3)) for h, s in hits])


def _konfig_zeile(quelle):
    return (f"Config: chunk={CHUNK_SIZE}/{CHUNK_OVERLAP}  top_k={TOP_K}  rerank={RERANK}"
            f"{'(' + RERANK_MODEL + ', cand=' + str(CANDIDATES) + ')' if RERANK else ''}"
            f"  embed={EMBED_MODEL}  llm={LLM_MODEL}  think={THINK}"
            f"  source={quelle}  drop_types={os.environ.get('DROP_TYPES', '') or '-'}")


def cmd_eval(golden_set_pfad=None):
    # Pfad als Parameter, damit der komplette Wertungsdurchlauf mit einem
    # Beispiel-Golden-Set testbar ist (siehe test_wertung.py, TestCmdEval).
    gs = json.load(open(golden_set_pfad
                        or os.path.join(os.path.dirname(__file__), "golden_set.json")))
    chunks, embs = build_index()
    print(_konfig_zeile(os.environ.get('SOURCE', 'pdf')))
    print(f"Index: {len(chunks)} Chunks aus {len(set(c['doc'] for c in chunks))} PDF(s)\n")
    saetze = werte_fragen(gs["fragen"], lambda frage: retrieve(frage, chunks, embs))
    for zeile in formatiere_zusammenfassung(fasse_zusammen(saetze)):
        print(zeile)


def lade_golden_set(spiel_id, data_dir=None):
    """data/<spiel_id>/golden_set.json -- muss sich ausdruecklich zu diesem Spiel bekennen.

    Ein Golden Set ohne oder mit fremder spiel_id ist ein Kopierfehler: seine
    Seitenzahlen wuerden gegen ein anderes Heft gewertet.
    """
    pfad = os.path.join(spiel_verzeichnis(spiel_id, data_dir), "golden_set.json")
    if not os.path.exists(pfad):
        raise KonfigFehler(f"{pfad} fehlt -- ohne Golden Set keine Eval fuer {spiel_id!r}.")
    with open(pfad, encoding="utf-8") as f:
        gs = json.load(f)
    if gs.get("spiel_id") != spiel_id:
        raise KonfigFehler(f"{pfad}: Feld 'spiel_id' ist {gs.get('spiel_id')!r}, erwartet {spiel_id!r}.")
    return gs


def cmd_eval_spiel(spiel_id, data_dir=None):
    """Golden Set eines Spiels gegen den Index -- dieselbe Wertung wie cmd_eval."""
    gs = lade_golden_set(spiel_id, data_dir)
    aktualisiere_index([spiel_id], data_dir=data_dir, ausgabe=lambda *_: None)
    con = oeffne_index()
    try:
        chunks, embs = lade_spiel(con, spiel_id, drop_fuer_index())
        name = lies_spiel(spiel_id, data_dir)["name"]
        print(_konfig_zeile("index") + f"  hybrid={HYBRID}")
        print(f"Spiel: {name} ({spiel_id})  Index: {len(chunks)} Chunks\n")
        saetze = werte_fragen(gs["fragen"],
                              lambda frage: retrieve(frage, chunks, embs, spiel_id=spiel_id, index=con))
    finally:
        con.close()
    for zeile in formatiere_zusammenfassung(fasse_zusammen(saetze)):
        print(zeile)
    return saetze


def cmd_eval_spiele(args, data_dir=None):
    """rag.py eval <spiel_id ...> | --alle. Bei mehreren Spielen zusaetzlich ein Gesamtblock.

    --alle nimmt nur Spiele mit golden_set.json und NENNT die uebrigen -- ein
    stilles Auslassen saehe aus wie Abdeckung, die es nicht gibt.
    """
    if "--alle" in args:
        alle = liste_spiele(data_dir)
        ids = [s for s in alle
               if os.path.exists(os.path.join(spiel_verzeichnis(s, data_dir), "golden_set.json"))]
        ohne = [s for s in alle if s not in ids]
        if ohne:
            print(f"Ohne Golden Set, nicht gewertet: {', '.join(ohne)}\n")
        if not ids:
            raise KonfigFehler("Kein Spiel unter data/ hat ein golden_set.json.")
    else:
        ids = [loese_spiel(a, data_dir) for a in args]
    alle_saetze = []
    for sid in ids:
        print(f"==================== {sid} ====================")
        alle_saetze += cmd_eval_spiel(sid, data_dir)
        print()
    if len(ids) > 1:
        print(f"==================== Gesamt ueber {len(ids)} Spiele ====================")
        for zeile in formatiere_zusammenfassung(fasse_zusammen(alle_saetze)):
            print(zeile)
    return alle_saetze


def werte_fragen(fragen, suche):
    """Frage fuer Frage: suchen, antworten, werten, ausgeben. suche(frage) -> hits."""
    saetze = []
    for f in fragen:
        hits = suche(f["frage"])
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
    return saetze


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "eval"
    try:
        if mode == "ask" and len(sys.argv) > 2:
            spiel, frage = ask_argumente(sys.argv[2:])
            cmd_ask(frage, spiel)
        elif mode == "index":
            cmd_index(sys.argv[2:])
        elif mode == "eval" and len(sys.argv) > 2:
            cmd_eval_spiele(sys.argv[2:])
        elif mode == "migriere":
            cmd_migriere(sys.argv[2:])
        elif mode == "vergleiche":
            cmd_vergleiche(sys.argv[2:])
        else:
            cmd_eval()
    except KonfigFehler as e:
        print(f"ABBRUCH (Konfiguration): {e}", file=sys.stderr)
        sys.exit(2)
