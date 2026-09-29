# Boardgame RAG Lab

Ein minimaler, lokaler RAG-Pruefstand fuer Brettspiel-Regelfragen -- Begleitcode zur
Mayflower-Blogserie ueber lokales Retrieval-Augmented-Generation auf eigener Hardware.

Kein Framework, keine Cloud: PDF einlesen, in Haeppchen schneiden, per Embedding
durchsuchbar machen, optional mit einem Reranker nachscharfstellen und von einem
lokalen LLM (via Ollama) beantworten lassen. Gedacht zum **Verstehen und Messen**,
nicht als Produktivsystem.

> **Urheberrecht:** In diesem Repo sind **keine Regelhefte** enthalten. Lege dein
> eigenes PDF nach `pdfs/` (per `.gitignore` ausgeschlossen).

## Schnellstart

```bash
git clone git@github.com:TMogdans/boardgame-rag-lab.git
cd boardgame-rag-lab

# 1. Ollama + Modelle bereitstellen (Details unter "Voraussetzungen")
# 2. Serving-venv einrichten
python3 -m venv .venv && . .venv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cpu torch   # CPU reicht; KEIN torchvision
pip install -r requirements-serve.txt

# 3. eigenes Regel-PDF ablegen und die erste Frage stellen
cp ~/mein-spiel.pdf pdfs/
python rag.py ask "Wie verdiene ich Geld?"
```

Das ist der schnellste Weg zur ersten Antwort (rohe PDF-Extraktion, ein Modell,
eine venv). Bessere Ingestion fuer Tabellen und Grafiken sowie die zweite venv
sind weiter unten beschrieben.

## Was drin ist

| Datei | Zweck |
|---|---|
| `rag.py` | Retrieval + optionaler Reranker + Golden-Set-Eval. Alle Stellschrauben per Umgebungsvariable. |
| `ingest.py` | Bessere Ingestion fuer Text/Tabellen: Docling (Layout) + faktentreue LLM-Verbalisierung -> `knowledge.jsonl`. |
| `render.py` | Rendert PDF-Seiten als PNG (Vorstufe fuer Vision). |
| `vision_test.py` | Schickt ein Bild + Frage an ein lokales Vision-Modell (schneller Check). |
| `vision_ingest.py` | Verbalisiert eine Grafik-/Infografik-Seite per Vision und haengt jede Karte als Chunk an `knowledge.jsonl`. |
| `auto_ingest.py` | **Auto-Router:** entscheidet pro Seite selbst zwischen Text/Tabelle/Vision (Docling-Layout + Fragment-Heuristik) -> `knowledge.jsonl`. |
| `classify.py` | Taggt jeden Chunk als `regel`/`flavor`/`meta`, damit sich Ballast beim Retrieval ausfiltern laesst. |
| `inspect_layout.py` | Zeigt die Docling-Region-Labels pro Seite (zum Debuggen und Verstehen des Routings). |
| `openwebui_pipe.py` | Open-WebUI-Pipe: dieselbe Retrieval-Logik als Modell in der Chat-Oberflaeche (siehe "Open WebUI"). |
| `install_openwebui_pipe.py` | Laedt die Pipe per API in Open WebUI (anlegen oder aktualisieren). |
| `golden_set.example.json` | Beispiel-Testset (Food Chain Magnate). Kopiere es nach `golden_set.json` und passe es an dein Spiel an. |

## Voraussetzungen

