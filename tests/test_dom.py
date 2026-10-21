#!/usr/bin/env python3
"""Reguły domu (dom.py): przewietrz, przed snem, zamknij okno, czujniki w pokojach — i planer
powiadomień domu.

    python -m unittest discover -s tests -v

Epizody z prawdziwych odczytów leżą w tests/dane_dom/ (wiersze przepisane bez zmian
z data/2026-09.csv i data/2026-10.csv, bez baterii; prognoza z data/pogoda.json z 11.10
16:01 UTC). Fikstury nie zależą od pory uruchomienia: każdy test sam ustala „teraz".
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import dom  # noqa: E402
import telefony as T  # noqa: E402

WAW = ZoneInfo("Europe/Warsaw")
GODZ = 3600 * 1000
MIN = 60 * 1000
DANE = Path(__file__).resolve().parent / "dane_dom"
LAZIENKA = "bfd6f4f87fea9d866dvpve"
SYPIALNIA = "bf7e2a70935af7de78mjqt"
KUCHNIA = "bf5741c97c96fa85b1d7do"
SALON = "bf43cf664d6644420axva3"
KODY = {"va_temperature": {"kind": "temp", "unit": "℃", "scale": 1},
        "va_humidity": {"kind": "hum", "unit": "%", "scale": 0},
        "battery_state": {"kind": "battery", "unit": "%", "scale": 0}}
# Manifest jak data/index.json: cztery pokoje, wentylator z włącznikiem i dwór.
URZADZENIA = {
    "bfe38c4af789b0c8fbxte4": {"name": "FERSK VIND 2", "appliance": True,
                               "codes": {"switch": {"kind": "power", "unit": "", "scale": 0}}},
    LAZIENKA: {"name": "Łazienka", "codes": KODY},
    SYPIALNIA: {"name": "Sypialnia", "codes": KODY},
    KUCHNIA: {"name": "Kuchnia", "codes": KODY},
    SALON: {"name": "Salon", "codes": KODY},
    "zewnatrz": {"name": "Na zewnątrz", "external": True,
                 "codes": {"va_temperature": {"kind": "temp", "unit": "°C", "scale": 0},
                           "va_humidity": {"kind": "hum", "unit": "%", "scale": 0}}},
}
OPISY = dom.opisy_pokoi(URZADZENIA, json.loads((REPO / "pokoje.json").read_text(encoding="utf-8")))


def ms(tekst: str) -> int:
    return int(datetime.fromisoformat(tekst.replace("Z", "+00:00")).timestamp() * 1000)


def lok(r, m, d, h, mi=0, fold=0) -> int:
    return int(datetime(r, m, d, h, mi, tzinfo=WAW, fold=fold).timestamp() * 1000)


def odczyty(plik: str) -> list[dict]:
    with (DANE / plik).open(encoding="utf-8", newline="") as f:
        return [{**r, "ms": ms(r["ts"])} for r in csv.DictReader(f)]


def szereg(wiersze: list[dict], dev: str, kod: str, do_ms: int | None = None) -> dom.Szereg:
    return dom.Szereg([(w["ms"], float(w["value"])) for w in wiersze if w["device_id"] == dev
                       and w["code"] == kod and (do_ms is None or w["ms"] <= do_ms)])


def staly(wartosc: float, od_ms: int, do_ms: int, co_min: int = 30) -> dom.Szereg:
    return dom.Szereg([(t, wartosc) for t in range(od_ms, do_ms + 1, co_min * MIN)])


PAZDZIERNIK = odczyty("odczyty-2026-10-03-11.csv")
WRZESIEN = odczyty("odczyty-2026-09-28.csv")
POGODA_11_10 = json.loads((DANE / "pogoda-2026-10-11.json").read_text(encoding="utf-8"))


class TestGranica(unittest.TestCase):
    def test_wzor_rowny_prog_plesni_z_kolektora(self):
        """dom.py nie importuje fetch.py (dwie kopie modułu __main__), więc wzór jest
        powtórzony — tu pilnujemy, że to ten sam wzór na całej siatce."""
        import fetch
        for tp10 in range(-50, 351, 7):
            for td10 in range(-200, 351, 13):
                tp, td = tp10 / 10, td10 / 10
                self.assertAlmostEqual(dom.granica(tp, td), fetch.prog_plesni(tp, td), places=9, msg=(tp, td))

    def test_bez_danych_none_zamiast_zapasu_65(self):
        self.assertIsNone(dom.granica(None, 5.0))
        self.assertIsNone(dom.granica(20.0, None))
        self.assertEqual(dom.granica(20.0, 25.0), 80.0)


class TestPrzewietrz(unittest.TestCase):
    def test_kuchnia_28_09_rano_z_zapasem_przebiegu(self):
        """Prawdziwy epizod: kuchnia nad granicą od 6:07 (04:07:29 UTC), przebieg o 8:01:30
        to 1 godz. 54 min — wyzwala dzięki zapasowi 10 min. Bez zapasu („≥ 2 godz.") ta
        wilgotność nie dałaby nic: o 9:01 już spadła."""
        teraz = ms("2026-09-28T06:01:30Z")

        def licz(t):
            return dom.przewietrz(szereg(WRZESIEN, KUCHNIA, "va_humidity", t),
                                  szereg(WRZESIEN, KUCHNIA, "va_temperature", t),
                                  szereg(WRZESIEN, "zewnatrz", "va_temperature", t), t)

        wynik = licz(teraz)
        self.assertIsNotNone(wynik)
        self.assertEqual(wynik["od"], "2026-09-28T04:07:29Z")
        self.assertEqual(wynik["wilg"], 70.0)
        self.assertEqual(wynik["granica"], 68.0)
        with mock.patch.object(dom, "ZAPAS_PRZEBIEGU_MS", 0):
            self.assertIsNone(licz(teraz), "wersja bez zapasu przebiegu przepuściłaby ten epizod")
        self.assertIsNone(licz(ms("2026-09-28T05:01:30Z")), "54 min to jeszcze nie „przewietrz”")
        self.assertIsNone(licz(ms("2026-09-28T07:01:30Z")), "o 9:01 wilgotność już pod granicą")

    def test_granica_dwoch_godzin_minus_zapas(self):
        """Warunek: teraz − od ≥ 2 godz. − 10 min. 1 godz. 49 min 59 s nie, 1 godz. 50 min
        tak — a więc przebieg 1 godz. 59 min po pierwszym odczycie nad granicą już wysyła."""
        od = lok(2026, 10, 12, 8)
        temp, dwor = staly(21.0, od - 3 * GODZ, od + 3 * GODZ), staly(5.0, od - 3 * GODZ, od + 3 * GODZ, 60)
        wilg = dom.Szereg([(od - 30 * MIN, 50.0)] + [(od + k * 30 * MIN, 75.0) for k in range(4)])
        self.assertIsNone(dom.przewietrz(wilg, temp, dwor, od + 110 * MIN - 1000))
        self.assertEqual(dom.przewietrz(wilg, temp, dwor, od + 110 * MIN)["od"], dom.iso(od))
        self.assertIsNotNone(dom.przewietrz(wilg, temp, dwor, od + 119 * MIN))
        self.assertIsNotNone(dom.przewietrz(wilg, temp, dwor, od + 2 * GODZ))

    def test_dziura_ponad_2_5_godz_przerywa_serie(self):
        od = lok(2026, 10, 12, 8)
        temp, dwor = staly(21.0, od - GODZ, od + 6 * GODZ), staly(5.0, od - GODZ, od + 6 * GODZ, 60)
        wilg = dom.Szereg([(od, 75.0), (od + 3 * GODZ, 75.0), (od + 4 * GODZ, 75.0)])
        self.assertIsNone(dom.przewietrz(wilg, temp, dwor, od + 4 * GODZ + MIN),
                          "3 godz. bez odczytu to nie „cały czas nad granicą”")
        wilg = dom.Szereg([(od, 75.0), (od + 2 * GODZ, 75.0), (od + 4 * GODZ, 75.0)])
        self.assertEqual(dom.przewietrz(wilg, temp, dwor, od + 4 * GODZ + MIN)["od"], dom.iso(od))

    def test_odczyt_pod_granica_przerywa_serie(self):
        od = lok(2026, 10, 12, 8)
        temp, dwor = staly(21.0, od - GODZ, od + 6 * GODZ), staly(5.0, od - GODZ, od + 6 * GODZ, 60)
        wilg = dom.Szereg([(od, 75.0), (od + GODZ, 50.0), (od + 2 * GODZ, 75.0), (od + 3 * GODZ, 75.0)])
        self.assertIsNone(dom.przewietrz(wilg, temp, dwor, od + 3 * GODZ + MIN))

    def test_kazdy_odczyt_z_granica_ze_swojej_chwili(self):
        """Rano na dworze 15° (granica ~70%), teraz 3° (granica ~55%). 62% o 8:00 i 9:00 było
        pod ówczesną granicą — seria nad granicą zaczyna się dopiero o 10:00, więc o 11:01
        to 1 godz. Wersja z jedną, dzisiejszą granicą dla całej serii liczyłaby od 8:00."""
        od = lok(2026, 10, 12, 8)
        temp = staly(21.0, od - GODZ, od + 4 * GODZ)
        dwor = dom.Szereg([(od - GODZ, 15.0), (od, 15.0), (od + GODZ, 15.0), (od + 2 * GODZ, 3.0),
                           (od + 3 * GODZ, 3.0)])
        wilg = dom.Szereg([(od + k * GODZ, 62.0) for k in range(4)])
        self.assertGreater(62.0, dom.granica(21.0, 3.0))
        self.assertLess(62.0, dom.granica(21.0, 15.0))
        self.assertIsNone(dom.przewietrz(wilg, temp, dwor, od + 3 * GODZ + MIN))

    def test_stary_ostatni_odczyt_i_brak_dworu(self):
        od = lok(2026, 10, 12, 8)
        temp, dwor = staly(21.0, od - GODZ, od + 8 * GODZ), staly(5.0, od - GODZ, od + 8 * GODZ, 60)
        wilg = dom.Szereg([(od + k * GODZ, 75.0) for k in range(4)])
        self.assertIsNotNone(dom.przewietrz(wilg, temp, dwor, od + 6 * GODZ))
        self.assertIsNone(dom.przewietrz(wilg, temp, dwor, od + 6 * GODZ + 1000),
                          "ostatni odczyt sprzed ponad 3 godz. nie mówi, co jest teraz")
        self.assertIsNone(dom.przewietrz(wilg, temp, dom.Szereg([]), od + 4 * GODZ),
                          "bez dworu nie ma granicy — reguła milczy, nie zgaduje 65%")


class TestOkno(unittest.TestCase):
    def licz(self, dev: str, t: int, wiersze=PAZDZIERNIK):
        return dom.okno(szereg(wiersze, dev, "va_temperature", t), szereg(wiersze, dev, "va_humidity", t),
                        szereg(wiersze, "zewnatrz", "va_temperature", t).najblizsza(t), t)

    def przebiegi(self, dev: str, od: str, do: str, co_min: int = 10):
        return {t: self.licz(dev, t) for t in range(ms(od), ms(do) + 1, co_min * MIN)}

    def test_farelka_8_10_nie_daje_okna(self):
        """Łazienka 8.10 rano: farelka 21,9 → 26,5 °C w 12 min, stygnięcie do 22,4 °C w godzinę
        (wilgotność przy tym spada o 4 pkt, więc „robi się zimno" też przechodzi). Przebieg
        co 10 min przez cały dzień: ani razu „zamknij okno". Wersja bez poziomu bazowego
        (A ≤ baza + 1 i ostatni ≥ 1,5° pod bazą) daje tu alarm — test ją odrzuca."""
        wyniki = self.przebiegi(LAZIENKA, "2026-10-08T06:00:00Z", "2026-10-08T16:00:00Z")
        self.assertEqual([t for t, o in wyniki.items() if o], [])
        with mock.patch.multiple(dom, OKNO_PONAD_BAZE=float("inf"), OKNO_PONIZEJ_BAZY=float("-inf")):
            bez_bazy = [dom.iso(t) for t, o in self.przebiegi(LAZIENKA, "2026-10-08T06:00:00Z",
                                                              "2026-10-08T16:00:00Z").items() if o]
        self.assertTrue(bez_bazy, "fikstura nie odróżnia wersji bez poziomu bazowego")

    def test_salon_6_10_wietrzenie_w_trakcie(self):
        """Prawdziwe wietrzenie: Salon 6.10, 21,3 °C o 22:06, potem 20,8, 20,3, 19,8 i 18,8 °C
        o 23:32 (na dworze 16 °C). Przebieg o 23:35 widzi otwarte okno od 22:06."""
        o = self.licz(SALON, ms("2026-10-06T21:35:00Z"))
        self.assertEqual(o, {"od": "2026-10-06T20:06:04Z", "przed": 21.3, "teraz": 18.8, "spadek": 2.5})

    def test_salon_6_10_po_zamknieciu_juz_nie(self):
        """O północy temperatura już wraca (18,8 → 19,3 → 19,8 °C), okno jest zamknięte.
        Wersja bez warunku „jeszcze nie wraca" (prototyp) mówiłaby „Zamknij okno w salonie?"
        — to jedyne trafienie reguły w 14 dobach prawdziwych danych (pomiar B-DOM)."""
        polnoc = ms("2026-10-06T22:01:30Z")
        self.assertIsNone(self.licz(SALON, polnoc))
        with mock.patch.object(dom, "OKNO_JUZ_WRACA", float("inf")):
            self.assertIsNotNone(self.licz(SALON, polnoc))

    def test_symulacja_z_prototypu(self):
        """Podgląd „Otwarte okno" z prototypu: baza 21,3° (5:00–7:00), potem 21,2 → 19,6 → 18,4 °C
        i wilgotność 57 → 54 → 52%, na dworze 10 °C. „Od 8:00 spadło 2,8°"."""
        t = lambda h: lok(2026, 10, 12, h)  # noqa: E731
        temp = dom.Szereg([(t(5), 21.3), (t(6), 21.3), (t(7), 21.3), (t(8), 21.2), (t(9), 19.6), (t(10), 18.4)])
        wilg = dom.Szereg([(t(5), 57.0), (t(6), 57.0), (t(7), 57.0), (t(8), 57.0), (t(9), 54.0), (t(10), 52.0)])
        o = dom.okno(temp, wilg, 10.0, t(10) + MIN)
        self.assertEqual(o, {"od": dom.iso(t(8)), "przed": 21.2, "teraz": 18.4, "spadek": 2.8})
        self.assertIsNone(dom.okno(temp, wilg, 18.0, t(10) + MIN), "na dworze ciepło — to nie okno")
        self.assertIsNone(dom.okno(temp, wilg, None, t(10) + MIN))
        self.assertIsNone(dom.okno(temp, wilg, 10.0, t(8) + 6 * GODZ + 2 * MIN), "A sprzed 6 godz. nie liczy się")
        tytul, tresc = dom._tekst_okno([OPISY[SYPIALNIA]], [o], WAW)
        self.assertEqual((tytul, tresc), ("Zamknij okno w sypialni?", "Od 8:00 spadło 2,8° (z 21,2 do 18,4°)."))

    def test_lato_to_nie_sezon_grzewczy(self):
        """Kuchnia 23.08: wieczorne chłodzenie przez okno, 25,2 → 22,5 °C, wilgotność 56 → 48%.
        Wszystkie warunki spadku przechodzą, ale to sierpień — okno otwarte celowo. Bez
        bramki sezonu grzewczego reguła trzymała „Zamknij okno w kuchni?" 6 godzin."""
        sierpien = odczyty("odczyty-2026-08-23.csv")
        teraz = ms("2026-08-23T19:30:00Z")
        self.assertIsNone(dom.stan_domu(sierpien, URZADZENIA, None, teraz, WAW)["pokoje"][KUCHNIA]["okno"])
        with mock.patch.object(dom, "SEZON_GRZEWCZY", tuple(range(1, 13))):
            o = dom.stan_domu(sierpien, URZADZENIA, None, teraz, WAW)["pokoje"][KUCHNIA]["okno"]
        self.assertEqual(o["od"], "2026-08-23T18:22:39Z")

    def test_lazienka_bez_okna_13_10(self):
        """Prawdziwe odczyty: Łazienka 13.10 po gorącej wodzie 24,2 → 21,1 °C w 25 min i o 17:01
        przyszło „Zamknij okno w łazience?” — w pokoju, który okna nie ma. Fikstura kończy się
        na 14:39 UTC, bo tyle miał wtedy kolektor (treść: „z 22,8 do 21,1°”). Pokój bez okna
        w pokoje.json nie dostaje tej reguły; strażnik: bez `bez_okna` reguła trafia."""
        wiersze = odczyty("odczyty-2026-10-13-lazienka.csv")
        teraz = ms("2026-10-13T15:01:31Z")
        self.assertIsNotNone(dom.stan_domu(wiersze, URZADZENIA, None, teraz, WAW)["pokoje"][LAZIENKA]["okno"])
        bez = [d for d, o in OPISY.items() if not o["okno"]]
        self.assertEqual(bez, [LAZIENKA])
        self.assertIsNone(dom.stan_domu(wiersze, URZADZENIA, None, teraz, WAW, bez_okna=bez)["pokoje"][LAZIENKA]["okno"])

    def test_prog_1_5_bez_szumu_float(self):
        """16,4 − 14,9 liczone wprost na float to 1,4999999999999982 — spadek równo o próg
        musi przejść tak samo jak 21,3 − 19,8."""
        t = lambda mi: lok(2026, 10, 12, 8) + mi * MIN  # noqa: E731
        temp = dom.Szereg([(t(-120), 16.4), (t(-60), 16.4), (t(0), 16.4), (t(30), 14.9), (t(50), 14.9)])
        wilg = dom.Szereg([(t(k), 50.0) for k in (-120, -60, 0, 30, 50)])
        self.assertLess(16.4 - 14.9, 1.5)
        self.assertIsNotNone(dom.okno(temp, wilg, 5.0, t(55)))


class TestNoc(unittest.TestCase):
    TERAZ = ms("2026-10-11T16:01:25Z")       # ostatnia zbiórka przed fiksturą, 18:01 w Warszawie

    def test_lazienka_przed_snem_11_10(self):
        """Prawdziwe dane: noc 11/12.10 najzimniej 7,6° (6:00), Łazienka 21,3 °C, zwykle
        w nocy do 61,3% (maksima 59, 64, 65, 62, 63, 53, 63) przy granicy 62,0% —
        ostrzeżenie, bo zapas < 2 pkt."""
        stan = dom.stan_domu(PAZDZIERNIK, URZADZENIA, POGODA_11_10, self.TERAZ, WAW)
        self.assertEqual(stan["pokoje"][LAZIENKA]["noc"],
                         {"noc": "2026-10-11", "t_min": 7.6, "granica": 62.0, "zwykle": 61.3, "ostrz": True})

    def test_kuchnia_tuz_pod_granica(self):
        """Kuchnia z podglądu (20,1 °C, noc do 7,8°): zwykle 61,43%, granica − 2 = 61,47% —
        bez ostrzeżenia. Pierwsza wersja prototypu brała odczyty od 22:00 i wychodziło 61,57%
        (ostrzeżenie); porównanie zaokrąglonych (61 ≥ 63 − 2) też by ostrzegało."""
        wilg = szereg(PAZDZIERNIK, KUCHNIA, "va_humidity", self.TERAZ)
        temp = dom.Szereg([(self.TERAZ, 20.1)])
        noc = dom.noc_pokoju(temp, wilg, 7.8, self.TERAZ, WAW)
        self.assertFalse(noc["ostrz"])
        self.assertAlmostEqual(dom.zwykle_w_nocy(wilg, "2026-10-11", WAW), 61.43, places=2)
        self.assertGreaterEqual(round(dom.zwykle_w_nocy(wilg, "2026-10-11", WAW)), round(dom.granica(20.1, 7.8)) - 2)
        with mock.patch.object(dom, "ZWYKLE_OD_H", 22):
            self.assertTrue(dom.noc_pokoju(temp, wilg, 7.8, self.TERAZ, WAW)["ostrz"])

    def test_ktora_noc(self):
        self.assertEqual(dom.klucz_nocy(lok(2026, 10, 12, 21, 59), WAW), "2026-10-12")
        self.assertEqual(dom.klucz_nocy(lok(2026, 10, 12, 22), WAW), "2026-10-12")
        self.assertEqual(dom.klucz_nocy(lok(2026, 10, 13, 6, 59), WAW), "2026-10-12")
        self.assertEqual(dom.klucz_nocy(lok(2026, 10, 13, 7), WAW), "2026-10-13")

    def test_najzimniej_tylko_noc_i_od_teraz_minus_godzina(self):
        def prognoza(od, punkty):
            return {"hourly": {"time": [dom.iso(od + k * GODZ) for k in range(len(punkty))],
                               "temperature_2m": punkty}}
        teraz = lok(2026, 10, 12, 18, 5)
        # 17:00 … 9:00 następnego dnia; najzimniej w dzień (−5° o 9:00) się nie liczy
        punkty = [9, 8, 7, 6, 5, 4.5, 4, 3, 2, 1, 1.5, 2, 2.5, 3, 3.5, 0, -5]
        self.assertEqual(dom.najzimniej_w_nocy(prognoza(lok(2026, 10, 12, 17), punkty), teraz, WAW), 1)
        siodma = list(punkty)
        siodma[14] = 0.5                     # 7:00 jeszcze należy do nocy
        self.assertEqual(dom.najzimniej_w_nocy(prognoza(lok(2026, 10, 12, 17), siodma), teraz, WAW), 0.5)
        # po północy: godziny sprzed teraz − 1 godz. odpadają (1° o 2:00 już minęło)
        teraz = lok(2026, 10, 13, 3, 30)
        self.assertEqual(dom.najzimniej_w_nocy(prognoza(lok(2026, 10, 12, 17), punkty), teraz, WAW), 1.5)
        self.assertIsNone(dom.najzimniej_w_nocy(prognoza(lok(2026, 10, 13, 8), [1, 2]), lok(2026, 10, 13, 8), WAW),
                          "prognoza bez godzin nocy")
        self.assertIsNone(dom.najzimniej_w_nocy(None, teraz, WAW))

    def test_zmiana_czasu_25_10(self):
        """Noc 24/25.10: o 3:00 zegar cofa się na 2:00. Powtórzona 2:00 to osobna godzina —
        noc z odczytami o 2:15, 2:15 (drugi raz), 3:15, 4:15 i 5:15 ma pięć godzin, a nie
        cztery. Prognoza z obiema 2:00 daje najzimniejszą z nich."""
        wilg = []
        for noc in range(17, 24):            # siedem zwykłych nocy, odczyty 23:30–6:30
            for h in (23, 0, 1, 2, 3, 4, 5, 6):
                dzien = noc if h == 23 else noc + 1
                wilg.append((lok(2026, 10, dzien, h, 30), 60.0))
        for h, fold in ((2, 0), (2, 1), (3, 0), (4, 0), (5, 0)):
            wilg.append((lok(2026, 10, 25, h, 15, fold), 70.0))
        sz = dom.Szereg(wilg)
        self.assertEqual(lok(2026, 10, 25, 2, 15, 1) - lok(2026, 10, 25, 2, 15, 0), GODZ)
        self.assertAlmostEqual(dom.zwykle_w_nocy(sz, "2026-10-25", WAW), (6 * 60 + 70) / 7)
        prognoza = {"hourly": {"time": [dom.iso(lok(2026, 10, 24, 22) + k * GODZ) for k in range(11)],
                               "temperature_2m": [8, 7, 6, 5, 4, 2, 3, 4, 5, 6, 7]}}
        # 22, 23, 0, 1, 2 (CEST), 2 (CET), 3, 4, 5, 6, 7 — jedenaście godzin czasu, noc 25.10 ma 10 h
        self.assertEqual(dom.najzimniej_w_nocy(prognoza, lok(2026, 10, 24, 21), WAW), 2)
        self.assertEqual(dom.klucz_nocy(lok(2026, 10, 25, 2, 30, 1), WAW), "2026-10-24")

    def test_noc_z_mniej_niz_5_godzinami_nie_liczy_sie(self):
        # noc 11/12.10: cztery godziny po 90% — nie liczy się; noc 12/13.10: pięć po 60%
        wilg = dom.Szereg([(lok(2026, 10, 12, h, 10), 90.0) for h in (0, 1, 2, 3)]
                          + [(lok(2026, 10, 13, h, 10), 60.0) for h in (0, 1, 2, 3, 4)])
        self.assertEqual(dom.zwykle_w_nocy(wilg, "2026-10-13", WAW), 60.0)
        self.assertIsNone(dom.zwykle_w_nocy(dom.Szereg([]), "2026-10-13", WAW))


class TestCzujnik(unittest.TestCase):
    def test_milczy_od_kursora_a_nie_od_teraz(self):
        """Ostatni odczyt 7 godz. przed „teraz", ale kolektor ma tylko 5 godz. świeżych logów
        (kursor 2 godz. temu, bo poprzednie przebiegi się spóźniły) — czujnik nie milczy."""
        teraz = lok(2026, 10, 12, 12)
        poczatek = teraz - dom.OKNO_ODCZYTOW_MS
        self.assertIsNone(dom.milczy_od(teraz - 7 * GODZ, teraz - 2 * GODZ, teraz, poczatek))
        self.assertEqual(dom.milczy_od(teraz - 7 * GODZ, None, teraz, poczatek), dom.iso(teraz - 7 * GODZ))
        self.assertEqual(dom.milczy_od(teraz - 8 * GODZ, teraz - 2 * GODZ, teraz, poczatek), dom.iso(teraz - 8 * GODZ))
        self.assertIsNone(dom.milczy_od(teraz - 8 * GODZ + 1000, teraz - 2 * GODZ, teraz, poczatek))
        self.assertEqual(dom.milczy_od(None, teraz, teraz, poczatek), dom.iso(poczatek))

    def test_stan_domu_nieodswiezony_nie_milczy(self):
        teraz = ms("2026-10-11T16:01:25Z") + 10 * GODZ
        stan = dom.stan_domu(PAZDZIERNIK, URZADZENIA, None, teraz, WAW)
        self.assertEqual(stan["pokoje"][LAZIENKA]["milczy_od"], "2026-10-11T15:12:52Z", "ostatni odczyt Łazienki")
        stan = dom.stan_domu(PAZDZIERNIK, URZADZENIA, None, teraz, WAW, nieodswiezone=[LAZIENKA])
        self.assertIsNone(stan["pokoje"][LAZIENKA]["milczy_od"])

    def test_bateria_ostatni_tekst(self):
        teraz = lok(2026, 10, 12, 12)
        wiersze = [{"ms": teraz - 2 * GODZ, "device_id": SALON, "code": "battery_state", "value": "low"},
                   {"ms": teraz - GODZ, "device_id": SALON, "code": "battery_state", "value": "Middle"},
                   {"ms": teraz - GODZ, "device_id": KUCHNIA, "code": "battery_state", "value": "42"}]
        pokoje = dom.stan_domu(wiersze, URZADZENIA, None, teraz, WAW)["pokoje"]
        self.assertEqual(pokoje[SALON]["bateria"], "middle")
        self.assertIsNone(pokoje[KUCHNIA]["bateria"])
        self.assertIsNone(pokoje[SYPIALNIA]["bateria"])


class TestStanDomu(unittest.TestCase):
    def test_ksztalt_i_zapis(self):
        teraz = ms("2026-10-11T16:01:25Z")
        stan = dom.stan_domu(PAZDZIERNIK, URZADZENIA, POGODA_11_10, teraz, WAW)
        self.assertEqual(stan["updated"], "2026-10-11T16:01:25Z")
        self.assertEqual(list(stan["pokoje"]), [LAZIENKA, SYPIALNIA, KUCHNIA, SALON],
                         "tylko pokoje, w kolejności manifestu — bez dworu i wentylatora")
        for dev, p in stan["pokoje"].items():
            self.assertEqual(list(p), ["przewietrz", "okno", "noc", "milczy_od", "bateria"])
        json.dumps(stan, allow_nan=False)
        kuchnia = stan["pokoje"][KUCHNIA]["noc"]
        for pole in ("t_min", "granica", "zwykle"):
            self.assertEqual(kuchnia[pole], round(kuchnia[pole], 1))

    def test_odczyty_z_przyszlosci_i_spoza_okna_nie_licza_sie(self):
        teraz = lok(2026, 10, 12, 12)
        wiersze = [{"ms": teraz + GODZ, "device_id": SALON, "code": "va_temperature", "value": "30"},
                   {"ms": teraz - 9 * 24 * GODZ, "device_id": SALON, "code": "va_temperature", "value": "30"}]
        self.assertEqual(dom.stan_domu(wiersze, URZADZENIA, None, teraz, WAW)["pokoje"][SALON]["milczy_od"],
                         dom.iso(teraz - dom.OKNO_ODCZYTOW_MS))

    def test_opisy_z_pokoje_json_a_bez_wpisu_z_nazwy(self):
        self.assertEqual(OPISY[LAZIENKA], {"nazwa": "Łazienka", "slug": "lazienka", "dop": "łazienki",
                                           "bier": "łazienkę", "miejsc": "łazience", "okno": False})
        self.assertTrue(OPISY[KUCHNIA]["okno"])
        opisy = dom.opisy_pokoi({"x1": {"name": "Pokój Ani", "codes": KODY}}, None)
        # pokoju spoza pokoje.json nie znamy — reguły okna zostają
        self.assertEqual(opisy["x1"], {"nazwa": "Pokój Ani", "slug": "pokoj-ani", "dop": "pokój Ani",
                                       "bier": "pokój Ani", "miejsc": "pokój Ani", "okno": True})


# ---------- planer ----------

PRZEWIETRZ = {"od": "2026-10-12T06:00:00Z", "wilg": 71.0, "granica": 63.2}
OKNO = {"od": "2026-10-12T17:40:00Z", "przed": 21.2, "teraz": 18.4, "spadek": 2.8}


def pokoj(**pola) -> dict:
    p = {"przewietrz": None, "okno": None, "noc": None, "milczy_od": None, "bateria": "middle"}
    p.update(pola)
    return p


def noc(data: str, ostrz: bool = True) -> dict:
    return {"noc": data, "t_min": 4.0, "granica": 60.4, "zwykle": 60.9, "ostrz": ostrz}


def ust(**zmiany) -> dict:
    u = dict(T.DOMYSLNE)
    u.update(zmiany)
    return u


def przebieg(pokoje: dict, poprz, teraz: int, tryb: str = "wlaczone", ustawienia=None, nieodswiezone=()):
    stan = {"updated": dom.iso(teraz), "pokoje": {d: pokoje.get(d, pokoj()) for d in OPISY}}
    wynik = dom.zaplanuj_powiadomienia(stan, poprz, teraz, WAW, tryb, f"p{teraz}", ustawienia, OPISY, nieodswiezone)
    # jak kolektor: przez JSON, z allow_nan=False
    return json.loads(json.dumps(wynik, ensure_ascii=False, allow_nan=False))


def nowe(wynik: dict, teraz: int) -> list[dict]:
    return [w for w in wynik["historia"] if w["przebieg"] == f"p{teraz}"]


class TestPlanerPrzewietrz(unittest.TestCase):
    def test_raz_na_epizod_i_plik_bez_zmian(self):
        t1 = lok(2026, 10, 12, 10, 1)
        w1 = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, None, t1)
        self.assertEqual(len(nowe(w1, t1)), 1)
        e = nowe(w1, t1)[0]
        self.assertEqual((e["regula"], e["pokoje"], e["tytul"], e["tag"], e["url"], e["telefony"], e["na_sucho"]),
                         ("przewietrz", ["Salon"], "Przewietrz salon", "przewietrz-salon", "#salon",
                          ["android", "iphone"], False))
        self.assertEqual(e["tresc"], "Salon: 71% od 2 godz., za wilgotno powyżej 63%.")
        t2 = t1 + GODZ
        w2 = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, w1, t2)
        self.assertEqual(nowe(w2, t2), [])
        self.assertEqual(json.dumps(w2, ensure_ascii=False, indent=1), json.dumps(w1, ensure_ascii=False, indent=1),
                         "bez zmian w stanie plik ma być identyczny — inaczej commit co godzinę")

    def test_pokoj_bez_okna_bez_powiadomienia(self):
        """Łazienka nie ma okna, a drzwi stoją otwarte: „Przewietrz łazienkę” przychodziło kilka
        razy w tygodniu bez niczego do zrobienia — właściciel 21.10: wyłączyć. Na ekranie zostaje
        (stan.json), na telefon nie idzie ani teraz, ani z kolejki po ciszy; pokój z oknem tak."""
        t = lok(2026, 10, 12, 10, 1)
        w = przebieg({LAZIENKA: pokoj(przewietrz=PRZEWIETRZ)}, None, t)
        self.assertEqual(nowe(w, t), [])
        self.assertIsNone(w["stan_regul"][LAZIENKA]["przewietrz"])
        w = przebieg({LAZIENKA: pokoj(przewietrz=PRZEWIETRZ), KUCHNIA: pokoj(przewietrz=PRZEWIETRZ)}, None, t)
        (e,) = nowe(w, t)
        self.assertEqual(e["pokoje"], ["Kuchnia"])
        # pozycja łazienki w kolejce sprzed zmiany nie wychodzi rano
        u = {"android": ust(), "iphone": ust(cisza=False)}
        w = przebieg({}, None, lok(2026, 10, 12, 22, 1), ustawienia=u)
        w["telefony"]["android"]["odlozone"] = [{"regula": "przewietrz", "obiekt": LAZIENKA, "ts": dom.iso(lok(2026, 10, 12, 22, 1))}]
        rano = lok(2026, 10, 13, 8, 1)
        w = przebieg({LAZIENKA: pokoj(przewietrz=PRZEWIETRZ)}, w, rano, ustawienia=u)
        self.assertEqual(nowe(w, rano), [])

    def test_kilka_pokoi_jeden_wpis(self):
        t = lok(2026, 10, 12, 10, 1)
        w = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ), KUCHNIA: pokoj(przewietrz=dict(PRZEWIETRZ, wilg=63.0))},
                     None, t)
        (e,) = nowe(w, t)
        self.assertEqual(e["tytul"], "Przewietrz: kuchnia, salon")
        self.assertEqual(e["url"], "#dom")
        self.assertEqual(e["tag"], "przewietrz-kuchnia-salon")
        # 63% i granica 63,2 po zaokrągleniu byłyby „63%, za wilgotno powyżej 63%"
        self.assertIn("Kuchnia: 63% od 2 godz., za wilgotno powyżej 63,2%.", e["tresc"])

    def test_polowki_w_gore_jak_na_karcie(self):
        """Karta pokazuje liczby ze stan.json przez Intl.NumberFormat (połówka w górę), więc
        granica 62,5 to na karcie 63%. Format Pythona dawał w powiadomieniu 62% (połówka do
        parzystej) — przegląd, B2/C1. Przy wilgotności 63 i granicy 62,5 po zaokrągleniu
        obie są 63, więc granica idzie z miejscem po przecinku."""
        t = lok(2026, 10, 12, 10, 1)
        w = przebieg({SALON: pokoj(przewietrz=dict(PRZEWIETRZ, granica=62.5)),
                      KUCHNIA: pokoj(przewietrz=dict(PRZEWIETRZ, wilg=63.0, granica=62.5))}, None, t)
        (e,) = nowe(w, t)
        self.assertEqual(e["tresc"].splitlines(), ["Kuchnia: 63% od 2 godz., za wilgotno powyżej 62,5%.",
                                                   "Salon: 71% od 2 godz., za wilgotno powyżej 63%."])
        for x in range(0, 100):
            self.assertEqual(dom._pl(x + 0.5, 0), str(x + 1), "Math.round na stronie")
        self.assertEqual(dom._pl(2.25, 1), "2,3")

    def test_koniec_epizodu_i_najwyzej_dwa_na_dobe(self):
        teraz, poprz, wyslane = lok(2026, 10, 12, 9, 1), None, []
        for _ in range(3):                   # trzy epizody w jeden dzień
            poprz = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, poprz, teraz)
            wyslane += nowe(poprz, teraz)
            teraz += GODZ
            poprz = przebieg({}, poprz, teraz)
            self.assertIsNone(poprz["stan_regul"][SALON]["przewietrz"])
            teraz += GODZ
        self.assertEqual(len(wyslane), 2, "trzeci epizod tej doby nie wychodzi")
        nastepny = lok(2026, 10, 13, 9, 1)
        poprz = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, poprz, nastepny)
        self.assertEqual(len(nowe(poprz, nastepny)), 1)

    def test_nieodswiezony_pokoj_nie_konczy_epizodu(self):
        t1 = lok(2026, 10, 12, 10, 1)
        w = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, None, t1)
        w = przebieg({}, w, t1 + GODZ, nieodswiezone=[SALON])
        self.assertIsNotNone(w["stan_regul"][SALON]["przewietrz"])
        w = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, w, t1 + 2 * GODZ)
        self.assertEqual(nowe(w, t1 + 2 * GODZ), [], "awaria Tuya nie może dać drugiego „przewietrz”")

    def test_wspolna_noc_nic_i_rano_wychodzi(self):
        noc_t = lok(2026, 10, 12, 23, 1)
        w = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, None, noc_t)
        self.assertEqual(nowe(w, noc_t), [])
        self.assertIsNone(w["stan_regul"][SALON]["przewietrz"]["wyslano"])
        self.assertEqual(w["telefony"]["android"]["odlozone"], [], "noc wszystkich to nie kolejka")
        rano = lok(2026, 10, 13, 8, 1)
        w = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, w, rano)
        self.assertEqual([e["telefony"] for e in nowe(w, rano)], [["android", "iphone"]])

    def test_kolejka_per_telefon(self):
        """Android ma ciszę 21–8, iPhone bez ciszy. O 22:01 wpis idzie tylko do iPhone'a,
        Android dostaje pozycję w kolejce; o 8:01 — wpis „odłożone" tylko do niego, a kolejka
        pusta w tym samym wyniku."""
        u = {"android": ust(), "iphone": ust(cisza=False)}
        wieczor = lok(2026, 10, 12, 22, 1)
        w = przebieg({KUCHNIA: pokoj(przewietrz=PRZEWIETRZ)}, None, wieczor, ustawienia=u)
        self.assertEqual([e["telefony"] for e in nowe(w, wieczor)], [["iphone"]])
        self.assertEqual([(p["regula"], p["obiekt"]) for p in w["telefony"]["android"]["odlozone"]],
                         [("przewietrz", KUCHNIA)])
        noc_t = lok(2026, 10, 13, 3, 1)
        w = przebieg({KUCHNIA: pokoj(przewietrz=PRZEWIETRZ)}, w, noc_t, ustawienia=u)
        self.assertEqual(nowe(w, noc_t), [])
        rano = lok(2026, 10, 13, 8, 1)
        w2 = przebieg({KUCHNIA: pokoj(przewietrz=PRZEWIETRZ)}, w, rano, ustawienia=u)
        (e,) = nowe(w2, rano)
        self.assertEqual((e["telefony"], e.get("odlozone"), e["tytul"]), (["android"], True, "Przewietrz kuchnię"))
        self.assertEqual(w2["telefony"]["android"]["odlozone"], [])
        # rano już sucho: pozycja odpada, kolejka i tak się czyści
        w3 = przebieg({}, w, rano, ustawienia=u)
        self.assertEqual(nowe(w3, rano), [])
        self.assertEqual(w3["telefony"]["android"]["odlozone"], [])
        # przed ranem Android wyłączył „przewietrz" — nic nie wychodzi
        w4 = przebieg({KUCHNIA: pokoj(przewietrz=PRZEWIETRZ)}, w, rano,
                      ustawienia={"android": ust(przewietrz=False), "iphone": ust(cisza=False)})
        self.assertEqual(nowe(w4, rano), [])

    def test_odlozone_nie_zjadaja_limitu_doby(self):
        u = {"android": ust(), "iphone": ust(cisza=False)}
        w = przebieg({KUCHNIA: pokoj(przewietrz=PRZEWIETRZ)}, None, lok(2026, 10, 12, 22, 1), ustawienia=u)
        teraz = lok(2026, 10, 13, 8, 1)
        w = przebieg({KUCHNIA: pokoj(przewietrz=PRZEWIETRZ)}, w, teraz, ustawienia=u)
        wyslane = 0
        for _ in range(3):
            teraz += GODZ
            w = przebieg({}, w, teraz, ustawienia=u)
            teraz += GODZ
            w = przebieg({KUCHNIA: pokoj(przewietrz=PRZEWIETRZ)}, w, teraz, ustawienia=u)
            wyslane += len(nowe(w, teraz))
        self.assertEqual(wyslane, 2)


