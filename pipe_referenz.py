#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Eingefrorene Ausgaben der Pipe von ed36f99 auf dem ALTEN Weg (ohne INDEX_PATH),
fuer 800 Werte von regelfrage.spiel plus 6 Nicht-Strings.

    python pipe_referenz.py --erzeuge      # braucht git, schreibt pipe_referenz.json
                                           # und pipe_verlauf_referenz.json

Zweiter Teil (Kritiker 4, c_diff.py): 600 zufaellige Verlaeufe -- Fusszeilen und
Fehlerzeilen im Verlauf, Listen-Inhalte, System-Nachrichten, task, sprache, kaputte
regelfrage -- durch den ECHTEN alten Weg (Suche ueber knowledge.jsonl mit Duplikat-
Chunks, Embedding- und LLM-Attrappen). Verglichen werden Ausgabe und die Nutzlast an
das LLM (als SHA-256). Das Soll stammt aus ed36f99 mit stabil sortierendem
np.argsort -- so ist die Regression C definiert (gleich bis auf die Reihenfolge
innerhalb exakter Gleichstaende, die ed36f99 nicht festlegte).

test_pipe_alt.py prueft, dass die heutige Pipe auf dem alten Weg byte-gleich
antwortet (Entscheidung Tobias: mit genau einem Spiel das Verhalten von ed36f99).
Vorlage: exp_c.py des dritten Kritikers (gleicher Zufallsstartwert, gleiche Werte).
Suche und LLM sind ersetzt (Attrappen unten) -- verglichen wird die Zuordnung und
alles, was die Pipe darum herum ausgibt (Meldung, Vorschlaege, Fusszeile).
"""
import asyncio
import hashlib
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
VERLAUF_PFAD = os.path.join(BASE, "pipe_verlauf_referenz.json")
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


# ---------- Verlaeufe (c_diff.py) ----------
ACHSEN = ("geld", "kette", "werbung", "rest")


def fake_vektor(text):
    t = text.lower()
    v = [float(t.count(a)) for a in ACHSEN[:-1]]
    return v + [0.1 if any(v) else 1.0]


class _Antwort:
    def __init__(self, daten):
        self._d = daten

    def raise_for_status(self):
        pass

    def json(self):
        return self._d


def fake_post(url, json=None, timeout=None):
    if url.endswith("/api/embed"):
        return _Antwort({"embeddings": [fake_vektor(t) for t in json["input"]]})
    raise AssertionError(f"unerwartete URL {url}")


def ndjson(*teile):
    return "".join(json.dumps({"message": {"content": t}, "done": False}) + "\n" for t in teile) + \
        json.dumps({"done": True}) + "\n"


def wissen_zeilen():
    """knowledge.jsonl wie c_diff.py --ties: 40 Zufallschunks + 30 Duplikate (Gleichstaende)."""
    rnd = random.Random(3)
    woerter = "Geld Kette Bank Phase Haus Werbung Karte Runde Spieler Markt Burger Pizza Limo Bier Zug Aktion".split()
    zeilen = []
    for i in range(40):
        t = " ".join(rnd.choice(woerter) for _ in range(rnd.randint(3, 12)))
        typ = rnd.choice(["regel"] * 6 + ["flavor", "meta"])
        zeilen.append({"id": i, "seite": 1 + i // 2, "typ": typ, "text": t})
    for i in range(40, 70):
        zeilen.append({"id": i, "seite": 100 + i, "typ": "regel", "text": "Geld Geld Kette"})
    return zeilen


FUSS = ["\n\n---\n*Abgerufen: S. 3 (0.512), S. 4 (0.300)*", "---\n*Abgerufen: S. 1 (0.1)*",
        "\n\n---\n*Quelle: Food Chain Magnate, Seite 3 -- Abgerufen: S. 3 (0.5)*",
        "\n\n**Fehler in der RAG-Pipe:** RuntimeError: x", "", "", "\n\n---\n*Abgerufen: S. 3*\nnachgeschoben", "  \n"]
SPIELE_RF = [None, None, "Food Chain Magnate", "FCM", "fcm", "Food Chain", "Food Chain Magnet", "Azul", "", " ",
             "Foodchain", "Brass", "Food Chain Magnate bitte", "F.C.M.", "Fut Schein", "Spiel: Azul", "Magnate", 7, None,
             "Wie bitte"]
FRAGEN_V = ["Wie verdiene ich Geld?", "Spiel: Azul", "Spiel: Azul: wer beginnt?", "Wechsel zu FCM",
            "Zu welchem Spiel ist die Frage?", "Azul", "", "   ", "Und zu zweit?", "Geld Kette",
            "Was kostet ein Haus?\n\nUnd die Bank?", "Spiel FCM", "Heat?"]


def verlauf_faelle():
    """600 Anfragen wie c_diff.py (Startwert 20260929): (body, task?)."""
    r = random.Random(20260929)

    def inhalt(t):
        if r.random() < 0.2:
            return [{"type": "text", "text": t}, {"type": "image_url", "image_url": {"url": "data:x"}}]
        return t
    faelle = []
    for _ in range(600):
        msgs = []
        if r.random() < 0.3:
            msgs.append({"role": "system", "content": "Sei nett."})
        for _ in range(r.randint(0, 4)):
            msgs.append({"role": "user", "content": inhalt(r.choice(FRAGEN_V))})
            msgs.append({"role": "assistant", "content": inhalt(
                "Antwort " + r.choice(["A", "B", "Zu welchem Spiel ist die Frage? X"]) + r.choice(FUSS))})
        if r.random() < 0.95:
            msgs.append({"role": "user", "content": inhalt(r.choice(FRAGEN_V))})
        b = {"messages": msgs}
        sp = r.choice(SPIELE_RF)
        if sp is not None or r.random() < 0.3:
            b["regelfrage"] = {"spiel": sp}
            if r.random() < 0.5:
                b["regelfrage"]["sprache"] = r.choice([True, False])
        elif r.random() < 0.1:
            b["regelfrage"] = r.choice(["kaputt", None, {"sprache": True}])
        faelle.append((b, r.random() < 0.05))
    return faelle


def lauf_verlaeufe(modul, rag_dir, wissen_pfad, faelle):
    """[(Ausgabe, SHA-256 der LLM-Nutzlast)] fuer den alten Weg einer Pipe-Version."""
    import httpx
    from unittest import mock
    bekam = []

    def handler(req):
        bekam.append(json.loads(req.content))
        return httpx.Response(200, text=ndjson("Ant", "wort"))
    echt = httpx.AsyncClient
    p = modul.Pipe()
    p.valves = modul.Pipe.Valves(RAG_DIR=rag_dir, KNOWLEDGE_PATH=wissen_pfad, OLLAMA_URL="http://stub")
    erg = []
    with mock.patch("requests.post", side_effect=fake_post), \
         mock.patch.object(modul.httpx, "AsyncClient", lambda **kw: echt(transport=httpx.MockTransport(handler), **kw)):
        for b, task in faelle:
            async def go():
                return "".join([s async for s in p.pipe(json.loads(json.dumps(b)),
                                                         __task__="title_generation" if task else None)])
            bekam.clear()
            aus = asyncio.run(go())
            last = hashlib.sha256(json.dumps(bekam, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            erg.append([aus, last])
    return erg


def erzeuge():
    tmp = tempfile.mkdtemp()
    try:
        for datei in ("openwebui_pipe.py", "rag.py"):
            quelle = subprocess.run(["git", "-C", BASE, "show", f"{REFERENZ_COMMIT}:{datei}"],
                                    check=True, capture_output=True, text=True).stdout
            with open(os.path.join(tmp, datei), "w", encoding="utf-8") as f:
                f.write(quelle)
        # C ist definiert gegen ed36f99 mit stabiler Sortierung
        pfad = os.path.join(tmp, "rag.py")
        with open(pfad, encoding="utf-8") as f:
            quelle = f.read()
        assert quelle.count("np.argsort(-sims)") == 2
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(quelle.replace("np.argsort(-sims)", 'np.argsort(-sims, kind="stable")'))
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
        wissen = os.path.join(tmp, "knowledge.jsonl")
        with open(wissen, "w", encoding="utf-8") as f:
            for z in wissen_zeilen():
                f.write(json.dumps(z, ensure_ascii=False) + "\n")
        erg = lauf_verlaeufe(alt, tmp, wissen, verlauf_faelle())
        with open(VERLAUF_PFAD, "w", encoding="utf-8") as f:
            f.write('{"_erzeugt_mit": ' + json.dumps(f"openwebui_pipe.py + rag.py (np.argsort stabil) aus "
                                                    f"{REFERENZ_COMMIT} -- python pipe_referenz.py --erzeuge")
                    + ',\n"faelle": [\n' + ",\n".join(json.dumps(x, ensure_ascii=False) for x in erg) + "\n]}\n")
        print(f"{len(erg)} Verlaeufe -> {VERLAUF_PFAD}")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    if "--erzeuge" not in sys.argv:
        sys.exit(__doc__)
    erzeuge()
