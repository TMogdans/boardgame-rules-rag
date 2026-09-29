#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spiel im Chat (rag.spiel_im_chat) -- abgenommene Regeln (Tobias):

  - Das Spiel des Chats ist das erste, das in einer Nutzer-Nachricht EXAKT genannt
    wird (Name oder Alias als ganze Wortfolge; Gross/Klein, Umlaut-/ss-Schreibung,
    Satzzeichen, Bindestriche egal). Keine Unschaerfe im Chat. Enthaelt ein Treffer
    einen anderen, gilt der laengere; zwei unabhaengige -> Rueckfrage.
  - Gewechselt wird NUR explizit: Namensnachricht (auch "Spiel: X", "Wechsel zu X",
    "X bitte", "Bei X.", "Fuer X") oder "Zu X: <Frage>". Ein Name in einer spaeteren
    Frage wechselt nicht.
  - Namensnachricht als Antwort auf die Rueckfrage -> die Frage davor wird
    beantwortet; sonst nur Bestaetigung.

    python test_chat.py

Katalog und Fragen stammen vom Kritiker (kritik-index-2/exp: katalog.py, fp.py,
satz.py, e2e.py).
"""
import os
import sys
import time
import unittest

import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402

SPIELE = [
    ("Food Chain Magnate", ["Food Chain", "FCM"]),
    ("Go", []), ("Root", []), ("Azul", []), ("Fuji", []), ("Hive", []),
    ("Arche Nova", ["Ark Nova"]), ("7 Wonders", ["Sieben Wunder"]), ("7 Wonders Duel", ["Duel"]),
    ("Terraforming Mars", ["TM", "Terraforming"]), ("Flügelschlag", ["Wingspan"]),
    ("Brass: Birmingham", ["Brass"]), ("Brass: Lancashire", []),
    ("Die Siedler von Catan", ["Catan", "Siedler"]), ("Carcassonne", []), ("Agricola", []),
    ("Codenames", ["Codenames"]), ("Dominion", []), ("Everdell", []), ("Gloomhaven", []),
    ("Spirit Island", []), ("Scythe", []), ("Twilight Imperium", ["TI4"]), ("Cascadia", []),
    ("Heat", ["Heat: Pedal to the Metal"]), ("Kingdomino", []), ("Patchwork", []),
    ("Die Crew", ["The Crew"]), ("Great Western Trail", ["GWT"]), ("Concordia", []),
    ("Paleo", []), ("Hanabi", []), ("Mysterium", []), ("Istanbul", []),
]
KATALOG, IDS = rag.katalog_aus_index([{"spiel_id": rag.spiel_slug(n), "name": n, "aliase": a} for n, a in SPIELE])
WB = rag.chat_woerterbuch(KATALOG)

# fp.py: 50 gewoehnliche Regelfragen -- viele enthalten Spielnamen als Wort
FRAGEN = ["Wie gehe ich an die Wurzel (root) des Baums?", "Was passiert in der Go-Phase?", "Wann darf ich go sagen?",
          "Wie viele Spieler dürfen mitspielen?", "Was kostet eine Ware?", "Darf ich in meiner Runde zweimal bauen?",
          "Wie funktioniert die Wertung am Spielende?", "Was passiert bei Gleichstand?", "Wie viele Karten ziehe ich?",
          "Wer beginnt das Spiel?", "Kann ich meine Route ändern?", "Wie weit fährt die Crew?",
          "Was bringt die Hitze (heat)?", "Wie baue ich einen Bienenstock (hive)?",
          "Welche Farbe hat das blaue Plättchen (azul)?", "Darf ich den Berg Fuji besteigen?",
          "Was ist ein Duell?", "Was mache ich im Duel?", "Wie lege ich ein Domino an?", "Was zählt als Patchwork?",
          "Wie viele Wunder kann ich bauen?", "Ist das ein Code Name?", "Gibt es eine Arche?",
          "Wann ist Concorde erlaubt?", "Wie funktioniert Handel mit den Nachbarn?",
          "Wer hat die Mehrheit im Mars-Gebiet?", "Wie heißt die Phase nach dem Essen?", "Kann ich Rohstoffe tauschen?",
          "Was ist ein Siedler?", "Wie bewege ich die Siedler?", "Was mache ich mit der Sense (scythe)?",
          "Kann man eine Insel (island) verlassen?", "Wo ist der Trail?", "Darf ich in den Hafen (haven)?",
          "Was macht der Magnat?", "Wieviel Geld gibt es in Phase 4?", "Was bedeutet Heat im Rennen?",
          "Wie spiele ich die Karte Root aus?", "Muss ich 7 Karten auf der Hand haben?", "Wie funktioniert Go?",
          "Und bei zwei Spielern?", "Was ist mit Hive-Steinen?", "Kann ich mit dem Truck Driver fahren?",
          "Wer darf zuerst?", "Gilt das auch für Heißluftballons?", "Darf ich passen?",
          "Was passiert, wenn der Stapel leer ist?", "Wie viele Punkte bringt ein Kloster?",
          "Wie viele Punkte gibt die Straße?", "Darf ich Arbeiter wieder einsetzen?"]


def U(t):
    return {"role": "user", "content": t}


def A(t):
    return {"role": "assistant", "content": t}


def chat(*wechsel):
    return [U(t) if i % 2 == 0 else A(t) for i, t in enumerate(wechsel)]


class TestErsteNennung(unittest.TestCase):
    def test_saetze_des_kritikers(self):
        for satz, soll in (("Wie funktioniert bei 7 Wonders die Wertung?", ["7 Wonders"]),
                           ("Wie läuft bei 7 Wonders der Handel?", ["7 Wonders"]),
                           ("7 Wonders: dürfen Nachbarn tauschen?", ["7 Wonders"]),
                           ("Bei Root die Vögel: wie bauen die?", ["Root"]),
                           ("Wie spielt man Azul mit zwei Spielern?", ["Azul"]),
                           ("Bei Brass Birmingham die Kanalphase?", ["Brass: Birmingham"]),
                           ("Bei Arche Nova die Pausekarte?", ["Arche Nova"]),
                           ("Bei Fuji die Würfel?", ["Fuji"]),
                           ("Was passiert in der Go-Phase bei Terraforming Mars?", ["Terraforming Mars"])):
            with self.subTest(satz=satz):
                self.assertEqual(rag.exakte_nennungen(satz, WB), soll)

    def test_laengerer_treffer_enthaelt_kuerzeren(self):
        self.assertEqual(rag.exakte_nennungen("Wie geht bei 7 Wonders Duel die Wertung?", WB), ["7 Wonders Duel"])
        self.assertEqual(rag.exakte_nennungen("Wie geht 7 Wonders die Wertung?", WB), ["7 Wonders"])

    def test_zwei_unabhaengige_sind_mehrdeutig(self):
        self.assertEqual(rag.exakte_nennungen("Ist Carcassonne leichter als Agricola?", WB), ["Agricola", "Carcassonne"])
        self.assertEqual(rag.spiel_im_chat(chat("Ist Carcassonne leichter als Agricola?"), WB)[0], "mehrdeutig")

    def test_schreibweisen(self):
        for satz in ("Wie fliegt man bei Flügelschlag?", "Wie fliegt man bei Fluegelschlag?",
                     "Wie fliegt man bei FLÜGEL-SCHLAG?", "Wie fliegt man bei flügelschlag!"):
            with self.subTest(satz=satz):
                self.assertEqual(rag.exakte_nennungen(satz, WB), ["Flügelschlag"])
        self.assertEqual(rag.exakte_nennungen("Food-Chain-Magnate: was kostet Bier?", WB), ["Food Chain Magnate"])

    def test_keine_unschaerfe_im_chat(self):
        for satz in ("Wie geht Fudschein Magnat?", "Wie spielt man Fujian?", "Carcasonne Kloster?", "Carcasonne"):
            with self.subTest(satz=satz):
                self.assertEqual(rag.exakte_nennungen(satz, WB), [])
                self.assertEqual(rag.spiel_im_chat(chat(satz), WB), ("frage", None, 0))


class TestLaufenderChat(unittest.TestCase):
    def test_fp_keine_faelschlichen_wechsel(self):
        # fp.py: 50 Regelfragen im laufenden Carcassonne-Chat -> 0 Wechsel
        falsch = []
        for q in FRAGEN:
            erg = rag.spiel_im_chat(chat("Carcassonne: Wie viele Punkte bringt ein Kloster?", "5 Punkte.", q), WB)
            if erg != ("frage", "Carcassonne", 2):
                falsch.append((q, erg))
        self.assertEqual(falsch, [])

    def test_name_in_spaeterer_frage_wechselt_nicht(self):
        # auch nicht, wenn die Nennung in einer mittleren Nachricht steht
        self.assertEqual(rag.spiel_im_chat(chat("Carcassonne: Kloster?", "5", "Und bei Agricola?", "...",
                                                "Wie viele Punkte?"), WB), ("frage", "Carcassonne", 4))
        for q in ("Und wie ist das bei Agricola?", "Und bei zwei Spielern?", "Was ist mit Brass?",
                  "Wie läuft das bei Agricola und Catan?"):
            with self.subTest(q=q):
                self.assertEqual(rag.spiel_im_chat(chat("Carcassonne: Kloster?", "5", q), WB),
                                 ("frage", "Carcassonne", 2))

    def test_explizite_wechsel(self):
        for q in ("Agricola", "Spiel: Agricola", "Spiel Agricola", "Wechsel zu Agricola", "Wechsle zu Agricola",
                  "zu Agricola", "Agricola bitte", "Bei Agricola.", "Für Agricola", "agricola!"):
            with self.subTest(q=q):
                self.assertEqual(rag.spiel_im_chat(chat("Carcassonne: Kloster?", "5", q), WB),
                                 ("gewechselt", "Agricola", None))
        for q in ("Zu Agricola: wie viele Felder?", "Spiel: Agricola: wie viele Felder?",
                  "Wechsel zu Agricola: wie viele Felder?"):
            with self.subTest(q=q):
                self.assertEqual(rag.spiel_im_chat(chat("Carcassonne: Kloster?", "5", q), WB),
                                 ("frage", "Agricola", 2))
        # nach dem Wechsel gilt das neue Spiel fuer Folgefragen
        self.assertEqual(rag.spiel_im_chat(chat("Carcassonne: Kloster?", "5", "Agricola", "Ok, ab jetzt Agricola.",
                                                "Wie viele Felder?"), WB), ("frage", "Agricola", 4))

    def test_nur_die_letzten_20_nutzer_nachrichten(self):
        verlauf = ["Carcassonne: Kloster?", "5"]
        for i in range(20):
            verlauf += [f"Frage {i}?", "Antwort."]
        verlauf.append("Und noch eine Frage?")
        self.assertEqual(rag.spiel_im_chat(chat(*verlauf), WB)[1], None)       # Nennung liegt vor dem Fenster
        self.assertEqual(rag.spiel_im_chat(chat(*verlauf[2:]), WB)[1], None)
        self.assertEqual(rag.spiel_im_chat(chat(*verlauf[4:]), WB)[1], None)
        kurz = ["Carcassonne: Kloster?", "5"] + ["x?", "y."] * 18 + ["Und?"]
        self.assertEqual(rag.spiel_im_chat(chat(*kurz), WB)[1], "Carcassonne")  # 20 Nutzer-Nachrichten: noch drin


class TestRueckfrage(unittest.TestCase):
    R = rag.RUECKFRAGE + " Im Index: 34 Spiele."

    def test_antwort_auf_rueckfrage_beantwortet_die_frage(self):
        for antwort in ("Carcassonne", "Carcassonne bitte", "Bei Carcassonne.", "Für Carcassonne", "Spiel: Carcassonne"):
            with self.subTest(antwort=antwort):
                self.assertEqual(rag.spiel_im_chat(chat("Wie viele Punkte bringt ein Kloster?", self.R, antwort), WB),
                                 ("frage", "Carcassonne", 0))

    def test_name_nach_beantworteter_frage_nur_bestaetigung(self):
        # MUSS-2: wiederholt NICHT die alte Frage im neuen Spiel
        v = chat("Wie viele Punkte bringt ein Kloster?", self.R, "Carcassonne", "5 Punkte.", "Agricola")
        self.assertEqual(rag.spiel_im_chat(v, WB), ("gewechselt", "Agricola", None))

    def test_namensnachricht_vor_der_rueckfrage_ist_keine_frage(self):
        k, _ = rag.katalog_aus_index([{"spiel_id": "brass-birmingham", "name": "Brass: Birmingham", "aliase": ["Brass"]},
                                      {"spiel_id": "brass-lancashire", "name": "Brass: Lancashire", "aliase": ["Brass"]}])
        wb = rag.chat_woerterbuch(k)
        self.assertEqual(rag.spiel_im_chat(chat("Brass"), wb)[0], "mehrdeutig")
        v = chat("Brass", rag.RUECKFRAGE + " Meintest du Brass: Birmingham oder Brass: Lancashire?", "Brass Birmingham")
        self.assertEqual(rag.spiel_im_chat(v, wb), ("gewechselt", "Brass: Birmingham", None))

    def test_ohne_rueckfrage_davor_ist_name_ein_wechsel(self):
        self.assertEqual(rag.spiel_im_chat(chat("Carcassonne"), WB), ("gewechselt", "Carcassonne", None))
        self.assertEqual(rag.spiel_im_chat(chat("Wie viele Punkte?", "Keine Angaben.", "Carcassonne"), WB),
                         ("gewechselt", "Carcassonne", None))


class TestLaufzeit(unittest.TestCase):
    def test_250_spiele_200_nachrichten(self):
        spiele = [{"spiel_id": f"s{i}", "name": f"Spiel Nummer {i} Deluxe Edition", "aliase": [f"SN{i}"]}
                  for i in range(250)]
        wb = rag.chat_woerterbuch(rag.katalog_aus_index(spiele)[0])
        satz = ("Wie viel Geld bekomme ich eigentlich in der dritten Runde wenn ich vorher zwei Karten "
                "gespielt habe und der Marker auf dem Feld neben der Stadt liegt oder nicht")
        verlauf = chat(*([satz, "Antwort."] * 100 + [satz]))
        zeiten = []
        for _ in range(5):
            t = time.perf_counter()
            rag.spiel_im_chat(verlauf, wb)
            zeiten.append(time.perf_counter() - t)
        self.assertLess(max(zeiten), 0.05, f"max {max(zeiten)*1000:.1f} ms")


if __name__ == "__main__":
    unittest.main(verbosity=2)
