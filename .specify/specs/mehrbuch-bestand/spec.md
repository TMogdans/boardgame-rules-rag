# Spec: Mehr-Bücher-Bestand — Datenmodell und Einlesen

- **Spec-ID:** mehrbuch-bestand (Spec 1 von voraussichtlich 2–3)
- **Kontext-Kürzel:** MB
- **Tier:** T3 — **vorläufig/advisorisch**, siehe Abschnitt „Tier"
- **Status:** Entwurf, wartet auf Abnahme durch Tobias (harter Spec-Stopp)

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
| **Abschnittspfad** | Überschriften-Hierarchie eines Häppchens, z. B. `["Kapitel 4: Disziplinen", "Krieger", "Talente"]`. |
| **Inhaltsart** | Themenbereich eines Abschnitts, mindestens `regel` und `welt`. Siehe O-2 zum Verhältnis zu `typ` aus `classify.py`. |
| **Altbestand** | Ein Bestand, dessen `spiel.json` keine Bücherliste hat (heutiges Format, ein `quelle_pdf`). |

Unberührt bleibt der Einzeldatei-Weg (`knowledge.jsonl`/`pdfs/` neben `rag.py`, ohne Index).

## Akzeptanzkriterien

### A. Datenmodell

**REQ-MB-1** — *Contract*
Ein Bestand kann in `spiel.json` eine Liste von Büchern deklarieren; jedes Buch hat
`buch_id` (Slug, im Bestand eindeutig), `titel`, `fassung`, `sprache` (aus `rag.SPRACHEN`)
und eine Quelldatei; optional eine Standard-Inhaltsart und Inhaltsart-Zuweisungen je
Abschnittspfad-Präfix (siehe O-3). Ein Altbestand wird gelesen, als hätte er genau ein Buch
(`buch_id`, Titel und Fassung aus vorhandenen Angaben abgeleitet), **ohne dass eine Datei
umgeschrieben wird**.
*Detektor:* synthetischer Bestand mit zwei Büchern → `rag.py index` legt Häppchen beider
Bücher an; Altbestand-Verzeichnis ist nach `index` byte-gleich (Hash aller Dateien).

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
`test_mutationen.py` und `messung/` bleiben **ohne Änderung ihrer Sollwerte** grün.
Ob ein Altbestand dabei neu eingebettet werden darf, entscheidet O-4.
*Detektor:* bestehende Suite unverändert; Diff der Referenzdateien leer.

**REQ-MB-4** — *When, Filter vor dem Ranking*
Wenn eine Suche mit Filter auf `buch_id`, `fassung`, `sprache` und/oder `inhaltsart` läuft,
dann stammen alle Kandidaten — für Vektorsuche, BM25 (`HYBRID=1`) und Reranker-Kandidatenfeld
— ausschließlich aus passenden Häppchen; ein nicht passendes Häppchen kann kein passendes
verdrängen. Ein Filter auf einen Wert, den der Bestand nicht hat, bricht mit `KonfigFehler`
ab (keine stille leere Suche).
*Detektor:* Konstruktion mit einem nicht passenden Häppchen, dessen Vektor gleich dem
Fragevektor ist (Score 1,0) — es erscheint nicht, und die Top-k sind identisch zur Suche in
einem Bestand, der nur die passenden Häppchen enthält. Gleiches mit BM25-Treffer.

**REQ-MB-5** — *Where, Fassungsregel*
Wo ein Bestand für eine Inhaltsart erlaubte Fassungen festlegt (z. B. `regel` nur aus
Fassung `ED4`), sind Häppchen dieser Inhaltsart aus anderen Fassungen **nie** Kandidaten;
Häppchen anderer Inhaltsarten (z. B. `welt`) kommen weiter aus allen Fassungen. Die Regel
gilt bei jeder Suche des Bestands (CLI, Eval, Pipe), unabhängig von der Frage, und wirkt wie
REQ-MB-4 vor dem Ranking.
*Detektor:* synthetischer Bestand mit Fassungen `A`/`B`, je ein `regel`- und ein
`welt`-Häppchen mit Score 1,0 → nur `regel@A`, `welt@A`, `welt@B` erreichbar.

