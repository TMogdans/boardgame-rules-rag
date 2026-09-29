#!/usr/bin/env python3
"""
Ingestion-Stufe: PDF -> Docling -> LLM-Verbalisierung -> knowledge.jsonl

Docling parst Layout und Tabellen deutlich besser als eine reine Textextraktion.
Anschliessend schreibt ein lokales LLM (ueber Ollama) jeden Block faktentreu in
Saetze um -- so werden vor allem Tabellen fuer die spaetere semantische Suche
auffindbar ("Campaign Manager | Briefkasten | Dauer 3" -> ein Satz).

Jeder Chunk traegt die physische PDF-Seite im Feld 'seite' (1-basiert, Deckblatt
= 1) -- dieselbe Konvention wie auto_ingest.py und das Golden Set. rag.py druckt
den Wert als "Fundstelle (Seite)" aus; fehlt er, stand dort vorher die Chunk-ID.
Bloecke werden deshalb PRO SEITE gebildet und laufen nicht ueber Seitengrenzen.

Laeuft in einer SEPARATEN venv (requirements-ingest.txt), nicht zusammen mit
sentence-transformers -- sonst kollidieren die transformers-Versionen.

    python ingest.py pdfs/mein-spiel.pdf --spiel "Mein Spiel" [--sprache en]
                                             # -> data/mein-spiel/knowledge.jsonl
    python ingest.py pdfs/mein-spiel.pdf     # alter Ein-Spiel-Weg (OUT, Default knowledge.jsonl),
                                             # verweigert das Ueberschreiben einer vorhandenen Datei
"""
import os, sys, json, requests
from collections import defaultdict
from docling.document_converter import DocumentConverter

_BASE = os.path.dirname(os.path.abspath(__file__))
if _BASE not in sys.path:
    sys.path.insert(0, _BASE)
import rag  # noqa: E402  (Spiel-Layout)

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LLM    = os.environ.get("LLM_MODEL", "qwen3:14b")
TARGET = int(os.environ.get("BLOCK_SIZE", 1200))
OUT    = os.environ.get("OUT", "knowledge.jsonl")
SPRACHE = "de"   # Sprache des Regelhefts; main() setzt sie aus spiel.json

VERB_PROMPT = """Du bekommst einen Ausschnitt aus einem Brettspiel-Regelheft (teils als Markdown-Tabelle oder als zerrissener Textausschnitt).
Formuliere ihn in vollstaendige, eigenstaendige {satzsprache} Saetze um, sodass jede Information auch ohne die urspruengliche Struktur verstaendlich ist.

REGELN:
- Uebernimm ALLE Zahlen, Namen und Werte EXAKT aus der Vorlage. Erfinde nichts. Lass nichts weg.
- Bei Tabellen/Auflistungen: schreibe pro Eintrag einen eigenstaendigen Satz, der Bezeichnung UND zugehoerigen Wert nennt.
- Wenn die Zuordnung von Werten zu Bezeichnungen unklar oder zerrissen ist, RATE NICHT. Gib die betroffenen Rohdaten dann unveraendert wieder.
- Fliesstext, der bereits aus vollstaendigen Saetzen besteht, kannst du weitgehend unveraendert uebernehmen.
- Antworte NUR mit dem umformulierten Text, ohne Einleitung, ohne Kommentar."""


def verb_prompt(sprache="de"):
    """Sprache des Regelhefts, nicht der Antwort: Namen und Werte bleiben so woertlich."""
    return VERB_PROMPT.replace("{satzsprache}", rag.SPRACHEN[sprache][0])


