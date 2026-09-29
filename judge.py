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

Golden-Fragen mit `kern`/`zusatz` bekommen die Kern/Zusatz-Variante des Prompts;
--golden-suffix waehlt die Golden-Dateien (Default .korrigiert.json, z. B. .v2.json).
--eichmenge-overrides <jsonl> ({"zeile": 0-basiert, "neu": label}) ueberschreibt Labels
nur fuer den Lauf. Im Modus anthropic werden Token und Kosten mitgezaehlt.

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
# Preise in USD je Million Token, Haiku 4.5. Stand 2026-09, pruefen (gelten nur fuer ANTHROPIC_DEFAULT).
PREIS_INPUT_USD_MTOK = 1.0
PREIS_OUTPUT_USD_MTOK = 5.0
GOLDEN_SUFFIX_DEFAULT = ".korrigiert.json"

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

# Variante fuer Golden-Set-Fragen mit kern/zusatz: praezisere Klassengrenzen.
KLASSEN_TEXT_KERN = """\
Klassen:
- richtig: Der Kern steht korrekt in der Antwort (Umformulierung, andere Sprache für Spielbegriffe, Zahlwort statt Ziffer ok) und kein Zusatz ist falsch wiedergegeben. Fehlende Zusätze sind kein Mangel. Ist laut Golden Set Verweigern richtig (erwartet_verweigerung: true), ist eine ehrliche Aussage „steht nicht im Heft“ richtig.
- teilweise: Der Kern steht nur unvollständig in der Antwort (z. B. ohne eine für die Entscheidung wesentliche Ausnahme), ohne Falsches zu behaupten. Fehlende Zusätze sind KEIN Grund für teilweise.
- falsch: enthält eine falsche Regelaussage (auch neben richtigen Teilen, auch ein falsch wiedergegebener Zusatz) oder erfindet bei einer Leerstelle eine Regel/Zahl. Vorsichtig formuliert, aber inhaltlich falsch = falsch. Eine falsche Anzahl, Aufzählung mit behaupteter Vollständigkeit („es gibt drei …“, wenn es vier sind) oder eine falsche Einschränkung („sofort“, „nur“, „immer“), die dem Kern widerspricht, ist falsch, nicht teilweise.
- unsicher: sagt ehrlich, dass es die Antwort nicht sicher weiß/gefunden hat, ohne Falsches zu behaupten. Das ist KEIN Fehler, auch wenn die Antwort im Regelheft steht: ob sie gefunden wurde, wird getrennt gemessen. Werte eine ehrlich unsichere Antwort ohne falsche Aussage immer als unsicher, nie als falsch."""

_PROMPT_EINLEITUNG = """\
Du bist Prüfer für ein Brettspiel-Regel-Assistenzsystem. Du bewertest eine Antwort des Systems gegen die Musterlösung aus dem Golden Set. Die Seitenangabe prüfst du nicht.

"""

PROMPT_KOPF = _PROMPT_EINLEITUNG + KLASSEN_TEXT + """

Frage: {frage}
Erwartet (Musterlösung): {erwartet}
Beleg aus dem Regelheft: {beleg}
Verweigern ist laut Golden Set die richtige Antwort (erwartet_verweigerung): {verweigerung}

Antwort des Systems:
\"\"\"
{antwort}
\"\"\"
"""