**REQ-MB-6** — *Contract, Fundstelle*
In einem Mehr-Bücher-Bestand nennen Quellenkopf im Prompt (`baue_kontext`), Pipe-Fusszeile
und die Seitenangaben des Entscheidungsschritts (C-Text, B-Hinweis, Sprachmodus) je Fundstelle
**Buch (Titel oder Kurzname), Fassung und Seite**. CLI und Pipe erzeugen dieselben Köpfe aus
derselben Funktion. Welche Seite (physisch/gedruckt) gilt, entscheidet O-5.
*Detektor:* Prompt-Nachrichten und Pipe-Ausgabe für einen synthetischen Zwei-Bücher-Bestand
mit gleicher Seitenzahl in beiden Büchern sind unterscheidbar; für Altbestände greift REQ-MB-3.

**REQ-MB-7** — *If/Then, Messung*
Golden-Set-Fragen eines Mehr-Bücher-Bestands können erwartete Fundstellen als
(`buch_id`, Seite) angeben; ein Treffer zählt nur bei passendem Buch. Wenn ein Golden Set
eines Mehr-Bücher-Bestands eine Seite ohne Buch angibt, dann bricht `eval`/`messung` mit
`KonfigFehler` ab (keine stille Wertung gegen ein beliebiges Buch). Altbestände: REQ-MB-3.
*Detektor:* Frage mit erwarteter Seite 12 in Buch A, Treffer auf Seite 12 in Buch B → verfehlt.

### B. Quelle ersetzen und inkrementell einbetten

**REQ-MB-8** — *When*
Wenn die Quelle eines Buchs durch eine andere Fassung oder Auflage ersetzt wird (gleiche
`buch_id`, neue Fassung/Quelldatei, neu eingelesen) und danach `rag.py index` läuft, dann
enthält der Index für diese `buch_id` nur noch Häppchen der neuen Fassung — null Häppchen
der alten, auch in FTS — und die Häppchen der übrigen Bücher werden **nicht** neu eingebettet.
*Detektor:* Fake-`embed` zählt eingebettete Texte: genau die Häppchenzahl des ersetzten
Buchs; Zeilenzählung je `buch_id`/`fassung` in `chunks` und `chunks_fts`.

**REQ-MB-9** — *When*
Wenn ein Buch neu hinzukommt oder unverändert bleibt, wird nur das neue Buch eingebettet;
ein `index`-Lauf ohne Änderung bettet nichts ein. Das Einlesen eines Buchs lässt die
Daten der anderen Bücher desselben Bestands byte-gleich.
*Detektor:* Embed-Zähler 0 beim zweiten Lauf; Dateihashes der anderen Bücher vor/nach Ingestion.

**REQ-MB-10** — *If/Then*
Wenn die Deklaration doppelte `buch_id`s enthält, zwei Bücher dieselbe Quelldatei nennen
oder Häppchen eine nicht deklarierte `buch_id` tragen, dann bricht `index` für diesen
Bestand mit `KonfigFehler` ab und dessen alter Stand bleibt (wie heute bei kaputten Spielen).
*Detektor:* je Fall ein synthetischer Bestand; Index-Inhalt vorher = nachher.

### C. Einlesen-Reparatur

Die Reparatur ist eine reine Funktion auf dem Seitentext **vor** jedem Whitespace-Zusammenfassen
und wird je Buch eingeschaltet (für Altbestände und den rohen PDF-Weg aus: REQ-MB-3).

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

Die Konjunktionsliste ist sprachabhängig und Teil der Daten/Konfiguration (O-6).
*Detektor:* Tabelle als Testfälle; zusätzlich Zähler „zusammengefügte Trennungen" im
Einlese-Protokoll.