class TestPlanerKolejka(unittest.TestCase):
    def test_przycinanie_ttl_i_limit(self):
        """Kolejka telefonu w ciszy traci pozycje starsze niż doba i trzyma najwyżej
        ODLOZONE_MAKS najnowszych (telefony.przytnij_odlozone) — inaczej pozycje pokoju,
        który zniknął z manifestu, albo błąd planera rosłyby w publicznym pliku bez końca.
        Przegląd, B4: bez przycinania wszystkie testy domu przechodziły."""
        noc_t = lok(2026, 10, 12, 23, 1)
        stara = {"regula": "przewietrz", "obiekt": "pokoj-x", "ts": dom.iso(noc_t - 24 * GODZ - MIN)}
        swieze = [{"regula": "przewietrz", "obiekt": f"pokoj-{i}", "ts": dom.iso(noc_t - (30 - i) * MIN)}
                  for i in range(T.ODLOZONE_MAKS + 5)]
        poprz = {"tryb": "wlaczone", "wlaczone_od": "2026-10-01T00:00:00Z", "historia": [], "stan_regul": {},
                 "telefony": {"android": {"odlozone": [stara] + swieze}}}
        w = przebieg({}, poprz, noc_t)
        self.assertEqual([p["obiekt"] for p in w["telefony"]["android"]["odlozone"]],
                         [p["obiekt"] for p in swieze[-T.ODLOZONE_MAKS:]])

    def test_pozycja_starsza_niz_doba_nie_wychodzi(self):
        """Android w ciszy dostał pozycję „przewietrz kuchnię", ale przebiegi stały ponad
        dobę. Pierwszy przebieg po ciszy nie doręcza tak starej sprawy jako „odłożonej"."""
        u = {"android": ust(), "iphone": ust(cisza=False)}
        w = przebieg({KUCHNIA: pokoj(przewietrz=PRZEWIETRZ)}, None, lok(2026, 10, 12, 22, 1), ustawienia=u)
        self.assertEqual(len(w["telefony"]["android"]["odlozone"]), 1)
        rano = lok(2026, 10, 13, 8, 1)
        w["telefony"]["android"]["odlozone"][0]["ts"] = dom.iso(rano - 24 * GODZ - MIN)
        w2 = przebieg({KUCHNIA: pokoj(przewietrz=PRZEWIETRZ)}, w, rano, ustawienia=u)
        self.assertEqual(nowe(w2, rano), [])
        self.assertEqual(w2["telefony"]["android"]["odlozone"], [])
        # strażnik: pozycja sprzed niecałej doby wychodzi
        w["telefony"]["android"]["odlozone"][0]["ts"] = dom.iso(rano - 24 * GODZ + MIN)
        w3 = przebieg({KUCHNIA: pokoj(przewietrz=PRZEWIETRZ)}, w, rano, ustawienia=u)
        self.assertEqual([(e["telefony"], e.get("odlozone")) for e in nowe(w3, rano)], [(["android"], True)])


