#!/usr/bin/env python3
"""Reguły powiadomień — rosliny.zaplanuj_powiadomienia() (etap 4).

Stany roślin powstają z syntetycznych wierszy CSV przez prawdziwe stan_rosliny(), tak
jak w kolektorze, więc reguły dostają ten kształt, który dostaną naprawdę. Każda granica
(2 godz. „poniżej", 21:00 i 8:00 w Europe/Warsaw — także w dniu zmiany czasu, 2 „podlej"
na dobę, ponowienie po 24 i 12 godz., histereza 6 pkt, 60 dni historii, niedziela 10:00)
jest sprawdzana z obu stron, żeby przesunięcie o jeden wyszło na teście.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import rosliny  # noqa: E402

WAWA = ZoneInfo("Europe/Warsaw")
MIN = 60_000
GODZ = 60 * MIN
DOBA = 24 * GODZ
KODY = {"gleba": "humidity", "temp": "temp_current", "wilg": "env_humidity",
        "swiatlo": "illumiance", "bateria": "battery_state", "alarm": "water_warning"}
KLUCZE_PLIKU = {"tryb", "wlaczone_od", "historia", "stan_regul", "podsumowanie_ostatnie"}


def ms(tekst: str) -> int:
    return int(datetime.fromisoformat(tekst.replace("Z", "+00:00")).timestamp() * 1000)


def wawa(tekst: str) -> int:
    """„2026-10-12 11:00" czasu warszawskiego → ms."""
    return int(datetime.fromisoformat(tekst).replace(tzinfo=WAWA).timestamp() * 1000)


def od(chwila: int, po: float, przed: float = 40):
    """Gleba `przed` do `chwila`, od niej `po`."""
    return lambda t: po if t >= chwila else przed


def _wartosc(zrodlo, t):
    return zrodlo(t) if callable(zrodlo) else zrodlo


class Doniczka:
    """Roślina z wierszy CSV co 30 min od `start` (wbicie sondy, „sucho" 10).

    Przy `skala=True` sześć godzin po wbiciu jest podlanie z 15 do 50, więc szczyt 50
    i progi w jednostkach czujnika (październik, progi zimowe): fikus 24, skrzydłokwiat
    30, azalia 40 (pilne ≤ 34). Potem gleba według `gleba(t)`; None to brak odczytu.
    """

    def __init__(self, nazwa="Fikus", gatunek="fikus", gleba=40, bateria="high", swiatlo=None,
                 start=ms("2026-10-05T00:00:00Z"), skala=True, wbita=True):
        self.nazwa, self.gatunek, self.gleba, self.bateria = nazwa, gatunek, gleba, bateria
        self.swiatlo, self.start, self.skala, self.wbita = swiatlo, start, skala, wbita

    def konf(self) -> dict:
        return {"czujnik": f"czujnik-{rosliny._slug(self.nazwa)}", "nazwa": self.nazwa,
                "gatunek": self.gatunek, "pokoj": None, "kody": dict(KODY), "sucho": 10.0,
                "od": rosliny.iso(self.start) if self.wbita else None, "pomin_podlania": []}

    def wiersze(self, teraz: int) -> list[dict]:
        czujnik, out, t = self.konf()["czujnik"], [], self.start
        while t <= teraz:
            if self.skala and t < self.start + 6 * GODZ:
                g = 15
            elif self.skala and t < self.start + 16 * GODZ:
                g = 50
            else:
                g = _wartosc(self.gleba, t)
            for kod, v in (("humidity", g), ("battery_state", _wartosc(self.bateria, t)),
                           ("illumiance", _wartosc(self.swiatlo, t))):
                if v is not None:
                    out.append({"ts": rosliny.iso(t), "device_id": czujnik, "code": kod, "value": str(v)})
            t += 30 * MIN
        return out

    def stan(self, teraz: int) -> dict:
        return rosliny.stan_rosliny(self.konf(), self.wiersze(teraz), teraz, WAWA)


# Plik po włączeniu dawno temu — żeby testy reguł nie zaczynały się od powitania.
WLACZONE = {"tryb": "wlaczone", "wlaczone_od": "2026-10-01T00:00:00Z", "historia": [],
            "stan_regul": {}, "podsumowanie_ostatnie": None}


def przebieg(doniczki, teraz: int, plik=WLACZONE, tryb: str = "wlaczone", stany=None):
    """Jeden przebieg kolektora: stany → reguły → plik przez JSON, jak z dysku.
    Zwraca (plik, wpisy tego przebiegu) — te, które nadawca by wziął."""
    stany = [d.stan(teraz) for d in doniczki] if stany is None else stany
    nr = f"{teraz}-1"
    wynik = rosliny.zaplanuj_powiadomienia(stany, copy.deepcopy(plik), teraz, WAWA, tryb, nr)
    wynik = json.loads(json.dumps(wynik, allow_nan=False))
    return wynik, [w for w in wynik["historia"] if w.get("przebieg") == nr]


def przebiegi(doniczki, czasy, plik=WLACZONE, tryb: str = "wlaczone"):
    """Kolejne przebiegi; zwraca plik po ostatnim i {czas: wpisy}."""
    wpisy = {}
    for t in czasy:
        plik, wpisy[t] = przebieg(doniczki, t, plik, tryb)
    return plik, wpisy


def reguly(wpisy) -> list[str]:
    return [w["regula"] for w in wpisy]


