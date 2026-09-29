#!/usr/bin/env python3
"""
Auto-Router-Ingestion: parst ein PDF mit Docling, klassifiziert jede Seite und
schickt sie automatisch zur passenden Methode:

  - Tabellen-Region        -> LLM-Verbalisierung
  - normaler Text          -> LLM-Verbalisierung
  - Fragment-Seite         -> Vision (Sicherheitsnetz fuer Infografiken, die
                              Docling faelschlich als viele kleine Text-Items labelt)

Ergebnis -> data/<spiel_id>/knowledge.jsonl (jeder Chunk traegt 'spiel' und
'spiel_id'), dazu data/<spiel_id>/spiel.json. Andere Spiele werden nie angefasst.
Laeuft in der Ingest-venv (docling + pymupdf + requests).

    python auto_ingest.py pdfs/brass.pdf --spiel "Brass: Birmingham" --sprache en --aliase "Brass"
    python auto_ingest.py pdfs/fcm.pdf --spiel-id food-chain-magnate      # Spiel existiert schon

Ohne --spiel gilt der alte Ein-Spiel-Weg (knowledge.jsonl neben dem Skript) --
dann aber nur, wenn die Datei noch nicht existiert: frueher hat ein zweites
Regelheft das erste still ueberschrieben.
"""
import sys, os, base64
from collections import defaultdict
import requests
from docling.document_converter import DocumentConverter
import pymupdf

BASE   = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import rag  # noqa: E402  (Spiel-Layout: rag.spiel_argumente, rag.bereite_spiel_vor)

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LLM    = os.environ.get("LLM_MODEL", "qwen3:14b")
VMODEL = os.environ.get("VISION_MODEL", "qwen2.5vl:7b")
KNOW   = os.path.join(BASE, "knowledge.jsonl")
DPI    = int(os.environ.get("DPI", 150))
# Seiten mit auffaellig vielen Text-Fragmenten sind wahrscheinlich Infografiken,
# die Docling als Text labelt -> ueber Vision behandeln.
FRAGMENT_THRESHOLD = int(os.environ.get("FRAGMENT_THRESHOLD", 50))


def verb_prompt(sprache="de"):
    satzsprache = rag.SPRACHEN[sprache][0]
    return ("Formuliere den folgenden Ausschnitt aus einem Brettspiel-Regelheft in "
            f"vollstaendige, eigenstaendige {satzsprache} Saetze um. Uebernimm ALLE Zahlen, "
            "Namen und Werte EXAKT. Erfinde nichts, lass nichts weg. Bei Tabellen: pro "
            "Zeile ein Satz mit Bezeichnung UND Wert. Antworte nur mit dem Text.")


vision_prompt = rag.vision_prompt   # eine Quelle fuer auto_ingest.py und vision_ingest.py


def verbalize(text, sprache="de"):
    r = requests.post(f"{OLLAMA}/api/chat", json={
        "model": LLM,
        "messages": [{"role": "system", "content": verb_prompt(sprache)},
                     {"role": "user", "content": text}],
        "think": False, "stream": False,
    }, timeout=600)
    r.raise_for_status()
    return r.json()["message"]["content"].strip()


def vision(pdf, pageno, prompt=None):
    pix = pymupdf.open(pdf)[pageno - 1].get_pixmap(dpi=DPI)
    b64 = base64.b64encode(pix.tobytes("png")).decode()
    r = requests.post(f"{OLLAMA}/api/generate", json={
        "model": VMODEL, "prompt": prompt or vision_prompt(), "images": [b64], "stream": False,
    }, timeout=600)
    r.raise_for_status()
    return r.json()["response"].strip()


