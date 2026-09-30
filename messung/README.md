# Messwerkzeug

Wiederholbare Messungen an `rag.py`: **Lauf -> Bewerten -> Vergleichen**. Nur Code -- Golden Sets,
Antworten und Urteile stammen aus Regelheften und liegen in einem eigenen Datenverzeichnis
ausserhalb des Repos (Default fuer Golden Sets: `DATA_DIR`, sonst `data/` des Repos, das per
`.gitignore` ausgeschlossen ist). Ausgaben gehen in ein Verzeichnis, das du beim Aufruf nennst.

## Ablauf

```bash
export DATEN=~/mein-datenverzeichnis     # Golden Sets: $DATEN/<spiel_id>/golden_set.json
export LAEUFE=~/messlaeufe               # Ausgaben, ausserhalb des Repos

# 1. Retrieval zuerst, ohne Antwortmodell (Minuten statt Stunden)
HYBRID=1 python messung/retrieval.py trefferquote --daten $DATEN

# 2. Laeufe: je Setting mindestens ZWEI (Antworten sind nicht deterministisch)
LLM_MODEL=qwen3:14b ENTSCHEIDUNG=1 python messung/lauf.py $LAEUFE/entscheid-a --daten $DATEN | tee $LAEUFE/entscheid-a.eval.txt
LLM_MODEL=qwen3:14b ENTSCHEIDUNG=1 python messung/lauf.py $LAEUFE/entscheid-b --daten $DATEN
LLM_MODEL=qwen3:14b                 python messung/lauf.py $LAEUFE/basis-a --daten $DATEN
LLM_MODEL=qwen3:14b                 python messung/lauf.py $LAEUFE/basis-b --daten $DATEN

# 3. Bewerten (Default: Modus anthropic, Modell Haiku; Key wie in judge.py)
python messung/bewerte.py --golden $DATEN $LAEUFE/entscheid-a $LAEUFE/entscheid-b $LAEUFE/basis-a $LAEUFE/basis-b

# 4. Vergleichen: NAME=lauf1,lauf2 -- der erste Name ist die Basis (oder --basis NAME)
python messung/vergleiche.py basis=$LAEUFE/basis-a,$LAEUFE/basis-b entscheid=$LAEUFE/entscheid-a,$LAEUFE/entscheid-b
```

Modellvergleich (je Modell zwei Laeufe; `@think` schaltet `THINK=1`; optional wartet das Skript je
Modell auf ein laufendes Pull, dessen Log eine Zeile `ENDE <modell> ` bekommt -- es beendet nie einen Prozess):

```bash
CHUNK_SIZE=400 DROP_TYPES=flavor,meta messung/modelle.sh -o $LAEUFE/modelle -d $DATEN \
    -p ~/pull.log -w 7200  gemma3:12b-it-qat  phi4:14b  gemma4:12b-it-qat@think
```

## Was jedes Werkzeug tut

| Datei | Zweck |
|---|---|
| `lauf.py` | `rag.py eval` (Default `--alle`, oder Spiel-IDs) mit Antwortprotokoll `antworten.jsonl` (Antwort, abgerufene Seiten, Scores, Option des Entscheidungsschritts, `t_antwort`) und `meta.json` (Modell, wirksame Stellschrauben, gesetzte Env-Werte, git-Commit von `rag.py` samt Aenderungsflag, Start/Ende). Ein Lauf ist damit ohne die Konsolenausgabe nachvollziehbar. Ueberschreibt nie einen vorhandenen Lauf. |
| `bewerte.py` | Bewertet `antworten.jsonl` mit `judge.bewerte` und schreibt `urteile.jsonl` daneben. Alle Fragen werden vor dem ersten Modellaufruf aufgeloest; eine unbekannte Frage bricht ab, bevor etwas bezahlt ist. |
| `vergleiche.py` | Tabelle ueber Settings: Zaehler je Urteil, Treffsicherheit = richtig / (alle - unsicher), stabil richtig/falsch ueber Wiederholungen, Laufzeit typisch (Median) und Maximum, Fragen, die sich gegenueber der Basis in **allen** Laeufen gleichgerichtet aendern. Keine Mittelwerte. |
| `retrieval.py` | `trefferquote`: Trefferquote je Spiel fuer die Env-Konfiguration. `verzeichnis --aus X.jsonl`: Anteil Vision-/Verzeichnis-artiger Chunks im Top-k (ohne Regelheft-Text in der Ausgabe). |
| `modelle.sh` | N Modelle x M Laeufe (`-n`, Default 2) ueber `lauf.py`. |

## Lehren, die im Werkzeug stecken

- **Mindestens zwei Laeufe je Setting.** Dieselbe Frage kippt zwischen Wiederholungen. Ein Unterschied
  zwischen zwei Settings mit je einem Lauf ist nicht von diesem Rauschen zu trennen; `vergleiche.py`
  macht dazu bei weniger als zwei Wiederholungen keine Aussage (`--min-laeufe`). "Gleichgerichtet"
  heisst streng: jeder Lauf des Settings besser als jeder Lauf der Basis.
- **Retrieval vor dem LLM messen.** Trifft das Retrieval die Seite nicht, kann kein Modell antworten;
  die Trefferquote ist in Minuten da und trennt Retrieval- von Modellfehlern.
- **Feste Verweigerungssaetze werden deterministisch gewertet.** `judge.bewerte` entscheidet sie ohne
  Modellaufruf (`deterministisch: true` in `urteile.jsonl`); sie zaehlen nicht in Laufzeit und Tokens.
- **Typisch und Maximum, nie ein Mittelwert allein.** Ein einzelner 60-s-Ausreisser verschwindet im
  Mittel, im Betrieb tut er weh.
- **Tests nie in einem Clone mit Symlinks auf Livedaten laufen lassen.** Ein Testlauf schrieb einmal
  ueber einen Symlink in die Live-Wissensbasis (siehe `test_schutz.py`). Die Tests hier importieren
  `testumgebung` zuerst und schreiben nur in Temp-Verzeichnisse.

## Tests

```bash
python test_messung_vergleiche.py   # Kennzahlen an handgebauten Urteilen (Nenner, stabil, Median, gleichgerichtet)
python test_messung_bewerte.py      # judge.bewerte-Fake, urteile.jsonl, Abbruch bei unbekannter Frage
python test_messung_lauf.py         # Haken an rag.answer, antworten.jsonl, meta.json (Fake-Eval und echte Verdrahtung)
python test_messung_retrieval.py    # Trefferquote und Verzeichnis-Anteil mit Fake-Embedding
```

Mutationsproben dazu: `NUR=MV,MB,ML,MR python test_mutationen.py`.