class TestPodlej(unittest.TestCase):
    def test_dopiero_po_dwoch_godzinach_ponizej(self):
        fikus = Doniczka(gleba=od(wawa("2026-10-12 11:00"), 21))
        plik, wpisy = przebiegi([fikus], [wawa("2026-10-12 10:00"), wawa("2026-10-12 11:00"),
                                          wawa("2026-10-12 12:00")])
        self.assertEqual([w for x in wpisy.values() for w in x], [])
        self.assertEqual(plik["stan_regul"]["Fikus"]["ponizej_od"], rosliny.iso(wawa("2026-10-12 11:00")))
        # 2 godz. minus 10 min zapasu na rozrzut startu przebiegów (commity :00–:06)
        self.assertEqual(przebieg([fikus], wawa("2026-10-12 12:49:59"), plik)[1], [])
        _, wpisy = przebieg([fikus], wawa("2026-10-12 12:50"), plik)
        self.assertEqual(len(wpisy), 1)
        w = wpisy[0]
        self.assertEqual((w["regula"], w["rosliny"], w["tytul"], w["tag"], w["url"], w["na_sucho"]),
                         ("podlej", ["Fikus"], "Podlej: fikus", "podlej-fikus", "rosliny.html#roslina=Fikus", False))
        self.assertEqual(w["tresc"], "Fikus: gleba 21% (podlewaj przy ok. 24%).")

    def test_histereza_6_punktow(self):
        """Gleba na chwilę nad progiem (werdykt „ok"), potem znowu poniżej. Do progu + 5
        epizod trwa i licznik 2 godz. się nie zeruje; próg + 6 kończy epizod. Skoki są
        mniejsze niż 10 pkt, więc to nie wykryte podlanie."""
        for chwilowo, trwa in ((29, True), (30, False)):          # próg fikusa 24
            with self.subTest(gleba=chwilowo):
                start, chwila = wawa("2026-10-12 11:00"), wawa("2026-10-12 11:30")

                def gleba(t, chwilowo=chwilowo):
                    return 40 if t < start else (chwilowo if chwila <= t < chwila + 30 * MIN else 21)

                fikus = Doniczka(gleba=gleba)
                plik, _ = przebiegi([fikus], [start, chwila, wawa("2026-10-12 12:00")])
                self.assertEqual(fikus.stan(chwila)["werdykt"], "ok")
                self.assertEqual(fikus.stan(chwila)["podlania"][-1]["ts"], rosliny.iso(fikus.start + 6 * GODZ))
                _, wpisy = przebieg([fikus], wawa("2026-10-12 12:50"), plik)
                self.assertEqual(reguly(wpisy), ["podlej"] if trwa else [])
                if not trwa:
                    self.assertEqual(plik["stan_regul"]["Fikus"]["ponizej_od"], rosliny.iso(wawa("2026-10-12 12:00")))

    def test_wykryte_podlanie_konczy_epizod(self):
        """Za mało wody (gleba dalej poniżej progu) to i tak koniec epizodu: liczniki od
        zera, więc po 2 godz. przychodzi nowe „podlej", a nie dopiero po 24. Podlanie
        sprzed `ponizej_od` (to od skali, 6 godz. po wbiciu) epizodu nie kończy — inaczej
        żaden test ponowień by nie przeszedł."""
        start, podlanie = wawa("2026-10-12 11:00"), wawa("2026-10-12 14:00")
        for podlana in (True, False):
            with self.subTest(podlana=podlana):
                def gleba(t, podlana=podlana):
                    return 40 if t < start else (26 if podlana and t >= podlanie else 15)

                skrzydlokwiat = Doniczka("Skrzydłokwiat", "skrzydlokwiat", gleba=gleba)
                plik, wpisy = przebiegi([skrzydlokwiat], [start, wawa("2026-10-12 13:00"), wawa("2026-10-12 14:30")])
                self.assertEqual(reguly(wpisy[wawa("2026-10-12 13:00")]), ["podlej"])
                self.assertEqual(skrzydlokwiat.stan(wawa("2026-10-12 14:30"))["werdykt"], "podlej")
                self.assertEqual(przebieg([skrzydlokwiat], wawa("2026-10-12 16:19:59"), plik)[1], [])
                _, wpisy = przebieg([skrzydlokwiat], wawa("2026-10-12 16:20"), plik)
                self.assertEqual(reguly(wpisy), ["podlej"] if podlana else [])

    def test_ponowienie_co_24_godz_najwyzej_3_razy(self):
        fikus = Doniczka(gleba=od(wawa("2026-10-12 11:00"), 21))
        plik, wpisy = przebiegi([fikus], [wawa("2026-10-12 11:00"), wawa("2026-10-12 13:00")])
        self.assertEqual(reguly(wpisy[wawa("2026-10-12 13:00")]), ["podlej"])
        self.assertEqual(przebieg([fikus], wawa("2026-10-13 12:49:59"), plik)[1], [])
        czasy = [wawa(f"2026-10-{d} 12:50") for d in (13, 14, 15, 16)]
        _, wpisy = przebiegi([fikus], czasy, plik)
        self.assertEqual([reguly(wpisy[t]) for t in czasy], [["podlej"], ["podlej"], [], []],
                         "najwyżej 3 wysyłki na epizod, potem już tylko karta")

    def test_azalia_ponawia_po_12_godz_fikus_po_24(self):
        """12 godz. po wysyłce między 9:50 a 21:00 wypada zawsze w nocy albo przed 9:50,
        więc dokładnej granicy 12 godz. nie widać — widać, że azalia nie czeka doby."""
        poczatek = wawa("2026-10-12 18:30")
        fikus = Doniczka(gleba=od(poczatek, 21))
        azalia = Doniczka("Azalia", "azalia", gleba=od(poczatek, 37, 45))   # R 0,68: podlej, nie pilne
        plik, wpisy = przebiegi([fikus, azalia], [poczatek, wawa("2026-10-12 20:20")])
        self.assertEqual(wpisy[wawa("2026-10-12 20:20")][0]["rosliny"], ["Fikus", "Azalia"])
        # rano licznik 2 godz. od 8:00 — także dla ponowienia
        self.assertEqual(przebieg([fikus, azalia], wawa("2026-10-13 09:49:59"), plik)[1], [])
        _, wpisy = przebieg([fikus, azalia], wawa("2026-10-13 09:50"), plik)
        self.assertEqual([w["rosliny"] for w in wpisy], [["Azalia"]])

    def test_pilne_u_azalii_z_rada_zanurzenia(self):
        azalia = Doniczka("Azalia", "azalia", gleba=od(wawa("2026-10-12 11:00"), 30, 45))   # R 0,5
        _, wpisy = przebiegi([azalia], [wawa("2026-10-12 11:00"), wawa("2026-10-12 13:00")])
        w = wpisy[wawa("2026-10-12 13:00")][0]
        self.assertEqual(w["tytul"], "Podlej: azalia (pilne)")
        self.assertTrue(w["tresc"].startswith("Azalia: gleba 30% (podlewaj przy ok. 40%). Wyjmij czujnik"))

    def test_kilka_roslin_to_jeden_wpis(self):
        start = wawa("2026-10-12 11:00")
        doniczki = [Doniczka(gleba=od(start, 21)), Doniczka("Skrzydłokwiat", "skrzydlokwiat", gleba=od(start, 15))]
        _, wpisy = przebiegi(doniczki, [start, wawa("2026-10-12 13:00")])
        (w,) = wpisy[wawa("2026-10-12 13:00")]
        self.assertEqual(w["rosliny"], ["Fikus", "Skrzydłokwiat"])
        self.assertEqual(w["tytul"], "Podlej: fikus, skrzydłokwiat")
        self.assertEqual(w["tresc"], "Fikus: gleba 21% (podlewaj przy ok. 24%).\n"
                                     "Skrzydłokwiat: gleba 15% (podlewaj przy ok. 30%).")
        self.assertEqual(w["tag"], "podlej-fikus-skrzydlokwiat")
        self.assertEqual(w["url"], "rosliny.html#roslina=Fikus")

    def test_najwyzej_dwa_podlej_na_dobe(self):
        fikus = Doniczka(gleba=od(wawa("2026-10-12 08:00"), 21))
        skrzydlokwiat = Doniczka("Skrzydłokwiat", "skrzydlokwiat", gleba=od(wawa("2026-10-12 10:00"), 15))
        azalia = Doniczka("Azalia", "azalia", gleba=od(wawa("2026-10-12 12:00"), 37, 45))
        czasy = [wawa(t) for t in ("2026-10-12 08:00", "2026-10-12 10:00", "2026-10-12 12:00",
                                   "2026-10-12 14:00", "2026-10-12 20:00", "2026-10-13 09:50")]
        plik, wpisy = przebiegi([fikus, skrzydlokwiat, azalia], czasy)
        self.assertEqual([[w["rosliny"] for w in wpisy[t]] for t in czasy],
                         [[], [["Fikus"]], [["Skrzydłokwiat"]], [], [], [["Fikus", "Azalia"]]],
                         "trzecia roślina tego samego dnia czeka do jutra")

    def test_limit_dobowy_liczy_wysylki_wlasnego_trybu(self):
        """Po włączeniu poranne wpisy na sucho nie zjadają limitu; na sucho liczą się
        i jedne, i drugie — tak by było, gdyby wysyłka już działała."""
        fikus = Doniczka(gleba=od(wawa("2026-10-12 11:00"), 21))

        def plik(tryb, na_sucho):
            historia = [{"id": f"x{i}", "ts": rosliny.iso(wawa(f"2026-10-12 {g}")), "przebieg": "0-1",
                         "regula": "podlej", "rosliny": ["Inna"], "na_sucho": na_sucho}
                        for i, g in enumerate(("09:00", "10:00"))]
            return {**WLACZONE, "tryb": tryb, "historia": historia, "stan_regul": {"Fikus": {
                "ponizej_od": rosliny.iso(wawa("2026-10-12 11:00")), "wyslano": [], "na_sucho": []}}}

        teraz = wawa("2026-10-12 13:00")
        for tryb, na_sucho, wychodzi in (("wlaczone", True, True), ("wlaczone", False, False),
                                         ("na-sucho", True, False), ("na-sucho", False, False)):
            with self.subTest(tryb=tryb, wczesniejsze_na_sucho=na_sucho):
                _, wpisy = przebieg([fikus], teraz, plik(tryb, na_sucho), tryb)
                self.assertEqual(reguly(wpisy), ["podlej"] if wychodzi else [])

    def test_nauka_nie_daje_podlej_i_konczy_epizod(self):
        przed_szczytem = Doniczka(gleba=15, skala=False)                 # czeka na pierwsze podlanie
        bez_wbicia = Doniczka("Azalia", "azalia", gleba=12, wbita=False)
        teraz = wawa("2026-10-12 13:00")
        self.assertEqual({przed_szczytem.stan(teraz)["werdykt"], bez_wbicia.stan(teraz)["werdykt"]}, {"nauka"})
        stary = {**WLACZONE, "stan_regul": {n: {"ponizej_od": rosliny.iso(teraz - 5 * GODZ), "wyslano": [],
                                                "na_sucho": []} for n in ("Fikus", "Azalia")}}
        plik, wpisy = przebiegi([przed_szczytem, bez_wbicia], [teraz, teraz + GODZ, teraz + 3 * GODZ], stary)
        self.assertEqual([w for x in wpisy.values() for w in x], [])
        self.assertEqual({n: s["ponizej_od"] for n, s in plik["stan_regul"].items()}, {"Fikus": None, "Azalia": None})


