# Spec: Mehr-Bücher-Bestand — Datenmodell und Einlesen

- **Spec-ID:** mehrbuch-bestand (Spec 1 von voraussichtlich 2–3)
- **Kontext-Kürzel:** MB
- **Tier:** T3 — siehe Abschnitt „Tier"
- **Status:** **Abgenommen** durch Tobias am 2026-10-22 (Fassung 7). (Historie: Fassung 4 abgenommen durch Tobias am 2026-10-21; Fassung 5 (nach Vorab-Messung) durch Tobias' Entscheidungen F6-1 bis F6-5 nachgeschärft; Fassung 6 abgenommen durch Tobias am 2026-10-21; Fassung 7 arbeitet Tobias' Entscheidungen F7-1 bis F7-7 nach dem Kritiker-Review am echten Buch ein.)

## User Story

Als Betreiber des lokalen Regel-RAG möchte ich einen Bestand aus **mehreren Büchern**
(verschiedene Titel, Fassungen und Sprachen) anlegen, einzelne Bücher durch eine andere
Fassung ersetzen und sauber gegliederte Häppchen aus schwierigen PDFs (Zweispaltensatz,
Silbentrennung, kaputte Überschriften-Schrift) erzeugen, **damit** Antworten aus dem
richtigen Buch und der richtigen Fassung kommen und Buch, Fassung und Seite als Fundstelle
nennen — ohne dass sich an den bestehenden Brettspiel-Beständen und an der Messung etwas
ändert.

Erster Anwendungsfall ist ein Earthdawn-Bestand (Spielerhandbuch ED4, 3. Aufl. 2023, deutsch;
später „Die Kreaturen von Barsaive" ED1 als OCR-Scan, „Throal" englisch). **Earthdawn steckt
nur in den Daten, nie im Code.**

## Begriffe

| Begriff | Bedeutung |
|---|---|
| **Bestand** | Das heutige Spielverzeichnis `data/<spiel_id>/` samt `spiel.json`. Die `spiel_id` bleibt die Bestands-ID; die Pipe-Zuordnung (`ordne_spiel`, `Spiel: X`) wählt weiter Bestände. |
| **Buch** | Eine Quelle innerhalb eines Bestands, mit stabiler `buch_id`, Titel, Fassung, Sprache, Quelldatei. |
| **Fassung** | Allgemeiner Name für Edition/Auflage/Version eines Buchs (z. B. `ED4`, `ED1`, `v3`). Ein freier Text, den nur die Daten deuten. |
| **Abschnittspfad** | Überschriften-Hierarchie eines Häppchens, z. B. `["Talente", "Talentbeschreibungen", "Ablenken"]`. |
| **Inhaltsart** | Themenbereich eines Abschnitts (z. B. `regel`, `welt` (Vokabular frei)); eigenes Feld, **orthogonal** zu `typ` aus `classify.py` (regel/flavor/meta bleibt Ballast-Filter für `DROP_TYPES` in Altbeständen; in Mehr-Bücher-Beständen wird `DROP_TYPES` nicht angewendet, REQ-MB-30). |
| **Überschriften-Liste** | Deklarierte Gliederung eines Buchs: Einträge (Titel, Ebene, Seite) aus PDF-Lesezeichen oder Inhaltsverzeichnis. |
| **Layout-Überschrift** | Überschrift, die unterhalb der Liste aus Zeilenmerkmalen der Extraktion erkannt wird (REQ-MB-20). |
| **Altbestand** | Ein Bestand, dessen `spiel.json` keine Bücherliste hat (heutiges Format, ein `quelle_pdf`). |

Unberührt bleibt der Einzeldatei-Weg (`knowledge.jsonl`/`pdfs/` neben `rag.py`, ohne Index).

## Akzeptanzkriterien

### A. Datenmodell

**REQ-MB-1** — *Contract*
Ein Bestand kann in `spiel.json` eine Liste von Büchern deklarieren; jedes Buch hat
`buch_id` (Slug nach derselben Regel wie `spiel_id`, im Bestand eindeutig), `titel`, `fassung`, `sprache` (aus `rag.SPRACHEN`),
eine Quelldatei, eine Standard-Inhaltsart und optional Inhaltsart-Zuweisungen je
Abschnittspfad-Präfix (längstes passendes Präfix gewinnt; keine LLM-Klassifikation). Jedes Buch
liegt in einer eigenen Datei `data/<spiel_id>/buecher/<buch_id>/knowledge.jsonl` mit eigenem
Fingerprint. Ein Altbestand wird gelesen, als hätte er genau ein Buch (`buch_id`, Titel und
Fassung aus vorhandenen Angaben abgeleitet), behält seine eine Datei und **keine Datei wird
umgeschrieben**.
*Detektor:* synthetischer Bestand mit zwei Büchern → `rag.py index` legt Häppchen beider
Bücher an; Präfix-Zuweisung `["K2"]`→`welt` bei Standard `regel` ergibt für Häppchen unter
`K2 › X` `welt`, unter `K1` `regel`; Altbestand-Verzeichnis ist nach `index` byte-gleich
(Hash aller Dateien).

**REQ-MB-2** — *Contract*
Jedes Häppchen eines Mehr-Bücher-Bestands trägt im Index und in den von `lade_spiel`
gelieferten Chunks: `buch_id`, `fassung`, `sprache`, `seite`, `abschnittspfad`, `inhaltsart`.
Die Werte stammen aus der Zeile des Index, nicht aus dem Aufruf (wie heute `spiel_id`).
*Detektor:* Index nach Bau auslesen; ein Buch mit falscher Deklaration im Aufruf, aber
korrekten Zeilen liefert die Zeilenwerte.

**REQ-MB-3** — *If/Then, Rückwärtskompatibilität*
Wenn ein Bestand ein Altbestand ist, dann sind Index-Inhalt (Texte, Seiten, Reihenfolge),
Retrieval-Ergebnisse, Quellenköpfe im Prompt, Pipe-Fusszeilen, Entscheidungstexte und
Eval-/Messausgaben **gleich zum Stand vor dieser Spec** (Gleichstands-Regel wie in
`test_regression.py`). Die bestehenden Referenzen (`regression_referenz.json`,
`pipe_referenz.json`, `pipe_verlauf_referenz.json`) und alle bestehenden Tests inklusive
`test_mutationen.py` und `messung/` bleiben **ohne Änderung ihrer Sollwerte** grün. Das
Index-Schema wird per **neuer Spalten** erweitert (Altwerte NULL/abgeleitet); ein vorhandener
Index-Stand bleibt gültig und wird **nicht** neu eingebettet.
*Detektor:* bestehende Suite unverändert; Diff der Referenzdateien leer. Migrationstest: ein
mit dem Code vor dieser Spec gebauter Index (im Test synthetisch erzeugt) → nach Migration
Embed-Zähler 0 und Abfrage-Ergebnisse gleich denen vor der Migration.

**REQ-MB-4** — *When, Filter vor dem Ranking*
Wenn eine Suche mit Filter auf `buch_id`, `fassung`, `sprache` und/oder `inhaltsart` läuft,
dann stammen alle Kandidaten — für Vektorsuche, BM25 (`HYBRID=1`) und Reranker-Kandidatenfeld
— ausschließlich aus passenden Häppchen; ein nicht passendes Häppchen kann kein passendes
verdrängen. Ein Filter auf einen Wert, den der Bestand nicht hat, bricht mit `KonfigFehler`
ab (keine stille leere Suche).
*Detektor:* Konstruktion mit einem nicht passenden Häppchen, dessen Vektor gleich dem
Fragevektor ist (Score 1,0) — es erscheint nicht, und die Top-k sind identisch zur Suche in
einem Bestand, der nur die passenden Häppchen enthält. Gleiches mit BM25-Treffer.

