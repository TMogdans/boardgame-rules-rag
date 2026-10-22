# Vorab-Messung REQ-MB-23 (Spec-Fassung 6)

Messergebnis: `vorabmessung.json` (nur Zahlen und Versionen, REQ-MB-18). Gemessen am
2026-10-21 am Zielbuch (Spielerhandbuch ED4, 3. Aufl., 314 S., physische Seite = gedruckte + 1).
Kein Buchtext in diesem Ordner; Talentnamen stehen nur als Beispiele.

## Werkzeuge

- Docling 2.131.0 (docling-core 2.99.0, docling-ibm-models 4.0.3, docling-parse 7.22.1,
  torch 2.14.0, transformers 5.17.0, MPS), `DocumentConverter()` mit Standard-Pipeline, je Seite
  `convert(pdf, page_range=(p, p))`, Elemente über `iterate_items(traverse_pictures=True)` (REQ-MB-27).
- pdfplumber 0.11.10 (pdfminer.six 20260107), `page.chars`. In `.venv-ingest` nachinstalliert;
  dabei kamen nur pdfplumber, pdfminer.six, cryptography, cffi, pycparser hinzu, die Docling-/Torch-
  Pakete blieben unverändert (pip-Liste vorher/nachher verglichen).
- Wegwerf-Prototyp der Kombinationsregel REQ-MB-20 und der Zeichenzuordnung REQ-MB-29 (außerhalb
  des Repos, nicht Teil der Implementierung).

## Buchdaten (aus Messungen abgeleitet)

**Seitenformat:** alle 314 Seiten 595,28 × 841,89 pt.

**Kopf- und Fußrand** (Histogramm der vertikalen Zeichenmittelpunkte über alle 314 Seiten):

| | gemessen | deklariert |
|---|---|---|
| Kopf: Kolumnentitel (Requiem 16/18 pt) | Mittelpunkt 4,7–22,6 pt von oben | |
| Kopf: nächstes Zeichen darunter | 50,0 pt (nur Rückseite S. 314), Satzspiegel ab ≈ 76 pt | **Kopfrand 36 pt** |
| Fuß: Seitenzahlen (Requiem 12 pt) | 16,7 pt von unten (309 Seiten); Rückseite bis 20,5 pt | |
| Fuß: unterstes Satzspiegel-Zeichen | 29,2 pt von unten | **Fußrand 25 pt** |

Beide Werte liegen in der Mitte der gemessenen Lücke (22,6 → 50,0 bzw. 20,5 → 29,2).

**Schrift je Zeile** (REQ-MB-20/-29): Zeichen ohne Leerraum, die ihren Mittelpunkt in der
Docling-bbox einer Zeile haben (± 1 pt; bei mehreren Treffern die kleinste bbox; Elemente mit
mehreren bboxen auf der Seite: Vereinigung). Schrift = (Größe auf 0,1 pt, Schnitt) der absoluten
Mehrheit der Zeichen, sonst keine Schrift. Schnitt aus dem Schriftnamen als Merkmalsmenge:
`fett` (Bold/Semibold/Heavy/Black), `kursiv` (Italic/Oblique), `kapitaelchen` (SC…), sonst
`normal`. Laufweite = mittlerer Abstand aufeinanderfolgender Mehrheitszeichen derselben Grundlinie.
Lage = Mitte aus oberster und unterster Zeichenkante, ohne Zeichen aus der Docling-bbox.
Zugeordnet: 143.930 von 143.944 Zeichen der Talentseiten.

**Histogramm der Zeilenschriften** auf den Talentseiten (1.196 Docling-Zeilen):