class TestCiszaNocna(unittest.TestCase):
    def test_wieczorem_do_2059_od_21_cisza(self):
        fikus = Doniczka(gleba=od(wawa("2026-10-12 18:00"), 21))
        plik, _ = przebieg([fikus], wawa("2026-10-12 18:00"))
        self.assertEqual(reguly(przebieg([fikus], wawa("2026-10-12 20:59:59"), plik)[1]), ["podlej"])
        self.assertEqual(przebieg([fikus], wawa("2026-10-12 21:00"), plik)[1], [])

    def test_noc_sie_nie_liczy_rano_od_nowa(self):
        fikus = Doniczka(gleba=od(wawa("2026-10-12 22:00"), 21))
        czasy = [wawa(t) for t in ("2026-10-12 22:00", "2026-10-12 23:00", "2026-10-13 02:00",
                                   "2026-10-13 06:00", "2026-10-13 07:59:59", "2026-10-13 08:00", "2026-10-13 09:00")]
        plik, wpisy = przebiegi([fikus], czasy)
        self.assertEqual([w for x in wpisy.values() for w in x], [], "w nocy ani o 8:00 nic nie wychodzi")
        self.assertEqual(plik["stan_regul"]["Fikus"]["ponizej_od"], rosliny.iso(wawa("2026-10-12 22:00")))
        self.assertEqual(przebieg([fikus], wawa("2026-10-13 09:49:59"), plik)[1], [])
        self.assertEqual(reguly(przebieg([fikus], wawa("2026-10-13 09:50"), plik)[1]), ["podlej"])

    def test_granice_nocy_przy_zmianie_czasu(self):
        """25.10.2026 i 28.03.2027: 8:00 i 21:00 to inne godziny UTC niż dzień wcześniej.
        Stałe przesunięcie (albo godzina UTC) wysłałoby godzinę za wcześnie lub za późno."""
        przypadki = [
            # (start sondy, bateria low od, jeszcze noc, już dzień)
            ("2026-10-20T00:00:00Z", "2026-10-24T00:00:00Z", "2026-10-24T05:59:59Z", "2026-10-24T06:00:00Z"),  # CEST
            ("2026-10-20T00:00:00Z", "2026-10-25T00:00:00Z", "2026-10-25T06:59:59Z", "2026-10-25T07:00:00Z"),  # CET
            ("2027-03-23T00:00:00Z", "2027-03-27T00:00:00Z", "2027-03-27T06:59:59Z", "2027-03-27T07:00:00Z"),  # CET
            ("2027-03-23T00:00:00Z", "2027-03-28T00:00:00Z", "2027-03-28T05:59:59Z", "2027-03-28T06:00:00Z"),  # CEST
        ]
        for start, low, noc, dzien in przypadki:
            with self.subTest(dzien=dzien):
                fikus = Doniczka(start=ms(start), bateria=lambda t, low=ms(low): "low" if t >= low else "high")
                plik, wpisy = przebiegi([fikus], [ms(low) + GODZ, ms(noc)])
                self.assertEqual([w for x in wpisy.values() for w in x], [])
                self.assertEqual(reguly(przebieg([fikus], ms(dzien), plik)[1]), ["czujnik"])
        # wieczór 25.10: 21:00 CET to 20:00 UTC, a nie 19:00 jak dzień wcześniej
        fikus = Doniczka(start=ms("2026-10-20T00:00:00Z"), gleba=od(ms("2026-10-25T16:00:00Z"), 21))
        plik, _ = przebieg([fikus], ms("2026-10-25T16:00:00Z"))
        self.assertEqual(reguly(przebieg([fikus], ms("2026-10-25T19:59:59Z"), plik)[1]), ["podlej"])
        self.assertEqual(przebieg([fikus], ms("2026-10-25T20:00:00Z"), plik)[1], [])


