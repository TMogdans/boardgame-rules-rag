#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Eingefrorene Soll-Ausgaben des Retrievals, erzeugt mit dem rag.py von ed36f99
(dem Stand VOR dem Mehr-Spiele-Umbau).

    python regression_referenz.py --erzeuge    # braucht git, schreibt regression_referenz.json
    python regression_referenz.py --erzeuge --ziel /tmp/ref.json [--gleichstand-umgekehrt]

test_regression.py vergleicht den heutigen alten Weg UND den neuen Index-Weg
gegen diese Datei. Vorher verglich der Test HEAD gegen HEAD: eine Aenderung an
der gemeinsamen Rangfolge-Zeile zog beide Seiten mit und blieb gruen (Mutation
K2 aus dem Review). Die Referenz haengt an keinem Code dieses Branches -- nur an
den Daten und Attrappen hier, und die sind mit eingefroren.

Zur Testzeit wird weder git noch ed36f99 gebraucht; nur diese Datei und die JSON.

Gleichstaende: ed36f99 rankte mit np.argsort(-sims) (quicksort, nicht stabil). Bei
exakt gleichem Score ist die Reihenfolge -- und an der k-Grenze die Auswahl --
dort plattformabhaengig (Linux/x86_64 lieferte in 487 von 1008 Faellen andere
Chunks gleichen Scores als macOS). test_regression vergleicht deshalb
gleichstandsbewusst: Scores je Platz, ausserhalb von Gleichstandsgruppen exakt
dieselben Treffer, in einer Gruppe, die die k-Grenze schneidet, nur die
Zugehoerigkeit zur Gruppe. Reranker- und eval-Faelle laufen mit der Hash-
Attrappe, bei der Gleichstaende nur zwischen identischen Duplikaten vorkommen --
ihre Ausgabe ist damit plattformunabhaengig (test_regression prueft das).
--gleichstand-umgekehrt erzeugt die Referenz mit einem ed36f99, dessen argsort
Gleichstaende umgekehrt aufloest: eine zweite "Plattform" zum Gegenmessen.
"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import importlib.util
from unittest import mock

import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
REFERENZ_COMMIT = "ed36f99"
JSON_PFAD = os.path.join(BASE, "regression_referenz.json")

# FCM-aehnliche Wissensbasis: Seiten wie im Golden Set, Duplikate, lange Texte
# (werden zerteilt), flavor/meta-Typen und ein Eintrag ohne typ. Die Vision-Chunks
# von Seite 6 stehen am ENDE, wie vision_ingest.py sie anhaengt -- die Datei ist
# also nicht nach Seiten sortiert, und ein Umsortieren faellt auf.
WISSEN = [
    {"id": 1, "seite": 1, "typ": "meta", "route": "text-roh", "text": "Food Chain Magnate Regelheft Inhaltsverzeichnis"},
    {"id": 2, "seite": 2, "typ": "flavor", "route": "text-roh",
     "text": "Gleicher Mist, doppelter Preis! Werbung fuer die beste Kette der Stadt."},
    {"id": 3, "seite": 5, "typ": "regel", "route": "table",
     "text": "Bei 2 Spielern werden die Reklametafeln 12, 15 und 16 entfernt. Bei 4 Spielern ist der Spielplan 4x4 gross. " * 6},
    {"id": 4, "seite": 10, "typ": "regel", "route": "text-roh", "text": "Die Reichweite zaehlt Strassenfelder. " * 12},
    {"id": 5, "seite": 11, "typ": "regel", "route": "text-roh",
     "text": "In Phase 4, der Essenszeit, wird Geld verdient. Eine Ware kostet 10 Dollar. Der CFO bringt 50 % Bonus. " * 5},
    {"id": 6, "seite": 11, "route": "text-roh", "text": "Eine Waitress bringt 3 Dollar Geld."},       # ohne typ
    {"id": 7, "seite": 14, "typ": "regel", "route": "table", "text": "Meilenstein First waitress played: 5 Dollar Geld."},
    {"id": 8, "seite": 14, "typ": "regel", "route": "table", "text": "Meilenstein First waitress played: 5 Dollar Geld."},
    {"id": 9, "seite": 15, "typ": "meta", "route": "text-roh", "text": "Impressum und Credits"},
    {"id": 10, "seite": 6, "typ": "regel", "quelle": "vision:seite_6.png", "text": "Truck Driver: Reichweite 3"},
    {"id": 11, "seite": 6, "typ": "regel", "quelle": "vision:seite_6.png", "text": "Campaign Manager: Kampagne maximale Dauer 3"},
    {"id": 12, "seite": 6, "typ": "regel", "quelle": "vision:seite_6.png", "text": "Truck Driver: Reichweite 3"},  # Duplikat
]

