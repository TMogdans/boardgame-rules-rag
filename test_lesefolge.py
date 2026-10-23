#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lesereihenfolge (Spec .specify/specs/einlese-qualitaet/spec.md, Abschnitt B): REQ-EQ-3 Baender an
Ueberschriften, REQ-EQ-4 Ausnahmeseiten.

    python test_lesefolge.py

Spec-PR: jeder Test einzeln @unittest.skip("devloop: REQ-EQ-<n> ..."), [REQ-EQ-<n>] im Docstring.
implement entfernt NUR das skip.

Weg: Docling-Weg einlesen.lies_pdf_ein mit der Docling-Attrappe (eq_attrappe.py) -- synthetische
Seiten mit Kaesten in absichtlich falscher Docling-Folge, Seite 600 x 800 pt, Spaltenraster
[[35, 292], [304, 560]], Toleranz 4, Waechter 0,8 (Satzspiegel 525 pt, Grenze 420 pt). Geprueft wird
die Wirkung: Folge der Elementtexte in der Buchdatei und der Abschnitt, in dem ein Element steht.

Vom Test erwartete Schnittstellen (aus der Spec abgeleitet, Namen hier festgelegt):
  Buchdeklaration "lesefolge": {"spalten": [[a, b], ...], "toleranz": pt, "waechter": Anteil,
                                "ausnahmen": [physische Seite, ...]}               (REQ-EQ-3/-4/-15)
                  "tabellenkopf": {"ausnahmen": [...]}  wirkt NICHT auf die Lesefolge   (REQ-EQ-4)
  Protokoll.lesefolge_ausnahmen: [physische Seite, ...]  Seiten, auf denen die Docling-Folge galt,
      weil sie als Ausnahme deklariert sind (REQ-EQ-4)
  Element ohne Lage (prov ohne bbox): bleibt hinter seinem Docling-Vorgaenger (REQ-EQ-3, Schritt 5)
  Bild-Element (picture) mit Text-Kindern: die Kinder werden einsortiert, das Bild selbst belegt die
      Nachbarspalte (ausser Eckbildern)
