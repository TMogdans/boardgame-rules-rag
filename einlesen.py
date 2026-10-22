#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ein Buch eines Mehr-Buecher-Bestands einlesen (Spec .specify/specs/mehrbuch-bestand/spec.md).

    python einlesen.py <spiel_id> <buch_id> [--pdf PFAD] [--ueberschreiben]

Kette: Docling-Layout (Lesereihenfolge, ohne LLM, REQ-MB-23) -> Zeilen je Seite (Text aus
Bild-Elementen inklusive, REQ-MB-27) -> optional pdfplumber-Schrift und -Lage je Zeile (REQ-MB-29)
-> reine Funktionen dieses Moduls: Rand verwerfen (REQ-MB-28), Ueberschriften-Liste abgleichen
(REQ-MB-12/-13), Layout-Ueberschriften (REQ-MB-20), Trennungen reparieren (REQ-MB-11) ->
Abschnitte -> data/<spiel_id>/buecher/<buch_id>/knowledge.jsonl (ein Eintrag je Abschnitt; das
Zerschneiden in Haeppchen macht `rag.py index`, REQ-MB-14).

Alles Buchspezifische (Liste, Seitenzahlen, Schriftstufen, Rand, Veto, Vorspann, Konjunktionen)
steht in der Buchdeklaration in spiel.json -- dieses Modul kennt kein Buch.

