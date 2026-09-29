#!/usr/bin/env python3
"""
Vision-Ingestion: verbalisiert eine Grafik-/Infografik-Seite mit einem lokalen
Vision-Modell (via Ollama) und fuegt JEDE Karte als EIGENEN Chunk in knowledge.jsonl
-- mit --spiel in data/<spiel_id>/knowledge.jsonl, sonst in die alte Einzeldatei.

Einzel-Chunks statt eines Riesenblocks: So matcht "Campaign Manager ... Dauer 3"
praezise mit einer Dauer-Frage, statt in einer 30-Karten-Liste unterzugehen.
Idempotent -- ersetzt die vorhandenen vision:-Chunks DESSELBEN Bildes. Frueher
fielen alle vision:-Chunks weg, also loeschte die zweite Grafikseite die erste.

Jeder Chunk traegt die physische PDF-Seite im Feld 'seite' (1-basiert, Deckblatt
= 1) -- dieselbe Konvention wie auto_ingest.py und das Golden Set. Sie steckt im
Dateinamen, den render.py vergibt (seite_6.png -> Seite 6; render.py rechnet die
0-Basiertheit von pymupdf selbst heraus). Ist der Name anders, muss die Seite
ausdruecklich mitgegeben werden -- geraten wird sie nicht.

    python vision_ingest.py seite_6.png --spiel-id food-chain-magnate
    python vision_ingest.py karten.png 6 --spiel "Brass: Birmingham" --sprache en
    SEITE=6 python vision_ingest.py karten.png      # alter Ein-Spiel-Weg
"""
import sys, os, re, json, base64, requests

BASE   = os.path.dirname(os.path.abspath(__file__))
OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
VMODEL = os.environ.get("VISION_MODEL", "qwen2.5vl:7b")
KNOW   = os.path.join(BASE, "knowledge.jsonl")
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import rag  # noqa: E402  (Spiel-Layout)
from rag import vision_prompt  # noqa: E402

# Frueher fest auf "Mitarbeiterkarten" (Food Chain Magnate); main() setzt den
# Prompt mit Spielname und Sprache aus spiel.json.
PROMPT = vision_prompt()


def seite_aus_bildname(pfad):
    """Physische Seite aus dem von render.py vergebenen Namen, sonst None."""
    m = re.search(r"seite[_-]?(\d+)", os.path.basename(pfad), re.IGNORECASE)
    return int(m.group(1)) if m else None


def bestimme_seite(pfad, argv_seite=None, env_seite=None):
    """Physische Seite -- ausdrueckliche Angabe schlaegt den Dateinamen.

    Ohne beides ein harter Fehler: eine erfundene Seitenzahl ist genau der
    Defekt ("Fundstelle: Seite 75"), der hier behoben wird.
    """
    for wert in (argv_seite, env_seite):
        if wert not in (None, ""):
            s = int(wert)
            if s < 1:
                raise SystemExit(f"Seite muss >= 1 sein (physische PDF-Seite), nicht {s}.")
            return s
    s = seite_aus_bildname(pfad)
    if s is None:
        raise SystemExit(
            f"Seitenzahl aus '{os.path.basename(pfad)}' nicht ableitbar. "
            "Entweder von render.py rendern lassen (seite_6.png) oder die "
            "physische PDF-Seite mitgeben: python vision_ingest.py <bild> <seite>")
    return s


def frag_vision(img):
    with open(img, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    r = requests.post(f"{OLLAMA}/api/generate", json={
        "model": VMODEL, "prompt": PROMPT, "images": [b64], "stream": False,
    }, timeout=600)
    r.raise_for_status()
    return r.json()["response"].strip()


def split_karten(text):
    """Vision-Ausgabe in Einzel-Karten: Zeilen, die "Name: Wert" enthalten."""
    karten = []
    for ln in text.splitlines():
        ln = ln.strip().lstrip("-*0123456789. ").strip()
        if ":" in ln and len(ln) > 5:
            karten.append(ln)
    return karten


def lade_ohne_vision(pfad, quelle=None):
    """Bestehende Wissensbasis ohne die alten vision:-Chunks dieses Bildes (Idempotenz).

    quelle=None entfernt wie frueher alle vision:-Chunks.
    """
    entries = []
    if os.path.exists(pfad):
        with open(pfad, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                e = json.loads(line)
                q = str(e.get("quelle", ""))
                if not (q == quelle if quelle else q.startswith("vision:")):
                    entries.append(e)
    return entries


def eintrag(cid, seite, img, text):
    return {"id": cid, "seite": seite,
            "quelle": f"vision:{os.path.basename(img)}", "text": text}


def main(argv=None):
    global PROMPT
    argv, opt = rag.spiel_argumente(sys.argv[1:] if argv is None else argv)
    if not argv:
        raise SystemExit("Nutzung: python vision_ingest.py <bild.png> [seite] [--spiel NAME | --spiel-id ID]")
    img = argv[0]
    seite = bestimme_seite(img, argv[1] if len(argv) > 1 else None,
                           os.environ.get("SEITE"))
    know, felder = KNOW, {}
    if opt is not None:
        meta, know = rag.bereite_spiel_vor(opt)
        felder = rag.spiel_felder(meta)
        PROMPT = vision_prompt(meta["name"], meta["sprache"])

    karten = split_karten(frag_vision(img))

    entries = lade_ohne_vision(know, f"vision:{os.path.basename(img)}")
    maxid = max([e.get("id", 0) for e in entries], default=0)
    for c in karten:
        maxid += 1
        e = eintrag(maxid, seite, img, c)
        e.update(felder)
        entries.append(e)

    with open(rag.pruefe_schreibziel(know), "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    print(f"{len(karten)} Vision-Karten-Chunks eingefuegt "
          f"(ein Chunk pro Karte, Seite {seite}).")
    for c in karten[:3]:
        print("  z.B.:", c)


if __name__ == "__main__":
    main()