class TestCzujnik(unittest.TestCase):
    def test_raz_na_powod_i_powrot(self):
        def bateria(t):
            slaba = wawa("2026-10-12 10:00") <= t < wawa("2026-10-12 12:00") or t >= wawa("2026-10-12 14:00")
            return "low" if slaba else "high"

        czasy = [wawa(t) for t in ("2026-10-12 10:30", "2026-10-12 11:30", "2026-10-12 12:30", "2026-10-12 14:30")]
        plik, wpisy = przebiegi([Doniczka(bateria=bateria)], czasy)
        self.assertEqual([reguly(wpisy[t]) for t in czasy], [["czujnik"], [], [], ["czujnik"]])
        w = wpisy[czasy[0]][0]
        self.assertEqual((w["tytul"], w["tresc"], w["tag"], w["url"]),
                         ("Czujnik: fikus", "Fikus: bateria na wyczerpaniu.", "czujnik-fikus",
                          "rosliny.html#roslina=Fikus"))
        self.assertEqual(list(plik["stan_regul"]["Fikus"]["czujnik"]), ["bateria"])

    def test_cisza_z_rosnacymi_godzinami_to_jeden_powod(self):
        cisza = wawa("2026-10-11 23:00")
        fikus = Doniczka(gleba=lambda t: 40 if t <= cisza else None, bateria=lambda t: "high" if t <= cisza else None)
        czasy = [wawa(t) for t in ("2026-10-12 11:30", "2026-10-12 12:30", "2026-10-12 13:30")]
        self.assertNotEqual(fikus.stan(czasy[0])["do_zgloszenia"], fikus.stan(czasy[1])["do_zgloszenia"])
        self.assertIn("milczy od", fikus.stan(czasy[1])["do_zgloszenia"][0])
        _, wpisy = przebiegi([fikus], czasy)
        self.assertEqual([reguly(wpisy[t]) for t in czasy], [["czujnik"], [], []])

    def test_powody_z_prawdziwych_stanow(self):
        """Klucz powodu bierze się z tekstu stan_rosliny() — zmiana treści zgłoszenia
        bez zmiany tutaj musi wyjść na teście, a nie dać alarm co przebieg."""
        teraz, wieczor = wawa("2026-10-12 12:00"), wawa("2026-10-11 20:00")
        doniczki = {
            "cisza": Doniczka("Cisza", gleba=lambda t: 40 if t <= wieczor else None,
                              bateria=lambda t: "high" if t <= wieczor else None),
            "gleba": Doniczka("Gleba", gleba=lambda t: 40 if t <= wieczor else None),
            "sonda": Doniczka("Sonda", gleba=od(wawa("2026-10-12 09:00"), 9)),
            "bateria": Doniczka("Bateria", bateria="low"),
            "brak-odczytow": Doniczka("Pusta", gleba=None, bateria=None, skala=False),
        }
        plik, wpisy = przebieg(list(doniczki.values()), teraz)
        for powod, d in doniczki.items():
            with self.subTest(powod):
                self.assertEqual(list(plik["stan_regul"][d.nazwa]["czujnik"]), [powod], d.stan(teraz)["do_zgloszenia"])
        (w,) = wpisy
        self.assertEqual(w["rosliny"], [d.nazwa for d in doniczki.values()], "jeden wpis „czujnik\" na przebieg")
        self.assertRegex(w["tag"], r"^[a-z0-9-]{1,32}$")

    def test_w_nocy_czeka_do_rana(self):
        fikus = Doniczka(bateria=od(wawa("2026-10-12 22:00"), "low", "high"))
        czasy = [wawa(t) for t in ("2026-10-12 22:30", "2026-10-13 03:00", "2026-10-13 07:59:59")]
        plik, wpisy = przebiegi([fikus], czasy)
        self.assertEqual([w for x in wpisy.values() for w in x], [])
        self.assertEqual([n["powod"] for n in plik["stan_regul"]["Fikus"]["noc"]], ["bateria"])
        plik, wpisy = przebieg([fikus], wawa("2026-10-13 08:00"), plik)
        self.assertEqual([(w["regula"], w["tresc"]) for w in wpisy], [("czujnik", "Fikus: bateria na wyczerpaniu.")])
        self.assertEqual(plik["stan_regul"]["Fikus"]["noc"], [])
        self.assertEqual(przebieg([fikus], wawa("2026-10-13 09:00"), plik)[1], [])

    def test_nocne_zdarzenie_wychodzi_rano_nawet_gdy_minelo(self):
        """Sonda wyjęta o 22:00 (≥ 2 godz. to zgłoszenie), wbita z powrotem o 2:00. Rano
        wychodzi to, co było w nocy — tylko alarm czujnika ma tę pamięć."""
        wyjeta, z_powrotem = wawa("2026-10-12 22:00"), wawa("2026-10-13 02:00")
        fikus = Doniczka(gleba=lambda t: 9 if wyjeta <= t < z_powrotem else 40)
        czasy = [wawa(t) for t in ("2026-10-12 22:30", "2026-10-13 00:30", "2026-10-13 03:00")]
        self.assertEqual(fikus.stan(czasy[0])["do_zgloszenia"], [], "pół godziny poza ziemią to nie alarm")
        self.assertTrue(fikus.stan(czasy[1])["do_zgloszenia"])
        self.assertEqual(fikus.stan(czasy[2])["do_zgloszenia"], [])
        plik, wpisy = przebiegi([fikus], czasy)
        self.assertEqual([w for x in wpisy.values() for w in x], [])
        plik, wpisy = przebieg([fikus], wawa("2026-10-13 08:00"), plik)
        (w,) = wpisy
        self.assertEqual(w["regula"], "czujnik")
        self.assertTrue(w["tresc"].startswith("Fikus: w nocy (13.10 00:30) od 12.10 22:00 gleba pokazuje"), w["tresc"])
        self.assertTrue(w["tresc"].endswith("Do rana minęło."))
        self.assertEqual((plik["stan_regul"]["Fikus"]["czujnik"], plik["stan_regul"]["Fikus"]["noc"]), ({}, []))
        self.assertEqual(przebieg([fikus], wawa("2026-10-13 09:00"), plik)[1], [])


