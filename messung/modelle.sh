#!/bin/bash
# Modellvergleich: je Modell N Laeufe (Default 2) mit messung/lauf.py.
#
#   messung/modelle.sh -o AUSGABEVERZEICHNIS [-p PULLLOG] [-n LAEUFE] [-w SEKUNDEN] [-d DATENVERZ] MODELL[@think] ...
#
# Alle anderen Stellschrauben kommen aus der Umgebung des Aufrufs (CHUNK_SIZE, DROP_TYPES,
# OLLAMA_URL ...), nichts ist hier festverdrahtet. PYTHON waehlt den Interpreter (Default python3).
# MODELL@think setzt THINK=1 fuer dieses Modell (sonst THINK=0).
# -p PULLLOG: vor jedem Modell warten, bis im Log eine Zeile "ENDE <modell> " steht (ein laufender
#    Download in einem anderen Prozess); -w begrenzt die Wartezeit je Modell (Default 0 = unbegrenzt).
#    Es wird nur gewartet, nie ein Prozess beendet.
# Ergebnis: AUSGABEVERZEICHNIS/<modell>-<a|b|...>/{antworten.jsonl,meta.json,eval.txt} und modelle.log.
# Danach: messung/bewerte.py und messung/vergleiche.py (siehe messung/README.md).

hier="$(cd "$(dirname "$0")" && pwd)"
python="${PYTHON:-python3}"
laeufe=2; wartezeit=0; aus=""; pulllog=""; daten=""
while getopts "o:p:n:w:d:" opt; do
  case "$opt" in
    o) aus="$OPTARG" ;;
    p) pulllog="$OPTARG" ;;
    n) laeufe="$OPTARG" ;;
    w) wartezeit="$OPTARG" ;;
    d) daten="$OPTARG" ;;
    *) exit 2 ;;
  esac
done
shift $((OPTIND - 1))
if [ -z "$aus" ] || [ $# -eq 0 ]; then
  sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//' >&2
  exit 2
fi
mkdir -p "$aus"
protokoll="$aus/modelle.log"

warte() { # modell -- wartet auf "ENDE <modell> " im Pull-Log; 1 bei Zeitueberschreitung
  [ -z "$pulllog" ] && return 0
  local seit=$SECONDS
  until grep -qF "ENDE $1 " "$pulllog" 2>/dev/null; do
    if [ "$wartezeit" -gt 0 ] && [ $((SECONDS - seit)) -ge "$wartezeit" ]; then return 1; fi
    sleep 30
  done
}

buchstaben=(a b c d e f g h)
for eintrag in "$@"; do
  modell="${eintrag%@think}"
  think=0; [ "$modell" != "$eintrag" ] && think=1
  name="$(echo "$modell" | tr ':/' '__')"; [ "$think" = 1 ] && name="$name-think"
  if ! warte "$modell"; then
    echo "$(date +%s) UEBERSPRUNGEN $modell (Pull-Log meldet kein Ende innerhalb ${wartezeit}s)" >> "$protokoll"
    continue
  fi
  for ((i = 0; i < laeufe; i++)); do
    d="$aus/$name-${buchstaben[$i]}"
    mkdir -p "$d"
    echo "$(date +%s) START $modell ${buchstaben[$i]}" >> "$protokoll"
    args=("$d")
    [ -n "$daten" ] && args+=(--daten "$daten")
    LLM_MODEL="$modell" THINK="$think" PYTHONUNBUFFERED=1 \
      "$python" "$hier/lauf.py" "${args[@]}" > "$d/eval.txt" 2>&1
    rc=$?
    echo "$(date +%s) ENDE $modell ${buchstaben[$i]} rc=$rc $(wc -l < "$d/antworten.jsonl" 2>/dev/null)" >> "$protokoll"
  done
done
echo "$(date +%s) ALLES-FERTIG" >> "$protokoll"
