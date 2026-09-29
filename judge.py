#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bewertungsmodell (Judge) fuer RAG-Antworten -- mit Eichlauf.

Ein Modell wertet eine Antwort gegen eine Golden-Set-Frage in vier Klassen:
richtig / teilweise / falsch / unsicher. Bevor man dem Urteil traut, wird der
Judge an einer Eichmenge mit bekannten Labels gemessen:

    python judge.py eichen --eichmenge eich.jsonl --golden-dir golden/ \\
        --modus logprob --modell gemma3:12b-it-qat

Modi:
  logprob    Ollama, ein Token (A-D), Wahrscheinlichkeiten aus top_logprobs
  frei       Ollama, Freitext mit Begruendung, letzte Zeile "URTEIL: <klasse>"
  anthropic  Claude ueber die Messages-API (Key aus ~/.config/anthropic/api_key)

Die Seitenangabe prueft der Judge NICHT -- das macht Code deterministisch.
Umgebungsvariable: OLLAMA_URL (wie rag.py).
"""
import argparse, json, math, os, re, statistics, sys, time
from collections import defaultdict

import requests

OLLAMA = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_KEY_DATEI = os.path.expanduser("~/.config/anthropic/api_key")
ANTHROPIC_DEFAULT = "claude-haiku-4-5-20251001"
OLLAMA_DEFAULT = os.environ.get("JUDGE_MODELL", "qwen3:14b")

KLASSEN = ("richtig", "teilweise", "falsch", "unsicher")
UNPARSEBAR = "unparsebar"
BUCHSTABEN = {"A": "richtig", "B": "teilweise", "C": "falsch", "D": "unsicher"}
BINS = ((0.0, 0.5, "<0.5"), (0.5, 0.7, "0.5-0.7"), (0.7, 0.9, "0.7-0.9"),
        (0.9, 0.97, "0.9-0.97"), (0.97, 1.0001, ">0.97"))
SCHWELLEN = (0.7, 0.8, 0.9, 0.95)


class JudgeAbbruch(Exception):
    """Lauf kann nicht sinnvoll weitergehen (fehlende logprobs, HTTP-Fehler, ...)."""


class ModusNichtVerfuegbar(JudgeAbbruch):
    pass


# ---------- Prompt ----------
KLASSEN_TEXT = """\
Klassen:
- richtig: inhaltlich korrekt und vollständig genug für den Spieltisch (Umformulierung, andere Sprache für Spielbegriffe, Zahlwort statt Ziffer ok). Ist laut Golden Set Verweigern richtig (erwartet_verweigerung: true), ist eine ehrliche Aussage „steht nicht im Heft“ richtig.
- teilweise: korrekt, lässt aber einen für die Entscheidung wesentlichen Teil weg (z. B. Ausnahme), ohne Falsches zu behaupten.
- falsch: enthält eine falsche Regelaussage (auch neben richtigen Teilen) oder erfindet bei einer Leerstelle eine Regel/Zahl. Vorsichtig formuliert, aber inhaltlich falsch = falsch.
- unsicher: sagt ehrlich, dass es die Antwort nicht sicher weiß/gefunden hat, ohne Falsches zu behaupten."""

PROMPT_KOPF = """\
Du bist Prüfer für ein Brettspiel-Regel-Assistenzsystem. Du bewertest eine Antwort des Systems gegen die Musterlösung aus dem Golden Set. Die Seitenangabe prüfst du nicht.

""" + KLASSEN_TEXT + """

Frage: {frage}
Erwartet (Musterlösung): {erwartet}
Beleg aus dem Regelheft: {beleg}
Verweigern ist laut Golden Set die richtige Antwort (erwartet_verweigerung): {verweigerung}

