# Vorab-Messung Spec 2 (Einlesequalität), Fassung 1

Gemessen am 2026-10-22 am Zielbuch (Spielerhandbuch ED4, 3. Aufl., 314 S., physische Seite =
gedruckte + 1). Zahlen in `vorabmessung.json`. In diesem Ordner steht kein Buchtext; Abschnittsnamen
und Wortpaare stehen nur als Stichworte da. Die Seitenangaben sind physisch.

## Werkzeuge und Weg

- Docling 2.131.0 und pdfplumber 0.11.10 (`.venv-ingest`), dieselben Versionen wie in Spec 1.
- Einlese-Weg wie `einlesen.lies_pdf_ein`: Docling je Seite (`convert(pdf, page_range=(p, p))`),
  `zeilen_aus_docling` (Bild-Kinder inklusive), `ordne_schrift_zu`, `lies_buch_ein(zeilenenden=False)`.
  Die Deklaration ist die aus Spec 1 (Lesezeichen, Versatz 1, Rand 36/25 pt, zwei Schriftstufen).
  Ergebnis: **539 Abschnitte**, 144/148 Lesezeichen gefunden, Stufe 1 = 386, Stufe 2 = 5, 718
  Randzeilen. Die Zahlen gleichen dem Spec-1-Stand (Bekannte Grenzen G4: 539 Abschnitte), der Weg ist
  also reproduziert.
- Die Kandidatenregeln sind Wegwerf-Prototypen außerhalb des Repos. Sie arbeiten auf denselben
  Zeilen und rufen `einlesen.baue_abschnitte` unverändert auf.
- **Zuordnung Element → Abschnitt:** Jede Zeile bekommt vor dem Lauf eine Marke aus
  Unicode-Formatzeichen (U+2063, U+200B, U+200C). `norm()` entfernt diese Zeichen, deshalb ändern
  die Marken weder den Listenabgleich noch die Schriftstufen. Nach dem Lauf werden die Marken aus den
  Abschnittstexten gelesen. Damit ist für jede Zeile bekannt, in welchem Abschnitt sie landet: mit
  Docling-Folge und mit Kandidatenregel. Listenüberschriften verschwinden dabei aus dem Text (sie
  werden durch den Listentitel ersetzt). Man erkennt sie daran, dass ihre Marke fehlt.
- **Urteil „besser/schlechter":** Jeder Abschnittswechsel wurde von Hand am Seitenbild (60 dpi) und
  an der Elementliste der Seite beurteilt. Maßstab: Folgt der Text dem Satzfluss der Seite (Spalte für
  Spalte, Fortsetzung über den Spaltenwechsel)? Steht ein Element unter der Überschrift, zu der es
  inhaltlich gehört?

## 1. Spaltenraster

Grundlage sind die Zeilen des 10-pt-Fließtexts (pdfplumber, Satzspiegel 76–812 pt, Segmente an
Lücken über 15 pt getrennt), auf allen 314 Seiten:

| | linke Spalte | rechte Spalte |
|---|---|---|
| Zeilenanfang x0 (Spitze) | 35 pt (9.292 Zeilen), Einzug 44 (1.978) | 304 pt (6.873), Einzug 312 (1.922) |
| Zeilenende x1 (Spitze) | 292 pt (6.422) | 560 pt (6.873) |

- Gerade und ungerade Seiten haben dasselbe Raster (getrennt gezählt). Die Spaltenlücke liegt bei
  292–304 pt.
- 294 Seiten sind rein zweispaltig (weniger als 0,5 % der Fließtextzeichen mit Mitte in der Lücke).
  10 Seiten haben keinen Fließtext. 10 Seiten sind gemischt: S. 10, 58, 72, 268, 307–311 und 313
  (Index, Zierseiten).
- Docling-Kästen im Satzspiegel, nach dem Raster mit 4 pt Toleranz eingeteilt (erster Kasten eines
  Elements): links 3.738, rechts 3.289, spaltenübergreifend 426 (213 Text, 129 `section_header`,
  56 `list_item`, 23 Tabellen, 5 Fußnoten).