class TestPodsumowanie(unittest.TestCase):
    def trzy(self, **zmiany) -> list[Doniczka]:
        return [Doniczka(**zmiany), Doniczka("Skrzydłokwiat", "skrzydlokwiat", **zmiany),
                Doniczka("Azalia", "azalia", gleba=45, **zmiany)]

    def test_niedziela_od_10_raz_w_tygodniu_zawsze(self):
        doniczki = self.trzy()
        czasy = [wawa(t) for t in ("2026-10-10 10:00", "2026-10-11 09:59:59", "2026-10-11 10:00",
                                   "2026-10-11 11:00", "2026-10-11 20:00", "2026-10-18 10:00")]
        plik, wpisy = przebiegi(doniczki, czasy)
        self.assertEqual([reguly(wpisy[t]) for t in czasy], [[], [], ["podsumowanie"], [], [], ["podsumowanie"]])
        self.assertEqual(plik["podsumowanie_ostatnie"], "2026-10-18")
        w = wpisy[czasy[2]][0]
        self.assertEqual((w["rosliny"], w["url"], w["tag"], w["tytul"]),
                         (["Fikus", "Skrzydłokwiat", "Azalia"], "rosliny.html", "podsumowanie",
                          "Rośliny — podsumowanie tygodnia"))
        linie = w["tresc"].split("\n")
        self.assertEqual([x.split(":")[0] for x in linie], ["Fikus", "Skrzydłokwiat", "Azalia"])
        # wszystko w porządku — i tak wychodzi, to sygnał, że system żyje
        self.assertTrue(all("w porządku" in x for x in linie), linie)
        self.assertIn("ostatnie podlanie 05.10 08:00", linie[0])

    def test_swiatlo_z_pelnych_dob_bez_dzisiejszej(self):
        """Średnia z 7 dób przed niedzielą (4–10.10), tylko z dób zmierzonych w ≥ 80%.
        Wypadają: dzisiejsza (jasna; o 20:00 — np. gdy Actions od rana stały — ma już 83%
        pokrycia), dziurawa (czwartek, jasny do południa) i ósma wstecz (jasna, pełna)."""
        def swiatlo(t):
            lokalnie = datetime.fromtimestamp(t / 1000, WAWA)
            dzien, godzina = lokalnie.date().isoformat(), lokalnie.hour
            if dzien in ("2026-10-11", "2026-10-03"):
                return 5000
            if dzien == "2026-10-08":
                return 1000 if godzina < 12 else (None if godzina < 22 else 100)
            return 100

        fikus = Doniczka(swiatlo=swiatlo, start=ms("2026-10-01T00:00:00Z"))
        teraz = wawa("2026-10-11 20:00")
        self.assertGreaterEqual(fikus.stan(teraz)["swiatlo_dobowe"][-1]["pokrycie"], rosliny.POKRYCIE_PELNEJ_DOBY)
        _, wpisy = przebieg([fikus], teraz)
        self.assertIn("światło śr. 2 400 lx·h na dobę, 12% potrzeby (pełne doby: 6 z 7)", wpisy[0]["tresc"])
        bez = Doniczka(start=ms("2026-10-01T00:00:00Z"))
        self.assertIn("światło: za mało pomiaru", przebieg([bez], wawa("2026-10-11 10:00"))[1][0]["tresc"])

    def test_dziesiata_w_niedziele_zmiany_czasu(self):
        doniczki = self.trzy(start=ms("2026-10-20T00:00:00Z"))
        plik, wpisy = przebieg(doniczki, ms("2026-10-25T08:59:59Z"))        # 9:59:59 CET
        self.assertEqual(wpisy, [])
        self.assertEqual(reguly(przebieg(doniczki, ms("2026-10-25T09:00:00Z"), plik)[1]), ["podsumowanie"])


