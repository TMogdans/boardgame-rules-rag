# Spec: Mehr-Bücher-Bestand — Datenmodell und Einlesen

- **Spec-ID:** mehrbuch-bestand (Spec 1 von voraussichtlich 2–3)
- **Kontext-Kürzel:** MB
- **Tier:** T3 — siehe Abschnitt „Tier"
- **Status:** **Abgenommen** durch Tobias am 2026-10-21 (Fassung 3 + MB-20-Negativfall)

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
| **Inhaltsart** | Themenbereich eines Abschnitts (mindestens `regel`, `welt`); eigenes Feld, **orthogonal** zu `typ` aus `classify.py` (regel/flavor/meta bleibt Ballast-Filter für `DROP_TYPES`). |
| **Überschriften-Liste** | Deklarierte Gliederung eines Buchs: Einträge (Titel, Ebene, Seite) aus PDF-Lesezeichen oder Inhaltsverzeichnis. |
| **Layout-Überschrift** | Überschrift, die unterhalb der Liste aus Zeilenmerkmalen der Extraktion erkannt wird (REQ-MB-20). |
| **Altbestand** | Ein Bestand, dessen `spiel.json` keine Bücherliste hat (heutiges Format, ein `quelle_pdf`). |

Unberührt bleibt der Einzeldatei-Weg (`knowledge.jsonl`/`pdfs/` neben `rag.py`, ohne Index).

## Akzeptanzkriterien

### A. Datenmodell

**REQ-MB-1** — *Contract*
Ein Bestand kann in `spiel.json` eine Liste von Büchern deklarieren; jedes Buch hat
`buch_id` (Slug, im Bestand eindeutig), `titel`, `fassung`, `sprache` (aus `rag.SPRACHEN`),
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
Wenn die Deklaration doppelte `buch_id`s enthält, zwei Bücher dieselbe Quelldatei nennen
oder Häppchen eine nicht deklarierte `buch_id` tragen, dann bricht `index` für diesen
Bestand mit `KonfigFehler` ab und dessen alter Stand bleibt (wie heute bei kaputten Spielen).
*Detektor:* je Fall ein synthetischer Bestand; Index-Inhalt vorher = nachher.

### C. Einlesen-Reparatur

Die Reparatur ist eine reine Funktion auf den Textzeilen der Extraktion **vor** jedem
Whitespace-Zusammenfassen und wird je Buch eingeschaltet (für Altbestände und den rohen
PDF-Weg aus: REQ-MB-3). Reihenfolge: (1) Überschriften-Abgleich auf Zeilen (REQ-MB-12, -20),
(2) Trennungsreparatur (REQ-MB-11) im Text zwischen den Überschriften — sonst würde der
gewöhnliche Umbruch (`Wurf⏎Stufe`) Überschriftenzeilen mit dem Folgetext verschmelzen.

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
*Detektor:* Tabelle als Testfälle; Einlese-Protokoll zählt „zusammengefügte Trennungen" und
„Strich behalten" — Zähler auf einer definierten Eingabe mit bekannter Anzahl je Fall exakt.

**REQ-MB-12** — *Where, Überschriften-Liste und unscharfer Abgleich*
Wo ein Buch eine Überschriften-Liste deklariert, gilt sie als Wahrheit für die Ebenen, die sie
kennt. Der Mechanismus nimmt allgemein eine Liste (Titel, Ebene, Seite); Lieferanten sind
mindestens **PDF-Lesezeichen** und eine **Inhaltsverzeichnis-Liste** (Titel, Ebene, gedruckte
Seite, umgerechnet nach REQ-MB-22). Für jeden Eintrag wird auf seiner **Zielseite (± 0)** die
passende Zeile gesucht und durch den Listentitel ersetzt; sie beginnt den Abschnitt.

*Abgleichregel:* `norm(s)` = Unicode-NFC, alle Leerraumzeichen entfernen, `casefold`.
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
„mehrdeutig = 1".

**REQ-MB-13** — *If/Then*
Wenn ein Listeneintrag auf seiner Zielseite nicht gefunden wird, dann beginnt sein Abschnitt
am Anfang der Zielseite, und der Eintrag erscheint im Einlese-Protokoll mit Titel und Seite
(Zähler gefunden/nicht gefunden/mehrdeutig). Kein Eintrag verschwindet still.
*Detektor:* Liste mit einem Eintrag ohne Gegenstück → Abschnitt vorhanden, Protokoll nennt ihn.

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
REQ-MB-4/-5): **typisch ≤ 15 ms, Maximum ≤ 45 ms** je Frage über 200 Fragen; Altbestände nicht
langsamer als heute (README: 2.000 Häppchen typisch 9,1 ms, max 13,5).
*Detektor:* Messskript mit typisch und Maximum, wie die README-Messung.