- **Deklaration für das Buch:** Spalten `[[35, 292], [304, 560]]`, Toleranz 4 pt.

## 2. Lesereihenfolge: Rasterregel

**Kandidat:**
- Je Seite liegen Bänder zwischen den spaltenübergreifenden Elementen (sortiert nach Oberkante des
  ersten Kastens).
- In jedem Band kommt zuerst die linke Spalte, dann die rechte, jeweils nach Oberkante. Bei gleicher
  Oberkante bleibt die Docling-Folge.
- Danach folgt das trennende spaltenübergreifende Element.
- Randzeilen bleiben, wo sie sind (sie werden ohnehin verworfen). Bild-Elemente sind keine
  Bandgrenze.

| Zahl | Docling-Folge | Rasterregel |
|---|---|---|
| Seiten mit anderer Elementfolge | – | 100 (ohne Werteblock-Zeilen: 55) |
| Elemente in einem anderen Abschnitt | – | 58 |
| Abschnitte mit anderer Elementmenge (alt / neu) | – | 21 / 20 |
| beteiligte Abschnitte (verlieren oder gewinnen Elemente) | – | 25 auf 11 Seiten |
| Abschnittsköpfe, die nach Inhalt kommen, der auf der Seite darunter liegt | 3 (S. 76, 114, 190) | 0 |
| Tabelle in einem fremden Abschnitt | 1 (S. 22) | 0 |
| Abschnitte / Liste gefunden / Stufe 1 / Stufe 2 | 539 / 144 / 386 / 5 | 539 / 144 / 386 / 5 |

**Urteil je Seite mit Abschnittswechsel (alle 11 beurteilt):**

| Seite | Elemente | Befund (Docling) | Rasterregel |
|---|---|---|---|
| 22 | 1 | Tabelle am Seitenende, unter der letzten Überschrift statt unter ihrer eigenen | besser |
| 37 | 1 | Kopf der rechten Spalte (Fortsetzung des Kapitelvorspanns) unter der nächsten Kapitelüberschrift | besser |
| 53 | 6 | Kasten füllt die linke Spalte, Kapitelüberschrift steht oben rechts; Docling: Kasten unter der neuen Überschrift, Raster: unter dem vorigen Unterabschnitt | **strittig** |
| 76 | 7 | spaltenübergreifende Listenüberschrift nach dem ersten Talent; Raster: Talent unter „Talentbeschreibungen" (149 statt 148) | besser |
| 94 | 2 | Text rechts neben einem Bild über beide Spalten: Fortsetzung des letzten Talents der linken Spalte | besser |
| 100 | 3 | links schmaler Text neben einem Bild und Kopf der rechten Spalte falsch einsortiert | besser |
| 114 | 12 | Listenüberschrift nach dem ersten Eintrag („Alchemie" im vorigen Kapitel) | besser |
| 172 | 1 | Fortsetzung oben links erst am Seitenende geliefert | besser |
| 177 | 10 | drei Zauber neben einem Bild im Wechsel zwischen den Spalten falsch zugeordnet | besser |
| 190 | 11 | rechte Spalte oben (Zauber des vorigen Kapitels) als Bild-Kind erst am Seitenende | besser |
| 191 | 4 | Folge von S. 190: Fortsetzung unter dem falschen Zauber | besser |

Bilanz: **10 Seiten besser, 1 strittig (S. 53), 0 schlechter**. Nach Abschnitten: 23 besser,
2 strittig (beide auf S. 53). Thematisch passt der Kasten auf S. 53 eher zur neuen Überschrift. Nach
dem Maßstab dieser Messung zählt er deshalb als möglicher Schaden.

**Innere Umstellung** (Elementmenge eines Abschnitts gleich, Folge anders): 193 Abschnitte.
- 156 davon betreffen nur Werteblock-Zeilen (`Schlüssel: Wert`). Im 2×2-Werteblock liest Docling
  spaltenweise, die Rasterregel zeilenweise. Die Paare bleiben dabei ganz; das ist gleichwertig.
- 37 Abschnitte betreffen anderes. Bei 25 davon springt Docling innerhalb eines Bands zwischen den
  Spalten zurück (links → rechts → links auf derselben Seite). Stichprobe S. 27, 121, 293: Die
  Docling-Folge zerreißt Absätze über die Spalten, die Rasterregel ist besser.
- 12 Abschnitte sind nicht beurteilt.

**Neben Bildern:**
- 154 Seiten tragen ein Inhaltsbild. Die Rasterregel ändert die Folge auf 35 dieser Seiten (22,7 %),
  auf den Seiten ohne Bild auf 20 (12,6 %). Gezählt ist jeweils ohne Werteblock-Zeilen.
- Abschnittswechsel neben Bildern gibt es auf S. 37, 53, 76, 94, 100, 172, 177, 190 und 191.

**Variante „Kasten behält Docling-Stelle"** (Läufe von Elementen, die beidseitig mindestens 12 pt
eingerückt sind): S. 53 bleibt dabei unverändert. Neu falsch wird aber S. 20. Die schmale zentrierte
Überschrift dort gilt als Kasten, und eine Tabelle wandert in den nächsten Abschnitt. Das ist dieselbe
Falle wie bei REQ-MB-31. Die Variante ist verworfen.