class TestTryby(unittest.TestCase):
    START = wawa("2026-10-12 11:00")

    def doniczki(self) -> list[Doniczka]:
        return [Doniczka(gleba=od(self.START, 21)),
                Doniczka("Skrzydłokwiat", "skrzydlokwiat", bateria=od(wawa("2026-10-12 10:00"), "low", "high"))]

    def test_na_sucho_te_same_decyzje(self):
        czasy = [wawa(t) for t in ("2026-10-12 10:30", "2026-10-12 11:00", "2026-10-12 13:00",
                                   "2026-10-13 12:49:59", "2026-10-13 12:50")]
        pola = ("ts", "regula", "rosliny", "tytul", "tresc", "tag", "url")
        wyniki = {}
        for tryb, plik in (("wlaczone", WLACZONE), ("na-sucho", None)):
            koniec, wpisy = przebiegi(self.doniczki(), czasy, plik, tryb)
            wyniki[tryb] = [[{k: w[k] for k in pola} for w in wpisy[t]] for t in czasy]
            self.assertEqual({w["na_sucho"] for x in wpisy.values() for w in x}, {tryb == "na-sucho"})
            fikus = koniec["stan_regul"]["Fikus"]
            wysylki = [rosliny.iso(czasy[2]), rosliny.iso(czasy[4])]
            self.assertEqual((fikus["wyslano"], fikus["na_sucho"]),
                             (wysylki, []) if tryb == "wlaczone" else ([], wysylki))
        self.assertEqual(wyniki["wlaczone"], wyniki["na-sucho"])
        self.assertEqual([[w["regula"] for w in x] for x in wyniki["wlaczone"]],
                         [["czujnik"], [], ["podlej"], [], ["podlej"]])

    def test_wlaczenie_daje_jeden_wpis_o_tym_co_trwa(self):
        """Dwa „podlej" na sucho (pon. 13:00, wt. 12:50), włączenie we wtorek o 14:00.
        Powitanie to jedyny wpis i pierwsza prawdziwa wysyłka epizodu; ponowienia i limit
        3 na epizod liczą się od niego — wysyłki na sucho by go wyczerpały."""
        sucho, wpisy = przebiegi(self.doniczki(), [wawa("2026-10-12 10:30"), self.START, wawa("2026-10-12 13:00"),
                                                   wawa("2026-10-13 12:50")], None, "na-sucho")
        self.assertEqual(sum(reguly(x).count("podlej") for x in wpisy.values()), 2)
        plik, wpisy = przebieg(self.doniczki(), wawa("2026-10-13 14:00"), sucho, "wlaczone")
        (w,) = wpisy
        self.assertEqual((w["regula"], w["na_sucho"], w["tytul"], w["tag"], w["url"], w["rosliny"]),
                         ("wlaczone", False, "Powiadomienia włączone", "wlaczone", "rosliny.html#roslina=Fikus",
                          ["Fikus", "Skrzydłokwiat"]))
        self.assertEqual(w["tresc"], "Już trwa:\nFikus: gleba 21% (podlewaj przy ok. 24%).\n"
                                     "Skrzydłokwiat: bateria na wyczerpaniu.")
        self.assertEqual((plik["tryb"], plik["wlaczone_od"]), ("wlaczone", rosliny.iso(wawa("2026-10-13 14:00"))))
        self.assertEqual(przebieg(self.doniczki(), wawa("2026-10-13 15:00"), plik)[1], [])
        self.assertEqual(przebieg(self.doniczki(), wawa("2026-10-14 13:40"), plik)[1], [])
        czasy = [wawa(f"2026-10-{d} 13:50") for d in (14, 15, 16)]
        _, wpisy = przebiegi(self.doniczki(), czasy, plik)
        self.assertEqual([reguly(wpisy[t]) for t in czasy], [["podlej"], ["podlej"], []])

    def test_na_sucho_liczy_tez_prawdziwe_wysylki(self):
        """Po powrocie na sucho decyzje dalej są takie, jakie byłyby przy włączonej
        wysyłce: prawdziwe „podlej" sprzed godziny nie powtarza się na sucho."""
        fikus = [Doniczka(gleba=od(self.START, 21))]
        plik, wpisy = przebiegi(fikus, [self.START, wawa("2026-10-12 13:00")])
        self.assertEqual(reguly(wpisy[wawa("2026-10-12 13:00")]), ["podlej"])
        plik, wpisy = przebieg(fikus, wawa("2026-10-12 14:00"), plik, "na-sucho")
        self.assertEqual(wpisy, [])
        _, wpisy = przebieg(fikus, wawa("2026-10-13 12:50"), plik, "na-sucho")
        self.assertEqual([(w["regula"], w["na_sucho"]) for w in wpisy], [("podlej", True)])

    def test_wlaczenie_w_nocy_powitanie_rano(self):
        doniczki = [Doniczka()]
        sucho, _ = przebieg(doniczki, wawa("2026-10-12 20:00"), None, "na-sucho")
        plik, wpisy = przebiegi(doniczki, [wawa("2026-10-12 23:00"), wawa("2026-10-13 03:00")], sucho)
        self.assertEqual([w for x in wpisy.values() for w in x], [])
        self.assertEqual((plik["tryb"], plik["wlaczone_od"]), ("wlaczone", None))
        plik, wpisy = przebieg(doniczki, wawa("2026-10-13 08:00"), plik)
        self.assertEqual([(w["regula"], w["tresc"], w["url"]) for w in wpisy],
                         [("wlaczone", "Teraz nic nie wymaga uwagi.", "rosliny.html")])
        self.assertEqual(plik["wlaczone_od"], rosliny.iso(wawa("2026-10-13 08:00")))
        self.assertEqual(przebieg(doniczki, wawa("2026-10-13 09:00"), plik)[1], [])

    def test_powrot_na_sucho_i_ponowne_wlaczenie(self):
        doniczki = [Doniczka()]
        plik, _ = przebieg(doniczki, wawa("2026-10-12 12:00"))
        plik, wpisy = przebieg(doniczki, wawa("2026-10-12 13:00"), plik, "na-sucho")
        self.assertEqual((plik["tryb"], plik["wlaczone_od"], wpisy), ("na-sucho", None, []))
        _, wpisy = przebieg(doniczki, wawa("2026-10-12 14:00"), plik, "wlaczone")
        self.assertEqual(reguly(wpisy), ["wlaczone"])

    def test_nieznany_tryb_to_na_sucho(self):
        for tryb in ("", "tak", "WLACZONE", None):
            with self.subTest(tryb=tryb):
                plik, wpisy = przebieg([Doniczka(bateria="low")], wawa("2026-10-12 12:00"), None, tryb)
                self.assertEqual((plik["tryb"], plik["wlaczone_od"]), ("na-sucho", None))
                self.assertEqual([(w["regula"], w["na_sucho"]) for w in wpisy], [("czujnik", True)])


