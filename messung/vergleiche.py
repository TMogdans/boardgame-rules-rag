#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vergleicht bewertete Messlaeufe (urteile.jsonl, siehe bewerte.py).

    python messung/vergleiche.py NAME=LAUF1,LAUF2 NAME2=LAUF3,LAUF4 [--basis NAME] [--min-laeufe 2]

Ein Setting ist eine Gruppe von Laufverzeichnissen mit DERSELBEN Konfiguration
(Wiederholungen). Ein Argument ohne "=" ist ein Setting aus einem einzigen Lauf.

Kennzahlen (bewusst ohne Mittelwerte; immer typisch = Median und Maximum):
  richtig/teilweise/falsch/unsicher/unparsebar   Zahl der Urteile je Lauf
  Treffsicherheit = richtig / (alle - unsicher)  je Lauf, dazu Minimum und Maximum ueber die Laeufe
  stabil richtig / stabil falsch                 Fragen, die in ALLEN Wiederholungen so bewertet wurden
  Laufzeit der Antwort                           Median (typisch) und Maximum, je Lauf und gepoolt
  gleichgerichtet                                Fragen, die sich gegenueber dem Basis-Setting in allen
                                                 Wiederholungen beider Settings in dieselbe Richtung aendern

Rangfolge der Urteile fuer "gleichgerichtet": falsch < unsicher < teilweise < richtig.
Eine Frage gilt als verbessert, wenn JEDER Lauf des Settings besser bewertet ist als JEDER
Lauf der Basis (min(Setting) > max(Basis)); verschlechtert entsprechend spiegelbildlich.
Antworten sind nicht deterministisch: mit weniger als --min-laeufe Wiederholungen je Setting
gibt es dazu keine Aussage.
"""
import json
import os
import statistics
import sys

KLASSEN = ("richtig", "teilweise", "falsch", "unsicher")
ALLE_URTEILE = KLASSEN + ("unparsebar",)
RANG = {"falsch": 0, "unsicher": 1, "teilweise": 2, "richtig": 3}


class VergleichFehler(Exception):
    pass


def lies_lauf(verz):
    """{(spiel_id, frage_id): {"urteil", "t"}} aus VERZ/urteile.jsonl."""
    pfad = os.path.join(verz, "urteile.jsonl")
    if not os.path.isfile(pfad):
        raise VergleichFehler(f"{pfad} fehlt -- erst messung/bewerte.py laufen lassen.")
    lauf = {}
    with open(pfad, encoding="utf-8") as f:
        for z in f:
            if not z.strip():
                continue
            d = json.loads(z)
            schluessel = (d["spiel_id"], d["frage_id"])
            if schluessel in lauf:
                raise VergleichFehler(f"{pfad}: Frage {schluessel} doppelt.")
            lauf[schluessel] = {"urteil": d["urteil"], "t": d.get("t_antwort")}
    if not lauf:
        raise VergleichFehler(f"{pfad} ist leer.")
    return lauf


def median_max(werte):
    werte = [w for w in werte if w is not None]
    if not werte:
        return {"n": 0, "median": None, "max": None}
    return {"n": len(werte), "median": statistics.median(werte), "max": max(werte)}


def treffsicherheit(zaehler, alle):
    """richtig / (alle - unsicher); None, wenn der Nenner 0 ist."""
    nenner = alle - zaehler["unsicher"]
    return {"zaehler": zaehler["richtig"], "nenner": nenner,
            "quote": zaehler["richtig"] / nenner if nenner else None}


def kennzahlen_lauf(lauf):
    zaehler = {u: 0 for u in ALLE_URTEILE}
    for e in lauf.values():
        if e["urteil"] not in zaehler:
            raise VergleichFehler(f"Unbekanntes Urteil {e['urteil']!r}.")
        zaehler[e["urteil"]] += 1
    return {"n": len(lauf), "zaehler": zaehler,
            "treffsicherheit": treffsicherheit(zaehler, len(lauf)),
            "zeit": median_max(e["t"] for e in lauf.values())}


def pruefe_gleiche_fragen(laeufe, name):
    """Wiederholungen muessen dieselben Fragen haben -- sonst vergleicht stabil() Aepfel mit Birnen."""
    erste = set(laeufe[0])
    for i, l in enumerate(laeufe[1:], 2):
        if set(l) != erste:
            fehlt, extra = erste - set(l), set(l) - erste
            raise VergleichFehler(f"Setting {name}: Lauf {i} hat andere Fragen als Lauf 1 "
                                  f"({len(fehlt)} fehlen, {len(extra)} zusaetzlich).")


def stabil(laeufe):
    """(stabil_richtig, stabil_falsch): Fragen, deren Urteil in ALLEN Laeufen richtig bzw. falsch ist."""
    richtig, falsch = [], []
    for k in sorted(laeufe[0]):
        u = {l[k]["urteil"] for l in laeufe}
        if u == {"richtig"}:
            richtig.append(k)
        elif u == {"falsch"}:
            falsch.append(k)
    return richtig, falsch


def gleichgerichtet(basis, setting):
    """(verbessert, verschlechtert): Fragen, die sich in allen Laeufen beider Settings gleich bewegen."""
    besser, schlechter = [], []
    for k in sorted(basis[0]):
        if k not in setting[0]:
            continue
        a = [RANG.get(l[k]["urteil"]) for l in basis]
        b = [RANG.get(l[k]["urteil"]) for l in setting]
        if None in a or None in b:   # unparsebar hat keine Richtung
            continue
        if min(b) > max(a):
            besser.append(k)
        elif max(b) < min(a):
            schlechter.append(k)
    return besser, schlechter


def setting_kennzahlen(name, laeufe):
    pruefe_gleiche_fragen(laeufe, name)
    je_lauf = [kennzahlen_lauf(l) for l in laeufe]
    quoten = [k["treffsicherheit"]["quote"] for k in je_lauf if k["treffsicherheit"]["quote"] is not None]
    s_richtig, s_falsch = stabil(laeufe)
    return {"name": name, "laeufe": len(laeufe), "je_lauf": je_lauf,
            "treffsicherheit_min": min(quoten) if quoten else None,
            "treffsicherheit_max": max(quoten) if quoten else None,
            "zeit": median_max(e["t"] for l in laeufe for e in l.values()),
            "stabil_richtig": s_richtig, "stabil_falsch": s_falsch}


def vergleiche(settings, basis_name=None, min_laeufe=2):
    """settings: {name: [lauf, ...]} (Reihenfolge = Ausgabe). Rueckgabe: Kennzahlen + Paarvergleiche."""
    if not settings:
        raise VergleichFehler("Keine Laeufe angegeben.")
    namen = list(settings)
    basis_name = basis_name or namen[0]
    if basis_name not in settings:
        raise VergleichFehler(f"--basis {basis_name!r} ist keines der Settings {namen}.")
    kz = {n: setting_kennzahlen(n, l) for n, l in settings.items()}
    paare = {}
    for n in namen:
        if n == basis_name:
            continue
        if len(settings[n]) < min_laeufe or len(settings[basis_name]) < min_laeufe:
            paare[n] = None   # keine Aussage: zu wenige Wiederholungen
        else:
            paare[n] = gleichgerichtet(settings[basis_name], settings[n])
    return {"basis": basis_name, "settings": kz, "paare": paare, "min_laeufe": min_laeufe}


def _q(t):
    return "  -  " if t["quote"] is None else f"{t['quote']:.3f}"


def _s(x):
    return "-" if x is None else f"{x:.1f}s"


def formatiere(erg):
    z = []
    for n, s in erg["settings"].items():
        z.append(f"== {n}  ({s['laeufe']} Lauf/Laeufe)")
        z.append(f"  {'Lauf':>4} {'n':>4} {'richtig':>8} {'teilw.':>7} {'falsch':>7} {'unsich.':>8} "
                 f"{'unpars.':>8} {'Treffs.':>8} {'Zeit typ.':>10} {'Zeit max':>9}")
        for i, k in enumerate(s["je_lauf"], 1):
            c = k["zaehler"]
            z.append(f"  {i:>4} {k['n']:>4} {c['richtig']:>8} {c['teilweise']:>7} {c['falsch']:>7} "
                     f"{c['unsicher']:>8} {c['unparsebar']:>8} {_q(k['treffsicherheit']):>8} "
                     f"{_s(k['zeit']['median']):>10} {_s(k['zeit']['max']):>9}")
        if s["treffsicherheit_min"] is not None:
            z.append(f"  Treffsicherheit ueber die Laeufe: Minimum {s['treffsicherheit_min']:.3f}, "
                     f"Maximum {s['treffsicherheit_max']:.3f}")
        z.append(f"  Laufzeit gepoolt: typisch (Median) {_s(s['zeit']['median'])}, Maximum {_s(s['zeit']['max'])}"
                 f"  ({s['zeit']['n']} Antworten)")
        if s["laeufe"] < 2:
            z.append("  stabil richtig/falsch: keine Aussage mit nur 1 Lauf")
        else:
            z.append(f"  stabil richtig: {len(s['stabil_richtig'])}   stabil falsch: {len(s['stabil_falsch'])}")
            if s["stabil_falsch"]:
                z.append("    stabil falsch: " + ", ".join(f"{a}/{b}" for a, b in s["stabil_falsch"]))
        z.append("")
    for n, p in erg["paare"].items():
        kopf = f"== {n} gegen Basis {erg['basis']}"
        if p is None:
            z.append(f"{kopf}: keine Aussage -- weniger als {erg['min_laeufe']} Wiederholungen je Setting")
            z.append("")
            continue
        besser, schlechter = p
        z.append(f"{kopf}: gleichgerichtet in allen Laeufen")
        z.append(f"  verbessert: {len(besser)}   verschlechtert: {len(schlechter)}")
        for etikett, liste in (("verbessert", besser), ("verschlechtert", schlechter)):
            if liste:
                z.append(f"    {etikett}: " + ", ".join(f"{a}/{b}" for a, b in liste))
        z.append("")
    return "\n".join(z).rstrip() + "\n"


def parse_argumente(argv):
    """['A=x,y', 'B=z'] -> {'A': [x, y], 'B': [z]}; ohne '=' heisst das Setting wie das Verzeichnis."""
    settings = {}
    for a in argv:
        name, sep, rest = a.partition("=")
        verz = [v for v in rest.split(",") if v] if sep else [a]
        if not sep:
            name = os.path.basename(os.path.normpath(a))
        if not verz:
            raise VergleichFehler(f"{a!r}: keine Laufverzeichnisse.")
        if name in settings:
            raise VergleichFehler(f"Setting {name!r} doppelt.")
        settings[name] = verz
    return settings


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    basis, min_laeufe, rest = None, 2, []
    while argv:
        a = argv.pop(0)
        if a in ("--basis", "--min-laeufe"):
            if not argv:
                print(f"{a} braucht einen Wert.", file=sys.stderr)
                return 2
            wert = argv.pop(0)
            if a == "--basis":
                basis = wert
            else:
                min_laeufe = int(wert)
        else:
            rest.append(a)
    if not rest:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        settings = {n: [lies_lauf(v) for v in verz] for n, verz in parse_argumente(rest).items()}
        print(formatiere(vergleiche(settings, basis, min_laeufe)), end="")
    except (VergleichFehler, OSError, json.JSONDecodeError, ValueError) as e:
        print(f"Abbruch: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