- [Ollama](https://ollama.com/) laeuft lokal, mit den Modellen:
  ```
  ollama pull qwen3:14b     # Antwortmodell
  ollama pull bge-m3        # Embeddings (multilingual/deutsch)
  ollama pull qwen2.5vl:7b  # Vision (fuer Grafik-/Infografik-Seiten)
  ```
  Ollama selbst startet je nach Plattform unterschiedlich. Auf einer AMD-GPU unter
  Linux laeuft es z.B. als ROCm-Container:
  ```bash
  podman run -d --device /dev/kfd --device /dev/dri \
    -v ollama:/root/.ollama -p 127.0.0.1:11434:11434 \
    --name ollama docker.io/ollama/ollama:rocm
  ```
- Python 3.11+.

## Einrichtung -- zwei getrennte venvs

Das ist kein Zufall: Docling und sentence-transformers stellen widerspruechliche
Ansprueche an `transformers`. In einer gemeinsamen venv bricht eines von beiden.
Also trennen (was fuer eine spaetere Microservice-Architektur ohnehin passt).

```bash
# venv 1: Serving / Retrieval / Vision
python3 -m venv .venv
. .venv/bin/activate
pip install --index-url https://download.pytorch.org/whl/cpu torch   # CPU reicht; KEIN torchvision
pip install -r requirements-serve.txt
deactivate

# venv 2: Ingestion (Docling)
python3 -m venv .venv-ingest
. .venv-ingest/bin/activate
pip install -r requirements-ingest.txt
deactivate
```

## Nutzung

```bash
# PDF in den Ordner legen
cp ~/mein-spiel.pdf pdfs/

# Eine Frage (einfache Ingestion: rohe PDF-Extraktion)
. .venv/bin/activate
python rag.py ask "Wie verdiene ich Geld?"

# Testset durchlaufen
cp golden_set.example.json golden_set.json   # dann an dein Spiel anpassen
python rag.py eval

# Mehrere Spiele: Golden Set je Spiel unter data/<spiel_id>/golden_set.json
# (Format wie golden_set.example.json, Feld "spiel_id" = Verzeichnisname)
DROP_TYPES=flavor,meta CHUNK_SIZE=400 python rag.py eval food-chain-magnate   # SOURCE entfaellt: Quelle ist der Index
python rag.py eval --alle    # alle Spiele mit Golden Set, plus Gesamtblock; nennt die ohne
```

`rag.py eval <spiel_id>` bringt den Index fuer dieses Spiel vorher auf Stand und wertet
mit derselben Logik wie der Einzeldatei-Weg (Dreiteilung, Keyword-Wortgrenzen,
Verweigerungsfragen). Mit `--alle` kommt ein Gesamtblock dazu; Spiele ohne Golden Set
werden ausdruecklich genannt statt still ausgelassen.

### Stellschrauben (alles per env)

```bash
CHUNK_SIZE=400 python rag.py eval         # Haeppchengroesse (Zeichen), Default 800
CHUNK_OVERLAP=150 python rag.py eval      # Ueberlappung, Default 150 -- siehe Warnung unten
TOP_K=8 python rag.py eval                # wie viele Haeppchen in den Kontext, Default 4
RERANK=1 python rag.py eval               # Reranker an (over-retrieve -> Cross-Encoder)
CANDIDATES=40 RERANK=1 python rag.py eval # Kandidatenfeld vor dem Reranking, Default 20
SOURCE=knowledge python rag.py eval       # knowledge.jsonl statt roher PDF-Extraktion
DROP_TYPES=flavor,meta python rag.py eval # Ballast aus dem Index werfen (nur mit SOURCE=knowledge)
THINK=1 python rag.py eval                # Reasoning des LLM anschalten
HYBRID=1 python rag.py eval food-chain-magnate  # Vektor + BM25 (FTS5) per Reciprocal Rank Fusion, nur mit Index
RRF_K=60                                  # Daempfung der Rangfusion, Default 60
```

`FRAGMENT_THRESHOLD=50` (in `auto_ingest.py`) entscheidet, ab wie vielen Text-Fragmenten
eine Seite als Grafik gilt und zur Vision-Route geht.

> **`CHUNK_OVERLAP` skaliert nicht mit `CHUNK_SIZE`.** Die Ueberlappung ist absolut, nicht
> relativ. Wer `CHUNK_SIZE` von 800 auf 400 halbiert, aendert damit **vier** Dinge auf
> einmal: Haeppchengroesse, relative Ueberlappung (18,8 % -> 37,5 %), Anzahl der Chunks
> im Index und -- bei festem `TOP_K` -- die Menge Kontext, die beim Modell ankommt
> (4 x 800 -> 4 x 400 Zeichen). Ein Ergebnisunterschied laesst sich deshalb **nicht**
> allein der Haeppchengroesse zuschreiben. Wer die Groesse isoliert messen will, muss
> `CHUNK_OVERLAP` mitskalieren und `TOP_K` gegenrechnen.

> **Ergebniszahlen aus frueheren Laeufen sind nicht mehr vergleichbar.** Die Wertung in
> `rag.py eval` wurde repariert (siehe "Was die Eval misst"): fruehere Quoten hatten einen
> Nenner, den die Lauf-Konfiguration mitverschieben konnte. Alle Vergleiche muessen mit
> diesem Stand neu erhoben werden.

Gemessen mit dem reparierten Stand, deutsches FCM-Regelheft (15 Seiten), Golden Set mit
10 Fragen, `auto_ingest.py` + `classify.py`, `CHUNK_SIZE=400`, `top_k=4`, qwen3:14b:

| Konfiguration | Index | getroffen | Precision@4 | MRR |
|---|---|---|---|---|
| ohne Reranker, ohne `DROP_TYPES` | 286 Chunks | 7/8 | **0,562** | **0,792** |
| ohne Reranker, `DROP_TYPES=flavor,meta` | 256 Chunks | 7/8 | 0,562 | 0,792 |
| mit Reranker, ohne `DROP_TYPES` | 286 Chunks | 7/8 | 0,531 | 0,729 |
| mit Reranker, `DROP_TYPES=flavor,meta` | 256 Chunks | 7/8 | 0,531 | 0,729 |

Zwei Dinge, die dabei herauskommen und die vorherige Aussage "beste Kombination
`CHUNK_SIZE=400 RERANK=1`" nicht stuetzen:

1. **Der Typ-Filter aendert nichts.** Er entfernt 30 Chunks aus dem Index -- und keine
   einzige Wertung, auch nicht Precision oder MRR. Die 30 Chunks kamen nie in die top_4.
   Frueher sah das nach einer Verbesserung aus, weil der Filter den *Nenner* senkte.
2. **Der Reranker verschlechtert hier leicht** (Precision@4 0,562 -> 0,531, MRR 0,792 ->
   0,729). Er veraendert die Reihenfolge sichtbar, aber nicht zum Besseren. Bei zehn Fragen
   ist das kein Urteil ueber Cross-Encoder, sondern ueber diesen Aufbau.

Und ein Hinweis auf die Grenze der Messlatte selbst: "erwartete Seite unter top_k" ist
binaer und hat in allen vier Konfigurationen 7/8 gemeldet. Erst Precision@4 und MRR zeigen
ueberhaupt einen Unterschied. Wer nur die Quote ansieht, sieht keine Stellschraube wirken.

### Mehrere Spiele: persistenter Index

Fuer die Spiele unter `data/` gibt es einen Index in einer SQLite-Datei
(`data/index.sqlite`, per `INDEX_PATH` verlegbar). Vektoren liegen dort als float32-BLOB,
Volltext (BM25) in einer FTS5-Tabelle. Eingebettet wird nur, was sich geaendert hat:
Der Fingerprint je Spiel ist SHA-256 der `knowledge.jsonl` plus `EMBED_MODEL`,
`CHUNK_SIZE`, `CHUNK_OVERLAP` und eine Schema-Version. Jede Konfiguration ist ein eigener
Stand -- ein Lauf mit `CHUNK_SIZE=800` ersetzt nicht den 400er-Stand der Pipe.
`DROP_TYPES` wirkt beim Laden und braucht kein neues Embedding.

```bash
CHUNK_SIZE=400 python rag.py index --alle            # alle Spiele unter data/, entfernt verschwundene
CHUNK_SIZE=400 python rag.py index brass-birmingham  # nur dieses Spiel
```

**Umstieg von der Einzeldatei** (einmalig, die alte Datei bleibt liegen und der alte Weg
funktioniert weiter):

```bash
python rag.py migriere --spiel "Food Chain Magnate" --aliase "Food Chain,FCM" --sprache de \
    --pdf FCM_Rules_DE_v3.pdf            # knowledge.jsonl + golden_set.json -> data/food-chain-magnate/
CHUNK_SIZE=400 python rag.py index food-chain-magnate
SOURCE=knowledge DROP_TYPES=flavor,meta CHUNK_SIZE=400 python rag.py vergleiche food-chain-magnate
```

`migriere` uebernimmt jeden Eintrag unveraendert und in derselben Reihenfolge, ergaenzt nur
`spiel`/`spiel_id` und ueberschreibt nie eine abweichende Datei im Spielverzeichnis.
`vergleiche` rechnet fuer jede Frage des Golden Sets die Top-k ueber den alten In-Memory-Weg
und ueber den Index -- mit echten Embeddings, ohne LLM -- und endet mit Exit-Code 1 bei
jeder Abweichung. Das ist der Test, den `test_regression.py` modellfrei nicht leisten kann:
ob Ollama batch-unabhaengig einbettet (der Index bettet in Stuecken von `EMBED_BATCH`,
Default 64, und inklusive `flavor`/`meta` ein, der alte Weg alles in einem Aufruf).
Eine leere oder nach `DROP_TYPES` leere Quelle, ein kaputter Symlink oder zu wenige
Embeddings von Ollama brechen mit Klartext ab (Pfad samt aufgeloestem Symlink und Zaehlern).

**Gleichstand:** Beide Wege ranken in `rag.rangfolge` stabil -- bei exakt gleichem Score
kommt die niedrigere Chunk-Position zuerst, auch fuer Reranker-Kandidaten und die
Hybrid-Vektorliste. ed36f99 sortierte mit `np.argsort` (quicksort, nicht stabil); dort
hing die Reihenfolge gleichauf liegender Chunks und an der top_k-Grenze die Auswahl von
der Plattform ab (Linux/x86_64 und macOS/arm64 lieferten in 487 von 1008 Testfaellen
andere, gleich bewertete Chunks). "Zahlengleich zu ed36f99" heisst deshalb: gleich bis auf
die Reihenfolge innerhalb exakter Gleichstaende, die dort nicht definiert war.

**Suche pro Spiel:** `retrieve(frage, spiel_id=...)` laedt nur die Zeilen dieses Spiels
und rankt dann -- der Filter wirkt vor dem Ranking, ein fremdes Spiel kann keine Treffer
verdraengen. `python rag.py ask --spiel food-chain-magnate "Wie verdiene ich Geld?"`
(`--spiel` und die Spielangaben von `eval`/`index`/`vergleiche` nehmen spiel_id, Name,
Alias oder Hoerfehler -- dieselbe Zuordnung wie die Pipe)
bringt den Index vorher auf Stand. `HYBRID=1` fusioniert die Vektor-Rangfolge mit BM25
(beide auf `CANDIDATES` begrenzt, mit `RERANK=1` danach Cross-Encoder); Default ist aus,
damit der Standardweg unveraendert bleibt. Der Spielfilter steht im MATCH-Ausdruck (ein
Token je Spiel und Stand), nicht als `rowid IN (...)` -- das wuchs gemessen mit
(Treffer gesamt) x (Chunks des Spiels) in den Sekundenbereich. Die IDF-Gewichte von FTS5
sind tabellenweit (alle Spiele und Staende) -- sie gewichten Woerter, waehlen aber keine
fremden Chunks aus.

Gemessen mit dem Indexcode bei 250 Spielen (ein Spiel mit 2000 Chunks, 1024 Dimensionen,
Embedding gefakt): Indexbau ohne Embedding 1,9 s, Lauf ohne Aenderung 0,16 s; ein Spiel
laden typisch 0,8 ms (181 Chunks) bzw. 9,1 ms (2000 Chunks, max 13,5); Vektorsuche in
2000 Chunks typisch 0,33 ms (max 0,64), hybrid 7,1 ms (max 7,6); BM25 allein bei 47.691
Zeilen typisch 3,4 ms (max 7,1). Platz: 4,6 KB je Zeile (4 KB Vektor + Text), bei 47k
Zeilen also rund 220 MB plus FTS.

**Warum kein sqlite-vec**, obwohl es auf der Zielmaschine laedt (Wheel 0.1.9 fuer
Python 3.14/manylinux, `enable_load_extension` vorhanden): Gesucht wird immer innerhalb
eines Spiels, also ueber hunderte bis wenige tausend Vektoren. Gemessen bei 47k x 1024
Vektoren in 250 Spielen (k=4, 200 Fragen): pro Spiel numpy typisch 0,07 ms (max 0,12),
sqlite-vec 0,29 ms (max 0,37). Entscheidend ist aber die Reihenfolge bei Gleichstand:
Bei identischen Vektoren liefert `vec0` die umgekehrte rowid-Folge wie `np.argsort`
(`[6,4,3,1]` statt `[1,3,4,6]`). An der top_k-Grenze aendert das, *welche* Chunks
zurueckkommen, und der bisherige Weg waere fuer FCM nicht mehr zahlengleich. Dazu kaeme
eine Abhaengigkeit mehr im Open-WebUI-Container. Das BLOB-Format ist das `vec_f32` von
sqlite-vec; ein spaeterer Wechsel kostet eine Abfrage, kein Neu-Embedden.

### Was die Eval misst -- und was nicht

`python rag.py eval` erhebt **zwei** Dinge, und beide sind Regressionswarner, kein
Korrektheitsmass:

1. **Retrieval-Dreiteilung** `getroffen / verfehlt`, plus `Verweigerungsfragen` als eigene
   Kategorie. Ob eine Frage in die Retrieval-Wertung eingeht, haengt allein an der Frage
   selbst (Feld `erwartet_verweigerung` im Golden Set), **nie** an der Konfiguration des
   Laufs. Der Nenner ist damit ueber alle `DROP_TYPES`-Varianten konstant -- eine
   Verbesserung kann nicht mehr dadurch entstehen, dass Fragen aus der Wertung fallen.
2. **Keyword-Treffer** in der Antwort, auf Wortgrenzen. Das ist ein grober
   Aenderungsdetektor: das Skript kennt **keine** Kategorie "falsch" und kann
   "keine einzige falsche Antwort" nicht ermitteln. Wer eine Korrektheitsaussage braucht,
   liest die Antworten selbst gegen das Heft.

Das Golden Set kennzeichnet Verweigerungsfragen ausdruecklich:

```json
{ "frage": "Gibt es die Spielregel 'Gleicher Mist, doppelter Preis'?",
  "typ": "flavor", "erwartet_verweigerung": true, "seiten": [2] }
```

`typ` ist eine inhaltliche Kategorie und **keine** Wertungsanweisung -- eine Frage ohne
`seiten` und ohne `erwartet_verweigerung` ist ein Konfigurationsfehler und bricht ab.

**Die Eval bricht ab statt stillschweigend etwas anderes zu messen**, wenn:

- `DROP_TYPES` einen Wert nennt, den `classify.py` nicht vergibt (`regel`/`flavor`/`meta`) --
  insbesondere bei Verwechslung mit den Frage-Typen des Golden Sets (`fakt`, `falle`,
  `leerstelle`, `tabelle`);
- `DROP_TYPES` ohne `SOURCE=knowledge` gesetzt ist (der Filter koennte dort nicht wirken);
- `DROP_TYPES` gesetzt ist, aber kein Chunk ein `typ`-Feld hat (`classify.py` fehlt);
- ein `knowledge.jsonl`-Eintrag kein Feld `seite` hat (fruehere Faelle lieferten die
  Chunk-ID als Seitenzahl aus -- eine erfundene Fundstelle ist schlimmer als ein Abbruch);
- `CHUNK_SIZE <= CHUNK_OVERLAP` (waere eine Endlosschleife).

> **Alte `knowledge.jsonl` neu erzeugen.** Dateien, die vor diesem Stand geschrieben wurden,
> haben kein `seite`-Feld und fuehren zum Abbruch. Die Ingestion muss einmal neu laufen --
> es genuegt nicht, nur `rag.py` zu aktualisieren.

### Tests

Die Auswertungslogik ist ohne Ollama, ohne Modelle und ohne PDF pruefbar:

```bash
python test_wertung.py       # Dreiteilung, DROP_TYPES-Entkopplung, Keywords, Guards
python test_classify.py      # Klassifikator-Auswertung, 17 Antwortvarianten
python test_ingest_seite.py  # 'seite'-Feld in ingest.py und vision_ingest.py
python test_spiele.py        # Mehr-Spiele-Layout: Ingestion schreibt nur ins eigene Spielverzeichnis
python test_index.py         # persistenter Index: Fingerprint, Neu-Embedding nur bei Aenderung
python test_suche.py         # Suche pro Spiel (Filter vor dem Ranking) und HYBRID
python test_eval_spiele.py   # Eval pro Spiel und --alle
python test_pipe_index.py    # Pipe auf dem Index-Weg: Zuordnung gegen alle Spiele, Veraltet-Pruefung
python test_zuordnung.py     # strenge Spielzuordnung, --spiel mit Name oder id
python test_chat.py          # Spiel im Chat: exakte Nennung, Wechsel nur explizit
python test_schutz.py        # kein Test-/Mutationslauf schreibt in echte Daten (auch nicht per Symlink)
python test_regression.py    # alter UND neuer Weg == Ausgabe von ed36f99 (regression_referenz.json),
                             # gleichstandsbewusst verglichen -> auf jeder Plattform gueltig
# Referenz neu erzeugen (braucht git), oder eine plattformeigene gegenpruefen:
# python regression_referenz.py --erzeuge [--ziel /tmp/ref.json] [--gleichstand-umgekehrt]
# REGRESSION_REFERENZ=/tmp/ref.json python test_regression.py
python test_mutationen.py    # Mutationsprobe: verfaelscht die Fixes und prueft, dass Tests rot werden
NUR=F,S python test_mutationen.py  # nur die Mutationen mit diesen Praefixen
python test_openwebui_pipe.py  # Pipe: gleiche Chunks, gleicher Prompt wie die CLI (braucht pydantic + httpx)
# test_mutationen.py faehrt auch die Pipe-Mutationen (P1-P26)
```

### Ingestion nach Inhaltstyp

Es gibt keine eine beste Methode -- es haengt davon ab, was auf der Seite steht.

**Mehrere Spiele:** Jedes Spiel bekommt ein eigenes Verzeichnis `data/<spiel_id>/`
(gitignored) mit `knowledge.jsonl`, `spiel.json` (Name, Aliase, Sprache, Quell-PDF) und
optional `golden_set.json`. Alle Ingestion-Skripte nehmen dafuer dieselben Optionen und
schreiben nur in das Verzeichnis dieses einen Spiels; jeder Chunk traegt `spiel` und
`spiel_id`. Die `spiel_id` ist ein Slug aus dem Namen ("Brass: Birmingham" ->
`brass-birmingham`), `--sprache` (de/en) ist die Sprache des Hefts und steuert die
Verbalisierung; der Vision-Prompt nennt das Spiel beim Namen.

```bash
python auto_ingest.py pdfs/brass.pdf --spiel "Brass: Birmingham" --sprache en --aliase "Brass"
python vision_ingest.py seite_6.png --spiel-id brass-birmingham   # Spiel existiert schon
python classify.py brass-birmingham
```

Ohne `--spiel` bleibt es beim alten Ein-Spiel-Weg (`knowledge.jsonl` neben den Skripten).
`auto_ingest.py` und `ingest.py` verweigern dort aber das Ueberschreiben einer vorhandenen
Datei -- frueher hat genau das ein Heft durch das naechste ersetzt. `vision_ingest.py`
ersetzt nur noch die Chunks desselben Bildes (vorher fiel jede fruehere Grafikseite weg).
Auch mit `--spiel` ersetzen `auto_ingest.py`/`ingest.py` eine vorhandene
`data/<spiel_id>/knowledge.jsonl` nur mit `--ueberschreiben` (dort stecken ggf. Vision-Chunks
und Typ-Tags). Die `spiel_id` transliteriert ("Café Łódź" -> `cafe-lodz`); ergeben zwei
verschiedene Namen dieselbe id, bricht das Anlegen ab -- dann `--spiel-id` selbst waehlen.

Beispiele unten zeigen den Ein-Spiel-Weg; mit `--spiel`/`--spiel-id` gilt dasselbe pro Spiel.

**Alles automatisch** (Auto-Router -- der bequemste Weg): entscheidet pro Seite selbst,
welcher der folgenden Wege genommen wird.

```bash
. .venv-ingest/bin/activate
python auto_ingest.py pdfs/mein-spiel.pdf   # routet jede Seite selbst -> knowledge.jsonl
deactivate

. .venv/bin/activate
python classify.py                          # optional: Ballast als flavor/meta taggen
                                            # schreibt die rohe Modellantwort als 'typ_antwort' mit,
                                            # damit eine Fehl-Einordnung nachvollziehbar bleibt
SOURCE=knowledge CHUNK_SIZE=400 RERANK=1 DROP_TYPES=flavor,meta python rag.py eval
```

Wer die einzelnen Wege lieber von Hand steuert:

**Text & echte Tabellen** (Docling + Verbalisierung):

```bash
. .venv-ingest/bin/activate
python ingest.py pdfs/mein-spiel.pdf     # erzeugt knowledge.jsonl
deactivate

. .venv/bin/activate
SOURCE=knowledge CHUNK_SIZE=400 RERANK=1 python rag.py eval
```

**Grafiken & Infografiken** (Vision) -- das, woran reine Textextraktion scheitert:

```bash
. .venv/bin/activate
python render.py pdfs/mein-spiel.pdf 6                    # Grafikseite -> seite_6.png
python vision_test.py seite_6.png "Was steht auf Karte X?" # schneller Check
python vision_ingest.py seite_6.png                       # jede Karte als Chunk -> knowledge.jsonl
                                                          # Seite kommt aus dem Dateinamen (seite_N.png);
                                                          # bei anderem Namen: SEITE=6 davorsetzen
SOURCE=knowledge CHUNK_SIZE=400 RERANK=1 python rag.py eval
```

## Open WebUI

`openwebui_pipe.py` macht die Pipeline in Open WebUI als eigenes Modell waehlbar
("Brettspiel-Regeln (RAG)"). Die Pipe enthaelt keine eigene Retrieval-Logik: sie
laedt `rag.py` zur Laufzeit aus einem gemounteten Clone und baut den Prompt ueber
`rag.baue_nachrichten` -- dieselbe Funktion, die `rag.py ask`/`eval` benutzen.
Mit denselben Werten fuer `CHUNK_SIZE`, `CHUNK_OVERLAP`, `DROP_TYPES` und `TOP_K` misst
`rag.py eval` also das, was im Chat antwortet. Ein `git pull` im Clone wirkt ohne
Neustart (die Pipe laedt `rag.py` neu, wenn sich die Datei aendert).

Unterschiede zur CLI, bewusst:

- nur `SOURCE=knowledge` (die Pipe liest `knowledge.jsonl`, keinen PDF-Ordner)
- kein Reranker (der braucht torch, das im Open-WebUI-Image fehlt)
- Rueckfragen im Chat: Retrieval laeuft auf der letzten Frage, der Verlauf geht ohne alte Quellen mit
- Open-WebUI-Hilfsaufgaben (Titel, Tags) gehen ohne Retrieval direkt ans Modell
- ein Systemprompt aus Modell- oder Nutzereinstellungen wird verworfen; es gilt allein der aus `rag.py`
- Fehler (z.B. `KonfigFehler`) erscheinen als Text im Chat, statt im Log zu verschwinden
- Chunking kommt aus den Valves, nie aus der Container-Umgebung -- Open WebUI benutzt
  `CHUNK_SIZE`/`CHUNK_OVERLAP` fuer seine eigene Dokumentsuche

**Einrichtung** (Podman-Quadlet, Pfade anpassen; `z` wegen SELinux):

```ini
# ~/.config/containers/systemd/open-webui.container, Abschnitt [Container]
Volume=/var/home/USER/boardgame-rag-lab:/rag/code:ro,z
Volume=/var/home/USER/rag-lab/knowledge.jsonl:/rag/data/knowledge.jsonl:ro,z
```

```bash
systemctl --user daemon-reload && systemctl --user restart open-webui.service
OPENWEBUI_URL=http://localhost:8080 OPENWEBUI_KEY=sk-... python install_openwebui_pipe.py
```

**Aufruf von aussen (z.B. Home Assistant):** ueber Open WebUIs OpenAI-kompatible API
(`POST /api/chat/completions`, `model: brettspiel_rag`) mit einem optionalen Feld:

```json
{"model": "brettspiel_rag", "stream": false,
 "messages": [{"role": "user", "content": "Welche Reichweite hat der Truck Driver?"}],
 "regelfrage": {"spiel": "Food Chain Magnate", "sprache": true}}
```

- `spiel` wird unscharf gegen die Valves `SPIEL`/`SPIEL_ALIASE` zugeordnet (Gross/Klein,
  Satzzeichen, Hoerfehler wie "Food Chain Magnet"). Ohne Treffer antwortet die Pipe
  "Zu „…“ habe ich kein Regelheft", ggf. mit Vorschlag -- ohne Suche und ohne LLM-Aufruf.
- `sprache: true` laesst nur die Fundstellen-Fusszeile weg. Der Prompt bleibt derselbe wie
  bei der CLI, damit das Golden Set weiter misst, was gesprochen wird.
- Ohne das Feld (Chat in Open WebUI) aendert sich nichts.

Die Stellschrauben (`CHUNK_SIZE`, `CHUNK_OVERLAP`, `TOP_K`, `DROP_TYPES`, `LLM_MODEL`,
`EMBED_MODEL`, `THINK`, Pfade, `OLLAMA_URL` aus Sicht des Containers) stehen als *Valves*
unter Admin → Funktionen. Die Defaults sind die oben gemessene Konfiguration:
`CHUNK_SIZE=400`, `CHUNK_OVERLAP=150`, `TOP_K=4`, `DROP_TYPES=flavor,meta`. Der passende
Vergleichslauf gegen dieselbe Datei, die der Container gemountet bekommt -- per Pfad,
**nicht per Symlink** neben `rag.py`:

```bash
KNOWLEDGE_JSONL=~/rag-lab/knowledge.jsonl GOLDEN_SET=~/rag-lab/golden_set.json \
  SOURCE=knowledge CHUNK_SIZE=400 DROP_TYPES=flavor,meta python rag.py eval
```

> **Keine Symlinks auf Live-Daten neben den Code legen.** Frueher stand hier
> `ln -s ~/rag-lab/knowledge.jsonl .`. Ein Testlauf (Mutationstreiber) hat darueber die
> Live-Wissensbasis der Pipe ueberschrieben: 79 Eintraege `flavor`, 8 Minuten keine
> Chunks. Seitdem schreibt kein Skript mehr durch einen Symlink (Abbruch mit Hinweis),
> alle Tests biegen ihre Pfade ueber `testumgebung.py` in ein Temp-Verzeichnis, und
> `test_mutationen.py` mutiert nur in einer Temp-Kopie. `test_schutz.py` prueft das.

**Viele Spiele (Index-Weg):** Valve `INDEX_PATH` setzen (z.B. `/rag/data/index.sqlite`)
und statt der Einzeldatei das ganze `data/` read-only mounten:

```ini
Volume=/var/home/USER/rag-lab/data:/rag/data:ro,z
```

Den Index baut der Host (`rag.py index --alle`) mit **denselben** `CHUNK_SIZE`,
`CHUNK_OVERLAP` und `EMBED_MODEL` wie in den Valves; die Pipe liest nur und bettet nur
noch die Frage ein. Dann gilt:

- `regelfrage.spiel` wird gegen Name, Aliase (aus `spiel.json`) und `spiel_id` **aller**
  Spiele im Index zugeordnet; `SPIEL`/`SPIEL_ALIASE` gelten nicht mehr. Unbekannt ->
  "kein Regelheft" wie bisher, ohne Suche und ohne LLM. Mehrdeutig (gemeinsamer Alias,
  zwei unscharfe Treffer fast gleichauf) -> ebenfalls kein Treffer, mit Vorschlaegen.
  Bei mehr als einem Spiel trifft unscharf nur, was ungefaehr gleich lang ist
  (Laengenverhaeltnis >= 0,8): sonst wird ein kurzer Name zum Auffangbecken ("Fujian" traf
  "Fuji" genau auf der Schwelle). Vorgeschlagen wird dann nur ab Ratio 0,6 und Laenge 0,7
  (Fujian/Fuji: 0,67 -> kein Vorschlag; Foodsharing Magnet -> Food Chain Magnate bleibt).
  Mit genau einem Spiel gilt das Verhalten von ed36f99 ("Food Chain Magnate Regeln" trifft).
  Dieselbe Zuordnung (`rag.ordne_spiel`) gilt fuer `--spiel` auf der Kommandozeile.
- Ohne `regelfrage.spiel` (Chat) gilt `rag.spiel_im_chat`:
  - Das Spiel des Chats ist das erste, das in einer Nutzer-Nachricht **exakt** genannt wird
    (Name oder Alias als ganze Wortfolge; Gross/Klein, ae/ä, ss/ß, Satzzeichen, Bindestriche
    egal; "Go-Phase" ist ein Wort). Keine Unschaerfe im Chat. Enthaelt ein Treffer einen
    anderen, gilt der laengere ("7 Wonders Duel" vor "7 Wonders"); zwei unabhaengige ->
    Rueckfrage mit Vorschlaegen.
  - Gewechselt wird **nur explizit**: mit einer Nachricht, die nur aus dem Namen besteht
    (davor erlaubt "Spiel:", "Spiel", "Wechsel zu", "Wechsle zu", "zu", "bei", "fuer",
    danach "bitte"/"danke") -- Antwort "Ok, ab jetzt X." --, oder mit "Spiel: X: <Frage>",
    "Zu X: <Frage>", "Wechsel zu X: <Frage>". Ein Name irgendwo in einer spaeteren Frage
    ("Und bei zwei Spielern?", "Go-Phase") wechselt nicht.
  - Ist die Namensnachricht die Antwort auf unsere Rueckfrage, wird die Frage davor
    beantwortet (gesucht wird mit ihr); sonst nur bestaetigt, die alte Frage wird nicht
    im neuen Spiel wiederholt.
  - Ohne festgelegtes Spiel: Valve `STANDARD_SPIEL`, sonst das einzige Spiel im Index,
    sonst die Rueckfrage "Zu welchem Spiel ist die Frage?".
  - Betrachtet werden hoechstens die letzten 20 Nutzer-Nachrichten; exakte Suche per
    Woerterbuch: 250 Spiele, 201 Nachrichten -> typisch 1,5 ms, max 1,6 ms.
- Passen die Valves nicht zu einem Stand im Index oder hat sich eine `knowledge.jsonl`
  seit dem letzten `rag.py index` geaendert, erscheint das als Fehlertext mit dem
  passenden `rag.py index`-Befehl -- keine stille Antwort aus altem Material.
- `HYBRID` gibt es als Valve (Default aus), nie aus der Container-Umgebung.

`knowledge.jsonl` ist als einzelne Datei gemountet. Ein Bind-Mount haengt an der Inode:
wird die Datei auf dem Host per Rename ersetzt (`mv`, rsync ohne `--inplace`), sieht der
Container weiter die alte. Die Ingest-Skripte schreiben an Ort und Stelle und sind nicht
betroffen; nach einem Rename-Ersatz `systemctl --user restart open-webui.service`.

## Was man dabei lernt

- Die groessten Fehler sind nicht die falschen Antworten, sondern die *ueberzeugend*
  falschen. Ein sauberer Grounding-Prompt und kleine Haeppchen bringen das Modell
  dazu, lieber "keine Angabe" zu sagen als zu raten.
- "Mehr" (mehr Haeppchen, groesseres Kandidatenfeld) macht es oft schlechter.
- Der Beobachtungspunkt darf nicht an derselben Konfiguration haengen, die er bewachen soll.
  Genau das war hier eine Zeit lang der Fall: `DROP_TYPES` verkleinerte den Nenner der
  Retrieval-Quote, ohne dass ein Retrieval besser wurde.
- Der groesste Hebel sitzt ganz vorne, beim Einlesen -- und die richtige Methode
  haengt vom Inhaltstyp ab: **Fliesstext -> rohe Extraktion reicht, echte Tabellen
  -> Docling + Verbalisierung, Grafiken -> Vision.**
- Miss die richtige Sache: ohne ein Golden Set, das alle Inhaltstypen abdeckt,
  zieht man leicht den falschen Schluss.
