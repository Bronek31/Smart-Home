"""Ustawienia telefonów i cisza nocna osobno dla każdego (telefony.py).

Uruchamianie: python -m unittest discover -s tests -v
"""

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import telefony as T  # noqa: E402

WAW = ZoneInfo("Europe/Warsaw")
REPO = Path(__file__).resolve().parent.parent


def lok(r, m, d, h, mi=0):
    return datetime(r, m, d, h, mi, tzinfo=WAW)


def ms(dt):
    return int(dt.timestamp() * 1000)


def ust(**zmiany):
    u = dict(T.DOMYSLNE)
    u.update(zmiany)
    return u


class TestParsowanie(unittest.TestCase):
    def test_brak_zmiennej_daje_domyslne(self):
        for tekst in (None, "", "   ", 5):
            self.assertEqual(T.ustawienia_telefonu(tekst), T.DOMYSLNE)

    def test_zly_json_lista_i_null_daja_domyslne(self):
        for tekst in ("{", "[1,2]", "null", "\"tekst\"", "[" * 5000):
            self.assertEqual(T.ustawienia_telefonu(tekst), T.DOMYSLNE, tekst[:20])

    def test_brakujace_klucze_uzupelnia_domyslnymi(self):
        u = T.ustawienia_telefonu('{"podlej": false, "od": 22}')
        self.assertFalse(u["podlej"])
        self.assertEqual(u["od"], 22)
        self.assertEqual(u["do"], 8)
        self.assertTrue(u["przewietrz"])

    def test_zle_typy_pola_biora_domyslne(self):
        # true z JSON-a to w Pythonie int 1 — nie może zostać godziną 1:00
        u = T.ustawienia_telefonu('{"od": true, "do": 24, "podlej": "nie", "cisza": 0, "okno": null}')
        self.assertEqual((u["od"], u["do"]), (21, 8))
        self.assertTrue(u["podlej"])
        self.assertTrue(u["cisza"])
        self.assertTrue(u["okno"])
        self.assertEqual(T.ustawienia_telefonu('{"od": -1, "do": 7.5}')["od"], 21)
        self.assertEqual(T.ustawienia_telefonu('{"od": -1, "do": 7.5}')["do"], 8)

    def test_nieznane_klucze_odpadaja(self):
        u = T.ustawienia_telefonu('{"endpoint": "https://x", "podlej": false}')
        self.assertNotIn("endpoint", u)
        self.assertEqual(set(u), set(T.DOMYSLNE))

    def test_z_env(self):
        env = {"POWIADOMIENIA_ANDROID": '{"podsumowanie": true}'}
        u = T.ustawienia_z_env(env)
        self.assertTrue(u["android"]["podsumowanie"])
        self.assertEqual(u["iphone"], T.DOMYSLNE)
        self.assertEqual(T.czy_wlasne(env), {"android": "własne", "iphone": "domyślne"})
        # zmienna jest, ale zepsuta: planer bierze domyślne, więc log nie może mówić „własne”
        self.assertEqual(T.czy_wlasne({"POWIADOMIENIA_IPHONE": "{zepsute"})["iphone"], "nieczytelne")
        self.assertEqual(T.czy_wlasne({"POWIADOMIENIA_IPHONE": "[1]"})["iphone"], "nieczytelne")

    def test_domyslne_zgodne_ze_strona(self):
        """Strażnik: DOMYSLNE w index.html to te same wartości. Rozjazd znaczyłby, że ekran
        pokazuje co innego, niż kolektor robi, dopóki ktoś nie zapisze ustawień."""
        import re
        html = (REPO / "index.html").read_text(encoding="utf-8")
        m = re.search(r"const DOMYSLNE\s*=\s*(\{[^}]*\})", html)
        # Strona ma zakładkę Powiadomienia, więc brak literału to błąd, a nie stara strona — inaczej strażnik
        # przechodziłby po cichu, gdyby ktoś zmienił jego zapis.
        self.assertIsNotNone(m, "index.html bez jednowierszowego literału const DOMYSLNE = {...}")
        js = re.sub(r"(\w+)\s*:", r'"\1":', m.group(1)).replace("'", '"')
        self.assertEqual(json.loads(js), T.DOMYSLNE)