class TestHistoria(unittest.TestCase):
    TERAZ = wawa("2026-10-12 12:00")

    def test_przycinanie_do_60_dni(self):
        stare = [{"id": "a", "ts": rosliny.iso(self.TERAZ - 60 * DOBA - 1000)},
                 {"id": "b", "ts": rosliny.iso(self.TERAZ - 60 * DOBA)},
                 "śmieć", {"id": "c"}, {"id": "d", "ts": "wczoraj"},
                 {"id": "e", "ts": rosliny.iso(self.TERAZ - DOBA)}]
        plik, _ = przebieg([], self.TERAZ, {**WLACZONE, "historia": stare})
        self.assertEqual([w["id"] for w in plik["historia"]], ["b", "e"])
        # nowe na końcu
        plik, wpisy = przebieg([Doniczka(bateria="low")], self.TERAZ, {**WLACZONE, "historia": stare})
        self.assertEqual(plik["historia"][-1], wpisy[0])

    def test_id_unikalne_ascii_i_znaczniki_topic(self):
        poczatek, teraz = wawa("2026-10-11 09:00"), wawa("2026-10-11 11:00")       # niedziela
        doniczki = [Doniczka(gleba=od(poczatek, 21), bateria=od(wawa("2026-10-11 10:30"), "low", "high")),
                    Doniczka("Skrzydłokwiat", "skrzydlokwiat", gleba=od(poczatek, 15)),
                    Doniczka("Azalia", "azalia", gleba=od(poczatek, 30, 45))]
        plik, wpisy = przebieg(doniczki, poczatek)
        self.assertEqual(wpisy, [])
        # wpis z tą samą sekundą już jest (ponowiony przebieg albo cofnięty zegar)
        plik["historia"].append({"id": "20261011T090000Z-podlej", "ts": rosliny.iso(teraz)})
        _, wpisy = przebieg(doniczki, teraz, plik)
        self.assertEqual(reguly(wpisy), ["podlej", "czujnik", "podsumowanie"])
        self.assertEqual([w["id"] for w in wpisy], ["20261011T090000Z-podlej-2", "20261011T090000Z-czujnik",
                                                    "20261011T090000Z-podsumowanie"])
        for w in wpisy:
            self.assertTrue(w["id"].isascii())
            self.assertRegex(w["tag"], r"^[a-z0-9-]{1,32}$")
            self.assertFalse(w["url"].startswith(("/", "http")), "adres względny, w zakresie aplikacji")
        self.assertEqual(wpisy[0]["tag"], "podlej-fikus-skrzydlokwiat-azali")

    def test_adres_jak_encodeURIComponent(self):
        """Strona odwraca #roslina= przez decodeURIComponent; te wartości to wynik
        encodeURIComponent z Node 22 dla tych samych nazw."""
        self.assertEqual(rosliny._adres("Skrzydłokwiat"), "rosliny.html#roslina=Skrzyd%C5%82okwiat")
        self.assertEqual(rosliny._adres("a b!'()*~"), "rosliny.html#roslina=a%20b!'()*~")
        self.assertEqual(rosliny._adres("Ąę#&=/?"), "rosliny.html#roslina=%C4%84%C4%99%23%26%3D%2F%3F")