class TestPlanerPrzedSnem(unittest.TestCase):
    def test_raz_na_noc_przed_cisza(self):
        dzis = "2026-10-12"
        wieczor = lok(2026, 10, 12, 19, 1)
        w = przebieg({KUCHNIA: pokoj(noc=noc(dzis)), SALON: pokoj(noc=noc(dzis, ostrz=False))}, None, wieczor)
        (e,) = nowe(w, wieczor)
        self.assertEqual((e["regula"], e["tytul"], e["tag"], e["url"], e["telefony"]),
                         ("przed-snem", "Przewietrz przed snem: kuchnia", "przed-snem", "#kuchnia",
                          ["android", "iphone"]))
        self.assertEqual(e["tresc"], "Kuchnia: w nocy za wilgotno od ok. 60%, zwykle masz do 61%.")
        self.assertEqual(w["telefony"]["android"]["przed_snem"], dzis)
        pozniej = lok(2026, 10, 12, 20, 1)
        w = przebieg({KUCHNIA: pokoj(noc=noc(dzis))}, w, pozniej)
        self.assertEqual(nowe(w, pozniej), [], "raz na noc")
        jutro = lok(2026, 10, 13, 19, 1)
        w = przebieg({KUCHNIA: pokoj(noc=noc("2026-10-13"))}, w, jutro)
        self.assertEqual(len(nowe(w, jutro)), 1)

    def test_pokoj_bez_okna_tylko_na_ekranie(self):
        """Łazienka nie ma okna, a drzwi i tak stoją otwarte: wieczorne „przewietrz łazienkę”
        szło 9 wieczorów na 10 (12–21.10) bez niczego, co da się zrobić. Na telefon idą
        tylko pokoje z oknem; łazienka zostaje w stan.json, więc ekran dalej ją pokazuje."""
        dzis, t = "2026-10-12", lok(2026, 10, 12, 19, 1)
        self.assertFalse(OPISY[LAZIENKA]["okno"])
        w = przebieg({LAZIENKA: pokoj(noc=noc(dzis))}, None, t)
        self.assertEqual(nowe(w, t), [])
        self.assertIsNone(w["telefony"]["android"]["przed_snem"], "noc nie jest zużyta — kuchnia może jeszcze przyjść")
        w = przebieg({LAZIENKA: pokoj(noc=noc(dzis)), KUCHNIA: pokoj(noc=noc(dzis))}, None, t)
        (e,) = nowe(w, t)
        self.assertEqual((e["tytul"], e["pokoje"]), ("Przewietrz przed snem: kuchnia", ["Kuchnia"]))

    def test_okno_kazdego_telefonu_i_nigdy_kolejka(self):
        """Android: cisza 21–8, okno 19–21. iPhone: cisza 23–7, okno 21–23. O 19:01 tylko
        Android, o 21:01 tylko iPhone (Android już śpi — nic do kolejki)."""
        u = {"android": ust(), "iphone": ust(od=23, do=7)}
        dzis = "2026-10-12"
        t1 = lok(2026, 10, 12, 19, 1)
        w = przebieg({KUCHNIA: pokoj(noc=noc(dzis))}, None, t1, ustawienia=u)
        self.assertEqual([e["telefony"] for e in nowe(w, t1)], [["android"]])
        t2 = lok(2026, 10, 12, 21, 1)
        w = przebieg({KUCHNIA: pokoj(noc=noc(dzis))}, w, t2, ustawienia=u)
        self.assertEqual([e["telefony"] for e in nowe(w, t2)], [["iphone"]])
        self.assertEqual((w["telefony"]["android"]["odlozone"], w["telefony"]["iphone"]["odlozone"]), ([], []))
        t3 = lok(2026, 10, 12, 23, 30)
        w = przebieg({KUCHNIA: pokoj(noc=noc(dzis))}, w, t3, ustawienia=u)
        self.assertEqual(nowe(w, t3), [])

    def test_polowki_w_gore_jak_na_karcie(self):
        """Linia nocna karty (nocZdanie) pokazuje granicę i „zwykle" ze stan.json połówką
        w górę: 62,5 i 60,5 to 63 i 61, a nie 62 i 60 (przegląd, B2 — Kuchnia 11.10)."""
        t = lok(2026, 10, 12, 19, 1)
        w = przebieg({KUCHNIA: pokoj(noc=dict(noc("2026-10-12"), granica=62.5, zwykle=60.5))}, None, t)
        (e,) = nowe(w, t)
        self.assertEqual(e["tresc"], "Kuchnia: w nocy za wilgotno od ok. 63%, zwykle masz do 61%.")

    def wieczor(self, ustawienia, od_h=12, do_h=24) -> dict:
        """Przebiegi co godzinę dnia 12.10 od `od_h`:01 → {telefon: [godziny „przed snem"]}."""
        dzis, w, kto = "2026-10-12", None, {t: [] for t in T.TELEFONY}
        for h in range(od_h, do_h):
            teraz = lok(2026, 10, 12, h, 1)
            w = przebieg({KUCHNIA: pokoj(noc=noc(dzis))}, w, teraz, ustawienia=ustawienia)
            for e in nowe(w, teraz):
                self.assertEqual(e["regula"], "przed-snem")
                for t in e["telefony"]:
                    self.assertFalse(T.w_ciszy(ustawienia[t], datetime.fromtimestamp(teraz / 1000, WAW)),
                                     f"{t} o {h}:01 ma ciszę")
                    kto[t].append(h)
        return kto

    def test_cisza_18_8_przed_snem_16_17(self):
        """Cisza 18–8 dostawała okno 19–21, czyli w środku swojej ciszy — „przed snem" nie
        przychodziło nigdy (przegląd, B3). Teraz o 16:01, raz na noc; iPhone z domyślną
        ciszą 21–8 dalej o 19:01."""
        kto = self.wieczor({"android": ust(od=18, do=8), "iphone": ust()})
        self.assertEqual(kto, {"android": [16], "iphone": [19]})

    def test_nigdy_w_ciszy_nawet_gdy_okno_na_nia_zachodzi(self):
        """Przy bardzo długiej ciszy okno przed nią zachodzi na jej koniec: cisza 18–17 ma
        okno 16–18, ale do 17:00 telefon jeszcze śpi; cisza 4–21 ma zapasowe 19–21 w całości
        w ciszy. Planer nie wysyła wtedy nic — odrzuca planer bez warunku `not w_ciszy`."""
        kto = self.wieczor({"android": ust(od=18, do=17), "iphone": ust(od=4, do=21)})
        self.assertEqual(kto, {"android": [17], "iphone": []})

    def test_inna_noc_albo_wylaczone_przewietrz(self):
        t = lok(2026, 10, 12, 19, 1)
        self.assertEqual(nowe(przebieg({KUCHNIA: pokoj(noc=noc("2026-10-13"))}, None, t), t), [])
        u = {"android": ust(przewietrz=False), "iphone": ust(przewietrz=False)}
        self.assertEqual(nowe(przebieg({KUCHNIA: pokoj(noc=noc("2026-10-12"))}, None, t, ustawienia=u), t), [])