class TestCisza(unittest.TestCase):
    def test_domyslna_21_8(self):
        u = ust()
        self.assertFalse(T.w_ciszy(u, lok(2026, 10, 11, 20, 59)))
        self.assertTrue(T.w_ciszy(u, lok(2026, 10, 11, 21, 0)))
        self.assertTrue(T.w_ciszy(u, lok(2026, 10, 12, 7, 59)))
        self.assertFalse(T.w_ciszy(u, lok(2026, 10, 12, 8, 0)))

    def test_cisza_w_srodku_doby_i_po_polnocy(self):
        u = ust(od=0, do=6)
        self.assertFalse(T.w_ciszy(u, lok(2026, 10, 11, 23)))
        self.assertTrue(T.w_ciszy(u, lok(2026, 10, 12, 0)))
        self.assertFalse(T.w_ciszy(u, lok(2026, 10, 12, 6)))

    def test_wylaczona_i_zerowa(self):
        self.assertFalse(T.w_ciszy(ust(cisza=False), lok(2026, 10, 11, 23)))
        self.assertFalse(T.w_ciszy(ust(od=22, do=22), lok(2026, 10, 11, 23)))

    def test_noc_wszystkich(self):
        u = {"android": ust(), "iphone": ust(od=23, do=7)}
        self.assertFalse(T.noc_wszystkich(u, lok(2026, 10, 11, 22)))
        self.assertTrue(T.noc_wszystkich(u, lok(2026, 10, 11, 23)))
        self.assertFalse(T.noc_wszystkich(u, lok(2026, 10, 12, 7)))
        u["iphone"] = ust(cisza=False)
        self.assertFalse(T.noc_wszystkich(u, lok(2026, 10, 12, 3)))

    def test_koniec_nocy_domyslny_to_8(self):
        u = {t: ust() for t in T.TELEFONY}
        self.assertEqual(T.koniec_nocy_ms(u, ms(lok(2026, 10, 12, 10, 1)), WAW), ms(lok(2026, 10, 12, 8)))
        self.assertEqual(T.koniec_nocy_ms(u, ms(lok(2026, 10, 12, 8, 1)), WAW), ms(lok(2026, 10, 12, 8)))
        self.assertIsNone(T.koniec_nocy_ms(u, ms(lok(2026, 10, 12, 7, 1)), WAW))

    def test_koniec_nocy_przy_roznych_ciszach_i_bez_wspolnej(self):
        u = {"android": ust(), "iphone": ust(od=23, do=7)}
        # wspólna noc 23–7, więc rano liczy się od 7:00
        self.assertEqual(T.koniec_nocy_ms(u, ms(lok(2026, 10, 12, 9)), WAW), ms(lok(2026, 10, 12, 7)))
        u["iphone"] = ust(cisza=False)
        self.assertIsNone(T.koniec_nocy_ms(u, ms(lok(2026, 10, 12, 9)), WAW))

    def test_koniec_nocy_przy_zmianie_czasu(self):
        u = {t: ust() for t in T.TELEFONY}
        # 25.10.2026: 3:00 CEST → 2:00 CET, doba ma 25 godz.; koniec nocy dalej o 8:00 lokalnie
        self.assertEqual(T.koniec_nocy_ms(u, ms(lok(2026, 10, 25, 9, 30)), WAW), ms(lok(2026, 10, 25, 8)))
        self.assertEqual(T.koniec_nocy_ms(u, ms(lok(2027, 3, 28, 9, 30)), WAW), ms(lok(2027, 3, 28, 8)))


class TestAdresaci(unittest.TestCase):
    def test_rozdzial_teraz_i_odloz(self):
        u = {"android": ust(), "iphone": ust(od=23, do=7)}
        self.assertEqual(T.adresaci("podlej", u, lok(2026, 10, 11, 22)), (["iphone"], ["android"]))
        self.assertEqual(T.adresaci("podlej", u, lok(2026, 10, 11, 12)), (["android", "iphone"], []))

    def test_wylaczona_regula_nie_trafia_nigdzie(self):
        u = {"android": ust(podlej=False), "iphone": ust()}
        self.assertEqual(T.adresaci("podlej", u, lok(2026, 10, 11, 12)), (["iphone"], []))
        self.assertEqual(T.adresaci("podsumowanie", {t: ust() for t in T.TELEFONY}, lok(2026, 10, 11, 12)),
                         ([], []))

    def test_bez_klucza_idzie_do_wszystkich(self):
        u = {"android": ust(podlej=False), "iphone": ust()}
        self.assertEqual(T.adresaci(None, u, lok(2026, 10, 11, 12)), (["android", "iphone"], []))