class TestOdpornosc(unittest.TestCase):
    TERAZ = wawa("2026-10-12 13:00")

    def test_stan_sprzed_etapu_4(self):
        """Bez prog_gleba, podlań, światła i zgłoszeń — reguły nie padają. Bez progu
        w jednostkach czujnika nie ma histerezy, więc „ok" od razu kończy epizod."""
        stare_pola = ("prog_gleba", "swiatlo_potrzeba_lxh", "swiatlo_dobowe", "podlania", "do_zgloszenia",
                      "uwagi", "szereg", "R", "prog")

        def stary(d, t):
            return {k: v for k, v in d.stan(t).items() if k not in stare_pola}

        start = wawa("2026-10-12 11:00")
        fikus = Doniczka(gleba=lambda t: 21 if start <= t < wawa("2026-10-12 14:00") else 29)
        plik, _ = przebieg(None, start, stany=[stary(fikus, start)])
        plik, wpisy = przebieg(None, self.TERAZ, plik, stany=[stary(fikus, self.TERAZ)])
        self.assertEqual([w["tresc"] for w in wpisy], ["Fikus: gleba 21%."])
        plik, _ = przebieg(None, wawa("2026-10-12 14:00"), plik, stany=[stary(fikus, wawa("2026-10-12 14:00"))])
        self.assertIsNone(plik["stan_regul"]["Fikus"]["ponizej_od"])
        niedziela = wawa("2026-10-18 10:00")
        _, wpisy = przebieg(None, niedziela, plik, stany=[stary(fikus, niedziela)])
        self.assertEqual(wpisy[0]["tresc"], "Fikus: w porządku, gleba 29%; bez wykrytego podlania; "
                                            "światło: za mało pomiaru z ostatnich 7 dób.")

    def test_zepsute_wejscie_nie_wywraca(self):
        dobry = Doniczka(bateria="low").stan(self.TERAZ)
        zle_stany = [None, {}, {"nazwa": 5}, "x", {**dobry, "nazwa": "Zepsuta", "werdykt": ["podlej"],
                                                  "gatunek": ["fikus"], "ostatnie": "x", "podlania": {"a": 1},
                                                  "uwagi": "Wyjmij", "do_zgloszenia": "x", "swiatlo_dobowe": 5},
                     dobry]
        zle_pliki = [None, [], "x", {"historia": "x", "stan_regul": [], "podsumowanie_ostatnie": 5},
                     {"stan_regul": {"Fikus": {"ponizej_od": "wczoraj", "wyslano": "x", "na_sucho": [None, 5],
                                               "czujnik": {"bateria": "x"}, "noc": ["x", {"powod": None}]}},
                      "historia": [{"id": ["x"], "ts": rosliny.iso(self.TERAZ)}]}]
        for plik in zle_pliki:
            with self.subTest(plik=plik):
                wynik, wpisy = przebieg(None, wawa("2026-10-11 13:00"), plik, "na-sucho", stany=zle_stany)
                self.assertEqual(set(wynik), KLUCZE_PLIKU)
                self.assertEqual(reguly(wpisy), ["czujnik", "podsumowanie"])

    def test_nie_zmienia_wejscia_i_nie_mieli_pliku(self):
        """Bez zmian w roślinach plik po przebiegu jest taki sam — zapisz.sh nie robi
        wtedy commita co godzinę."""
        doniczki = [Doniczka(), Doniczka("Azalia", "azalia", gleba=45)]
        plik, _ = przebiegi(doniczki, [wawa("2026-10-12 10:00"), wawa("2026-10-12 11:00")])
        stany = [d.stan(wawa("2026-10-12 12:00")) for d in doniczki]
        kopia, stany_kopia = copy.deepcopy(plik), copy.deepcopy(stany)
        wynik = rosliny.zaplanuj_powiadomienia(stany, plik, wawa("2026-10-12 12:00"), WAWA, "wlaczone", "9-1")
        self.assertEqual((plik, stany), (kopia, stany_kopia))
        self.assertEqual(wynik, plik)

    def test_roslina_nieobecna_w_przebiegu_zachowuje_stan(self):
        """Błąd obliczeń jednej rośliny (fetch.py ją wtedy pomija) nie może zerować jej
        liczników — inaczej po powrocie dostałaby „podlej" od nowa."""
        azalia = {"ponizej_od": rosliny.iso(self.TERAZ - 5 * GODZ), "wyslano": [rosliny.iso(self.TERAZ - 3 * GODZ)],
                  "na_sucho": [], "czujnik": {"bateria": {"wyslano": rosliny.iso(self.TERAZ - DOBA)}}, "noc": []}
        plik, _ = przebieg([Doniczka()], self.TERAZ, {**WLACZONE, "stan_regul": {"Azalia": azalia}})
        self.assertEqual(plik["stan_regul"]["Azalia"], azalia)

    def test_plik_publiczny_bez_subskrypcji(self):
        plik, _ = przebiegi([Doniczka(gleba=od(wawa("2026-10-11 11:00"), 21), bateria="low")],
                            [wawa("2026-10-11 11:00"), wawa("2026-10-11 13:00")])
        tekst = json.dumps(plik, ensure_ascii=False, allow_nan=False)
        self.assertEqual(set(plik), KLUCZE_PLIKU)
        for zakazane in ("endpoint", "p256dh", "auth", "http"):
            self.assertNotIn(zakazane, tekst)
        self.assertEqual({w["regula"] for w in plik["historia"]}, {"podlej", "czujnik", "podsumowanie"})
        for w in plik["historia"]:
            self.assertEqual(set(w), {"id", "ts", "przebieg", "regula", "rosliny", "tytul", "tresc", "tag", "url",
                                      "na_sucho"})


if __name__ == "__main__":
    unittest.main()