class TestPlanerOkno(unittest.TestCase):
    def test_nigdy_w_kolejce(self):
        u = {"android": ust(), "iphone": ust(cisza=False)}
        t = lok(2026, 10, 12, 22, 1)
        w = przebieg({SYPIALNIA: pokoj(okno=OKNO)}, None, t, ustawienia=u)
        (e,) = nowe(w, t)
        self.assertEqual((e["regula"], e["telefony"], e["tytul"], e["tag"], e["url"]),
                         ("okno", ["iphone"], "Zamknij okno w sypialni?", "okno-sypialnia", "#sypialnia"))
        self.assertEqual(e["tresc"], "Od 19:40 spadło 2,8° (z 21,2 do 18,4°).")
        self.assertEqual(w["telefony"]["android"]["odlozone"], [])
        rano = lok(2026, 10, 13, 8, 1)
        w = przebieg({SYPIALNIA: pokoj(okno=OKNO)}, w, rano, ustawienia=u)
        self.assertEqual(nowe(w, rano), [], "okno raz na epizod, bez porannego dostarczenia")

    def test_wszyscy_w_ciszy_epizod_czeka(self):
        t = lok(2026, 10, 12, 22, 1)
        w = przebieg({SYPIALNIA: pokoj(okno=OKNO)}, None, t)
        self.assertEqual(nowe(w, t), [])
        self.assertIsNone(w["stan_regul"][SYPIALNIA]["okno"]["wyslano"])
        rano = lok(2026, 10, 13, 8, 1)
        w = przebieg({SYPIALNIA: pokoj(okno=OKNO)}, w, rano)
        self.assertEqual([e["telefony"] for e in nowe(w, rano)], [["android", "iphone"]])
        w = przebieg({}, w, rano + GODZ)
        self.assertIsNone(w["stan_regul"][SYPIALNIA]["okno"])

    def test_kilka_pokoi(self):
        t = lok(2026, 10, 12, 18, 1)
        w = przebieg({SYPIALNIA: pokoj(okno=OKNO), SALON: pokoj(okno=dict(OKNO, spadek=1.6))}, None, t)
        (e,) = nowe(w, t)
        self.assertEqual(e["tytul"], "Zamknij okna? sypialnia i salon")
        self.assertEqual(e["tresc"].splitlines()[1], "Salon: od 19:40 spadło 1,6° (z 21,2 do 18,4°).")


