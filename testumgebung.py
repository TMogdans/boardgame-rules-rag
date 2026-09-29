# -*- coding: utf-8 -*-
"""
Gemeinsame Testumgebung: JEDE test_*.py importiert dieses Modul als Erstes.

    import testumgebung  # noqa: F401  -- vor rag/classify/ingest/...

Vorfall, den es verhindert: Ein Testlauf (Mutationstreiber) schrieb ueber
classify.main() in die knowledge.jsonl neben dem Code -- im Clone ein Symlink
auf die LIVE-Wissensbasis der Pipe. Ergebnis: 79 Eintraege "flavor", die
Sprach-Regelfrage hatte 8 Minuten lang 0 Chunks.

Deshalb zeigt fuer die Laufzeit der Tests jeder Standardpfad, in den ein
Skript schreiben oder aus dem es lesen kann, in ein eigenes Temp-Verzeichnis:
  - DATA_DIR / INDEX_PATH per Umgebung, BEVOR rag.py importiert wird (auch fuer
    Kindprozesse und das rag.py, das die Pipe selbst laedt)
  - rag.__file__ (alter Weg: knowledge.jsonl/golden_set.json/pdfs neben rag.py),
    rag.DATA_DIR, rag.INDEX_PATH, rag.PDF_DIR
  - classify.KNOW, vision_ingest.KNOW, auto_ingest.KNOW, ingest.OUT
  - judge.ANTHROPIC_KEY_DATEI (nie der echte API-Key)
  - HOME und XDG_CONFIG_HOME, BEVOR ein Skript importiert wird: auch ein Pfad, der
    beim Import aus "~" gebildet und festgehalten wird (etwa als Default-Argument,
    Kritiker-Mutation J1), zeigt damit nie auf den echten Key. PYTHONUSERBASE bleibt
    auf dem echten Wert, damit Kindprozesse ihre --user-Pakete weiter finden.
Einzelne Tests duerfen darueber hinaus eigene Temp-Pfade setzen.
"""
import atexit
import os
import shutil
import site
import sys
import tempfile
import types

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

if "judge" in sys.modules:
    raise RuntimeError("testumgebung muss vor judge importiert werden -- sonst gilt der echte HOME")
TMP = tempfile.mkdtemp(prefix="rag-tests-")
atexit.register(shutil.rmtree, TMP, True)
os.environ.setdefault("PYTHONUSERBASE", site.getuserbase())
HOME = os.path.join(TMP, "home")
os.makedirs(os.path.join(HOME, ".config"))
os.environ["HOME"] = HOME
os.environ["XDG_CONFIG_HOME"] = os.path.join(HOME, ".config")
DATA = os.path.join(TMP, "data")
os.environ["DATA_DIR"] = DATA
os.environ["INDEX_PATH"] = os.path.join(DATA, "index.sqlite")
for _k in ("KNOWLEDGE_JSONL", "GOLDEN_SET"):
    os.environ.pop(_k, None)

# docling und pymupdf gehoeren in die Ingest-venv; ohne sie Attrappen, damit auch
# auto_ingest/ingest hier importiert und umgebogen werden koennen.
for _name in ("docling", "docling.document_converter", "pymupdf"):
    if _name not in sys.modules:
        try:  # pragma: no cover
            __import__(_name)
        except ImportError:
            _m = types.ModuleType(_name)
            if _name == "docling.document_converter":
                _m.DocumentConverter = object
                sys.modules["docling"].document_converter = _m
            sys.modules[_name] = _m

import rag            # noqa: E402
import classify       # noqa: E402
import vision_ingest  # noqa: E402
import auto_ingest    # noqa: E402
import ingest         # noqa: E402
import judge          # noqa: E402

rag.__file__ = os.path.join(TMP, "rag.py")
rag.DATA_DIR = DATA
rag.INDEX_PATH = os.environ["INDEX_PATH"]
rag.PDF_DIR = os.path.join(TMP, "pdfs")
classify.KNOW = os.path.join(TMP, "knowledge.jsonl")
vision_ingest.KNOW = os.path.join(TMP, "knowledge.jsonl")
auto_ingest.KNOW = os.path.join(TMP, "knowledge.jsonl")
ingest.OUT = os.path.join(TMP, "knowledge.jsonl")
# judge.py liest sonst den echten API-Key aus ~/.config/anthropic/api_key
judge.ANTHROPIC_KEY_DATEI = os.path.join(TMP, "anthropic_api_key")
