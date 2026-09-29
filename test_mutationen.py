#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mutationsprobe: verfaelscht die Implementierung gezielt und prueft, dass ein
Test rot wird. Ein gruener Testlauf beweist nichts, solange nicht gezeigt ist,
dass die Tests ueberhaupt etwas festhalten.

    python test_mutationen.py

Der Treiber arbeitet NIE im Arbeitsverzeichnis: er kopiert die Quelldateien in
ein Temp-Verzeichnis (ohne Symlinks, ohne data/, knowledge.jsonl, golden_set.json)
und mutiert nur dort. Vorfall: verfaelschter Code schreibt, wohin er will -- unter
S10 schrieb classify.main() ueber einen Symlink im Clone in die LIVE-Wissensbasis.
Jede Mutation wird in der Kopie eingespielt, die Tests aus TESTS laufen dort, dann
wird die Datei der Kopie zurueckgeschrieben (finally).
Exit-Code 1, wenn eine Mutation gruen bleibt, deren Namen nicht mit "[gleich]"
beginnt -- solche sind nachweislich verhaltensgleich, siehe M3.
"""
import glob
import io
import os
import shutil
import site
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
# Was in die Laufkopie gehoert: Code und die eingecheckten Testdaten -- nie echte Daten.
KOPIEREN = ("*.py", "golden_set.example.json", "regression_referenz.json", "pipe_referenz.json",
            "pipe_verlauf_referenz.json")


def laufkopie():
    """Temp-Kopie der Quelldateien; Symlinks werden nicht mitgenommen."""
    ziel = tempfile.mkdtemp(prefix="rag-mutationen-")
    for muster in KOPIEREN:
        for quelle in glob.glob(os.path.join(BASE, muster)):
            if os.path.islink(quelle):
                continue
            shutil.copy(quelle, ziel)
    os.makedirs(os.path.join(ziel, "pdfs"))
    return ziel
TESTS = ("test_classify.py", "test_ingest_seite.py", "test_wertung.py", "test_openwebui_pipe.py",
         "test_spiele.py", "test_index.py", "test_suche.py", "test_eval_spiele.py",
         "test_pipe_index.py", "test_regression.py", "test_zuordnung.py", "test_chat.py",
         "test_pipe_alt.py", "test_judge.py")

# (Name, Datei, Suchmuster, Ersatz)
MUTATIONEN = [
    ("M1 Negationserkennung aus (NEG_FENSTER = 0)",
     "classify.py", "NEG_FENSTER = 2", "NEG_FENSTER = 0"),

    ("M2 Reihenfolge zurueckgedreht: Substring, flavor/meta zuerst",
     "classify.py",
     "    treffer = _nennungen(text)\n"
     "    kandidaten = {kat for kat, exakt in treffer if exakt}\n"
     "    genannt = {kat for kat, _ in treffer}\n"
     "    if len(kandidaten) == 1 and len(genannt) == 1:\n"
     "        return next(iter(kandidaten))\n"
     "    return None",
     '    for kat in ("flavor", "meta", "regel"):\n'
     "        if kat in text:\n"
     "            return kat\n"
     "    return None"),

    # Schritt 1 ist ein Schnellpfad: der exakte Vergleich in Schritt 2 deckt
    # ihn semantisch ab (0 Abweichungen ueber 322 Eingaben). Bleibt gruen.
    ("[gleich] M3 exaktes Matching (Schritt 1) entfernt",
     "classify.py",
     "    a = antwort.strip().lower()\n    if a in KATEGORIEN:\n        return a",
     "    a = antwort.strip().lower()"),

    ("M4 <think>-Block wird nicht entfernt",
     "classify.py",
     '    rest = re.sub(r"<think>.*?(?:</think>|\\Z)", " ", a, flags=re.DOTALL)',
     "    rest = a"),

    ("M5 Fallback ist flavor statt regel",
     "classify.py", 'FALLBACK   = "regel"', 'FALLBACK   = "flavor"'),

    ("M6 Wortgrenze aufgeweicht: Kompositum zaehlt als Kandidat",
     "classify.py", "            treffer.append((kat, wort == kat))",
     "            treffer.append((kat, True))"),

    ("M7 ingest.py laesst 'seite' wieder weg",
     "ingest.py", '    return {"id": cid, "seite": seite, "roh": roh, "text": text}',
     '    return {"id": cid, "roh": roh, "text": text}'),

    ("M8 ingest.py schreibt die Chunk-ID als Seite",
     "ingest.py", '    return {"id": cid, "seite": seite, "roh": roh, "text": text}',
     '    return {"id": cid, "seite": cid, "roh": roh, "text": text}'),

    ("M9 ingest.py bildet Bloecke wieder ueber das Gesamtdokument",
     "ingest.py",
     "    out = []\n"
     "    for p in sorted(seiten):\n"
     '        for b in split_blocks("\\n\\n".join(seiten[p]), target):\n'
     "            out.append((p, b))\n"
     "    return out",
     '    alles = "\\n\\n".join("\\n\\n".join(seiten[p]) for p in sorted(seiten))\n'
     "    return [(1, b) for b in split_blocks(alles, target)]"),

    ("M16 Wertung wieder von DROP_TYPES abhaengig machen",
     "rag.py",
     '    if frage.get("erwartet_verweigerung"):\n        return KAT_VERWEIGERUNG',
     '    import os as _os\n'
     '    if frage.get("typ") in {x for x in _os.environ.get("DROP_TYPES", "").split(",") if x}:\n'
     '        return KAT_VERWEIGERUNG\n'
     '    if frage.get("erwartet_verweigerung"):\n        return KAT_VERWEIGERUNG'),

    ("M17 stiller seite-Fallback zurueck (Chunk-ID als Seitenzahl)",
     "rag.py", 'def chunk_seite(c):', 'def chunk_seite(c):\n    return c.get("seite", c["id"])'),

    ("M18 Chunk-Guard entfernt (Endlosschleife bei CHUNK_SIZE <= OVERLAP)",
     "rag.py", "def pruefe_chunk_konfiguration(size=None, overlap=None):",
     "def pruefe_chunk_konfiguration(size=None, overlap=None):\n    return\n\n\ndef _abgeschaltet(size=None, overlap=None):"),

    ("M15 Flexionsendung bei Phrasen entfernt (Falsch-Negativ 'keine Angaben')",
     "rag.py",
     '    if rechts and len(kw.split()) > 1 and kw[-1:].isalpha():\n'
     '        rechts = r"\\w{0,3}(?!\\w)"',
     "    pass"),

    ("M10 vision_ingest.py laesst 'seite' wieder weg",
     "vision_ingest.py",
     '    return {"id": cid, "seite": seite,\n'
     '            "quelle": f"vision:{os.path.basename(img)}", "text": text}',
     '    return {"id": cid,\n'
     '            "quelle": f"vision:{os.path.basename(img)}", "text": text}'),

    ("M11 vision_ingest.py erfindet Seite 1, statt abzubrechen",
     "vision_ingest.py",
     "    s = seite_aus_bildname(pfad)\n    if s is None:\n        raise SystemExit(",
     "    s = seite_aus_bildname(pfad)\n    if s is None:\n        return 1\n"
     "    if False:\n        raise SystemExit("),

    ("M12 classify.py schreibt die Rohantwort nicht mit",
     "classify.py", '        e["typ"], e["typ_antwort"] = classify(e["text"])',
     '        e["typ"] = classify(e["text"])[0]'),

    ("M13 classify.py verliert beim Neuschreiben das 'seite'-Feld",
     "classify.py",
     '    with open(KNOW, "w") as f:\n        for e in entries:\n'
     '            f.write(json.dumps(e, ensure_ascii=False) + "\\n")',
     '    with open(KNOW, "w") as f:\n        for e in entries:\n'
     '            mager = {k: v for k, v in e.items() if k != "seite"}\n'
     '            f.write(json.dumps(mager, ensure_ascii=False) + "\\n")'),

    ("M14 Kontrollausgabe nennt die Modellantwort nicht",
     "classify.py",
     "            print(f\"  [{e['typ']}] Modell sagte: {e['typ_antwort'][:70]!r}\")",
     "            print(f\"  [{e['typ']}]\")"),

    # ---- Open-WebUI-Pipe (test_openwebui_pipe.py) ----
    ("P1 Pipe baut den Prompt selbst statt ueber rag.baue_nachrichten",
     "openwebui_pipe.py", "        return rag.baue_nachrichten(frage, hits), hits",
     '        return [{"role": "system", "content": rag.SYSTEM_PROMPT}, {"role": "user", "content": frage}], hits'),
    ("P2 CLI baut den Prompt anders als die Pipe",
     "rag.py", '"messages": baue_nachrichten(query, hits),', '"messages": [{"role": "user", "content": query}],'),
    ("P3 CHUNK_SIZE-Valve wirkt nicht (Container-Umgebung schlaegt durch)",
     "openwebui_pipe.py", "        rag.CHUNK_SIZE = v.CHUNK_SIZE\n", ""),
    ("P4 RERANK nicht fest aus",
     "openwebui_pipe.py", "        rag.RERANK = False  # braucht torch, das im Open-WebUI-Image fehlt\n", ""),
    ("P5 EMBED_MODEL-Valve wirkt nicht",
     "openwebui_pipe.py", "        rag.EMBED_MODEL = v.EMBED_MODEL\n", ""),
    ("P6 Defaults weichen von der gemessenen Konfiguration ab",
     "openwebui_pipe.py", 'CHUNK_SIZE: int = Field(400,', 'CHUNK_SIZE: int = Field(800,'),
    ("P7 DROP_TYPES nicht im Index-Key",
     "openwebui_pipe.py", "v.DROP_TYPES, v.EMBED_MODEL, v.OLLAMA_URL, v.CHUNK_SIZE", "v.EMBED_MODEL, v.OLLAMA_URL, v.CHUNK_SIZE"),
    ("P8 Cache-Key nur mtime",
     "openwebui_pipe.py", "return (st.st_mtime_ns, st.st_size, st.st_ino)", "return st.st_mtime_ns"),
    ("P9 rag.py wird nie neu geladen",
     "openwebui_pipe.py", "if key != self._rag_key:", "if self._rag is None:"),
    ("P10 Retrieval blockiert den Event-Loop (kein to_thread)",
     "openwebui_pipe.py", "await asyncio.to_thread(self._suche, frage, self.valves)", "self._suche(frage, self.valves)"),
    ("P11 retrieve ausserhalb des Locks (Modell-Globale koennen wechseln)",
     "openwebui_pipe.py", "            chunks, embs = self._lade_index(rag, v)\n            hits =",
     "            chunks, embs = self._lade_index(rag, v)\n        hits ="),
    ("P12 Fehler entkommen dem Chat",
     "openwebui_pipe.py", "        except Exception as e:\n            yield f", "        except ZeroDivisionError as e:\n            yield f"),
    ("P13 auch GeneratorExit wird als Fehler abgefangen",
     "openwebui_pipe.py", "        except Exception as e:\n            yield f", "        except BaseException as e:\n            yield f"),
    ("P14 Fusszeile geht in den Verlauf",
     "openwebui_pipe.py", '"content": ohne_fusszeile(text_von(m.get("content")), index_weg)', '"content": text_von(m.get("content"))'),
    ("P15 Task-Anfragen laufen ins Retrieval",
     "openwebui_pipe.py", "        if task:", "        if task == 'title_generation':"),
    ("P16 Ollama-Fehlergrund geht verloren",
     "openwebui_pipe.py", 'raise RuntimeError(f"Ollama antwortet {r.status_code}: {grund}")', 'raise RuntimeError(f"Ollama antwortet {r.status_code}")'),
    ("P17 LLM-Valves wirken nicht",
     "openwebui_pipe.py", '"model": v.LLM_MODEL, "messages": nachrichten, "think": v.THINK', '"model": "qwen3:14b", "messages": nachrichten, "think": False'),
    # _lade_rag setzt beim Neuladen _index_key=None -> der Index wird ohnehin neu
    # gebaut; der rag-Key im Index-Key ist Absicherung, kein zusaetzliches Verhalten.
    ("[gleich] P18 rag-Key nicht im Index-Key",
     "openwebui_pipe.py", "key = (self._rag_key, v.KNOWLEDGE_PATH", "key = (v.KNOWLEDGE_PATH"),
    ("P19 unbekanntes Spiel wird trotzdem beantwortet",
     "openwebui_pipe.py", '            if status != "treffer":', '            if False:'),
    ("P20 Spielzuordnung ohne Unschaerfe (nur exakt)",
     "rag.py", "    if bewertet and bewertet[0][0] >= schwelle:", "    if False:"),
    ("P21 Schwelle so niedrig, dass fremde Spiele treffen",
     "rag.py", "def ordne_spiel(anfrage, katalog, schwelle=0.8):", "def ordne_spiel(anfrage, katalog, schwelle=0.1):"),
    ("P22 Normalisierung ignoriert Leerzeichen/Satzzeichen nicht",
     "rag.py", 'return re.sub(r"[\\W_]+", "", (name or "").casefold())', 'return (name or "").casefold()'),
    ("P23 Aliase aus den Valves werden ignoriert",
     "rag.py", '    formen = [name] + [a for a in (aliase or "").split(",") if a.strip()]', '    formen = [name]'),
    ("P24 Sprachmodus behaelt die Fusszeile",
     "openwebui_pipe.py", '        if not rf.get("sprache"):\n            yield fundstellen(hits)', '        yield fundstellen(hits)'),
    ("P25 Vorschlaege werden nicht genannt",
     "rag.py", '        return "unbekannt", [k for r, k in roh if r >= 0.5]', '        return "unbekannt", []'),
    ("P26 Katalog kommt nicht aus den Valves",
     "openwebui_pipe.py", "ordne_spiel_valves(rf[\"spiel\"], katalog_aus_valves(v.SPIEL, v.SPIEL_ALIASE))", "ordne_spiel_valves(rf[\"spiel\"], katalog_aus_valves(\"Food Chain Magnate\", \"Food Chain, FCM\"))"),

    # ---- Spiel als Dimension (test_spiele.py) ----
    ("S1 auto_ingest.py schreibt wieder in die gemeinsame knowledge.jsonl",
     "auto_ingest.py", "    return pdf, pfad, rag.spiel_felder(meta), meta", "    return pdf, KNOW, rag.spiel_felder(meta), meta"),
    ("S2 auto_ingest.py-Chunks tragen kein Spiel",
     "auto_ingest.py", "    return pdf, pfad, rag.spiel_felder(meta), meta", "    return pdf, pfad, {}, meta"),
    ("S3 Einzeldatei-Weg ueberschreibt wieder ein vorhandenes Heft",
     "auto_ingest.py", "        if os.path.exists(KNOW):", "        if False:"),
    ("S4 vision_ingest.py ersetzt wieder alle vision:-Chunks (zweite Grafikseite loescht die erste)",
     "vision_ingest.py", '    entries = lade_ohne_vision(know, f"vision:{os.path.basename(img)}")', "    entries = lade_ohne_vision(know)"),
    ("S5 vision_ingest.py schreibt trotz --spiel in die Einzeldatei",
     "vision_ingest.py", "        meta, know = rag.bereite_spiel_vor(opt)", "        meta, _ = rag.bereite_spiel_vor(opt)"),
    ("S6 Vision-Prompt ohne Spielname/Sprache",
     "vision_ingest.py", '        PROMPT = vision_prompt(meta["name"], meta["sprache"])', "        pass"),
    ("S7 ingest.py ignoriert die Heftsprache",
     "ingest.py", '    return VERB_PROMPT.replace("{satzsprache}", rag.SPRACHEN[sprache][0])', '    return VERB_PROMPT.replace("{satzsprache}", "deutsche")'),
    ("S8 spiel_id wird nicht geprueft (Pfad-Ausbruch)",
     "rag.py", "    if not isinstance(spiel_id, str) or not SPIEL_ID_MUSTER.fullmatch(spiel_id):", "    if False:"),
    ("S9 fremde Chunks im Spielverzeichnis werden still uebernommen",
     "rag.py", '    falsch = [c.get("id", "?") for c in roh if c.get("spiel_id") != spiel_id]', "    falsch = []"),
    ("S10 classify.py ignoriert die spiel_id",
     "classify.py", "    if not rest:\n        return KNOW", "    if True:\n        return KNOW"),

    # ---- Persistenter Index, Fingerprint-Invalidierung (test_index.py) ----
    ("F1 Fingerprint ohne Dateiinhalt (nur Konfiguration)",
     "rag.py", "            h.update(block)\n", "            pass\n"),
    ("F2 Konfiguration ohne EMBED_MODEL",
     "rag.py", '"embed_model": embed_model or EMBED_MODEL,', '"embed_model": "egal",'),
    ("F3 Konfiguration ohne CHUNK_OVERLAP",
     "rag.py", '"chunk_size": size, "chunk_overlap": overlap}', '"chunk_size": size}'),
    ("F4 Konfiguration ohne Schema-Version",
     "rag.py", 'json.dumps({"schema": INDEX_SCHEMA, ', 'json.dumps({'),
    ("F5 vorhandener Stand gilt immer als aktuell",
     "rag.py", "    if alt and alt[0] == fp:", "    if alt:"),
    ("F6 immer neu einbetten (kein persistenter Nutzen)",
     "rag.py", "    if alt and alt[0] == fp:", "    if False:"),
    ("F7 Einzelaufruf raeumt fremde Spiele ab",
     "rag.py", "    alle = spiel_ids is None\n", "    alle = True\n"),
    ("F8 erst loeschen, dann einbetten (Abbruch hinterlaesst leeren Stand)",
     "rag.py", "    embs = l2norm(embed_gebatcht([s for _, _, s in stuecke])).astype(\"<f4\")\n",
     "    con.execute(\"DELETE FROM chunks WHERE spiel_id=? AND konfig=?\", (spiel_id, konfig)); con.commit()\n"
     "    embs = l2norm(embed_gebatcht([s for _, _, s in stuecke])).astype(\"<f4\")\n"),
    ("F9 Seite verliert beim Speichern ihren Typ",
     "rag.py", '"seite": json.loads(z[2]), "text": z[4],', '"seite": z[2], "text": z[4],'),

    # ---- Suche pro Spiel: Spielfilter und Hybrid (test_suche.py, test_index.py) ----
    ("SF1 lade_spiel filtert nicht nach Spiel",
     "rag.py", '"WHERE spiel_id=? AND konfig=? ORDER BY pos", (spiel_id, konfig)).fetchall()',
     '"WHERE ? IS NOT NULL AND konfig=? ORDER BY pos", (spiel_id, konfig)).fetchall()'),
    ("SF2 vorab geladene fremde Chunks werden durchgewunken",
     "rag.py", "        if fremd:\n            raise KonfigFehler", "        if False:\n            raise KonfigFehler"),
    ("SF3 BM25 filtert erst nach dem LIMIT (Spiel nicht im MATCH)",
     "rag.py", """(f'tag : "{fts_tag(spiel_id, konfig)}" AND text : ({ausdruck})', n + ausgelassen)""",
     """(f'text : ({ausdruck})', n + ausgelassen)"""),
    ("SF4 BM25 ganz ohne Spielfilter",
     "rag.py", "    return [pos[r[0]] for r in zeilen if r[0] in pos][:n]",
     "    return [pos.get(r[0], 0) for r in con.execute('SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? "
     "ORDER BY bm25(chunks_fts), rowid LIMIT ?', (ausdruck, n))]"),
    ("SF5 BM25 ohne Nachholen fuer ausgelassene Typen (DROP_TYPES verschluckt Treffer)",
     "rag.py", "        (f'tag : \"{fts_tag(spiel_id, konfig)}\" AND text : ({ausdruck})', n + ausgelassen)",
     "        (f'tag : \"{fts_tag(spiel_id, konfig)}\" AND text : ({ausdruck})', n)"),
    ("SF6 tag-Spalte zaehlt in BM25 mit",
     "rag.py", "ORDER BY bm25(chunks_fts, 1.0, 0.0), rowid LIMIT ?", "ORDER BY bm25(chunks_fts, 0.0, 1.0), rowid LIMIT ?"),
    ("H1 HYBRID per Default an",
     "rag.py", 'HYBRID        = os.environ.get("HYBRID", "0") == "1"', 'HYBRID        = os.environ.get("HYBRID", "1") == "1"'),
    ("H2 Fusion ignoriert BM25",
     "rag.py", "        fusion = rrf([vektor, bm25_rangfolge(con, query, chunks, CANDIDATES)])",
     "        fusion = rrf([vektor])"),
    ("H3 Nutzertext geht ungeschuetzt in MATCH",
     "rag.py", """    return " OR ".join('"' + w.replace('"', '""') + '"' for w in dict.fromkeys(woerter))""",
     "    return query"),
    ("H4 RRF ohne Daempfung (1/rang statt 1/(k+rang))",
     "rag.py", "            score[i] = score.get(i, 0.0) + 1.0 / (k + rang)", "            score[i] = score.get(i, 0.0) + 1.0 / rang"),

    # ---- Eval pro Spiel (test_eval_spiele.py) ----
    ("E1 Golden Set eines fremden Spiels wird angenommen",
     "rag.py", '    if gs.get("spiel_id") != spiel_id:', "    if False:"),
    ("E2 --alle laesst Spiele ohne Golden Set stillschweigend weg",
     "rag.py", "        if ohne:\n", "        if False:\n"),
    ("E3 Gesamtblock zaehlt nur das letzte Spiel",
     "rag.py", "        alle_saetze += cmd_eval_spiel(sid, data_dir)", "        alle_saetze = cmd_eval_spiel(sid, data_dir)"),
    ("E4 Eval bringt den Index nicht auf Stand",
     "rag.py", "    aktualisiere_index([spiel_id], data_dir=data_dir, ausgabe=lambda *_: None)\n    con = oeffne_index()\n    try:\n        chunks, embs = lade_spiel(con, spiel_id, drop_fuer_index())",
     "    con = oeffne_index()\n    try:\n        chunks, embs = lade_spiel(con, spiel_id, drop_fuer_index())"),
    ("E5 Eval ignoriert DROP_TYPES auf dem Index-Weg",
     "rag.py", "        chunks, embs = lade_spiel(con, spiel_id, drop_fuer_index())\n        name =",
     "        chunks, embs = lade_spiel(con, spiel_id)\n        name ="),

    # ---- Pipe auf dem Index-Weg, Spielzuordnung (test_pipe_index.py) ----
    ("P27 Index-Weg ordnet gegen die Valves statt gegen den Index",
     "openwebui_pipe.py", "        status, ergebnis = rag.ordne_spiel(anfrage, katalog)\n",
     "        status, ergebnis = rag.ordne_spiel(anfrage, rag.katalog_aus(v.SPIEL, v.SPIEL_ALIASE))\n"),
    ("P28 Aliase aus spiel.json werden ignoriert",
     "rag.py", '        formen = [s["name"], s["spiel_id"]] + list(s.get("aliase") or [])',
     '        formen = [s["name"], s["spiel_id"]]'),
    ("P29 gemeinsamer Alias: das erste Spiel gewinnt",
     "rag.py", '    if exakt:\n        return "unbekannt", exakt', '    if exakt:\n        return "treffer", exakt[0]'),
    ("P30 unscharfer Fast-Gleichstand wird nicht erkannt",
     "rag.py", "        if len(knapp) > 1:", "        if False:"),
    ("P31 veralteter Index wird still benutzt",
     "openwebui_pipe.py", "            if stand and stand[0] != rag.fingerprint(wissen, konfig):", "            if False:"),
    ("P32 HYBRID aus der Container-Umgebung schlaegt durch",
     "openwebui_pipe.py", "        rag.HYBRID = v.HYBRID  # nie aus der Container-Umgebung\n", ""),
    ("P33 ohne Spielangabe wird einfach das erste Spiel genommen",
     "openwebui_pipe.py", "            if len(spiele) == 1:", "            if len(spiele) >= 1:"),
    ("P34 Spiel-Cache ohne spiel_id im Schluessel",
     "openwebui_pipe.py", "datei_stand(v.INDEX_PATH), spiel_id, stand_wissen,", "datei_stand(v.INDEX_PATH), stand_wissen,"),
    ("P35 Katalog wird nie neu gelesen (neues Spiel erst nach Neustart)",
     "openwebui_pipe.py", "        if key != self._katalog_key:", "        if self._katalog is None:"),
    ("P36 STANDARD_SPIEL wird ignoriert",
     "openwebui_pipe.py", "            if v.STANDARD_SPIEL:", "            if False:"),
    ("P37 INDEX_PATH schaltet den Index-Weg nicht ein",
     "openwebui_pipe.py", "        if self.valves.INDEX_PATH:", "        if False:"),
    ("P38 Spiel-Cache waechst unbegrenzt",
     "openwebui_pipe.py", "        while len(self._spiel_cache) > v.CACHE_SPIELE:", "        while False:"),

    # ---- Regression alter -> neuer Weg (test_regression.py) ----
    ("R1 Index liefert Chunks in umgekehrter Folge (Gleichstaende kippen, wie bei sqlite-vec)",
     "rag.py", '"WHERE spiel_id=? AND konfig=? ORDER BY pos", (spiel_id, konfig)).fetchall()',
     '"WHERE spiel_id=? AND konfig=? ORDER BY pos DESC", (spiel_id, konfig)).fetchall()'),
    ("R2 Vektoren als float16 gespeichert",
     "rag.py", "(spiel_id, konfig, pos, json.dumps(seite), typ, text, e.tobytes())",
     "(spiel_id, konfig, pos, json.dumps(seite), typ, text, e.astype('<f2').astype('<f4').tobytes())"),
    ("R3 Migration verliert das typ-Feld",
     "rag.py", "    zeilen = \"\".join(json.dumps({**c, **felder}, ensure_ascii=False)",
     "    zeilen = \"\".join(json.dumps({**{k: v for k, v in c.items() if k != 'typ'}, **felder}, ensure_ascii=False)"),
    ("R4 Migration sortiert nach Seite",
     "rag.py", '+ "\\n" for c in roh)', '+ "\\n" for c in sorted(roh, key=lambda c: c["seite"]))'),
    ("R5 Index zerteilt anders als der alte Weg",
     "rag.py", '        for stueck in zerteile(c["text"], size, overlap):', '        for stueck in zerteile(c["text"].strip(), size, overlap):'),
    # Aus dem Review: beide Wege teilen die Rangfolge-Zeile. Solange der Test HEAD
    # gegen HEAD verglich, blieb K2 gruen; jetzt Referenz ed36f99 (regression_referenz.json).
    ("K2 Gleichstand in der gemeinsamen Rangfolge-Zeile umgedreht",
     "rag.py", '    return np.argsort(-sims, kind="stable")', "    return np.lexsort((-np.arange(len(sims)), -sims))"),
    ("K3 Gleichstand kippt nur im Index-Weg",
     "rag.py", "    order = rangfolge(sims)[:k]\n",
     "    order = rangfolge(sims)[:k] if spiel_id is None else np.lexsort((-np.arange(len(sims)), -sims))[:k]\n"),
    ("K2b Rangfolge wieder instabil (quicksort, plattformabhaengig bei Gleichstand)",
     "rag.py", '    return np.argsort(-sims, kind="stable")', "    return np.argsort(-sims)"),
    ("K2c Reranker-Kandidaten ohne definierte Gleichstandsregel",
     "rag.py", "        cand = [int(i) for i in rangfolge(sims)[:CANDIDATES]]\n        # 2. Stufe",
     "        cand = [int(i) for i in np.lexsort((-np.arange(len(sims)), -sims))[:CANDIDATES]]\n        # 2. Stufe"),
    ("K2d Hybrid-Vektorliste ohne definierte Gleichstandsregel",
     "rag.py", "        vektor = [int(i) for i in rangfolge(sims)[:CANDIDATES]]",
     "        vektor = [int(i) for i in np.lexsort((-np.arange(len(sims)), -sims))[:CANDIDATES]]"),
    ("V1 leere Quelle des alten Wegs faellt nicht auf",
     "rag.py", "    if not alt_chunks:\n        raise KonfigFehler(f\"Alter Weg ohne Chunks", "    if False:\n        raise KonfigFehler(f\"Alter Weg ohne Chunks"),
    ("V2 retrieve rechnet mit leeren Embeddings (matmul-Traceback)",
     "rag.py", '    if embs is None or getattr(embs, "ndim", 0) != 2 or len(embs) == 0 or len(embs) != len(chunks):',
     "    if False:"),
    ("V4 Dimensionskonflikt Chunks/Frage laeuft in matmul",
     "rag.py", "    if embs.shape[1] != q.shape[0]:\n        raise KonfigFehler(f\"Embedding-Dimension",
     "    if False:\n        raise KonfigFehler(f\"Embedding-Dimension"),
    ("V3 zu wenige Embeddings von Ollama fallen nicht auf",
     "rag.py", "    if len(texts) and (embs.ndim != 2 or len(embs) != len(texts)):", "    if False:"),
    # ---- Strenge Spielzuordnung, eine Quelle fuer Pipe und CLI (test_zuordnung.py) ----
    ("Z1 Laengenbedingung aus ('Fujian' trifft 'Fuji')",
     "rag.py", "    if laengenregel and _laenge(n, f) < MIN_LAENGENVERHAELTNIS:\n        return 0.0",
     "    if False:\n        return 0.0"),
    ("Z2 Schnelltest verwirft jeden unscharfen Treffer",
     "rag.py", "    if m.real_quick_ratio() < schwelle or m.quick_ratio() < schwelle:",
     "    if m.real_quick_ratio() < schwelle or m.quick_ratio() <= 1.0:"),
    ("Z3 CLI nimmt nur spiel_ids, keine Namen",
     "rag.py", '    status, ergebnis = ordne_spiel(anfrage, katalog)\n    if status == "treffer":\n        return zu_id[ergebnis]',
     '    status, ergebnis = "unbekannt", []'),
    ("Z4 ask --spiel=X wird als Frage gelesen",
     "rag.py", '        if a.startswith("--spiel="):', '        if False:'),
    ("K14 Mehrdeutigkeitsabstand 0.5 (fast jeder Hoerfehler wird abgelehnt)",
     "rag.py", "MEHRDEUTIG_ABSTAND = 0.05", "MEHRDEUTIG_ABSTAND = 0.5"),
    ("K15 Mehrdeutigkeitsabstand 0 (Muenzwurf gewinnt)",
     "rag.py", "MEHRDEUTIG_ABSTAND = 0.05", "MEHRDEUTIG_ABSTAND = 0.0"),
    ("K16 spiel_id zaehlt nicht als Schreibweise",
     "rag.py", '        formen = [s["name"], s["spiel_id"]] + list(s.get("aliase") or [])',
     '        formen = [s["name"]] + list(s.get("aliase") or [])'),
    # ---- Chat, Spec D' (test_chat.py, test_pipe_index.py) ----
    ("DW1 automatische Erkennung von Spielnamen im Freitext wieder an",
     "rag.py", '    return "frage", spiel, letzte, None\n',
     '    if spiel is None:\n'
     '        for w in text(letzte).split():\n'
     '            if chat_norm(w) in wb:\n'
     '                spiel = sorted(wb[chat_norm(w)])[0]\n'
     '                break\n'
     '    return "frage", spiel, letzte, None\n'),
    ("DW2 Fenster wieder da (nur die letzten 20 Nutzer-Nachrichten)",
     "rag.py", '    nutzer = [i for i, m in enumerate(nachrichten) if m.get("role") == "user"]\n    if not nutzer:\n        return "frage", None, None, None',
     '    nutzer = [i for i, m in enumerate(nachrichten) if m.get("role") == "user"][-20:]\n    if not nutzer:\n        return "frage", None, None, None'),
    ("DW3 Namensnachricht ohne Rueckfrage wechselt (letzte Nachricht)",
     "rag.py", "        if nach_rueckfrage(i):\n            namen = antwort_namen(text(i), wb)",
     "        if True:\n            namen = antwort_namen(text(i), wb)"),
    ("KR25 Namensnachricht im Verlauf ohne Rueckfrage setzt das Spiel",
     "rag.py", "    for i in nutzer[:-1]:\n        e = einordnen(i)\n",
     "    for i in nutzer[:-1]:\n        e = einordnen(i) or ((\"wahl\", namens_nachricht(text(i), wb), \"\", \"\")\n"
     "                             if namens_nachricht(text(i), wb) else None)\n"),
    ("KR1 Rueckfrage-Erkennung ohne Rollenpruefung",
     "rag.py", '        c = vorher.get("content") if vorher.get("role") == "assistant" else None',
     '        c = vorher.get("content")'),
    ("KR2 Rueckfrage irgendwo im Text statt am Anfang",
     "rag.py", "isinstance(c, str) and (c.startswith(RUECKFRAGE) or", "isinstance(c, str) and (RUECKFRAGE in c or"),
    ("KR9 STANDARD_SPIEL ungeprueft",
     "openwebui_pipe.py", "                if v.STANDARD_SPIEL not in ids.values():", "                if False:"),
    ("KR12 alter Weg entfernt auch die Quelle-Fusszeile (C)",
     "openwebui_pipe.py", "def zerlege_verlauf(messages, index_weg=False):", "def zerlege_verlauf(messages, index_weg=True):"),
    ("KR13 Listen-Inhalte nicht in Text gewandelt",
     "openwebui_pipe.py", 'als_text = [{"role": m.get("role"), "content": text_von(m.get("content"))} for m in messages]',
     "als_text = messages"),
    ("KR15 Umlaut-Transliteration im Chat weg (auch Aliase)",
     "rag.py", '    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):\n        s = s.replace(alt, neu)\n    return "".join(',
     '    for alt, neu in ():\n        s = s.replace(alt, neu)\n    return "".join('),
    ("W1 unbekannte Wahl antwortet still im alten Spiel (MUSS-1)",
     "rag.py", '    if e[0] == "vorschlag":\n        return "unbekannt", e[1], None, e[2]',
     '    if e[0] == "vorschlag":\n        return "frage", spiel, letzte, None'),
    ("W2 unbekannte Wahl ohne Vorschlaege",
     "openwebui_pipe.py", '            meintest = f" Meintest du {\' oder \'.join(vorschlaege[:3])}?" if vorschlaege else ""',
     '            meintest = ""'),
    ("W3 Stream-Abbruch nennt das Spiel nicht (MUSS-3)",
     "openwebui_pipe.py", '            yield f"\\n\\n---\\n*Quelle: {name} -- Antwort unvollstaendig: {grund}*"\n            return',
     "            raise"),
    ("W4 Wahl nach der Rueckfrage beantwortet die Frage nicht (SOLLTE-4)",
     "rag.py", "    j = letzte\n    while nach_rueckfrage(j):", "    j = letzte\n    while False:"),
    ("W5 Rueckfrage-Kette: Antwort auf eine Rueckfrage gilt als Frage (SOLLTE-5, Runde 7 (d))",
     "rag.py", "        j = k                                   # Antwort/Wahl-Versuch: weiter zurueck",
     "        return \"frage\", namen[0], k, None"),
    ("W6 'Spiel X' ohne Doppelpunkt wieder eine Wahl",
     "rag.py", '_WAHL = re.compile(r"^\\s*(?:spiel\\s*:|wechsel\\s+zu\\s)\\s*(?P<rest>.*)\\Z", re.I | re.S)',
     '_WAHL = re.compile(r"^\\s*(?:spiel\\s*:?|wechsel\\s+zu\\s)\\s*(?P<rest>.*)\\Z", re.I | re.S)'),
    ("W7 heisses Journal ohne klare Meldung",
     "rag.py", '        if "readonly" in str(e) and os.path.exists(pfad + "-journal"):', "        if False:"),
    ("U3 testumgebung biegt judge.ANTHROPIC_KEY_DATEI nicht um",
     "testumgebung.py", 'judge.ANTHROPIC_KEY_DATEI = os.path.join(TMP, "anthropic_api_key")\n', "", ("test_schutz.py",)),
    ("DW4 Fusszeile des Index-Wegs nennt das Spiel nicht",
     "openwebui_pipe.py", "            yield fundstellen_spiel(hits, name)", "            yield fundstellen(hits)"),
    ("DW5 Spiel-Fusszeile auch auf dem alten Weg",
     "openwebui_pipe.py", '        if not rf.get("sprache"):\n            yield fundstellen(hits)',
     '        if not rf.get("sprache"):\n            yield fundstellen_spiel(hits, self.valves.SPIEL)'),
    ("DW6 Fusszeile auch im Sprachmodus (Index-Weg)",
     "openwebui_pipe.py", '        if not rf.get("sprache"):\n            yield fundstellen_spiel(hits, name)',
     '        if True:\n            yield fundstellen_spiel(hits, name)'),
    ("DW7 Rueckfrage ohne Beispiel 'Spiel: X'",
     "openwebui_pipe.py", 'Schreib zum Beispiel „Spiel: {namen[0]}“. Im Index', 'Im Index'),
    ("DW8 'Spiel: X: <Frage>' sucht mit der ganzen Nachricht",
     "openwebui_pipe.py", "            teil = teil[:-1] + [dict(teil[-1], content=frage)]", "            pass"),
    ("DW9 Index-Fusszeile geht in den Verlauf",
     "openwebui_pipe.py", '        text = _FUSSZEILE_INDEX.sub("", text)', "        pass"),
    ("D4 zweite Rueckfrage beantwortet die aelteste statt die juengste Frage",
     "rag.py", "        k = davor[-1]", "        k = davor[0]"),
    ("D5 mehrdeutige Wahl im Verlauf nimmt das erste Spiel",
     "rag.py", '        if e and e[0] == "wahl" and len(e[1]) == 1:', '        if e and e[0] == "wahl" and e[1]:'),
    ("D6 Name endet auch an einem Leerzeichen (nicht nur am Doppelpunkt)",
     "rag.py", '[i for i in range(len(rest) - 1, -1, -1) if rest[i] == ":"]', '[i for i in range(len(rest) - 1, -1, -1) if rest[i] in ": "]'),
    ("D8 'danke' hinter dem Namen nicht erlaubt",
     "rag.py", '_HINTEN = ("bitte", "danke")', '_HINTEN = ("bitte",)'),
    # ---- Deployment-Schutz, URI (test_pipe_index.py, test_pipe_alt.py, test_index.py) ----
    ("DP1 Schnittstellenpruefung des geladenen rag.py aus",
     "openwebui_pipe.py", "        if fehlt or (v.INDEX_PATH and version < MIN_SCHNITTSTELLE):", "        if False:"),
    ("DP2 alter Weg braucht fuer 'kein Regelheft' wieder rag.py",
     "openwebui_pipe.py", "            status, ergebnis = ordne_spiel_valves(",
     "            self._rag_fuer(v)\n            status, ergebnis = ordne_spiel_valves("),
    ("DP3 fehlendes RAG_DIR ohne klare Meldung",
     "openwebui_pipe.py", '        if not os.path.exists(pfad):\n            raise RuntimeError(f"rag.py nicht gefunden',
     '        if False:\n            raise RuntimeError(f"rag.py nicht gefunden'),
    ("UR1 Indexpfad unmaskiert in die file:-URI",
     "rag.py", 'pathlib.Path(os.path.abspath(pfad)).as_uri() + "?mode=ro"', 'f"file:{pfad}?mode=ro"'),
    # ---- Einspiel-Zuordnung = ed36f99 (Kritiker C3/C5), rag.py und Pipe-Kopie ----
    ("C3a Einspiel-Vorschlaege ab 0.6 statt 0.5 (rag.py)",
     "rag.py", '        return "unbekannt", [k for r, k in roh if r >= 0.5]', '        return "unbekannt", [k for r, k in roh if r >= 0.6]'),
    ("C3b Einspiel-Vorschlaege ab 0.6 statt 0.5 (Pipe, alter Weg)",
     "openwebui_pipe.py", '    return "unbekannt", [k for r, k in bewertet if r >= 0.5]', '    return "unbekannt", [k for r, k in bewertet if r >= 0.6]'),
    ("C5a Schwelle 0.85 (rag.py)",
     "rag.py", "def ordne_spiel(anfrage, katalog, schwelle=0.8):", "def ordne_spiel(anfrage, katalog, schwelle=0.85):"),
    ("C5b Schwelle 0.85 (Pipe, alter Weg)",
     "openwebui_pipe.py", "def ordne_spiel_valves(anfrage, katalog, schwelle=0.8):", "def ordne_spiel_valves(anfrage, katalog, schwelle=0.85):"),
    ("P20b alter Weg ohne Unschaerfe",
     "openwebui_pipe.py", '    if bewertet and bewertet[0][0] >= schwelle:\n        return "treffer", bewertet[0][1]\n    return "unbekannt", [k for r, k in bewertet if r >= 0.5]',
     '    if False:\n        return "treffer", bewertet[0][1]\n    return "unbekannt", [k for r, k in bewertet if r >= 0.5]'),
    ("P22b alter Weg: Normalisierung ohne Satzzeichen-Entfernung",
     "openwebui_pipe.py", '    return re.sub(r"[\\W_]+", "", (name or "").casefold())', '    return (name or "").casefold()'),
    ("P23b alter Weg ignoriert SPIEL_ALIASE",
     "openwebui_pipe.py", '    formen = [name] + [a for a in (aliase or "").split(",") if a.strip()]', "    formen = [name]"),
    # ---- Laengenregel/Vorschlaege (test_zuordnung.py) ----
    ("L0 Laengengrenze 0.8 -> 0.7 (Kritiker-M8)",
     "rag.py", "MIN_LAENGENVERHAELTNIS = 0.8", "MIN_LAENGENVERHAELTNIS = 0.7"),
    ("L1 Laengenregel auch bei einem Spiel (ed36f99-Verhalten verletzt)",
     "rag.py", "    mehrere = len(katalog) > 1", "    mehrere = True"),
    ("L2 Laengenregel auch bei mehreren Spielen aus",
     "rag.py", "    mehrere = len(katalog) > 1", "    mehrere = len(katalog) > 1000"),
    ("L3 Vorschlaege mit Laenge >= 0.6 (Fujian schlaegt Fuji vor)",
     "rag.py", "VORSCHLAG_RATIO, VORSCHLAG_LAENGE = 0.6, 0.7", "VORSCHLAG_RATIO, VORSCHLAG_LAENGE = 0.6, 0.6"),

    ("K7 Pipe-Cache-Schluessel ohne CHUNK_SIZE",
     "openwebui_pipe.py", "               v.DROP_TYPES, v.EMBED_MODEL, v.CHUNK_SIZE, v.CHUNK_OVERLAP)",
     "               v.DROP_TYPES, v.EMBED_MODEL, v.CHUNK_OVERLAP)"),
    ("K18 fehlender Stand wird als 'veraltet' diagnostiziert",
     "openwebui_pipe.py", "            if stand and stand[0] != rag.fingerprint(wissen, konfig):",
     "            if stand is None or stand[0] != rag.fingerprint(wissen, konfig):"),
    ("K19 BM25-Gleichstand rowid absteigend",
     "rag.py", "ORDER BY bm25(chunks_fts, 1.0, 0.0), rowid LIMIT ?", "ORDER BY bm25(chunks_fts, 1.0, 0.0), rowid DESC LIMIT ?"),
    ("B1 BM25-Abfrage mit casefold (ß -> ss, findet 'Straße' nicht)",
     "rag.py", '    woerter = re.findall(r"\\w+", query.lower())', '    woerter = re.findall(r"\\w+", query.casefold())'),
    ("B2 WAL-Index wird nicht erkannt",
     "rag.py", "    if len(kopf) == 20 and kopf[18] == 2 and kopf[19] == 2:", "    if False:"),
    ("I1 ein kaputtes Spiel bricht index --alle ab",
     "rag.py", "                if len(spiel_ids) == 1 and not alle:\n                    raise",
     "                if True:\n                    raise"),
    ("I2 Fehler einzelner Spiele werden verschluckt (Exit 0)",
     "rag.py", "        if fehler:\n            e = KonfigFehler(", "        if False:\n            e = KonfigFehler("),
    ("S11 Slug ohne NFKD (Café -> caf)",
     "rag.py", '    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))\n', ""),
    ("S12 Slug-Kollision zweier Namen wird still zusammengelegt",
     "rag.py", "        if name and normalisiere(name) != normalisiere(meta[\"name\"]):", "        if False:"),
    ("S13 auto_ingest --spiel ueberschreibt ungefragt",
     "auto_ingest.py", "    if os.path.exists(ziel_pfad) and not ueberschreiben:", "    if False:"),
    ("S14 ingest.py --spiel ueberschreibt ungefragt",
     "ingest.py", "    if os.path.exists(ziel_pfad) and not ueberschreiben:", "    if False:"),
    # ---- Schutz echter Daten (test_schutz.py; fuenftes Feld = nur diese Testdateien) ----
    ("A1 Mutationstreiber arbeitet im Arbeitsverzeichnis statt in einer Kopie",
     "test_mutationen.py", '    ziel = tempfile.mkdtemp(prefix="rag-mutationen-")\n',
     '    return BASE\n    ziel = tempfile.mkdtemp(prefix="rag-mutationen-")\n', ("test_schutz.py",)),
    ("U1 testumgebung biegt classify.KNOW nicht um",
     "testumgebung.py", 'classify.KNOW = os.path.join(TMP, "knowledge.jsonl")\n', "", ("test_schutz.py",)),
    ("U2 testumgebung biegt vision_ingest.KNOW nicht um",
     "testumgebung.py", 'vision_ingest.KNOW = os.path.join(TMP, "knowledge.jsonl")\n', "", ("test_schutz.py",)),
    ("Y1 Schreiben durch Symlinks wieder erlaubt",
     "rag.py", "    if os.path.islink(pfad):\n        raise KonfigFehler(", "    if False:\n        raise KonfigFehler(",
     ("test_schutz.py",)),
    ("Y2 classify.py prueft das Schreibziel nicht",
     "classify.py", "    rag.pruefe_schreibziel(KNOW)", "    pass", ("test_schutz.py",)),
    ("Y3 vision_ingest.py prueft das Schreibziel nicht",
     "vision_ingest.py", "    with open(rag.pruefe_schreibziel(know), \"w\"", "    with open(know, \"w\"", ("test_schutz.py",)),
    ("Y4 ingest.py prueft das Schreibziel nicht",
     "ingest.py", "    with open(rag.pruefe_schreibziel(out), \"w\"", "    with open(out, \"w\"", ("test_schutz.py",)),
    ("Q1 alter Eval-Weg ignoriert KNOWLEDGE_JSONL",
     "rag.py", 'with open(os.environ.get("KNOWLEDGE_JSONL") or os.path.join(os.path.dirname(__file__), "knowledge.jsonl")) as kf:',
     'with open(os.path.join(os.path.dirname(__file__), "knowledge.jsonl")) as kf:'),
    ("Q2 vergleiche ignoriert KNOWLEDGE_JSONL",
     "rag.py", '    quelle = os.environ.get("KNOWLEDGE_JSONL") or os.path.join(',
     '    quelle = None or os.path.join('),
    ("R6 Migration ueberschreibt eine abweichende Datei",
     "rag.py", "        raise KonfigFehler(f\"{pfad} existiert schon mit anderem Inhalt", "        if False: raise KonfigFehler(f\"{pfad} existiert schon mit anderem Inhalt"),
    # ---- Runde 7: Antwort auf die Rueckfrage (D-Rueckfrage), HOME, judge, Migration, Fingerprint ----
    ("DR1 Formen (a) nach der Rueckfrage aus ('fuer X', 'bei X', 'Spiel X', 'Das Spiel heisst X')",
     "rag.py", '    m = _ANTWORT.match(text or "")\n', "    m = None\n"),
    ("DR2 (b) aus: ungenauer Name nach der Rueckfrage gilt als neue Frage",
     "rag.py", "            if vorschlaege:                     # (b)", "            if False:                           # (b)"),
    ("DR3 (c) aus: jede Antwort auf die Rueckfrage ist ein Wahl-Versuch",
     "rag.py", "            if vorschlaege:                     # (b)", "            if True:                            # (b)"),
    ("DR4 KEIN_REGELHEFT-Meldung zaehlt nicht als Rueckfrage",
     "rag.py", "(c.startswith(RUECKFRAGE) or c.startswith(KEIN_REGELHEFT))", "(c.startswith(RUECKFRAGE))"),
    ("DR5 Pipe-Meldung beginnt nicht mit KEIN_REGELHEFT",
     "openwebui_pipe.py", '(f"{rag.KEIN_REGELHEFT}{erg}“ im Index.', '(f"Zu „{erg}“ kein Regelheft im Index.'),
    ("DR6 Vorschlag: Name als ganze Woerter im Text nicht erkannt",
     "rag.py", '                    gefunden |= wb.get("".join(woerter[i:j]), set())', "                    pass"),
    ("DR7 Vorschlag: Stueck eines Namens nicht erkannt ('Food Chain')",
     "rag.py", "            if s in form:", "            if s == form:"),
    ("DR8 Vorschlag auch bei Fragen ('Wer beginnt bei Azul?' wuerde die neue Frage verlieren)",
     "rag.py", '    if "?" not in ohne:', "    if True:"),
    ("DR9 Vorschlag: beliebig viele Woerter neben dem Namen",
     "rag.py", "                if len(woerter) - (j - i) <= _VORSCHLAG_EXTRA_WOERTER:", "                if True:"),
    ("DR10 Hoeflichkeit vor dem Doppelpunkt nicht abgetrennt (SOLLTE-5)",
     "rag.py", "        kandidat = _ohne_hoeflichkeit(rest[:pos])\n",
     "        kandidat = _ohne_hoeflichkeit(rest[:pos]) if pos == len(rest) else rest[:pos]\n"),
    ("DR11 Embedding-Ausfall: Meldung ohne Spiel (SOLLTE-4)",
     "openwebui_pipe.py", '            yield f"**Fehler in der RAG-Pipe:** {grund}\\n\\n---\\n*Quelle: {name} -- keine Antwort*"\n            return\n',
     "            raise\n"),
    ("DR12 Kette: reine Namensnachricht ohne Rueckfrage gilt als Frage",
     "rag.py", '            ek = ("name",)', "            ek = None"),
    ("U4 testumgebung lenkt HOME nicht um",
     "testumgebung.py", 'os.environ["HOME"] = HOME\nos.environ["XDG_CONFIG_HOME"] = os.path.join(HOME, ".config")\n', "",
     ("test_schutz.py",)),
    ("U5 Mutationstreiber lenkt HOME nicht um",
     "test_mutationen.py", "                    HOME=home, XDG_CONFIG_HOME=os.path.join(home, \".config\"))\n", "                    )\n",
     ("test_schutz.py",)),
    ("J1 judge: Key-Pfad als Default-Argument (Kritiker)", "judge.py",
     "def lies_anthropic_key(pfad=None):\n    pfad = pfad or ANTHROPIC_KEY_DATEI",
     "def lies_anthropic_key(pfad=ANTHROPIC_KEY_DATEI):\n    pfad = pfad", ("test_judge.py", "test_schutz.py")),
    ("J2 judge: Netzfehler-Meldung enthaelt die Header (Key-Leak)", "judge.py",
     'raise JudgeAbbruch(f"Netzfehler bei {url}: {type(e).__name__}") from None',
     'raise JudgeAbbruch(f"Netzfehler bei {url}: {type(e).__name__} {kw}") from None', ("test_judge.py",)),
    ("J3 judge: HTTP-Fehler-Meldung enthaelt die Header", "judge.py",
     'raise JudgeAbbruch(f"{url} antwortet {r.status_code}: {r.text[:300]}")',
     'raise JudgeAbbruch(f"{url} antwortet {r.status_code}: {r.text[:300]} {kw.get(\'headers\')}")', ("test_judge.py",)),
    ("J4 judge: Key aus der Umgebung statt aus der Datei", "judge.py",
     "    pfad = pfad or ANTHROPIC_KEY_DATEI\n",
     "    if os.environ.get('ANTHROPIC_API_KEY'): return os.environ['ANTHROPIC_API_KEY']\n    pfad = pfad or ANTHROPIC_KEY_DATEI\n",
     ("test_judge.py",)),
    ("KI1 Fingerprint nur erste 1 KiB (Kritiker I1)", "rag.py",
     '        for block in iter(lambda: f.read(1 << 20), b""):\n            h.update(block)', '        h.update(f.read(1024))',
     ("test_index.py",)),
    ("KI2 Fingerprint ohne Konfiguration (Kritiker I2)", "rag.py", '    h.update(b"\\0" + konfig.encode())', '    pass',
     ("test_index.py",)),
    ("MG1 Migration: fremde spiel_id erlaubt (Kritiker)", "rag.py",
     "    if fremd:\n        raise KonfigFehler(f\"{quelle} enthaelt Chunks anderer Spiele",
     "    if False:\n        raise KonfigFehler(f\"{quelle} enthaelt Chunks anderer Spiele", ("test_regression.py",)),
    ("MG3 Migration: fremdes Golden Set akzeptiert (Kritiker)", "rag.py",
     '        if gs.get("spiel_id") not in (None, spiel_id):\n            raise', '        if False:\n            raise',
     ("test_regression.py",)),
]


def rote_tests(lauf, tests=TESTS):
    rot = []
    # HOME/XDG_CONFIG_HOME in die Laufkopie: auch unter einer Mutation, die testumgebung
    # umgeht, gibt es dort keinen echten Key (~/.config/anthropic/api_key) zu lesen
    home = os.path.join(lauf, "home")
    os.makedirs(os.path.join(home, ".config"), exist_ok=True)
    umgebung = dict(os.environ, DATA_DIR=os.path.join(lauf, "data"),
                    INDEX_PATH=os.path.join(lauf, "data", "index.sqlite"),
                    HOME=home, XDG_CONFIG_HOME=os.path.join(home, ".config"))
    umgebung.setdefault("PYTHONUSERBASE", site.getuserbase())
    for k in ("KNOWLEDGE_JSONL", "GOLDEN_SET", "REGRESSION_REFERENZ"):
        umgebung.pop(k, None)
    for datei in tests:
        p = subprocess.run([sys.executable, os.path.join(lauf, datei)],
                           cwd=lauf, env=umgebung, capture_output=True, text=True)
        if p.returncode == 0:
            continue
        namen = [z.split(" ")[1] for z in p.stderr.splitlines()
                 if z.startswith(("FAIL:", "ERROR:"))]
        rot += [f"{datei}::{n}" for n in namen] or [f"{datei}::(Abbruch)"]
    return rot


def ausgewaehlt():
    """NUR=F,S3 python test_mutationen.py -- nur Mutationen mit diesen Praefixen (Default: alle)."""
    praefixe = [p.strip() for p in os.environ.get("NUR", "").split(",") if p.strip()]
    if not praefixe:
        return MUTATIONEN
    return [m for m in MUTATIONEN
            if any(m[0].replace("[gleich] ", "").startswith(p) for p in praefixe)]


def main():
    unerwartet_gruen = []
    auswahl = ausgewaehlt()
    lauf = laufkopie()
    try:
        return _mutiere(auswahl, lauf, unerwartet_gruen)
    finally:
        # nie das Arbeitsverzeichnis loeschen -- auch nicht unter einer Mutation von laufkopie()
        if os.path.realpath(lauf) != os.path.realpath(BASE):
            shutil.rmtree(lauf, ignore_errors=True)


def _mutiere(auswahl, lauf, unerwartet_gruen):
    for name, datei, alt, neu, *nur_tests in auswahl:
        pfad = os.path.join(lauf, datei)
        orig = io.open(pfad, encoding="utf-8").read()
        if alt not in orig:
            print(f"[FEHLT] {name}: Muster nicht mehr in {datei} -- Mutation nachziehen")
            unerwartet_gruen.append(name)
            continue
        try:
            io.open(pfad, "w", encoding="utf-8").write(orig.replace(alt, neu, 1))
            rot = rote_tests(lauf, nur_tests[0] if nur_tests else TESTS)
        finally:
            io.open(pfad, "w", encoding="utf-8").write(orig)
        print(f"[{'ROT  ' if rot else 'GRUEN'}] {name}")
        for r in rot:
            print(f"         {r}")
        if not rot and not name.startswith("[gleich]"):
            unerwartet_gruen.append(name)

    print()
    if unerwartet_gruen:
        print(f"{len(unerwartet_gruen)} Mutation(en) ohne roten Test -- da fehlt ein Test:")
        for n in unerwartet_gruen:
            print(f"  {n}")
        return 1
    print(f"{len(auswahl)} Mutationen geprueft, alle erwartungsgemaess.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