**Laufzeit:** Rasterregel je Seite typisch 0,018 ms, Maximum 0,171 ms.

## 3. Striche

**Zeilenend-Striche der Quelle:**
- Grundlage sind pdfplumber-Zeilen je Spalte, deren letztes Wort auf Buchstabe oder Ziffer + `-`
  endet, und die nächste Zeile derselben Spalte (höchstens 20 pt tiefer).
- Gezählt ist, was im Abschnittstext dieser und der nächsten Seite steht.
- Klassen wie in REQ-MB-11.

| Klasse (Quelle) | im Häppchen richtig | falsch |
|---|---|---|
| Großbuchstabe folgt (echter Bindestrich) | 38 Strich behalten | 20 zusammengezogen, 5 nicht gefunden |
| Ziffer davor | – | 2 zusammengezogen |
| Konjunktion folgt (Ergänzungsstrich) | 5 `X- und` | 4 zusammengezogen |
| Kleinbuchstabe folgt (Silbentrennung) | 4.616 zusammengefügt | 28 `Ver- teidigung`-Form, 9 Leerzeichen ohne Strich, 1 nicht gefunden |
| am Spalten- oder Seitenende | – | 67 (Fortsetzung in einem anderen Element) |

Echte Striche: 69, davon **26 zusammengezogen**. Das bestätigt die Spec-1-Zahl (26 von 69).
Silbentrennung ist zu 99,2 % richtig (4.616 von 4.654 gefundenen Fällen).

**Regel „Zeilenende aus der Quelle"** (Prototyp):
- Je Fall wird die Sollform nach der MB-11-Tabelle in den Abschnittstext der Seite gesetzt.
- Das geschieht nur, wenn die Docling-Form genau einmal und an Wortgrenzen vorkommt und die Sollform
  noch nicht dasteht.
- Ergebnis: **59 Stellen in 49 Abschnitten**. Davon 40 Striche wiederhergestellt (z. B.
  `NovizenTalent`, Probe-Komposita, 2 Würfel-Komposita mit Ziffer, 3 Ergänzungsstriche vor `und`/`oder`), 11
  `X- y`-Formen und 8 `X y`-Formen zusammengefügt.
- Alle 59 einzeln gelesen: **59 besser, 0 schlechter**.
- Verdachtszähler REQ-MB-32 danach: Binnen-Großbuchstabe 63 → 28, Strichrest 50 → 39.

**Strich am Elementende:**
- 36 Elemente enden auf Buchstabe + `-`.
- Das nächste Element der Docling-Folge beginnt in 30 Fällen klein, in 5 groß, in 1 mit Konjunktion.
- Mit der Rasterregel: 31 / 4 / 1.