| Schrift (Größe, Schnitt) | Zeilen | davon Klasse `section_header` | Inhalt |
|---|---|---|---|
| 10,0 normal | 552 | 4 | Fließtext; 4 Tabellentitel |
| 10,0 fett | 317 | 0 | Werteblock-Zeilen |
| **7,0 fett+kapitaelchen** | **149** | 147 | **Talentnamen** (Kapitälchen: Versalien 10 pt, Rest 7 pt) |
| 12,0 normal | 32 | 0 | Seitenzahlen (im Fußrand) |
| 16,0 normal | 32 | 32 | 30 Kolumnentitel (im Kopfrand), 2 Kastentitel |
| 10,0 kursiv | 22 | 0 | Beispieltexte |
| 18,0 normal | 16 | 0 | Kapitelnummer im Kopfrand |
| 8,5 / 8,0 / 9,0 normal | 14 | 0 | Tabellen, Fußnoten, Kastentext |
| **7,0 fett+kapitaelchen+kursiv** | **5** | 5 | **Zwischenüberschriften in Talenten** |
| 20,0 normal | 1 | 1 | Listenüberschrift „Talentbeschreibungen" (S. 76) |
| keine Schrift (Gleichstand) | 56 | 0 | Werteblock-Zeilen mit gleich vielen fetten und normalen Zeichen |

Laufweite der beiden Stufen 0,00–0,29 pt; sie wird nicht gebraucht und nicht deklariert.

**Deklaration für das Buch:**

- Schriftstufe 1 (Talentname): Größe 6,5–7,5 pt, Schnitt `fett+kapitaelchen`.
- Schriftstufe 2 (Zwischenüberschrift im Talent): Größe 6,5–7,5 pt, Schnitt `fett+kapitaelchen+kursiv`.
- Überschriften-Klasse für den Rückfall: `section_header`.
- Veto-Menge: Default (`table`, `caption`, `page_header`, `page_footer`) ohne Ergänzung.
- Zeilenmerkmale: keine.

## H — über alle Talentseiten (physisch 76–107)

Kombinationsregel REQ-MB-20 genau wie in der Spec (Bedingungen 1–5; eine Zeile ohne Lage gilt
als nicht im Rand; Listenzuordnung: die Zeile „Talentbeschreibungen" auf S. 76 ist dem Lesezeichen
zugeordnet, Bedingung 3).

- **Anker:** Docling-Element der Klasse `text`, das mit „Stufe:" beginnt → 148 Talente.
- **Von Hand geprüft:** 1 Talent (S. 96, „Reittier Panzern": Werteblock als `table`, Anker greift
  nicht) → gegen Seitenbild geprüft, ist ein Talent.
- **Gegenprobe ohne Docling:** pdfplumber-Anker (fettes „Stufe:" 10 pt, darüber ≤ 20 pt in
  derselben Spalte genau eine Zeile in Kapitälchen fett) → 149 Talente, 0 mehrdeutig, 0
  Kapitälchen-Namen ohne Anker.
- **vorhanden** = 149; **erkannt** = 149 (jeder Talentname Überschrift der Stufe 1, Zuordnung über
  die Zeichen des Namens); **fehltreffer** = 0.
- Darunter die 2 Talentnamen, die Docling als `text` statt `section_header` liefert (S. 94
  „Luftsegeln", S. 97 „Rüstung Schmieden"): erkannt nach 5(a).
- **Zwischenüberschriften Stufe 2:** 5 (S. 85: 1, S. 93: 1, S. 106: 3), alle gegen die Seitenbilder
  geprüft: Zwischenüberschriften innerhalb eines Talents, keine Fehltreffer.
- **Protokoll-Zähler:** Stufe 1 = 149, Stufe 2 = 5, Rückfall 5(b) = 0, nur wegen Rand = 0, nur
  wegen Veto = 0. Zeilen im Rand insgesamt (Verwerfen nach REQ-MB-28): 78.
- Nicht Überschrift wegen Schrift außerhalb aller Stufen, obwohl `section_header`: 30
  Kolumnentitel (zusätzlich im Rand), 4 Tabellentitel, 2 Kastentitel.

Vergleich und Mutationsproben (Prototyp gezielt verfälscht, gleiche Daten):

| Variante | erkannt | Fehltreffer Stufe 1 |
|---|---|---|
| Regel wie deklariert | 149 | 0 |
| ohne Schriftstufen (Klasse allein, mit Rand und Veto) | 147 | 11 |
| Stufen ohne Schnitt (nur Größe) | 149 | 5 |
| Zeichenzuordnung ohne Spaltentrennung (nur vertikale Lage) | 31 | 75 |
| Rand aus | 149 | 0 |
| Veto aus | 149 | 0 |
| `traverse_pictures=False` (Bild-Kinder entfernt) | 149 | 0 |

