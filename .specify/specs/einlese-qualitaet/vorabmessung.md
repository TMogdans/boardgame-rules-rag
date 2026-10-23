# Vorab-Messung Spec 2 (Einlesequalität), Fassung 3a (abgenommen 2026-10-23)

Fassung 1 gemessen am 2026-10-22, Fassung 2 am 2026-10-23 (gleiche Daten neu erzeugt, gleiche Versionen) am Zielbuch (Spielerhandbuch ED4, 3. Aufl., 314 S., physische Seite =
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
- **Urteil „besser/schlechter" (Fassung 2):** Jede Änderung wird einzeln beurteilt, und zwar an
  der Elementliste der Seite, an den **Fugen** (Ende des neuen Vorgängers ‖ Anfang des bewegten Blocks
  … Ende ‖ Anfang des Nachfolgers, z. B. eine Silbentrennung über den Spaltenwechsel) und, wo die Fuge
  nichts entscheidet, am Seitenbild bzw. Ausschnitt mit 100–110 dpi. Die Änderungsliste läuft über
  (Pfad, Vorkommen). Gemischte Fälle (andere Menge **und** andere Folge) zählen mit. Eine Klasse ist
  nur für die 2×2-Werteblock-Tausche zugelassen, und auch dort mechanisch belegt.
- **Urteil Fassung 1** (60 dpi, Stichproben): Maßstab: Folgt der Text dem Satzfluss der Seite (Spalte für
  Spalte, Fortsetzung über den Spaltenwechsel)? Steht ein Element unter der Überschrift, zu der es
  inhaltlich gehört?

## 0. Korrekturen gegenüber Fassung 1 (blinde Gegenprüfung vom 2026-10-23)

Die Gegenprüfung hat mit 100–150 dpi geurteilt und ihre Urteile festgeschrieben, bevor sie diese
Messung gelesen hat. Ihre Befunde gelten; die Fassung-1-Aussagen unten sind damit korrigiert:

| Fassung 1 | korrigiert |
|---|---|
| Rasterregel: 10 Seiten besser, 1 strittig (S. 53) | 10 besser, **1 schlechter** (S. 53): Der Kasten gehört thematisch zur neuen Kapitelüberschrift |
| 37 innere Umstellungen ohne Werteblock: 25 „Spaltenrücksprung", Stichprobe 3/3 besser, 12 nicht beurteilt | **31 besser, 5 schlechter, 1 strittig** (S. 58 überbreiter Block; S. 237 zweispaltiger Kasten; S. 274 Tabellenkopf aus Text-Elementen; S. 285–291 Passionsnamen ohne Bandgrenze; S. 299–306 Werte-Raster; S. 307–314 strittig). „Spaltenrücksprung" ist **kein** Gütesignal |
| Änderungsliste nach Pfad | `innen.py`/`innen2.py` übersahen 7 gemischte Abschnitte (andere Menge und andere Folge); `vergleich2.py` zählte nach Pfad statt nach Vorkommen. Fassung 2 zählt nach (Pfad, Vorkommen) und schließt gemischte Fälle ein |
| Strichrest ohne Prüfung: 5 schlechter, mit Liste 0 | **6 schlechter**, mit `als`/`beziehungsweise` noch **1** (S. 287: `gro- durch`, die Fortsetzung `-ßer` steht in der anderen Spalte) |
| Zierschrift-Umlaut: 4 Zeilen | **3 Zeilen** (S. 9, 10, 20); S. 216 trifft die Regel nicht (kein Vokal vor den Punkten). 4 geänderte *Abschnitte* bleiben richtig |
| — | 16 Formen `X- Großbuchstabe` und Flussbrüche (`beispiels- Die`) erfasste weder Regel noch Zähler |
| 2×2-Werteblöcke 156 gleichwertig | bestätigt (Stichprobe 20/20) |
| Zeilenend-Striche 59/59 besser | bestätigt |

## 0b. Korrekturen aus Gegenprüfung 2 (2026-10-23), eingearbeitet in Fassung 3

Ab Fassung 3 misst jede Zahl den Spec-Wortlaut. Die Prototypen sind daran angeglichen, nicht
umgekehrt. Alle Fassung-3-Läufe nutzen eine gemeinsame Kette (Kopfmenge aus Listenabgleich in
Docling-Folge + Layout-Köpfe; U+00AD, EQ-8, EQ-10, EQ-5, EQ-7, EQ-3/-4, Abschnitte, EQ-6, EQ-21).

| Fassung 2 | korrigiert |
|---|---|
| EQ-5: 60 Änderungen, 0 schlechter | Gemessen war ein Prototyp (Abschnittstext je Seite). Der damalige Wortlaut (Elementtext) ergibt 95, davon 1 schlechter (S. 296 `Throals` → `Thro- als`). Fassung 3: Elementtext-Wortlaut mit Sicherung → **94 geändert, 94 besser, 0 schlechter**, 1 gesichert (Abschnitt 3) |
| EQ-21: 104 Häppchen mit Vorsatz | Skriptfehler: Zerteilung ohne Kopfzeile (Grenzen verschoben); 11 Tabellen wegen U+00AD nicht gefunden; je Häppchen nur die erste Tabelle; Markdown-Zeile r+1 als Rasterzeile r. Fassung 3 mit genau gefasstem Kopf: **173 Häppchen**, 52 Tabellen (Abschnitt 7a) |
| EQ-21: „alle Kopfzeilen" verworfen, weil in 25 Tabellen eine Datenzeile Kopf würde | Artefakt der Markdown-Zeilenverschiebung. Am Raster enthält kein Kopf eine Datenzeile |
| EQ-21: S. 45 | Nach dem Fassung-2-Wortlaut würde die verbundene Datenzeile (Zeile 2) Kopf. Fassung 3: Kopf nur ab Zeile 0 zusammenhängend → kein Kopf |
| EQ-21: Spaltenköpfe S. 39, 96, 153, 231, 260 übergangen | Fassung 3: Titel + markierter Spaltenkopf |
| EQ-3: „Wächter verhindert S. 58 und S. 299–306", „25 Seiten ohne Wirkung" | 27 Wächterseiten. Ohne Wächter umsortiert wären **8** (S. 58, 299, 300, 302–305, 312), 19 ohne Änderung (nachgerechnet) |
| EQ-3: 2 teilweise besser | **5** (S. 25, 28, 32, 34 Windlinge, 34 Zwerge) |
| EQ-3: Spaltendefinition „Kasten in [a−tol, b+tol]" | Der Prototyp prüft nur die Spaltenlücke. Nach dem alten Wortlaut griffe der Wächter zusätzlich auf S. 20, 59, 68 (auf S. 20 ginge eine richtige Korrektur verloren, nachgerechnet). Wortlaut angeglichen |
| EQ-3: Freiheitsprüfung | Der Prototyp nimmt mehrspaltige Elemente und Eckbilder aus; Wortlaut angeglichen |
| Kopfmengen der Skripte | `strich2.py` und `tabkopf.py` bestimmten Listenköpfe anders als `vergleich3.py`. Fassung 3 nutzt eine Menge (146 Listen-, 391 Layout-Köpfe) |
| `wb_beweis.py` | Eine Bedingung war immer falsch. Korrigiert: genau 2 abweichende Positionen im selben Schlüssel:Wert-Lauf (≤ 8), Menge gleich → **156/156 belegt** (Laufgrößen 4, 6, 7) |
| EQ-6: „Großbuchstabe nie geändert" | Präzisiert: auch belegte Fälle nie (der Prototyp-Zweig `X-Y` ist verboten, Mutation im Messtor) |
| Bestätigt | EQ-3/-4 50/50 Urteile, keine verpasste Grenze; EQ-6 36/36; EQ-7 3/3 |

## 0c. Korrekturen aus der letzten Gegenprüfung, eingearbeitet in Fassung 3a

| Fassung 3 | Fassung 3a |
|---|---|
| EQ-5: 4.725 Striche, 4.610 unverändert, 5 nicht gefunden | Grundlinien als **Kette** zusammengelegt (Abstand zum letzten Wert der Gruppe): **4.726** Striche = 4.609 unverändert + 94 geändert + 1 gesichert + 16 mehrdeutig + 6 nicht gefunden. Textänderungen gleich, 94/94 besser (bestätigt), Mutation „Sicherung aus" schlägt an |
| EQ-21: 173 Häppchen mit Vorsatz | 3 Häppchen überlappten die Tabelle nur mit Füllzeichen und bekamen einen fremden Kopf: S. 113 (4 Zeichen am Ende), S. 141 (9 Zeichen am Ende), S. 260 (195 Zeichen leere Kopf- und Trennzeile am Anfang). **Füllzeichen-Bedingung** (Buchstabe oder Ziffer im überlappten Teil) nimmt genau 5 heraus (dazu 2 gleichwertige: S. 96, 231) → **168** |
| EQ-21: Kopftext ohne EQ-8 | U+0007 stand in den Vorsätzen von S. 136 und S. 141; EQ-8 gilt jetzt auch im Kopftext (mit Füllzeichen-Bedingung bleiben ohne EQ-8 noch 2 betroffene Häppchen, mit EQ-8 0) |
| EQ-21: Tabellen per Textsuche gefunden | Die textgleiche Tabelle „Sprachen" (S. 85/93) wurde in beiden Abschnitten gefunden, der Vorsatz stand doppelt. Zuordnung jetzt über die Lage des Elements; 79 Tabellen je genau einmal |
| EQ-21: 178 Häppchen mit Tabelle ohne Kopf | 172 (gezählt mit Füllzeichen-Bedingung; ohne sie 178) |
| Bestätigt | EQ-21: alle 52 Vorsätze sind der richtige Kopf |

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

## 2. Lesereihenfolge Fassung 1: Rasterregel (überholt, siehe Abschnitt 0 und 2a)

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

## 2a. Lesereihenfolge Fassung 2: Bänder an Überschriften

**Regel (Prototyp `raster_w4`):**
1. **Seitenwächter:** Trägt die Seite ein spaltenübergreifendes Element, das keine Überschrift ist und
   schmaler als 80 % des Satzspiegels (35–560 pt) ist, bleibt die Docling-Folge. Das betrifft 27
   Seiten. Geänderte Fälle verhindert der Wächter auf S. 58 (überbreiter Block) und S. 299–306
   (Werte-Raster der Beispielcharaktere). Auf den übrigen 25 Seiten hätte die Regel ohnehin nichts
   geändert.
2. **Ausnahmeseiten** (deklariert): S. 237 (zweispaltiger Kasten) und S. 274 (Tabellenkopf aus
   Text-Elementen). Das sind **2 Ausnahmen**.
3. **Mehrspaltige Elemente** (Docling-Element mit Kästen in verschiedenen Spalten; 104 im Buch)
   behalten ihre Stelle hinter ihrem Docling-Vorgänger.
4. **Bandgrenzen:** alle spaltenübergreifenden Elemente, dazu Überschriften in einer Spalte. Als
   Überschrift zählen Listen- und Layout-Köpfe aus Spec 1 sowie Docling-`section_header`. Eine solche
   Überschrift ist Bandgrenze, wenn die Nachbarspalte auf ihrer Höhe (±2 pt) frei ist (auch von
   Bildern) **und** sich darunter fortsetzt, vor dem nächsten spaltenübergreifenden Element.
5. In jedem Band kommt links vor rechts, jeweils nach Oberkante; bei Gleichstand gilt die
   Docling-Folge.

**Warum diese Grenzen:**
- Alle erkannten Köpfe als Bandgrenze (wörtlich „unabhängig von der Kastenbreite"): **444 Fälle**.
  Die Talentnamen stehen mitten in der Spalte, und die Nachbarspalte setzt das vorige Talent fort; die
  Regel zerlegt damit alle Talent- und Zauberseiten (S. 77–107, 163–215).
- Nur „Nachbarspalte frei": Die Fortsetzung oben rechts wandert vor kleine Spaltenüberschriften
  (S. 28: Text einer Rassenfähigkeit vor „Rassenfähigkeiten"). Deshalb gilt zusätzlich „setzt sich
  darunter fort".
- Kästen per Einzug erkennen: verworfen (Fassung 1, S. 20).

| Zahl | Docling-Folge | Fassung 2 |
|---|---|---|
| Fälle (Pfad, Vorkommen) | – | 206 |
| davon 2×2-Werteblock-Tausch | – | 156 |
| einzeln beurteilt | – | 50 (25 nur Folge, 8 gemischt, 17 nur Menge) |
| Elemente in einem anderen Abschnitt | – | 55 |
| Abschnitte mit anderer Elementmenge | – | 25 |
| Abschnittsköpfe nach ihrem Inhalt | 3 (S. 76, 114, 190) | 0 |
| Abschnitte / Liste gefunden / Stufe 1 / Stufe 2 | 539 / 144 / 386 / 5 | 539 / 144 / 386 / 5 |

**Urteile, alle 50 einzeln:**
- **49 besser.** Darunter: S. 16, 19/20, 22/23, 24, 25, 27/28, 30, 31, 32, 34, 37, 52, 76, 94, 100, 114,
  121, 124/126, 128/130, 140, 144, 148, 149, 171/172, 177, 190/191, 217, 222, 233, 257, 283, 286–291
  (Passionen: jede Passionsüberschrift wird Bandgrenze, die Fortsetzungen stehen unter der richtigen
  Passion), 297. Belegt ist das an Fugen, die eine Trennung über den Spaltenwechsel schließen (z. B.
  `gro- ‖ ßer`, `Grup- ‖ pentagebuch`, `ein- ‖ ladend`, `erzählst du ‖ dem`), sonst am Ausschnitt.
- Davon **5 nur teilweise besser** (korrigiert in Fassung 3: S. 25, S. 28 Elfen, S. 32, S. 34
  Windlinge, S. 34 Zwerge): Ein mehrspaltiges Element hält
  Text beider Spalten. Das bewegte Stück steht jetzt im richtigen Unterabschnitt neben seinem Absatz,
  aber nicht direkt an der Trennstelle. Abhilfe wäre die Teilung (O-10).
- **1 gleichwertig:** Index S. 308 (Indexzeile nach statt vor der Seitentabelle).
- **0 schlechter, 0 strittig.**
- Ohne die 2 Ausnahmen kämen S. 237 und S. 274 als schlechter hinzu.
- S. 53 ändert sich nicht mehr: Die rechte Kapitelüberschrift ist Bandgrenze, der Kasten bleibt unter
  ihr.

**2×2-Werteblöcke (156):** Mechanisch belegt ist für jeden Fall:
- Es weichen genau 2 Positionen ab (ein Tausch).
- Beide Elemente sind `Schlüssel: Wert`-Zeilen in einem zusammenhängenden Lauf von höchstens 7 solchen
  Zeilen.
- Die Menge des Laufs ist gleich.
- Die Paare bleiben ganz. Das Urteil ist gleichwertig (Gegenprüfung 20/20).

**Gemessene Varianten (nicht gewählt):**
- **Teilung mehrspaltiger Elemente** an Doclings `charspan` (je Kasten ein Stück): Sie ergibt 238
  Fälle, davon 91 einzeln zu beurteilen; beurteilt sind sie nicht. Die Fugen zeigen, dass sie die
  Flussbrüche schließt (`einset- ‖ zen`). An Kastengrenzen mitten im Wort fällt aber ein Zeichen weg
  bzw. ein Wort wird zerteilt (`verbleib ‖ nden`). Das braucht eine eigene Regel (O-10).

**Laufzeit:** Regel je Seite typisch 0,041 ms, Maximum 0,257 ms.

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

**Fassung 2, Striche auf der Fassung-2-Lesefolge** (Konjunktionsliste des Buchs um `als`,
`beziehungsweise` ergänzt):

- **Zeilenende aus der Quelle (EQ-5):** 60 Stellen in 50 Abschnitten (41 Strich wiederhergestellt,
  19 zusammengefügt). Alle 60 einzeln gelesen: **60 besser, 0 schlechter**. Gegenüber Fassung 1 kommt
  eine Stelle hinzu, weil die neue Folge eine Form eindeutig macht.
- **Strichrest mit Nachweis (EQ-6):** `X- y` (`y` klein, keine Konjunktion) wird nur zusammengefügt,
  wenn pdfplumber eine Zeile zeigt, die auf `X-` endet, und deren Quell-Folgezeile mit `y` beginnt.
  Folgezeile ist die nächste Zeile derselben Spalte (höchstens 20 pt tiefer); am Spaltenende ist es
  ein Blockanfang der anderen Spalte bzw. der nächsten Seite.
  - Ergebnis: **36 Stellen in 26 Abschnitten, 36 besser, 0 schlechter.** `gro- ßer` wird `großer`,
    weil die neue Folge die richtige Fortsetzung liefert. `gro- durch` (Docling-Folge) bekäme keinen
    Nachweis.
  - Die 5 Ergänzungsstriche vor `als`/`beziehungsweise` bleiben stehen.
- **`X- Großbuchstabe`:** 15 Stellen, alle **ohne** Nachweis über die Folgezeile derselben Spalte.
  9 davon sind Flussbrüche mehrspaltiger Elemente (`beispiels- Die`, `sei- Viele` …), 6 sind
  Komposita (`Karma- Modifikator`, `Mindest- Talentrang`, `Gesamt- Legendenpunkte` …).
  - Mit dem lockereren Nachweis (Blockanfang) hätte die Regel 4 Flussbrüche fälschlich zu
    `beispiels-Die` usw. gemacht. Deshalb gibt es für Großbuchstaben **keine Regel, nur einen Zähler**.
- **Verdachtszähler REQ-MB-32** (Fassung-2-Folge, ergänzte Liste): Binnen-Großbuchstabe 63 → 27
  (nach EQ-5), Strichrest 47 → 36 (nach EQ-5) → 0 (nach EQ-6).

**Fassung 1, Regel „Strichrest im Text" ohne Nachweis** (verbleibendes `X- y` mit kleinem `y`, keine Konjunktion → `Xy`; korrigiert in Abschnitt 0):
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

**Fassung 3, EQ-5 genau nach Spec-Wortlaut (Elementtext):**
- Arbeitsbasis ist der Elementtext nach U+00AD, EQ-8 und EQ-10. Zeichen werden den Elementkästen
  zugeordnet (kleinster Kasten, alle Elemente als Kandidaten), Quellzeilen je Kasten gebildet,
  Folgezeile nur im selben Kasten.
- 4.725 Zeilenend-Striche (Fassung 3, Anker-Lesart; Fassung 3a mit Kette: 4.726, davon 6 nicht gefunden, siehe 0c):

| Ergebnis | Anzahl |
|---|---|
| unverändert (Sollform steht schon da) | 4.610 |
| **geändert** | **94** (52 Strich wiederhergestellt, 36 Trennung zusammengefügt, 6 Ergänzungsstrich vor Konjunktion) |
| gesichert (Konjunktion, aber `LR` im Buch sonst als Wort) | 1 (S. 296 `Throals`) |
| mehrdeutig (Form mehrfach im Element) | 16 |
| nicht gefunden | 5 |

- Alle 94 einzeln gelesen: **94 besser, 0 schlechter**. Darunter alle 60 Stellen des Fassung-2-
  Prototyps, dazu 34 weitere (z. B. `HalbmagieProbe`, `gleich zeitig`, `Blut amulette`,
  `Drachenund`).
- Ohne Sicherung: 95 geändert, darunter 1 schlechter (S. 296).
- 83 Elemente ändern sich.
- **EQ-6 danach (Fassung 3):** 32 Stellen in 27 Abschnitten, alle aus den von Gegenprüfung 2
  bestätigten 36 (4 erledigt jetzt EQ-5 im Element); 32 besser, 0 schlechter. `X- Großbuchstabe`:
  15, unverändert.

## 4. Zierschrift-Umlaut (G5)

- **Korrigiert (Fassung 2):** Die Regel ändert **3 Zeilen** (S. 9, 10, 20) und dadurch 4 Abschnitte,
  4 besser. S. 216 (`Beschworung . .`, Punkte am Wortende, ohne Vokal davor) erfasst sie nicht;
  welcher Vokal gemeint ist, bleibt offen (`o` oder `u`). Das ist eine bekannte Grenze.
- Fassung 1: Docling liefert auf 4 Zeilen einen Umlaut als Grundvokal mit zwei abgesetzten Punkten
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
| Länge je Tabelle | typisch 1.361, Maximum 27.521 (Beispielcharakter S. 49; korrigiert in Fassung 2, Fassung 1 nannte fälschlich den Index). Der Index S. 307–311 kommt als je eine Tabelle pro Seite; 52 von 79 länger als `CHUNK_SIZE` 800 |
| Häppchen (800/150, nachgerechnet mit `rag.zerteile`) | 2.638 gesamt; **366 mit Tabellenteil, 316 davon ohne Tabellenkopf** |
| dasselbe ohne Füll-Leerzeichen | 2.383 / 186 / 131 |
| Spannzellen im Raster doppelt | 50 Tabellen, 271 Zellen |
| Zahlen im Tabellenkasten | Quelle 3.498, Markdown 4.156: 7 fehlen (S. 40: 6, S. 308: 1), 665 zusätzlich (vervielfacht) |
| Tabelle doppelt (Tabelle + Bild-Kinder im selben Kasten) | 1 (S. 20, 41 Bild-Kinder) |
| Tabelle in einem fremden Abschnitt | 1 (S. 22; Rasterregel behebt) |
| Werteblock als Tabelle | 4 (S. 96, 117, 118 zweimal) |
| Zeilen-Schablone `Kopf: Wert; …` (erste Rasterzeile als Kopf, Spannzellen einmal) | 1.117 Zeilen, Länge typisch 85, p95 177, Maximum 712; 938 Zeilen höchstens 150 Zeichen lang (`CHUNK_OVERLAP`) |

## 7a. Tabellenkopf je Häppchen (Fassung 3a)

**Wortlaut (REQ-EQ-21):**
- Kopf = zusammenhängende markierte Rasterzeilen ab Zeile 0 (`column_header` oder Titelzeile).
- Kopfbereich = erste zwei Markdown-Zeilen.
- Vorsatz an jedes Häppchen, das die Tabelle überlappt, ohne den Kopfbereich ganz zu enthalten. Alle
  Tabellen eines Häppchens zählen.
- Die Zerteilung läuft auf dem vollen Abschnittstext (800/150).
- Die Tabelle wird über die Lage ihres Elements zugeordnet (Fassung 3a); alle 79 genau einmal.
- Vorsatz nur, wenn der überlappte Teil einen Buchstaben oder eine Ziffer enthält; EQ-8 auf dem Kopftext (Fassung 3a).
- Ausnahme Index S. 307–311.

| Zahl | Wert |
|---|---|
| Tabellen / mit Kopf / ohne Kopf / Ausnahme Index | 79 / 59 / 20 / 5 (unter den 59) |
| Tabellen mit Vorsatz | 52 (2 mit Kopf schneidet kein Häppchen ohne Kopfbereich an) |
| Häppchen mit Vorsatz | **168** (Fassung 3a; Fassung 3: 173) |
| Zuwachs je Häppchen | typisch 82, Maximum 260 Zeichen; Summe 15.139 (+1,0 %) |
| Häppchenlänge mit Vorsatz | typisch 880, Maximum 1.060 |
| Häppchen, die eine Tabelle ohne Kopf anschneiden | 172 (kein Vorsatz) |
| Vorsätze mit Steuerzeichen | 0 |

**Urteil je Tabelle (52, alle einzeln, am Kopftext gegen das Raster):**
- **51 besser.** 41 davon mit Titel und/oder Spaltenkopf, 10 nur mit dem Titel (Spaltenkopf in
  Docling nicht markiert: S. 106, 110, 112, 118, 119, 124, 156, 219, 267, 270).
- **1 gleichwertig** (S. 136, Kopf in Docling verstümmelt).
- **0 schlechter.**
- Keine Datenzeile in einem Kopf.

**Varianten:**
- nur `column_header`-Zeilen: 150 Häppchen, 40 Tabellen; die Titel fehlen.
- nur erste markierte Zeile (Prototyp Fassung 2): 173 Häppchen, aber bei 28 Tabellen nur die erste
  von mehreren Kopfzeilen.
- **Fassung 2 (überholt):** 104 Häppchen, Skriptfehler siehe Abschnitt 0b.

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
