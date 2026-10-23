# Spec: Einlesequalität: Lesereihenfolge, Tabellen und Werteblöcke, Zahlentreue

- **Spec-ID:** einlese-qualitaet (Spec 2; Schnitt 2a/2b abgenommen, O-1)
- **Kontext-Kürzel:** EQ
- **Tier:** T3 (siehe Abschnitt „Tier")
- **Status:** **Entwurf Fassung 3, nicht abgenommen.** Fassung 3 arbeitet die blinde
  Gegenprüfung 2 (2026-10-23) ein; das Vorgehen hat Tobias abgenommen.
  - EQ-5 ist auf den Elementtext festgeschrieben und hat eine Sicherung für den Konjunktionsfall.
  - EQ-21 hat einen genau gefassten Tabellenkopf und ist neu gemessen.
  - Wortlaut und Zählung von EQ-3 sind an den Prototyp angeglichen; EQ-6 ist präzisiert.
  - Bekannte Grenzen sind ergänzt.

  Ab Fassung 3 läuft jede Messung nach dem Spec-Wortlaut, nicht nach einem abweichenden Prototyp.
  Fassung 2 (Bänder an Überschriften, Strichrest mit Nachweis, Tabellenkopf) und Fassung 1 sind im
  Verlauf der Vorab-Messung dokumentiert (`vorabmessung.md`, Abschnitte 0 und 0b). Offen: O-2, O-3,
  O-5, O-10 bis O-17.
- **Abbruchbedingung (Tobias, vorab):** Nach Fassung 3 prüft ein frischer Agent blind nur EQ-5 und
  EQ-21. Blockieren darf nur eine Verschlechterung am echten Buch durch eine dieser beiden Regeln.

## User Story

Als Betreiber des lokalen Regel-RAG möchte ich, dass ein Buch mit Zweispaltensatz, Bildern, Tabellen
und Werteblöcken so eingelesen wird, dass jeder Text unter seiner eigenen Überschrift steht, Tabellen
und Werteblöcke in jedem Häppchen lesbar bleiben (Spaltenkopf zum Wert) und keine Zahl der Quelle
verloren geht oder hinzukommt. **Damit** werden Antworten auf Regel- und Wertefragen aus dem richtigen
Abschnitt und mit den richtigen Zahlen gegeben. Jede Korrektur soll ihren Nutzen am echten Buch
nachgewiesen haben, bevor sie gilt, und sie soll sich je Buch abschalten lassen.

Erster Anwendungsfall ist wieder das Spielerhandbuch ED4 (3. Aufl.). **Earthdawn steckt nur in den
Daten (Buchdeklaration in `spiel.json`), nie im Code.**

**Lehre aus Spec 1:** REQ-MB-31 (Überschriften nach Lage einsortieren) wurde ohne Messung an echten
Docling-Kästen abgenommen. Am Buch hat die Regel genau 2 Abschnitte geändert, beide zum Schlechteren.
Deshalb gilt hier für **jede** Regel ein Messtor (REQ-EQ-1): Vor der Abnahme wird am echten Buch
gezählt, wie viele Abschnitte sich ändern und wie viele davon besser oder schlechter werden.

**Lehre aus Fassung 1:** Die Bilanz der Rasterregel (10 besser, 1 strittig) hielt der blinden
Gegenprüfung nicht stand. Richtig sind 1 schlechter auf den Abschnittswechseln und 5 schlechter, 1
strittig auf den inneren Umstellungen. Die Ursachen:
- Klassen-Urteile („Spaltenrücksprung") wurden aus einer Stichprobe von 3 hochgerechnet.
- Geurteilt wurde mit 60 dpi.
- Die Änderungsliste übersah gemischte Fälle.

Deshalb verlangt das Messtor jetzt Einzelurteile, Bilder mit mindestens 100 dpi und eine
Änderungsliste über (Pfad, Vorkommen).

## Begriffe

| Begriff | Bedeutung |
|---|---|
| **Regel** | Eine Korrektur dieser Spec (EQ-3 bis EQ-14, EQ-21), je Buch einzeln eingeschaltet. |
| **Spec-2-Deklaration** | Die neuen Schlüssel eines Buchs in `spiel.json` (Entwurf: `lesefolge`, `striche`, `zeichen`, `tabellenkopf`, `tabellen`, `werteblock`; Schema REQ-EQ-15). Fehlt ein Schlüssel, ist die zugehörige Regel aus. |
| **Spaltenraster** | Je Buch deklarierte x-Bereiche der Satzspalten in PDF-Punkten, z. B. `[[35, 292], [304, 560]]`, dazu eine Toleranz. |
| **Spalte eines Elements** | Maßgeblich ist der **erste** Kasten des Elements (`x0`, `x1`). Spalte *i*, wenn er nicht in die Spaltenlücke links oder rechts von Spalte *i* hineinreicht: `x0 ≥ a_i − tol` (entfällt für die erste Spalte) und `x1 ≤ b_i + tol` (entfällt für die letzte Spalte). Sonst ist das Element **spaltenübergreifend**. Der äußere Rand begrenzt nicht (Fassung 3, wie gemessen; mit Rand-Grenze griffe der Wächter zusätzlich auf S. 20, 59, 68 und nähme auf S. 20 eine richtige Korrektur weg). |
| **Band** | Bereich einer Seite zwischen zwei Bandgrenzen (nach Oberkante). |
| **Kopfmenge** | Zeilen, die der Listenabgleich (REQ-MB-12) in der Docling-Folge einem Listeneintrag zuordnet, plus die Zeilen außerhalb des Rands, die nach REQ-MB-20 Layout-Überschrift einer Stufe sind. Eine Menge für alle Regeln und Messungen. |
| **Bandgrenze** | (1) jedes spaltenübergreifende Element; (2) eine **Überschrift in einer Spalte** (Zeile der Kopfmenge oder Docling-Klasse `section_header`), wenn die Nachbarspalte auf Höhe ihres ersten Kastens ±2 pt **frei** ist **und** sich darunter vor dem nächsten spaltenübergreifenden Element **fortsetzt** (REQ-EQ-3). Für „frei" und „fortsetzt" zählen nur Elemente, die nicht im Rand liegen und **nicht mehrspaltig** sind. Bilder belegen die Nachbarspalte, außer **Eckbildern** (Unterkante ≤ 70 pt und ganz links bis x ≤ 80 pt oder ganz rechts ab x ≥ 500 pt, Zielbuch: Kapitelzierden). Ein Bild belegt die rechte Nachbarspalte, wenn es links vor der Lücke beginnt bzw. rechts hinter ihr endet (x0 < b_1 + tol bzw. x1 > a_2 − tol). |
| **Mehrspaltiges Element** | Docling-Element mit Kästen (`prov`) in verschiedenen Spalten; Docling hat Text über den Spaltenwechsel zusammengelegt. |
| **Seitenwächter** | Eine Seite mit einem spaltenübergreifenden Element (außerhalb des Rands, nicht Kopfmenge, nicht `section_header`), dessen erster Kasten schmaler ist als der deklarierte Anteil der Breite von `a_1` bis `b_letzte` (Zielbuch 80 % von 35–560 pt), wird nicht umgeordnet. |
| **Fall** | Eine Änderung der Regel, gezählt über (Abschnittspfad, Vorkommen): andere Elementmenge, andere Folge oder beides. |
| **Fuge** | Übergang zwischen zwei Elementen in der neuen Folge (Ende des Vorgängers ‖ Anfang des Nachfolgers). Eine Fuge, die eine Silbentrennung über Spalten schließt (`gro- ‖ ßer`), belegt die Folge. |
| **Abschnittsänderung** | Ein Abschnitt verliert oder gewinnt Elemente gegenüber dem Lauf ohne die Regel. Ein Abschnitt, dessen Elementmenge gleich bleibt, dessen Text sich aber ändert (Folge innen, Zeichen), heißt **Textänderung**. |
| **Urteil** | Von Hand, je Fall, an Elementliste, Fugen und Seitenbild bzw. Ausschnitt mit mindestens 100 dpi: `besser`, `gleichwertig`, `schlechter`, `strittig`. „Strittig" zählt für das Messtor wie `schlechter`, bis Tobias anders entscheidet. |
| **Regel-Messung** | Der Abschnitt der Vorab-Messung für eine Regel: Prototyp am echten Buch, Zählung, Urteile (REQ-EQ-1). |
| **Zeilenend-Strich** | Eine Quellzeile eines Elementkastens (REQ-EQ-5) endet auf Buchstabe oder Ziffer + `-` bzw. U+00AD, und im selben Kasten folgt eine weitere Quellzeile. |
| **Werteblock** | Folge kurzer `Schlüssel: Wert`-Zeilen unter einer Überschrift (Talent, Zauber, Fertigkeit). Die Schlüssel sind Daten des Buchs. |
| **Werteblock-Paar** | Schlüssel + Wert einer Werteblock-Zeile der Quelle. Es ist **intakt**, wenn `Schlüssel Wert` (Leerraum normalisiert) im Text der Seite steht. |
| **Tabellen-Schablone** | Textform einer Tabelle: je Rasterzeile eine Zeile mit `Spaltenkopf: Zellwert`-Paaren (REQ-EQ-11). |
| **Tabellenkopf** | Die **zusammenhängende Folge markierter Rasterzeilen ab Zeile 0** einer Docling-Tabelle. Markiert ist eine Rasterzeile, wenn mindestens eine Zelle `column_header` trägt **oder** alle Zellen denselben nicht-leeren Text haben (Titelzeile). Die Folge endet an der ersten unmarkierten Zeile; Zeilen ohne Text darin entfallen. Ist Zeile 0 nicht markiert, hat die Tabelle keinen Kopf. Titel und markierter Spaltenkopf stehen damit gemeinsam im Kopf. |
| **Kopfbereich** | Die ersten zwei Zeilen des Markdown-Texts der Tabelle (Kopfzeile und Trennzeile), so wie Docling sie liefert. |
| **Zahlenprotokoll** | Vergleich der Ziffernfolgen (`\d+`) je Seite zwischen Quelle und Buchdatei (REQ-EQ-9). |

## Akzeptanzkriterien

### A. Messtor und Wirkungszähler (für alle Regeln)

**REQ-EQ-1**: *Vorbedingung, Messtor je Regel*
- Für jede Regel EQ-3 bis EQ-14 und EQ-21 liegt **vor der Abnahme** des Commits, der sie umsetzt, eine
  Regel-Messung im Spec-Ordner (`vorabmessung.json`, Schlüssel `regeln.<REQ-ID>`).
- Gemessen wird am echten Zielbuch, mit den Docling- und pdfplumber-Versionen von REQ-EQ-19.
- Die Regel-Messung enthält:
  - die **Änderungsliste über (Abschnittspfad, Vorkommen)**, je Fall mit Art (andere Menge,
    andere Folge, beides) und Seiten. Gemischte Fälle zählen mit; eine Liste nur nach Pfad genügt
    nicht;
  - je Fall ein **Einzelurteil**, auch für **innere Umstellungen** (gleiche Elementmenge, andere
    Folge). Grundlage sind Elementliste, Fugen und Seitenbild bzw. Ausschnitt mit **mindestens
    100 dpi**;
  - **einzige zugelassene Klasse:** der Tausch zweier `Schlüssel: Wert`-Zeilen innerhalb eines
    Werteblocks (2×2-Werteblock). Er gilt als gleichwertig, wenn mechanisch belegt ist: Alte und
    neue Folge sind gleich lang, genau 2 Positionen weichen ab, beide Elemente sind
    `Schlüssel: Wert`-Zeilen im selben zusammenhängenden Lauf solcher Zeilen der alten Folge, der Lauf
    hat höchstens 8 Zeilen, und seine Menge ist in alter und neuer Folge gleich. Jede andere Hochrechnung aus
    Stichproben ist unzulässig;
  - die Bilanz `besser / gleichwertig / schlechter / strittig`, dazu die **Zahl der Ausnahmen**
    (Ausnahmeseiten nach REQ-EQ-4 und durch den Seitenwächter verhinderte Fälle), jeweils mit Seiten.
- **Ziel:** `schlechter + strittig = 0`, **nach** Ausnahmen; die Ausnahmen stehen als Zahl in der
  Messung. Sonst entscheidet Tobias **vor** dem Weiterbauen: Regel ändern und neu messen, Ausnahme
  deklarieren (REQ-EQ-4) oder Regel streichen.
- Die Zielzahlen der Kriterien unten stammen aus der Vorab-Messung Fassung 2. Sie gelten als
  **Erwartung**, nicht als Spielraum.

*Detektor:*
- `vorabmessung.json` enthält für jede umgesetzte Regel den Schlüssel mit den Feldern
  `faelle`, `faelle_art{menge, folge, beides}`, `seiten`, `ausnahmen`, `urteil{besser, gleichwertig,
  schlechter, strittig}`, und zwar bevor ein Commit die Regel umsetzt (Prüfung im Review über die
  Git-Historie).
- Ein Test prüft das Format: Zahlen nichtnegativ, Summe der Urteile = Zahl der beurteilten Fälle,
  nur Zahlen und Versionen (REQ-EQ-18).

**REQ-EQ-2**: *Contract, Wirkungszähler und Messgleichheit*
- Das Einlese-Protokoll zählt je eingeschalteter Regel die Abschnittsänderungen und Textänderungen
  mit Seiten. Verglichen wird mit einem Lauf, in dem nur diese Regel aus ist.
- Die Regeln wirken in fester Reihenfolge:
  1. Entfernen von U+00AD aus jedem Elementtext (REQ-MB-11, Tabellenzeile 2). Das läuft **vor**
     EQ-5, weil 8 der gemessenen Fälle sonst nicht gefunden würden.
  2. Elementtexte: EQ-8, EQ-10, EQ-13, EQ-14, **EQ-5**, dann EQ-7.
  3. Kopfmenge und Listenabgleich (REQ-MB-12), EQ-3/-4 (Folge), EQ-11 (Tabellentext).
  4. Abschnitte, EQ-6 (Abschnittstext), EQ-21 (beim Zerteilen).
  Gezählt wird jeweils gegen den Lauf mit allen vorangehenden Regeln.
- Text und Abschnitte entstehen nur aus dem Lauf mit allen eingeschalteten Regeln. Die
  Vergleichsläufe sind reine Funktionsaufrufe auf denselben Zeilen.
- **Messgleichheit:** Beim ersten Einlesen des Zielbuchs mit der Implementierung zeigt das Protokoll
  je Regel **dieselben** Zahlen und Seiten wie die Regel-Messung. Weicht eine Zahl ab, setzt die
  Implementierung eine andere Regel um als die gemessene: Stopp und Rückfrage, kein Merge.

*Detektor:*
- Synthetisches Buch mit je einem Fall pro Regel, alle Regeln an → jeder Regelzähler = 1 mit der
  richtigen Seite.
- Eine Regel aus → ihr Zähler fehlt, die anderen bleiben.
- Mutation „Zähler vergleicht gegen den Lauf ohne alle Regeln" → der Test mit zwei Regeln auf
  derselben Seite wird rot.

### B. Lesereihenfolge (Teil 2a)

**REQ-EQ-3**: *Where, Bänder an Überschriften (Fassung 2)*
- Wo ein Buch `lesefolge.spalten` deklariert, ordnet das Einlesen die Elemente jeder Seite (ohne
  Randzeilen, REQ-MB-28) neu:
  1. **Seitenwächter:** Trägt die Seite ein spaltenübergreifendes Element, das keine Überschrift ist
     und schmaler als `lesefolge.waechter` × Satzspiegelbreite ist (Zielbuch: 0,8), bleibt die
     Docling-Folge der Seite. Ebenso auf Ausnahmeseiten (REQ-EQ-4).
  2. **Mehrspaltige Elemente** nehmen an Schritt 3 und 4 nicht teil. Danach stehen sie direkt hinter
     ihrem Docling-Vorgänger, also dem letzten Nicht-Rand-Element davor in der Docling-Folge.
  3. Die **Bandgrenzen** (Begriffe) teilen die Seite nach der Oberkante des ersten Kastens in Bänder.
     Welche Zeilen Überschriften sind, sagt die Kopfmenge (Begriffe), bestimmt vorab in der
     Docling-Folge.
  4. In jedem Band kommen die Elemente der Spalten von links nach rechts, innerhalb einer Spalte nach
     Oberkante des ersten Kastens, bei Gleichstand in Docling-Folge. Danach folgt die Bandgrenze.
  5. Ein Element ohne Lage behält seinen Platz hinter seinem Docling-Vorgänger. Bild-Elemente sind
     keine Bandgrenze, belegen aber die Nachbarspalte für die Freiheitsprüfung. Text aus
     Bild-Elementen (REQ-MB-27) wird wie jedes andere Element einsortiert.
- Danach laufen Abschnittsbildung, Layout-Überschriften und Zerschneiden (REQ-MB-12, -20, -14).

*Ziel (Vorab-Messung Fassung 2, Ausnahmen S. 237 und 274):*
- **206 Fälle**: 156 2×2-Werteblock-Tausche (gleichwertig, mechanisch belegt) und **50 einzeln
  beurteilte** (25 nur Folge, 8 gemischt, 17 nur Menge).
- Davon **49 besser**, **1 gleichwertig** (Index S. 308), **0 schlechter, 0 strittig**; von
  Gegenprüfung 2 bestätigt.
  - **5** der 49 sind nur teilweise besser (korrigiert in Fassung 3): S. 25, S. 28, S. 32,
    S. 34 Windlinge, S. 34 Zwerge. Der Restfehler kommt jeweils von einem mehrspaltigen Element.
- **Ausnahmen:** 2 Seiten deklariert (S. 237 zweispaltiger Kasten, S. 274 Tabellenkopf aus
  Text-Elementen; ohne sie je 1 schlechter).
- Der Seitenwächter greift auf **27 Seiten**:
  - Auf **8** davon würde die Regel ohne Wächter die Folge ändern: S. 58, 299, 300, 302–305, 312.
    Laut Gegenprüfung 2 jeweils zum Schlechteren.
  - Auf **19** Seiten änderte sie ohnehin nichts.
- Der Wortlaut der Spaltendefinition und der Freiheitsprüfung ist in Fassung 3 an den gemessenen
  Prototyp angeglichen (Begriffe); die Zahlen gelten für diesen Wortlaut. Gemessen ist die Kette auf
  den Docling-Texten.
- 55 Elemente wechseln den Abschnitt, 25 Abschnitte ändern ihre Elementmenge.
- Abschnittsköpfe nach ihrem Inhalt: 3 → 0 (S. 76, 114, 190). Unter „Talentbeschreibungen" stehen
  149 Talente.
- Passionen S. 285–291: Jede Passionsüberschrift wird Bandgrenze. S. 53 ändert sich nicht mehr (der
  Kasten bleibt unter „Disziplinbeschreibungen").
- Gleich bleiben: Abschnittszahl 539, Lesezeichen gefunden 144, Layout-Stufen 386/5.
- Zusatzzeit je Seite: typisch 0,041 ms, Maximum 0,257 ms.

*Detektor:* synthetische Seiten mit Kästen in absichtlich falscher Docling-Folge:
- (a) Eine spaltenübergreifende Überschrift oben kommt nach dem ersten Element der linken Spalte →
  sie steht zuerst, das Element liegt in ihrem Abschnitt.
- (b) Der Kopf der rechten Spalte kommt als Bild-Kind am Seitenende → er steht hinter der linken
  Spalte und vor der nächsten Bandgrenze.
- (c) Eine Tabelle oben rechts kommt hinter allen Absätzen der Seite → sie liegt im Abschnitt der
  Überschrift über ihr.
- (d) Ein Bild reicht über beide Spalten, rechts daneben steht ein schmales Element → dieses folgt
  dem Ende der linken Spalte.
- (e) **Schmale Überschrift mit freier, fortgesetzter Nachbarspalte** (Passionsfall): links
  `Kopf A`, Text A1; rechts A2 darüber, B2 darunter; dann links `Kopf B` auf Höhe einer Lücke
  rechts → Folge A1, A2, `Kopf B`, B…; A2 liegt in A.
- (f) **Überschrift in der Spalte** (Talentfall): links `Talent X` auf Höhe eines rechten Absatzes →
  keine Bandgrenze, rechte Spalte folgt nach der ganzen linken.
- (g) **Kurze Nachbarspalte** (Fall S. 28): links eine Überschrift, rechts nur ein Element darüber,
  darunter nichts → keine Bandgrenze.
- (h) Mehrspaltiges Element bleibt hinter seinem Docling-Vorgänger.
- (i) Teilbreites spaltenübergreifendes Element (z. B. 50 % Breite) → Docling-Folge der ganzen
  Seite.
- (j) Ein 2×2-Werteblock mit gleichen Oberkanten → zeilenweise Folge.
- (k) Ohne `lesefolge` → Folge und Buchdatei byte-gleich zum Lauf vor dieser Spec.
- Mutationen machen je einen Fall rot: „Bänder ignorieren", „Fortsetzungsbedingung weglassen" (g
  rot), „alle Köpfe als Bandgrenze" (f rot), „Wächter aus" (i rot), „mehrspaltige Elemente
  einsortieren" (h rot).

**REQ-EQ-4**: *Where, Ausnahmeseiten*
- Wo ein Buch `lesefolge.ausnahmen` deklariert (Liste physischer Seiten), gilt auf diesen Seiten
  die Docling-Folge. Das Protokoll nennt die Ausnahmeseiten.
- Jede Ausnahme braucht in der Regel-Messung eine Begründung (Seite, Urteil ohne Ausnahme).
- Ein Buch kann für REQ-EQ-21 eigene Ausnahmeseiten deklarieren (`tabellenkopf.ausnahmen`); sie
  wirken nur dort.
- *Ziel:* `lesefolge.ausnahmen = [237, 274]`. Ohne sie wären es je 1 schlechter (S. 237: der rechte
  Kastenteil reißt einen Satz; S. 274: Tabellenkopf aus Text-Elementen zeilenweise zerlegt). Mit
  ihnen gilt die Bilanz von REQ-EQ-3 (Entscheidung O-2).

*Detektor:* synthetisches Buch mit zwei Seiten im Fall (a) von REQ-EQ-3, Seite 2 als Ausnahme →
Seite 1 neu geordnet, Seite 2 in Docling-Folge, Protokoll nennt Seite 2.

### C. Striche und Zeichen (Teil 2a)

**REQ-EQ-5**: *Where, Zeilenend-Striche aus der Quelle (Docling-Weg), Fassung 3*
- Wo ein Buch `striche.zeilenenden` einschaltet, bearbeitet das Einlesen jedes Element außer
  Tabellen. **Arbeitsbasis** ist der Elementtext nach Entfernen von U+00AD, EQ-8 und EQ-10 (REQ-EQ-2).
- **Quellzeilen je Kasten:**
  - Alle pdfplumber-Zeichen der Seite (auch Leerzeichen) werden dem Kasten zugeordnet, in dem ihre
    Mitte liegt (±1 pt). Kandidaten sind alle Kästen aller Docling-Elemente der Seite, Tabellen und
    Randzeilen eingeschlossen; bei mehreren gewinnt der kleinste, bei Gleichstand der erste in
    Docling-Folge.
  - Je Kasten eines Elements (mehrere Kästen: je Kasten getrennt) bilden die Zeichen Zeilen nach
    Grundlinie: `bottom` auf ganze pt gerundet, benachbarte Werte mit Abstand ≤ 1 pt zusammengelegt.
  - Innerhalb einer Zeile gilt die Folge nach `x0`. Zwischen zwei Zeichen mit einer Lücke über 1,2 pt
    steht ein Leerzeichen; Leerraum wird zu einem Leerzeichen zusammengefasst.
  - Die **Folgezeile** ist die nächste Zeile desselben Kastens. Über Kasten- und Elementgrenzen gibt
    es keine Folgezeile (das ist EQ-6).
- **Fall:** Eine Zeile endet auf `L-` oder `L` + U+00AD (`L` = Buchstaben/Ziffern), die Folgezeile
  beginnt mit dem Wort `R`. Sollform:

  | Quelle | Sollform |
  |---|---|
  | Ziffer am Ende von `L`, oder `R` beginnt groß | `L-R` |
  | `R` in der Konjunktionsliste des Buchs **und** `LR` kommt im Buch sonst **nicht** als Wort vor | `L- R` |
  | `R` in der Konjunktionsliste, aber `LR` kommt im Buch sonst als Wort vor (**Sicherung**) | `LR` |
  | sonst (`R` beginnt klein) | `LR` |

  „Im Buch sonst als Wort": `LR` steht mindestens einmal als ganzes Wort in den Arbeitsbasis-Texten
  aller Elemente des Buchs, ein Vorkommen im bearbeiteten Element selbst nicht mitgezählt.
- **Ersetzen:** Gesucht werden die vier Formen `LR`, `L-R`, `L- R`, `L R` als ganze Wörter (kein
  Buchstabe, keine Ziffer und kein `_` direkt davor oder danach) im aktuellen Elementtext. Dieser
  enthält die Ersetzungen früherer Fälle desselben Elements.
  - Kein Vorkommen → `nicht_gefunden`.
  - Alle Vorkommen sind die Sollform → `unveraendert`.
  - Mehr als ein Vorkommen → `mehrdeutig`, Text unverändert.
  - Genau ein Vorkommen in anderer Form → durch die Sollform ersetzen.
- Das Protokoll zählt `geaendert` (getrennt: Strich, Trennung, Konjunktion), `gesichert`,
  `unveraendert`, `mehrdeutig`, `nicht_gefunden`.
- Die Verdachtszähler aus REQ-MB-32 laufen danach.

*Ziel (Vorab-Messung Fassung 3, genau nach diesem Wortlaut):*
- 4.725 Zeilenend-Striche: 4.610 unverändert, **94 geändert** (52 Striche wiederhergestellt,
  36 Trennungen zusammengefügt, 6 Ergänzungsstriche vor Konjunktion), 1 gesichert, 16 mehrdeutig,
  5 nicht gefunden. 83 Elemente ändern sich.
- Einzeln gelesen: **94 besser, 0 gleichwertig, 0 schlechter**.
- Gesichert ist S. 296: Ohne Sicherung würde `Throals` zu `Thro- als` (1 schlechter, Gegenprüfung 2).
  `Throals` steht im Buch sonst als Wort, also bleibt es.
- Fassung 2 maß einen abweichenden Prototyp (Abschnittstext je Seite, Spaltenzeilen der Seite): 60
  Änderungen. Der Elementwortlaut findet alle 60 und 34 weitere, alle besser.

*Detektor:*
- Synthetisches PDF (`reportlab`, wie REQ-MB-29) mit den Zeilenenden `Novizen-⏎Talent`,
  `W8-⏎Würfel`, `Nah-⏎und`, `Akti-⏎onswürfel`, `Bur-⏎gund` (Konjunktion) und `Thro-⏎als`.
- Dazu eine Docling-Struktur mit den Texten `NovizenTalent`, `W8Würfel`, `Nahund`,
  `Akti- onswürfel`, `Burgund`, `Throals`. Ein weiteres Element enthält das Wort `Throals`.
- Erwartet: `Novizen-Talent`, `W8-Würfel`, `Nah- und`, `Aktionswürfel`; `Burgund` bleibt
  (`gund` ist keine Konjunktion, Sollform `Burgund`); `Throals` bleibt (`gesichert = 1`).
- `NovizenTalent` zweimal im selben Element → `mehrdeutig = 1`.
- Mit U+00AD im Elementtext (`Novizen­Talent`) → nach der Entfernung gefunden.
- Ohne `striche` → byte-gleich.
- Mutationen machen je einen Fall rot: „Sicherung aus" (`Throals` → `Thro- als`), „Konjunktion
  ignorieren" (`Nah- und`), „U+00AD nach EQ-5 entfernen", „Folgezeile über Kastengrenze hinweg".

**REQ-EQ-6**: *Where, Strichrest mit Quellnachweis (Fassung 2)*
- Wo ein Buch `striche.strichrest` einschaltet, wird im Abschnittstext nach REQ-EQ-5 jede Folge
  „Wortstück `X`, `-`, ein oder mehrere Leerzeichen, Wort `y` mit Kleinbuchstaben am Anfang, nicht in
  der Konjunktionsliste" **nur dann** zu `Xy` zusammengefügt, wenn pdfplumber auf einer Seite des
  Abschnitts eine Zeile zeigt, deren letztes Wort auf `X-` endet, und deren **Quell-Folgezeile** mit
  `y` beginnt.
  - Quell-Folgezeile ist die nächste Zeile derselben Spalte (höchstens 20 pt tiefer).
  - Hat die Zeile keine solche (Spalten- oder Seitenende), ist es ein Blockanfang der anderen Spalte
    derselben Seite, ein Blockanfang darunter in derselben Spalte oder (rechte Spalte) ein
    Blockanfang der nächsten Seite. Blockanfang heißt: keine Zeile derselben Spalte höchstens 20 pt
    darüber.
- Ohne Nachweis bleibt der Text unverändert.
- **`X- Großbuchstabe`** wird **nie** geändert, auch dann nicht, wenn pdfplumber die Fortsetzung
  belegt (Fassung 3: Der Prototyp-Zweig `X-Y` darf nicht in die Implementierung). Das Protokoll
  zählt solche Stellen mit Seiten als neuen Verdachtsfall `strich_vor_grossbuchstabe` (Komposita wie
  `Karma- Modifikator` und Flussbrüche wie `beispiels- Die`; die Fuge entscheidet nicht zwischen
  beiden).
- Die Konjunktionsliste ist die der Buchdeklaration (`reparatur.konjunktionen`, REQ-MB-11). Für das
  Zielbuch ist sie um `als` und `beziehungsweise` ergänzt.

*Ziel (Vorab-Messung Fassung 2, nach REQ-EQ-3 und -5):*
- Fassung 3 (nach EQ-5 im neuen Wortlaut, der 4 der früheren Stellen schon im Element erledigt):
  **32 Stellen in 27 Abschnitten**, alle aus den 36 von Gegenprüfung 2 bestätigten, 32 besser,
  0 schlechter. (Fassung 2: 36 in 26.)
  - Darunter `gro- ßer` → `großer`: Die neue Folge liefert die richtige Fortsetzung. Unter
    Docling-Folge (`gro- durch`) gäbe es keinen Nachweis.
  - Die 5 Ergänzungsstriche vor `als`/`beziehungsweise` bleiben stehen.
- Strichrest nach EQ-6: 0.
- `strich_vor_grossbuchstabe`: 15 Stellen (9 Flussbrüche, 6 Komposita).
- Gegenprobe ohne Nachweis (Fassung 1): 6 schlechter. Mit Liste bleibt 1 schlechter (S. 287).
  Ein lockerer Nachweis auch für Großbuchstaben (Blockanfang) machte 4 Flussbrüche fälschlich zu
  `beispiels-Die` u. a.

*Detektor:*
- Synthetisches PDF (`reportlab`): links unten endet eine Zeile auf `Verteidi-`, rechts oben beginnt
  eine Zeile mit `gung`.
- Docling-Struktur mit `Verteidi-` am Ende von Element 1 und `gung …` am Anfang von Element 2 →
  `Verteidigung`.
- Dieselbe Struktur, aber Element 2 beginnt mit `durch` (Fortsetzung steht anderswo) → unverändert,
  kein Zähler.
- `Fertigkeits- als auch`, Liste mit `als` → unverändert.
- `Karma- Modifikator` mit Quellzeile `Karma-` / `Modifikator` → unverändert,
  `strich_vor_grossbuchstabe = 1`.
- Mutationen machen je einen Fall rot: „Nachweis aus" (`durch`-Fall rot), „Großbuchstabe
  zusammenfügen" und „belegter Großbuchstabe → `X-Y`" (`Karma`-Fall rot). Die letzte Mutation gehört
  ausdrücklich ins Messtor (REQ-EQ-1).
- Ohne `striche.strichrest` → byte-gleich.

**REQ-EQ-7**: *Where, Zierschrift-Umlaut (G5)*
- Wo ein Buch `zeichen.zierumlaut` einschaltet, wird in jeder Zeile **vor** dem Listenabgleich
  (REQ-MB-12) die Folge „Vokal `a o u A O U`, optional ein Leerzeichen, ` . .`" durch den Umlaut des
  Vokals ersetzt.
- *Ziel (korrigiert in Fassung 2):* **3 Zeilen** (S. 9, 10, 20) ändern sich, dadurch 4 Abschnitte,
  4 besser, 0 schlechter. Lesezeichen gefunden 144 → 146.
- S. 216 (`Beschworung . .`, Punkte am Wortende ohne Vokal davor) erfasst die Regel nicht. Welcher
  Vokal gemeint ist, ist aus der Zeile nicht entscheidbar, und Lesezeichen (Mehrzahl) und Zeile
  (Einzahl) unterscheiden sich zusätzlich. Bekannte Grenze, wie S. 1.

*Detektor:*
- Zeilen `U . . ber dies`, `Fu . . r den`, `Stufen/Aktionswu . . rfel` → `Über dies`, `Für den`,
  `Stufen/Aktionswürfel`; Lesezeichen `Über dies` auf dieser Seite → gefunden.
- `Punkt. . Ende` (kein Vokal davor) → unverändert.
- Ohne Schalter → byte-gleich.

**REQ-EQ-8**: *Where, Steuerzeichen*
- Wo ein Buch `zeichen.steuerzeichen` einschaltet, wird in jedem Elementtext jedes Zeichen der
  Unicode-Kategorie `Cc` außer `\n` und `\t` durch ein Leerzeichen ersetzt. Benachbarter Leerraum
  wird zu einem Leerzeichen zusammengefasst.
- *Ziel:* 739 × U+0007 in 241 Abschnitten → 0. Die Fälle sind eine Klasse („nur Leerraum geändert"),
  das Urteil ist gleichwertig bis besser.

*Detektor:* Element `Wirkung: \x07WIL + 5` → `Wirkung: WIL + 5`; `\n` bleibt; ohne Schalter →
byte-gleich.

### C2. Tabellenkopf je Häppchen (Teil 2a, neu in Fassung 2)

**REQ-EQ-21**: *Where, Tabellenkopf-Vorsatz (Fassung 3)*
- Wo ein Buch `tabellenkopf` einschaltet, schreibt das Einlesen für jede Docling-Tabelle mit
  Tabellenkopf (Begriffe) in die Buchdatei:
  - den Zeichenbereich der Tabelle im Abschnittstext und den Bereich ihres **Kopfbereichs**
    (Begriffe);
  - den **Kopftext**: je Kopfzeile die Zellen von links nach rechts, U+00AD entfernt, Leerraum zu einem
    Leerzeichen, leere Zellen weg, direkt aufeinanderfolgende gleiche Zellen (Spannzellen) einmal,
    getrennt durch ` | `; Kopfzeilen durch Zeilenumbruch getrennt, am Ende ein Zeilenumbruch.
- `rag.py index` zerteilt den Abschnittstext wie heute (REQ-MB-14). Jedes Häppchen, dessen
  Zeichenbereich den einer Tabelle überlappt, ohne ihren Kopfbereich ganz zu enthalten, bekommt den
  Kopftext als **Tabellenkopf-Vorsatz**: nach dem Titelvorsatz (REQ-MB-15), vor dem Häppchentext, im
  eingebetteten wie im Prompt-Text.
- Mehrere solche Tabellen in einem Häppchen: Die Vorsätze stehen in Tabellenreihenfolge.
- Der Vorsatz zählt **nicht** zu `CHUNK_SIZE`. Die Zerteilung bleibt zeichengenau (O-12).
- Der Tabellentext selbst bleibt unverändert (Markdown roh; die Schablone ist REQ-EQ-11, Teil 2b).
- Kein Vorsatz entsteht bei Tabellen ohne Kopf; das Protokoll zählt sie mit Seite
  (`tabellen_ohne_kopf`). Ebenso keiner auf Ausnahmeseiten `tabellenkopf.ausnahmen` (REQ-EQ-4).

*Ziel (Vorab-Messung Fassung 3, genau nach diesem Wortlaut):*
- Die Kette läuft wie REQ-EQ-2 bis EQ-6, zerteilt mit 800/150; Ausnahme Index S. 307–311.
- 79 Tabellen, alle im Abschnittstext gefunden.
  - **59** haben einen Kopf. Davon schneiden **52** ein Häppchen ohne Kopfbereich an und bekommen
    einen Vorsatz; 5 sind Index-Ausnahmen, 2 schneidet kein Häppchen so an.
  - **20** haben keinen Kopf (Zeile 0 unmarkiert: Beispielcharaktere, Preis- und Ausrüstungslisten,
    Talentlisten, 3 Werteblöcke).
- **173 Häppchen** bekommen einen Vorsatz. Zuwachs je Häppchen typisch 82, Maximum 260 Zeichen,
  Summe 15.568 (+1,0 % Text); Häppchenlänge mit Vorsatz typisch 882, Maximum 1.060. Die Häppchenzahl
  bleibt gleich.
- 178 Häppchen schneiden eine Tabelle ohne Kopf an und bleiben ohne Vorsatz.
- **Urteil je Tabelle (52), einzeln:**
  - **51 besser**. Davon tragen 41 Titel und/oder Spaltenkopf. Bei 10 ist es nur der Titel, weil
    Docling den Spaltenkopf darunter nicht markiert (S. 106, 110, 112, 118, 119, 124, 156, 219,
    267, 270).
  - **1 gleichwertig**: S. 136, der Kopf ist schon in Docling verstümmelt.
  - **0 schlechter.**
- Die in Fassung 2 übergangenen Spaltenköpfe (S. 39, 96, 153, 231, 260) stehen jetzt mit Titel im
  Kopf. S. 45 hat keinen Kopf mehr, denn die verbundene Datenzeile steht in Zeile 2, und Zeile 0 ist
  unmarkiert.

*Detektor:*
- Synthetische Tabelle: Zeile 0 Titel (eine Spannzelle über alle Spalten), Zeile 1 `column_header`
  `Stufe | Würfel`, 30 Datenzeilen, in einem Abschnitt. `CHUNK_SIZE` ist so klein, dass sie über 3
  Häppchen läuft.
  - Häppchen 2 und 3 tragen nach dem Titelvorsatz den Vorsatz `Titel⏎Stufe | Würfel⏎`, Häppchen 1
    nicht (es enthält den Kopfbereich).
  - Häppchentexte ohne beide Vorsätze sind gleich `zerteile` auf dem Abschnittstext.
- Tabelle mit unmarkierter Zeile 0 und einer Titelzeile in Zeile 2 → kein Vorsatz,
  `tabellen_ohne_kopf = 1`.
- Tabelle mit markierter Zeile 0 und leerer markierter Zeile 1 → Vorsatz nur aus Zeile 0.
- Zwei Tabellen in einem Häppchen ohne Kopfbereich → zwei Vorsätze in Tabellenreihenfolge.
- Kopf mit U+00AD in einer Zelle → Vorsatz ohne U+00AD; die Tabelle wird im Abschnittstext ohne
  U+00AD gefunden.
- Ausnahmeseite → kein Vorsatz.
- Mutationen machen je einen Fall rot: „Vorsatz zählt zu `CHUNK_SIZE`", „nur erste Tabelle je
  Häppchen", „Titelzeile mitten in der Tabelle als Kopf".
- Ohne `tabellenkopf` → Index-Inhalt byte-gleich.

### D. Zahlentreue-Protokoll (Teil 2a, Detektor für 2b)

**REQ-EQ-9**: *Contract, Zahlenprotokoll und Textverlust*
- Für ein Buch mit pdfplumber-Zugriff schreibt das Einlesen je Seite ins Protokoll:
  - **fehlend**: Ziffernfolgen der Quelle ohne Rand (pdfplumber-Wörter, `\d+`) gegen den Text der
    Buchdatei, der dieser Seite zugeordnet ist (`seitenwechsel`, ohne Titelvorsatz). Getrennt nach
    `gar_nicht` (Wert fehlt auf der Seite ganz) und `seltener`;
  - **zusätzlich**: getrennt nach `erfunden` (Wert kommt in der Quelle der Seite nicht vor) und
    `vervielfacht`;
  - **Textverlust**: Zeichen der Quelle ohne Rand, deren Mitte in keinem Docling-Textkasten liegt.
- Summen und die 20 Seiten mit den höchsten Werten stehen in der Konsolenausgabe.
- Der Text ändert sich dadurch **nicht**.
- Ein Buch ohne pdfplumber-Zugriff bzw. ohne Textebene trägt `nicht_gemessen` statt 0.

*Ziel:* Die Zahlen der Vorab-Messung werden reproduziert:
- Quelle 8.490.
- fehlend 199 (gar nicht 178, seltener 21).
- zusätzlich 820 (erfunden 1, vervielfacht 819).
- Textverlust 7.255 Zeichen auf 4 Seiten.

*Detektor:*
- Synthetisches PDF mit `Stufe 3`, `Probe 12` und einer zweiten `12`.
- Dazu Buchtexte mit `Stufe 3` (die 12 fehlt) → `gar_nicht = 1`.
- Mit `Stufe 3, Probe 12, 12, 12` → `vervielfacht = 1`.
- Mit `Stufe 7` → `gar_nicht` 2 und `erfunden` 1 (die 7).
- Ein Zeichen außerhalb aller Kästen → `Textverlust = 1`.
- Buchtext unverändert (Hash).

**REQ-EQ-10**: *Where, Listennummern*
- Wo ein Buch `zeichen.listennummern` einschaltet, beginnt der Text jedes nummerierten
  Listenelements (Docling `list_item` mit `enumerated` und nicht-leerem `marker`) mit der Nummer
  (`marker` + Leerzeichen).
- *Ziel:* fehlende Listennummern 24 → 0 auf S. 37, 130, 139, 221, 225, gemessen mit dem
  Zahlenprotokoll. Gezählt werden geänderte Abschnitte mit Urteil.

*Detektor:* synthetische Docling-Struktur mit nummerierten Elementen (`1.`, `2.`) und einem
Aufzählungspunkt ohne Nummer → `1. …`, `2. …`, der Aufzählungspunkt unverändert; ohne Schalter →
byte-gleich.

### E. Tabellen und Werteblöcke (Teil 2b)

**REQ-EQ-11**: *Where, Tabellen-Schablone*
- Wo ein Buch `tabellen.form = "schablone"` deklariert, wird jede Docling-Tabelle statt als
  Markdown so geschrieben:
  - Zeile 1 ist der **Tabellentitel**: Eine Rasterzeile, deren Zellen alle denselben Text tragen,
    gilt als Titel. Sonst bleibt die Zeile leer.
  - Jede weitere **Datenzeile** wird `Kopf_1: Wert_1; Kopf_2: Wert_2; …`. Kopf sind die
    Spaltenkopf-Zellen (Docling-Kennung, sonst die erste Nicht-Titel-Zeile). Eine Zelle, die über
    mehrere Spalten reicht, erscheint einmal. Leere Zellen entfallen. Ist Kopf = Wert oder ist der
    Kopf leer, steht nur der Wert.
  - Es gibt keinen Füll-Leerraum.
- Die Tabelle bleibt an ihrer Stelle in der Lesefolge (REQ-EQ-3).

*Ziel (Vorab-Messung):*
- Tabellentext 261.238 → ≤ 110.000 Zeichen.
- Häppchen mit Tabellenteil ohne Spaltennamen (bei 800/150): 316 → 0. Jede vollständige Datenzeile
  trägt ihre Spaltennamen.
- Vervielfachte Zahlen in Tabellen (Zahlenprotokoll, Tabellenseiten): 665 → 0, ohne die
  Kopfwiederholung, die gesondert gezählt wird.
- Zeilenlänge der Schablone (ohne Titel) gemessen: typisch 85, p95 177, Maximum 712 Zeichen. 938 von
  1.117 Zeilen sind höchstens `CHUNK_OVERLAP` lang und stehen damit sicher vollständig in einem
  Häppchen.
- Urteil nach REQ-EQ-1: Hier ändern sich **alle 58 Tabellenseiten**. Die Regel-Messung urteilt je
  Tabelle (79), nicht je Abschnitt (O-4).

*Detektor:*
- Synthetisches Raster 3×3 mit Titelzeile (Spannzelle über 3 Spalten), Kopfzeile `Stufe | Würfel |
  Bemerkung` und einer Spannzelle über 2 Spalten in Zeile 3.
- Erwartet: genau der Text `Titel⏎Stufe: 1; Würfel: W6; Bemerkung: –⏎Stufe: 2; Würfel: W8` (Spannzelle
  einmal). Kein Doppelleerzeichen.
- Ohne Schalter → Markdown byte-gleich zu heute.

**REQ-EQ-12**: *Contract, Zahlentreue der Schablone*
- Für jede Tabelle in Schablonenform gilt:
  - Die Ziffernfolgen der Datenzellen (jede Spannzelle einmal) stehen in der Schablone **genau so oft
    wie im Raster**.
  - Ziffernfolgen der Kopf- und Titelzellen stehen in der Schablone je Datenzeile höchstens einmal.
  - Sonst steht keine Ziffernfolge in der Schablone.
- Das Protokoll zählt je Tabelle `zahlen_raster`, `zahlen_schablone`, `abweichung`. Bei einer
  Abweichung ungleich 0 bricht das Einlesen mit `KonfigFehler` ab (Seite und Tabelle in der Meldung,
  keine Buchdatei).

*Detektor:*
- Raster aus REQ-EQ-11 → `abweichung = 0`.
- Mutation „Spannzelle je Spalte wiederholen" → `KonfigFehler`.
- Mutation „leere Zelle als 0 schreiben" → `KonfigFehler`.

**REQ-EQ-13**: *If/Then, doppelte Tabelle aus Bild-Kindern*
- Wenn auf einer Seite ein Text-Kind eines Bild-Elements (REQ-MB-27) mit seiner Kastenmitte im Kasten
  einer Docling-Tabelle derselben Seite liegt, dann wird dieses Kind **nicht** übernommen. Die
  Tabelle trägt den Inhalt.
- Das Protokoll zählt die entfallenen Kinder je Seite.
- *Ziel:* 1 Tabelle (S. 20), 41 Kinder entfallen. Vervielfachte Zahlen auf S. 20: 154 → 0. Urteil in
  der Regel-Messung.

*Detektor:* synthetische Seite: Bild-Element mit 3 Text-Kindern, 2 davon im Kasten einer Tabelle →
nur das dritte Kind steht im Text, Protokoll = 2; Kind knapp außerhalb (1 pt) → bleibt.

**REQ-EQ-14**: *Where, Werteblock-Zeilen aus der Quelle*
- Wo ein Buch `werteblock.schluessel` deklariert (Liste, z. B. `["Stufe:", "Aktion:", …]`; Daten),
  wird jedes Text-Element, dessen Docling-Text **zwei oder mehr** deklarierte Schlüssel enthält, aus
  den pdfplumber-Zeichen seines Kastens neu gebildet:
  - Zeilen nach Grundlinie, Wörter nach x.
  - Eine Lücke über 15 pt wird zu `; `.
  - Zeilen werden mit `; ` verbunden.
- Werteblöcke, die Docling als Tabelle liefert, folgen der Tabellen-Schablone (REQ-EQ-11).
- Das Protokoll zählt die Werteblock-Paare der Quelle (fetter Schlüssel aus der Liste + Wert),
  getrennt in `intakt` und `getrennt`.

*Ziel (Vorab-Messung):*
- Paare 2.652, intakt 2.620 → 2.629 (die 9 getrennten `Aktion:`-Paare auf S. 114–119 sind behoben).
- Die 16 Zeichenersetzungen durch Docling bleiben (siehe Abgrenzung).
- Elemente mit einem Paar bleiben byte-gleich.

*Detektor:*
- Synthetisches PDF mit der Zeile `Stufe: Rang+X ⇥ Aktion: Standard` und der Zeile
  `Überanstrengung: 0 ⇥ Kosten: Novize`.
- Docling-Struktur mit den Texten `Stufe: Rang+X Aktion:` und `Überanstrengung: 0 Kosten: Novize
  Standard` → `Stufe: Rang+X; Aktion: Standard; Überanstrengung: 0; Kosten: Novize`; Protokoll
  `getrennt = 0`.
- Element mit nur `Stufe: Rang+X` → unverändert.

### F. Nicht-funktional

**REQ-EQ-15**: *If/Then, Schema der Spec-2-Deklaration*
- Wenn `lesefolge`, `striche`, `zeichen`, `tabellenkopf`, `tabellen` oder `werteblock` gegen ihr Schema verstoßen,
  bricht das Einlesen ab wie in REQ-MB-34: `KonfigFehler` vor dem Schreiben, die Meldung nennt den
  Schlüssel.
- Schema:
  - `lesefolge`: `spalten` (Liste ≥ 1 von Bereichen `[a, b]`, `a < b`, aufsteigend, nicht
    überlappend), `toleranz` (Zahl ≥ 0, Default 4), `waechter` (Zahl in (0, 1], Default 0,8),
    `ausnahmen` (Liste ganzer Zahlen ≥ 1);
  - `tabellenkopf`: Objekt mit optional `ausnahmen` (Liste ganzer Zahlen ≥ 1);
  - `striche`: `zeilenenden`, `strichrest` (Wahrheitswerte);
  - `zeichen`: `zierumlaut`, `steuerzeichen`, `listennummern` (Wahrheitswerte);
  - `tabellen`: `form` ∈ {`markdown`, `schablone`};
  - `werteblock`: `schluessel` (nicht-leere Liste nicht-leerer Zeichenketten);
  - keine anderen Schlüssel.

*Detektor:* je ein Verstoß (Tippfehler `spalte`, Bereich `[292, 35]`, überlappende Spalten, `form:
"md"`, `zierumlaut: "ja"`) → `KonfigFehler`, keine Buchdatei bzw. die alte byte-gleich. Mutation
„Schemaprüfung aus" → rot.

**REQ-EQ-16**: *If/Then, Abschaltbarkeit und Rückwärtskompatibilität*
- Wenn ein Buch keine Spec-2-Deklaration trägt, dann ist seine Buchdatei (`knowledge.jsonl`)
  **byte-gleich** zum Einlesen mit dem Stand vor dieser Spec.
- Das Einlese-Protokoll behält alle bisherigen Felder mit gleichen Werten. Neue Felder dürfen mit
  Leerwerten hinzukommen. Ausnahme: Das Zahlenprotokoll (REQ-EQ-9) erscheint bei jedem Buch mit
  pdfplumber-Zugriff. Es ändert keinen Text.
- Jede Regel lässt sich einzeln abschalten. Abgeschaltet ändert sie keinen Text.
- Altbestände, der rohe PDF-Weg und alle Referenzen von REQ-MB-3 bleiben unverändert. Die bestehende
  Suite einschließlich `test_mutationen.py` und `messung/` bleibt ohne Änderung ihrer Sollwerte grün.

*Detektor:*
- Synthetischer Zwei-Bücher-Bestand, nur Buch A mit Spec-2-Deklaration → Buch B byte-gleich zum
  Lauf auf dem Stand vor dieser Spec (im Test mit abgeschalteten Regeln erzeugt).
- Je Regel ein Lauf mit nur dieser Regel aus → nur deren Fall ändert sich.
- Bestehende Suite unverändert.
- Am echten Buch (manuell, Messgleichheit REQ-EQ-2): ohne Spec-2-Deklaration Hash gleich dem
  Spec-1-Stand.

**REQ-EQ-17**: *Architektur, generisch*
- Jede Wirkung ist mit einem synthetischen Buch ohne Earthdawn-Bezug erreichbar.
- Spaltenraster, Wächteranteil, Ausnahmeseiten, Konjunktionen, Werteblock-Schlüssel und Schalter
  sind Daten.
- Es gibt keinen Code-Pfad, der nur bei bestimmten Buch- oder Bestandsnamen wirkt.

*Detektor:* alle Tests dieser Spec mit Bestand `testwelt` und Fassungen `alpha`/`beta`; Umbenennen
aller Bezeichner in den Testdaten ändert kein Ergebnis.

**REQ-EQ-18**: *Architektur, Urheberrecht*
- Wie REQ-MB-18: Kein Test liest echte Bücher oder `DATA_DIR`.
- Die Vorab- und Regel-Messungen legen im Repo nur Zahlen, Seiten, Koordinaten, Versionen und kurze
  Stichworte ab, keinen Buchtext.
- Messskripte, die das echte Buch lesen, liegen nicht im Repo.

*Detektor:* `test_schutz.py` deckt die neuen Schreibpfade (Protokollfelder) ab. Das Formattest von
REQ-EQ-1 weist Textfelder über 40 Zeichen in `vorabmessung.json` zurück.

**REQ-EQ-19**: *Vorbedingung, Versionen*
- Die Spec-2-Regeln gelten nur für die Docling- und pdfplumber-Version ihrer Vorab-Messung (heute
  2.131.0 / 0.11.10, dieselben wie Spec 1).
- Ein Buch mit Spec-2-Deklaration und abweichender oder fehlender Version (bzw. fehlender
  Spec-2-`vorabmessung.json`) bricht mit `KonfigFehler` ab (Mechanismus wie REQ-MB-23).
- Bücher ohne Spec-2-Deklaration prüfen nur gegen Spec 1.

*Detektor:* wie REQ-MB-23, Version injiziert, je gleich / abweichend / fehlend; Buch ohne
Spec-2-Deklaration liest trotz fehlender Spec-2-Datei ein.

**REQ-EQ-20**: *Performance*
- Gemessen über die Seiten des Zielbuchs (bzw. eines synthetischen Buchs gleicher Elementzahl je
  Seite).
- Zusatzzeit aller Spec-2-Regeln je Seite, ohne Docling und ohne Öffnen der PDF in pdfplumber:
  **typisch ≤ 20 ms, Maximum ≤ 200 ms**.
- Braucht eine Regel pdfplumber bei einem Buch, das ohne sie keine Schriftzuordnung hätte: pdfplumber
  je Seite typisch ≤ 0,1 s, Maximum ≤ 0,5 s (Spec 1 gemessen: 0,06 / 0,29 s).
- Die Wirkungszähler (REQ-EQ-2) dürfen das Einlesen des Zielbuchs (heute 152 s Docling + 25 s
  Zuordnung) um höchstens 10 % verlängern.
- Retrieval-Zeiten (REQ-MB-19) bleiben unberührt.

*Detektor:* Messskript mit typisch und Maximum je Seite (beide Zahlen im Ergebnis); Zeittests zählen
in Mutationsproben nicht als Fang (wie REQ-MB-19).

## Lesarten (Entwurf, zur Bestätigung)

- **EQ-1** „Vor der Abnahme" heißt: Die Regel-Messung liegt im Spec-Ordner in einem Commit, der
  **vor** dem Implementierungs-Commit der Regel liegt. Messtor und Messgleichheit (EQ-2) sind
  Review-Schritte, kein Code, der eine Messdatei liest. Ein Beobachtungspunkt, den dieselbe Änderung
  mitziehen kann, ist keiner.
- **EQ-3** Die zeilenweise Folge im 2×2-Werteblock (156 Fälle) gilt als gleichwertig: Die Paare
  bleiben ganz (mechanisch belegt nach REQ-EQ-1).
- **EQ-3** „Teilweise besser" zählt als besser, wenn das bewegte Stück im richtigen Unterabschnitt
  näher an seiner Fortsetzung steht als in der Docling-Folge und keine andere Fuge schlechter wird.
  Die Messung weist solche Fälle getrennt aus (5).
- **EQ-21** „Anschneiden" heißt: Der Zeichenbereich des Häppchens überlappt den der Tabelle.
  „Kopfbereich ganz enthalten" heißt: Die ersten zwei Markdown-Zeilen der Tabelle liegen ganz im
  Häppchen. Ein Häppchen, das nur den Anfang des Kopfbereichs enthält, bekommt also den Vorsatz.
- **EQ-5** „Wort" heißt: eine Folge von Buchstaben, Ziffern und `_` (`\w+`).
- **EQ-5/-6** „Konjunktionsliste" ist die von REQ-MB-11 (`reparatur.konjunktionen` ersetzt den
  Sprach-Default). Die Ergänzung um `als`/`beziehungsweise` ist Teil der Buchdeklaration, nicht des
  Codes.
- **EQ-9** Ziffernfolgen sind `\d+` auf Wortebene. `5/10` sind zwei Zahlen, `W12+2W6` vier.
- **EQ-11** Docling-Kennungen für Spaltenköpfe (`column_header`) haben Vorrang. Die Regel „erste
  Nicht-Titel-Zeile" ist der Rückfall und wird im Protokoll gezählt.

## Abgrenzung (nicht in Spec 2)

- **Hausregeln** als Markdown (Art neu/ergänzt/ersetzt, Bezug, feste Mitlieferung): eigene Spec.
- **FTS5-Trigram bzw. Komposita-Suche** und **Earthdawn-Golden-Set**: Spec 3. Ohne Golden Set ist
  der Nutzen der Tabellen-Schablone für das Retrieval **nicht** messbar; Spec 2 misst nur Form und
  Zahlentreue (O-1, O-4).
- **Kreaturenwerte:** Im Zielbuch gibt es keine, vom Kreaturenband liegt nur eine 6-seitige Probe
  vor. Die Werteblock-Regel (EQ-14) ist generisch; eine Messung folgt mit dem Buch.
- **OCR-Vertauschungen** (Fehlerklasse 3, REQ-MB-12) und OCR-Bücher allgemein.
- **Inhaltsverzeichnis** S. 3/4 (Docling `document_index`, 7.144 Zeichen, 150 Zahlen): fällt weiter
  weg. Die Gliederung kommt aus den Lesezeichen (Entscheidung O-7).
- **Docling-Zeichenersetzung** von Gedanken- und Anführungszeichen (691 Gedankenstriche → `-`;
  16 Werteblock-Paare betroffen): nicht rückgängig gemacht, nur als Grenze dokumentiert.
- **Index S. 307–311 als Tabelle** (je Seite eine Docling-Tabelle; die längste Tabelle des Buchs, 27.521 Zeichen, ist dagegen der Beispielcharakter S. 49): Die Schablone behandelt
  ihn wie jede Tabelle. Ein Ausschluss über `inhaltsart` ist Datensache.
- **Elementtext ganz aus pdfplumber:** Am Prototyp waren 218 von 6.037 Elementen anders (Stichprobe
  2/12 schlechter). Spec 2 verwendet pdfplumber nur gezielt (EQ-5, EQ-14).
- **G4** Impressumzeile S. 313: netto neutral (Spec 1). Bleibt.
- **S. 117**: 2 Zeilen am Spaltenende fehlen in Docling (108 Zeichen). Das Zahlenprotokoll zeigt es
  (EQ-9), eine Reparatur ist nicht vorgesehen (O-8).

## Bekannte Grenzen (vorab)

- **REQ-EQ-3** kennt keine Kästen und keine Werte-Raster. Den zweispaltigen Kasten (S. 237) und den
  Tabellenkopf aus Text-Elementen (S. 274) fangen Ausnahmeseiten, überbreite Blöcke und Werte-Raster
  der Seitenwächter. „Kasten nach Einzug" ist gemessen gescheitert (S. 20).
- **REQ-EQ-3** lässt mehrspaltige Elemente an ihrer Docling-Stelle. Sie halten Text beider Spalten.
  Daher bleiben 9 Flussbrüche (`strich_vor_grossbuchstabe`), und 5 Fälle sind nur teilweise besser.
  Abhilfe wäre die Teilung an `charspan` (O-10).
- **REQ-EQ-6** fügt `X- Großbuchstabe` nie zusammen; 6 echte Komposita bleiben mit `- `.
- **REQ-EQ-5** lässt 16 mehrdeutige Fälle stehen (dieselbe Form mehrfach im Element, z. B.
  `SpruchzaubereiProbe` zweimal auf S. 197), dazu 5 nicht gefundene. Eine Zuordnung über die
  Position statt über die Eindeutigkeit wäre eine neue Regel (O-17).
- **Docling und Regel liegen beide falsch, keine Verschlechterung** (Gegenprüfung 2):
  - S. 284: Ein mehrspaltiges Element verbindet den Anfang von „Astendar" mit der Einleitung der
    Passionen.
  - S. 111 und S. 141: Ein Seitenkasten steht vor der Fortsetzung des Fließtexts.
- **REQ-EQ-21:** 10 Tabellen tragen nur den Titel als Kopf (Spaltenkopf in Docling nicht markiert),
  20 Tabellen haben keinen Kopf (178 Häppchen ohne Vorsatz). Docling verschmilzt Kopf und erste
  Datenzeile ungekennzeichnet auf S. 263, 265, 266 (Tabellen ohne Kopf, also kein Vorsatz).
- **REQ-EQ-21** gibt 20 Tabellen ohne Docling-Kopf (178 Häppchen) keinen Vorsatz (O-11).
- **REQ-EQ-5** findet Fälle nur, wenn Docling-Form und pdfplumber-Wörter übereinstimmen. 5
  echte Striche und 1 Trennung wurden nicht gefunden. Laufweiten-Artefakte von pdfplumber (gemessen
  5 Werteblock-Paare) können Fälle verdecken.
- **REQ-EQ-7** löst S. 216 nicht (Punkte am Wortende ohne Vokal davor, Ein-/Mehrzahl).

## Entscheidungen (Tobias, 2026-10-23)

- **O-1 (b)** Schnitt: Spec 2a jetzt (EQ-1 bis EQ-10, EQ-15 bis EQ-21), Spec 2b danach (EQ-11 bis
  EQ-14), IDs stabil. Das Zahlenprotokoll (EQ-9) liegt in 2a als Detektor für 2b.
- **O-4 (a)+(b)** Tabellen-Schablone: Urteil je Tabelle von Hand jetzt; ein Retrieval-Vergleich mit
  dem Golden Set aus Spec 3 ist Bedingung, bevor sie am Zielbuch eingeschaltet wird.
- **O-6 (a)** Steuerzeichen und Listennummern in 2a.
- **O-7 (a)** Inhaltsverzeichnis S. 3/4 bleibt weg.
- **O-8 (a)** Textverlust S. 117 nur zählen.
- **O-9 (b)** Werteblock-Regel (EQ-14) erst mit dem Kreaturenband.
- **Vorgaben Fassung 2:**
  - Bandgrenzen an erkannten Überschriften.
  - Vollständige Einzelmessung.
  - Strichrest nur mit pdfplumber-Nachweis, `als`/`beziehungsweise` in die Liste.
  - Umlaut-Zahl korrigiert.
  - Tabellenkopf je Häppchen in 2a (EQ-21).

## Offene Entscheidungen (Fassung 3)

**O-2 (neu gefasst): Ausnahmen der Lesefolge, Ausnahmeseiten oder Erkennung?**
- (a) Seitenwächter (generisch) + 2 deklarierte Ausnahmeseiten (S. 237, 274), wie gemessen.
- (b) Alle 10 Problemseiten deklarieren (S. 58, 237, 274, 299, 300, 302–305, 312), kein Wächter.
- (c) Zusätzliche Erkennung für zweispaltige Kästen (zwei Bildkästen gleicher Höhe nebeneinander als
  Band) und Tabellenköpfe aus Text-Elementen, neu messen.
- **Empfehlung (a):** Der Wächter ist generisch und gemessen ohne Preis. Er greift auf 27 Seiten,
  verhindert die Umordnung genau auf den 8 Seiten, wo sie schaden würde (S. 58, 299, 300, 302–305,
  312), und ändert auf den 19 übrigen nichts; neue Bücher bekommen ihn mit. Für die 2 Einzelseiten ist eine Erkennung teurer als die Deklaration, und jede neue
  Erkennung braucht ein eigenes Messtor (Lehre MB-31, Kasten-Einzug S. 20).

**O-3 (neu gefasst): Klassen im Messtor.**
- (a) Nur die 2×2-Werteblock-Klasse mit mechanischem Beleg (wie jetzt in REQ-EQ-1).
- (b) Keine Klasse, auch die 156 Werteblock-Tausche einzeln.
- **Empfehlung (a):** Der Beleg ist kein Stichprobenschluss. Er prüft für jeden der 156 Fälle, dass
  genau zwei `Schlüssel: Wert`-Zeilen im selben Lauf getauscht sind. Die Gegenprüfung fand in ihrer
  Stichprobe 20/20 gleichwertig.

**O-5 (neu gefasst): Strichrest (REQ-EQ-6).**
- (a) Mit pdfplumber-Nachweis und ergänzter Liste, Großbuchstaben nur zählen (wie jetzt).
- (b) Nachweis auch für Großbuchstaben, nur über die Folgezeile derselben Spalte.
- (c) Weglassen, nur Verdachtszähler.
- **Empfehlung (a):** 32/32 besser, 0 schlechter. (b) brächte am Zielbuch 0 zusätzliche Treffer
  (alle 15 Großbuchstaben-Stellen haben keine Folgezeile in derselben Spalte) bei mehr Regelfläche.

**O-10: Teilung mehrspaltiger Elemente an `charspan`.**
- (a) Nicht in Fassung 2; die mehrspaltigen Elemente bleiben an ihrer Docling-Stelle (wie gemessen).
- (b) Als eigene Regel EQ-22 in 2a mit eigenem Messtor.
- **Empfehlung (a) jetzt, (b) als Nachtrag:**
  - Die Teilung schließt die 9 Flussbrüche und die 2 Teilfälle, die Fugen zeigen es (`einset- ‖ zen`).
  - Sie ändert aber 238 Fälle, davon 91 einzeln zu beurteilen.
  - An Kastengrenzen mitten im Wort zerreißt sie Wörter (`verbleib ‖ nden`). Das braucht eine
    eigene Regel: dort nicht teilen oder ohne Leerzeichen fügen.
  - 104 Elemente auf 94 Seiten sind betroffen.

**O-11: Tabellen ohne Docling-Kopf (REQ-EQ-21).**
- (a) Kein Vorsatz, nur gezählt (wie gemessen).
- (b) Rückfall „erste Rasterzeile" als Kopf.
- **Empfehlung (a):** Der Rückfall (Messung Fassung 2) erfasste 331 Häppchen mit 183.564 Zeichen.
  Bei Tabellen ohne Kopfzeile wiederholt er eine **Datenzeile** in jedem Häppchen und vervielfacht
  deren Zahlen. Die betroffenen Tabellen (Beispielcharaktere, Preislisten) sind Fälle für die
  Schablone in 2b.

**O-12: Zählt der Tabellenkopf-Vorsatz zu `CHUNK_SIZE`?**
- (a) Nein, wie der Titelvorsatz (REQ-MB-14): Die Zerteilung bleibt zeichengenau, nur der Text
  wächst.
- (b) Ja: Die Zerteilung richtet sich nach Text + Vorsatz.
- **Empfehlung (a):**
  - Mit (b) würden alle Tabellenabschnitte neu zerteilt, und die Grenzen hingen vom Vorsatz ab, eine
    zweite Größe neben MB-14.
  - Ein Vorsatz bis 260 Zeichen (Fassung 3) ließe für den Tabellentext nur 540 von 800 Zeichen.
  - Bei (a) wächst das größte Häppchen auf 1.060 Zeichen; das trägt jedes Embedding-Modell des
    Repos.

**O-13: Index-Ausnahme für den Tabellenkopf.**
- (a) `tabellenkopf.ausnahmen = [307 … 311]` deklarieren (wie gemessen).
- (b) Regel: kein Vorsatz, wenn die Kopfzeile Ziffern-Spalten wie die Datenzeilen hat.
- **Empfehlung (a):** Eine Regel nur für den Index wäre neue Regelfläche mit eigenem Messtor; der
  Index ist ein Seitenbereich, und die Deklaration ist Daten.

**O-14: Bekannte Grenze S. 216 (Zierschrift-Umlaut).**
- (a) Als Grenze führen.
- (b) Regel „Punkte am Wortende → Umlaut auf dem einzigen Kandidaten-Vokal", neu messen.
- **Empfehlung (a):** `Beschworung` hat zwei Kandidaten (`o`, `u`), die Regel kann nicht entscheiden.
  Selbst richtig umgesetzt fände der Listenabgleich das Lesezeichen nicht (Ein- und Mehrzahl,
  2 Auslassungen > k = 1).

**O-15: Sicherung im Konjunktionsfall von EQ-5.**
- (a) `L- R` nur, wenn `LR` im Buch sonst nicht als Wort vorkommt (wie gemessen).
- (b) Keine Sicherung (Fassung-2-Wortlaut).
- (c) Konjunktionsfall ganz streichen (`LR` immer).
- **Empfehlung (a):** 0 schlechter. Ohne Sicherung wäre S. 296 schlechter (`Thro- als`). Mit (c)
  blieben die 6 echten Ergänzungsstriche zusammengezogen (`Fadenwebenoder`, `Dorfund` …). Das wäre
  nicht schlechter als heute, aber 6 Verbesserungen fielen weg.

**O-16: Umfang des Tabellenkopfs (EQ-21).**
- (a) Markierte Zeilen ab Zeile 0, Titel- und `column_header`-Zeilen zusammen (wie gemessen):
  173 Häppchen, 52 Tabellen.
- (b) Nur `column_header`-Zeilen: 150 Häppchen, 40 Tabellen. Die Titel fehlen, und 12 Tabellen mit nur
  einem Titel bekommen nichts.
- (c) Nur die erste markierte Zeile mit Text (Fassung-2-Prototyp): ebenfalls 173 Häppchen, aber bei
  28 Tabellen mit mehrzeiligem Kopf nur dessen erste Zeile (meist der Titel ohne Spaltenkopf).
- **Empfehlung (a).** Die Fassung-2-Begründung gegen „alle Kopfzeilen" (25 Tabellen mit Datenzeile
  im Kopf) war ein Artefakt des Skripts (Markdown-Zeile statt Rasterzeile). Am Raster gemessen
  enthält kein Kopf eine Datenzeile.

**O-17: Mehrdeutige Fälle in EQ-5 (16).**
- (a) Stehen lassen und zählen (wie jetzt).
- (b) Fall über die Zeichenposition im Element zuordnen.
- **Empfehlung (a):** (b) bräuchte eine Abbildung von Quellzeichen auf Elementtext-Positionen. Das ist
  neue Regelfläche mit eigenem Messtor für 16 Stellen, die heute unverändert und damit nicht
  schlechter sind.

## Erledigte Entscheidungen Fassung 1 (Verlauf)

Die Fassung-1-Optionen zu O-2 (Ausnahme S. 53), O-3 (Klasse „Spaltenrücksprung") und O-5 (Strichrest
ohne Nachweis) sind durch die Gegenprüfung überholt. S. 53 ändert sich mit Fassung 2 nicht mehr.

## Tier

**T3**, ohne Tier-Map wie Spec 1 (O-9 b dort). `derive-tier.js` findet keine Map (Exit 2), es greift
die Regel „unbekannter Pfad → höchste Stufe". Inhaltlich passt das: Es geht um den Einlese-Contract
aller Mehr-Bücher-Bestände und um Texte, die in den Index gehen. Ohne CI-Anker wird nicht
server-seitig nachgerechnet; maßgeblich ist Tobias' Abnahme jedes Merges.