def ziel(argv):
    """(pdf, Zieldatei, Zusatzfelder je Chunk, meta) -- ein Spiel, ein Verzeichnis."""
    rest, opt = rag.spiel_argumente(argv)
    pdf = rest[0] if rest else next(
        iter(sorted(__import__("glob").glob(os.path.join(BASE, "pdfs", "*.pdf")))), None)
    if not pdf:
        sys.exit("Kein PDF. Nutzung: python auto_ingest.py <pdf> --spiel NAME [--sprache de|en]")
    if opt is None:
        if os.path.exists(KNOW):
            raise rag.KonfigFehler(
                f"{KNOW} existiert schon. Ohne --spiel wuerde es ueberschrieben -- genau so "
                "ist frueher ein Regelheft durch das naechste ersetzt worden. Mit "
                "--spiel NAME (oder --spiel-id) einlesen; fuer die alte Einzeldatei "
                "`python rag.py migriere` benutzen.")
        return pdf, KNOW, {}, {"name": None, "sprache": "de"}
    meta, pfad = rag.bereite_spiel_vor(opt, quelle_pdf=pdf)
    return pdf, pfad, rag.spiel_felder(meta), meta


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pdf, know, felder, meta = ziel(argv)
    sprache = meta.get("sprache") or "de"
    vprompt = vision_prompt(meta.get("name"), sprache)

    print(f"Docling parst {pdf} ...")
    doc = DocumentConverter().convert(pdf).document

    pages = defaultdict(lambda: {"texts": [], "tables": [], "count": 0})
    for item, _ in doc.iterate_items():
        prov = getattr(item, "prov", None)
        if not prov:
            continue
        p = prov[0].page_no
        if type(item).__name__ == "TableItem":
            try:
                pages[p]["tables"].append(item.export_to_markdown())
            except Exception:
                pass
        else:
            t = getattr(item, "text", "") or ""
            if t:
                pages[p]["texts"].append(t)
            pages[p]["count"] += 1

    chunks = []

    def neu(seite, route, text):
        chunks.append({"id": len(chunks) + 1, "seite": seite, "route": route, "text": text, **felder})

    for p in sorted(pages):
        info = pages[p]
        if info["count"] > FRAGMENT_THRESHOLD:
            route = "vision"
            out = vision(pdf, p, vprompt)
            for ln in out.splitlines():
                ln = ln.strip().lstrip("-*0123456789. ").strip()
                if ":" in ln and len(ln) > 5:
                    neu(p, route, ln)
            # Gemischte Seite: von Docling erkannte Tabellen ZUSAETZLICH verbalisieren.
            # Der Vision-Prompt listet Elemente und uebersieht Tabellen sonst leicht.
            for tbl in info["tables"]:
                neu(p, "table", verbalize("Tabelle:\n" + tbl, sprache))
        else:
            route = "text/table"
            for tbl in info["tables"]:
                neu(p, "table", verbalize("Tabelle:\n" + tbl, sprache))
            # Reiner Fliesstext wird ROH uebernommen: Docling liefert bereits saubere
            # Saetze, und Verbalisierung wuerde hier nur Werte verwaessern
            # (aus "50 % Bonus" wird "ein bestimmter Prozentsatz"). Nur Tabellen und
            # Grafiken brauchen die Umwandlung.
            txt = "\n".join(info["texts"]).strip()
            if txt:
                neu(p, "text-roh", txt)
        print(f"  Seite {p:>2}: route={route:11s} (text-items={info['count']}, tabellen={len(info['tables'])})")

    if not chunks:
        # Typisch fuer ein Heft ohne Textlayer, wenn Docling kein OCR macht: lieber
        # laut als eine leere Wissensbasis, die spaeter zu allem "keine Angaben" sagt.
        raise rag.KonfigFehler(f"{pdf}: keine einzige Seite mit Inhalt erkannt (Scan ohne Textlayer?).")
    rag.schreibe_jsonl(know, chunks)
    print(f"{len(chunks)} Chunks -> {know}")
    routes = defaultdict(int)
    for c in chunks:
        routes[c["route"]] += 1
    print("Routen:", dict(routes))


if __name__ == "__main__":
    try:
        main()
    except rag.KonfigFehler as e:
        sys.exit(f"ABBRUCH: {e}")