**REQ-MB-12** — *Where, Überschriften-Quelle*
Wo ein Buch eine Überschriften-Quelle deklariert, gilt diese als Wahrheit für die
Abschnittspfade. Der Mechanismus nimmt allgemein eine Liste (Titel, Ebene, Seite); Lieferanten
sind mindestens **PDF-Lesezeichen** und eine **Inhaltsverzeichnis-Liste** (Titel, Ebene,
gedruckte Seite + Seitenversatz). Eine kaputte Überschrift im Seitentext, die auf der
Zielseite unscharf zum Listeneintrag passt, wird im Text durch den Listentitel ersetzt.
*Detektor:* definierte Eingabe (Seitentexte + Liste): Seite 7 enthält `Bonusw rfel` bzw.
`A ktionswürfel`, Liste nennt `Bonuswürfel`/`Aktionswürfel` auf Seite 7 → Abschnittspfad und
Häppchentext enthalten die korrekte Form, die kaputte nicht mehr; eine gleich lautende
Zeichenfolge auf einer anderen Seite bleibt unangetastet.

**REQ-MB-13** — *If/Then*
Wenn ein Listeneintrag auf seiner Zielseite nicht gefunden wird, dann beginnt sein Abschnitt
am Anfang der Zielseite, und der Eintrag erscheint im Einlese-Protokoll mit Titel und Seite
(Zähler gefunden/nicht gefunden). Kein Eintrag verschwindet still.
*Detektor:* Liste mit einem Eintrag ohne Gegenstück → Abschnitt vorhanden, Protokoll nennt ihn.

### D. Zerschneiden nach Überschriften

**REQ-MB-14** — *Contract, Abschnittsgrenzen*
Bei Büchern mit Überschriften-Quelle enthält kein Häppchen Text aus zwei verschiedenen
(Blatt-)Abschnitten; auch die Überlappung (`CHUNK_OVERLAP`) reicht nie über eine
Abschnittsgrenze. Ein Abschnitt, der kürzer als `CHUNK_SIZE` ist, ergibt genau ein Häppchen;
ein längerer wird innerhalb des Abschnitts nach `CHUNK_SIZE`/`CHUNK_OVERLAP` geteilt. Ob der
Titelvorsatz (REQ-MB-15) zur Größe zählt und ob kurze Geschwister zusammengelegt werden,
entscheidet O-7.
*Detektor:* synthetisches Buch mit markierten Abschnittstexten; jedes Häppchen ist Teilstring
genau eines Abschnitts (ohne Vorsatz).

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
Buchtitel, Fassungen und Inhaltsarten-Zuweisungen keinen Bezug zu Earthdawn haben; es gibt
keinen Code-Pfad, der nur bei bestimmten Bestands- oder Buchnamen wirkt.
*Detektor:* sämtliche Tests dieser Spec laufen mit einem Bestand `testwelt` und Fassungen
`alpha`/`beta`; Umbenennen aller Bezeichner in den Testdaten ändert kein Ergebnis.

**REQ-MB-18** — *Architektur, Urheberrecht*
Kein Test liest echte Bücher oder `DATA_DIR`-Inhalte; alle Testdaten sind synthetisch und
werden im Test erzeugt. Einlese-Ergebnisse geschützter Bücher entstehen nur unter
`DATA_DIR`/`pdfs/` (gitignored). `test_schutz.py` deckt die neuen Schreibpfade (Bücherdateien,
Einlese-Protokoll) mit ab.
*Detektor:* `test_schutz.py` mit Mutation „Bücherdatei neben den Code schreiben" wird rot.

**REQ-MB-19** — *Performance*
Laden und Vektorsuche in einem Bestand mit 5 Büchern und zusammen 3.000 Häppchen
(1.024 Dimensionen, Embedding gefakt, mit aktivem Filter nach REQ-MB-4/-5): **typisch ≤ 15 ms,
Maximum ≤ 30 ms** je Frage über 200 Fragen; Altbestände nicht langsamer als heute
(README: 2.000 Häppchen typisch 9,1 ms, max 13,5). Zahlen sind Vorschlag, siehe O-8.
*Detektor:* Messskript mit typisch und Maximum, wie die README-Messung.

