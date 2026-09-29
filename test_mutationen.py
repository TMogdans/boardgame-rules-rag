#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mutationsprobe: verfaelscht die Implementierung gezielt und prueft, dass ein
Test rot wird. Ein gruener Testlauf beweist nichts, solange nicht gezeigt ist,
dass die Tests ueberhaupt etwas festhalten.

    python test_mutationen.py

Jede Mutation wird eingespielt, die Tests aus TESTS laufen, dann wird die Datei aus dem Speicher zurueckgeschrieben (finally).
Exit-Code 1, wenn eine Mutation gruen bleibt, deren Namen nicht mit "[gleich]"
beginnt -- solche sind nachweislich verhaltensgleich, siehe M3.
"""
import io
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
TESTS = ("test_classify.py", "test_ingest_seite.py", "test_wertung.py", "test_openwebui_pipe.py",
         "test_spiele.py", "test_index.py", "test_suche.py", "test_eval_spiele.py",
         "test_pipe_index.py", "test_regression.py", "test_zuordnung.py")

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
     "openwebui_pipe.py", '"content": ohne_fusszeile(text_von(m.get("content")))', '"content": text_von(m.get("content"))'),
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
     "rag.py", "def ordne_spiel(anfrage, katalog, schwelle=0.8,", "def ordne_spiel(anfrage, katalog, schwelle=0.1,"),
    ("P22 Normalisierung ignoriert Leerzeichen/Satzzeichen nicht",
     "rag.py", 'return re.sub(r"[\\W_]+", "", (name or "").casefold())', 'return (name or "").casefold()'),
    ("P23 Aliase aus den Valves werden ignoriert",
     "rag.py", '    formen = [name] + [a for a in (aliase or "").split(",") if a.strip()]', '    formen = [name]'),
    ("P24 Sprachmodus behaelt die Fusszeile",
     "openwebui_pipe.py", '        if not rf.get("sprache"):\n            yield fundstellen(hits)', '        yield fundstellen(hits)'),
    ("P25 Vorschlaege werden nicht genannt",
     "rag.py", '    return "unbekannt", [k for r, k in roh if r >= 0.5]', '    return "unbekannt", []'),
    ("P26 Katalog kommt nicht aus den Valves",
     "openwebui_pipe.py", "rag.ordne_spiel(rf[\"spiel\"], rag.katalog_aus(v.SPIEL, v.SPIEL_ALIASE))", "rag.ordne_spiel(rf[\"spiel\"], rag.katalog_aus(\"Food Chain Magnate\", \"Food Chain, FCM\"))"),

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
     "rag.py", "    order = np.argsort(-sims)[:k]\n", "    order = np.lexsort((-np.arange(len(sims)), -sims))[:k]\n"),
    ("K3 Gleichstand kippt nur im Index-Weg",
     "rag.py", "    order = np.argsort(-sims)[:k]\n",
     "    order = np.argsort(-sims)[:k] if spiel_id is None else np.lexsort((-np.arange(len(sims)), -sims))[:k]\n"),
    # ---- Strenge Spielzuordnung, eine Quelle fuer Pipe und CLI (test_zuordnung.py) ----
    ("Z1 Laengenbedingung aus ('Fujian' trifft 'Fuji')",
     "rag.py", "    if min(len(n), len(f)) < MIN_LAENGENVERHAELTNIS * max(len(n), len(f)):\n        return 0.0",
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
    # ---- Chat: Spiel aus dem Verlauf (test_pipe_index.py TestChatVerlauf) ----
    ("C1 Antwort auf die Rueckfrage (nur Spielname) wird selbst zur Frage",
     "openwebui_pipe.py", "            return ids[name], messages[:davor[-1] + 1], None", "            return ids[name], messages, None"),
    ("C2 aelteste statt neueste Nennung gilt (kein Spielwechsel)",
     "openwebui_pipe.py", "        for i in reversed(nutzer):", "        for i in nutzer:"),
    ("C3 Teilfolgen verdraengen nicht (Brass in Brass Birmingham macht mehrdeutig)",
     "rag.py", "    offen = [s for s in spannen\n             if not any(",
     "    offen = spannen\n    _ = [s for s in spannen\n             if not any("),
    ("C4 mehrdeutige Nennung: das erste Spiel gewinnt",
     "openwebui_pipe.py", "            if genannt:\n                return None, messages,",
     "            if genannt:\n                return ids[genannt[0]], messages[:frage_idx + 1], None\n                return None, messages,"),
    ("C5 Verlauf wird nie nach Spielen durchsucht",
     "openwebui_pipe.py", "        for i in reversed(nutzer):", "        for i in []:"),
    ("C6 Spielnamen nur als ganze Nachricht, nicht im Satz",
     "rag.py", "        for j in range(i + 1, min(len(woerter), i + max_woerter) + 1):",
     "        for j in range(len(woerter) + 1, len(woerter) + 1):"),
    # ---- Testluecken aus dem Review ----
    ("K7 Pipe-Cache-Schluessel ohne CHUNK_SIZE",
     "openwebui_pipe.py", "               v.DROP_TYPES, v.EMBED_MODEL, v.CHUNK_SIZE, v.CHUNK_OVERLAP)",
     "               v.DROP_TYPES, v.EMBED_MODEL, v.CHUNK_OVERLAP)"),
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
    ("R6 Migration ueberschreibt eine abweichende Datei",
     "rag.py", "        raise KonfigFehler(f\"{pfad} existiert schon mit anderem Inhalt", "        if False: raise KonfigFehler(f\"{pfad} existiert schon mit anderem Inhalt"),
]


def rote_tests():
    rot = []
    for datei in TESTS:
        p = subprocess.run([sys.executable, os.path.join(BASE, datei)],
                           cwd=BASE, capture_output=True, text=True)
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
    for name, datei, alt, neu in auswahl:
        pfad = os.path.join(BASE, datei)
        orig = io.open(pfad, encoding="utf-8").read()
        if alt not in orig:
            print(f"[FEHLT] {name}: Muster nicht mehr in {datei} -- Mutation nachziehen")
            unerwartet_gruen.append(name)
            continue
        try:
            io.open(pfad, "w", encoding="utf-8").write(orig.replace(alt, neu, 1))
            rot = rote_tests()
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