**REQ-MB-5** — *Where, Fassungsregel (zweistufig)*
Wo ein Bestand für eine Inhaltsart eine Fassungsregel festlegt, nennt sie **maßgebliche**
Fassungen und optional **gekennzeichnete** Fassungen mit je einem festen Hinweistext
(z. B. `regel`: maßgeblich `ED4`; gekennzeichnet `ED1` mit „Fassung ED1 — für die maßgebliche
Fassung umrechnen"). Für Häppchen dieser Inhaltsart gilt:
- **maßgebliche Fassung** → normaler Kandidat;
- **gekennzeichnete Fassung** → Kandidat, im Ranking gleich behandelt (kein Bonus/Malus), trägt
  aber den Hinweis (REQ-MB-21);
- **jede andere Fassung** → **ausgeschlossen**: nie Kandidat, wirkt wie REQ-MB-4 vor dem Ranking.

Inhaltsarten ohne Regel kommen aus allen Fassungen ohne Hinweis. Die Regel gilt bei jeder
Suche des Bestands (CLI, Eval, Pipe), unabhängig von der Frage. Hinweistexte und
Fassungsnamen sind Daten.
*Detektor:* synthetischer Bestand mit Fassungen `alpha`/`beta`/`gamma`, Regel `regel`:
maßgeblich `alpha`, gekennzeichnet `beta`; je ein `regel`- und `welt`-Häppchen je Fassung mit
Score 1,0 → erreichbar `regel@alpha`, `regel@beta` (mit Hinweis), alle drei `welt`; `regel@gamma`
erscheint in keinem Kandidatenfeld (Vektor, BM25, Reranker). Ranking-Gleichbehandlung: Top-k-
Reihenfolge gleich der eines Bestands ohne Regel, aus dem `regel@gamma` entfernt ist.

**REQ-MB-6** — *Contract, Fundstelle*
In einem Mehr-Bücher-Bestand nennen Quellenkopf im Prompt (`baue_kontext`), Pipe-Fusszeile
und die Seitenangaben des Entscheidungsschritts (C-Text, B-Hinweis, Sprachmodus) je Fundstelle
**Buch (Titel oder Kurzname), Fassung und gedruckte Seite** (REQ-MB-22). CLI und Pipe erzeugen
dieselben Köpfe aus derselben Funktion.
*Detektor:* Prompt-Nachrichten und Pipe-Ausgabe für einen synthetischen Zwei-Bücher-Bestand
mit gleicher Seitenzahl in beiden Büchern sind unterscheidbar; Mutation der Kopf-Funktion
(liefert Marker) ändert CLI- **und** Pipe-Ausgabe. Altbestände: REQ-MB-3.

**REQ-MB-7** — *If/Then, Messung*
Golden-Set-Fragen eines Mehr-Bücher-Bestands geben erwartete Fundstellen als
(`buch_id`, gedruckte Seite) an; ein Treffer zählt nur bei passendem Buch. Wenn ein Golden Set
eines Mehr-Bücher-Bestands eine Seite ohne Buch angibt, dann bricht `eval`/`messung` mit
`KonfigFehler` ab (keine stille Wertung gegen ein beliebiges Buch). Altbestände: REQ-MB-3.
*Detektor:* Frage mit erwarteter Seite 12 in Buch A, Treffer auf Seite 12 in Buch B → verfehlt.

### B. Quelle ersetzen und inkrementell einbetten

**REQ-MB-8** — *When*
Wenn die Quelle eines Buchs durch eine andere Fassung oder Auflage ersetzt wird (gleiche
`buch_id`, neue Fassung/Quelldatei, neu eingelesen) und danach `rag.py index` läuft, dann
enthält der Index für diese `buch_id` nur noch Häppchen der neuen Fassung — null Häppchen
der alten, auch in FTS — und die Häppchen der übrigen Bücher werden **nicht** neu eingebettet.
`--ueberschreiben` beim Einlesen wirkt nur auf das genannte Buch.
*Detektor:* Fake-`embed` zählt eingebettete Texte: genau die Häppchenzahl des ersetzten
Buchs; Zeilenzählung je `buch_id`/`fassung` in `chunks` und `chunks_fts`.

**REQ-MB-9** — *When*
Wenn ein Buch neu hinzukommt oder unverändert bleibt, wird nur das neue Buch eingebettet;
ein `index`-Lauf ohne Änderung bettet nichts ein. Das Einlesen eines Buchs lässt die
Daten der anderen Bücher desselben Bestands byte-gleich.
*Detektor:* Embed-Zähler 0 beim zweiten Lauf; Dateihashes der anderen Bücher vor/nach Ingestion.

**REQ-MB-10** — *If/Then*
Wenn die Deklaration doppelte `buch_id`s enthält, zwei Bücher dieselbe Quelldatei nennen,
eine `buch_id` keinen Slug bildet (gleiche Regel wie `spiel_id`), eine `sprache` nicht in
`rag.SPRACHEN` liegt oder Häppchen eine nicht deklarierte `buch_id` tragen, dann bricht `index`
für diesen Bestand mit `KonfigFehler` ab und dessen alter Stand bleibt (wie heute bei kaputten
Spielen).
*Detektor:* je Fall ein synthetischer Bestand (u. a. `buch_id` `"Buch A"` bzw. `"../x"`,
`sprache` `"xx"`); `KonfigFehler`, Index-Inhalt vorher = nachher.

### C. Einlesen-Reparatur

Die Reparatur ist eine reine Funktion auf den Textzeilen der Extraktion **vor** jedem
Whitespace-Zusammenfassen und wird je Buch eingeschaltet (für Altbestände und den rohen
PDF-Weg aus: REQ-MB-3). Reihenfolge: (1) Überschriften-Abgleich auf Zeilen (REQ-MB-12, -20)
samt Einsortieren der Listenüberschriften nach Lage (REQ-MB-31),
(2) Trennungsreparatur (REQ-MB-11, nur auf Wegen mit Zeilenenden) im Text zwischen den Überschriften — sonst würde der
gewöhnliche Umbruch (`Wurf⏎Stufe`) Überschriftenzeilen mit dem Folgetext verschmelzen.
Zeilen im Kopf- oder Fußrand (Position nach REQ-MB-20) werden in (1) erkannt und gezählt, nehmen
aber weder am Listenabgleich (REQ-MB-12) teil noch gelangen sie in einen Häppchentext (REQ-MB-28).

**REQ-MB-11** — *Contract, Trennungen*
Für die folgenden Eingaben (`⏎` = Zeilenumbruch, `·` = U+00AD) liefert die Reparatur genau:

| Eingabe | Ergebnis | Fall |
|---|---|---|
| `Akti-⏎onswürfel` | `Aktionswürfel` | Trennung, Kleinbuchstabe folgt |
| `Bewusstlosigkeits·schwelle` | `Bewusstlosigkeitsschwelle` | weicher Trennstrich im Wort |
| `Bewusstlosigkeits·⏎schwelle` | `Bewusstlosigkeitsschwelle` | weicher Trennstrich am Zeilenende |
| `Zwerg-⏎Krieger` | `Zwerg-Krieger` | echter Bindestrich, Großbuchstabe folgt |
| `ED4-⏎Regeln` | `ED4-Regeln` | Bindestrich nach Ziffer |
| `Nah-⏎und Fernkampf` | `Nah- und Fernkampf` | Ergänzungsstrich vor Konjunktion |
| `Stufen/⏎Aktionswürfel` | `Stufen/Aktionswürfel` | Schrägstrich bleibt |
| `Schaden - 2` | `Schaden - 2` | freistehender Strich bleibt |
| `Wurf⏎Stufe` | `Wurf Stufe` | gewöhnlicher Umbruch |

Regelwerk nur wie in der Tabelle (keine Wörterbuchprüfung); die Konjunktionsliste ist
sprachabhängig und Teil der Konfiguration.

*Geltungsbereich (Fassung 7):* Die Reparatur der Zeilenenden (alle Tabellenzeilen mit `⏎`) gilt
nur für Extraktionswege, die die Zeilenenden des Satzes liefern (Seitenzeilen, deren Elementtexte
die Zeilenumbrüche enthalten). Auf dem **Docling-Weg**, der die Zeilen eines Elements selbst
zusammenfügt und dabei Zeilenend-Striche streicht, **entfällt** sie: ein Elementtext dieses Wegs
wird an `⏎` und Strichen nicht verändert, auch wenn er ein `⏎` enthält. Der Weg ist eine
Eigenschaft des Einlesens, nicht des Texts. Das Entfernen des weichen Trennstrichs im Wort
(Tabellenzeile 2, kein Zeilenende beteiligt) gilt auf allen Wegen. Auf dem Docling-Weg zählt
stattdessen das Protokoll Verdachtsfälle (REQ-MB-32).
*Detektor:* Tabelle als Testfälle; Einlese-Protokoll zählt „zusammengefügte Trennungen" und
„Strich behalten" — Zähler auf einer definierten Eingabe mit bekannter Anzahl je Fall exakt.
Docling-Weg (synthetische Extraktionsstruktur ohne echtes Docling, wie REQ-MB-27): Element
`Akti-⏎onswürfel` bleibt byte-gleich, Element `Bewusstlosigkeits·schwelle` →
`Bewusstlosigkeitsschwelle`, Zähler „zusammengefügte Trennungen" = 0; dasselbe Element
`Akti-⏎onswürfel` auf dem Zeilenweg → `Aktionswürfel`.

**REQ-MB-12** — *Where, Überschriften-Liste und unscharfer Abgleich*
Wo ein Buch eine Überschriften-Liste deklariert, gilt sie als Wahrheit für die Ebenen, die sie
kennt. Der Mechanismus nimmt allgemein eine Liste (Titel, Ebene, Seite); Lieferanten sind
mindestens **PDF-Lesezeichen** und eine **Inhaltsverzeichnis-Liste** (Titel, Ebene, gedruckte
Seite, umgerechnet nach REQ-MB-22). Für jeden Eintrag wird auf seiner **Zielseite (± 0)** die
passende Zeile gesucht und durch den Listentitel ersetzt; sie beginnt den Abschnitt.
Wo das Buch einen Kopf- und/oder Fußrand deklariert (Position nach REQ-MB-20), sind Zeilen im
Rand vom Abgleich **ausgenommen**: sie passen zu keinem Eintrag, sind kein Kandidat für die
Auswahl unter mehreren Zeilen und zählen nicht für „mehrdeutig". Ohne Randangabe gilt der Abgleich
wie bisher über alle Zeilen der Seite.

*Abgleichregel:* `norm(s)` = Unicode-NFC, alle Leerraumzeichen und alle Unicode-Formatzeichen
(Kategorie `Cf`, u. a. weicher Trennstrich U+00AD, U+200B) entfernen, `casefold`.
Eine Zeile **passt** zu Titel `t`, wenn `norm(zeile)` durch Streichen von höchstens `k`
Zeichen aus `norm(t)` entsteht (Teilfolge, nur Auslassungen — keine Vertauschungen, keine
Einfügungen) mit `k = 0` für `len(norm(t)) < 6`, sonst `k = max(1, ⌊len(norm(t)) / 10⌋)`.
Verglichen wird immer die **ganze Zeile**, nie ein Teilstück. Mehrere passende Zeilen auf der
Seite: die mit den wenigsten Auslassungen gewinnt, bei Gleichstand die erste in Lesereihenfolge;
der Gleichstand wird im Protokoll als „mehrdeutig" mit Titel und Seite gezählt. Eine Zeile wird
höchstens einem Eintrag zugeordnet (Einträge in Listenreihenfolge). Keine passende Zeile →
REQ-MB-13.

Abgedeckt sind die gemessenen Fehlerklassen (1) fehlende Zeichen und (2) eingeschobene
Leerzeichen. **Klasse (3) OCR-Vertauschungen** (`DLE I<REATUREN VON BARSALVE`, `LEKTOAAT`,
`so` für `50`) ist **nicht** Teil von Spec 1: eine Regel mit Vertauschungen träfe bei Abstand 1
auch echte Nachbarwörter (`Feuerball`/`Feuerwall`, siehe Tabelle); solche Einträge fallen
sichtbar unter REQ-MB-13.

| Listentitel (Seite 7) | Zeile auf Seite 7 | Ergebnis | Grund |
|---|---|---|---|
| `Bonuswürfel` | `Bonusw rfel` | ersetzt → `Bonuswürfel` | 1 Auslassung, k = 1 |
| `Aktionswürfel` | `A ktionswürfel` | ersetzt | nur Leerzeichen |
| `Stufen/Aktionswürfel` | `Stufen/Aktionsw rfel` | ersetzt | 1 Auslassung, k = 2 |
| `Ätherhaut` | `therhaut` | ersetzt | 1 Auslassung, k = 1 |
| `Bonuswürfel` | `BONUSWÜRFEL` | ersetzt | nur Groß/Klein |
| `Bewusstlosigkeitsschwelle` | `Bewusstlosigkeits·schwelle` (`·` = U+00AD) | ersetzt | Formatzeichen (`Cf`) entfernt, 0 Auslassungen |
| `Bonuswürfel` | `Bonusw rf l` | **nicht** ersetzt | 2 Auslassungen > k = 1 |
| `Bonuswürfel` | `Bonus` | **nicht** ersetzt | 6 Auslassungen |
| `Bonuswürfel` | `Bonuswürfel einsetzen …` (Fließtext) | **nicht** ersetzt | Zeile länger als Titel |
| `Feuerball` | `Feuerwall` | **nicht** ersetzt | Vertauschung, keine Auslassung |
| `Rang` | `Rng` | **nicht** ersetzt | Titel < 6, k = 0 |
| `Bonuswürfel` | `Bonusw rfel` auf **Seite 8** | **nicht** ersetzt | nicht Zielseite |
| `Die Kreaturen von Barsaive` | `DLE I<REATUREN VON BARSALVE` | **nicht** ersetzt → REQ-MB-13 | Klasse (3) |

*Detektor:* Tabelle als Testfälle (Seitentexte + Liste → Abschnittspfad und Häppchentext);
ersetzte Fälle: Pfad und Text enthalten die Listenform, die kaputte nicht mehr; nicht ersetzte:
Zeile byte-gleich. Gleichstand-Fall: zwei gleich gute Zeilen → erste gewinnt, Protokoll
„mehrdeutig = 1". Rand-Fall: Kopfrand deklariert; auf Seite 7 steht im Kopfrand der Kolumnentitel
`Bonuswürfel` (in Lesereihenfolge zuerst), im Satzspiegel die echte Überschrift `Bonuswürfel`,
Lesezeichen `Bonuswürfel` → Seite 7 → der Abschnitt beginnt an der Zeile im Satzspiegel (der Text
zwischen Kolumnentitel und echter Überschrift liegt nicht im Abschnitt `Bonuswürfel`), Protokoll
„mehrdeutig = 0", „gefunden = 1". Gegenprobe: dieselbe Seite ohne Randangabe → erste Zeile gewinnt,
„mehrdeutig = 1".

**REQ-MB-13** — *If/Then*
Wenn ein Listeneintrag auf seiner Zielseite nicht gefunden wird, dann beginnt sein Abschnitt
direkt hinter der Zeile des in **Listenreihenfolge** vorangehenden gefundenen Eintrags auf
derselben Zielseite; gibt es auf dieser Seite keinen solchen, am Anfang der Zielseite. Die
Reihenfolge der Überschriften-Liste ist maßgeblich. Der Eintrag erscheint im Einlese-Protokoll
mit Titel und Seite (Zähler gefunden/nicht gefunden/mehrdeutig). Kein Eintrag verschwindet still.
*Detektor:* (a) Liste mit einem Eintrag ohne Gegenstück, als erster seiner Seite → Abschnitt
beginnt am Seitenanfang, Protokoll nennt ihn; (b) Seite mit gefundenem Eintrag `A`, danach
Fließtext, Liste `A`, `B` (B ohne Gegenstück) → Abschnitt `B` beginnt direkt hinter der Zeile
`A` (der Fließtext liegt in `B`, nicht in `A`), Protokoll nennt `B`.

### D. Zerschneiden nach Überschriften

**REQ-MB-14** — *Contract, Abschnittsgrenzen*
Bei Büchern mit Überschriften-Liste enthält kein Häppchen Text aus zwei verschiedenen
(Blatt-)Abschnitten — Blätter sind auch Layout-Abschnitte (REQ-MB-20); auch die Überlappung
(`CHUNK_OVERLAP`) reicht nie über eine Abschnittsgrenze. `CHUNK_SIZE` gilt für den Text
**ohne** Titelvorsatz (REQ-MB-15). Ein Abschnitt, der kürzer als `CHUNK_SIZE` ist, ergibt genau
ein Häppchen (keine Zusammenlegung kurzer Geschwister); ein längerer wird innerhalb des
Abschnitts nach `CHUNK_SIZE`/`CHUNK_OVERLAP` **zeichengenau wie heute** (`zerteile`) geteilt.
Das Protokoll weist die Häppchenzahl je Buch aus.
*Detektor:* synthetisches Buch mit markierten Abschnittstexten; jedes Häppchen ist Teilstring
genau eines Abschnitts (ohne Vorsatz); Abschnitt der Länge `CHUNK_SIZE` + 1 → 2 Häppchen,
Textteile gleich `zerteile` auf dem Abschnittstext; zwei 50-Zeichen-Geschwister → 2 Häppchen.

**REQ-MB-15** — *Contract, Titel trägt mit*
Jeder Häppchentext — der eingebettete wie der im Prompt — beginnt mit seinem Abschnittspfad,
auch ein Häppchen aus der Mitte eines langen Abschnitts.
*Detektor:* Abschnitt „Grauer Wolf" mit Werteblock über drei Häppchen → alle drei beginnen
mit dem Pfad bis „Grauer Wolf"; BM25-Suche nach „Grauer Wolf" findet alle drei.

**REQ-MB-16** — *Contract, Seiten über Seitengrenzen*
Läuft ein Häppchen über eine Seitengrenze, trägt es alle Seiten, über die sein Text läuft;
die Fundstelle nennt die erste, eine Golden-Set-Erwartung trifft bei jeder davon.
*Detektor:* Abschnitt von Seite 4 nach 5 → Häppchen mit Seiten [4, 5]; Erwartung 5 = getroffen.

### E. Nicht-funktional

**REQ-MB-17** — *Architektur*
Jede Wirkung dieser Spec ist mit einem synthetischen Bestand erreichbar, dessen Namen,
Buchtitel, Fassungen, Hinweistexte und Inhaltsarten-Zuweisungen keinen Bezug zu Earthdawn
haben; es gibt keinen Code-Pfad, der nur bei bestimmten Bestands- oder Buchnamen wirkt.
*Detektor:* sämtliche Tests dieser Spec laufen mit einem Bestand `testwelt` und Fassungen
`alpha`/`beta`/`gamma`; Umbenennen aller Bezeichner in den Testdaten ändert kein Ergebnis.

**REQ-MB-18** — *Architektur, Urheberrecht*
Kein Test liest echte Bücher oder `DATA_DIR`-Inhalte; alle Testdaten sind synthetisch und
werden im Test erzeugt. Einlese-Ergebnisse geschützter Bücher entstehen nur unter
`DATA_DIR`/`pdfs/` (gitignored). `test_schutz.py` deckt die neuen Schreibpfade (Bücherdateien,
Einlese-Protokoll) mit ab. Die Vorabmessung (REQ-MB-23) legt im Repo nur Seitennummern und
Zahlen ab, keinen Buchtext.
*Detektor:* `test_schutz.py` mit Mutation „Bücherdatei neben den Code schreiben" wird rot.

**REQ-MB-19** — *Performance*
Laden und Vektorsuche in einem Bestand mit 5 Büchern und zusammen 3.000 Häppchen
(1.024 Dimensionen, Embedding gefakt, mit aktiver Filter- und Fassungsregel nach
REQ-MB-4/-5): **typisch ≤ 15 ms, Maximum ≤ 45 ms** je Frage über 200 Fragen. Altbestände sind
nicht langsamer als der Stand vor dieser Spec, gemessen **auf derselben Maschine** (Referenzlauf
des alten Codes bzw. im selben Testlauf gemessene Basis): typisch und Maximum je höchstens
**+20 %** gegenüber der Basis. Für Altbestände gilt dabei (Fassung 7): **typisch** wird wie bisher
verglichen; das **Maximum** ist je Seite (neuer Code bzw. Basis) der **Median der Maxima aus
5 Wiederholungen** (je Wiederholung 200 Fragen, Wiederholungen von neu und Basis abwechselnd),
und der Median von neu darf höchstens Median der Basis × 1,2 sein. Median statt Mittelwert:
gemessen schwankt das Verhältnis zweier Einzel-Maxima zwischen 0,47 und 2,35 bei typisch 1,002;
ein einzelner Ausreißerlauf (Planer, GC) verschiebt einen Mittelwert aus 5 Werten um bis zu ein
Fünftel seiner Höhe, den Median nicht, solange höchstens 2 von 5 Läufen ausreißen. Die absoluten
Grenzen für den Mehr-Bücher-Bestand (typisch ≤ 15 ms, Maximum ≤ 45 ms) bleiben unverändert.
Die README-Zahlen (2.000 Häppchen typisch 9,1 ms, max 13,5) dienen nur noch zur Information,
nicht als Sollwert. Zeittests nach REQ-MB-19 zählen in den Mutationsproben **nicht als Fang**: eine
Mutation gilt nur als gefangen, wenn ein Test außerhalb der Zeitmessung rot wird.
*Detektor:* Messskript mit typisch und Maximum, wie die README-Messung; für Altbestände Basis
und neuer Code im selben Lauf auf derselben Maschine, typisch gegen Basis × 1,2, Maximum als
Median der 5 Maxima je Seite gegen Median der Basis × 1,2; das Messergebnis nennt alle 5 Maxima
je Seite.

### F. Ergänzungen (Entwurf 2)

**REQ-MB-20** — *Where, Layout-Überschriften unterhalb der Liste*
Wo ein Buch Layout-Merkmale für Überschriften deklariert (allgemeiner Mechanismus, alle Werte je
Buch konfigurierbar), werden Layout-Überschriften aus drei Merkmalsquellen bestimmt:

- **Schrift** (aus pdfplumber, je Zeile zugeordnet): Die Schrift einer Zeile ist Größe, Schnitt
  (aus dem Schriftnamen, z. B. fett) und Laufweite (mittlerer Zeichenabstand) der Mehrheit ihrer
  Zeichen ohne Leerzeichen; ohne eindeutige Mehrheit hat die Zeile keine zugeordnete Schrift. Das
  Buch deklariert eine geordnete Liste von **Schriftstufen** (Stufe 1 = oberste Layout-Ebene,
  z. B. Talentname; Stufe 2 = Zwischenüberschrift; …), je Stufe Größe von–bis, optional Schnitt,
  optional Laufweite von–bis. Eine Schrift **trifft** Stufe n, wenn sie alle Angaben der Stufe n
  erfüllt; trifft sie mehrere, gilt die kleinste n.
- **Position:** Kopf- und Fußrand je Buch als Abstand in PDF-Punkten von der oberen bzw. unteren
  Seitenkante. Eine Zeile liegt im Rand, wenn ihr vertikaler Mittelpunkt darin liegt.
- **Layout-Klasse** der Docling-Extraktion: (i) die deklarierte Überschriften-Klasse (z. B.
  `section_header`) für den Rückfall; (ii) eine je Buch deklarierte **Veto-Menge** von Klassen,
  deren Zeilen nie Überschrift sind. Default der Veto-Menge sind mindestens Tabelle samt
  Tabellenzellen, Bildunterschrift, Seitenkopf und Seitenfuß (Docling `table`, `caption`,
  `page_header`, `page_footer`); eine Veto-Deklaration des Buchs **ergänzt** diese Menge und ersetzt sie nicht.

Optional deklarierte **Höchstlänge** (Zeichenzahl der Zeile ohne Leerraum am Anfang und Ende)
gilt zusätzlich. Weitere Zeilenmerkmale gibt es nicht (das Merkmal „eigene Zeile" ist ab
Fassung 7 gestrichen). Die Deklaration wird gegen ihr Schema geprüft (REQ-MB-34).

*Kombinationsregel.* Eine Zeile ist genau dann Layout-Überschrift der Stufe n, wenn alle fünf
Bedingungen gelten:
1. *notwendig:* sie liegt nicht im Kopf- oder Fußrand;
2. *notwendig:* ihre Layout-Klasse gehört nicht zur Veto-Menge des Buchs;
3. *notwendig:* sie ist nicht schon einem Listeneintrag zugeordnet (REQ-MB-12);
4. *notwendig:* ist eine Höchstlänge deklariert, ist sie nicht länger;
5. entweder (a) ihr ist eine Schrift zugeordnet und diese trifft Stufe n — zusammen mit 1–4
   **hinreichend**; die Layout-Klasse wirkt hier nur über das Veto (Bedingung 2), nicht als
   Voraussetzung; oder (b) ihr ist keine Schrift zugeordnet und ihre Layout-Klasse ist die
   deklarierte Überschriften-Klasse — dann Stufe 1 (**Rückfall**, im Protokoll gezählt).

Folgerungen: Eine Zeile mit zugeordneter Schrift, die keine Stufe trifft, ist **nie**
Überschrift, auch mit Überschriften-Klasse (die Klasse allein ist nicht hinreichend). Eine Zeile
im Rand oder mit einer Klasse der Veto-Menge ist nie Überschrift, auch mit passender Schrift.
Deklariert ein Buch keine Schriftstufen, entscheidet für alle Zeilen außerhalb von Rand und Veto
5(b), also die Klasse allein (Stand Fassung 4).

*Ebene und Pfad.* Eine Layout-Überschrift der Stufe n liegt n Ebenen unter ihrem umschließenden
Listenabschnitt. Ihr Abschnittspfad ist der Pfad des Listenabschnitts, danach die im selben
Listenabschnitt zuletzt begonnenen, noch offenen Layout-Überschriften der Stufen 1 bis n − 1
(fehlt eine Stufe, wird sie übersprungen, keine Lücke gefüllt), danach die Zeile selbst. Sie
beginnt einen Unterabschnitt, der bis zur nächsten Layout-Überschrift der Stufe ≤ n oder bis zur
nächsten Listenüberschrift reicht; eine Überschrift der Stufe n + 1 beendet ihn also nicht,
sondern beginnt darin einen tieferen Unterabschnitt. Eine Zwischenüberschrift der Stufe 2
zerteilt damit kein Talent der Stufe 1 in zwei gleichrangige Abschnitte.

Layout-Überschriften werden **nicht** gegen die Liste abgeglichen oder ersetzt und erzeugen keine
Ebenen oberhalb der Liste. Das Protokoll zählt erkannte Layout-Überschriften je Listenabschnitt
(alle Stufen zusammen), außerdem je Stufe, die Rückfälle nach 5(b), die Zeilen, die nur wegen
des Rands (Bedingung 1) keine Überschrift wurden, obwohl 5(a) oder 5(b) zuträfe, und die Zeilen,
die nur wegen des Vetos (Bedingung 2) keine Überschrift wurden, obwohl 5(a) zuträfe.
Anlass (gemessen): im Zielbuch ist „Talentbeschreibungen" **ein** Lesezeichen für S. 76–107;
die Talentnamen stehen nur im Text. Die Klasse allein reicht nicht (Vorab-Messung, Entscheidung
N-1 revidiert).
*Detektor:* synthetisches Buch, Liste auf 2 Ebenen (`K1 › U1`), Zeilen mit Klasse, Schrift und
Position, zwei Schriftstufen deklariert:
- Grundfall: Zeilen `Alpha`, `Beta` mit Schrift der Stufe 1 und je Text → Pfade `K1 › U1 › Alpha`
  bzw. `… › Beta`; jedes Häppchen eines Unterabschnitts beginnt mit dessen Namen (REQ-MB-15);
  Protokoll `U1` = 2.
- (a) Kolumnentitel: Zeile im Kopfrand mit Überschriften-Klasse und Schrift der Stufe 1 → keine
  Überschrift, kein Pfad enthält sie, Rand-Zähler = 1. Grenzfall: dieselbe Zeile mit Mittelpunkt
  1 pt außerhalb des Rands → Überschrift.
- (b) Zeile `Delta` mit Schrift der Stufe 1, aber Klasse `text` → Überschrift, Pfad `… › Delta`.
- (c) In `Alpha`: Text, Zeile `Unter` mit Schrift der Stufe 2, Text, dann `Beta` → Pfade
  `K1 › U1 › Alpha` (Text davor), `K1 › U1 › Alpha › Unter` (Text danach), `K1 › U1 › Beta`; kein
  Abschnitt `K1 › U1 › Unter`; die Häppchen aus `Unter` beginnen mit dem Pfad samt `Alpha`.
- (d) Negativfall: kurze Fließtextzeile `Gamma` als eigenes Element, Klasse `text`, Schrift in
  Fließtextgröße (außerhalb aller Stufen) → bleibt Fließtext in `Beta`.
- (e) Zeile `Epsilon` mit Überschriften-Klasse, aber Fließtextschrift → bleibt Fließtext (Klasse
  nicht hinreichend).
- (f) Rückfall: Zeile ohne zugeordnete Schrift mit Überschriften-Klasse → Stufe 1, Rückfall-Zähler = 1.
- (g) Veto Tabelle: fette Tabellenzeile `Zeta` (Klasse `table`) mit Schrift der Stufe 1 → keine
  Überschrift, kein Pfad enthält `Zeta`, ihr Text bleibt im umgebenden Abschnitt; Veto-Zähler = 1.
  Gegenprobe: dieselbe Zeile mit Klasse `text` → Überschrift `… › Zeta`.
- (h) Veto Bildunterschrift: Zeile `Eta` mit Klasse `caption` und Schrift der Stufe 1 → keine
  Überschrift, kein Pfad enthält `Eta`.
- Ohne deklarierte Merkmale: Pfade nur aus der Liste (Wirkung von REQ-MB-12 unverändert).

**REQ-MB-21** — *Contract, Hinweis gekennzeichneter Fassungen*
Ein Häppchen einer gekennzeichneten Fassung (REQ-MB-5) trägt seinen deklarierten Hinweistext
im Quellenkopf des Prompts und in seiner Fundstelle (CLI-Quellenausgabe, Pipe-Fusszeile).
Kopf und Fundstelle kommen in CLI und Pipe aus **derselben** Funktion wie REQ-MB-6;
maßgebliche und ungeregelte Häppchen tragen keinen Hinweis.
*Detektor:* synthetischer Bestand aus REQ-MB-5 → Prompt und Pipe-Ausgabe enthalten den
Hinweistext genau bei `regel@beta`, nicht bei `regel@alpha`/`welt@*`. Mutation der
Hinweis-Funktion (liefert Marker) ändert CLI- **und** Pipe-Ausgabe; Änderung des Hinweistexts
in den Daten ändert beide Ausgaben ohne Code-Änderung.

**REQ-MB-22** — *Contract, gedruckte Seite*
Fundstelle und Golden-Set-Seite eines Mehr-Bücher-Bestands ist die **gedruckte** Seite; die
physische PDF-Seite wird zusätzlich gespeichert. Quelle je Buch deklariert: PDF-Seitenlabels
**oder** ein Seitenversatz (gedruckt = physisch − Versatz) als Rückfall. Optional deklarierte
Kontrollpunkte (physisch → gedruckt) werden beim Einlesen geprüft; widersprechen die Labels
einem Kontrollpunkt, bricht das Einlesen mit `KonfigFehler` ab (Hinweis: Versatz deklarieren).
Seiten ohne arabische Zahl als Label (z. B. römisch) tragen keine gedruckte Seite; ihre
Fundstelle nennt „PDF-S. n". Altbestände bleiben physisch (REQ-MB-3).
*Detektor:* synthetisches PDF mit Labels (i, ii, 1, 2, …) → Häppchen von physisch 3 trägt
gedruckt 1, physisch 3; dasselbe mit Versatz 2 ohne Labels → gleiches Ergebnis; falsche Labels
+ Kontrollpunkt → `KonfigFehler`; Seite „ii" → Fundstelle „PDF-S. 2".

**REQ-MB-23** — *Vorbedingung, Extraktionsweg*
Fließtext wird über Docling-Layout (Lesereihenfolge) **ohne LLM-Verbalisierung** extrahiert,
Tabellen roh. Vor der Implementierung von Abschnitt C/D wird an **10 festgelegten
Stichprobenseiten** des Zielbuchs gemessen (davon ≥ 3 Zweispaltenseiten mit Tabelle, ≥ 2 aus
„Talentbeschreibungen"), von Hand gegen das PDF gezählt:
- **L** = Anteil der Absätze in richtiger Lesereihenfolge — Ziel ≥ 95 %;
- **T** = Tabellenzeilen, die in einen Fließtext-Absatz geraten — Ziel 0;
- **H** wird nicht auf den Stichprobenseiten, sondern über **alle Seiten des Abschnitts
  „Talentbeschreibungen"** (physisch 76–107, 149 Talente) gemessen, mit den Merkmalen nach
  REQ-MB-20 (Klasse, Schrift, Rand; ab Fassung 6 zusätzlich Veto-Menge) — Ziel alle erkannt,
  0 Fehltreffer:
  - **vorhanden** = Talente auf diesen Seiten. Die Zählung darf automatisch über einen
    dokumentierten Anker erfolgen (Werteblock, der mit „Stufe:" beginnt); jedes Talent, bei dem
    der Anker nicht greift oder mehrdeutig ist, wird von Hand geprüft und mitgezählt;
  - **erkannt** = Talentnamen, die Layout-Überschrift der **Stufe 1** (Talent-Ebene) werden;
  - **fehltreffer** = Layout-Überschriften der Stufe 1, die kein Talentname sind (zerteilen ein
    Talent oder sind Rand-/Kolumnentitel), plus Layout-Überschriften jeder Stufe, die keine
    inhaltliche Überschrift sind. Zwischenüberschriften der Stufe 2 innerhalb eines Talents sind
    kein Fehltreffer.

Verfehlt eine Zahl ihr Ziel, wird **vor** dem Weiterbauen mit Tobias über den Weg entschieden
(spaltenbewusste Extraktion ohne Docling oder Spaltensatz in Spec 2; bei H über die
Merkmalsdeklaration nach REQ-MB-20).

*Format `vorabmessung.json`* (nur Zahlen außer `docling_version` und `pdfplumber_version`,
REQ-MB-18; beide Zeichenketten mit der jeweils bei der Messung verwendeten Version):
`seiten` (die 10 Stichprobenseiten für L und T), `zweispalten_mit_tabelle` (⊆ `seiten`, ≥ 3),
`talentseiten` (**alle** physischen Seiten von „Talentbeschreibungen", Grundlage von H; davon
≥ 2 auch in `seiten`), `L` `{richtig, absaetze}`, `T` (Zahl), `H` `{erkannt, vorhanden,
fehltreffer, anker, handgeprueft}` mit `anker` = per Anker gezählte Talente und `handgeprueft`
= Talente, die von Hand nachgezählt wurden (Anker griff nicht oder war mehrdeutig);
`erkannt ≤ vorhanden`, `anker ≤ vorhanden ≤ anker + handgeprueft`.
Messung und spätere Ingestion laufen mit **derselben Docling-Version**; sie wird im
Messergebnis `vorabmessung.json` notiert, und die Messung gilt nur für diese Version
(`requirements-ingest.txt` ist heute ungepinnt). Das Einlese-Protokoll notiert die beim Einlesen
verwendete Docling-Version; weicht sie von der im Messergebnis notierten ab, bricht das Einlesen
eines Buchs mit Docling mit `KonfigFehler` ab (keine stille Abweichung). Fehlt `vorabmessung.json` oder enthält sie keine Docling-Version, bricht das Einlesen eines Buchs mit Docling ebenfalls mit `KonfigFehler` ab (kein stilles Überspringen des Versionsvergleichs).
Dasselbe gilt für pdfplumber: Messung und Ingestion mit Schriftinfo (Buch deklariert
Schriftstufen, REQ-MB-20) laufen mit derselben pdfplumber-Version; sie steht als
`pdfplumber_version` im Messergebnis, das Einlese-Protokoll notiert die verwendete Version, und
eine abweichende oder fehlende Version (bzw. fehlende `vorabmessung.json`) bricht das Einlesen
eines Buchs mit Schriftinfo mit `KonfigFehler` ab.
*Detektor:* Messergebnis im obigen Format mit Seitenlisten, L/T/H und Docling-Version liegt im
Spec-Ordner (nur Zahlen, REQ-MB-18), bevor ein Commit Abschnitt C/D implementiert. Versionsprüfung ohne echtes
Docling, Version injiziert: gleiche Version → Einlesen läuft, Protokoll nennt sie; abweichende
Version → `KonfigFehler`, keine Buchdatei geschrieben bzw. alte unverändert. Ohne `vorabmessung.json` bzw. ohne Docling-Version darin → `KonfigFehler` beim Einlesen mit Docling, keine Buchdatei geschrieben bzw. alte unverändert.
Gleiche drei Fälle für `pdfplumber_version` (Version injiziert, Buch mit Schriftstufen): gleich →
Einlesen läuft, Protokoll nennt sie; abweichend bzw. fehlend → `KonfigFehler`, keine Buchdatei
geschrieben bzw. alte unverändert; ein Buch ohne Schriftstufen liest trotz fehlender
`pdfplumber_version` ein. Messergebnis-Format: `pdfplumber_version` ist eine Zeichenkette.

### G. Ergänzungen (Fassung 4, Lücken aus spec-to-tests)

**REQ-MB-24** — *Contract, PDF-Adapter für Lesezeichen und Seitenlabels*
Lesezeichen (Lieferant der Überschriften-Liste, REQ-MB-12) und Seitenlabels (Quelle der
gedruckten Seite, REQ-MB-22) werden beim Einlesen aus der **PDF-Datei selbst** gelesen. Die
Lesezeichen ergeben die Liste (Titel, Ebene nach Verschachtelung, physische Zielseite) in
Dokumentreihenfolge; die Labels ergeben je physischer Seite ihr Label.
*Detektor:* der Test erzeugt ein synthetisches PDF mit Lesezeichen auf **2 Ebenen** und
Seitenlabels (römisch, dann arabisch mit Versatz, z. B. `i`, `ii`, `1`, `2`, …) → die gelesene
Liste stimmt in Titel, Ebene, Seite und Reihenfolge, die gelesenen Labels bzw. daraus ermittelten
gedruckten Seiten stimmen je physischer Seite. `pypdf` (aus `requirements-serve.txt`) darf in der
Testumgebung vorausgesetzt werden.

**REQ-MB-25** — *Contract, Vorspann*
Text vor dem ersten Listeneintrag eines Buchs mit Überschriften-Liste wird nicht verworfen,
sondern bildet einen Abschnitt mit dem Pfad `["Vorspann"]`. Der Name ist Datum/Konfiguration
(Default „Vorspann"); der Abschnitt wird wie jeder andere zerschnitten (REQ-MB-14, -15, -16).
*Detektor:* synthetisches Buch mit eindeutigem Text vor dem ersten Eintrag → dieser Text ist
nach `index` als Häppchen mit Pfad `["Vorspann"]` auffindbar (BM25 bzw. `lade_spiel`); mit
anders konfiguriertem Namen trägt das Häppchen diesen Namen.

**REQ-MB-26** — *When, Veraltet-Prüfung der Pipe*
Die Prüfung der Pipe, ob der Index veraltet ist, liest heute ein einzelnes `knowledge.jsonl` je
Spiel. Für einen Mehr-Bücher-Bestand berücksichtigt sie **alle Buchdateien** des Bestands: wenn
sich eine Buchdatei nach dem Index-Bau ändert, meldet die Pipe den Bestand als veraltet (wie
heute bei der Einzeldatei). Altbestände verhalten sich unverändert (REQ-MB-3).
*Detektor:* Zwei-Bücher-Bestand, `index` gebaut; eine Buchdatei (nicht die erste) danach
ändern → Pipe meldet veraltet; unverändert → Pipe meldet nicht veraltet.

### H. Ergänzungen (Fassung 5, nach Vorab-Messung)

**REQ-MB-27** — *Contract, kein Textverlust aus Bild-Elementen*
Text, den die Extraktion als Kind eines Bild-Elements liefert (z. B. dunkle Textkästen, die
Docling als `picture` erkennt), wird übernommen: **genau einmal**, in Lesereihenfolge an der
Stelle des Bild-Elements (nach dem Element davor, vor dem Element danach), und wie jede andere
Zeile weiterverarbeitet (Reparatur, Überschriften, Zerschneiden). Er ist nach `index` als
Häppchen auffindbar. Das Einlese-Protokoll zählt die aus Bild-Elementen übernommenen
Textelemente.
Anlass (gemessen): mit `iterate_items()` ohne Parameter fehlen im Zielbuch auf 23 Seiten
57 Textelemente (rund 21.700 Zeichen); mit `traverse_pictures=True` stehen sie an der
richtigen Stelle.
*Detektor:* synthetische Extraktionsstruktur ohne echtes Docling: Seite mit Text `Vor`, einem
Bild-Element mit zwei Text-Kindern (eindeutige Marker), Text `Nach`, außerdem ein Bild-Element
ohne Text-Kinder → die Zeilenfolge ist `Vor`, Kind 1, Kind 2, `Nach`, jeder Marker genau einmal;
nach `index` findet BM25 bzw. `lade_spiel` jeden Marker in einem Häppchen; Protokoll-Zähler = 2.
Mutation: Adapter durchläuft Bild-Elemente nicht → Test rot.

### I. Ergänzungen (Fassung 6)

**REQ-MB-28** — *Where, Randzeilen verwerfen*
Wo ein Buch einen Kopf- und/oder Fußrand deklariert (Position nach REQ-MB-20), gelangen Zeilen
im Rand (Kolumnentitel, Seitenzahlen) in **keinen** Häppchentext — weder eingebettet noch im
Prompt — und in keinen Abschnittspfad. Das Einlese-Protokoll zählt die verworfenen Randzeilen
je Buch. Bücher ohne Randangabe und Altbestände bleiben unverändert (REQ-MB-3).
*Detektor:* synthetisches Buch, zwei Seiten, je Seite Kopfzeile mit Marker `KOPFMARKE-n`,
Fußzeile mit Marker `FUSSMARKE-n` und Fließtext mit eigenem Marker; Kopf- und Fußrand deklariert
→ nach `index` enthält kein Häppchen (BM25 bzw. `lade_spiel`) und kein Pfad einen Kopf- oder
Fußmarker, jeder Fließtextmarker ist auffindbar, Protokoll-Zähler = 4. Zwei Bücher im Bestand,
nur eines mit Randangabe → Zähler nur bei diesem, das andere enthält seine Kopf-/Fußmarker wie
vor dieser Änderung (Häppchentexte gleich dem Lauf ohne Randangabe). Mutation: Randzeilen nur
zählen, nicht verwerfen → Test rot.

**REQ-MB-29** — *Contract, Zuordnung der pdfplumber-Zeichen zu den Extraktionszeilen*
Für ein Buch mit Schriftinfo werden jeder Extraktionszeile die pdfplumber-Zeichen zugeordnet,
die auf derselben Seite zu dieser Zeile gehören; daraus ergeben sich ihre Schrift (Mehrheit nach
REQ-MB-20, ohne eindeutige Mehrheit keine Schrift) und ihre Lage für die Randprüfung. Zeichen
einer anderen Zeile — auch einer gleich hohen Zeile der Nachbarspalte — gehen nicht in die
Mehrheit ein.
*Detektor:* der Test erzeugt ein synthetisches PDF mit gesteuerten Schriften (Größen und
Schnitte), z. B. per `reportlab` (reine Testabhängigkeit, darf in der Testumgebung wie
`pdfplumber` vorausgesetzt werden), und dazu die Extraktionszeilen mit ihrer Lage:
- Zeile ganz in Schrift X (z. B. 14 pt fett) → Schrift X;
- gemischte Zeile mit Mehrheit X und einem kürzeren Teil in Schrift Y → Schrift X;
- Zeile mit gleich vielen Zeichen in X und Y → keine zugeordnete Schrift;
- zwei Spalten mit gleich hohen Zeilen in Schrift X (links) und Y (rechts) → links X, rechts Y;
- Zeile im deklarierten Kopfrand → als Rand erkannt; dieselbe Zeile 1 pt außerhalb → nicht.
Mutation: Zuordnung ohne Spaltentrennung (alle Zeichen gleicher Höhe) → Spaltenfall rot.

### J. Ergänzungen (Fassung 7, nach Kritiker-Review)

**REQ-MB-30** — *If/Then, `DROP_TYPES` nur für Altbestände*
Wenn ein Bestand ein Mehr-Bücher-Bestand ist, dann wird `DROP_TYPES` für ihn **nicht angewendet** —
weder beim `index`-Lauf (CLI) noch in der Pipe noch in `eval`/`messung`: kein Häppchen wird wegen
seines `typ` ausgelassen, und ein fehlendes `typ`-Feld ist kein Fehler (auch nicht über die heutige
Prüfung „`DROP_TYPES` ohne `classify.py`-Lauf"). Die Rolle des Ballast-Filters übernimmt dort
`inhaltsart` (REQ-MB-4, -5). Die Prüfung des `DROP_TYPES`-Werts selbst (unbekannte Typen →
`KonfigFehler`) bleibt wie heute. Für Altbestände wirkt `DROP_TYPES` unverändert (REQ-MB-3).
*Detektor:* synthetischer Mehr-Bücher-Bestand, Häppchen ohne `typ`, `DROP_TYPES="flavor,meta"`
(Pipe-Default) → `rag.py index`, Pipe-Antwort und `eval` laufen ohne Fehler; Häppchenzahl im Index
gleich der mit `DROP_TYPES=""`. Wirkungsprobe: Häppchen eines Mehr-Bücher-Bestands, die (künstlich)
`typ: "flavor"` tragen, bleiben im Index und sind per BM25 bzw. `lade_spiel` auffindbar.
Altbestand: bestehende Suite und Referenzen unverändert grün (REQ-MB-3); Altbestand ohne `typ` mit
`DROP_TYPES=flavor` bricht wie heute ab, Altbestand mit `typ: "flavor"` verliert diese Häppchen wie
heute.

**REQ-MB-31** — *If/Then, Listenüberschrift nach Lage einsortieren*
Wenn auf einer Seite eine Zeile `Ü` einem Listeneintrag zugeordnet ist (REQ-MB-12), dann werden die
Elemente der Seite nach der Lage von `Ü` umsortiert. Lage eines Elements = `x0`, `x1`, `oben`, `unten`
in PDF-Punkten (Ursprung oben links, wie REQ-MB-20). Ein Element `E` derselben Seite **liegt unter
`Ü`**, wenn beide eine Lage haben und gilt:
1. der vertikale Mittelpunkt von `E` liegt unterhalb der Unterkante von `Ü`:
   `(E.oben + E.unten) / 2 > Ü.unten`, und
2. `E` und `Ü` überlappen sich waagrecht: `E.x0 < Ü.x1` und `Ü.x0 < E.x1`.

Jedes Element, das in der Extraktionsfolge **vor** `Ü` steht und unter `Ü` liegt, wird hinter `Ü`
verschoben: die verschobenen Elemente stehen unmittelbar hinter `Ü`, untereinander in ihrer
bisherigen Reihenfolge, danach die bisherigen Nachfolger von `Ü`; alle übrigen Elemente behalten
ihre Reihenfolge. Eine spaltenübergreifende Überschrift überlappt waagrecht beide Spalten und zieht
damit die unter ihr liegenden Elemente **beider** Spalten hinter sich; eine Überschrift, die nur in
einer Spalte steht, verschiebt kein Element der Nachbarspalte. Sind auf einer Seite mehrere Zeilen
zugeordnet, wird die Regel für sie in Listenreihenfolge nacheinander auf die jeweils aktuelle Folge
angewandt.

Unverändert bleibt: hat `Ü` keine Lage, wird nichts verschoben; ein Element ohne Lage wird nicht
verschoben; Elemente, die in der Extraktionsfolge **nach** `Ü` stehen, bleiben, wo sie sind (auch
wenn sie über `Ü` liegen); Randzeilen (REQ-MB-12, -28) werden nicht verschoben; Layout-Überschriften
(REQ-MB-20) und nicht gefundene Einträge (REQ-MB-13) lösen kein Umsortieren aus. Der Abgleich
(REQ-MB-12, einschließlich „erste in Lesereihenfolge" bei Gleichstand) läuft auf der ursprünglichen
Folge; Abschnittsbildung, REQ-MB-13 und REQ-MB-20 arbeiten auf der umsortierten. Das
Einlese-Protokoll zählt die verschobenen Elemente je Buch („umsortiert").
Anlass (gemessen): Docling liefert auf zweispaltigen Seiten mit spaltenübergreifender
Kapitelüberschrift die Überschrift **nach** dem ersten Eintrag der linken Spalte (S. 76: das erste
Talent landet unter dem vorherigen Kapitel; S. 114 analog).
*Detektor:* synthetische Seitenzeilen mit Lage, Liste `Alt` (Vorseite), `Neu` (diese Seite):
`Oben` (links, über `Neu`, Marker `OBENMARKE`), `Links` (links, unter `Neu`, Marker `LINKSMARKE`),
`Neu` (über beide Spalten), `Rechts` (rechts, unter `Neu`) in dieser Extraktionsfolge → `LINKSMARKE`
und `Rechts` liegen im Abschnitt `Neu`, `OBENMARKE` in `Alt`; Protokoll „umsortiert = 1".
Gegenproben: (a) `Neu` nur über der rechten Spalte (`x0` rechts von `Links.x1`) → `LINKSMARKE`
bleibt in `Alt`, „umsortiert = 0"; (b) dieselbe Seite ohne Lageangaben → Folge unverändert,
`LINKSMARKE` in `Alt`; (c) `Links` mit Mittelpunkt 1 pt über `Neu.unten` → nicht verschoben.
Mutation: Umsortieren aus → Test rot.

**REQ-MB-32** — *Contract, Verdachtszähler für Striche*
Das Einlese-Protokoll zählt je Buch auf jedem Extraktionsweg, nach der Reparatur (REQ-MB-11), in den
Abschnittstexten (ohne Titelvorsatz) zwei Arten von Verdachtsfällen und nennt je Art Anzahl und
Seiten (gedruckt, sonst physisch); der Text wird dadurch **nicht** verändert:
- **Binnen-Großbuchstabe:** ein Kleinbuchstabe (Unicode `Ll`), unmittelbar gefolgt von einem
  Großbuchstaben (`Lu`), z. B. `NovizenTalent` — Verdacht auf einen gestrichenen Bindestrich;
- **Strichrest:** ein Buchstabe, `-`, ein oder mehrere Leerzeichen, dann ein Wort, das mit einem
  Kleinbuchstaben beginnt und nicht in der Konjunktionsliste der Buchsprache steht (REQ-MB-11),
  z. B. `Akti- onswürfel` — Verdacht auf eine nicht zusammengefügte Trennung.

Anlass (gemessen, Docling-Weg): Silbentrennungen zu 99,3 % richtig zusammengefügt, aber echte
Binde-/Ergänzungsstriche in 26 von 69 Fällen zusammengezogen; die Reparatur nach REQ-MB-11 griff nur
bei 0,8 % der Trennungen.
*Detektor:* synthetische Docling-Struktur (ohne echtes Docling) mit den Elementen `Das NovizenTalent
wirkt` (S. 1), `die Akti- onswürfel` (S. 2), `Nah- und Fernkampf`, `ED4-Regeln`, `Zwerg-Krieger`
(S. 3) → Protokoll „Binnen-Großbuchstabe = 1 (S. 1)", „Strichrest = 1 (S. 2)"; alle Elementtexte
byte-gleich im Häppchentext. Mutationen: Konjunktionsausnahme fehlt (`Nah- und` zählt mit) → rot;
Zähler zählt nicht → rot.

**REQ-MB-33** — *Contract, Listentitel normalisiert*
Titel der Überschriften-Liste (aus Lesezeichen und Inhaltsverzeichnis, REQ-MB-12, -24) werden vor
jeder Verwendung normalisiert: `titelnorm(t)` = Unicode-NFC, jede Folge von Leerraumzeichen
(`str.isspace`, u. a. Leerzeichen, Tab, CR, LF, U+00A0) → ein Leerzeichen, Leerraum am Anfang und Ende
entfernt. Abschnittspfad, Titelvorsatz (REQ-MB-15), die ersetzte Zeile (REQ-MB-12) und die
Protokolleinträge (REQ-MB-13) verwenden die normalisierte Form. Jedes Element eines
Abschnittspfads — auch Layout-Überschriften (REQ-MB-20) und der Vorspann-Name (REQ-MB-25) — wird
mit `titelnorm` gebildet; der Titelvorsatz ist damit **einzeilig** (genau ein Zeilenumbruch, der am
Ende vor dem Text). Die Präfixe der Inhaltsart-Zuweisung (REQ-MB-1, O-3) werden mit derselben
Funktion normalisiert und dann wie bisher exakt mit den Pfadelementen verglichen.
Anlass (gemessen): 48 von 148 Lesezeichen-Titeln enthalten `\r\n`, 73 abweichenden Leerraum →
28,9 % der Häppchen mit CR/LF im Titelvorsatz; Präfix-Zuweisungen griffen still nicht.
*Detektor:* synthetisches PDF (wie REQ-MB-24) mit Lesezeichen `"Kapitel\r\nZwei"`,
`"Teil  Drei\t"` (Doppelleerzeichen, Tab) und `"Übersicht"` (NFD), dazu eine
Inhaltsverzeichnis-Liste mit einem Titel `"Anhang\r\nEins"`; Zuweisung `["Kapitel Zwei"]` → `welt`
bei Standard `regel` → Pfade `["Kapitel Zwei"]`, `["Teil Drei"]`, `["Übersicht"]` (NFC),
`["Anhang Eins"]`; kein Abschnittspfad und kein Titelvorsatz enthält CR, LF (außer dem einen am
Vorsatzende), Tab oder Doppelleerzeichen; Häppchen unter `Kapitel Zwei` tragen `welt`, die übrigen
`regel`. Mutation: Normalisierung aus → Test rot.

**REQ-MB-34** — *If/Then, Schema der Layout-Deklaration*
Wenn die Deklaration eines Buchs für `layout` (samt `stufen` und `veto`) oder `rand` gegen ihr Schema
verstößt, dann bricht das Einlesen dieses Buchs mit `KonfigFehler` ab, bevor eine Buchdatei
geschrieben wird (eine vorhandene bleibt unverändert); die Meldung nennt den fehlerhaften Schlüssel.
Schema:
- `layout`: Objekt, nur die optionalen Schlüssel `klasse` (nicht-leere Zeichenkette), `stufen`
  (nicht-leere Liste von Stufen), `veto` (Liste nicht-leerer Zeichenketten), `hoechstlaenge`
  (ganze Zahl ≥ 1);
- Stufe: Objekt mit **mindestens einem** der Schlüssel `groesse` (Bereich, `von` > 0), `laufweite`
  (Bereich), `fett`, `kursiv`, `kapitaelchen` (je Wahrheitswert), keine anderen;
- Bereich: Liste aus genau zwei Zahlen `[von, bis]` mit `von ≤ bis`;
- `rand`: Objekt mit mindestens einem der Schlüssel `kopf`, `fuss` (je Zahl ≥ 0), keine anderen.

Unbekannte Schlüssel (auch Tippfehler und das gestrichene Merkmal „eigene Zeile"), falsche Typen
(Wahrheitswerte zählen nicht als Zahl), leere Stufen und Bereiche mit `von > bis` sind Verstöße.
Anlass (gemessen): ein Tippfehler `groese` ergab eine Stufe ohne Angabe — jede Zeile wurde
Überschrift.
*Detektor:* je Fall ein synthetisches Buch → `KonfigFehler`, keine Buchdatei bzw. alte byte-gleich:
Stufe `{"groese": [10, 12]}`; `layout` `{"groese": …}`; Stufe `{}`; `groesse` `[14, 12]`;
`groesse` `[12]`; `rand` `{"kopf": "40"}`; `rand` `{"kopf": true}`; `veto` `"table"`;
`hoechstlaenge` `0`; `layout` `{"eigene_zeile": true}`. Gegenprobe: eine gültige Deklaration mit
allen Schlüsseln liest ein und ergibt dieselben Abschnitte wie vor der Prüfung. Mutation:
Schemaprüfung aus → Test rot.

## Lesarten (festgelegt)

Von Tobias bestätigt (Fassung 4):

- **MB-2** „falsche Deklaration im Aufruf": `spiel.json` wird nach dem Index-Bau verfälscht; `lade_spiel` liefert trotzdem die Zeilenwerte des Index.
- **MB-11** Die Zähler zählen nur die eindeutigen Fälle der Tabelle; die Konjunktionsliste ist ein Konfigurationsparameter je Sprache.
- **MB-14** „Protokoll" der Häppchenzahl = Ausgabe des Index-Laufs je Buch.
- **MB-17** Earthdawn-Wörter in den Spec-Tabellen sind Testdaten, kein Code-Bezug.
- **Inhaltsart** Das Vokabular ist frei; `regel`/`welt` sind nur Beispiele.
- **MB-18** Die Code-Mutation „Bücherdatei neben den Code schreiben" wird mit der Implementierung in `test_mutationen.py` ergänzt.

## Abgrenzung (nicht in Spec 1)

- Hausregeln als Markdown (Art neu/ergänzt/ersetzt, Bezug, feste Mitlieferung) — eigene Spec.
- Zahlentreue: Schablonen-Serialisierung für Werteblöcke, Zahlenprüfung nach LLM-Verbalisierung.
- Tabellen an falscher Stelle in der Lesereihenfolge (Tabelle hinter allen Absätzen der Seite,
  dadurch unter der letzten Überschrift der Seite statt unter ihrer eigenen; gemessen S. 22) —
  gehört zu Spec 2 (Werteblöcke/Tabellen).
- Falsche Lesereihenfolge neben Bildern (gemessen S. 94, rechte Spalte) — Spec 2, zusammen mit
  den Tabellen.
- OCR-Vertauschungen im Überschriften-Abgleich (Fehlerklasse 3, REQ-MB-12).
- Rekonstruktion echter Binde- und Ergänzungsstriche auf dem Docling-Weg (z. B. über
  pdfplumber-Zeilen); Spec 1 zählt nur Verdachtsfälle (REQ-MB-32). Gemessen: 26 von 69 echten
  Strichen zusammengezogen — Spec 2.
- Elemente, die die Extraktion **nach** einer Listenüberschrift liefert, die aber über ihr liegen
  (Gegenrichtung zu REQ-MB-31) — Spec 2, zusammen mit der Lesereihenfolge neben Bildern.
- FTS5-Trigram bzw. Komposita-Suche.
- Earthdawn-Testsatz (Golden Set) — Daten, nicht Code; folgt nach Spec 1.
- Übersetzungs-/Suchfassung für englische Bände (Throal).
- Automatische Erkennung, ob eine *Frage* eine Regel- oder Weltfrage ist.

## Entscheidungen (Tobias, 2026-10-21)

- **O-1 (a)** je Buch eigene `knowledge.jsonl` + Fingerprint — Ersetzen/Inkrementell folgen direkt aus Datei-Hashes (MB-1, -8, -9).
- **O-2 (a)** `inhaltsart` orthogonal zu `typ` — sonst löscht `DROP_TYPES=flavor` Weltwissen (Begriffe).
- **O-3 (a)** Standard je Buch + Präfix-Zuweisung — deterministisch, prüfbar (MB-1).
- **O-4 (b)** neue Spalten, Altstände gültig, Migration getestet — kein Neu-Einbetten ohne Textänderung (MB-3).
- **O-5 (b)** gedruckte Seite, physische zusätzlich; Labels mit Versatz als Rückfall — mit dem Buch in der Hand zählt die gedruckte Seite (MB-22).
- **O-6 (a)** Trennungsregeln wie MB-11 + Protokoll-Zähler — Wörterbuch erst, wenn eine Stichprobe Fehlzusammenfügungen zeigt (MB-11).
- **O-7 (a)** `CHUNK_SIZE` ohne Vorsatz, keine Zusammenlegung, zeichengenau — Wirkung der Grenzen getrennt messbar (MB-14).
- **O-8 (a)** Docling-Layout ohne Verbalisierung, Tabellen roh, Vorabmessung — Verbalisierung gehört zur Zahlentreue-Spec (MB-23). Performance-Zahlen MB-19 unverändert übernommen.
- **O-9 (b)** keine Tier-Map — ohne CI keine Neuberechnung, jeder Merge wird ohnehin abgenommen (Tier).
- **N-1 (c)** Layout-Merkmale zuerst nur aus der Docling-Layout-Klasse, pdfplumber-Schriftinfo nur bei verfehltem H — ein Extraktionsweg weniger, falls die Klasse reicht (MB-20, -23).
- **N-1 revidiert nach Vorab-Messung** (Docling 2.131.0, 2026-10-21): Klasse allein verfehlt H — Stichprobe 11/11 erkannt, aber 2 Fehltreffer (Kolumnentitel); über alle 32 Talentseiten 182 `section_header`, davon 25 Kolumnentitel, 147/149 Talentnamen (2 neben Bildern als `text`), 7 Zwischenüberschriften innerhalb von Talenten und 1 Tabellentitel auf Talent-Ebene. Neu: Klasse + pdfplumber-Schrift (Stufen) + Kopf-/Fußrand, Schrift hinreichend, Klasse nur Rückfall; H über alle Talentseiten; Text aus Bild-Elementen übernehmen (MB-20, -23, -27). L 111/114 = 97,4 % und T = 0 erfüllt.
- **N-2 (a)** gekennzeichnete Fassungen im Ranking gleich behandelt — eine Rangregel ändert die Messung und ist erst mit einem Earthdawn-Golden-Set bewertbar (MB-5).
- **F6-1** Layout-Klasse mit Vetorolle: Zeilen einer Veto-Klasse (mindestens Tabelle/Zelle, Bildunterschrift, Seitenkopf, Seitenfuß) sind nie Überschrift; sonst entscheidet die Schrift, Rückfall auf die Klasse bleibt (MB-20).
- **F6-2** Rand auch beim Listenabgleich: Randzeilen sind kein Kandidat und zählen nicht für „mehrdeutig" (MB-12).
- **F6-3** Randzeilen werden verworfen und je Buch gezählt; ohne Randangabe unverändert (MB-28).
- **F6-4** pdfplumber-Version wie die Docling-Version gemessen und geprüft; Zuordnung der Zeichen zu den Zeilen eigenes Kriterium mit synthetischem PDF (`reportlab` als Testabhängigkeit) (MB-23, -29).
- **F6-5** Falsche Lesereihenfolge neben Bildern (S. 94) in Spec 2, zusammen mit den Tabellen (Abgrenzung).

Fassung 7 (Tobias, 2026-10-22, nach Kritiker-Review am echten Buch):

- **F7-1** `DROP_TYPES` wird für Mehr-Bücher-Bestände nicht angewendet, `inhaltsart` übernimmt; Altbestände unverändert — gemessen: Mehr-Bücher-Häppchen tragen kein `typ`, der Pipe-Default `flavor,meta` brach mit `KonfigFehler` ab (MB-30).
- **F7-2** Listenüberschrift nach Lage vor die unter ihr liegenden Elemente einsortieren, spaltenübergreifend über beide Spalten — gemessen: S. 76 und S. 114 erstes Talent unter dem vorherigen Kapitel (MB-31).
- **F7-3** Zeilenend-Reparatur nur auf Wegen mit Zeilenenden, auf dem Docling-Weg Verdachtszähler; Strich-Rekonstruktion in Spec 2 — gemessen: Silbentrennung 99,3 % richtig, echte Striche 26/69 zusammengezogen, MB-11 griff bei 0,8 % der Trennungen (MB-11, -32).
- **F7-4** `norm()` entfernt zusätzlich Formatzeichen (`Cf`, u. a. U+00AD) — gemessen: 1 Lesezeichen wegen U+00AD im Seitentext nicht gefunden (MB-12).
- **F7-5** Listentitel vor Verwendung normalisiert (Leerraum → ein Leerzeichen, trim, NFC), Vorsatz einzeilig, Präfixe ebenso — gemessen: 48/148 Titel mit `\r\n`, 73 mit abweichendem Leerraum, 28,9 % der Häppchen mit CR/LF im Vorsatz (MB-33).
- **F7-6** MB-19 Altbestand: Maximum als Median der Maxima aus 5 Wiederholungen je Seite, Grenze +20 %; Zeittests zählen in Mutationsproben nicht als Fang — gemessen: 2/26 Läufe rot, Verhältnis der Einzel-Maxima 0,47–2,35 bei typisch 1,002 (MB-19).
- **F7-7** Zeilenmerkmal „eigene Zeile" gestrichen, Layout-/Rand-Deklaration gegen Schema geprüft — gemessen: Tippfehler `groese` machte jede Zeile zur Überschrift; „eigene Zeile" war nie definiert noch umgesetzt (MB-20, -34).
- **F7-A** Abnahme-Auslegungen (Tobias, 2026-10-22): weicher Trennstrich (U+00AD) im Wort wird auf allen Extraktionswegen entfernt (MB-11 Tabellenzeile 2); MB-31 regelt nur „vorher geliefert, liegt darunter“ (Gegenrichtung Spec 2); MB-19 neu und Basis abwechselnd; MB-33 normalisiert auch Präfixe aus spiel.json und alle Pfadelemente; MB-30 behält die Prüfung unbekannter DROP_TYPES-Werte.

## Tier

**T3**, ohne Tier-Map (Entscheidung O-9 b). `derive-tier.js` findet keine Map (Exit 2), die
devloop-Regel „unbekannter Pfad → höchste Stufe" greift; inhaltlich passend (Index-Schema,
Pipe-Schnittstelle, Fundstellen-Contract). Ohne CI-Anker keine server-seitige Neuberechnung;
maßgeblich ist Tobias' Abnahme jedes Merges.
