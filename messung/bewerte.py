#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bewertet Messlaeufe: jede antworten.jsonl gegen das Golden Set, per judge.bewerte.

    python messung/bewerte.py [--golden VERZEICHNIS] [--golden-datei NAME] [--daten VERZEICHNIS] \\
        [--modus anthropic] [--modell NAME] LAUF/antworten.jsonl [LAUF2/antworten.jsonl ...]

Ein Argument darf auch ein Laufverzeichnis sein (dann gilt LAUF/antworten.jsonl).
Schreibt urteile.jsonl neben jede antworten.jsonl: die Zeile des Laufs plus urteil,
begruendung (Rohtext des Bewerters), Token-Zahlen und das Flag "deterministisch"
(feste Verweigerungssaetze werden von judge.bewerte ohne Modellaufruf gewertet).

Golden Sets: <golden>/<spiel_id>/golden_set.json (Layout des Datenverzeichnisses)
oder <golden>/<spiel_id>.json. Default fuer --golden: DATA_DIR bzw. data/ des Repos.
Mehr-Buecher-Bestaende: die Buecherdeklaration (<daten>/<spiel_id>/spiel.json) braucht der Judge,
um ihre festen Saetze deterministisch zu werten. --daten VERZEICHNIS nennt das Datenverzeichnis
(Default: --golden). Eine flache Golden-Kopie (<golden>/<spiel_id>.json) bringt keine spiel.json
mit -- dann --daten auf das echte Datenverzeichnis setzen; fehlt die Deklaration und sieht eine
Antwort wie so ein Satz aus, warnt der Lauf einmal auf stderr.
--golden-datei NAME waehlt eine andere Datei im Spielordner (<golden>/<spiel_id>/NAME, z. B.
golden_praxis.json). Ohne die Option gilt die Datei, die meta.json des Laufs festhielt
(GOLDEN_DATEI beim Lauf), sonst golden_set.json -- Urteile laufen so gegen dieselbe Datei
wie die Messung. Ketten: die Zwischenantworten aus "verlauf" gehen nicht an den Bewerter.
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
import rag  # noqa: E402


class BewerteFehler(Exception):
    pass


def lies_jsonl(pfad):
    with open(pfad, encoding="utf-8") as f:
        return [json.loads(z) for z in f if z.strip()]


STANDARD_DATEI = "golden_set.json"


def golden_datei_des_laufs(pfad_antworten):
    """Golden-Set-Datei, mit der der Lauf gemessen wurde (meta.json), sonst der Standard."""
    meta = os.path.join(os.path.dirname(os.path.abspath(pfad_antworten)), "meta.json")
    try:
        with open(meta, encoding="utf-8") as f:
            return json.load(f).get("golden_datei") or STANDARD_DATEI
    except (OSError, ValueError, AttributeError):
        return STANDARD_DATEI


def lade_fragen(golden_verz, spiel_id, datei=STANDARD_DATEI):
    """{frage_id: Frage} eines Spiels aus dem Golden-Set-Verzeichnis."""
    kandidaten = [os.path.join(golden_verz, spiel_id, datei)]
    if datei == STANDARD_DATEI:
        kandidaten.append(os.path.join(golden_verz, spiel_id + ".json"))
    for pfad in kandidaten:
        if os.path.isfile(pfad):
            with open(pfad, encoding="utf-8") as f:
                gs = json.load(f)
            return {q["id"]: q for q in gs["fragen"]}
    raise BewerteFehler(f"Kein Golden Set fuer Spiel {spiel_id!r} unter {golden_verz} "
                        f"(gesucht: {', '.join(os.path.relpath(k, golden_verz) for k in kandidaten)}).")


def loese_fragen_auf(zeilen, golden_verz, quelle="", datei=STANDARD_DATEI):
    """Golden-Set-Frage je Zeile; bricht bei unbekanntem Spiel oder unbekannter Frage ab."""
    cache, aufgeloest = {}, []
    for i, z in enumerate(zeilen, 1):
        sid = z["spiel_id"]
        if sid not in cache:
            cache[sid] = lade_fragen(golden_verz, sid, datei)
        if z["frage_id"] not in cache[sid]:
            raise BewerteFehler(f"{quelle} Zeile {i}: Frage {z['frage_id']!r} ist nicht im Golden Set "
                                f"von {sid!r} -- Golden Set und Lauf passen nicht zusammen.")
        aufgeloest.append(cache[sid][z["frage_id"]])
    return aufgeloest


def bewerte_lauf(pfad_antworten, golden_verz, modus, modell, ausgabe=print, zeilen=None, fragen=None,
                 datei=None, daten=None):
    """urteile.jsonl neben antworten.jsonl. Rueckgabe: Pfad.
    daten: Datenverzeichnis mit <spiel_id>/spiel.json (Buecherdeklaration), Default golden_verz."""
    zeilen = zeilen if zeilen is not None else lies_jsonl(pfad_antworten)
    datei = datei or golden_datei_des_laufs(pfad_antworten)
    fragen = fragen if fragen is not None else loese_fragen_auf(zeilen, golden_verz, pfad_antworten, datei)
    ziel = os.path.join(os.path.dirname(os.path.abspath(pfad_antworten)), "urteile.jsonl")
    # Buecherdeklaration je Bestand ueber die spiel_id (REQ-MB-6, F9a-1); Altbestand: keine
    buecher = {sid: rag.buecher_fuer_judge(sid, daten or golden_verz) for sid in {z["spiel_id"] for z in zeilen}}
    verdacht = []
    with open(ziel, "w", encoding="utf-8") as aus:
        for z, q in zip(zeilen, fragen):
            if buecher[z["spiel_id"]]:          # Mehr-Buecher-Bestand
                r = judge.bewerte(modus, modell, q, z["antwort"], buecher=buecher[z["spiel_id"]])
            else:                               # Altbestand: Aufruf wie vor der Spec
                if getattr(judge, "sieht_nach_buchsatz_aus", lambda _: False)(z["antwort"]):
                    verdacht.append(z["spiel_id"])
                r = judge.bewerte(modus, modell, q, z["antwort"])
            aus.write(json.dumps({**z, "typ": q.get("typ"), "urteil": r["urteil"], "begruendung": r.get("rohtext"),
                                  "input_tokens": r.get("input_tokens"),
                                  "output_tokens": r.get("output_tokens"),
                                  "deterministisch": bool(r.get("deterministisch"))},
                                 ensure_ascii=False) + "\n")
            aus.flush()
            ausgabe(f"{z['spiel_id']} {z['frage_id']} {r['urteil']}")
    if verdacht:                            # einmal je Lauf, nur stderr (Urteile unveraendert)
        judge.warne_ohne_deklaration(verdacht)
    return ziel


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    opt = {"--golden": os.environ.get("DATA_DIR") or os.path.join(BASE, "data"),
           "--modus": "anthropic", "--modell": None, "--golden-datei": None, "--daten": None}
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
            datei = opt["--golden-datei"] or golden_datei_des_laufs(p)
            geladen.append((p, zeilen, datei, loese_fragen_auf(zeilen, opt["--golden"], p, datei)))
        for p, zeilen, datei, fragen in geladen:
            print(f"== {p}  (Golden Set: {datei})", file=sys.stderr)
            print(bewerte_lauf(p, opt["--golden"], opt["--modus"], modell, zeilen=zeilen, fragen=fragen,
                               datei=datei, daten=opt["--daten"]))
    except (BewerteFehler, judge.JudgeAbbruch, OSError, json.JSONDecodeError) as e:
        print(f"Abbruch: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