PROMPT_KOPF_KERN = _PROMPT_EINLEITUNG + KLASSEN_TEXT_KERN + """

Frage: {frage}
Kern (muss in der Antwort stehen, sonst höchstens teilweise): {kern}
Zusatz (darf fehlen, ohne Abzug; falsch wiedergegeben = falsch):{zusatz}
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
    """Judge-Prompt. Eingabe: Frage-Dict (frage, erwartet, beleg, erwartet_verweigerung;
    optional kern (str) und zusatz (Liste) -- mit kern gilt die Kern/Zusatz-Variante,
    ohne kern der bisherige Prompt unveraendert)."""
    gemeinsam = dict(
        frage=frage.get("frage", ""),
        beleg=frage.get("beleg") or "(keiner angegeben)",
        verweigerung="ja" if frage.get("erwartet_verweigerung") else "nein",
        antwort=antwort,
    )
    if frage.get("kern"):
        zusatz = frage.get("zusatz") or []
        kopf = PROMPT_KOPF_KERN.format(
            kern=frage["kern"],
            zusatz=("\n" + "\n".join(f"- {z}" for z in zusatz)) if zusatz else " (keiner)",
            **gemeinsam)
    else:
        kopf = PROMPT_KOPF.format(erwartet=frage.get("erwartet", ""), **gemeinsam)
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
        usage = j.get("usage") or {}
        res = {"urteil": parse_urteil(text), "probs": None, "rest": None, "rohtext": text,
               "input_tokens": usage.get("input_tokens"),
               "output_tokens": usage.get("output_tokens")}
    else:
        raise JudgeAbbruch(f"Unbekannter Modus: {modus}")
    res["sekunden"] = time.perf_counter() - t0
    return res


# ---------- Metriken (rein) ----------
def _quote(zaehler, nenner):
    return {"zaehler": zaehler, "nenner": nenner,
            "quote": (zaehler / nenner) if nenner else None}


def _aufschluesselung(urteile, label, trifft, schluessel):
    """Quote 'Eintraege mit diesem label, deren Urteil trifft(urteil) erfuellt', gesamt und je Schluessel."""
    gruppen = defaultdict(list)
    for u in urteile:
        if u["label"] == label:
            gruppen[schluessel(u)].append(u)
    je = {k: _quote(sum(1 for u in v if trifft(u["urteil"])), len(v))
          for k, v in sorted(gruppen.items())}
    alle = [u for v in gruppen.values() for u in v]
    gesamt = _quote(sum(1 for u in alle if trifft(u["urteil"])), len(alle))
    return gesamt, je


def _block(haupt, label, trifft, schluessel_art):
    gesamt, je_art = _aufschluesselung(haupt, label, trifft, schluessel_art)
    _, je_spiel = _aufschluesselung(haupt, label, trifft, lambda u: u["spiel_id"])
    return {"gesamt": gesamt, "je_fehlerart": je_art, "je_spiel": je_spiel,
            "schlechtestes_spiel": _schlechtestes(je_spiel)}


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
        "durchgewunken": _block(haupt, "falsch", lambda ur: ur == "richtig", art),
        "abgelehnt": _block(haupt, "richtig", lambda ur: ur == "falsch", art),
        # Strenger als durchgewunken: jedes Urteil ausser dem passenden zaehlt (auch teilweise/unsicher/unparsebar)
        "falsch_nicht_erkannt": _block(haupt, "falsch", lambda ur: ur != "falsch", art),
        "richtig_nicht_erkannt": _block(haupt, "richtig", lambda ur: ur != "richtig", art),
        "unsicher_trennung": unsicher,
        "unparsebar": _quote(sum(1 for u in haupt if u["urteil"] == UNPARSEBAR), len(haupt)),
        "laufzeit": laufzeit(einzel),
    }
    tk = tokens_und_kosten(einzel)
    if tk:
        m["tokens"] = tk
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


def kosten_usd(input_tokens, output_tokens):
    return (input_tokens * PREIS_INPUT_USD_MTOK + output_tokens * PREIS_OUTPUT_USD_MTOK) / 1e6


def tokens_und_kosten(einzel):
    """Token-Summen, typisch/Maximum je Aufruf und Kosten; None ohne Token-Angaben (Ollama-Modi)."""
    mit = [u for u in einzel if u.get("input_tokens") is not None
           and u.get("output_tokens") is not None]
    if not mit:
        return None
    ein = [u["input_tokens"] for u in mit]
    aus = [u["output_tokens"] for u in mit]
    kosten = [kosten_usd(i, o) for i, o in zip(ein, aus)]
    return {"n": len(mit), "aufrufe_gesamt": len(einzel),
            "input_summe": sum(ein), "output_summe": sum(aus),
            "input_typisch": statistics.median(ein), "input_max": max(ein),
            "output_typisch": statistics.median(aus), "output_max": max(aus),
            "kosten_usd_summe": sum(kosten), "kosten_usd_typisch": statistics.median(kosten),
            "kosten_usd_max": max(kosten),
            "preis_input_usd_mtok": PREIS_INPUT_USD_MTOK,
            "preis_output_usd_mtok": PREIS_OUTPUT_USD_MTOK}


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


def lade_overrides(pfad):
    """JSONL mit {"zeile": <0-basiert>, "neu": <label>} -> Liste der Overrides."""
    with open(pfad, encoding="utf-8") as f:
        ov = [json.loads(z) for z in f if z.strip()]
    for o in ov:
        if o.get("neu") not in KLASSEN:
            raise JudgeAbbruch(f"Overrides: unbekanntes Label {o.get('neu')!r} (Zeile {o.get('zeile')})")
        if not isinstance(o.get("zeile"), int) or isinstance(o["zeile"], bool):
            raise JudgeAbbruch(f"Overrides: 'zeile' muss eine ganze Zahl sein: {o!r}")
    return ov


def wende_overrides(eintraege, overrides):
    """Kopie der Eichmenge mit ueberschriebenen Labels (Zeilen 0-basiert, wie in der Datei).

    Die Eichmenge selbst bleibt unangetastet. Ueberschriebene Eintraege tragen
    override=True und label_original; die fehlerart entfaellt, wenn das neue Label
    nicht 'falsch' ist (ausser der Override nennt eine).
    """
    neu = [dict(e) for e in eintraege]
    gesehen = set()
    for o in overrides:
        z = o["zeile"]
        if not 0 <= z < len(neu):
            raise JudgeAbbruch(f"Overrides: Zeile {z} ausserhalb der Eichmenge (0..{len(neu) - 1})")
        if z in gesehen:
            raise JudgeAbbruch(f"Overrides: Zeile {z} doppelt")
        gesehen.add(z)
        e = neu[z]
        e["label_original"] = e["label"]
        e["override"] = True
        e["label"] = o["neu"]
        if "fehlerart" in o:
            e["fehlerart"] = o["fehlerart"]
        elif o["neu"] != "falsch":
            e["fehlerart"] = None
    return neu


def lade_golden(golden_dir, spiel_ids, suffix=GOLDEN_SUFFIX_DEFAULT):
    golden = {}
    for sid in sorted(set(spiel_ids)):
        pfad = os.path.join(golden_dir, f"{sid}{suffix}")
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
            "input_tokens": r.get("input_tokens"), "output_tokens": r.get("output_tokens"),
        })
        if e.get("override"):
            einzel[-1]["override"] = True
            einzel[-1]["label_original"] = e["label_original"]
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
                     ("Falsch nicht erkannt (falsch, Urteil != falsch)", "falsch_nicht_erkannt"),
                     ("Abgelehnt (richtig als falsch)", "abgelehnt"),
                     ("Richtig nicht erkannt (richtig, Urteil != richtig)", "richtig_nicht_erkannt")):
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
    tk = m.get("tokens")
    if tk:
        z += ["", f"Tokens (n={tk['n']} von {tk['aufrufe_gesamt']} Aufrufen): "
                  f"Input {tk['input_summe']}, Output {tk['output_summe']}",
              f"  je Aufruf Input: typisch (Median) {tk['input_typisch']:g}, Maximum {tk['input_max']}",
              f"  je Aufruf Output: typisch (Median) {tk['output_typisch']:g}, Maximum {tk['output_max']}",
              f"Kosten (Preise Input {tk['preis_input_usd_mtok']:g} / Output "
              f"{tk['preis_output_usd_mtok']:g} USD je MTok, Haiku 4.5, Stand 2026-09): "
              f"Summe ${tk['kosten_usd_summe']:.4f}, je Aufruf typisch ${tk['kosten_usd_typisch']:.5f}, "
              f"Maximum ${tk['kosten_usd_max']:.5f}"]
    return "\n".join(z)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="kommando", required=True)
    e = sub.add_parser("eichen", help="Judge an einer Eichmenge messen")
    e.add_argument("--eichmenge", required=True)
    e.add_argument("--golden-dir", required=True)
    e.add_argument("--golden-suffix", default=GOLDEN_SUFFIX_DEFAULT,
                   help=f"Dateiendung der Golden-Sets (Default {GOLDEN_SUFFIX_DEFAULT}, z. B. .v2.json)")
    e.add_argument("--eichmenge-overrides", default=None,
                   help='JSONL {"zeile": <0-basiert>, "neu": <label>}: Labels fuer diesen Lauf ueberschreiben')
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
        overrides = lade_overrides(a.eichmenge_overrides) if a.eichmenge_overrides else []
        eintraege = wende_overrides(eintraege, overrides)
        if a.limit:
            eintraege = eintraege[:a.limit]
        golden = lade_golden(a.golden_dir, [x["spiel_id"] for x in eintraege], a.golden_suffix)
        einzel = eichen(eintraege, golden, a.modus, modell, log=lambda s: print(s, file=sys.stderr))
    except JudgeAbbruch as ex:
        print(f"ABBRUCH: {ex}", file=sys.stderr)
        return 2
    m = berechne_metriken(einzel)
    print(formatiere(m, a.modus, modell))
    if overrides:
        print(f"\nOverrides: {len(overrides)} Label(s) fuer diesen Lauf ueberschrieben "
              f"({a.eichmenge_overrides}); Eichmenge unveraendert")
    ziel = a.ausgabe or f"eichlauf_{a.modus}.json"
    with open(ziel, "w", encoding="utf-8") as f:
        json.dump({"modus": a.modus, "modell": modell, "golden_suffix": a.golden_suffix,
                   "overrides": overrides, "metriken": m, "einzelurteile": einzel},
                  f, ensure_ascii=False, indent=2)
    print(f"\nEinzelurteile: {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
