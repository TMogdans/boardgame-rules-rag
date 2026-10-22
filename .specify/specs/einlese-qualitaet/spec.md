# Spec: Einlesequalität: Lesereihenfolge, Tabellen und Werteblöcke, Zahlentreue

- **Spec-ID:** einlese-qualitaet (Spec 2; Schnitt-Vorschlag 2a/2b siehe O-1)
- **Kontext-Kürzel:** EQ
- **Tier:** T3 (siehe Abschnitt „Tier")
- **Status:** **Entwurf Fassung 1, nicht abgenommen.** Die Vorab-Messung liegt daneben
  (`vorabmessung.md`, `vorabmessung.json`). Offene Entscheidungen O-1 bis O-9 stehen am Ende.

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

## Begriffe

| Begriff | Bedeutung |
|---|---|
| **Regel** | Eine Korrektur dieser Spec (EQ-3 bis EQ-14), je Buch einzeln eingeschaltet. |
| **Spec-2-Deklaration** | Die neuen Schlüssel eines Buchs in `spiel.json` (Entwurf: `lesefolge`, `striche`, `zeichen`, `tabellen`, `werteblock`; Schema REQ-EQ-15). Fehlt ein Schlüssel, ist die zugehörige Regel aus. |
| **Spaltenraster** | Je Buch deklarierte x-Bereiche der Satzspalten in PDF-Punkten, z. B. `[[35, 292], [304, 560]]`, dazu eine Toleranz. |
| **Spalte eines Elements** | Spalte *i*, wenn der **erste** Kasten des Elements in `[a_i − tol, b_i + tol]` liegt; sonst ist das Element **spaltenübergreifend**. |
| **Band** | Bereich einer Seite zwischen zwei spaltenübergreifenden Elementen (nach Oberkante). |
| **Abschnittsänderung** | Ein Abschnitt verliert oder gewinnt Elemente gegenüber dem Lauf ohne die Regel. Ein Abschnitt, dessen Elementmenge gleich bleibt, dessen Text sich aber ändert (Folge innen, Zeichen), heißt **Textänderung**. |
| **Urteil** | Von Hand am Seitenbild: `besser`, `gleichwertig`, `schlechter`, `strittig`. „Strittig" zählt für das Messtor wie `schlechter`, bis Tobias anders entscheidet. |
| **Regel-Messung** | Der Abschnitt der Vorab-Messung für eine Regel: Prototyp am echten Buch, Zählung, Urteile (REQ-EQ-1). |
| **Zeilenend-Strich** | In der Quelle (pdfplumber-Zeile) endet eine Zeile auf Buchstabe oder Ziffer + `-`, und die nächste Zeile derselben Spalte gehört zum selben Docling-Element. |
| **Werteblock** | Folge kurzer `Schlüssel: Wert`-Zeilen unter einer Überschrift (Talent, Zauber, Fertigkeit). Die Schlüssel sind Daten des Buchs. |
| **Werteblock-Paar** | Schlüssel + Wert einer Werteblock-Zeile der Quelle. Es ist **intakt**, wenn `Schlüssel Wert` (Leerraum normalisiert) im Text der Seite steht. |
| **Tabellen-Schablone** | Textform einer Tabelle: je Rasterzeile eine Zeile mit `Spaltenkopf: Zellwert`-Paaren (REQ-EQ-10). |
| **Zahlenprotokoll** | Vergleich der Ziffernfolgen (`\d+`) je Seite zwischen Quelle und Buchdatei (REQ-EQ-9). |

## Akzeptanzkriterien

### A. Messtor und Wirkungszähler (für alle Regeln)

**REQ-EQ-1**: *Vorbedingung, Messtor je Regel*
- Für jede Regel EQ-3 bis EQ-14 liegt **vor der Abnahme** des Commits, der sie umsetzt, eine
  Regel-Messung im Spec-Ordner (`vorabmessung.json`, Schlüssel `regeln.<REQ-ID>`).
- Gemessen wird am echten Zielbuch, mit den Docling- und pdfplumber-Versionen von REQ-EQ-19.
- Die Regel-Messung enthält:
  - die Zahl der **Abschnittsänderungen** und der **Textänderungen**, mit Seiten;
  - je Abschnittsänderung ein Urteil (alle beurteilt, keine Stichprobe);
  - für Textänderungen ein Urteil je Fall oder je dokumentierter Fallklasse. Eine Fallklasse braucht
    eine automatische Abgrenzung (z. B. „nur Werteblock-Zeilen umgestellt") und eine Stichprobe von
    mindestens 10 Fällen bzw. allen, wenn es weniger sind. Fälle außerhalb jeder Klasse werden
    einzeln beurteilt;
  - die Bilanz `besser / gleichwertig / schlechter / strittig`.
- **Ziel:** `schlechter + strittig = 0`. Sonst entscheidet Tobias **vor** dem Weiterbauen: Regel
  ändern und neu messen, Ausnahme deklarieren (REQ-EQ-4) oder Regel streichen.
- Die Zielzahlen der Kriterien unten stammen aus der Vorab-Messung Fassung 1. Sie gelten als
  **Erwartung**, nicht als Spielraum.

*Detektor:*
- `vorabmessung.json` enthält für jede umgesetzte Regel den Schlüssel mit den Feldern
  `abschnittsaenderungen`, `textaenderungen`, `seiten`, `urteil{besser, gleichwertig, schlechter,
  strittig}`, und zwar bevor ein Commit die Regel umsetzt (Prüfung im Review über die
  Git-Historie).
- Ein Test prüft das Format: Zahlen nichtnegativ, Summe der Urteile = Zahl der beurteilten Fälle,
  nur Zahlen und Versionen (REQ-EQ-18).

**REQ-EQ-2**: *Contract, Wirkungszähler und Messgleichheit*
- Das Einlese-Protokoll zählt je eingeschalteter Regel die Abschnittsänderungen und Textänderungen
  mit Seiten. Verglichen wird mit einem Lauf, in dem nur diese Regel aus ist.
- Die Regeln wirken in fester Reihenfolge: EQ-8, EQ-10, EQ-13, EQ-14 (Elementtexte), EQ-3/-4
  (Folge), EQ-7 (Zeilen vor dem Listenabgleich), EQ-11 (Tabellentext), EQ-5, EQ-6 (Striche).
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

**REQ-EQ-3**: *Where, Spaltenraster und Bandregel*
- Wo ein Buch `lesefolge.spalten` deklariert, ordnet das Einlesen die Elemente jeder Seite (ohne
  Randzeilen, REQ-MB-28) neu:
  1. Die spaltenübergreifenden Elemente teilen die Seite nach der Oberkante ihres ersten Kastens in
     Bänder.
  2. In jedem Band kommen die Elemente der Spalten von links nach rechts. Innerhalb einer Spalte
     zählt die Oberkante des ersten Kastens, bei Gleichstand die Docling-Folge.
  3. Danach folgt das spaltenübergreifende Element, das das Band abschließt.
  4. Ein Element ohne Lage behält seinen Platz hinter seinem Docling-Vorgänger.
  5. Randzeilen bleiben unberührt (sie werden nach REQ-MB-28 verworfen).
  6. Bild-Elemente sind keine Bandgrenze. Text aus Bild-Elementen (REQ-MB-27) wird wie jedes andere
     Element einsortiert.
- Erst danach laufen Listenabgleich, Layout-Überschriften und Zerschneiden (REQ-MB-12, -20, -14).

*Ziel (Vorab-Messung):*
- Am Zielbuch ändern sich **25 Abschnitte auf 11 Seiten** (58 Elemente wechseln den Abschnitt):
  23 besser, 2 strittig (S. 53, Kasten, siehe REQ-EQ-4), 0 schlechter.
- Abschnittsköpfe nach ihrem Inhalt: 3 → 0 (S. 76, 114, 190).
- Tabelle in einem fremden Abschnitt: 1 → 0 (S. 22).
- Unter „Talentbeschreibungen" stehen 149 Talente (statt 148).
- Gleich bleiben: Abschnittszahl 539, Lesezeichen gefunden 144, Layout-Stufen 386/5.
- Textänderungen: 193. Davon sind 156 nur umgestellte Werteblock-Zeilen (gleichwertig) und 25
  Spaltenrücksprünge der Docling-Folge (Stichprobe 3/3 besser). 12 sind noch nicht beurteilt und
  müssen in der Regel-Messung beurteilt werden.
- Zusatzzeit je Seite: typisch 0,02 ms, Maximum 0,2 ms.

*Detektor:* synthetische Seiten mit Kästen in absichtlich falscher Docling-Folge:
- (a) Eine spaltenübergreifende Überschrift oben kommt nach dem ersten Element der linken Spalte →
  sie steht zuerst, das Element liegt in ihrem Abschnitt.
- (b) Der Kopf der rechten Spalte kommt als Bild-Kind am Seitenende → er steht hinter der linken
  Spalte und vor der nächsten spaltenübergreifenden Überschrift.
- (c) Eine Tabelle oben rechts kommt hinter allen Absätzen der Seite → sie liegt im Abschnitt der
  Überschrift über ihr.
- (d) Ein Bild reicht über beide Spalten, rechts daneben steht ein schmales Element → dieses folgt
  dem Ende der linken Spalte.
- (e) Ein 2×2-Werteblock mit gleichen Oberkanten → zeilenweise Folge.
- (f) Ohne `lesefolge` → Folge und Buchdatei byte-gleich zum Lauf vor dieser Spec.
- Mutationen „Bänder ignorieren", „rechte vor linke Spalte" und „Oberkante des letzten statt des
  ersten Kastens" machen je einen Fall rot.

**REQ-EQ-4**: *Where, Ausnahmeseiten*
- Wo ein Buch `lesefolge.ausnahmen` deklariert (Liste physischer Seiten), gilt auf diesen Seiten
  die Docling-Folge. Das Protokoll nennt die Ausnahmeseiten.
- Jede Ausnahme braucht in der Regel-Messung eine Begründung (Seite, Urteil ohne Ausnahme).
- *Ziel:* Mit der Ausnahme S. 53 lautet die Bilanz von REQ-EQ-3 23 besser, 0 strittig, 0 schlechter
  (Entscheidung O-2).

*Detektor:* synthetisches Buch mit zwei Seiten im Fall (a) von REQ-EQ-3, Seite 2 als Ausnahme →
Seite 1 neu geordnet, Seite 2 in Docling-Folge, Protokoll nennt Seite 2.

### C. Striche und Zeichen (Teil 2a)

**REQ-EQ-5**: *Where, Zeilenend-Striche aus der Quelle (Docling-Weg)*
- Wo ein Buch `striche.zeilenenden` einschaltet, bestimmt das Einlesen für jedes Text-Element die
  Zeilenend-Striche aus den pdfplumber-Zeichen in seinem Kasten. Die Zeichenzuordnung erfolgt wie in
  REQ-MB-29. Zeilen werden nach Grundlinie gebildet.
- Je Fall (linkes Wortstück `L`, erstes Wort `R` der Folgezeile) gilt die Sollform nach REQ-MB-11:

  | Quelle | Sollform |
  |---|---|
  | Ziffer am Ende von `L`, oder `R` beginnt groß | `L-R` |
  | `R` steht in der Konjunktionsliste des Buchs | `L- R` |
  | sonst (`R` beginnt klein) | `LR` |

- Im Docling-Elementtext wird die vorhandene Form (`LR`, `L-R`, `L- R`, `L R`) durch die Sollform
  ersetzt. Das geschieht nur, wenn die vorhandene Form im Element **genau einmal** an Wortgrenzen
  steht. Sonst bleibt der Text unverändert, und der Fall zählt als `mehrdeutig`.
- Das Protokoll zählt `wiederhergestellt`, `zusammengefuegt`, `unveraendert`, `mehrdeutig`.
- Die Verdachtszähler aus REQ-MB-32 laufen danach.

*Ziel (Vorab-Messung):*
- **59 Stellen in 49 Abschnitten:** 40 Striche wiederhergestellt, 19 Trennungen zusammengefügt;
  59 besser, 0 schlechter.
- Binnen-Großbuchstabe 63 → 28, Strichrest 50 → 39.
- 4.616 richtig zusammengefügte Trennungen bleiben unverändert.

*Detektor:*
- Synthetisches PDF (`reportlab`, wie REQ-MB-29) mit Zeilenenden `Novizen-⏎Talent`, `W8-⏎Würfel`,
  `Nah-⏎und`, `Akti-⏎onswürfel`.
- Dazu eine Docling-Struktur mit den Texten `NovizenTalent`, `W8Würfel`, `Nahund`, `Akti-
  onswürfel` → `Novizen-Talent`, `W8-Würfel`, `Nah- und`, `Aktionswürfel`; Zähler
  `wiederhergestellt` 3, `zusammengefuegt` 1, `unveraendert` 0, `mehrdeutig` 0.
- Element, in dem `NovizenTalent` zweimal steht → unverändert, `mehrdeutig = 1`.
- Ohne `striche` → byte-gleich.
- Mutationen „Konjunktionsprüfung fehlt" und „Großbuchstabe → zusammenfügen" machen je einen Fall
  rot.

**REQ-EQ-6**: *Where, Strichrest an Elementgrenzen und im Text*
- Wo ein Buch `striche.strichrest` einschaltet, wird im Abschnittstext nach REQ-EQ-5 jede Folge
  „Buchstabe, `-`, ein oder mehrere Leerzeichen, Wort mit Kleinbuchstaben am Anfang, nicht in der
  Konjunktionsliste" zu „Buchstabe + Wort" zusammengefügt.
- Das betrifft vor allem Trennungen über Spalten- und Seitenwechsel: Dort endet ein Docling-Element
  auf `X-`, und `_Verbinder` setzt ein Leerzeichen.
- Die Konjunktionsliste ist die der Buchdeklaration (`reparatur.konjunktionen`, REQ-MB-11).

*Ziel (Vorab-Messung):*
- 39 Stellen in 32 Abschnitten. Mit der heutigen Liste wären 33 besser, **5 schlechter**
  (Ergänzungsstrich vor `als` ×4, vor `beziehungsweise` ×1) und 1 ungeklärt.
- Die Deklaration des Zielbuchs ergänzt deshalb `als` und `beziehungsweise` → 0 schlechter.
- Strichrest danach 0. Der ungeklärte Fall (S. 284) wird in der Regel-Messung beurteilt.

*Detektor:*
- Synthetische Docling-Struktur: Element 1 endet `Verteidi-`, Element 2 beginnt `gung`; dazu
  `Fertigkeits- als auch` und `Nah- und`. Liste mit `als` → `Verteidigung`, `Fertigkeits- als auch`,
  `Nah- und`.
- Liste ohne `als` → `Fertigkeitsals auch`. Das ist der dokumentierte Schaden und belegt die Wirkung
  der Liste.
- Ohne `striche.strichrest` → byte-gleich.

**REQ-EQ-7**: *Where, Zierschrift-Umlaut (G5)*
- Wo ein Buch `zeichen.zierumlaut` einschaltet, wird in jeder Zeile **vor** dem Listenabgleich
  (REQ-MB-12) die Folge „Vokal `a o u A O U`, optional ein Leerzeichen, ` . .`" durch den Umlaut des
  Vokals ersetzt.
- *Ziel:* 4 Zeilen (S. 9, 10, 20, 216). 4 Abschnitte ändern sich, 4 besser, 0 schlechter.
  Lesezeichen gefunden 144 → 146. S. 1 und 216 bleiben nicht gefunden (Grenze).

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
- Wenn `lesefolge`, `striche`, `zeichen`, `tabellen` oder `werteblock` gegen ihr Schema verstoßen,
  bricht das Einlesen ab wie in REQ-MB-34: `KonfigFehler` vor dem Schreiben, die Meldung nennt den
  Schlüssel.
- Schema:
  - `lesefolge`: `spalten` (Liste ≥ 1 von Bereichen `[a, b]`, `a < b`, aufsteigend, nicht
    überlappend), `toleranz` (Zahl ≥ 0, Default 4), `ausnahmen` (Liste ganzer Zahlen ≥ 1);
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
- Spaltenraster, Ausnahmeseiten, Konjunktionen, Werteblock-Schlüssel und Schalter sind Daten.
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
- **EQ-3** Die zeilenweise Folge im 2×2-Werteblock (156 Abschnitte) gilt als gleichwertig: Die Paare
  bleiben ganz (REQ-EQ-14 zählt sie).
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
- **Index S. 307–313 als Tabelle** (27.521 Zeichen je Seite in Markdown): Die Schablone behandelt
  ihn wie jede Tabelle. Ein Ausschluss über `inhaltsart` ist Datensache.
- **Elementtext ganz aus pdfplumber:** Am Prototyp waren 218 von 6.037 Elementen anders (Stichprobe
  2/12 schlechter). Spec 2 verwendet pdfplumber nur gezielt (EQ-5, EQ-14).
- **G4** Impressumzeile S. 313: netto neutral (Spec 1). Bleibt.
- **S. 117**: 2 Zeilen am Spaltenende fehlen in Docling (108 Zeichen). Das Zahlenprotokoll zeigt es
  (EQ-9), eine Reparatur ist nicht vorgesehen (O-8).

## Bekannte Grenzen (vorab)

- **REQ-EQ-3** kennt keine Kästen. Ein Kasten, der eine Spalte füllt, steht nach Spaltenfolge
  (S. 53). Die Variante „Kasten nach Einzug" hat am Buch neuen Schaden gemacht (S. 20) und ist
  verworfen. Abhilfe nur über Ausnahmeseiten (REQ-EQ-4).
- **REQ-EQ-5** findet Fälle nur, wenn Docling-Form und pdfplumber-Wörter übereinstimmen. 5
  echte Striche und 1 Trennung wurden nicht gefunden. Laufweiten-Artefakte von pdfplumber (gemessen
  5 Werteblock-Paare) können Fälle verdecken.
- **REQ-EQ-7** löst S. 216 nicht (Punkte am Wortende, Ein-/Mehrzahl).

## Offene Entscheidungen

**O-1: Schnitt der Spec.**
- (a) Eine Spec 2 mit allen Teilen.
- (b) **Schnitt:** Spec 2a „Lesereihenfolge und Zeichentreue" (EQ-1 bis EQ-10, EQ-15 bis EQ-20)
  jetzt, Spec 2b „Tabellen und Werteblöcke" (EQ-11 bis EQ-14) danach. Die IDs bleiben stabil.
- (c) Schnitt wie (b), aber 2b erst nach Spec 3 (Golden Set).
- **Empfehlung (b)**, mit Tendenz zu (c) für EQ-11. Begründung aus den Zahlen:
  - 2a ändert wenige, einzeln beurteilbare Stellen: 25 Abschnitte (Lesefolge), 59 + 39 Strichstellen,
    4 Umlautzeilen, 24 Listennummern. Das Messtor ist dort voll durchführbar, und die Urteile liegen
    schon zu über 95 % vor.
  - 2b ändert die Form von 366 Häppchen (13,9 % von 2.638) auf allen 58 Tabellenseiten. Ein
    Urteil „besser" ist dort ohne Retrieval-Messung nur Formprüfung.
  - Die Werteblöcke sind auf dem Docling-Weg schon zu 98,8 % intakt (9 echte Brüche). Der größte
    Hebel ist die Tabelle: 316 Häppchen ohne Kopf, 819 vervielfachte Zahlen.
  - Das Zahlenprotokoll (EQ-9) gehört in 2a, damit 2b einen Detektor vorfindet.

**O-2: Strittiger Kasten S. 53 (REQ-EQ-3).**
- (a) Als gleichwertig werten (beide Abschnitte sind Geschwister unter „Disziplinen").
- (b) Ausnahmeseiten je Buch (REQ-EQ-4), S. 53 deklariert.
- (c) Kastenerkennung neu entwerfen und neu messen.
- **Empfehlung (b):** Das hält „0 strittig" ohne Sonderlogik ein. (c) ist gemessen gescheitert
  (S. 20, zentrierte Überschrift als Kasten, wie bei MB-31). (a) weicht die Schwelle auf, die
  gerade die Lehre aus MB-31 ist.

**O-3: Innere Umstellungen beurteilen (REQ-EQ-1).**
- (a) Jede Textänderung einzeln.
- (b) Klassen mit automatischer Abgrenzung und Stichprobe ≥ 10, Rest einzeln.
- (c) Nur Abschnittsänderungen beurteilen.
- **Empfehlung (b):** 193 Textänderungen allein bei EQ-3, 156 davon in einer klaren Klasse
  (Werteblock-Zeilen), 25 in einer zweiten (Spaltenrücksprung). Bei (a) prüft man 156-mal dasselbe,
  bei (c) blieben die 25 Absatzrisse unbewertet, obwohl sie die häufigste echte Verbesserung sind.

**O-4: Messtor für die Tabellen-Schablone (REQ-EQ-11).**
- (a) Urteil je Tabelle von Hand (79), Kriterium „Spaltenkopf zum Wert lesbar, keine Zahl
  verloren".
- (b) Zusätzlich ein Retrieval-Vergleich mit dem Golden Set aus Spec 3.
- (c) Nur der automatische Zahlentreue-Detektor (EQ-12).
- **Empfehlung (a) jetzt, (b) als Abnahmebedingung für das Einschalten am Zielbuch:** Formfehler
  fängt (a), den Nutzen nur (b). (c) prüft die Form, nicht die Wirkung.

**O-5: Strichrest im Text (REQ-EQ-6).**
- (a) Mit ergänzter Konjunktionsliste (`als`, `beziehungsweise`) einschalten.
- (b) Nur an Elementgrenzen (Docling-Element endet auf `-`), nicht im Elementinneren.
- (c) Weglassen, nur der Verdachtszähler bleibt.
- **Empfehlung (a):** 33 besser, 0 schlechter mit der Liste. Ohne Liste wären es 5 schlechter. Die
  Liste ist Sprachdatum, kein Earthdawn-Wissen. (b) ließe die 11 Fälle im Elementinneren liegen, die
  EQ-5 nur auflöst, wenn sie eindeutig sind.

**O-6: Steuerzeichen und Listennummern (REQ-EQ-8, -10) in 2a?**
- (a) Beide aufnehmen.
- (b) Nur Steuerzeichen.
- (c) Keins.
- **Empfehlung (a):** Beide sind klein, gemessen und haben einen Zahlendetektor: 739 → 0 bzw.
  24 → 0. Die Listennummern sind Regelinhalt („Schritt 3"), Docling liefert sie schon (`marker`,
  S. 139 5/5).

**O-7: Inhaltsverzeichnis S. 3/4.**
- (a) Weglassen wie heute.
- (b) Als eigenen Abschnitt aus `document_index` übernehmen.
- **Empfehlung (a):** Die Gliederung kommt aus den Lesezeichen. Ein TOC-Häppchen voller Seitenzahlen
  stört das Retrieval eher. Das Zahlenprotokoll zeigt die 150 Zahlen weiter als `gar_nicht`; das ist
  die bekannte Grenze.

**O-8: Textverlust S. 117 (2 Zeilen).**
- (a) Nur zählen (EQ-9).
- (b) Zeilen ohne Docling-Kasten aus pdfplumber als eigenes Element an der Lageposition einfügen.
- **Empfehlung (a):** 1 Fall mit 108 Zeichen im ganzen Buch. Eine Einfügeregel bräuchte ein eigenes
  Messtor für einen Einzelfall. Dokumentieren reicht.

**O-9: Werteblock-Regel (REQ-EQ-14) jetzt oder mit dem Kreaturenband?**
- (a) In 2b mit dem Zielbuch (9 Paare).
- (b) Erst, wenn der Kreaturenband (Werteblöcke in Fülle) eingelesen wird.
- **Empfehlung (b):** Im Zielbuch ist der Nutzen 9 von 2.652 Paaren (0,3 %). Der Kreaturenband ist
  OCR (Fehlerklasse 3) und braucht ohnehin eine eigene Messung. Die 9 Paare bleiben bis dahin
  dokumentiert.

## Tier

**T3**, ohne Tier-Map wie Spec 1 (O-9 b dort). `derive-tier.js` findet keine Map (Exit 2), es greift
die Regel „unbekannter Pfad → höchste Stufe". Inhaltlich passt das: Es geht um den Einlese-Contract
aller Mehr-Bücher-Bestände und um Texte, die in den Index gehen. Ohne CI-Anker wird nicht
server-seitig nachgerechnet; maßgeblich ist Tobias' Abnahme jedes Merges.