"""
import os
import sys
import unittest

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)
import testumgebung  # noqa: F401,E402  -- zuerst: alle Standardpfade der Skripte ins Temp-Verzeichnis
import eq_attrappe as eqa  # noqa: E402

E = eqa.Element
LESEFOLGE = eqa.LESEFOLGE


def K(text, lage):
    return E("section_header", text, lage)


def T(text, lage):
    return E("text", text, lage)


def kapitel():
    """Listeneintrag "Kapitel" (Seite 1), ueber die volle Breite oben."""
    return K("Kapitel", (40, 30, 555, 50))


def mit(lesefolge=None, **weitere):
    d = {"lesefolge": dict(LESEFOLGE, **(lesefolge or {}))}
    d.update(weitere)
    return d


# ---------- Faelle (a) bis (j) der Spec, je eine Seite in falscher Docling-Folge ----------
def fall_a(breite=(40, 555)):
    """(a) Spaltenuebergreifende Ueberschrift oben kommt nach dem ersten Element der linken Spalte."""
    return [kapitel(), T("Linksabsatz eins.", (40, 150, 290, 200)), K("Breiter Kopf", (breite[0], 100, breite[1], 120)),
            T("Rechtsabsatz zwei.", (310, 150, 555, 200))]


def fall_b():
    """(b) Kopf der rechten Spalte als Bild-Kind am Seitenende."""
    return [kapitel(), T("Linksoben eins.", (40, 100, 290, 280)), T("Linksunten zwei.", (40, 300, 290, 480)),
            T("Rechtstext drei.", (310, 120, 555, 480)), K("Neuer Teil", (40, 500, 555, 520)),
            T("Teiltext vier.", (40, 530, 290, 600)),
            E("picture", "", (305, 95, 560, 118), kinder=[T("Rechter Kopf", (310, 100, 555, 115))])]


def fall_c():
    """(c) Tabelle oben rechts kommt hinter allen Absaetzen der Seite."""
    return [kapitel(), K("Tabellenteil", (40, 60, 555, 80)), T("Linker Absatz.", (40, 100, 290, 400)),
            K("Spaeterer Teil", (40, 450, 555, 470)), T("Spaeterer Text.", (40, 480, 290, 600)),
            eqa.tabelle([["Stufe", "Wert"], ["1", "5"]], kopf=[0], lage=(310, 100, 555, 200))]


def fall_d():
    """(d) Bild ueber beide Spalten, rechts daneben ein schmales Element."""
    return [kapitel(), T("Linksoben eins.", (40, 100, 290, 300)), T("Rechtsoben zwei.", (310, 100, 555, 300)),
            E("picture", "", (40, 320, 470, 500)), T("Schmal neben Bild.", (480, 320, 555, 500)),
            T("Linksunten drei.", (40, 520, 290, 700))]


def fall_e():
    """(e) Passionsfall: schmale Ueberschrift links, Nachbarspalte auf ihrer Hoehe frei und darunter fortgesetzt."""
    return [kapitel(), K("Passion Alpha", (40, 100, 200, 115)), T("Alphalinks eins.", (40, 120, 290, 380)),
            K("Passion Beta", (40, 400, 200, 415)), T("Betalinks drei.", (40, 420, 290, 700)),
            T("Alpharechts zwei.", (310, 100, 555, 380)), T("Betarechts vier.", (310, 420, 555, 700))]


def fall_f():
    """(f) Talentfall: Ueberschrift in der Spalte auf Hoehe eines rechten Absatzes."""
    return [kapitel(), T("Talentlinks eins.", (40, 100, 290, 300)), T("Talentrechts drei.", (310, 100, 555, 600)),
            K("Talent Xeno", (40, 310, 200, 325)), T("Talentlinks zwei.", (40, 330, 290, 600))]


def fall_g():
    """(g) Kurze Nachbarspalte (S. 28): rechts nur ein Element ueber der Ueberschrift, darunter nichts."""
    return [kapitel(), T("Kurzlinks eins.", (40, 100, 290, 300)), T("Kurzrechts zwei.", (310, 100, 555, 300)),
            K("Kleiner Kopf", (40, 400, 200, 415)), T("Kurzlinks drei.", (40, 420, 290, 700))]


def fall_h():
    """(h) Mehrspaltiges Element (erster Kasten links unten, zweiter rechts oben) hinter L1; Docling setzt
    R1 vor L2."""
    return [kapitel(), T("Mehrlinks eins.", (40, 100, 290, 300)),
            E("text", "Mehrspaltig zwei.", (40, 600, 290, 700), weitere_kaesten=[(310, 100, 555, 150)]),
            T("Mehrrechts vier.", (310, 160, 555, 400)), T("Mehrlinks drei.", (40, 310, 290, 590))]


def fall_i(x0=150, x1=450):
    """(i) Teilbreites spaltenuebergreifendes Element (Standard 300 pt < 420 pt) unter beiden Spalten."""
    return [kapitel(), T("Waechterrechts eins.", (310, 100, 555, 280)), T("Waechterlinks zwei.", (40, 100, 290, 280)),
            T("Waechterblock drei.", (x0, 300, x1, 340))]


def fall_j():
    """(j) 2x2-Werteblock in der linken Spalte, Docling liest spaltenweise."""
    return [kapitel(), T("Stufe: 3", (40, 200, 150, 212)), T("Kosten: 1", (40, 215, 150, 227)),
            T("Aktion: frei", (160, 200, 290, 212)), T("Dauer: 2", (160, 215, 290, 227))]


class LesefolgeTest(eqa.EQTest):
    def lies_seite(self, seite, **spec2):
        self.deklariere(**spec2)
        return self.lies({1: seite})


# ===================================================================================
# REQ-EQ-3: Faelle (a) bis (j)
# ===================================================================================
class TestBaender(LesefolgeTest):
    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_a_breite_ueberschrift_steht_zuerst(self):
        """[REQ-EQ-3] (a) Spaltenuebergreifende Ueberschrift kommt in Docling nach dem ersten linken Element -> sie steht zuerst, das Element liegt in ihrem Abschnitt; ohne lesefolge in "Kapitel"."""
        self.lies_seite(fall_a(), **mit())
        self.assertEqual(self.folge("Rechtsabsatz", "Linksabsatz", "Breiter Kopf"),
                         ["Breiter Kopf", "Linksabsatz", "Rechtsabsatz"])
        self.assertEqual(self.pfad_von("Linksabsatz"), ["Kapitel", "Breiter Kopf"])
        self.lies_seite(fall_a())                                   # Gegenprobe: Docling-Folge
        self.assertEqual(self.pfad_von("Linksabsatz"), ["Kapitel"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_a_schmale_spaltenuebergreifende_ueberschrift_ist_kein_waechter(self):
        """[REQ-EQ-3] (a) mit schmaler zentrierter Ueberschrift (200 pt < 420 pt): Ueberschriften loesen den Seitenwaechter nicht aus -> gleiche Umordnung. Faengt: Waechter ohne Ausnahme fuer Ueberschriften."""
        self.lies_seite(fall_a(breite=(200, 400)), **mit())
        self.assertEqual(self.folge("Rechtsabsatz", "Linksabsatz", "Breiter Kopf"),
                         ["Breiter Kopf", "Linksabsatz", "Rechtsabsatz"])
        self.assertEqual(self.pfad_von("Linksabsatz"), ["Kapitel", "Breiter Kopf"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_b_bild_kind_kopf_der_rechten_spalte(self):
        """[REQ-EQ-3] (b) Kopf der rechten Spalte kommt als Bild-Kind am Seitenende -> hinter der linken Spalte, vor dem Rest der rechten und vor der naechsten Bandgrenze."""
        self.lies_seite(fall_b(), **mit())
        self.assertEqual(self.folge("Linksoben", "Linksunten", "Rechtstext", "Neuer Teil", "Teiltext", "Rechter Kopf"),
                         ["Linksoben", "Linksunten", "Rechter Kopf", "Rechtstext", "Neuer Teil", "Teiltext"])
        self.assertEqual(self.pfad_von("Rechter Kopf"), ["Kapitel"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_c_tabelle_oben_rechts_im_abschnitt_darueber(self):
        """[REQ-EQ-3] (c) Tabelle oben rechts kommt in Docling hinter allen Absaetzen -> sie liegt im Abschnitt der Ueberschrift ueber ihr (ohne lesefolge im spaeteren)."""
        self.lies_seite(fall_c(), **mit())
        self.assertEqual(self.pfad_von("| Stufe"), ["Kapitel", "Tabellenteil"])
        self.assertEqual(self.folge("Linker Absatz", "| Stufe", "Spaeterer Teil"), ["Linker Absatz", "| Stufe", "Spaeterer Teil"])
        self.lies_seite(fall_c())
        self.assertEqual(self.pfad_von("| Stufe"), ["Kapitel", "Spaeterer Teil"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_d_schmales_element_neben_bild_folgt_der_linken_spalte(self):
        """[REQ-EQ-3] (d) Bild ueber beide Spalten (keine Bandgrenze), rechts daneben ein schmales Element -> es folgt dem Ende der linken Spalte und dem Kopf der rechten. Faengt: Bild als Bandgrenze."""
        self.lies_seite(fall_d(), **mit())
        self.assertEqual(self.folge("Linksoben", "Rechtsoben", "Schmal neben", "Linksunten"),
                         ["Linksoben", "Linksunten", "Rechtsoben", "Schmal neben"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_e_passionsfall_schmale_ueberschrift_wird_bandgrenze(self):
        """[REQ-EQ-3] (e) Passionsfall: Kopf B links auf Hoehe einer Luecke rechts, rechts darunter fortgesetzt -> Folge A1, A2, Kopf B, B1, B2; A2 liegt in A, B2 in B."""
        self.lies_seite(fall_e(), **mit())
        self.assertEqual(self.folge("Passion Alpha", "Alphalinks", "Passion Beta", "Betalinks", "Alpharechts", "Betarechts"),
                         ["Passion Alpha", "Alphalinks", "Alpharechts", "Passion Beta", "Betalinks", "Betarechts"])
        self.assertEqual(self.pfad_von("Alpharechts"), ["Kapitel", "Passion Alpha"])
        self.assertEqual(self.pfad_von("Betarechts"), ["Kapitel", "Passion Beta"])
        self.lies_seite(fall_e())                                   # Gegenprobe: unter Docling liegt A2 in B
        self.assertEqual(self.pfad_von("Alpharechts"), ["Kapitel", "Passion Beta"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_e_kopf_aus_der_liste_ist_ueberschrift_der_kopfmenge(self):
        """[REQ-EQ-3] (e) mit "Passion Beta" als Klasse text, aber Listeneintrag der Seite: die Kopfmenge (Listenabgleich in Docling-Folge) macht ihn zur Ueberschrift -> Bandgrenze wie in (e)."""
        seite = fall_e()
        seite[3] = T("Passion Beta", (40, 400, 200, 415))
        self.deklariere(liste=(("Kapitel", 1, 1), ("Passion Beta", 1, 1)), **mit())
        self.lies({1: seite})
        self.assertEqual(self.folge("Alphalinks", "Alpharechts", "Passion Beta", "Betalinks", "Betarechts"),
                         ["Alphalinks", "Alpharechts", "Passion Beta", "Betalinks", "Betarechts"])
        self.assertEqual(self.pfad_von("Alpharechts"), ["Kapitel", "Passion Alpha"])
        self.assertEqual(self.pfad_von("Betarechts"), ["Passion Beta"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_e_linie_ueber_die_volle_breite_unter_der_ueberschrift(self):
        """[REQ-EQ-3] (e) mit einer Linie (Bild) ueber die volle Breite unter "Passion Beta": 4 pt darunter -> keine Bandgrenze durch das Bild, kein Waechter, Kopf B bleibt Bandgrenze; die Linie innerhalb +-2 pt der Ueberschrift belegt die Nachbarspalte -> keine Bandgrenze (Docling-Folge der Spalten)."""
        darunter = fall_e()
        darunter.insert(4, E("picture", "", (35, 419, 560, 420)))
        self.lies_seite(darunter, **mit())
        self.assertEqual(self.folge("Alphalinks", "Passion Beta", "Betalinks", "Alpharechts", "Betarechts"),
                         ["Alphalinks", "Alpharechts", "Passion Beta", "Betalinks", "Betarechts"])
        im_fenster = fall_e()
        im_fenster.insert(4, E("picture", "", (35, 416, 560, 417)))
        self.lies_seite(im_fenster, **mit())
        self.assertEqual(self.folge("Alphalinks", "Passion Beta", "Betalinks", "Alpharechts", "Betarechts"),
                         ["Alphalinks", "Passion Beta", "Betalinks", "Alpharechts", "Betarechts"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_f_talentfall_ueberschrift_in_der_spalte_keine_bandgrenze(self):
        """[REQ-EQ-3] (f) Talentfall: "Talent Xeno" links auf Hoehe eines rechten Absatzes -> keine Bandgrenze, die rechte Spalte folgt nach der ganzen linken. Mutation "alle Koepfe als Bandgrenze" -> rot."""
        self.lies_seite(fall_f(), **mit())
        self.assertEqual(self.folge("Talentlinks eins", "Talentrechts", "Talent Xeno", "Talentlinks zwei"),
                         ["Talentlinks eins", "Talent Xeno", "Talentlinks zwei", "Talentrechts"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_g_kurze_nachbarspalte_keine_bandgrenze(self):
        """[REQ-EQ-3] (g) Kurze Nachbarspalte (S. 28): rechts nur ein Element ueber der Ueberschrift, darunter nichts -> keine Bandgrenze. Mutation "Fortsetzungsbedingung weglassen" -> rot."""
        self.lies_seite(fall_g(), **mit())
        self.assertEqual(self.folge("Kurzlinks eins", "Kurzrechts", "Kleiner Kopf", "Kurzlinks drei"),
                         ["Kurzlinks eins", "Kleiner Kopf", "Kurzlinks drei", "Kurzrechts"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_h_mehrspaltiges_element_bleibt_hinter_seinem_vorgaenger(self):
        """[REQ-EQ-3] (h) Mehrspaltiges Element (Kaesten in beiden Spalten) bleibt direkt hinter seinem Docling-Vorgaenger, die anderen werden einsortiert. Mutation "mehrspaltige Elemente einsortieren" -> rot."""
        self.lies_seite(fall_h(), **mit())
        self.assertEqual(self.folge("Mehrlinks eins", "Mehrspaltig", "Mehrlinks drei", "Mehrrechts"),
                         ["Mehrlinks eins", "Mehrspaltig", "Mehrlinks drei", "Mehrrechts"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_i_teilbreites_element_waechter_docling_folge(self):
        """[REQ-EQ-3] (i) Teilbreites spaltenuebergreifendes Element (300 pt) -> Docling-Folge der ganzen Seite; ueber 80 % breit (515 pt) -> umgeordnet. Mutation "Waechter aus" -> rot."""
        self.lies_seite(fall_i(), **mit())
        self.assertEqual(self.folge("Waechterlinks", "Waechterrechts", "Waechterblock"),
                         ["Waechterrechts", "Waechterlinks", "Waechterblock"])
        self.lies_seite(fall_i(40, 555), **mit())
        self.assertEqual(self.folge("Waechterlinks", "Waechterrechts", "Waechterblock"),
                         ["Waechterlinks", "Waechterrechts", "Waechterblock"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_i_waechtergrenze_ist_der_deklarierte_anteil(self):
        """[REQ-EQ-3] (i) Grenze = waechter x (b_letzte - a_1): 415 pt < 420 -> Waechter; 425 pt -> umgeordnet; mit waechter 0,9 (472,5 pt) greift er auch bei 425 pt. Der Anteil ist Datum, kein Code."""
        for (x0, x1), anteil, waechter in (((100, 515), 0.8, True), ((100, 525), 0.8, False), ((100, 525), 0.9, True)):
            with self.subTest(breite=x1 - x0, anteil=anteil):
                self.lies_seite(fall_i(x0, x1), **mit({"waechter": anteil}))
                soll = (["Waechterrechts", "Waechterlinks", "Waechterblock"] if waechter
                        else ["Waechterlinks", "Waechterrechts", "Waechterblock"])
                self.assertEqual(self.folge("Waechterlinks", "Waechterrechts", "Waechterblock"), soll)

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_j_werteblock_2x2_zeilenweise(self):
        """[REQ-EQ-3] (j) 2x2-Werteblock mit gleichen Oberkanten, Docling spaltenweise -> zeilenweise Folge (Gleichstand: Docling-Folge)."""
        self.lies_seite(fall_j(), **mit())
        self.assertEqual(self.folge("Stufe: 3", "Kosten: 1", "Aktion: frei", "Dauer: 2"),
                         ["Stufe: 3", "Aktion: frei", "Kosten: 1", "Dauer: 2"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_k_ohne_lesefolge_byte_gleich_zum_stand_vor_der_spec(self):
        """[REQ-EQ-3] (k) Ohne "lesefolge": alle Faelle (a)-(j) auf je einer Seite -> Buchdatei byte-gleich zum Einlesen mit einlesen.py/rag.py aus BASIS_COMMIT; mit lesefolge anders (die Faelle wirken)."""
        faelle = [fall_a, fall_b, fall_c, fall_d, fall_e, fall_f, fall_g, fall_h, fall_i, fall_j]
        elemente = {}
        for s, fall in enumerate(faelle, 1):
            seite = fall()
            if s > 1:
                seite[0] = K(f"Kapitel {s}", (40, 30, 555, 50))
            elemente[s] = seite
        liste = tuple((f"Kapitel {s}" if s > 1 else "Kapitel", s, 1) for s in elemente)
        pdf = self.pdf_leer(len(elemente))
        self.deklariere(liste=liste)
        self.lies_alt(elemente, pdf)
        alt = self.roh()
        self.lies(elemente, pdf)
        self.assertEqual(self.roh(), alt)
        self.deklariere(liste=liste, **mit())
        self.lies(elemente, pdf)
        self.assertNotEqual(self.roh(), alt)


# ===================================================================================
# REQ-EQ-3: weitere Regeln aus dem Wortlaut (Begriffe "Bandgrenze", "Seitenwaechter", Schritt 5)
# ===================================================================================
class TestBaenderWortlaut(LesefolgeTest):
    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_kasten_fuellt_spalte_bleibt_unter_der_rechten_kapitelueberschrift(self):
        """[REQ-EQ-3] S. 53: rechte Kapitelueberschrift oben, links auf ihrer Hoehe frei und darunter ein Kasten, der die Spalte fuellt -> Bandgrenze; der Kasten steht unter der Ueberschrift -- bei richtiger Docling-Folge unveraendert, bei Kasten vor der Ueberschrift umgeordnet. Faengt: "Baender ignorieren" (Kasten vor die Ueberschrift)."""
        kopf = K("Neues Kapitel", (310, 60, 555, 80))
        kasten = T("Kastentext fuellt die Spalte.", (40, 100, 290, 700))
        rechts = T("Kapitelrechts Text.", (310, 100, 555, 700))
        for name, seite in (("Docling richtig", [kopf, kasten, rechts]), ("Docling Kasten zuerst", [kasten, kopf, rechts])):
            with self.subTest(fall=name):
                self.deklariere(liste=(("Neues Kapitel", 1, 1),), **mit())
                self.lies({1: seite})
                self.assertEqual(self.folge("Kastentext", "Neues Kapitel", "Kapitelrechts"),
                                 ["Neues Kapitel", "Kastentext", "Kapitelrechts"])
                self.assertEqual(self.pfad_von("Kastentext"), ["Neues Kapitel"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_werte_raster_ueber_der_spaltenluecke_waechter(self):
        """[REQ-EQ-3] Werte-Raster (S. 299-306): 3 x 3 kleine Zellen, die mittlere ueberbrueckt die Spaltenluecke (schmal, spaltenuebergreifend) -> Seitenwaechter, Docling-Folge (zeilenweise) bleibt; der Waechter gilt je Seite: Seite 2 (Fall a) wird umgeordnet."""
        seite = [kapitel()]
        for r, oben in enumerate((100, 120, 140), 1):
            seite += [T(f"Raster a{r}", (40, oben, 120, oben + 12)), T(f"Raster m{r}", (250, oben, 350, oben + 12)),
                      T(f"Raster b{r}", (450, oben, 540, oben + 12))]
        zweite = fall_a()[1:]
        self.deklariere(**mit())
        self.lies({1: seite, 2: zweite})
        marken = [f"Raster {c}{r}" for r in (1, 2, 3) for c in "amb"]
        self.assertEqual(self.folge(*marken), marken)
        self.assertEqual(self.folge("Rechtsabsatz", "Linksabsatz", "Breiter Kopf"),
                         ["Breiter Kopf", "Linksabsatz", "Rechtsabsatz"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_randelement_loest_den_waechter_nicht_aus(self):
        """[REQ-EQ-3] Schmale zentrierte Seitenzahl im deklarierten Fussrand (spaltenuebergreifend, 40 pt) -> kein Waechter, die Seite wird umgeordnet (Fall a). Faengt: Waechter zaehlt Randelemente."""
        seite = fall_a() + [E("page_footer", "Seite 7", (280, 770, 320, 780))]
        self.deklariere(rand={"fuss": 40}, **mit())
        self.lies({1: seite})
        self.assertEqual(self.pfad_von("Linksabsatz"), ["Kapitel", "Breiter Kopf"])
        self.assertNotIn("Seite 7", self.gesamttext())

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_eckbild_belegt_die_nachbarspalte_nicht(self):
        """[REQ-EQ-3] Ueberschrift links oben neben einem Bild rechts oben: Eckbild (Unterkante <= 70 pt, ab x 500) -> Nachbarspalte frei, Bandgrenze; Unterkante 72 pt -> kein Eckbild, belegt, keine Bandgrenze."""
        def seite(unterkante):
            return [T("Eckelinks null.", (40, 20, 290, 50)), T("Eckerechts null.", (310, 20, 495, 50)),
                    K("Eckkopf", (40, 55, 200, 68)), T("Eckelinks eins.", (40, 75, 290, 500)),
                    T("Eckerechts eins.", (310, 75, 555, 500)), E("picture", "", (510, 20, 590, unterkante))]
        marken = ("Eckelinks null", "Eckerechts null", "Eckkopf", "Eckelinks eins", "Eckerechts eins")
        self.deklariere(liste=(("Eckkopf", 1, 1),), **mit())
        self.lies({1: seite(70)})
        self.assertEqual(self.folge(*marken), ["Eckelinks null", "Eckerechts null", "Eckkopf", "Eckelinks eins",
                                               "Eckerechts eins"])
        self.lies({1: seite(72)})
        self.assertEqual(self.folge(*marken), ["Eckelinks null", "Eckkopf", "Eckelinks eins", "Eckerechts null",
                                               "Eckerechts eins"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_element_ohne_lage_bleibt_hinter_seinem_docling_vorgaenger(self):
        """[REQ-EQ-3] Schritt 5: Element ohne Lage (kein Kasten) behaelt seinen Platz hinter seinem Docling-Vorgaenger: Docling R1, X, L1 -> L1, R1, X."""
        seite = [kapitel(), T("Lagerechts eins.", (310, 100, 555, 300)), T("Ohnelage zwei.", None),
                 T("Lagelinks drei.", (40, 100, 290, 300))]
        self.lies_seite(seite, **mit())
        self.assertEqual(self.folge("Lagerechts", "Ohnelage", "Lagelinks"), ["Lagelinks", "Lagerechts", "Ohnelage"])

    @unittest.skip("devloop: REQ-EQ-3 noch nicht implementiert")
    def test_req_eq_3_toleranz_und_spalten_sind_daten(self):
        """[REQ-EQ-3] Spalte nach dem ersten Kasten mit Toleranz: rechtes Element bei x0 = 301 ist mit Toleranz 4 Spalte 2 (Fall a wirkt), mit Toleranz 2 spaltenuebergreifend und schmal -> Waechter, Docling-Folge."""
        seite = fall_a()
        seite[3] = T("Rechtsabsatz zwei.", (301, 150, 555, 200))
        self.lies_seite(seite, **mit({"toleranz": 4}))
        self.assertEqual(self.pfad_von("Linksabsatz"), ["Kapitel", "Breiter Kopf"])
        self.lies_seite(seite, **mit({"toleranz": 2}))
        self.assertEqual(self.pfad_von("Linksabsatz"), ["Kapitel"])


# ===================================================================================
# REQ-EQ-4: Ausnahmeseiten
# ===================================================================================
def zwei_seiten_a():
    s1 = fall_a()
    s2 = [T("Zweitlinks eins.", (40, 150, 290, 200)), K("Zweiter Kopf", (40, 100, 555, 120)),
          T("Zweitrechts zwei.", (310, 150, 555, 200))]
    return {1: s1, 2: s2}


class TestAusnahmeseiten(LesefolgeTest):
    @unittest.skip("devloop: REQ-EQ-4 noch nicht implementiert")
    def test_req_eq_4_ausnahmeseite_behaelt_docling_folge_und_steht_im_protokoll(self):
        """[REQ-EQ-4] Zwei Seiten im Fall (a), Seite 2 als Ausnahme -> Seite 1 neu geordnet, Seite 2 in Docling-Folge; Protokoll (Objekt und Datei) nennt Seite 2."""
        self.deklariere(**mit({"ausnahmen": [2]}))
        p = self.lies(zwei_seiten_a())
        self.assertEqual(self.pfad_von("Linksabsatz"), ["Kapitel", "Breiter Kopf"])          # Seite 1 umgeordnet
        self.assertEqual(self.pfad_von("Zweitlinks"), ["Kapitel", "Breiter Kopf"])           # Seite 2: Docling, vor "Zweiter Kopf"
        self.assertEqual(self.folge("Zweitlinks", "Zweiter Kopf", "Zweitrechts"), ["Zweitlinks", "Zweiter Kopf", "Zweitrechts"])
        self.assertEqual(p.lesefolge_ausnahmen, [2])
        self.assertEqual(self.protokoll_datei()["lesefolge_ausnahmen"], [2])
        self.deklariere(**mit())                                                             # Gegenprobe ohne Ausnahme
        p = self.lies(zwei_seiten_a())
        self.assertEqual(self.pfad_von("Zweitlinks"), ["Kapitel", "Zweiter Kopf"])
        self.assertEqual(p.lesefolge_ausnahmen, [])

    @unittest.skip("devloop: REQ-EQ-4 noch nicht implementiert")
    def test_req_eq_4_tabellenkopf_ausnahmen_wirken_nicht_auf_die_lesefolge(self):
        """[REQ-EQ-4] tabellenkopf.ausnahmen = [1, 2] ohne lesefolge.ausnahmen -> beide Seiten neu geordnet, keine Lesefolge-Ausnahme im Protokoll."""
        self.deklariere(**mit(tabellenkopf={"ausnahmen": [1, 2]}))
        p = self.lies(zwei_seiten_a())
        self.assertEqual(self.pfad_von("Linksabsatz"), ["Kapitel", "Breiter Kopf"])
        self.assertEqual(self.pfad_von("Zweitlinks"), ["Kapitel", "Zweiter Kopf"])
        self.assertEqual(p.lesefolge_ausnahmen, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