class TestPlanerCzujniki(unittest.TestCase):
    def test_bateria_low_middle_low_jeden_alarm(self):
        t, w, alarmy = lok(2026, 10, 12, 8, 1), None, []
        for bateria in ("low", "middle", "low", "middle", "low"):
            w = przebieg({KUCHNIA: pokoj(bateria=bateria)}, w, t)
            alarmy += nowe(w, t)
            t += 2 * GODZ
        self.assertEqual([(e["tytul"], e["tresc"]) for e in alarmy],
                         [("Słaba bateria czujnika w kuchni", "Kuchnia: bateria na wyczerpaniu, wymień ogniwo.")])
        w = przebieg({KUCHNIA: pokoj(bateria="high")}, w, t)
        self.assertEqual(w["stan_regul"][KUCHNIA]["czujniki"], {}, "nowa bateria kończy epizod")
        w = przebieg({KUCHNIA: pokoj(bateria="low")}, w, t + GODZ)
        self.assertEqual(len(nowe(w, t + GODZ)), 1)

    def test_cisza_i_nieodswiezony(self):
        t = lok(2026, 10, 12, 10, 1)
        w = przebieg({SALON: pokoj(milczy_od="2026-10-12T01:05:00Z")}, None, t)
        (e,) = nowe(w, t)
        self.assertEqual((e["tytul"], e["tresc"], e["tag"]),
                         ("Czujnik w salonie milczy", "Salon: ostatni odczyt 12.10 o 3:05.", "czujniki-salon"))
        # awaria Tuya: stan_domu nie daje „milczy", ale epizod trwa
        w = przebieg({}, w, t + GODZ, nieodswiezone=[SALON])
        self.assertIn("cisza", w["stan_regul"][SALON]["czujniki"])
        w = przebieg({SALON: pokoj(milczy_od="2026-10-12T01:05:00Z")}, w, t + 2 * GODZ)
        self.assertEqual(nowe(w, t + 2 * GODZ), [])
        w = przebieg({}, w, t + 3 * GODZ)
        self.assertNotIn("cisza", w["stan_regul"][SALON]["czujniki"])

    def test_nowy_powod_niesie_trwajace(self):
        t = lok(2026, 10, 12, 10, 1)
        w = przebieg({KUCHNIA: pokoj(bateria="low")}, None, t)
        w = przebieg({KUCHNIA: pokoj(bateria="low", milczy_od="2026-10-12T02:00:00Z")}, w, t + GODZ)
        (e,) = nowe(w, t + GODZ)
        self.assertEqual(e["tytul"], "Czujnik w kuchni milczy")
        self.assertEqual(len(e["tresc"].splitlines()), 2, "bateria nie może zniknąć pod „milczy” (ten sam tag)")
        w = przebieg({KUCHNIA: pokoj(bateria="low"), SALON: pokoj(bateria="low")}, w, t + 2 * GODZ)
        (e,) = nowe(w, t + 2 * GODZ)
        self.assertEqual((e["tytul"], e["url"]), ("Słaba bateria czujnika w salonie", "#salon"))

    def test_noc_wszystkich_i_kolejka(self):
        noc_t = lok(2026, 10, 12, 23, 1)
        w = przebieg({KUCHNIA: pokoj(bateria="low")}, None, noc_t)
        self.assertEqual(nowe(w, noc_t), [])
        rano = lok(2026, 10, 13, 8, 1)
        w = przebieg({KUCHNIA: pokoj(bateria="middle")}, w, rano)
        self.assertEqual(len(nowe(w, rano)), 1, "trzymana bateria rano dalej trwa")
        # kolejka z walidacją: rano bateria wymieniona — pozycja odpada
        u = {"android": ust(), "iphone": ust(cisza=False)}
        w = przebieg({SALON: pokoj(bateria="low")}, None, noc_t, ustawienia=u)
        self.assertEqual([e["telefony"] for e in nowe(w, noc_t)], [["iphone"]])
        self.assertEqual(w["telefony"]["android"]["odlozone"][0]["powody"], ["bateria"])
        w_ok = przebieg({SALON: pokoj(bateria="high")}, w, rano, ustawienia=u)
        self.assertEqual(nowe(w_ok, rano), [])
        w_dalej = przebieg({SALON: pokoj(bateria="middle")}, w, rano, ustawienia=u)
        self.assertEqual([(e["telefony"], e.get("odlozone")) for e in nowe(w_dalej, rano)], [(["android"], True)])