with open(os.path.join(BASE, "golden_set.example.json"), encoding="utf-8") as _f:
    GOLDEN = json.load(_f)
FRAGEN = [f["frage"] for f in GOLDEN["fragen"]] + ["Geld", "Reichweite", "Waitress Dollar", "xyz"]
RASTER = [(size, overlap, drop) for size, overlap in ((800, 150), (400, 150), (60, 10))
          for drop in ("", "flavor", "flavor,meta")]
KS = (1, 4, 8, None)          # None = alle Chunks
ACHSEN = ("geld", "reichweite", "kampagne", "dauer", "phase", "spieler", "waitress", "reklametafel", "dollar")


def achsen_embed(texte):
    """Ganzzahlige Themenachsen -> sehr viele exakte Gleichstaende."""
    out = []
    for t in texte:
        t = t.lower()
        v = [float(t.count(a)) for a in ACHSEN]
        out.append(v + [0.1 if any(v) else 1.0])
    return np.array(out, dtype=np.float32)


def hash_embed(texte):
    """Pseudozufaellig, gleiche Texte -> gleiche Vektoren (Gleichstand nur bei Duplikaten)."""
    return np.array([[b / 255.0 - 0.5 for b in hashlib.sha256(t.encode()).digest()[:16]] for t in texte],
                    dtype=np.float32)


EMBEDS = {"fake-achsen": achsen_embed, "fake-hash": hash_embed}


def fake_rerank_predict(paare):
    """Deterministischer 'Cross-Encoder': gemeinsame Woerter, dann Laenge."""
    out = []
    for frage, text in paare:
        gemeinsam = len(set(frage.lower().split()) & set(text.lower().split()))
        out.append(gemeinsam + 1.0 / (1 + len(text)))
    return np.array(out)


class _FakeReranker:
    predict = staticmethod(fake_rerank_predict)


def fake_answer(frage, hits):
    return "Antwort: " + " | ".join(h["text"][:40] for h, _ in hits)


def signatur(hits, chunks):
    """[position, seite, text-hash, score] -- die Position trennt auch identische Duplikate."""
    out = []
    for h, s in hits:
        pos = next(i for i, c in enumerate(chunks) if c is h)
        out.append([pos, h["seite"], hashlib.sha1(h["text"].encode()).hexdigest()[:16], float(s)])
    return out


def schluessel(embed_name, size, overlap, drop, k, frage):
    return f"{embed_name}|{size}/{overlap}|{drop or '-'}|k={k or 'alle'}|{frage}"


def kopfzeile(z):
    return z.startswith(("Config:", "Index:", "Spiel:", "===="))


def berechne(suche, eval_lauf):
    """Soll-Ausgaben rechnen.

    suche(embed_name, size, overlap, drop) -> (chunks, retrieve_fn(frage, k)) ;
    eval_lauf(embed_name, size, overlap, drop) -> Textausgabe von cmd_eval.
    """
    topk, rerank, evals = {}, {}, {}
    for embed_name in EMBEDS:
        for size, overlap, drop in RASTER:
            chunks, finde = suche(embed_name, size, overlap, drop, False)
            for k in KS:
                for frage in FRAGEN:
                    topk[schluessel(embed_name, size, overlap, drop, k, frage)] = \
                        signatur(finde(frage, k or len(chunks)), chunks)
    chunks, finde = suche("fake-hash", 400, 150, "flavor,meta", True)
    for frage in FRAGEN:
        rerank[frage] = signatur(finde(frage, 4), chunks)
    for embed_name in ("fake-hash",):
        for size, overlap, drop in (RASTER[1], RASTER[5], RASTER[6]):
            text = eval_lauf(embed_name, size, overlap, drop)
            evals[f"{embed_name}|{size}/{overlap}|{drop or '-'}"] = [
                z for z in text.splitlines() if z.strip() and not kopfzeile(z)]
    return {"topk": topk, "rerank": rerank, "eval": evals}