def verbalize(text):
    r = requests.post(f"{OLLAMA}/api/chat", json={
        "model": LLM,
        "messages": [{"role": "system", "content": verb_prompt(SPRACHE)},
                     {"role": "user", "content": text}],
        "think": False, "stream": False,
    }, timeout=600)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def sammle_seiten(doc):
    """Docling-Items nach physischer PDF-Seite gruppieren.

    Seitenquelle ist prov[0].page_no -- 1-basiert und identisch zu dem, was
    auto_ingest.py schreibt. Items ohne Provenance (z.B. der Dokument-Wurzel-
    knoten) haben keine Seite und werden uebersprungen; ein Platzhalter waere
    genau die erfundene Seitenzahl, die hier vermieden werden soll.

    export_to_markdown() des Gesamtdokuments ist als Quelle unbrauchbar: dort
    ist die Provenance weg, die Seitenzahl also strukturell nicht verfuegbar.
    """
    seiten = defaultdict(list)
    for item, _ in doc.iterate_items():
        prov = getattr(item, "prov", None)
        if not prov:
            continue
        p = prov[0].page_no
        if type(item).__name__ == "TableItem":
            try:
                seiten[p].append(item.export_to_markdown())
            except Exception:
                pass
        else:
            t = (getattr(item, "text", "") or "").strip()
            if t:
                seiten[p].append(t)
    return dict(seiten)


def split_blocks(md, target=TARGET):
    paras = [p.strip() for p in md.split("\n\n") if p.strip()]
    blocks, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) > target:
            blocks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        blocks.append(cur)
    return blocks


def blocks_mit_seite(seiten, target=TARGET):
    """[(seite, block)] -- Bloecke pro Seite, damit jeder genau eine Seite hat."""
    out = []
    for p in sorted(seiten):
        for b in split_blocks("\n\n".join(seiten[p]), target):
            out.append((p, b))
    return out


def eintrag(cid, seite, roh, text):
    """Ein knowledge.jsonl-Datensatz. 'roh' bleibt zum Gegenpruefen erhalten."""
    return {"id": cid, "seite": seite, "roh": roh, "text": text}


def ziel(argv):
    """(pdf, Zieldatei, Zusatzfelder je Chunk, Sprache).

    Mit --spiel: data/<spiel_id>/knowledge.jsonl -- andere Spiele bleiben unberuehrt.
    Ohne: der alte Weg ueber OUT, aber nie ueber eine vorhandene Datei hinweg.
    """
    rest, opt = rag.spiel_argumente(argv)
    ueberschreiben = "--ueberschreiben" in rest
    rest = [a for a in rest if a != "--ueberschreiben"]
    if not rest:
        print("Nutzung: python ingest.py <pfad/zum/regelheft.pdf> [--spiel NAME] [--sprache de|en]")
        sys.exit(1)
    pdf = rest[0]
    if opt is None:
        if os.path.exists(OUT):
            raise rag.KonfigFehler(
                f"{OUT} existiert schon und wuerde ueberschrieben. Mit --spiel NAME einlesen "
                "(eigenes Verzeichnis je Spiel) oder die Datei vorher selbst entfernen.")
        return pdf, OUT, {}, "de"
    ziel_pfad = rag.knowledge_pfad(opt.get("spiel_id") or rag.spiel_slug(opt["name"]))
    if os.path.exists(ziel_pfad) and not ueberschreiben:
        raise rag.KonfigFehler(f"{ziel_pfad} existiert schon -- mit --ueberschreiben bestaetigen.")
    meta, pfad = rag.bereite_spiel_vor(opt, quelle_pdf=pdf)
    return pdf, pfad, rag.spiel_felder(meta), meta["sprache"]


def main():
    global SPRACHE
    pdf, out, felder, SPRACHE = ziel(sys.argv[1:])
    print(f"Docling parst {pdf} ...")
    doc = DocumentConverter().convert(pdf).document
    blocks = blocks_mit_seite(sammle_seiten(doc))
    print(f"{len(blocks)} Bloecke, verbalisiere mit {LLM} ...")
    with open(out, "w", encoding="utf-8") as f:
        for i, (seite, b) in enumerate(blocks, 1):
            v = verbalize(b)
            e = eintrag(i, seite, b, v)
            e.update(felder)
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
            print(f"  Block {i}/{len(blocks)} (Seite {seite}): {len(b)} -> {len(v)} Zeichen")
    print(f"{out} geschrieben.")


if __name__ == "__main__":
    try:
        main()
    except rag.KonfigFehler as e:
        sys.exit(f"ABBRUCH: {e}")