class TestPlanerTrybyIFormat(unittest.TestCase):
    def test_na_sucho_te_same_decyzje_potem_naprawde(self):
        t = lok(2026, 10, 12, 10, 1)
        w = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, None, t, tryb="na-sucho")
        (e,) = nowe(w, t)
        self.assertTrue(e["na_sucho"])
        self.assertEqual((w["tryb"], w["wlaczone_od"]), ("na-sucho", None))
        self.assertEqual(w["stan_regul"][SALON]["przewietrz"]["na_sucho"], dom.iso(t))
        w = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, w, t + GODZ, tryb="na-sucho")
        self.assertEqual(nowe(w, t + GODZ), [])
        w = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, w, t + 2 * GODZ)
        (e,) = nowe(w, t + 2 * GODZ)
        self.assertFalse(e["na_sucho"], "po włączeniu trwający epizod idzie naprawdę")
        self.assertEqual((w["tryb"], w["wlaczone_od"]), ("wlaczone", dom.iso(t + 2 * GODZ)))

    def test_wlaczenie_bez_powitania_i_wlaczone_od_trwa(self):
        t = lok(2026, 10, 12, 23, 1)
        w = przebieg({}, None, t)
        self.assertEqual(w["historia"], [])
        self.assertEqual(w["wlaczone_od"], dom.iso(t))
        w2 = przebieg({}, w, t + 10 * GODZ)
        self.assertEqual(w2["wlaczone_od"], dom.iso(t))
        self.assertEqual(przebieg({}, w, t, tryb="WLACZONE")["tryb"], "na-sucho")

    def test_klucze_i_tresci(self):
        t = lok(2026, 10, 12, 19, 1)
        pokoje = {d: pokoj(przewietrz=PRZEWIETRZ, okno=OKNO, noc=noc("2026-10-12"), milczy_od="2026-10-12T01:00:00Z",
                           bateria="low") for d in OPISY}
        w = przebieg(pokoje, None, t)
        self.assertEqual(list(w), ["tryb", "wlaczone_od", "historia", "stan_regul", "telefony"])
        self.assertEqual(sorted(w["telefony"]), ["android", "iphone"])
        self.assertEqual({r["regula"] for r in w["historia"]}, {"przewietrz", "przed-snem", "okno", "czujniki"})
        for e in w["historia"]:
            self.assertEqual(list(e), ["id", "ts", "przebieg", "regula", "pokoje", "tytul", "tresc", "tag", "url",
                                       "na_sucho", "telefony"])
            self.assertRegex(e["tag"], r"^[a-z0-9-]{1,32}$")
            self.assertRegex(e["url"], r"^#[a-z0-9-]+$")
            self.assertNotRegex((e["tytul"] + e["tresc"]).lower(), r"pleś|plesn|http|android|iphone")
        self.assertEqual(len({e["id"] for e in w["historia"]}), len(w["historia"]))
        tekst = json.dumps(w, ensure_ascii=False)
        self.assertNotIn("endpoint", tekst)

    def test_historia_60_dni(self):
        stary = {"id": "x", "ts": "2026-08-01T10:00:00Z", "regula": "okno"}
        swiezy = {"id": "y", "ts": "2026-10-01T10:00:00Z", "regula": "okno"}
        w = przebieg({}, {"tryb": "wlaczone", "wlaczone_od": "2026-07-01T00:00:00Z", "historia": [stary, swiezy],
                          "stan_regul": {}, "telefony": None}, lok(2026, 10, 12, 10, 1))
        self.assertEqual([e["id"] for e in w["historia"]], ["y"])

    def test_zepsute_poprzednie_nie_wywracaja(self):
        t = lok(2026, 10, 12, 10, 1)
        zepsute = {"tryb": 5, "historia": [1, None, {"ts": "zle"}], "stan_regul": {LAZIENKA: {"przewietrz": "x",
                   "czujniki": {"bateria": 3}}, "inny": 7},
                   "telefony": {"android": {"odlozone": [5, {"regula": 1}, {"regula": "przewietrz", "ts": dom.iso(t),
                                                                           "obiekt": [1]},
                                                         {"regula": "czujniki", "ts": dom.iso(t), "obiekt": KUCHNIA,
                                                          "powody": "bateria"}]}}}
        w = przebieg({SALON: pokoj(przewietrz=PRZEWIETRZ)}, zepsute, t)
        self.assertEqual(len(nowe(w, t)), 1)
        self.assertNotIn("inny", w["stan_regul"])
        self.assertEqual(w["telefony"]["android"]["odlozone"], [])

    def test_wylaczone_u_obu_wpis_bez_adresatow(self):
        u = {t: ust(okno=False) for t in T.TELEFONY}
        t = lok(2026, 10, 12, 18, 1)
        w = przebieg({SYPIALNIA: pokoj(okno=OKNO)}, None, t, ustawienia=u)
        self.assertEqual([e["telefony"] for e in nowe(w, t)], [[]])
        self.assertEqual(w["stan_regul"][SYPIALNIA]["okno"]["wyslano"], dom.iso(t))