# ---------- Erzeugen mit ed36f99 ----------
class _NumpyGleichstandUmgekehrt:
    """numpy, aber argsort loest Gleichstaende absteigend nach Position auf."""

    def __getattr__(self, name):
        return getattr(np, name)

    @staticmethod
    def argsort(a, *args, **kw):
        return np.lexsort((-np.arange(len(a)), a))


def _lade_ed36f99(ziel):
    quelle = subprocess.run(["git", "-C", BASE, "show", f"{REFERENZ_COMMIT}:rag.py"],
                            check=True, capture_output=True, text=True).stdout
    pfad = os.path.join(ziel, "rag.py")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(quelle)
    spec = importlib.util.spec_from_file_location("rag_ed36f99", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def erzeuge(ziel=JSON_PFAD, umgekehrt=False):
    tmp = tempfile.mkdtemp()
    try:
        alt = _lade_ed36f99(tmp)
        if umgekehrt:
            alt.np = _NumpyGleichstandUmgekehrt()
        with open(os.path.join(tmp, "knowledge.jsonl"), "w", encoding="utf-8") as f:
            for e in WISSEN:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        with open(os.path.join(tmp, "golden_set.json"), "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in GOLDEN.items() if k != "spiel_id"}, f, ensure_ascii=False)

        def stellschrauben(embed_name, size, overlap, drop, rerank=False):
            return [mock.patch.object(alt, "embed", EMBEDS[embed_name]),
                    mock.patch.multiple(alt, CHUNK_SIZE=size, CHUNK_OVERLAP=overlap, RERANK=rerank, CANDIDATES=6,
                                        get_reranker=lambda: _FakeReranker, answer=fake_answer),
                    mock.patch.dict(os.environ, {"SOURCE": "knowledge", "DROP_TYPES": drop})]

        def suche(embed_name, size, overlap, drop, rerank):
            with contextlib.ExitStack() as st:
                for p in stellschrauben(embed_name, size, overlap, drop, rerank):
                    st.enter_context(p)
                chunks, embs = alt.build_index()

            def finde(frage, k):
                with contextlib.ExitStack() as st:
                    for p in stellschrauben(embed_name, size, overlap, drop, rerank):
                        st.enter_context(p)
                    return alt.retrieve(frage, chunks, embs, k=k)
            return chunks, finde

        def eval_lauf(embed_name, size, overlap, drop):
            puffer = io.StringIO()
            with contextlib.ExitStack() as st:
                for p in stellschrauben(embed_name, size, overlap, drop):
                    st.enter_context(p)
                st.enter_context(contextlib.redirect_stdout(puffer))
                alt.cmd_eval()
            return puffer.getvalue()

        daten = berechne(suche, eval_lauf)
        import platform
        daten["_erzeugt_mit"] = (f"rag.py aus {REFERENZ_COMMIT}, numpy {np.__version__}, Python "
                                 f"{sys.version.split()[0]}, {platform.system()}/{platform.machine()}"
                                 f"{', Gleichstand umgekehrt' if umgekehrt else ''}"
                                 " -- python regression_referenz.py --erzeuge")
        # Eine Zeile je Fall: lesbare Diffs, falls die Referenz je neu erzeugt wird.
        with open(ziel, "w", encoding="utf-8") as f:
            f.write("{\n")
            bloecke = sorted(daten)
            for bi, block in enumerate(bloecke):
                wert = daten[block]
                if isinstance(wert, dict):
                    f.write(f"{json.dumps(block)}: {{\n")
                    zeilen = [f"  {json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
                              for k, v in sorted(wert.items())]
                    f.write(",\n".join(zeilen) + "\n}")
                else:
                    f.write(f"{json.dumps(block)}: {json.dumps(wert, ensure_ascii=False)}")
                f.write(",\n" if bi < len(bloecke) - 1 else "\n")
            f.write("}\n")
        print(f"{len(daten['topk'])} Top-k-Faelle, {len(daten['rerank'])} Reranker-Faelle, "
              f"{len(daten['eval'])} eval-Laeufe -> {ziel}")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    if "--erzeuge" not in sys.argv:
        sys.exit(__doc__)
    ziel = sys.argv[sys.argv.index("--ziel") + 1] if "--ziel" in sys.argv else JSON_PFAD
    erzeuge(ziel, "--gleichstand-umgekehrt" in sys.argv)
