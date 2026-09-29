#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Eingefrorene Ausgaben der Pipe von ed36f99 auf dem ALTEN Weg (ohne INDEX_PATH),
fuer 800 Werte von regelfrage.spiel plus 6 Nicht-Strings.

    python pipe_referenz.py --erzeuge      # braucht git, schreibt pipe_referenz.json

test_pipe_alt.py prueft, dass die heutige Pipe auf dem alten Weg byte-gleich
antwortet (Entscheidung Tobias: mit genau einem Spiel das Verhalten von ed36f99).
Vorlage: exp_c.py des dritten Kritikers (gleicher Zufallsstartwert, gleiche Werte).
Suche und LLM sind ersetzt (Attrappen unten) -- verglichen wird die Zuordnung und
alles, was die Pipe darum herum ausgibt (Meldung, Vorschlaege, Fusszeile).
"""
import asyncio
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
REFERENZ_COMMIT = "ed36f99"
JSON_PFAD = os.path.join(BASE, "pipe_referenz.json")
FRAGE = "Wie verdiene ich Geld?"
NICHT_STRINGS = [0, 5, True, [], {}, ["FCM"]]


def werte():
    """Die 800 spiel-Werte aus exp_c.py (Kritiker 3), deterministisch."""
    rnd = random.Random(7)
    basis = ["Food Chain Magnate", "Food Chain", "FCM"]
    ergebnis = set()
    fueller = ["", " bitte", " Regeln", " Regelheft", "das ", "äh ", " spiel", " game", ", danke", " von Splotter", "Spiel "]
    hoer = ["Food Chain Magnet", "Foodchain Magnet", "Fut Chain Magnate", "Food Shane Magnate", "Food Chain Magnaten",
            "Foot Chain Magnate", "Food Change Magnate", "Fud Tschein Magnet", "Food Chain Magnat", "Foodchainmagnate",
            "F C M", "fcm!", "FCM?", "Ef Ce Em", "Food", "Chain", "Magnate", "Food Chain Magnate 2",
            "Food Chain Magnate: Ketchup", "Brass", "Azul", "Root", "Terraforming Mars", "Foodsharing Magnet", "Fujian",
            "Fuji", "", " ", "???", "Ö", "ß", "Straße", "Food\u00a0Chain\u00a0Magnate", "FOOD CHAIN MAGNATE", "food_chain_magnate",
            "food-chain-magnate", "Food Chain Magnate Magnate", "Magnate Chain Food",
            "Food Chain Magnate Regeln bitte danke", "Chain Magnate", "Food Magnate"]
    for b in basis + hoer:
        for f in fueller:
            ergebnis.add(f + b if f.endswith(" ") else b + f)
    alph = "abcdefghijklmnopqrstuvwxyzäöü "
    while len(ergebnis) < 800:
        s = list(rnd.choice(basis + hoer[:12]))
        for _ in range(rnd.randint(1, 4)):
            op = rnd.random()
            i = rnd.randrange(len(s) + 1) if s else 0
            if op < .33 and s:
                s[min(i, len(s) - 1)] = rnd.choice(alph)
            elif op < .66:
                s.insert(i, rnd.choice(alph))
            elif s:
                del s[min(i, len(s) - 1)]
        ergebnis.add("".join(s))
    return sorted(ergebnis)


def pipe_mit_attrappen(modul, rag_dir):
    p = modul.Pipe()
    p.valves = modul.Pipe.Valves(RAG_DIR=rag_dir)
    p._suche = lambda frage, v: ([{"role": "system", "content": "S"}, {"role": "user", "content": frage}],
                                 [({"seite": 3}, 0.5)])

    async def stream(n):
        yield "ANTWORT(" + n[-1]["content"] + ")"
    p._stream = stream
    return p


def antworten(p, alle):
    async def lauf(body):
        return "".join([s async for s in p.pipe(body)])
    return [asyncio.run(lauf({"messages": [{"role": "user", "content": FRAGE}], "regelfrage": {"spiel": w}}))
            for w in alle]


def erzeuge():
    tmp = tempfile.mkdtemp()
    try:
        for datei in ("openwebui_pipe.py", "rag.py"):
            quelle = subprocess.run(["git", "-C", BASE, "show", f"{REFERENZ_COMMIT}:{datei}"],
                                    check=True, capture_output=True, text=True).stdout
            with open(os.path.join(tmp, datei), "w", encoding="utf-8") as f:
                f.write(quelle)
        spec = importlib.util.spec_from_file_location("pipe_ed36f99", os.path.join(tmp, "openwebui_pipe.py"))
        alt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(alt)
        alle = werte() + NICHT_STRINGS
        daten = {"_erzeugt_mit": f"openwebui_pipe.py aus {REFERENZ_COMMIT} -- python pipe_referenz.py --erzeuge",
                 "faelle": [[w, a] for w, a in zip(alle, antworten(pipe_mit_attrappen(alt, tmp), alle))]}
        with open(JSON_PFAD, "w", encoding="utf-8") as f:
            f.write('{"_erzeugt_mit": ' + json.dumps(daten["_erzeugt_mit"]) + ',\n"faelle": [\n')
            f.write(",\n".join(json.dumps(x, ensure_ascii=False) for x in daten["faelle"]))
            f.write("\n]}\n")
        treffer = sum(1 for _, a in daten["faelle"] if a.startswith("ANTWORT"))
        print(f"{len(alle)} Faelle ({treffer} Treffer) -> {JSON_PFAD}")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    if "--erzeuge" not in sys.argv:
        sys.exit(__doc__)
    erzeuge()