## Abgrenzung (nicht in Spec 1)

- Hausregeln als Markdown (Art neu/ergänzt/ersetzt, Bezug, feste Mitlieferung) — eigene Spec.
- Zahlentreue: Schablonen-Serialisierung für Werteblöcke, Zahlenprüfung nach LLM-Verbalisierung.
- FTS5-Trigram bzw. Komposita-Suche.
- Earthdawn-Testsatz (Golden Set) — Daten, nicht Code; folgt nach Spec 1.
- Übersetzungs-/Suchfassung für englische Bände (Throal).
- Automatische Erkennung, ob eine *Frage* eine Regel- oder Weltfrage ist.

## Offene Fragen (Entscheidung durch Tobias)

**O-1 Ablage der Bücher im Bestand**
(a) je Buch eine eigene Datei `data/<id>/buecher/<buch_id>/knowledge.jsonl`, Fingerprint je Buch;
(b) eine `knowledge.jsonl` je Bestand mit Feld `buch_id`, Fingerprint je Bestand, Ersatz per Filter-Neuschreiben;
(c) wie (b), aber Fingerprint über die Zeilen je Buch.
*Empfehlung (a):* REQ-MB-8/-9 folgen direkt aus Datei-Hashes; Ersetzen = eine Datei ersetzen;
`--ueberschreiben` wirkt nur auf ein Buch. Altbestände behalten ihre eine Datei (REQ-MB-1).

**O-2 Inhaltsart vs. `typ` aus `classify.py`**
(a) eigenes Feld `inhaltsart` (regel/welt/…), orthogonal zu `typ` (regel/flavor/meta = Ballast-Filter für `DROP_TYPES`);
(b) `typ` um `welt` erweitern; (c) `flavor` als `welt` umdeuten.
*Empfehlung (a):* Welttext ist bei Earthdawn gesuchter Inhalt, `flavor` ist Ballast —
zusammengelegt würde `DROP_TYPES=flavor` Weltwissen löschen, und die Klassifikator-Garantien
(`test_classify.py`, Sollwerte) blieben nicht unverändert.

**O-3 Wie bekommt ein Abschnitt seine Inhaltsart?**
(a) Deklaration: Standard je Buch + Zuweisung je Abschnittspfad-Präfix in `spiel.json`;
(b) LLM-Klassifikation je Abschnitt (wie `classify.py`); (c) (a) mit (b) als Vorschlag, den die Deklaration übersteuert.
*Empfehlung (a)* für Spec 1: deterministisch, prüfbar, bei Lesezeichen-Gliederung pro Kapitel
wenige Zeilen; (b)/(c) später, falls Mischkapitel häufig sind.

**O-4 Index-Schema und Altbestände**
(a) `INDEX_SCHEMA` hochzählen → alle Stände ungültig, alles wird einmal neu eingebettet;
(b) Schema-Erweiterung per neuer Spalten mit Altwerten (NULL/abgeleitet), Altstände bleiben gültig, kein Neu-Einbetten;
(c) neue Tabelle für Buch-Metadaten, `chunks` nur um `buch_id` erweitert, sonst wie (b).
*Empfehlung (b):* Altbestände ändern ihre Texte nicht, ein Neu-Einbetten wäre reiner Aufwand
und würde die README-Aussage „nur was sich geändert hat" verletzen. Kostet eine Migration,
die selbst getestet werden muss (Index von vorher → Abfrage-Ergebnis gleich).

