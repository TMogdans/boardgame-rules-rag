#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Retrieval messen, ohne Antwortmodell -- zuerst hier, dann erst das LLM.

    python messung/retrieval.py trefferquote [--daten VERZEICHNIS]
    python messung/retrieval.py verzeichnis --aus AUSGABE.jsonl [--daten VERZEICHNIS] [--schwelle 0.5]

trefferquote  je Spiel mit Golden Set: bei wie vielen beantwortbaren Fragen liegt mindestens eine
              erwartete Seite im Top-k? Fragen mit erwartet_verweigerung oder ohne "seiten" zaehlen
              nicht (sie haben keine erwartete Fundstelle). Stellschrauben per Umgebung wie im Eval
              (HYBRID, TOP_K, RERANK, CHUNK_SIZE, DROP_TYPES ...); die Konfiguration steht in der
              ersten Zeile der Ausgabe.
verzeichnis   Anteil der Top-k-Treffer, die von Vision-Seiten stammen bzw. wie ein Inhaltsverzeichnis
              aussehen (Zeilen, die auf eine Seitenzahl enden). Je Treffer eine Zeile in AUSGABE.jsonl
              (Seite, Typ, Flags, Anteile -- ohne Text aus dem Regelheft).

Der Index wird vorher auf Stand gebracht wie beim Eval. Die Daten liegen im Datenverzeichnis
(Default: DATA_DIR bzw. data/ des Repos), nie im Repo.
"""
import collections
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import rag  # noqa: E402

# Verzeichnis-artig: Zeile endet auf eine Seitenzahl (mit Punkten/Leerraum davor).
VZ = re.compile(r"(\.{3,}|…|\s)\s*\d{1,3}\s*$")


def spiele_mit_golden_set(data_dir=None):
    return [s for s in rag.liste_spiele(data_dir)
            if os.path.exists(os.path.join(rag.spiel_verzeichnis(s, data_dir), "golden_set.json"))]


def _oeffne(data_dir):
    """Index auf Stand bringen (wie der Eval) und oeffnen; Rueckgabe: (Spiele, Verbindung)."""
    ids = spiele_mit_golden_set(data_dir)
    if not ids:
        raise rag.KonfigFehler("Kein Spiel mit golden_set.json im Datenverzeichnis.")
    rag.aktualisiere_index(ids, data_dir=data_dir, ausgabe=lambda *_: None)
    return ids, rag.oeffne_index()


def trefferquote(data_dir=None, ausgabe=print):
    """{"je_spiel": {sid: (treffer, n)}, "gesamt": (treffer, n), "verfehlt": ["sid/id", ...]}."""
    ids, con = _oeffne(data_dir)
    je_spiel, verfehlt = {}, []
    try:
        for sid in ids:
            gs = rag.lade_golden_set(sid, data_dir)
            chunks, embs = rag.lade_spiel(con, sid, rag.drop_fuer_index())
            g = n = 0
            for f in gs["fragen"]:
                if f.get("erwartet_verweigerung") or not f.get("seiten"):
                    continue
                hits = rag.retrieve(f["frage"], chunks, embs, spiel_id=sid, index=con)
                ok = bool({h["seite"] for h, _ in hits} & set(f["seiten"]))
                g += ok
                n += 1
                if not ok:
                    verfehlt.append(f"{sid}/{f['id']}")
            je_spiel[sid] = (g, n)
            ausgabe(f"  {sid:22} {g}/{n}")
    finally:
        con.close()
    gesamt = (sum(g for g, _ in je_spiel.values()), sum(n for _, n in je_spiel.values()))
    ausgabe(f"GESAMT {gesamt[0]}/{gesamt[1]}  verfehlt: {verfehlt}")
    return {"je_spiel": je_spiel, "gesamt": gesamt, "verfehlt": verfehlt}


def verzeichnis_anteil(pfad_aus, data_dir=None, schwelle=0.5, ausgabe=print):
    """Je Treffer eine jsonl-Zeile; Rueckgabe: {sid: {"treffer", "vision", "verzeichnis"}}."""
    ids, con = _oeffne(data_dir)
    summe = {}
    try:
        with open(pfad_aus, "w", encoding="utf-8") as aus:
            for sid in ids:
                roh = rag.lies_jsonl(rag.knowledge_pfad(sid, data_dir))
                route = collections.defaultdict(collections.Counter)
                for c in roh:
                    route[c["seite"]][c.get("route", "?")] += 1
                vision_seiten = {s for s, r in route.items() if r.get("vision")}
                gs = rag.lade_golden_set(sid, data_dir)
                chunks, embs = rag.lade_spiel(con, sid, rag.drop_fuer_index())
                s = summe[sid] = {"treffer": 0, "vision": 0, "verzeichnis": 0}
                for f in gs["fragen"]:
                    for h, score in rag.retrieve(f["frage"], chunks, embs, spiel_id=sid, index=con):
                        zeilen = [z for z in h["text"].splitlines() if z.strip()]
                        vz = sum(bool(VZ.search(z)) for z in zeilen)
                        anteil = round(vz / len(zeilen), 2) if zeilen else 0
                        ist_vision = h["seite"] in vision_seiten
                        s["treffer"] += 1
                        s["vision"] += ist_vision
                        s["verzeichnis"] += anteil >= schwelle
                        aus.write(json.dumps({"spiel_id": sid, "frage_id": f["id"], "seite": h["seite"],
                                              "typ": h.get("typ"), "vision_seite": ist_vision,
                                              "vz_anteil": anteil, "laenge": len(h["text"]),
                                              "erwartet": f.get("seiten") or []}) + "\n")
    finally:
        con.close()
    for sid, s in summe.items():
        n = s["treffer"] or 1
        ausgabe(f"  {sid:22} Treffer {s['treffer']:>4}  Vision {s['vision']:>4} ({s['vision'] / n:.0%})  "
                f"Verzeichnis-artig {s['verzeichnis']:>4} ({s['verzeichnis'] / n:.0%}, Schwelle {schwelle})")
    return summe


def _konfig():
    return (f"TOP_K={rag.TOP_K} HYBRID={rag.HYBRID} RERANK={rag.RERANK} CHUNK_SIZE={rag.CHUNK_SIZE} "
            f"CHUNK_OVERLAP={rag.CHUNK_OVERLAP} EMBED_MODEL={rag.EMBED_MODEL} "
            f"DROP_TYPES={sorted(rag.drop_fuer_index())}")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("trefferquote", "verzeichnis"):
        print(__doc__, file=sys.stderr)
        return 2
    befehl, opt, i = argv[0], {"--daten": None, "--aus": None, "--schwelle": "0.5"}, 1
    while i < len(argv):
        if argv[i] not in opt or i + 1 >= len(argv):
            print(f"Unbekanntes oder unvollstaendiges Argument: {argv[i]}", file=sys.stderr)
            return 2
        opt[argv[i]] = argv[i + 1]
        i += 2
    try:
        print(_konfig())
        if befehl == "trefferquote":
            trefferquote(opt["--daten"])
        else:
            if not opt["--aus"]:
                print("verzeichnis braucht --aus AUSGABE.jsonl.", file=sys.stderr)
                return 2
            verzeichnis_anteil(opt["--aus"], opt["--daten"], float(opt["--schwelle"]))
    except rag.KonfigFehler as e:
        print(f"Abbruch: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