Antwort des Systems:
\"\"\"
{antwort}
\"\"\"
"""

PROMPT_ENDE_LOGPROB = """
Wie ist die Antwort zu bewerten?
A) richtig B) teilweise C) falsch D) unsicher — antworte nur mit dem Buchstaben"""

PROMPT_ENDE_FREI = """
Begründe dein Urteil kurz (höchstens fünf Sätze) und schreibe als letzte Zeile genau:
URTEIL: <klasse>
wobei <klasse> eines von richtig, teilweise, falsch, unsicher ist."""


def baue_prompt(frage, antwort, modus):
    """Judge-Prompt. Eingabe: Frage-Dict (frage, erwartet, beleg, erwartet_verweigerung)."""
    kopf = PROMPT_KOPF.format(
        frage=frage.get("frage", ""),
        erwartet=frage.get("erwartet", ""),
        beleg=frage.get("beleg") or "(keiner angegeben)",
        verweigerung="ja" if frage.get("erwartet_verweigerung") else "nein",
        antwort=antwort,
    )
    return kopf + (PROMPT_ENDE_LOGPROB if modus == "logprob" else PROMPT_ENDE_FREI)


# ---------- Auswertung der Modellausgabe (rein, ohne Netz) ----------
def _buchstabe(token):
    t = token.strip().rstrip(").:").strip().upper()
    return t if t in BUCHSTABEN else None


def extrahiere_logprobs(antwort_json):
    """Wahrscheinlichkeiten fuer A-D aus dem ersten Token.

    Rueckgabe (probs, rest): probs sind auf Summe 1 normiert (Klassenname ->
    Wahrscheinlichkeit), rest ist die Masse ausserhalb A-D (Rohwerte, inkl.
    Wahrscheinlichkeit jenseits der top_logprobs). Fehlt logprobs, wird
    abgebrochen -- nie still auf etwas anderes ausgewichen.
    """
    lp = antwort_json.get("logprobs")
    if not lp:
        raise JudgeAbbruch(
            "Antwort enthaelt kein 'logprobs' -- dieses Modell/diese Ollama-Version "
            "liefert keine Token-Wahrscheinlichkeiten. Abbruch (kein Freitext-Fallback); "
            "--modus frei verwenden.")
    erstes = lp[0]
    kandidaten = erstes.get("top_logprobs") or [erstes]
    roh = {k: 0.0 for k in KLASSEN}
    for eintrag in kandidaten:
        b = _buchstabe(eintrag.get("token", ""))
        if b:
            roh[BUCHSTABEN[b]] += math.exp(eintrag["logprob"])
    summe = sum(roh.values())
    if summe <= 0:
        raise JudgeAbbruch("Kein A/B/C/D unter den top_logprobs des ersten Tokens.")
    rest = max(0.0, 1.0 - summe)
    return {k: v / summe for k, v in roh.items()}, rest


def urteil_aus_probs(probs):
    """Argmax; Gleichstand entscheidet die Reihenfolge richtig..unsicher."""
    return max(KLASSEN, key=lambda k: probs[k])


_URTEIL_ZEILE = re.compile(r"URTEIL\s*[:=]\s*[\*_`\"'\s]*([A-Za-zÄÖÜäöüß]+)", re.IGNORECASE)


def parse_urteil(text):
    """Freitext -> Klasse oder UNPARSEBAR. Massgeblich ist die LETZTE URTEIL-Zeile."""
    text = re.sub(r"<think>.*?(?:</think>|\Z)", " ", text or "", flags=re.DOTALL)
    treffer = _URTEIL_ZEILE.findall(text)
    if not treffer:
        return UNPARSEBAR
    wort = treffer[-1].lower()
    return wort if wort in KLASSEN else UNPARSEBAR


# ---------- Aufrufe ----------
def _post(url, **kw):
    try:
        r = requests.post(url, **kw)
    except requests.RequestException as e:
        raise JudgeAbbruch(f"Netzfehler bei {url}: {type(e).__name__}") from None
    if r.status_code >= 400:
        raise JudgeAbbruch(f"{url} antwortet {r.status_code}: {r.text[:300]}")
    return r.json()


def _ollama_chat(modell, prompt, optionen, extra=None):
    body = {"model": modell, "stream": False, "think": False,
            "messages": [{"role": "user", "content": prompt}], "options": optionen}
    body.update(extra or {})
    return _post(f"{OLLAMA}/api/chat", json=body, timeout=600)


def lies_anthropic_key(pfad=None):
    pfad = pfad or ANTHROPIC_KEY_DATEI
    if not os.path.isfile(pfad):
        raise ModusNichtVerfuegbar(
            f"Modus 'anthropic' nicht verfuegbar: Key-Datei {pfad} fehlt.")
    with open(pfad) as f:
        key = f.read().strip()
    if not key:
        raise ModusNichtVerfuegbar(f"Modus 'anthropic' nicht verfuegbar: {pfad} ist leer.")
    return key


def bewerte(modus, modell, frage, antwort):
    """Ein Urteil. Rueckgabe: dict(urteil, probs, rest, rohtext, sekunden)."""
    prompt = baue_prompt(frage, antwort, modus)
    t0 = time.perf_counter()
    if modus == "logprob":
        j = _ollama_chat(modell, prompt, {"num_predict": 1, "temperature": 0},
                         {"logprobs": True, "top_logprobs": 20})
        probs, rest = extrahiere_logprobs(j)
        res = {"urteil": urteil_aus_probs(probs), "probs": probs, "rest": rest,
               "rohtext": j.get("message", {}).get("content", "")}
    elif modus == "frei":
        j = _ollama_chat(modell, prompt, {"num_predict": 600, "temperature": 0})
        text = j.get("message", {}).get("content", "")
        res = {"urteil": parse_urteil(text), "probs": None, "rest": None, "rohtext": text}
    elif modus == "anthropic":
        key = lies_anthropic_key()
        j = _post(ANTHROPIC_URL, timeout=120,
                  headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                           "content-type": "application/json"},
                  json={"model": modell, "max_tokens": 600, "temperature": 0,
                        "messages": [{"role": "user", "content": prompt}]})
        text = "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text")
        res = {"urteil": parse_urteil(text), "probs": None, "rest": None, "rohtext": text}
    else:
        raise JudgeAbbruch(f"Unbekannter Modus: {modus}")
    res["sekunden"] = time.perf_counter() - t0
    return res


# ---------- Metriken (rein) ----------
def _quote(zaehler, nenner):
    return {"zaehler": zaehler, "nenner": nenner,
            "quote": (zaehler / nenner) if nenner else None}


def _aufschluesselung(urteile, label, urteil_soll, schluessel):
    """Quote 'label wurde als urteil_soll gewertet', gesamt und je Schluessel."""
    gruppen = defaultdict(list)
    for u in urteile:
        if u["label"] == label:
            gruppen[schluessel(u)].append(u)
    je = {k: _quote(sum(1 for u in v if u["urteil"] == urteil_soll), len(v))
          for k, v in sorted(gruppen.items())}
    alle = [u for v in gruppen.values() for u in v]
    gesamt = _quote(sum(1 for u in alle if u["urteil"] == urteil_soll), len(alle))
    return gesamt, je


def _schlechtestes(je_spiel):
    kand = [(v["quote"], k) for k, v in je_spiel.items() if v["nenner"]]
    if not kand:
        return None
    _, k = max(kand)
    return {"spiel_id": k, **je_spiel[k]}


def konfusionsmatrix(urteile):
    m = {l: {u: 0 for u in KLASSEN + (UNPARSEBAR,)} for l in KLASSEN}
    for u in urteile:
        m[u["label"]][u["urteil"]] += 1
    return m


def berechne_metriken(einzel):
    """Alle Kennzahlen. strittig=true faellt aus den Hauptzahlen und wird separat ausgewiesen."""
    haupt = [u for u in einzel if not u.get("strittig")]
    strittig = [u for u in einzel if u.get("strittig")]
    art = lambda u: u.get("fehlerart") or "-"
    spiel = lambda u: u["spiel_id"]

    dw_ges, dw_art = _aufschluesselung(haupt, "falsch", "richtig", art)
    _, dw_spiel = _aufschluesselung(haupt, "falsch", "richtig", spiel)
    ab_ges, ab_art = _aufschluesselung(haupt, "richtig", "falsch", art)
    _, ab_spiel = _aufschluesselung(haupt, "richtig", "falsch", spiel)

    def n(label):
        return sum(1 for u in haupt if u["label"] == label)

    def z(label, urteil):
        return sum(1 for u in haupt if u["label"] == label and u["urteil"] == urteil)

    unsicher = {
        "unsicher_als_falsch": _quote(z("unsicher", "falsch"), n("unsicher")),
        "unsicher_als_richtig": _quote(z("unsicher", "richtig"), n("unsicher")),
        "falsch_als_unsicher": _quote(z("falsch", "unsicher"), n("falsch")),
        "richtig_als_unsicher": _quote(z("richtig", "unsicher"), n("richtig")),
    }

    m = {
        "anzahl_haupt": len(haupt),
        "anzahl_strittig": len(strittig),
        "matrix": konfusionsmatrix(haupt),
        "matrix_strittig": konfusionsmatrix(strittig),
        "durchgewunken": {"gesamt": dw_ges, "je_fehlerart": dw_art, "je_spiel": dw_spiel,
                          "schlechtestes_spiel": _schlechtestes(dw_spiel)},
        "abgelehnt": {"gesamt": ab_ges, "je_fehlerart": ab_art, "je_spiel": ab_spiel,
                      "schlechtestes_spiel": _schlechtestes(ab_spiel)},
        "unsicher_trennung": unsicher,
        "unparsebar": _quote(sum(1 for u in haupt if u["urteil"] == UNPARSEBAR), len(haupt)),
        "laufzeit": laufzeit(einzel),
    }
    lp = [u for u in haupt if u.get("probs")]
    if lp:
        m["kalibrierung"] = kalibrierung(lp)
        m["schwellen"] = schwellen(lp)
    return m


def laufzeit(einzel):
    s = [u["sekunden"] for u in einzel if u.get("sekunden") is not None]
    if not s:
        return {"n": 0, "median": None, "max": None}
    return {"n": len(s), "median": statistics.median(s), "max": max(s)}


def _konfidenz(u):
    return max(u["probs"].values())


def kalibrierung(lp):
    out = []
    for lo, hi, name in BINS:
        drin = [u for u in lp if lo <= _konfidenz(u) < hi]
        treffer = sum(1 for u in drin if u["urteil"] == u["label"])
        out.append({"bin": name, "n": len(drin), "treffer": treffer,
                    "trefferquote": (treffer / len(drin)) if drin else None})
    return out


def schwellen(lp):
    out = []
    for t in SCHWELLEN:
        unter = [u for u in lp if _konfidenz(u) < t]
        ueber = [u for u in lp if _konfidenz(u) >= t]
        fehler = sum(1 for u in ueber if u["urteil"] != u["label"])
        out.append({"schwelle": t,
                    "eskalation": _quote(len(unter), len(lp)),
                    "fehler_oberhalb": _quote(fehler, len(ueber))})
    return out


# ---------- Eichlauf ----------
def lade_eichmenge(pfad):
    with open(pfad, encoding="utf-8") as f:
        eintraege = [json.loads(z) for z in f if z.strip()]
    for e in eintraege:
        if e["label"] not in KLASSEN:
            raise JudgeAbbruch(f"Eichmenge: unbekanntes Label {e['label']!r} "
                               f"({e['spiel_id']}/{e['frage_id']})")
    return eintraege


def lade_golden(golden_dir, spiel_ids):
    golden = {}
    for sid in sorted(set(spiel_ids)):
        pfad = os.path.join(golden_dir, f"{sid}.korrigiert.json")
        if not os.path.isfile(pfad):
            raise JudgeAbbruch(f"Golden Set fehlt: {pfad}")
        with open(pfad, encoding="utf-8") as f:
            golden[sid] = {q["id"]: q for q in json.load(f)["fragen"]}
    return golden


def eichen(eintraege, golden, modus, modell, bewerter=bewerte, log=None):
    """Alle Eintraege bewerten. Rueckgabe: Liste der Einzelurteile."""
    fehlend = [(e["spiel_id"], e["frage_id"]) for e in eintraege
               if e["frage_id"] not in golden.get(e["spiel_id"], {})]
    if fehlend:
        raise JudgeAbbruch(f"Frage-IDs nicht im Golden Set: {fehlend[:10]}")
    einzel = []
    for i, e in enumerate(eintraege, 1):
        frage = golden[e["spiel_id"]][e["frage_id"]]
        r = bewerter(modus, modell, frage, e["antwort"])
        einzel.append({
            "spiel_id": e["spiel_id"], "frage_id": e["frage_id"], "label": e["label"],
            "fehlerart": e.get("fehlerart"), "strittig": bool(e.get("strittig")),
            "urteil": r["urteil"], "probs": r.get("probs"), "rest": r.get("rest"),
            "sekunden": r["sekunden"], "rohtext": r.get("rohtext"),
        })
        if log:
            log(f"[{i}/{len(eintraege)}] {e['spiel_id']}/{e['frage_id']} "
                f"label={e['label']} urteil={r['urteil']} {r['sekunden']:.1f}s")
    return einzel


# ---------- Ausgabe ----------
def _p(q):
    if q["nenner"] == 0:
        return "n/a (0)"
    return f"{q['quote']*100:.1f}% ({q['zaehler']}/{q['nenner']})"


def _matrix_text(m):
    sp = KLASSEN + (UNPARSEBAR,)
    zeilen = ["Label \\ Urteil".ljust(16) + "".join(s.rjust(11) for s in sp)]
    for l in KLASSEN:
        zeilen.append(l.ljust(16) + "".join(str(m[l][s]).rjust(11) for s in sp))
    return "\n".join(zeilen)


def formatiere(m, modus, modell):
    z = [f"=== Eichlauf: Modus {modus}, Modell {modell} ===",
         f"Hauptzahlen: {m['anzahl_haupt']} Eintraege; strittig (separat): {m['anzahl_strittig']}",
         "", "Konfusionsmatrix (ohne strittig):", _matrix_text(m["matrix"])]
    if m["anzahl_strittig"]:
        z += ["", "Nur strittige Eintraege:", _matrix_text(m["matrix_strittig"])]
    z.append(f"\nUnparsebar (zaehlt als Fehler): {_p(m['unparsebar'])}")
    for titel, k in (("Durchgewunken (falsch als richtig)", "durchgewunken"),
                     ("Abgelehnt (richtig als falsch)", "abgelehnt")):
        d = m[k]
        z += ["", f"{titel}: {_p(d['gesamt'])}"]
        z += [f"  Fehlerart {a}: {_p(q)}" for a, q in d["je_fehlerart"].items()]
        z += [f"  Spiel {a}: {_p(q)}" for a, q in d["je_spiel"].items()]
        s = d["schlechtestes_spiel"]
        z.append("  schlechtestes Spiel: " + (f"{s['spiel_id']} {_p(s)}" if s else "n/a"))
    z += ["", "unsicher-Trennung:"]
    z += [f"  {k}: {_p(q)}" for k, q in m["unsicher_trennung"].items()]
    if "kalibrierung" in m:
        z += ["", "Kalibrierung (max. Wahrscheinlichkeit -> Trefferquote):"]
        for b in m["kalibrierung"]:
            tq = "n/a" if b["trefferquote"] is None else f"{b['trefferquote']*100:.1f}%"
            z.append(f"  {b['bin']:>9}: n={b['n']:>3}  Treffer {b['treffer']}/{b['n']} = {tq}")
        z += ["", "Schwellen (Eskalation = Anteil unter Schwelle; Fehler oberhalb):"]
        for s in m["schwellen"]:
            z.append(f"  {s['schwelle']}: Eskalation {_p(s['eskalation'])}; "
                     f"Fehler oberhalb {_p(s['fehler_oberhalb'])}")
    lz = m["laufzeit"]
    if lz["n"]:
        z += ["", f"Laufzeit je Aufruf (n={lz['n']}): typisch (Median) {lz['median']:.2f}s, "
                  f"Maximum {lz['max']:.2f}s"]
    return "\n".join(z)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="kommando", required=True)
    e = sub.add_parser("eichen", help="Judge an einer Eichmenge messen")
    e.add_argument("--eichmenge", required=True)
    e.add_argument("--golden-dir", required=True)
    e.add_argument("--modus", required=True, choices=("logprob", "frei", "anthropic"))
    e.add_argument("--modell", default=None)
    e.add_argument("--ausgabe", default=None, help="JSON-Datei (Default: eichlauf_<modus>.json)")
    e.add_argument("--limit", type=int, default=None, help="nur die ersten N Eintraege (Rauchtest)")
    a = ap.parse_args(argv)

    modell = a.modell or (ANTHROPIC_DEFAULT if a.modus == "anthropic" else OLLAMA_DEFAULT)
    try:
        if a.modus == "anthropic":
            lies_anthropic_key()  # frueh scheitern, nicht erst beim ersten Aufruf
        eintraege = lade_eichmenge(a.eichmenge)
        if a.limit:
            eintraege = eintraege[:a.limit]
        golden = lade_golden(a.golden_dir, [x["spiel_id"] for x in eintraege])
        einzel = eichen(eintraege, golden, a.modus, modell, log=lambda s: print(s, file=sys.stderr))
    except JudgeAbbruch as ex:
        print(f"ABBRUCH: {ex}", file=sys.stderr)
        return 2
    m = berechne_metriken(einzel)
    print(formatiere(m, a.modus, modell))
    ziel = a.ausgabe or f"eichlauf_{a.modus}.json"
    with open(ziel, "w", encoding="utf-8") as f:
        json.dump({"modus": a.modus, "modell": modell, "metriken": m, "einzelurteile": einzel},
                  f, ensure_ascii=False, indent=2)
    print(f"\nEinzelurteile: {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