**Regel „Strichrest im Text"** (verbleibendes `X- y` mit kleinem `y`, keine Konjunktion → `Xy`):
- 39 Stellen in 32 Abschnitten: 33 besser, 1 ungeklärt (S. 284).
- **5 schlechter** mit der heutigen Konjunktionsliste: 4 × Ergänzungsstrich vor `als` (sowohl … als
  auch), 1 × vor `beziehungsweise`.
- Mit beiden Wörtern in der Konjunktionsliste des Buchs: 0 schlechter.
- Strichrest danach 0.

**Prototyp „Elementtext ganz aus pdfplumber"** (Zeichen im Docling-Kasten, Zeilen nach Grundlinie,
Leerzeichen bei einer Lücke über 0,25 × Schriftgröße, Zeilen mit der MB-11-Reparatur verbunden):
- 6.037 Text-Elemente, davon 5.819 mit gleicher Wortfolge und 218 anders.
- Stichprobe 12: 7 besser (Striche, Trennungen, Listennummern), 2 schlechter (Kapitälchen zerfallen in
  Buchstaben, S. 20), 3 nur andere Wortfolge (Initialen).
- Nicht als Regel geeignet: Der Prototyp bringt eigene Fehler mit.

## 4. Zierschrift-Umlaut (G5)

- Docling liefert auf 4 Zeilen einen Umlaut als Grundvokal mit zwei abgesetzten Punkten
  (`U . . ber`, `Fu . . r`, `…wu . . rfel`), dazu einmal mit den Punkten am Wortende (S. 216). Die
  Zeilen stehen auf S. 9, 10, 20 und 216.
- Regel „Vokal + ` . .` → Umlaut": 4 Abschnitte ändern sich, **4 besser, 0 schlechter**.
- Lesezeichen gefunden 144 → 146 (S. 9, 10). Auf S. 9 beginnt „Über dieses Buch" jetzt an der
  Überschrift statt am Seitenanfang.
- Nicht lösbar sind S. 1 (Titelseite ohne Textzeile) und S. 216: Dort sind die Punkte ans Wortende
  gerückt, und Lesezeichen und Zeile unterscheiden sich in Ein- und Mehrzahl.

## 5. Zeichentreue

- **Steuerzeichen:** Die Häppchen enthalten 739 × U+0007, in 241 Abschnitten auf 78 Seiten.
  Docling setzt es für einen doppelten Leerraum in Werteblöcken (nach `Wirkung:` vor dem Wert). In der Quelle
  steht dort Leerraum.
- **Gedankenstriche:** In der Quelle stehen 657 × U+2013 und 34 × U+2014, in den Häppchen keiner.
  Docling setzt `-`. Die 115 Aufzählungspunkte U+2022 der Quelle stehen in den Häppchen nicht als
  U+2022.

## 6. Zahlentreue (ganzes Buch)

- Ziffernfolgen der Quelle (pdfplumber-Wörter ohne Rand, `\d+`) je Seite, verglichen mit denen im
  Abschnittstext dieser Seite (Seitenwechsel aus `seitenwechsel`, ohne Titelvorsatz).
- Quelle: **8.490**.

| | Anzahl | Ursache |
|---|---|---|
| fehlend, Wert auf der Seite gar nicht im Häppchen | 178 | 150 Inhaltsverzeichnis S. 3/4 (Docling-Klasse `document_index` ohne Text); 24 Listennummern auf S. 37, 130, 139, 221, 225 (Docling hält die Nummer in `marker`, S. 139: 5 von 5); 4 auf S. 117 (zwei Zeilen am Spaltenende fehlen) |
| fehlend, seltener als in der Quelle | 21 | |
| zusätzlich, Wert kommt auf der Seite nicht vor | **1** | S. 313 |
| zusätzlich, vervielfacht | 819 | Tabellen-Markdown wiederholt Spannzellen (S. 49, 300–306); Tabelle doppelt (S. 20) |