**O-5 Welche Seite ist die Fundstelle?**
(a) physische PDF-Seite wie heute; (b) gedruckte Seite (aus PDF-Seitenlabels oder Seitenversatz je Buch), physische zusätzlich gespeichert;
(c) beides in der Fundstelle („S. 112 (PDF 114)").
*Empfehlung (b):* Mit dem Buch in der Hand zählt die gedruckte Seite; Golden Sets eines
Mehr-Bücher-Bestands schreiben dann gedruckte Seiten. Altbestände bleiben physisch (REQ-MB-3).

**O-6 Trennungs-Heuristik**
(a) Regeln wie in REQ-MB-11 (Kleinbuchstabe → zusammen, außer vor Konjunktion; Groß/Ziffer → Strich bleibt);
(b) zusätzlich Wörterbuchprüfung gegen das Vokabular des Buchs (zusammengesetztes Wort kommt anderswo ungetrennt vor);
(c) nur (b).
*Empfehlung (a)* jetzt, mit Protokoll-Zähler; (b) erst, wenn eine Stichprobe der ~3.200
Trennungen Fehlzusammenfügungen zeigt.

**O-7 Häppchengröße bei Abschnitten**
(a) `CHUNK_SIZE` gilt für den Text ohne Titelvorsatz, keine Zusammenlegung kurzer Abschnitte;
(b) `CHUNK_SIZE` inklusive Vorsatz; (c) wie (a), kurze Geschwister unter gemeinsamem Elternpfad bis `CHUNK_SIZE` zusammenlegen.
Innerhalb eines Abschnitts schneidet `zerteile` wie heute zeichengenau (auch mitten im Wort) — alternativ an Wortgrenzen.
*Empfehlung (a), zeichengenau wie heute:* ein Werteblock bleibt bei seinem Namen, und die
Wirkung der Abschnittsgrenzen ist getrennt von einer Schnitt-Änderung messbar. Häppchenzahl
im Protokoll ausweisen.

**O-8 Spaltensatz und Extraktionsweg in Spec 1**
Der Zweispaltensatz lässt Tabellen bei einfacher Extraktion neben Fließtext laufen; ohne
Lösung verletzen Häppchen REQ-MB-14 inhaltlich, obwohl sie formal im richtigen Abschnitt liegen.
(a) Docling-Layout (Lesereihenfolge) ohne LLM-Verbalisierung für Fließtext, Tabellen roh;
(b) spaltenbewusste Text-Extraktion (pdfplumber/pypdf-Layout) ohne Docling;
(c) Spaltensatz aus Spec 1 herausnehmen, zusammen mit Zahlentreue/Werteblöcken in Spec 2.
*Empfehlung (a)* mit Messung an 10 Stichprobenseiten vorab; LLM-Verbalisierung gehört zur
Zahlentreue-Spec. Außerdem: Performance-Zahlen in REQ-MB-19 bestätigen oder ändern.

**O-9 Tier-Map fehlt im Repo**
Siehe unten. (a) `.devloop/tier-map.json` in einem eigenen kleinen Schritt vor der
Implementierung anlegen; (b) ohne Map bleiben, Tier bleibt konservativ T3.
*Empfehlung (a)* — sonst ist jede Änderung T3 und die Stufung wertlos.

## Tier

**T3 (vorläufig/advisorisch).** Abgeleitet mit
`node /Users/tmogdans/Code/devloop/dist/cli/derive-tier.js`. Im Repo gibt es **keine
Tier-Map** (`.devloop/`, `tools/`, Wurzel: nichts gefunden, Exit 2). Mit leerer Regelmenge
greift die konservative devloop-Regel „unbekannter Pfad → höchste Stufe": voraussichtlich
berührte Pfade `rag.py`, `auto_ingest.py`, `ingest.py`, `classify.py`, `openwebui_pipe.py`,
`messung/retrieval.py`, `README.md`, neues Einlese-Modul, neue Tests → **T3**. Inhaltlich passt
das: Index-Schema, Pipe-Schnittstelle und Fundstellen-Contract werden berührt. Ohne CI-Anker
gibt es keine server-seitige Neuberechnung; maßgeblich ist Tobias' Abnahme.