class TestDomNaZywychDanych(unittest.TestCase):
    """Niezmienniki data/dom/*.json w repozytorium, gdy już istnieją (bez konkretnych
    wartości — te zmieniają się co godzinę)."""

    def wczytaj(self, nazwa: str) -> dict:
        p = REPO / "data" / "dom" / nazwa
        if not p.exists():
            self.skipTest(f"brak data/dom/{nazwa}")

        def bez_nan(stala):
            raise ValueError(f"{stala} w {nazwa}")
        return json.loads(p.read_text(encoding="utf-8"), parse_constant=bez_nan)

    def test_stan(self):
        stan = self.wczytaj("stan.json")
        self.assertRegex(stan["updated"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        manifest = json.loads((REPO / "data" / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(set(stan["pokoje"]), set(dom.pokoje_z_manifestu(manifest["devices"])))
        for p in stan["pokoje"].values():
            self.assertEqual(list(p), ["przewietrz", "okno", "noc", "milczy_od", "bateria"])
            self.assertIn(p["bateria"], (None, "low", "middle", "high"))

    def test_powiadomienia(self):
        w = self.wczytaj("powiadomienia.json")
        self.assertEqual(list(w), ["tryb", "wlaczone_od", "historia", "stan_regul", "telefony"])
        for e in w["historia"]:
            self.assertRegex(e["tag"], r"^[a-z0-9-]{1,32}$")
            self.assertTrue(e["url"].startswith("#"))
            self.assertIn(e["regula"], ("przewietrz", "przed-snem", "okno", "czujniki"))
            self.assertTrue(set(e["telefony"]) <= set(T.TELEFONY))
            self.assertNotRegex((e["tytul"] + e["tresc"]).lower(), r"pleś")


if __name__ == "__main__":
    unittest.main()