Rand und Veto sind auf den Talentseiten nicht tragend: die Kolumnentitel und Tabellen haben keine
Schrift der Stufen. Tragend sind Stufen, Schnitt und die spaltentreue Zeichenzuordnung.

## L und T — 10 Stichprobenseiten

Zählregeln wie in der ersten Messung: Absatz = Fließtextabsatz, Beispielabsatz, Absatz in einem
Textkasten, Aufzählungspunkt; eine zentrierte Zeilenfolge ohne Leerzeile = 1 Absatz. Keine Absätze:
Überschriften, Werteblöcke, Fußnoten, Tabellen samt Titel, Kolumnentitel, Seitenzahlen. Ein Absatz
über eine Spaltengrenze ist einer. Richtig = vollständig vorhanden und an der richtigen Stelle nach
dem vorangehenden Absatz (Spalte für Spalte, Kästen an ihrer Stelle im Fluss); fehlend = nicht
richtig. T = Tabellenzeilen in einem Fließtext-Element.

| Seite (physisch) | zweispaltig + Tabelle | richtig / Absätze | T |
|---|---|---|---|
| 19 | ja | 10 / 10 | 0 |
| 21 | | 13 / 13 | 0 |
| 22 | ja | 13 / 13 | 0 |
| 77 | | 9 / 9 | 0 |
| 79 | | 12 / 12 | 0 |
| 122 | | 9 / 9 | 0 |
| 223 | | 10 / 10 | 0 |
| 228 | ja | 12 / 12 | 0 |
| 231 | ja | 8 / 8 | 0 |
| 245 | | 18 / 18 | 0 |
| **Summe** | 4 | **114 / 114** | **0** |

Kastentexte: S. 21 (dunkler Kasten, in der ersten Messung 3 fehlende Absätze) liefert mit
`traverse_pictures=True` die drei Kastenabsätze und den Kastentitel als Kinder des Bild-Elements,
direkt nach dem Element davor und vor der nächsten Überschrift. Bekannt und unverändert (Spec 2):
die Tabelle auf S. 22 steht hinter allen Absätzen der Seite. Seitenzahlen und Kolumnentitel stehen
teils als Bild-Kinder oder mitten in der Folge (S. 223, 228, 231) — sie liegen im Rand.

## Ziele

| Zahl | Ziel | gemessen | |
|---|---|---|---|
| L | ≥ 95 % | 114/114 = 100 % | erfüllt |
| T | 0 | 0 | erfüllt |
| H erkannt | alle | 149/149 | erfüllt |
| H Fehltreffer | 0 | 0 | erfüllt |

## Laufzeit je Seite (40 Seiten, MPS)

Modell-Initialisierung einmalig 2,0 s. Docling typisch (Median) 0,31 s, Maximum 3,40 s (erste
Seite des Laufs, Aufwärmen; zweithöchste 0,82 s). pdfplumber `page.chars` typisch 0,06 s, Maximum
0,29 s. Zuordnung + Regel typisch 0,019 s, Maximum 0,023 s. Gesamt je Seite typisch 0,39 s,
Maximum 3,69 s (erste Seite), ohne erste Seite 0,87 s.

## Unabhängige Nachzählung

Ein frischer Subagent (Sonnet) bekam nur Seitenbilder und Docling-Folge der Seiten 94, 96, 97
(H-Abweichungen) und 21, 22 (L), nicht diese Zahlen.

- H: S. 94 5 Talente, S. 96 6, S. 97 3 (Anker-Zählung: 5 / 6 / 3). Werteblock als `table` genau
  bei „Reittier Panzern" (S. 96); Talentnamen als `text` genau bei S. 94 „Luftsegeln" und S. 97
  „Rüstung Schmieden"; keine fehlenden Talentnamen, keine Zwischenüberschriften auf diesen Seiten.
- L: S. 21 13/13, S. 22 13/13; Kastentext S. 21 an der richtigen Stelle; T = 0 auf beiden Seiten.
- Abweichungen zur eigenen Zählung: 0.
