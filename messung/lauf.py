#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Messlauf: `rag.py eval` ueber Spiele mit Golden Set, dazu ein Antwortprotokoll.

    python messung/lauf.py AUSGABEVERZEICHNIS [--daten DATENVERZEICHNIS] [spiel_id ... | --alle]

Alle Stellschrauben bleiben Umgebungsvariablen wie beim Eval (LLM_MODEL, THINK,
PROMPT_VERSION, ENTSCHEIDUNG, HYBRID, TOP_K, CHUNK_SIZE, DROP_TYPES ...).

Schreibt ins Ausgabeverzeichnis (das der Aufrufer nennt, nie ins Repo):
  antworten.jsonl  je Frage: volle Antwort, abgerufene Seiten, Scores, Option des
                   Entscheidungsschritts, Laufzeit der Antwort (Sekunden)
  meta.json        vollstaendige Konfiguration des Laufs (Modell, Stellschrauben,
                   git-Commit von rag.py, Zeitstempel) -- ein Lauf ist damit auch
                   ohne die Konsolenausgabe (eval.txt) nachvollziehbar

Die Golden Sets lesen wir aus dem Datenverzeichnis (Default: DATA_DIR bzw. data/ des
Repos); es liegt ausserhalb des Repos. Der Lauf haengt sich nur an rag.answer,
rag.werte_fragen und rag.cmd_eval_spiel -- die Wertung selbst bleibt die von rag.py.
"""
import json
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import rag  # noqa: E402

# Umgebungsvariablen, die das Ergebnis beeinflussen koennen. Bewusst eine feste Liste:
# nie die ganze Umgebung protokollieren (Tokens!).
ENV_SCHLUESSEL = ("LLM_MODEL", "THINK", "PROMPT_VERSION", "ENTSCHEIDUNG", "HYBRID", "TOP_K", "RERANK",
                  "RRF_K", "CANDIDATES", "CHUNK_SIZE", "CHUNK_OVERLAP", "DROP_TYPES", "SOURCE",
                  "EMBED_MODEL", "RERANK_MODEL", "OLLAMA_URL")
# Wirksame Werte, wie rag.py sie nach dem Import haelt (Default eingerechnet).
RAG_KONFIG = ("OLLAMA", "EMBED_MODEL", "LLM_MODEL", "CHUNK_SIZE", "CHUNK_OVERLAP", "TOP_K", "THINK", "RERANK",
              "HYBRID", "RRF_K", "RERANK_MODEL", "CANDIDATES", "PROMPT_VERSION", "ENTSCHEIDUNG")


class MessFehler(Exception):
    pass


def git_stand(pfad):
    """(commit, geaendert) der Datei; (None, None), wenn sie nicht in einem git-Baum liegt."""
    verz = os.path.dirname(os.path.abspath(pfad))
    name = os.path.basename(pfad)
    try:
        c = subprocess.run(["git", "-C", verz, "log", "-n1", "--format=%H", "--", name],
                           capture_output=True, text=True, timeout=20)
        s = subprocess.run(["git", "-C", verz, "status", "--porcelain", "--", name],
                           capture_output=True, text=True, timeout=20)
        if c.returncode or s.returncode or not c.stdout.strip():
            return None, None
        return c.stdout.strip(), bool(s.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None, None


def baue_meta(args, data_dir, start):
    commit, geaendert = git_stand(rag.__file__)
    try:
        drop = sorted(rag.drop_fuer_index())
    except Exception:  # falsche DROP_TYPES sollen den Lauf nicht vor dem Eval-eigenen Fehler abbrechen
        drop = None
    return {
        "modell": rag.LLM_MODEL,
        "konfiguration": {k: getattr(rag, k, None) for k in RAG_KONFIG},
        "drop_types": drop,
        "entscheidung_an": bool(rag.entscheidung_an()),
        "env": {k: os.environ[k] for k in ENV_SCHLUESSEL if k in os.environ},
        "rag_commit": commit,
        "rag_geaendert": geaendert,
        "argumente": list(args),
        "daten": data_dir,
        "python": sys.version.split()[0],
        "start": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(start)),
        "ende": None,
        "antworten": None,
    }


def schreibe_meta(pfad, meta):
    tmp = pfad + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, pfad)


def fuehre_aus(ausgabe, args=("--alle",), data_dir=None, ueberschreiben=False, eval_fn=None, uhr=time.time):
    """Ein Messlauf. Rueckgabe: Anzahl protokollierter Antworten.

    eval_fn(args, data_dir=...) ist der Eval (Default rag.cmd_eval_spiele); der Test setzt
    eine Attrappe ein. Die Haken sitzen an rag.*, also greifen sie auch dort.
    """
    eval_fn = eval_fn or rag.cmd_eval_spiele
    os.makedirs(ausgabe, exist_ok=True)
    pfad_a = os.path.join(ausgabe, "antworten.jsonl")
    pfad_m = os.path.join(ausgabe, "meta.json")
    if not ueberschreiben and (os.path.exists(pfad_a) or os.path.exists(pfad_m)):
        raise MessFehler(f"{ausgabe} enthaelt schon einen Lauf -- anderes Verzeichnis nehmen "
                         f"(oder --ueberschreiben).")
    start = uhr()
    meta = baue_meta(args, data_dir, start)
    schreibe_meta(pfad_m, meta)   # gleich am Anfang: auch ein abgebrochener Lauf ist zuzuordnen
    akt = {"spiel": None, "fragen": {}, "n": 0}
    orig_spiel, orig_answer, orig_werte = rag.cmd_eval_spiel, rag.answer, rag.werte_fragen
    aus = open(pfad_a, "w", encoding="utf-8")

    def spiel(sid, *a, **k):
        akt["spiel"] = sid
        return orig_spiel(sid, *a, **k)

    def werte(fragen, suche):
        akt["fragen"] = {f["frage"]: f for f in fragen}
        return orig_werte(fragen, suche)

    def answer(frage, hits):
        t = time.perf_counter()
        ans = orig_answer(frage, hits)
        dt = time.perf_counter() - t
        f = akt["fragen"][frage]
        ent = getattr(rag, "LETZTER_ENTSCHEID", None)
        opt, probs = ent if ent else (None, None)
        aus.write(json.dumps({"spiel_id": akt["spiel"], "frage_id": f["id"], "frage": frage, "antwort": ans,
                              "abgerufen": [h["seite"] for h, _ in hits],
                              "scores": [round(float(s), 4) for _, s in hits],
                              "entscheid": opt, "probs": probs, "t_antwort": round(dt, 2)},
                             ensure_ascii=False) + "\n")
        aus.flush()
        akt["n"] += 1
        return ans

    rag.cmd_eval_spiel, rag.answer, rag.werte_fragen = spiel, answer, werte
    try:
        eval_fn(list(args), data_dir=data_dir)
    finally:
        rag.cmd_eval_spiel, rag.answer, rag.werte_fragen = orig_spiel, orig_answer, orig_werte
        aus.close()
        meta["ende"] = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(uhr()))
        meta["antworten"] = akt["n"]
        schreibe_meta(pfad_m, meta)
    return akt["n"]


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ueberschreiben = "--ueberschreiben" in argv
    argv = [a for a in argv if a != "--ueberschreiben"]
    data_dir = None
    if "--daten" in argv:
        i = argv.index("--daten")
        if i + 1 >= len(argv):
            print("--daten braucht ein Verzeichnis.", file=sys.stderr)
            return 2
        data_dir = argv[i + 1]
        del argv[i:i + 2]
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    ausgabe, ziele = argv[0], argv[1:] or ["--alle"]
    try:
        n = fuehre_aus(ausgabe, ziele, data_dir, ueberschreiben)
    except (MessFehler, rag.KonfigFehler) as e:
        print(f"Abbruch: {e}", file=sys.stderr)
        return 1
    print(f"\n{n} Antworten protokolliert in {os.path.join(ausgabe, 'antworten.jsonl')}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