class TestPrzedSnem(unittest.TestCase):
    def test_dwie_godziny_przed_cisza(self):
        u = ust()
        self.assertFalse(T.przed_snem(u, lok(2026, 10, 11, 18, 59)))
        self.assertTrue(T.przed_snem(u, lok(2026, 10, 11, 19)))
        self.assertTrue(T.przed_snem(u, lok(2026, 10, 11, 20, 59)))
        self.assertFalse(T.przed_snem(u, lok(2026, 10, 11, 21)))

    def test_cisza_od_polnocy_do_2_to_22_24(self):
        """Cisza od 1:00 dawała okno 23:00–0:59 — push po północy z radą, której karta po
        północy już nie daje (przegląd, C4). Od 0, 1 i 2 okno to 22:00–24:00."""
        for od in (0, 1, 2):
            with self.subTest(od=od):
                u = ust(od=od, do=7)
                self.assertFalse(T.przed_snem(u, lok(2026, 10, 11, 21, 59)))
                self.assertTrue(T.przed_snem(u, lok(2026, 10, 11, 22)))
                self.assertTrue(T.przed_snem(u, lok(2026, 10, 11, 23, 59)))
                self.assertFalse(T.przed_snem(u, lok(2026, 10, 12, 0)))
                self.assertFalse(T.przed_snem(u, lok(2026, 10, 12, 1)))

    def test_cisza_od_14_do_23_dwie_godziny_przed(self):
        """Cisza 18–8 dostawała zapasowe 19–21, czyli okno w środku swojej ciszy — „przed
        snem" nie przychodziło nigdy (przegląd, B3). Teraz 16:00–18:00."""
        u = ust(od=18, do=8)
        self.assertEqual([h for h in range(24) if T.przed_snem(u, lok(2026, 10, 11, h, 30))], [16, 17])
        for od in range(14, 24):
            with self.subTest(od=od):
                u = ust(od=od, do=7)
                self.assertEqual([h for h in range(24) if T.przed_snem(u, lok(2026, 10, 11, h, 30))],
                                 [od - 2, od - 1])

    def test_bez_wieczornej_ciszy_19_21(self):
        """Cisza wyłączona, zerowa (od = do) albo zaczynająca się 3:00–13:00 — zapasowe
        19:00–21:00."""
        for u in (ust(cisza=False), ust(od=3, do=5), ust(od=13, do=15), ust(od=22, do=22)):
            with self.subTest(u=(u["cisza"], u["od"], u["do"])):
                self.assertEqual([h for h in range(24) if T.przed_snem(u, lok(2026, 10, 11, h, 30))], [19, 20])

    def test_okno_zawsze_przed_polnoca(self):
        """Każde ustawienie ciszy: okno tylko w godzinach 12–23, nigdy po północy — wtedy
        rada „przewietrz przed snem" zgadza się z kartą pokoju."""
        for cisza in (True, False):
            for od in range(24):
                for do in range(24):
                    u = ust(cisza=cisza, od=od, do=do)
                    godziny = [h for h in range(24) if T.przed_snem(u, lok(2026, 10, 11, h, 30))]
                    self.assertEqual(len(godziny), 2, (cisza, od, do))
                    self.assertTrue(all(12 <= h <= 23 for h in godziny), (cisza, od, do, godziny))

    def test_data_nocy(self):
        self.assertEqual(T.data_nocy(lok(2026, 10, 11, 20)), "2026-10-11")
        self.assertEqual(T.data_nocy(lok(2026, 10, 12, 3)), "2026-10-11")
        self.assertEqual(T.data_nocy(lok(2026, 10, 12, 13)), "2026-10-12")


class TestKolejka(unittest.TestCase):
    def iso_ms(self, s):
        try:
            return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)
        except (AttributeError, ValueError):
            return None

    def test_stan_telefonow_odsiewa_smieci_i_zostawia_inne_pola(self):
        s = T.stan_telefonow({"android": {"odlozone": [1, {"regula": "podlej", "ts": "2026-10-11T20:00:00Z"},
                                                       {"regula": 5, "ts": "x"}], "przed_snem": "2026-10-11"},
                              "iphone": "zepsute"})
        self.assertEqual(len(s["android"]["odlozone"]), 1)
        self.assertEqual(s["android"]["przed_snem"], "2026-10-11")
        self.assertEqual(s["iphone"], {"odlozone": []})
        self.assertEqual(T.stan_telefonow(None), {t: {"odlozone": []} for t in T.TELEFONY})

    def test_odloz_bez_dubli(self):
        s = T.stan_telefonow(None)
        T.odloz(s, ["android"], {"regula": "podlej", "obiekt": "Fikus", "ts": "2026-10-11T20:00:00Z"})
        T.odloz(s, ["android"], {"regula": "podlej", "obiekt": "Fikus", "ts": "2026-10-11T21:00:00Z"})
        T.odloz(s, ["android"], {"regula": "podlej", "obiekt": "Azalia", "ts": "2026-10-11T21:00:00Z"})
        self.assertEqual([p["obiekt"] for p in s["android"]["odlozone"]], ["Fikus", "Azalia"])
        self.assertEqual(s["android"]["odlozone"][0]["ts"], "2026-10-11T20:00:00Z")
        self.assertEqual(s["iphone"]["odlozone"], [])

    def test_przytnij_ttl_i_limit(self):
        teraz = ms(datetime(2026, 10, 12, 8, tzinfo=timezone.utc))
        stara = {"regula": "x", "ts": "2026-10-11T07:59:00Z"}
        swieza = {"regula": "x", "ts": "2026-10-11T08:01:00Z"}
        self.assertEqual(T.przytnij_odlozone([stara, swieza], teraz, self.iso_ms), [swieza])
        duzo = [{"regula": str(i), "ts": "2026-10-12T07:00:00Z"} for i in range(30)]
        wynik = T.przytnij_odlozone(duzo, teraz, self.iso_ms)
        self.assertEqual(len(wynik), T.ODLOZONE_MAKS)
        self.assertEqual(wynik[-1]["regula"], "29")


if __name__ == "__main__":
    unittest.main()