**Text ohne Docling-Kasten:** 7.255 von 1.153.626 Zeichen (0,63 %). Davon entfallen 7.144 auf
S. 3/4 (Inhaltsverzeichnis), 108 auf S. 117 und 3 auf S. 14.

## 7. Tabellen

| Zahl | Wert |
|---|---|
| Docling-Tabellen | 79 auf 58 Seiten; 1.196 Rasterzeilen, 5.741 Zellen (455 leer) |
| Lage (Kasten ganz links bzw. rechts von x = 298 pt) | 21 links, 35 rechts, 23 spaltenübergreifend |
| Markdown-Text | 261.238 Zeichen = 17,0 % des Abschnittstexts (1.535.444); ohne Füll-Leerzeichen 95.127 (−63,6 %) |
| Länge je Tabelle | typisch 1.361, Maximum 27.521 (Index S. 307–313 je Seite als eine Tabelle); 52 von 79 länger als `CHUNK_SIZE` 800 |
| Häppchen (800/150, nachgerechnet mit `rag.zerteile`) | 2.638 gesamt; **366 mit Tabellenteil, 316 davon ohne Tabellenkopf** |
| dasselbe ohne Füll-Leerzeichen | 2.383 / 186 / 131 |
| Spannzellen im Raster doppelt | 50 Tabellen, 271 Zellen |
| Zahlen im Tabellenkasten | Quelle 3.498, Markdown 4.156: 7 fehlen (S. 40: 6, S. 308: 1), 665 zusätzlich (vervielfacht) |
| Tabelle doppelt (Tabelle + Bild-Kinder im selben Kasten) | 1 (S. 20, 41 Bild-Kinder) |
| Tabelle in einem fremden Abschnitt | 1 (S. 22; Rasterregel behebt) |
| Werteblock als Tabelle | 4 (S. 96, 117, 118 zweimal) |
| Zeilen-Schablone `Kopf: Wert; …` (erste Rasterzeile als Kopf, Spannzellen einmal) | 1.117 Zeilen, Länge typisch 85, p95 177, Maximum 712; 938 Zeilen höchstens 150 Zeichen lang (`CHUNK_OVERLAP`) |

## 8. Werteblöcke

- Schlüssel-Wert-Paare der Quelle: fetter 10-pt-Schlüssel, der auf `:` endet, dazu die folgenden
  nicht-fetten Wörter derselben Zeile (auch hinter einer Tabulatorlücke). Gezählt sind Schlüssel mit
  mindestens 30 Vorkommen (15 Schlüssel). Das ergibt 149 Talente, 216 Zauber und rund 25
  Fertigkeiten.
- Ein Paar ist **intakt**, wenn `Schlüssel Wert` (normalisiert) im Text der Seite steht.

| | Anzahl |
|---|---|
| Paare | 2.652 |
| intakt | **2.620 (98,8 %)** |
| getrennt: Docling legt zwei Zellen eines Fertigkeiten-Werteblocks in ein Element, der Wert rutscht hinter den nächsten Schlüssel (S. 114, 117, 118, 119, alle `Aktion:`) | **9** |
| Docling-Zeichenersetzung (Gedankenstrich → `-`, Anführungszeichen) | 16 |
| Messartefakt (pdfplumber-Laufweite trennt Wörter) | 5 |
| Wert nicht in derselben Zeile | 2 |

Kreaturenwerte: Das Zielbuch enthält keine. Vom Kreaturenband liegt nur eine 6-seitige Probe vor,
deshalb ist hier nichts gemessen.

## 9. Laufzeit (Docling, MPS)

- Docling je Seite: typisch 0,315 s, Maximum 3,98 s (zweithöchste 2,98 s), Summe 152 s für 314 Seiten.
- Schriftzuordnung (pdfplumber, `ordne_schrift_zu`) für das ganze Buch: 25,1 s.
- Rasterregel: siehe Abschnitt 2.