Docling und pdfplumber werden nur im Adapter (lies_pdf_ein, ordne_schrift_zu) importiert: das
Modul selbst laeuft ohne beide (Tests mit synthetischen Zeilen).
"""
import bisect
import json
import os
import re
import sys
import unicodedata

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import rag  # noqa: E402

KonfigFehler = rag.KonfigFehler

# Messergebnis der Vorab-Messung (REQ-MB-23): Docling- und pdfplumber-Version, mit denen gemessen wurde
VORABMESSUNG = os.path.join(BASE, ".specify", "specs", "mehrbuch-bestand", "vorabmessung.json")
# Ergaenzungsstrich vor Konjunktion ("Nah- und Fernkampf"), je Sprache; Buchdeklaration
# "reparatur": {"konjunktionen": [...]} ersetzt die Liste.
KONJUNKTIONEN = {"de": ("und", "oder", "bis", "sowie", "bzw"), "en": ("and", "or", "to", "nor")}
# Layout-Klassen, deren Zeilen nie Ueberschrift sind (REQ-MB-20); "veto" im Buch ergaenzt sie.
VETO_STANDARD = ("table", "caption", "page_header", "page_footer")
# Schnitt-Merkmale einer Schrift (aus dem Schriftnamen), je Schriftstufe optional deklariert
SCHNITTE = ("fett", "kursiv", "kapitaelchen")
_SCHNITT_MUSTER = {"fett": re.compile(r"Bold|Semibold|SemiBold|Demi|Heavy|Black"),
                   "kursiv": re.compile(r"Italic|Oblique|Kursiv"),
                   "kapitaelchen": re.compile(r"SC(?![a-z])|SmallCaps|Smallcaps")}
SHY = "­"
BILD_KLASSEN = ("picture", "chart")
PROTOKOLL_DATEI = "einlese_protokoll.json"


class Protokoll:
    """Einlese-Protokoll eines Buchs: Zaehler je Reparatur-/Erkennungsschritt."""

    def __init__(self):
        self.trennungen_zusammengefuegt = 0     # REQ-MB-11
        self.strich_behalten = 0
        self.gefunden, self.nicht_gefunden, self.mehrdeutig = [], [], []   # REQ-MB-12/-13: (titel, seite)
        self.layout_ueberschriften = {}         # REQ-MB-20: Pfad des Listenabschnitts -> Anzahl
        self.layout_je_stufe = {}
        self.rueckfaelle = 0
        self.rand_verhindert = 0
        self.veto_verhindert = 0
        self.randzeilen = 0                     # REQ-MB-28
        self.ohne_lage = 0                      # Rand deklariert, Zeile ohne Lage: gilt als nicht im Rand
        self.aus_bildern = 0                    # REQ-MB-27
        self.docling_version = None             # REQ-MB-23
        self.pdfplumber_version = None
        self.abschnitte = 0
        self.umsortiert = 0                     # REQ-MB-31
        self.binnen_grossbuchstabe = {"anzahl": 0, "seiten": []}   # REQ-MB-32
        self.strichrest = {"anzahl": 0, "seiten": []}

    def als_dict(self):
        d = dict(vars(self))
        d["layout_ueberschriften"] = [[list(k), v] for k, v in self.layout_ueberschriften.items()]
        return d


def _zaehle(d, schluessel):
    d[schluessel] = d.get(schluessel, 0) + 1


# ---------- REQ-MB-11: Trennungen ----------
def _zeile_vorbereiten(zeile):
    """Leerraum der Zeile zusammenfassen; weiche Trennstriche im Wort entfernen, einen am
    Zeilenende stehen lassen (er entscheidet die Verbindung zur naechsten Zeile)."""
    zeile = " ".join(zeile.split())
    if zeile.endswith(SHY):
        return zeile[:-1].replace(SHY, "") + SHY
    return zeile.replace(SHY, "")


class _Verbinder:
    """Fuegt Zeilen zu einem Text zusammen und repariert dabei die Trennungen an den Zeilengrenzen.

    add() liefert den Offset, an dem der Text der Zeile im Ergebnis beginnt -- daraus entstehen die
    Seitenwechsel eines Abschnitts (REQ-MB-16), ohne dass eine spaetere Ersetzung sie verschiebt."""

    def __init__(self, reparatur=True, konjunktionen=(), protokoll=None, zeilenenden=True):
        self.text, self.reparatur, self.konj, self.p = "", reparatur, set(konjunktionen), protokoll
        self.zeilenenden = zeilenenden

    def _zaehle(self, feld):
        if self.p is not None:
            setattr(self.p, feld, getattr(self.p, feld) + 1)

    def add(self, zeile):
        if not self.zeilenenden:
            # Docling-Weg (REQ-MB-11, Fassung 7): der Elementtext bleibt an Zeilenenden und Strichen
            # unveraendert; nur der weiche Trennstrich im Wort faellt (auf allen Wegen)
            zeile = zeile.replace(SHY, "") if self.reparatur else zeile
            if not zeile.strip():
                return None
            if not self.text:
                self.text = zeile
                return 0
            self.text = self.text + " " + zeile
            return len(self.text) - len(zeile)
        zeile = _zeile_vorbereiten(zeile) if self.reparatur else " ".join(zeile.split())
        if not zeile:
            return None
        links = self.text
        if not links:
            self.text = zeile
            return 0
        if not self.reparatur:
            self.text = links + " " + zeile
            return len(links) + 1
        if links.endswith(SHY):                                     # weicher Trennstrich am Zeilenende
            self._zaehle("trennungen_zusammengefuegt")
            self.text = links[:-1] + zeile
            return len(links) - 1
        if links.endswith("-") and len(links) > 1 and links[-2].isalnum() and zeile[0].isalpha():
            wort = re.match(r"\w+", zeile).group(0)
            if wort.casefold() in self.konj:                        # Ergaenzungsstrich: "Nah- und"
                self._zaehle("strich_behalten")
                self.text = links + " " + zeile
                return len(links) + 1
            if links[-2].isdigit() or zeile[0].isupper():          # "ED4-Regeln", "Zwerg-Krieger"
                self._zaehle("strich_behalten")
                self.text = links + zeile
                return len(links)
            self._zaehle("trennungen_zusammengefuegt")             # "Akti-" + "onswuerfel"
            self.text = links[:-1] + zeile
            return len(links) - 1
        if links.endswith("/"):                                     # "Stufen/" + "Aktionswuerfel"
            self.text = links + zeile
            return len(links)
        self.text = links + " " + zeile                             # gewoehnlicher Umbruch
        return len(links) + 1

    def ergebnis(self):
        return self.text[:-1] if self.text.endswith(SHY) else self.text


def konjunktionen_fuer(sprache="de", konjunktionen=None):
    return tuple(KONJUNKTIONEN.get(sprache, ()) if konjunktionen is None else konjunktionen)


def repariere_trennungen(text, sprache="de", konjunktionen=None, protokoll=None):
    """Zeilen ("\\n") zu einem Text; Trennungen nach der Tabelle in REQ-MB-11, sonst ein Leerzeichen."""
    v = _Verbinder(True, konjunktionen_fuer(sprache, konjunktionen), protokoll)
    for zeile in text.split("\n"):
        v.add(zeile)
    return v.ergebnis()


# ---------- REQ-MB-12: unscharfer Abgleich ----------
def norm(s):
    """NFC, ohne Leerraum und ohne Unicode-Formatzeichen (Cf, u. a. U+00AD, U+200B), casefold."""
    return "".join(ch for ch in unicodedata.normalize("NFC", s or "")
                   if not ch.isspace() and unicodedata.category(ch) != "Cf").casefold()


def auslassungen(zeile, titel):
    """Anzahl Auslassungen, wenn die ganze Zeile aus dem Titel durch Streichen von hoechstens k
    Zeichen entsteht (nur Auslassungen); sonst None. k = 0 unter 6 Zeichen, sonst max(1, n // 10)."""
    z, t = norm(zeile), norm(titel)
    if not t or len(z) > len(t):
        return None
    k = 0 if len(t) < 6 else max(1, len(t) // 10)
    d = len(t) - len(z)
    if d > k:
        return None
    it = iter(t)
    return d if all(ch in it for ch in z) else None


# ---------- Rand und Layout-Merkmale (REQ-MB-20, -28) ----------
def im_rand(zeile, rand, seitenhoehe=None):
    """True/False -- oder None, wenn die Zeile keine Lage hat (gilt dann als nicht im Rand)."""
    if zeile.get("oben") is None or zeile.get("unten") is None:
        return None
    mitte = (zeile["oben"] + zeile["unten"]) / 2
    if rand.get("kopf") is not None and mitte <= rand["kopf"]:
        return True
    if rand.get("fuss") is not None:
        hoehe = zeile.get("seitenhoehe") or seitenhoehe
        if hoehe is None:
            raise KonfigFehler("Fussrand deklariert, aber keine Seitenhoehe bekannt (seitenhoehe angeben).")
        if mitte >= hoehe - rand["fuss"]:
            return True
    return False


def _im_bereich(wert, bereich):
    return wert is not None and bereich[0] <= wert <= bereich[1]


def stufe_der_schrift(schrift, stufen):
    """Kleinste Stufe n (1-basiert), deren Angaben die Schrift alle erfuellt, sonst None."""
    for n, st in enumerate(stufen, 1):
        if "groesse" in st and not _im_bereich(schrift.get("groesse"), st["groesse"]):
            continue
        if any(m in st and bool(schrift.get(m, False)) != bool(st[m]) for m in SCHNITTE):
            continue
        if "laufweite" in st and not _im_bereich(schrift.get("laufweite"), st["laufweite"]):
            continue
        return n
    return None


def _merkmale_ok(zeile, layout):
    n = layout.get("hoechstlaenge")
    return n is None or len(zeile["text"].strip()) <= n


def _schrift_stufe(zeile, layout):
    """5(a): Stufe der zugeordneten Schrift, sonst None."""
    stufen = layout.get("stufen") or []
    schrift = zeile.get("schrift")
    return stufe_der_schrift(schrift, stufen) if stufen and schrift else None


def _rueckfall(zeile, layout):
    """5(b): keine zugeordnete Schrift (oder keine Stufen deklariert) und Ueberschriften-Klasse."""
    if layout.get("stufen") and zeile.get("schrift"):
        return False
    return layout.get("klasse") is not None and zeile.get("klasse") == layout["klasse"]


def layout_stufe(zeile, layout, protokoll=None):
    """Kombinationsregel REQ-MB-20 fuer eine Zeile ausserhalb des Rands, die keinem Listeneintrag
    gehoert (Bedingungen 1 und 3 prueft der Aufrufer): (Stufe, Rueckfall) oder None."""
    if not layout:
        return None
    veto = set(VETO_STANDARD) | set(layout.get("veto") or [])
    merkmale = _merkmale_ok(zeile, layout)
    a = _schrift_stufe(zeile, layout)
    if zeile.get("klasse") in veto:                                   # Bedingung 2
        if a is not None and merkmale and protokoll is not None:
            protokoll.veto_verhindert += 1
        return None
    if not merkmale:                                                  # Bedingung 4
        return None
    if a is not None:                                                 # 5(a): hinreichend
        return a, False
    if _rueckfall(zeile, layout):                                     # 5(b)
        return 1, True
    return None


def _waere_ueberschrift(zeile, layout):
    """Fuer den Rand-Zaehler: traefe 5(a) oder 5(b) zu, wenn die Zeile nicht im Rand laege?"""
    if not layout or zeile.get("klasse") in set(VETO_STANDARD) | set(layout.get("veto") or []):
        return False
    return _merkmale_ok(zeile, layout) and (_schrift_stufe(zeile, layout) is not None or _rueckfall(zeile, layout))


# ---------- Abschnitte (REQ-MB-12, -13, -14, -20, -25, -28) ----------
def baue_abschnitte(seiten, liste=None, layout=None, sprache="de", reparatur=True, protokoll=None,
                    vorspann=None, rand=None, seitenhoehe=None, konjunktionen=None, zeilenenden=True):
    """Seitenzeilen + Ueberschriften-Liste -> [{"abschnittspfad", "text", "seiten", "seitenwechsel"}].

    seiten: {physische Seite: [{"text", "klasse", "schrift"?, "oben"?, "unten"?}, ...]} in Lesereihenfolge
    liste:  [{"titel", "ebene", "seite" (physisch)}] in Listenreihenfolge
    Reihenfolge der Schritte: Rand verwerfen, Listenabgleich, Layout-Ueberschriften auf ZEILEN, erst
    danach die Trennungsreparatur im Text zwischen den Ueberschriften.
    "seiten": physische Seiten des Abschnitts; "seitenwechsel": [[Zeichenoffset, physische Seite]].
    """
    p = protokoll if protokoll is not None else Protokoll()
    layout = layout or {}
    vorspann = rag.titelnorm(vorspann or rag.VORSPANN_STANDARD)            # REQ-MB-33
    konj = konjunktionen_fuer(sprache, konjunktionen)

    # 1. Zeilen in Lesereihenfolge; Randzeilen werden gezaehlt und verworfen (REQ-MB-28)
    zeilen = []
    for s in sorted(seiten):
        for z in seiten[s]:
            if not (z.get("text") or "").strip():
                continue
            if rand:
                lage = im_rand(z, rand, seitenhoehe)
                if lage is None:
                    p.ohne_lage += 1
                elif lage:
                    p.randzeilen += 1
                    if _waere_ueberschrift(z, layout):
                        p.rand_verhindert += 1
                    continue
            zeilen.append((s, z))
    seitenfolge = [s for s, _ in zeilen]

    def seitenanfang(s):
        return bisect.bisect_left(seitenfolge, s)

    # 2. Listenabgleich: je Eintrag (Listenreihenfolge) die beste Zeile seiner Zielseite
    liste = [dict(e, titel=rag.titelnorm(e["titel"])) for e in liste or []]    # REQ-MB-33
    vergeben, gefunden_bei, nicht = {}, {}, {}
    for i, e in enumerate(liste):
        s = e["seite"]
        bewertet = []
        for j in range(seitenanfang(s), bisect.bisect_right(seitenfolge, s)):
            if j in vergeben:
                continue
            d = auslassungen(zeilen[j][1]["text"], e["titel"])
            if d is not None:
                bewertet.append((d, j))
        if bewertet:
            beste = min(d for d, _ in bewertet)
            gleich = [j for d, j in bewertet if d == beste]
            if len(gleich) > 1:
                p.mehrdeutig.append((e["titel"], s))
            vergeben[gleich[0]] = i
            gefunden_bei[i] = gleich[0]
            p.gefunden.append((e["titel"], s))
        else:
            p.nicht_gefunden.append((e["titel"], s))
            davor = [m for m in range(i) if liste[m]["seite"] == s and m in gefunden_bei]
            nicht[i] = gefunden_bei[davor[-1]] if davor else None

    # 2b. Listenueberschriften nach Lage einsortieren (REQ-MB-31) -- der Abgleich lief auf der
    # urspruenglichen Folge, Abschnitte, REQ-MB-13 und -20 arbeiten auf der umsortierten
    reihe = list(range(len(zeilen)))
    for i in range(len(liste)):
        if i in gefunden_bei:
            reihe = _einsortieren(reihe, gefunden_bei[i], zeilen, p)
    neu = {alt: pos for pos, alt in enumerate(reihe)}
    zeilen = [zeilen[k] for k in reihe]
    starts = []
    for i, e in enumerate(liste):
        if i in gefunden_bei:
            starts.append((neu[gefunden_bei[i]], 1, i))
        else:
            starts.append((neu[nicht[i]] + 1 if nicht[i] is not None else seitenanfang(e["seite"]), 0, i))

    # Pfade aus der Liste (Wahrheit fuer ihre Ebenen); eine uebersprungene Ebene bleibt leer
    pfade, stapel = {}, []
    for i, e in enumerate(liste):
        stapel = stapel[:max(1, int(e.get("ebene") or 1)) - 1] + [e["titel"]]
        pfade[i] = list(stapel)

    # 3. Bereiche [start, ende) je Listenabschnitt, davor der Vorspann (REQ-MB-25)
    starts.sort()
    bereiche = []
    if liste:
        erster = starts[0][0] if starts else len(zeilen)
        if erster > 0:
            bereiche.append(([vorspann], None, 0, erster))
        for n, (start, gef, i) in enumerate(starts):
            ende = starts[n + 1][0] if n + 1 < len(starts) else len(zeilen)
            bereiche.append((pfade[i], liste[i]["titel"] if gef else None, start, max(start, ende)))
    else:
        bereiche.append(([], None, 0, len(zeilen)))

    abschnitte = []
    for pfad, titel, start, ende in bereiche:
        rumpf = list(range(start + 1 if titel is not None else start, ende))
        kopfzeile = start if titel is not None else None
        # 4. Layout-Ueberschriften im Listenabschnitt (REQ-MB-20)
        teile, offen = [(pfad, titel, kopfzeile, [])], {}
        for j in rumpf:
            stufe = layout_stufe(zeilen[j][1], layout, p)
            if stufe is None:
                teile[-1][3].append(j)
                continue
            n, rueckfall = stufe
            p.rueckfaelle += rueckfall
            _zaehle(p.layout_ueberschriften, tuple(pfad))
            _zaehle(p.layout_je_stufe, n)
            name = rag.titelnorm(zeilen[j][1]["text"])
            offen = {k: v for k, v in offen.items() if k < n}
            unter = pfad + [offen[k] for k in sorted(offen)] + [name]
            offen[n] = name
            teile.append((unter, name, j, []))
        for upfad, kopf, kj, rj in teile:
            a = _baue_text(upfad, kopf, kj, rj, zeilen, reparatur, konj, p, zeilenenden)
            if a is not None:
                abschnitte.append(a)
    p.abschnitte = len(abschnitte)
    return abschnitte


def _hat_lage(z):
    return all(z.get(k) is not None for k in ("x0", "x1", "oben", "unten"))


def _einsortieren(reihe, j, zeilen, p):
    """REQ-MB-31: Elemente derselben Seite, die VOR der Listenueberschrift j geliefert wurden, aber
    unter ihr liegen (Mittelpunkt unter ihrer Unterkante, waagrecht ueberlappend), hinter j."""
    s, u = zeilen[j]
    if not _hat_lage(u):
        return reihe
    pos = reihe.index(j)

    def darunter(k):
        sk, e = zeilen[k]
        return (sk == s and _hat_lage(e) and (e["oben"] + e["unten"]) / 2 > u["unten"]
                and e["x0"] < u["x1"] and u["x0"] < e["x1"])
    weg = [k for k in reihe[:pos] if darunter(k)]
    if not weg:
        return reihe
    p.umsortiert += len(weg)
    return [k for k in reihe[:pos] if k not in weg] + [j] + weg + reihe[pos + 1:]


def _baue_text(pfad, kopf, kopfzeile, rumpf, zeilen, reparatur, konj, p, zeilenenden=True):
    """Ein Abschnitt: Ueberschrift (Listenform bzw. Layout-Zeile), dann der reparierte Text."""
    wechsel = []

    def seite(j, offset):
        if not wechsel or wechsel[-1][1] != zeilen[j][0]:
            wechsel.append([offset, zeilen[j][0]])

    v = _Verbinder(reparatur, konj, p, zeilenenden)
    for j in rumpf:
        # Zeilenweg: die Zeilenenden eines Elementtexts sind Zeilen fuer die Reparatur (REQ-MB-11)
        stuecke = zeilen[j][1]["text"].split("\n") if zeilenenden else [zeilen[j][1]["text"]]
        for n, stueck in enumerate(stuecke):
            off = v.add(stueck)
            if off is not None:
                seite(j, off)
    rumpftext = v.ergebnis()
    if kopf is None:
        text = rumpftext
    else:
        text = kopf + ("\n" + rumpftext if rumpftext else "")
        verschoben = [[o + len(kopf) + 1, s] for o, s in wechsel]
        wechsel = []
        seite(kopfzeile, 0)
        for o, s in verschoben:
            if wechsel[-1][1] != s:
                wechsel.append([o, s])
    if not text.strip():
        return None
    return {"abschnittspfad": list(pfad), "text": text,
            "seiten": sorted({s for _, s in wechsel}), "seitenwechsel": wechsel}


# ---------- REQ-MB-22: gedruckte Seite ----------
_ARABISCH = re.compile(r"\d+")


def _seitenzahlen(buch, labels, pdf):
    """(gedruckt(physisch), physisch(gedruckt)) aus der Buchdeklaration "seitenzahlen"."""
    decl = buch.get("seitenzahlen")
    if not isinstance(decl, dict):
        raise KonfigFehler(f"Buch {buch['buch_id']!r}: 'seitenzahlen' fehlt ({{\"quelle\": \"labels\"}} oder "
                           "{\"quelle\": \"versatz\", \"versatz\": n}).")
    if decl.get("quelle") == "labels":
        if labels is None and pdf:
            labels = seitenlabels_aus_pdf(pdf)
        if labels is None:
            raise KonfigFehler(f"Buch {buch['buch_id']!r}: Seitenlabels deklariert, aber keine geliefert (PDF?).")
        labels = list(labels)

        def gedruckt(phys):
            lab = labels[phys - 1] if 1 <= phys <= len(labels) else None
            return int(lab) if lab is not None and _ARABISCH.fullmatch(str(lab)) else None

        def physisch(ged):
            return next((i for i in range(1, len(labels) + 1) if gedruckt(i) == ged), None)
    elif decl.get("quelle") == "versatz":
        versatz = decl.get("versatz")
        if not isinstance(versatz, int):
            raise KonfigFehler(f"Buch {buch['buch_id']!r}: 'versatz' muss eine ganze Zahl sein.")

        def gedruckt(phys):
            return phys - versatz if phys - versatz >= 1 else None

        def physisch(ged):
            return ged + versatz
    else:
        raise KonfigFehler(f"Buch {buch['buch_id']!r}: seitenzahlen.quelle {decl.get('quelle')!r} unbekannt "
                           "(labels oder versatz).")
    for phys, soll in (decl.get("kontrollpunkte") or {}).items():
        ist = gedruckt(int(phys))
        if ist != soll:
            raise KonfigFehler(
                f"Buch {buch['buch_id']!r}: Kontrollpunkt physische Seite {phys} -> gedruckt {soll}, die Seitenzahlen "
                f"ergeben {ist}. Die PDF-Labels stimmen nicht -- stattdessen einen Versatz deklarieren "
                "(\"seitenzahlen\": {\"quelle\": \"versatz\", \"versatz\": n}).")
    return gedruckt, physisch


def _liste(buch, lesezeichen, pdf, physisch):
    decl = buch.get("ueberschriften")
    if decl is None:
        return None
    if decl.get("quelle") == "lesezeichen":
        if lesezeichen is None and pdf:
            lesezeichen = lesezeichen_aus_pdf(pdf)
        if lesezeichen is None:
            raise KonfigFehler(f"Buch {buch['buch_id']!r}: Ueberschriften aus Lesezeichen deklariert, aber keine "
                               "geliefert (PDF?).")
        return [dict(e) for e in lesezeichen]
    if decl.get("quelle") == "inhaltsverzeichnis":
        out = []
        for e in decl.get("eintraege") or []:
            phys = physisch(e["seite"])
            if phys is None:
                raise KonfigFehler(f"Buch {buch['buch_id']!r}: Inhaltsverzeichnis-Eintrag {e['titel']!r} nennt die "
                                   f"gedruckte Seite {e['seite']}, die es im Buch nicht gibt.")
            out.append({"titel": e["titel"], "ebene": e.get("ebene", 1), "seite": phys})
        return out
    raise KonfigFehler(f"Buch {buch['buch_id']!r}: ueberschriften.quelle {decl.get('quelle')!r} unbekannt "
                       "(lesezeichen oder inhaltsverzeichnis).")


# ---------- REQ-MB-24: PDF-Lesezeichen und Seitenlabels ----------
def lesezeichen_aus_pdf(pfad):
    """[{"titel", "ebene", "seite" (physisch, 1-basiert)}] in Dokumentreihenfolge; Ebene nach Verschachtelung."""
    from pypdf import PdfReader
    leser = PdfReader(pfad)
    out = []

    def lauf(eintraege, ebene):
        for e in eintraege:
            if isinstance(e, list):
                lauf(e, ebene + 1)
                continue
            seite = leser.get_destination_page_number(e)
            if seite is None or seite < 0:
                continue
            out.append({"titel": e.title, "ebene": ebene, "seite": seite + 1})
    lauf(leser.outline, 1)
    return out


def seitenlabels_aus_pdf(pfad):
    """Label je physischer Seite (Index 0 = Seite 1)."""
    from pypdf import PdfReader
    return list(PdfReader(pfad).page_labels)


# ---------- REQ-MB-23: Versionen gegen das Messergebnis ----------
def pruefe_versionen(buch, docling_version=None, pdfplumber_version=None, vorabmessung=None, protokoll=None):
    """Docling-Einlesen nur mit der gemessenen Docling-Version; Schriftinfo nur mit der gemessenen
    pdfplumber-Version. Fehlt das Messergebnis oder die Version darin: KonfigFehler."""
    stufen = bool((buch.get("layout") or {}).get("stufen"))
    pruefen = [("docling_version", docling_version)] if docling_version is not None else []
    if pdfplumber_version is not None and stufen:
        pruefen.append(("pdfplumber_version", pdfplumber_version))
    if protokoll is not None:
        protokoll.docling_version, protokoll.pdfplumber_version = docling_version, pdfplumber_version
    if not pruefen:
        return
    pfad = vorabmessung or VORABMESSUNG
    if not os.path.exists(pfad):
        raise KonfigFehler(f"Messergebnis {pfad} fehlt -- ohne Vorab-Messung kein Einlesen mit Docling/Schriftinfo "
                           "(REQ-MB-23).")
    with open(pfad, encoding="utf-8") as f:
        messung = json.load(f)
    for feld, version in pruefen:
        soll = messung.get(feld)
        if not soll:
            raise KonfigFehler(f"{pfad} nennt keine {feld} -- der Versionsvergleich ist nicht moeglich.")
        if soll != version:
            raise KonfigFehler(f"{feld} {version!r} weicht von der gemessenen {soll!r} ab ({pfad}). Mit der gemessenen "
                               "Version einlesen oder neu messen.")


# ---------- Einlesen eines Buchs ----------
def _buch(meta, buch_id):
    for b in rag.pruefe_buecher(meta):
        if b["buch_id"] == buch_id:
            return b
    raise KonfigFehler(f"{meta['spiel_id']}: Buch {buch_id!r} ist in spiel.json nicht deklariert.")


def _reparatur(buch):
    r = buch.get("reparatur", False)
    if isinstance(r, dict):
        return bool(r.get("an", True)), r.get("konjunktionen")
    return bool(r), None


def lies_buch_ein(spiel_id, buch_id, seiten, lesezeichen=None, labels=None, data_dir=None, ueberschreiben=False,
                  pdf=None, docling_version=None, vorabmessung=None, pdfplumber_version=None, seitenhoehe=None,
                  protokoll=None, zeilenenden=True):
    """Seitenzeilen eines Buchs -> data/<spiel_id>/buecher/<buch_id>/knowledge.jsonl (+ Einlese-Protokoll).

    Die Buchdeklaration (spiel.json) sagt alles Weitere: "ueberschriften", "seitenzahlen", "layout",
    "rand", "vorspann", "reparatur", "sprache". Bricht etwas ab, wird nichts geschrieben; eine
    vorhandene Buchdatei bleibt ohne ueberschreiben=True stehen (REQ-MB-8).
    zeilenenden=False: Docling-Weg (Elementtexte ohne Zeilenend-Reparatur, REQ-MB-11)."""
    meta = rag.lies_spiel(spiel_id, data_dir)
    if not rag.ist_mehrbuch(meta):
        raise KonfigFehler(f"{spiel_id}: spiel.json deklariert keine 'buecher' -- einlesen.py ist fuer "
                           "Mehr-Buecher-Bestaende.")
    buch = _buch(meta, buch_id)
    pruefe_layout_schema(buch)
    p = protokoll if protokoll is not None else Protokoll()
    pruefe_versionen(buch, docling_version, pdfplumber_version, vorabmessung, p)
    ziel = rag.buch_pfad(spiel_id, buch_id, data_dir)
    if os.path.exists(ziel) and not ueberschreiben:
        raise KonfigFehler(f"{ziel} existiert schon -- zum Ersetzen mit --ueberschreiben (wirkt nur auf {buch_id!r}).")
    gedruckt, physisch = _seitenzahlen(buch, labels, pdf)
    liste = _liste(buch, lesezeichen, pdf, physisch)
    an, konj = _reparatur(buch)
    abschnitte = baue_abschnitte(seiten, liste, layout=buch.get("layout"), sprache=buch["sprache"], reparatur=an,
                                 protokoll=p, vorspann=buch.get("vorspann"), rand=buch.get("rand"),
                                 seitenhoehe=seitenhoehe, konjunktionen=konj, zeilenenden=zeilenenden)
    if not abschnitte:
        raise KonfigFehler(f"{spiel_id}/{buch_id}: kein Abschnitt mit Text -- nichts eingelesen.")
    eintraege = []
    for n, a in enumerate(abschnitte, 1):
        wechsel = [[o, gedruckt(s), s] for o, s in a["seitenwechsel"]]
        eintraege.append({"id": n, "seite": wechsel[0][1], "seite_pdf": wechsel[0][2], "seitenwechsel": wechsel,
                          "text": a["text"], "spiel": meta["name"], "spiel_id": spiel_id, "buch_id": buch_id,
                          "abschnittspfad": a["abschnittspfad"]})
    zaehle_verdacht(eintraege, konjunktionen_fuer(buch["sprache"], konj), p)
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    _schreibe_atomar(ziel, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in eintraege))
    _schreibe_atomar(os.path.join(os.path.dirname(ziel), PROTOKOLL_DATEI),
                     json.dumps(p.als_dict(), ensure_ascii=False, indent=2) + "\n")
    return p


def zaehle_verdacht(eintraege, konj, p):
    """REQ-MB-32: Verdachtsfaelle in den Abschnittstexten (nach der Reparatur, Text unveraendert) --
    Binnen-Grossbuchstabe (Ll gefolgt von Lu) und Strichrest (Buchstabe, "-", Leerzeichen, Wort mit
    Kleinbuchstaben, keine Konjunktion). Seite: gedruckt, sonst physisch."""
    konj = {k.casefold() for k in konj}
    for e in eintraege:
        text, wechsel = e["text"], e["seitenwechsel"]

        def seite(offset):
            w = [x for x in wechsel if x[0] <= offset] or wechsel[:1]
            return w[-1][1] if w[-1][1] is not None else w[-1][2]
        for i in range(len(text) - 1):
            if unicodedata.category(text[i]) == "Ll" and unicodedata.category(text[i + 1]) == "Lu":
                _verdacht(p.binnen_grossbuchstabe, seite(i))
        for m in _STRICHREST.finditer(text):
            wort = m.group(1)
            if unicodedata.category(wort[0]) == "Ll" and wort.casefold() not in konj:
                _verdacht(p.strichrest, seite(m.start()))


_STRICHREST = re.compile(r"(?<=[^\W\d_])- +(\w+)")


def _verdacht(zaehler, seite):
    zaehler["anzahl"] += 1
    if seite not in zaehler["seiten"]:
        zaehler["seiten"].append(seite)
        zaehler["seiten"].sort()


# ---------- REQ-MB-34: Schema der Layout-/Rand-Deklaration ----------
_STUFEN_SCHLUESSEL = ("groesse", "laufweite") + SCHNITTE


def _zahl(w):
    return isinstance(w, (int, float)) and not isinstance(w, bool)


def _bereich(w, name, positiv=False):
    if not (isinstance(w, list) and len(w) == 2 and all(_zahl(x) for x in w) and w[0] <= w[1]):
        raise KonfigFehler(f"Schluessel {name!r}: erwartet [von, bis] aus zwei Zahlen mit von <= bis, nicht {w!r}.")
    if positiv and not w[0] > 0:
        raise KonfigFehler(f"Schluessel {name!r}: 'von' muss groesser als 0 sein, nicht {w[0]!r}.")


def pruefe_layout_schema(buch):
    """Layout- und Rand-Deklaration eines Buchs gegen ihr Schema; Verstoss -> KonfigFehler mit dem Schluessel."""
    wo = f"Buch {buch.get('buch_id')!r}"
    layout = buch.get("layout")
    if layout is not None:
        if not isinstance(layout, dict):
            raise KonfigFehler(f"{wo}: 'layout' muss ein Objekt sein.")
        fremd = sorted(set(layout) - {"klasse", "stufen", "veto", "hoechstlaenge"})
        if fremd:
            raise KonfigFehler(f"{wo}: unbekannter Schluessel {fremd[0]!r} in 'layout'.")
        if "klasse" in layout and not (isinstance(layout["klasse"], str) and layout["klasse"].strip()):
            raise KonfigFehler(f"{wo}: Schluessel 'klasse' muss eine nicht leere Zeichenkette sein.")
        if "veto" in layout and not (isinstance(layout["veto"], list)
                                     and all(isinstance(v, str) and v.strip() for v in layout["veto"])):
            raise KonfigFehler(f"{wo}: Schluessel 'veto' muss eine Liste nicht leerer Zeichenketten sein.")
        if "hoechstlaenge" in layout and not (isinstance(layout["hoechstlaenge"], int)
                                              and not isinstance(layout["hoechstlaenge"], bool)
                                              and layout["hoechstlaenge"] >= 1):
            raise KonfigFehler(f"{wo}: Schluessel 'hoechstlaenge' muss eine ganze Zahl >= 1 sein.")
        if "stufen" in layout:
            stufen = layout["stufen"]
            if not (isinstance(stufen, list) and stufen):
                raise KonfigFehler(f"{wo}: Schluessel 'stufen' muss eine nicht leere Liste sein.")
            for n, st in enumerate(stufen, 1):
                if not isinstance(st, dict) or not st:
                    raise KonfigFehler(f"{wo}: 'stufen' Stufe {n} muss ein Objekt mit mindestens einer Angabe sein.")
                fremd = sorted(set(st) - set(_STUFEN_SCHLUESSEL))
                if fremd:
                    raise KonfigFehler(f"{wo}: unbekannter Schluessel {fremd[0]!r} in Stufe {n} ('stufen').")
                if "groesse" in st:
                    _bereich(st["groesse"], "groesse", positiv=True)
                if "laufweite" in st:
                    _bereich(st["laufweite"], "laufweite")
                for m in SCHNITTE:
                    if m in st and not isinstance(st[m], bool):
                        raise KonfigFehler(f"{wo}: Schluessel {m!r} in Stufe {n} muss true oder false sein.")
    rand = buch.get("rand")
    if rand is not None:
        if not isinstance(rand, dict) or not rand:
            raise KonfigFehler(f"{wo}: 'rand' muss ein Objekt mit 'kopf' und/oder 'fuss' sein.")
        fremd = sorted(set(rand) - {"kopf", "fuss"})
        if fremd:
            raise KonfigFehler(f"{wo}: unbekannter Schluessel {fremd[0]!r} in 'rand'.")
        for k, w in rand.items():
            if not _zahl(w) or w < 0:
                raise KonfigFehler(f"{wo}: Schluessel {k!r} in 'rand' muss eine Zahl >= 0 sein, nicht {w!r}.")


def _schreibe_atomar(pfad, inhalt):
    rag.pruefe_schreibziel(pfad)
    tmp = pfad + ".neu"
    with open(rag.pruefe_schreibziel(tmp), "w", encoding="utf-8") as f:
        f.write(inhalt)
    os.replace(tmp, pfad)


# ---------- REQ-MB-27: Docling-Adapter ----------
def _klasse(item):
    label = getattr(item, "label", None)
    return str(getattr(label, "value", label))


def _text_von(item, doc):
    if _klasse(item) == "table" and hasattr(item, "export_to_markdown"):
        try:
            return item.export_to_markdown(doc=doc)          # Tabellen roh (REQ-MB-23)
        except Exception:  # pragma: no cover - aeltere docling-core
            pass
    return getattr(item, "text", None)


def zeilen_aus_docling(doc, protokoll=None):
    """DoclingDocument -> {physische Seite: [Zeile]} in Lesereihenfolge.

    Text-Kinder eines Bild-Elements (dunkle Kaesten) werden an dessen Stelle uebernommen, genau
    einmal (traverse_pictures=True); das Protokoll zaehlt sie (aus_bildern)."""
    seiten, bild_ebene = {}, None
    for item, ebene in doc.iterate_items(traverse_pictures=True):
        if bild_ebene is not None and ebene <= bild_ebene:
            bild_ebene = None
        klasse = _klasse(item)
        if klasse in BILD_KLASSEN:
            if bild_ebene is None:
                bild_ebene = ebene
            continue
        text = _text_von(item, doc)
        prov = (getattr(item, "prov", None) or [None])[0]
        if not text or not text.strip() or prov is None:
            continue
        zeile = {"text": text, "klasse": klasse}
        _lage_aus_docling(zeile, prov, doc)
        if bild_ebene is not None:
            zeile["aus_bild"] = True
            if protokoll is not None:
                protokoll.aus_bildern += 1
        seiten.setdefault(prov.page_no, []).append(zeile)
    return seiten


def _lage_aus_docling(zeile, prov, doc):
    """bbox (PDF-Punkte, Ursprung oben links wie pdfplumber) und Seitenhoehe, falls vorhanden."""
    bbox, pages = getattr(prov, "bbox", None), getattr(doc, "pages", None)
    if bbox is None or not pages or prov.page_no not in pages:
        return
    hoehe = float(pages[prov.page_no].size.height)
    b = bbox.to_top_left_origin(page_height=hoehe) if hasattr(bbox, "to_top_left_origin") else bbox
    zeile.update(x0=float(b.l), x1=float(b.r), oben=float(b.t), unten=float(b.b), seitenhoehe=hoehe)


# ---------- REQ-MB-29: pdfplumber-Zeichen den Zeilen zuordnen ----------
def schnitt_aus_name(fontname):
    name = (fontname or "").split("+")[-1]
    return {m: bool(rx.search(name)) for m, rx in _SCHNITT_MUSTER.items()}


def _schrift(zeichen):
    """Mehrheitsschrift (Groesse auf 0,1 pt, Schnitt) der Zeichen ohne Leerraum, mit Laufweite;
    ohne absolute Mehrheit None."""
    if not zeichen:
        return None
    gruppen = {}
    for ch in zeichen:
        schnitt = schnitt_aus_name(ch.get("fontname"))
        schluessel = (round(float(ch["size"]), 1),) + tuple(schnitt[m] for m in SCHNITTE)
        gruppen.setdefault(schluessel, []).append(ch)
    schluessel, mehrheit = max(gruppen.items(), key=lambda kv: len(kv[1]))
    if 2 * len(mehrheit) <= len(zeichen):
        return None
    abstaende = []
    for grund in {round(ch["bottom"], 1) for ch in mehrheit}:
        reihe = sorted((ch for ch in mehrheit if round(ch["bottom"], 1) == grund), key=lambda ch: ch["x0"])
        abstaende += [b["x0"] - a["x1"] for a, b in zip(reihe, reihe[1:])]
    schrift = {"groesse": schluessel[0], "laufweite": sum(abstaende) / len(abstaende) if abstaende else 0.0}
    schrift.update(zip(SCHNITTE, schluessel[1:]))
    return schrift


def ordne_schrift_zu(pdf_pfad, seiten, rand=None):
    """Jeder Extraktionszeile die pdfplumber-Zeichen ihrer Seite zuordnen, deren Mitte in ihrem Kasten
    liegt (+-1 pt; mehrere Kaesten: der kleinste). Spaltentreu: ein Zeichen der Nachbarspalte liegt
    nicht im Kasten. Daraus Schrift (Mehrheit) und Lage (oben/unten aus den Zeichen), mit rand
    zusaetzlich "im_rand"."""
    import numpy as np
    import pdfplumber
    out = {}
    with pdfplumber.open(pdf_pfad) as pdf:
        for s in sorted(seiten):
            zeilen = [dict(z) for z in seiten[s]]
            seite = pdf.pages[s - 1]
            hoehe = float(seite.height)
            zeichen = [ch for ch in seite.chars if not ch["text"].isspace()]
            zugeordnet = {i: [] for i in range(len(zeilen))}
            if zeichen:
                cx = np.array([(ch["x0"] + ch["x1"]) / 2 for ch in zeichen])
                cy = np.array([(ch["top"] + ch["bottom"]) / 2 for ch in zeichen])
                beste_flaeche = np.full(len(zeichen), np.inf)
                beste = np.full(len(zeichen), -1)
                for i, z in enumerate(zeilen):
                    if any(z.get(k) is None for k in ("x0", "x1", "oben", "unten")):
                        continue
                    flaeche = (z["x1"] - z["x0"]) * (z["unten"] - z["oben"])
                    drin = ((cx >= z["x0"] - 1) & (cx <= z["x1"] + 1) & (cy >= z["oben"] - 1) & (cy <= z["unten"] + 1)
                            & (flaeche < beste_flaeche))
                    beste_flaeche[drin] = flaeche
                    beste[drin] = i
                for n, i in enumerate(beste):
                    if i >= 0:
                        zugeordnet[int(i)].append(zeichen[n])
            for i, z in enumerate(zeilen):
                chs = zugeordnet[i]
                z["schrift"] = _schrift(chs)
                if chs:
                    z["oben"] = min(ch["top"] for ch in chs)
                    z["unten"] = max(ch["bottom"] for ch in chs)
                z["seitenhoehe"] = hoehe
                if rand:
                    z["im_rand"] = bool(im_rand(z, rand, hoehe))
            out[s] = zeilen
    return out


def lies_pdf_ein(spiel_id, buch_id, pdf=None, data_dir=None, ueberschreiben=False, ausgabe=print):
    """Echter Weg: Docling je Seite -> Zeilen; mit Schriftstufen oder Rand pdfplumber-Zuordnung;
    dann lies_buch_ein. Die Versionen von Docling und pdfplumber werden hier ermittelt und
    durchgereicht -- nur so greift der Vergleich mit dem Messergebnis (REQ-MB-23)."""
    from importlib.metadata import version
    from docling.document_converter import DocumentConverter
    from pypdf import PdfReader
    meta = rag.lies_spiel(spiel_id, data_dir)
    buch = _buch(meta, buch_id)
    pruefe_layout_schema(buch)
    pdf = pdf or os.path.join(rag.PDF_DIR, buch["quelle"])
    if not os.path.exists(pdf):
        raise KonfigFehler(f"Quelldatei {pdf} fehlt (--pdf angeben).")
    layout = buch.get("layout") or {}
    mit_schrift = bool(layout.get("stufen") or buch.get("rand"))
    docling_version = version("docling")
    pdfplumber_version = version("pdfplumber") if mit_schrift else None
    p = Protokoll()
    pruefe_versionen(buch, docling_version, pdfplumber_version, None, p)     # vor der teuren Konvertierung
    ziel = rag.buch_pfad(spiel_id, buch_id, data_dir)
    if os.path.exists(ziel) and not ueberschreiben:
        raise KonfigFehler(f"{ziel} existiert schon -- zum Ersetzen mit --ueberschreiben.")
    konverter = DocumentConverter()
    seiten = {}
    n = len(PdfReader(pdf).pages)
    for s in range(1, n + 1):
        doc = konverter.convert(pdf, page_range=(s, s)).document
        for k, zeilen in zeilen_aus_docling(doc, protokoll=p).items():
            seiten.setdefault(k, []).extend(zeilen)
        if s % 25 == 0:
            ausgabe(f"  Docling: Seite {s}/{n}")
    if mit_schrift:
        seiten = ordne_schrift_zu(pdf, seiten, rand=buch.get("rand"))
    return lies_buch_ein(spiel_id, buch_id, seiten, data_dir=data_dir, ueberschreiben=ueberschreiben, pdf=pdf,
                         docling_version=docling_version, pdfplumber_version=pdfplumber_version, protokoll=p,
                         zeilenenden=False)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    ueberschreiben = "--ueberschreiben" in argv
    argv = [a for a in argv if a != "--ueberschreiben"]
    pdf = None
    if "--pdf" in argv:
        i = argv.index("--pdf")
        if i + 1 >= len(argv):
            print("--pdf braucht einen Pfad.", file=sys.stderr)
            return 2
        pdf = argv[i + 1]
        del argv[i:i + 2]
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        p = lies_pdf_ein(argv[0], argv[1], pdf=pdf, ueberschreiben=ueberschreiben)
    except KonfigFehler as e:
        print(f"ABBRUCH (Konfiguration): {e}", file=sys.stderr)
        return 2
    d = p.als_dict()
    print(f"Abschnitte {d['abschnitte']}; Liste gefunden {len(d['gefunden'])}, nicht gefunden "
          f"{len(d['nicht_gefunden'])}, mehrdeutig {len(d['mehrdeutig'])}; Layout je Stufe {d['layout_je_stufe']}, "
          f"Rueckfaelle {d['rueckfaelle']}, nur wegen Rand {d['rand_verhindert']}, nur wegen Veto "
          f"{d['veto_verhindert']}; Randzeilen {d['randzeilen']}; aus Bildern {d['aus_bildern']}; Trennungen "
          f"zusammengefuegt {d['trennungen_zusammengefuegt']}, Strich behalten {d['strich_behalten']}; Docling "
          f"{d['docling_version']}, pdfplumber {d['pdfplumber_version']}")
    for titel, seite in d["nicht_gefunden"]:
        print(f"  nicht gefunden: {titel!r} (Seite {seite})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
