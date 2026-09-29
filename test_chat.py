#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spiel im Chat (rag.spiel_im_chat) -- abgenommene Spec D' (Tobias):

  Das Spiel wird NUR explizit gewaehlt:
    (a) "Spiel: X", "Spiel X", "Wechsel zu X" -- optional mit ": <Frage>" dahinter
    (b) nur der Spielname (ggf. "bitte"/"danke") DIREKT als Antwort auf unsere
        Rueckfrage -> die urspruengliche Frage wird beantwortet
  X exakt (Name oder Alias, chat_norm). Die Wahl gilt fuer den ganzen Chat bis zur
  naechsten Wahl, ohne Fenster. KEINE Erkennung von Spielnamen im Freitext -- auch
  nicht in der ersten Nachricht. Eine reine Namensnachricht ohne Rueckfrage ist eine
  gewoehnliche Frage im aktuellen Spiel.

    python test_chat.py

Katalog (52 Titel) und die 100 Folgefragen stammen vom dritten Kritiker
(kritik-index-3/exp: katalog.py, fragen.py); gemessen hatte er beim vorigen Stand
59/100 Festlegungen aus der ersten Frage, ~43 davon falsch.
"""
import time
import unittest

import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import rag  # noqa: E402

SPIELE = [
 ("Food Chain Magnate", ["FCM", "Food Chain"]), ("Die Crew", ["The Crew", "Crew"]), ("Root", []), ("Go", []),
 ("Die Siedler von Catan", ["Siedler", "Catan"]), ("Hive", []), ("Azul", []), ("Everdell", []),
 ("Flügelschlag", ["Wingspan"]), ("Brass: Birmingham", ["Brass"]), ("Brass: Lancashire", []),
 ("7 Wonders", []), ("7 Wonders: Duel", ["Duel"]), ("Café International", []), ("Die Burgen von Burgund", ["Burgen von Burgund"]),
 ("Burgund", []), ("Carcassonne", []), ("Agricola", []), ("Dominion", []), ("Spirit Island", []),
 ("Scythe", []), ("Terraforming Mars", ["Terraforming"]), ("Arche Nova", ["Ark Nova"]), ("Cascadia", []),
 ("Heat", []), ("Kingdomino", []), ("Patchwork", []), ("Concordia", []), ("Hanabi", []), ("Istanbul", []),
 ("Paleo", []), ("Mysterium", []), ("Codenames", []), ("Just One", []), ("Wizard", []), ("Skat", []),
 ("Schach", []), ("Tichu", []), ("Qwixx", []), ("Kniffel", []), ("Mensch ärgere Dich nicht", []),
 ("Die Quacksalber von Quedlinburg", ["Quacksalber"]), ("Zug um Zug", ["Ticket to Ride"]), ("Fuji", []),
 ("Mars", []), ("Everdell: Pearlbrook", ["Pearlbrook"]), ("Uno", []), ("Das Spiel", []), ("Nova Luna", []),
 ("Village", []), ("Ganz schön clever", []), ("Die Macher", []),
]
KATALOG, IDS = rag.katalog_aus_index([{"spiel_id": rag.spiel_slug(n), "name": n, "aliase": a} for n, a in SPIELE])
WB = rag.chat_woerterbuch(KATALOG)
R = rag.RUECKFRAGE + " Schreib zum Beispiel „Spiel: Azul“. Im Index: 52 Spiele."

FRAGEN = [
    'Wie endet das Spiel?',
    'Wer gewinnt das Spiel bei Gleichstand?',
    'Wann ist das Spiel vorbei?',
    'Wie viele Runden dauert das Spiel?',
    'Darf ich die Crew austauschen?',
    'Was ist die Wurzel des Problems, wenn niemand bauen kann?',
    'Wann darf ich go sagen?',
    'Muss ich bei Go warten?',
    'Wie viele Siedler bekomme ich?',
    'Was macht der Mars-Marker?',
    'Wie funktioniert das Duel am Ende?',
    'Gibt es ein Duel zwischen zwei Spielern?',
    'Ist das wie beim Skat?',
    'Spielt man das ähnlich wie Schach?',
    'Das ist ja wie Uno, oder?',
    'Wie bei Kniffel?',
    'Kann ich wie bei Tichu passen?',
    'Wer ist der Wizard?',
    'Welche Karte ist die Heat-Karte?',
    'Wie viel Heat bekomme ich?',
    'Was ist ein Village?',
    'Kann ich mein Village erweitern?',
    'Brass oder Holz, was ist wertvoller?',
    'Wann darf ich Brass einsetzen?',
    'Wieviele Punkte bringt Burgund?',
    'Liegt die Provinz Burgund am Rand?',
    'Was ist Fuji auf der Karte?',
    'Wie funktioniert die Go-Phase?',
    'Die Macher der Erweiterung sagen was?',
    'Was sagen die Macher dazu?',
    'Ist Patchwork erlaubt beim Legen?',
    'Darf ich eine Patchwork-Decke bauen?',
    'Was bedeutet Paleo als Symbol?',
    'Welche Rolle spielt Istanbul?',
    'Was passiert in Istanbul?',
    'Ich spiele sonst Catan, ist das ähnlich?',
    'Wie in Carcassonne, oder?',
    'Kann ich wie in Dominion Karten kaufen?',
    'Und bei zwei Spielern?',
    'Und zu dritt?',
    'Wie viele Karten auf der Hand?',
    'Was kostet ein Haus?',
    'Wann bekomme ich Geld?',
    'Wie viel Geld gibt es?',
    'Darf ich tauschen?',
    'Was ist das Spielziel?',
    'Wie baue ich?',
    'Wer fängt an?',
    'Wie wird gewertet?',
    'Was ist mit dem Bonus?',
    'Darf ich Karten abwerfen?',
    'Wie viele Aktionen habe ich?',
    'Kann ich passen?',
    'Was passiert am Rundenende?',
    'Was mache ich mit Uno-Karten?',
    'Wie gewinnt man Hanabi-mäßig ohne Hinweise?',
    'Was ist die Mysterium-Karte?',
    'Hat das was mit Codenames zu tun?',
    'Ist das Just One-artig?',
    'Gibt es hier eine Everdell-Variante?',
    'Ist Azul ein anderes Spiel?',
    'Wie im Spiel Azul?',
    'Das Spiel ist neu für mich, wie fange ich an?',
    'Erklär mir das Spiel kurz.',
    'Was ist der beste Zug im Spiel?',
    'Wie schnell ist das Spiel?',
    'Gibt es eine Solo-Variante für das Spiel?',
    'Die Crew hat gewonnen, oder?',
    'Wie viele Hive-Steine gibt es?',
    'Wie viele Wonders darf ich bauen?',
    'Wie funktionieren die 7 Wonders?',
    'Zug um Zug: wie ziehe ich eine Karte?',
    'Wie viel kostet Zug um Zug eine Route?',
    'Zug um Zug gebaut, dann?',
    'Was mache ich im Zug um Zug-Modus?',
    'Qwixx-Regel: wann kreuze ich?',
    'Darf ich Root spielen?',
    'Was ist Root?',
    'Wo ist mein Root-Marker?',
    'Heat?',
    'Go?',
    'Mars?',
    'Burgund?',
    'Die Crew?',
    'Das Spiel?',
    'Village?',
    'Uno!',
    'Skat.',
    'Wie funktioniert Heat im Detail?',
    'Zu zweit, wie läuft das?',
    'Bei vier Spielern?',
    'Für Anfänger?',
    'Spiel: wie viele Karten?',
    'Zu Beginn: wie viel Geld?',
    'Bei Gleichstand: wer gewinnt?',
    'Zu Mars: wie viele Punkte?',
    'Bei Mars: wie viele Punkte?',
    'Zu dem Café: was kostet der Kaffee?',
    'Bitte',
    'Danke',
]


def U(t):
    return {"role": "user", "content": t}


def A(t):
    return {"role": "assistant", "content": t}


def chat(*wechsel):
    return [U(t) if i % 2 == 0 else A(t) for i, t in enumerate(wechsel)]


def wahl(*wechsel):
    return rag.spiel_im_chat(chat(*wechsel), WB)


class TestKeineErkennungImFreitext(unittest.TestCase):
    def test_erste_frage_legt_nie_ein_spiel_fest(self):
        falsch = [(q, wahl(q)) for q in FRAGEN if wahl(q) != ("frage", None, 0, None)]
        self.assertEqual(falsch, [])
        for q in ("Wie punktet man in Food Chain Magnate?", "Wie endet Das Spiel?", "Azul: wer beginnt?",
                  "Wie funktioniert bei 7 Wonders die Wertung?", "Azul"):
            with self.subTest(q=q):
                self.assertEqual(wahl(q), ("frage", None, 0, None))

    def test_laufender_chat_wechselt_nie_ueber_freitext(self):
        for start in ("Spiel: Food Chain Magnate", "Spiel: Azul", "Wechsel zu Everdell"):
            soll = rag.explizite_wahl(start, WB)[0][0]
            falsch = [(q, r) for q in FRAGEN if (r := wahl(start, "Ok.", q)) != ("frage", soll, 2, None)]
            with self.subTest(start=start):
                self.assertEqual(falsch, [])

    def test_natuerliche_wechselformen_sind_keine_wahl(self):
        # Kritiker exp_w.py: alles ausser den drei Formen bleibt beim alten Spiel -- sichtbar
        # in der Fusszeile ("Quelle: Food Chain Magnate ...")
        for w in ("Und jetzt eine Frage zu Azul: wie viele Fliesen?", "Bei Root: wer beginnt?", "Wechseln wir zu Hive",
                  "Jetzt Azul", "Nun zu Azul: wer beginnt?", "Neues Spiel: Azul", "Zu Azul", "Bei Azul", "Für Azul",
                  "Wechsle zu Azul", "Wechsel auf Azul", "Azul: wer beginnt?", "Zu Azul: wer beginnt?", "OK, Azul",
                  "Und Azul?", "Azul", "Azul bitte", "Spiel: Azul wer beginnt?"):
            with self.subTest(w=w):
                self.assertEqual(wahl("Spiel: Food Chain Magnate", "Ok.", w), ("frage", "Food Chain Magnate", 2, None))


class TestExpliziteWahl(unittest.TestCase):
    def test_die_drei_formen(self):
        for w in ("Spiel: Azul", "Spiel Azul", "Wechsel zu Azul", "spiel:Azul", "SPIEL : azul", "Spiel: Azul!",
                  "Spiel: AZUL"):
            with self.subTest(w=w):
                self.assertEqual(wahl(w), ("gewechselt", "Azul", None, None))
                self.assertEqual(wahl("Spiel: Root", "Ok.", w), ("gewechselt", "Azul", None, None))

    def test_mit_frage(self):
        for w in ("Spiel: Azul: wer beginnt?", "Spiel Azul: wer beginnt?", "Wechsel zu Azul: wer beginnt?"):
            with self.subTest(w=w):
                self.assertEqual(wahl(w), ("frage", "Azul", 0, "wer beginnt?"))
        self.assertEqual(wahl("Spiel: 7 Wonders: Duel"), ("gewechselt", "7 Wonders: Duel", None, None))
        self.assertEqual(wahl("Spiel: 7 Wonders: Duel: wer beginnt?"), ("frage", "7 Wonders: Duel", 0, "wer beginnt?"))
        self.assertEqual(wahl("Spiel: 7 Wonders: wer beginnt?"), ("frage", "7 Wonders", 0, "wer beginnt?"))
        self.assertEqual(wahl("Spiel: Fluegelschlag: wie fliegt man?"), ("frage", "Flügelschlag", 0, "wie fliegt man?"))

    def test_ohne_doppelpunkt_nach_dem_namen_keine_wahl(self):
        self.assertEqual(wahl("Spiel: Azul wer beginnt?"), ("frage", None, 0, None))

    def test_wahl_gilt_ohne_fenster(self):
        v = ["Spiel: Azul", "Ok, ab jetzt Azul."]
        v += ["Ist das wie bei Root?", "A.", "Wie bei Brass Birmingham?", "A."]
        for i in range(250):
            v += [f"Folgefrage {i}?", "A."]
        v.append("Und noch eine?")
        self.assertEqual(wahl(*v)[1], "Azul")

    def test_letzte_wahl_gilt(self):
        self.assertEqual(wahl("Spiel: Azul", "Ok.", "Spiel: Root", "Ok.", "Wer beginnt?"), ("frage", "Root", 4, None))

    def test_mehrdeutige_wahl(self):
        k, _ = rag.katalog_aus_index([{"spiel_id": "brass-birmingham", "name": "Brass: Birmingham", "aliase": ["Brass"]},
                                      {"spiel_id": "brass-lancashire", "name": "Brass: Lancashire", "aliase": ["Brass"]},
                                      {"spiel_id": "azul", "name": "Azul", "aliase": []}])
        wb = rag.chat_woerterbuch(k)
        self.assertEqual(rag.spiel_im_chat(chat("Spiel: Brass"), wb)[0], "mehrdeutig")
        # im Verlauf setzt eine mehrdeutige Wahl kein Spiel -- das alte bleibt (D5)
        self.assertEqual(rag.spiel_im_chat(chat("Spiel: Azul", "Ok.", "Spiel: Brass", "Meintest du ...?",
                                                "Wer beginnt?"), wb), ("frage", "Azul", 4, None))
        self.assertEqual(rag.spiel_im_chat(chat("Spiel: Brass", "Meintest du ...?", "Wer beginnt?"), wb),
                         ("frage", None, 2, None))


class TestRueckfrage(unittest.TestCase):
    def test_name_auf_rueckfrage_beantwortet_die_frage(self):
        for antwort in ("Azul", "Azul bitte", "Azul danke", "azul!", "Spiel: Azul"):
            with self.subTest(antwort=antwort):
                erg = wahl("Wer beginnt?", R, antwort)
                self.assertEqual(erg, ("frage", "Azul", 0, None) if not antwort.startswith("Spiel")
                                 else ("gewechselt", "Azul", None, None))

    def test_zweite_rueckfrage_beantwortet_die_juengste_frage(self):
        # D4: F1, Rueckfrage, F2, Rueckfrage, Name -> F2
        self.assertEqual(wahl("Frage eins?", R, "Frage zwei?", R, "Azul"), ("frage", "Azul", 2, None))

    def test_andere_antwort_ist_keine_wahl(self):
        for antwort in ("Bei Azul", "Zu Azul", "Fudschein Magnat", "Azulx"):
            with self.subTest(antwort=antwort):
                self.assertEqual(wahl("Wer beginnt?", R, antwort), ("frage", None, 2, None))

    def test_name_ohne_rueckfrage_ist_eine_frage(self):
        self.assertEqual(wahl("Spiel: Azul", "Ok, ab jetzt Azul.", "Root"), ("frage", "Azul", 2, None))
        self.assertEqual(wahl("Azul"), ("frage", None, 0, None))

    def test_rueckfrage_nach_mehrdeutiger_wahl_mit_frage(self):
        k, _ = rag.katalog_aus_index([{"spiel_id": "brass-birmingham", "name": "Brass: Birmingham", "aliase": ["Brass"]},
                                      {"spiel_id": "brass-lancashire", "name": "Brass: Lancashire", "aliase": ["Brass"]}])
        wb = rag.chat_woerterbuch(k)
        r = rag.RUECKFRAGE + " Meintest du Brass: Birmingham oder Brass: Lancashire?"
        self.assertEqual(rag.spiel_im_chat(chat("Spiel: Brass: wieviel Geld?", r, "Brass: Birmingham"), wb),
                         ("frage", "Brass: Birmingham", 0, "wieviel Geld?"))
        self.assertEqual(rag.spiel_im_chat(chat("Spiel: Brass", r, "Brass: Lancashire"), wb),
                         ("gewechselt", "Brass: Lancashire", None, None))

    def test_gewaehltes_spiel_bleibt_nach_rueckfrage(self):
        self.assertEqual(wahl("Wer beginnt?", R, "Azul", "Spieler 1.", "Und dann?"), ("frage", "Azul", 4, None))


class TestLaufzeit(unittest.TestCase):
    def test_250_spiele_500_nachrichten(self):
        spiele = [{"spiel_id": f"s{i}", "name": f"Spiel Nummer {i} Deluxe Edition", "aliase": [f"SN{i}"]}
                  for i in range(250)]
        wb = rag.chat_woerterbuch(rag.katalog_aus_index(spiele)[0])
        satz = ("Wie viel Geld bekomme ich eigentlich in der dritten Runde wenn ich vorher zwei Karten "
                "gespielt habe und der Marker auf dem Feld neben der Stadt liegt oder nicht")
        verlauf = chat(*(["Spiel: SN7", "Ok."] + [satz, "Antwort."] * 249 + [satz]))
        zeiten = []
        for _ in range(5):
            t = time.perf_counter()
            erg = rag.spiel_im_chat(verlauf, wb)
            zeiten.append(time.perf_counter() - t)
        self.assertEqual(erg[1], "Spiel Nummer 7 Deluxe Edition")
        self.assertLess(max(zeiten), 0.05, f"max {max(zeiten)*1000:.1f} ms")


if __name__ == "__main__":
    unittest.main(verbosity=2)