### F. Ergänzungen (Entwurf 2)

**REQ-MB-20** — *Where, Layout-Überschriften unterhalb der Liste*
Wo ein Buch Layout-Merkmale für Überschriften deklariert (allgemeiner Mechanismus; Merkmale je
Buch konfigurierbar, z. B. Schriftgröße von–bis, Schnitt fett, eigene Zeile, Höchstlänge,
Layout-Klasse der Extraktion), gilt eine Zeile als Layout-Überschrift genau dann, wenn sie
**alle** deklarierten Merkmale erfüllt und nicht schon einem Listeneintrag zugeordnet ist
(REQ-MB-12). Sie erhält die Ebene ihres umschließenden Listenabschnitts + 1, verfeinert dessen
Abschnittspfad und beginnt einen Unterabschnitt bis zur nächsten Layout- oder Listenüberschrift.
Layout-Überschriften werden **nicht** gegen die Liste abgeglichen oder ersetzt und erzeugen
keine Ebenen oberhalb der Liste. Das Protokoll zählt erkannte Layout-Überschriften je
Listenabschnitt.
Merkmalsquelle ist zunächst **nur die Layout-Klasse der Docling-Extraktion**. Schriftinformation
(Größe, Schnitt) aus pdfplumber, je Zeile zugeordnet, kommt nur hinzu, wenn H aus REQ-MB-23 sein
Ziel verfehlt — dann wird mit Tobias entschieden. Das Kriterium bleibt gleich, nur die
Merkmalsquelle wechselt.
Anlass (gemessen): im Zielbuch ist „Talentbeschreibungen" **ein** Lesezeichen für S. 76–107;
die Talentnamen stehen nur im Text.
*Detektor:* synthetisches Buch, Liste auf 2 Ebenen (`K1 › U1`), darin Zeilen `Alpha`, `Beta`
mit den Merkmalen und je Text → Pfade `K1 › U1 › Alpha` bzw. `… › Beta`, jedes Häppchen eines
Unterabschnitts beginnt mit dessen Namen (REQ-MB-15). Negativfall: eine kurze Fließtextzeile
`Gamma` ohne die Merkmale (eigene Zeile, aber andere Layout-Klasse; kommt später pdfplumber-Schriftinfo hinzu, wird der Negativfall um die Schriftgröße erweitert) bleibt Fließtext in `Beta`.
Protokoll: `U1` = 2. Ohne deklarierte Merkmale: Pfade nur aus der Liste (Wirkung von
REQ-MB-12 unverändert).

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
- **H** = auf den Talentseiten erkannte / vorhandene Talentnamen und Fehltreffer, mit
  Merkmalen nach REQ-MB-20 allein aus der Docling-Layout-Klasse — Ziel alle erkannt,
  0 Fehltreffer.

Verfehlt eine Zahl ihr Ziel, wird **vor** dem Weiterbauen mit Tobias über den Weg entschieden
(spaltenbewusste Extraktion ohne Docling oder Spaltensatz in Spec 2; bei H zuerst
Schriftinformation aus pdfplumber, REQ-MB-20).
Messung und spätere Ingestion laufen mit **derselben Docling-Version**; sie wird im
Messergebnis notiert, und die Messung gilt nur für diese Version (`requirements-ingest.txt`
ist heute ungepinnt).
*Detektor:* Messergebnis mit Seitenliste, L/T/H und Docling-Version liegt im Spec-Ordner (nur
Zahlen, REQ-MB-18), bevor ein Commit Abschnitt C/D implementiert.

## Abgrenzung (nicht in Spec 1)

- Hausregeln als Markdown (Art neu/ergänzt/ersetzt, Bezug, feste Mitlieferung) — eigene Spec.
- Zahlentreue: Schablonen-Serialisierung für Werteblöcke, Zahlenprüfung nach LLM-Verbalisierung.
- OCR-Vertauschungen im Überschriften-Abgleich (Fehlerklasse 3, REQ-MB-12).
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
- **N-2 (a)** gekennzeichnete Fassungen im Ranking gleich behandelt — eine Rangregel ändert die Messung und ist erst mit einem Earthdawn-Golden-Set bewertbar (MB-5).

## Tier

**T3**, ohne Tier-Map (Entscheidung O-9 b). `derive-tier.js` findet keine Map (Exit 2), die
devloop-Regel „unbekannter Pfad → höchste Stufe" greift; inhaltlich passend (Index-Schema,
Pipe-Schnittstelle, Fundstellen-Contract). Ohne CI-Anker keine server-seitige Neuberechnung;
maßgeblich ist Tobias' Abnahme jedes Merges.
