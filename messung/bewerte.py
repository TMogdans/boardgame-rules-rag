#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bewertet Messlaeufe: jede antworten.jsonl gegen das Golden Set, per judge.bewerte.

    python messung/bewerte.py [--golden VERZEICHNIS] [--modus anthropic] [--modell NAME] \\
        LAUF/antworten.jsonl [LAUF2/antworten.jsonl ...]

Ein Argument darf auch ein Laufverzeichnis sein (dann gilt LAUF/antworten.jsonl).
Schreibt urteile.jsonl neben jede antworten.jsonl: die Zeile des Laufs plus urteil,
begruendung (Rohtext des Bewerters), Token-Zahlen und das Flag "deterministisch"
(feste Verweigerungssaetze werden von judge.bewerte ohne Modellaufruf gewertet).

Golden Sets: <golden>/<spiel_id>/golden_set.json (Layout des Datenverzeichnisses)
oder <golden>/<spiel_id>.json. Default fuer --golden: DATA_DIR bzw. data/ des Repos.
Vor dem ersten Modellaufruf werden ALLE Fragen aufgeloest: eine unbekannte Frage
bricht den Lauf ab, bevor Geld ausgegeben ist.
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import judge  # noqa: E402


class BewerteFehler(Exception):
    pass


def lies_jsonl(pfad):
    with open(pfad, encoding="utf-8") as f:
        return [json.loads(z) for z in f if z.strip()]


def lade_fragen(golden_verz, spiel_id):
    """{frage_id: Frage} eines Spiels aus dem Golden-Set-Verzeichnis."""
    kandidaten = (os.path.join(golden_verz, spiel_id, "golden_set.json"),
                  os.path.join(golden_verz, spiel_id + ".json"))
    for pfad in kandidaten:
        if os.path.isfile(pfad):
            with open(pfad, encoding="utf-8") as f:
                gs = json.load(f)
            return {q["id"]: q for q in gs["fragen"]}
    raise BewerteFehler(f"Kein Golden Set fuer Spiel {spiel_id!r} unter {golden_verz} "
                        f"(gesucht: {spiel_id}/golden_set.json, {spiel_id}.json).")


def loese_fragen_auf(zeilen, golden_verz, quelle=""):
    """Golden-Set-Frage je Zeile; bricht bei unbekanntem Spiel oder unbekannter Frage ab."""
    cache, aufgeloest = {}, []
    for i, z in enumerate(zeilen, 1):
        sid = z["spiel_id"]
        if sid not in cache:
            cache[sid] = lade_fragen(golden_verz, sid)
        if z["frage_id"] not in cache[sid]:
            raise BewerteFehler(f"{quelle} Zeile {i}: Frage {z['frage_id']!r} ist nicht im Golden Set "
                                f"von {sid!r} -- Golden Set und Lauf passen nicht zusammen.")
        aufgeloest.append(cache[sid][z["frage_id"]])
    return aufgeloest


def bewerte_lauf(pfad_antworten, golden_verz, modus, modell, ausgabe=print, zeilen=None, fragen=None):
    """urteile.jsonl neben antworten.jsonl. Rueckgabe: Pfad."""
    zeilen = zeilen if zeilen is not None else lies_jsonl(pfad_antworten)
    fragen = fragen if fragen is not None else loese_fragen_auf(zeilen, golden_verz, pfad_antworten)
    ziel = os.path.join(os.path.dirname(os.path.abspath(pfad_antworten)), "urteile.jsonl")
    with open(ziel, "w", encoding="utf-8") as aus:
        for z, q in zip(zeilen, fragen):
            r = judge.bewerte(modus, modell, q, z["antwort"])
            aus.write(json.dumps({**z, "urteil": r["urteil"], "begruendung": r.get("rohtext"),
                                  "input_tokens": r.get("input_tokens"),
                                  "output_tokens": r.get("output_tokens"),
                                  "deterministisch": bool(r.get("deterministisch"))},
                                 ensure_ascii=False) + "\n")
            aus.flush()
            ausgabe(f"{z['spiel_id']} {z['frage_id']} {r['urteil']}")
    return ziel


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    opt = {"--golden": os.environ.get("DATA_DIR") or os.path.join(BASE, "data"),
           "--modus": "anthropic", "--modell": None}
    pfade = []
    while argv:
        a = argv.pop(0)
        if a in opt:
            if not argv:
                print(f"{a} braucht einen Wert.", file=sys.stderr)
                return 2
            opt[a] = argv.pop(0)
        else:
            pfade.append(a)
    if not pfade:
        print(__doc__, file=sys.stderr)
        return 2
    modell = opt["--modell"] or (judge.ANTHROPIC_DEFAULT if opt["--modus"] == "anthropic" else None)
    if modell is None:
        print("--modell fehlt (Ollama-Modi brauchen ein Modell).", file=sys.stderr)
        return 2
    pfade = [os.path.join(p, "antworten.jsonl") if os.path.isdir(p) else p for p in pfade]
    try:
        # erst alles aufloesen, dann bewerten: ein Fehler in Lauf 3 darf Lauf 1 nicht schon bezahlt haben
        geladen = []
        for p in pfade:
            zeilen = lies_jsonl(p)
            geladen.append((p, zeilen, loese_fragen_auf(zeilen, opt["--golden"], p)))
        for p, zeilen, fragen in geladen:
            print(f"== {p}", file=sys.stderr)
            print(bewerte_lauf(p, opt["--golden"], opt["--modus"], modell, zeilen=zeilen, fragen=fragen))
    except (BewerteFehler, judge.JudgeAbbruch, OSError, json.JSONDecodeError) as e:
        print(f"Abbruch: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
