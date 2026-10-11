#!/usr/bin/env python3
"""Reguły powiadomień — rosliny.zaplanuj_powiadomienia() (etap 4).

Stany roślin powstają z syntetycznych wierszy CSV przez prawdziwe stan_rosliny(), tak
jak w kolektorze, więc reguły dostają ten kształt, który dostaną naprawdę. Każda granica
(2 godz. „poniżej", 21:00 i 8:00 w Europe/Warsaw — także w dniu zmiany czasu, 2 „podlej"
na dobę, ponowienie po 24 i 12 godz., histereza 6 pkt, 60 dni historii, niedziela 10:00,
u = 0,45 końca epizodu „przestaw") jest sprawdzana z obu stron, żeby przesunięcie o jeden
wyszło na teście.

Bez `ustawienia` planer dostaje obu telefonom telefony.DOMYSLNE (cisza 21–8, podsumowanie
wyłączone) — stare klasy testów sprawdzają więc, że przy domyślnych ustawieniach decyzje
są takie jak przed ustawieniami per telefon. Ustawienia, cisza i kolejka odłożonych mają
własne klasy na końcu pliku.
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
import telefony  # noqa: E402

WAWA = ZoneInfo("Europe/Warsaw")
MIN = 60_000
GODZ = 60 * MIN
DOBA = 24 * GODZ
KODY = {"gleba": "humidity", "temp": "temp_current", "wilg": "env_humidity",
        "swiatlo": "illumiance", "bateria": "battery_state", "alarm": "water_warning"}
KLUCZE_PLIKU = {"tryb", "wlaczone_od", "historia", "stan_regul", "podsumowanie_ostatnie", "telefony"}
KLUCZE_WPISU = {"id", "ts", "przebieg", "regula", "rosliny", "tytul", "tresc", "tag", "url", "na_sucho",
                "telefony"}
OBA = ["android", "iphone"]


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


def przebieg(doniczki, teraz: int, plik=WLACZONE, tryb: str = "wlaczone", stany=None, ustawienia=None):
    """Jeden przebieg kolektora: stany → reguły → plik przez JSON, jak z dysku.
    Zwraca (plik, wpisy tego przebiegu) — te, które nadawca by wziął."""
    stany = [d.stan(teraz) for d in doniczki] if stany is None else stany
    nr = f"{teraz}-1"
    wynik = rosliny.zaplanuj_powiadomienia(stany, copy.deepcopy(plik), teraz, WAWA, tryb, nr,
                                           copy.deepcopy(ustawienia))
    wynik = json.loads(json.dumps(wynik, allow_nan=False))
    return wynik, [w for w in wynik["historia"] if w.get("przebieg") == nr]


def przebiegi(doniczki, czasy, plik=WLACZONE, tryb: str = "wlaczone", ustawienia=None):
    """Kolejne przebiegi; zwraca plik po ostatnim i {czas: wpisy}."""
    wpisy = {}
    for t in czasy:
        plik, wpisy[t] = przebieg(doniczki, t, plik, tryb, ustawienia=ustawienia)
    return plik, wpisy


def ust(**zmiany) -> dict:
    """Ustawienia jednego telefonu: domyślne z telefony.py z podmienionymi polami."""
    return {**telefony.DOMYSLNE, **zmiany}


def oba(**zmiany) -> dict:
    return {t: ust(**zmiany) for t in telefony.TELEFONY}


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
                         ("podlej", ["Fikus"], "Podlej: fikus", "podlej-fikus", "#fikus", False))
        self.assertEqual(w["telefony"], OBA, "przy domyślnych ustawieniach do obu telefonów")
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
        """Ponowienie nie czeka na poranne 2 godz. od 8:00 — to dotyczy tylko pierwszej
        wysyłki epizodu. Dawniej „azalia co 12 godz." wypadało rano około 10:00, czyli
        raz na dobę jak u pozostałych (przegląd 9.10)."""
        poczatek = wawa("2026-10-12 18:30")
        fikus = Doniczka(gleba=od(poczatek, 21))
        azalia = Doniczka("Azalia", "azalia", gleba=od(poczatek, 37, 45))   # R 0,68: podlej, nie pilne
        plik, wpisy = przebiegi([fikus, azalia], [poczatek, wawa("2026-10-12 20:20")])
        self.assertEqual(wpisy[wawa("2026-10-12 20:20")][0]["rosliny"], ["Fikus", "Azalia"])
        # 12 godz. później, w nocy — nic; pierwszy przebieg po 8:00 — azalia, fikus jeszcze nie
        self.assertEqual(przebieg([fikus, azalia], wawa("2026-10-13 07:59"), plik)[1], [])
        plik, wpisy = przebieg([fikus, azalia], wawa("2026-10-13 08:15"), plik)
        self.assertEqual([w["rosliny"] for w in wpisy], [["Azalia"]])
        # wieczorem fikus po dobie, azalia po 12 godz. — drugie „podlej" tej doby
        _, wpisy = przebieg([fikus, azalia], wawa("2026-10-13 20:15"), plik)
        self.assertEqual([w["rosliny"] for w in wpisy], [["Fikus", "Azalia"]])

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
        self.assertEqual(w["url"], "#rosliny", "kilka roślin — lista, nie pierwsza z nich")

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
                         ("Czujnik: fikus", "Fikus: bateria na wyczerpaniu.", "czujnik-fikus", "#fikus"))
        self.assertEqual(list(plik["stan_regul"]["Fikus"]["czujnik"]), ["bateria"])

    def test_bateria_na_granicy_low_middle_to_jeden_alarm(self):
        """Bateria skacząca low ↔ middle co godzinę dawniej dawała alarm przy każdym
        powrocie do „low" (przegląd 9.10: 28 zamiast 1). Znacznik trzyma się do „high"."""
        def bateria(t):
            return "low" if int((t - wawa("2026-10-12 09:00")) // GODZ) % 2 == 0 else "middle"

        czasy = [wawa("2026-10-12 09:00") + k * GODZ + 30 * MIN for k in range(11)]   # 9:30 … 19:30
        _, wpisy = przebiegi([Doniczka(bateria=bateria)], czasy)
        self.assertEqual(sum(len(wpisy[t]) for t in czasy), 1)

    def test_nowy_alarm_niesie_tez_wczesniejszy_powod(self):
        """Ten sam tag „czujnik-fikus" podmienia na telefonie poprzedni alarm — nowy wpis
        musi powtórzyć nieprzeczytaną „baterię", inaczej znikałaby pod „sonda wyjęta"."""
        wyjeta = wawa("2026-10-12 12:00")
        fikus = Doniczka(gleba=lambda t: 9 if t >= wyjeta else 40, bateria="low")
        czasy = [wawa("2026-10-12 10:30"), wawa("2026-10-12 14:30")]
        _, wpisy = przebiegi([fikus], czasy)
        self.assertEqual(reguly(wpisy[czasy[0]]), ["czujnik"])
        (w,) = wpisy[czasy[1]]
        self.assertIn("bateria na wyczerpaniu", w["tresc"])
        self.assertIn("sonda wyjęta", w["tresc"])

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


class TestZaokraglanie(unittest.TestCase):
    """Liczby w treściach połówką w górę — tak jak strona (Intl.NumberFormat, Math.round)
    pokazuje te same pola ze stan.json (przegląd, C1)."""

    def test_gleba_i_prog(self):
        stan = {"nazwa": "Fikus", "ostatnie": {"gleba": {"v": 22.5}}, "prog_gleba": 24, "werdykt": "podlej"}
        self.assertEqual(rosliny._linia_podlej(stan), "Fikus: gleba 23% (podlewaj przy ok. 24%).")

    def test_swiatlo_w_podsumowaniu(self):
        dzis = datetime(2026, 10, 18).date()
        stan = {"nazwa": "Fikus", "werdykt": "ok", "ostatnie": {"gleba": {"v": 40.5}}, "prog_gleba": 24.5,
                "swiatlo_potrzeba_lxh": 20000,
                "swiatlo_dobowe": [{"data": f"2026-10-{d}", "lxh": 3700, "pokrycie": 1.0} for d in range(11, 18)]}
        self.assertEqual(rosliny._linia_podsumowania(stan, dzis, WAWA),
                         "Fikus: w porządku, gleba 41% (podlewaj przy ok. 25%); bez wykrytego podlania; "
                         "światło śr. 3 700 lx·h na dobę, 19% potrzeby (pełne doby: 7 z 7).")


class TestPodsumowanie(unittest.TestCase):
    """Podsumowanie włączone na obu telefonach — tak działało przed ustawieniami per
    telefon. Domyślnie jest wyłączone (zatwierdzony ekran): test_domyslnie_wylaczone."""
    WLACZONE_PODSUMOWANIE = oba(podsumowanie=True)

    def trzy(self, **zmiany) -> list[Doniczka]:
        return [Doniczka(**zmiany), Doniczka("Skrzydłokwiat", "skrzydlokwiat", **zmiany),
                Doniczka("Azalia", "azalia", gleba=45, **zmiany)]

    def test_niedziela_od_10_raz_w_tygodniu_zawsze(self):
        doniczki = self.trzy()
        czasy = [wawa(t) for t in ("2026-10-10 10:00", "2026-10-11 09:59:59", "2026-10-11 10:00",
                                   "2026-10-11 11:00", "2026-10-11 20:00", "2026-10-18 10:00")]
        plik, wpisy = przebiegi(doniczki, czasy, ustawienia=self.WLACZONE_PODSUMOWANIE)
        self.assertEqual([reguly(wpisy[t]) for t in czasy], [[], [], ["podsumowanie"], [], [], ["podsumowanie"]])
        self.assertEqual(plik["podsumowanie_ostatnie"], "2026-10-18")
        w = wpisy[czasy[2]][0]
        self.assertEqual((w["rosliny"], w["url"], w["tag"], w["tytul"], w["telefony"]),
                         (["Fikus", "Skrzydłokwiat", "Azalia"], "#rosliny", "podsumowanie",
                          "Rośliny — podsumowanie tygodnia", OBA))
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
        # 100 lx to 12% potrzeby fikusa — ten sam przebieg daje też „przestaw"
        (w,) = [w for w in wpisy if w["regula"] == "podsumowanie"]
        self.assertIn("światło śr. 2 400 lx·h na dobę, 12% potrzeby (pełne doby: 6 z 7)", w["tresc"])
        bez = Doniczka(start=ms("2026-10-01T00:00:00Z"))
        self.assertIn("światło: za mało pomiaru", przebieg([bez], wawa("2026-10-11 10:00"))[1][0]["tresc"])

    def test_dziesiata_w_niedziele_zmiany_czasu(self):
        doniczki = self.trzy(start=ms("2026-10-20T00:00:00Z"))
        plik, wpisy = przebieg(doniczki, ms("2026-10-25T08:59:59Z"))        # 9:59:59 CET
        self.assertEqual(wpisy, [])
        self.assertEqual(reguly(przebieg(doniczki, ms("2026-10-25T09:00:00Z"), plik)[1]), ["podsumowanie"])

    def test_domyslnie_wylaczone_ale_wpis_powstaje(self):
        """D4: zatwierdzony ekran ma podsumowanie wyłączone. Wpis i tak powstaje (bez
        adresatów), a `podsumowanie_ostatnie` działa jak dotąd — włączenie przełącznika
        w środku niedzieli nie da drugiego podsumowania tego dnia."""
        doniczki = self.trzy()
        plik, wpisy = przebieg(doniczki, wawa("2026-10-11 10:00"))
        (w,) = wpisy
        self.assertEqual((w["regula"], w["telefony"]), ("podsumowanie", []))
        self.assertEqual(plik["podsumowanie_ostatnie"], "2026-10-11")
        self.assertEqual(przebieg(doniczki, wawa("2026-10-11 11:00"), plik, ustawienia=self.WLACZONE_PODSUMOWANIE)[1],
                         [])
        # włączone na jednym telefonie — tylko on
        _, wpisy = przebieg(doniczki, wawa("2026-10-18 10:00"), plik,
                            ustawienia={"android": ust(), "iphone": ust(podsumowanie=True)})
        self.assertEqual([w["telefony"] for w in wpisy], [["iphone"]])


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
                         ("wlaczone", False, "Powiadomienia włączone", "wlaczone", "#rosliny",
                          ["Fikus", "Skrzydłokwiat"]))
        self.assertEqual(w["telefony"], OBA)
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
                         [("wlaczone", "Teraz nic nie wymaga uwagi.", "#rosliny")])
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

    def test_adres_to_slug_nazwy_w_aplikacji(self):
        """D7: `#<slug nazwy>` (ta sama funkcja co znaczniki), `#rosliny` bez nazwy, a slug
        równy zakładce dostaje „-2" — inaczej `#historia` otworzyłoby zakładkę, a nie
        roślinę. Bez `rosliny.html`: ta strona to już tylko przekierowanie."""
        self.assertEqual(rosliny._adres("Skrzydłokwiat"), "#skrzydlokwiat")
        self.assertEqual(rosliny._adres("Fikus"), "#fikus")
        self.assertEqual(rosliny._adres("Ąę#&=/?"), "#ae")
        self.assertEqual(rosliny._adres("Mała Łódź 2"), "#mala-lodz-2")
        for zakladka in ("Dom", "Rośliny", "Historia", "Powiadomienia"):
            self.assertEqual(rosliny._adres(zakladka), "#" + rosliny._slug(zakladka) + "-2")
        for pusta in (None, "", "!!!"):
            self.assertEqual(rosliny._adres(pusta), "#rosliny")


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
        zle_stany[4].update({"swiatlo_ocena": {"kierunek": ["jasniej"], "u": "x"}})
        zle_stany.append({**dobry, "nazwa": "Ocena", "swiatlo_ocena": 5})
        zle_stany.append({**dobry, "nazwa": "Ocena2", "swiatlo_ocena": {"kierunek": "jasniej", "u": None,
                                                                       "szczyt_lx": "x"}})
        zle_pliki = [None, [], "x", {"historia": "x", "stan_regul": [], "podsumowanie_ostatnie": 5, "telefony": 5},
                     {"stan_regul": {"Fikus": {"ponizej_od": "wczoraj", "wyslano": "x", "na_sucho": [None, 5],
                                               "czujnik": {"bateria": "x"}, "noc": ["x", {"powod": None}],
                                               "przestaw": "x"},
                                     "Ocena": {"przestaw": {"kierunek": 5}}},
                      "historia": [{"id": ["x"], "ts": rosliny.iso(self.TERAZ)}],
                      "telefony": {"android": {"odlozone": [5, {"regula": "podlej", "ts": "x"},
                                                            {"regula": "czujnik", "obiekt": "Fikus",
                                                             "ts": rosliny.iso(self.TERAZ), "powody": "x",
                                                             "minione": [5]},
                                                            {"regula": "przestaw", "obiekt": ["x"],
                                                             "ts": rosliny.iso(self.TERAZ)}]},
                                   "iphone": []}}]
        ustawienia = [None, 5, {"android": "x", "iphone": {"podlej": "nie", "od": True, "x": object()}}]
        for plik in zle_pliki:
            for u in ustawienia:
                with self.subTest(plik=plik, ustawienia=u):
                    wynik = rosliny.zaplanuj_powiadomienia(zle_stany, copy.deepcopy(plik), wawa("2026-10-11 13:00"),
                                                           WAWA, "na-sucho", "1-1", u)
                    wynik = json.loads(json.dumps(wynik, allow_nan=False))
                    wpisy = [w for w in wynik["historia"] if w.get("przebieg") == "1-1"]
                    self.assertEqual(set(wynik), KLUCZE_PLIKU)
                    self.assertEqual(reguly(wpisy), ["czujnik", "przestaw", "podsumowanie"])
                    self.assertEqual(wpisy[1]["rosliny"], ["Ocena2"])

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
                  "na_sucho": [], "czujnik": {"bateria": {"wyslano": rosliny.iso(self.TERAZ - DOBA)}}, "noc": [],
                  # strażnik: stan „przestaw" też przechodzi bez zmian (przechodzi i na wersji
                  # sprzed tej reguły, bo ta przepisywała stan nieobecnej rośliny w całości)
                  "przestaw": {"kierunek": "jasniej", "od": rosliny.iso(self.TERAZ - 2 * DOBA),
                               "wyslano": rosliny.iso(self.TERAZ - 2 * DOBA)}}
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
            self.assertEqual(set(w), KLUCZE_WPISU)


def odlozone(plik, telefon="android") -> list[dict]:
    return plik["telefony"][telefon]["odlozone"]


def z_ocena(d: Doniczka, teraz: int, kierunek=None, u=None, szczyt=None, za_duzo=None) -> dict:
    """Stan rośliny z podmienioną oceną światła — granice u bez budowania sum lx·h."""
    s = d.stan(teraz)
    s["swiatlo_ocena"] = None if kierunek is None else {"kierunek": kierunek, "u": u, "doby": [],
                                                        "szczyt_lx": szczyt}
    if za_duzo is not None:
        s["swiatlo_za_duzo_lx"] = za_duzo
    return s


# Android z domyślną ciszą 21–8, iPhone bez ciszy — najprostszy rozjazd telefonów.
A_CISZA_B_BEZ = {"android": ust(), "iphone": ust(cisza=False)}


class TestUstawieniaTelefonow(unittest.TestCase):
    """Ustawienia mówią tylko, kto dostaje wpis — decyzje reguł zostają te same."""
    START = wawa("2026-10-12 11:00")

    def doniczki(self):
        return [Doniczka(gleba=od(self.START, 21)),
                Doniczka("Skrzydłokwiat", "skrzydlokwiat", bateria=od(wawa("2026-10-12 10:00"), "low", "high"))]

    def scenariusz(self, ustawienia):
        czasy = [wawa(t) for t in ("2026-10-12 10:30", "2026-10-12 11:00", "2026-10-12 13:00",
                                   "2026-10-13 12:50", "2026-10-18 10:00")]
        return przebiegi(self.doniczki(), czasy, ustawienia=ustawienia)

    def test_jawne_domyslne_to_to_samo_co_brak(self):
        bez, wpisy = self.scenariusz(None)
        jawne, _ = self.scenariusz(oba())
        self.assertEqual(bez, jawne)
        wszystkie = [w for x in wpisy.values() for w in x]
        self.assertEqual(reguly(wszystkie), ["czujnik", "podlej", "podlej", "podlej", "podsumowanie"])
        self.assertEqual([w["telefony"] for w in wszystkie], [OBA, OBA, OBA, OBA, []])

    def test_regula_wylaczona_na_jednym_telefonie(self):
        _, wpisy = self.scenariusz({"android": ust(podlej=False), "iphone": ust(czujnik=False)})
        self.assertEqual([(w["regula"], w["telefony"]) for x in wpisy.values() for w in x],
                         [("czujnik", ["android"]), ("podlej", ["iphone"]), ("podlej", ["iphone"]),
                          ("podlej", ["iphone"]), ("podsumowanie", [])])

    def test_wylaczona_na_obu_wpis_bez_adresatow_te_same_liczniki(self):
        """Wpis powstaje z `telefony: []` (nadawca go pominie), a epizod liczy się jak
        zawsze — po włączeniu reguły nie przyjdzie zaległe „podlej" za cały tydzień."""
        domyslne, _ = self.scenariusz(None)
        wylaczone, wpisy = self.scenariusz(oba(podlej=False, czujnik=False))
        self.assertEqual(domyslne["stan_regul"], wylaczone["stan_regul"])
        self.assertEqual({tuple(w["telefony"]) for x in wpisy.values() for w in x}, {()})
        self.assertEqual(wylaczone["telefony"], {t: {"odlozone": []} for t in telefony.TELEFONY},
                         "wyłączona reguła nie trafia też do kolejki")

    def test_powitanie_idzie_do_wszystkich_poza_cisza(self):
        """Powitanie nie ma przełącznika — i nigdy nie czeka w kolejce."""
        wylaczony = {k: False for k in telefony.KLUCZE_REGUL}
        _, wpisy = przebieg([Doniczka()], wawa("2026-10-12 12:00"), None, ustawienia={
            "android": ust(**wylaczony), "iphone": ust()})
        self.assertEqual([(w["regula"], w["telefony"]) for w in wpisy], [("wlaczone", OBA)])
        plik, wpisy = przebieg([Doniczka()], wawa("2026-10-12 22:00"), None, ustawienia=A_CISZA_B_BEZ)
        self.assertEqual([(w["regula"], w["telefony"]) for w in wpisy], [("wlaczone", ["iphone"])])
        self.assertEqual(odlozone(plik), [])


class TestCiszaPerTelefon(unittest.TestCase):
    """D12: telefon w ciszy dostaje to, co go ominęło, w pierwszym przebiegu po jej końcu —
    sprawdzone na świeżym stanie, jako osobny wpis z `odlozone: true`."""

    def fikus_od(self, poczatek, **kw):
        return Doniczka(gleba=od(poczatek, 21), **kw)

    def test_podlej_w_nocy_do_b_a_dostaje_rano(self):
        fikus = self.fikus_od(wawa("2026-10-12 20:30"))
        plik, _ = przebieg([fikus], wawa("2026-10-12 20:30"), ustawienia=A_CISZA_B_BEZ)
        plik, wpisy = przebieg([fikus], wawa("2026-10-12 22:30"), plik, ustawienia=A_CISZA_B_BEZ)
        self.assertEqual([(w["regula"], w["telefony"]) for w in wpisy], [("podlej", ["iphone"])])
        self.assertEqual(odlozone(plik), [{"regula": "podlej", "obiekt": "Fikus",
                                           "ts": rosliny.iso(wawa("2026-10-12 22:30")),
                                           "ponizej_od": rosliny.iso(wawa("2026-10-12 20:30"))}])
        self.assertEqual(odlozone(plik, "iphone"), [])
        czasy = [wawa(t) for t in ("2026-10-12 23:30", "2026-10-13 03:00", "2026-10-13 07:59:59")]
        plik, wpisy = przebiegi([fikus], czasy, plik, ustawienia=A_CISZA_B_BEZ)
        self.assertEqual([w for x in wpisy.values() for w in x], [])
        self.assertEqual(len(odlozone(plik)), 1)
        plik, wpisy = przebieg([fikus], wawa("2026-10-13 08:00"), plik, ustawienia=A_CISZA_B_BEZ)
        (w,) = wpisy
        self.assertEqual((w["regula"], w["telefony"], w["odlozone"], w["tresc"], w["tag"], w["url"]),
                         ("podlej", ["android"], True, "Fikus: gleba 21% (podlewaj przy ok. 24%).", "podlej-fikus",
                          "#fikus"))
        self.assertEqual(odlozone(plik), [], "kolejka czyści się w tym samym wyniku")
        self.assertEqual(plik["stan_regul"]["Fikus"]["wyslano"], [rosliny.iso(wawa("2026-10-12 22:30"))],
                         "dostarczenie odłożonego to nie nowa wysyłka epizodu")
        self.assertEqual(przebieg([fikus], wawa("2026-10-13 09:00"), plik, ustawienia=A_CISZA_B_BEZ)[1], [])

    def test_przy_domyslnych_w_nocy_nic_nie_czeka(self):
        """Strażnik zgodności: obie cisze 21–8 to dawna noc — nic się nie decyduje, więc
        i kolejka zostaje pusta."""
        fikus = self.fikus_od(wawa("2026-10-12 20:30"))
        plik, wpisy = przebiegi([fikus], [wawa("2026-10-12 20:30"), wawa("2026-10-12 22:30")])
        self.assertEqual([w for x in wpisy.values() for w in x], [])
        self.assertEqual(plik["telefony"], {t: {"odlozone": []} for t in telefony.TELEFONY})

    def test_podlana_w_nocy_rano_nic(self):
        poczatek, podlanie = wawa("2026-10-12 20:30"), wawa("2026-10-13 02:00")
        fikus = Doniczka(gleba=lambda t: 40 if t < poczatek or t >= podlanie else 21)
        plik, _ = przebiegi([fikus], [poczatek, wawa("2026-10-12 22:30")], ustawienia=A_CISZA_B_BEZ)
        self.assertEqual(len(odlozone(plik)), 1)
        plik, wpisy = przebieg([fikus], wawa("2026-10-13 08:00"), plik, ustawienia=A_CISZA_B_BEZ)
        self.assertEqual(wpisy, [])
        self.assertEqual(odlozone(plik), [])

    def test_podlana_za_malo_w_nocy_to_nowy_epizod_bez_odlozonego(self):
        """Podlanie, po którym gleba dalej jest poniżej progu, kończy epizod — rano roślina
        znowu „do podlania", ale to nowy epizod (nowe `ponizej_od`): odłożone z 22:30
        odpada, a świeże przyjdzie po 2 godz. jak zawsze. Podlanie o 4:00, żeby do 9:50
        nie minęło 6 godz. i szczyt tego podlania nie zmienił jeszcze skali."""
        poczatek, podlanie = wawa("2026-10-12 20:30"), wawa("2026-10-13 04:00")
        skrzydlokwiat = Doniczka("Skrzydłokwiat", "skrzydlokwiat",
                                 gleba=lambda t: 40 if t < poczatek else (26 if t >= podlanie else 15))
        plik, _ = przebiegi([skrzydlokwiat], [poczatek, wawa("2026-10-12 22:30")], ustawienia=A_CISZA_B_BEZ)
        self.assertEqual(len(odlozone(plik)), 1)
        self.assertEqual(skrzydlokwiat.stan(wawa("2026-10-13 08:00"))["werdykt"], "podlej")
        plik, wpisy = przebieg([skrzydlokwiat], wawa("2026-10-13 08:00"), plik, ustawienia=A_CISZA_B_BEZ)
        self.assertEqual(wpisy, [])
        self.assertEqual(odlozone(plik), [])
        _, wpisy = przebieg([skrzydlokwiat], wawa("2026-10-13 09:50"), plik, ustawienia=A_CISZA_B_BEZ)
        self.assertEqual([(w["regula"], w["telefony"]) for w in wpisy], [("podlej", OBA)])

    def test_bez_wspolnej_nocy_nie_ma_porannego_czekania(self):
        """Dawne „po nocy od 8:00" to koniec wspólnej nocy telefonów. Gdy iPhone nie ma
        ciszy, wspólnej nocy nie ma — „podlej" z 3:00 idzie o 5:00 na iPhone'a, a Android
        dostaje je po swojej ciszy. Przy domyślnych obu (strażnik) dopiero o 10:00."""
        fikus = self.fikus_od(wawa("2026-10-13 03:00"))
        _, wpisy = przebiegi([fikus], [wawa("2026-10-13 03:00"), wawa("2026-10-13 05:00")], ustawienia=A_CISZA_B_BEZ)
        self.assertEqual([(w["regula"], w["telefony"]) for x in wpisy.values() for w in x], [("podlej", ["iphone"])])
        czasy = [wawa(t) for t in ("2026-10-13 03:00", "2026-10-13 05:00", "2026-10-13 09:49", "2026-10-13 09:50")]
        _, wpisy = przebiegi([fikus], czasy)
        self.assertEqual([reguly(wpisy[t]) for t in czasy], [[], [], [], ["podlej"]])

    def test_czujnik_z_nocy_ktory_minal_rano_do_rana_minelo(self):
        wyjeta, z_powrotem = wawa("2026-10-12 22:00"), wawa("2026-10-13 02:00")
        fikus = Doniczka(gleba=lambda t: 9 if wyjeta <= t < z_powrotem else 40)
        czasy = [wawa(t) for t in ("2026-10-12 22:30", "2026-10-13 00:30", "2026-10-13 03:00")]
        plik, wpisy = przebiegi([fikus], czasy, ustawienia=A_CISZA_B_BEZ)
        self.assertEqual([(w["regula"], w["telefony"]) for x in wpisy.values() for w in x], [("czujnik", ["iphone"])])
        plik, wpisy = przebieg([fikus], wawa("2026-10-13 08:00"), plik, ustawienia=A_CISZA_B_BEZ)
        (w,) = wpisy
        self.assertEqual((w["regula"], w["telefony"], w["odlozone"]), ("czujnik", ["android"], True))
        self.assertTrue(w["tresc"].startswith("Fikus: w nocy (13.10 00:30) od 12.10 22:00 gleba pokazuje"), w["tresc"])
        self.assertTrue(w["tresc"].endswith("Do rana minęło."))
        self.assertEqual(odlozone(plik), [])

    def test_nowy_powod_w_nocy_dopisuje_sie_do_kolejki(self):
        """Bateria o 22:00, sonda wyjęta o 3:00 (zgłoszenie od 5:00): Android dostaje rano
        oba powody w jednym wpisie, a nie tylko pierwszy z kolejki."""
        wyjeta = wawa("2026-10-13 03:00")
        fikus = Doniczka(gleba=lambda t: 9 if t >= wyjeta else 40, bateria=od(wawa("2026-10-12 22:00"), "low", "high"))
        plik, wpisy = przebiegi([fikus], [wawa("2026-10-12 22:30")], ustawienia=A_CISZA_B_BEZ)
        przed = copy.deepcopy(plik)
        wynik = rosliny.zaplanuj_powiadomienia([fikus.stan(wawa("2026-10-13 05:30"))], plik, wawa("2026-10-13 05:30"),
                                               WAWA, "wlaczone", "x-1", A_CISZA_B_BEZ)
        self.assertEqual(plik, przed, "scalanie kolejki nie może zmieniać wejścia")
        self.assertEqual([r["powod"] for r in odlozone(wynik)[0]["powody"]], ["bateria", "sonda"])
        self.assertEqual(odlozone(wynik)[0]["ts"], rosliny.iso(wawa("2026-10-12 22:30")), "czas pierwszego zdarzenia")
        plik = json.loads(json.dumps(wynik))
        plik, wpisy = przebieg([fikus], wawa("2026-10-13 08:00"), plik, ustawienia=A_CISZA_B_BEZ)
        (w,) = wpisy
        self.assertEqual(w["telefony"], ["android"])
        self.assertEqual(w["tresc"].split("\n")[0], "Fikus: bateria na wyczerpaniu.")
        self.assertIn("sonda wyjęta", w["tresc"])

    def test_swiezy_wpis_tej_reguly_zastepuje_odlozony(self):
        """O 8:00 nowy powód daje świeży „czujnik" do obu telefonów z wszystkimi trwającymi
        powodami — odłożony wpis o samej baterii byłby dublem."""
        wyjeta = wawa("2026-10-13 06:00")
        fikus = Doniczka(gleba=lambda t: 9 if t >= wyjeta else 40, bateria=od(wawa("2026-10-12 22:00"), "low", "high"))
        plik, _ = przebiegi([fikus], [wawa("2026-10-12 22:30"), wawa("2026-10-13 07:59")], ustawienia=A_CISZA_B_BEZ)
        self.assertEqual(len(odlozone(plik)), 1)
        plik, wpisy = przebieg([fikus], wawa("2026-10-13 08:00"), plik, ustawienia=A_CISZA_B_BEZ)
        (w,) = wpisy
        self.assertEqual((w["regula"], w["telefony"], "odlozone" in w), ("czujnik", OBA, False))
        self.assertIn("bateria", w["tresc"])
        self.assertEqual(odlozone(plik), [])

    def test_zmiana_ustawien_przed_ranem_kasuje_odlozone(self):
        fikus = self.fikus_od(wawa("2026-10-12 20:30"))
        plik, _ = przebiegi([fikus], [wawa("2026-10-12 20:30"), wawa("2026-10-12 22:30")], ustawienia=A_CISZA_B_BEZ)
        self.assertEqual(len(odlozone(plik)), 1)
        plik, wpisy = przebieg([fikus], wawa("2026-10-13 08:00"), plik,
                               ustawienia={"android": ust(podlej=False), "iphone": ust(cisza=False)})
        self.assertEqual(wpisy, [])
        self.assertEqual(odlozone(plik), [])

    def test_wlasne_godziny_22_7_i_0_6(self):
        u = {"android": ust(od=22, do=7), "iphone": ust(od=0, do=6)}
        fikus = self.fikus_od(wawa("2026-10-12 20:00"))
        plik, wpisy = przebiegi([fikus], [wawa("2026-10-12 20:00"), wawa("2026-10-12 22:00")], ustawienia=u)
        self.assertEqual([(w["regula"], w["telefony"]) for x in wpisy.values() for w in x], [("podlej", ["iphone"])])
        czasy = [wawa(t) for t in ("2026-10-13 00:30", "2026-10-13 06:00", "2026-10-13 06:59:59")]
        plik, wpisy = przebiegi([fikus], czasy, plik, ustawienia=u)
        self.assertEqual([w for x in wpisy.values() for w in x], [], "Android ma ciszę do 7:00")
        plik, wpisy = przebieg([fikus], wawa("2026-10-13 07:00"), plik, ustawienia=u)
        self.assertEqual([(w["regula"], w["telefony"], w.get("odlozone")) for w in wpisy],
                         [("podlej", ["android"], True)])

    def test_koniec_ciszy_przy_zmianie_czasu(self):
        """25.10.2026: 8:00 CET to 7:00 UTC, a dzień wcześniej 6:00 UTC. Cisza liczona stałym
        przesunięciem oddałaby kolejkę godzinę za wcześnie."""
        start = ms("2026-10-20T00:00:00Z")
        fikus = Doniczka(start=start, gleba=od(ms("2026-10-24T17:00:00Z"), 21))      # 19:00 CEST
        plik, wpisy = przebiegi([fikus], [ms("2026-10-24T17:00:00Z"), ms("2026-10-24T19:00:00Z")],
                                ustawienia=A_CISZA_B_BEZ)                                 # 21:00 CEST
        self.assertEqual([w["telefony"] for x in wpisy.values() for w in x], [["iphone"]])
        plik, wpisy = przebieg([fikus], ms("2026-10-25T06:59:59Z"), plik, ustawienia=A_CISZA_B_BEZ)
        self.assertEqual(wpisy, [])
        _, wpisy = przebieg([fikus], ms("2026-10-25T07:00:00Z"), plik, ustawienia=A_CISZA_B_BEZ)
        self.assertEqual([(w["telefony"], w.get("odlozone")) for w in wpisy], [(["android"], True)])

    def test_po_odlozonym_ponowienie_dla_telefonu_najwczesniej_po_odstepie(self):
        """iPhone z ciszą 23–7, Android domyślnie 21–8, azalia sucha od 19:00. O 21:01 „podlej"
        idzie do iPhone'a, Android dostaje je o 8:01 jako odłożone. Ponowienie azalii (12 godz.)
        liczy się od wysyłki do iPhone'a, więc o 9:01 wypada świeże — dawniej szło też do
        Androida, godzinę po odłożonym (przegląd, C3). Teraz Android dostaje kolejne nie
        wcześniej niż 12 godz. po 8:01."""
        u = {"android": ust(), "iphone": ust(od=23, do=7)}
        poczatek, koniec_suszy = wawa("2026-10-12 19:00"), wawa("2026-10-14 09:30")
        azalia = Doniczka("Azalia", "azalia", gleba=lambda t: 30 if poczatek <= t < koniec_suszy else 45)
        plik, dostal = WLACZONE, {t: [] for t in telefony.TELEFONY}
        teraz, pliki = wawa("2026-10-12 19:01"), {}
        while teraz <= wawa("2026-10-14 11:01"):
            plik, wpisy = przebieg([azalia], teraz, plik, ustawienia=u)
            pliki[teraz] = plik
            for w in wpisy:
                self.assertEqual(w["regula"], "podlej")
                for t in w["telefony"]:
                    dostal[t].append((teraz, bool(w.get("odlozone"))))
            teraz += GODZ
        self.assertEqual(dostal["iphone"], [(wawa("2026-10-12 21:01"), False), (wawa("2026-10-13 09:01"), False),
                                            (wawa("2026-10-13 21:01"), False)])
        self.assertEqual(dostal["android"], [(wawa("2026-10-13 08:01"), True), (wawa("2026-10-14 08:01"), True)])
        chwile = [t for t, _ in dostal["android"]]
        self.assertTrue(all(b - a >= 12 * GODZ for a, b in zip(chwile, chwile[1:])))
        # doręczenie zapisane w stanie reguły; bez zmian w danych plik się nie zmienia
        stan = pliki[wawa("2026-10-13 10:01")]["stan_regul"]["Azalia"]
        self.assertEqual(stan["podlej_dla"], {"android": rosliny.iso(wawa("2026-10-13 08:01"))})
        self.assertEqual(json.dumps(pliki[wawa("2026-10-13 10:01")], ensure_ascii=False, indent=1),
                         json.dumps(pliki[wawa("2026-10-13 11:01")], ensure_ascii=False, indent=1))
        # koniec epizodu (podlana) czyści doręczenia
        self.assertNotIn("podlej_dla", pliki[wawa("2026-10-14 11:01")]["stan_regul"]["Azalia"])

    def test_doreczenie_odlozonego_tez_czeka_odstep(self):
        """Ten sam odstęp pilnuje doręczenia z kolejki: Android dostał odłożone „podlej:
        azalia" o 8:01, a o 9:01 zmienił ciszę na 9–10, więc świeże ponowienie z 9:01 trafiło
        mu do kolejki. O 10:01 doręczenie byłoby dublem dwie godziny po poprzednim — odpada,
        a następne przychodzi świeżo o 21:01, 13 godz. po 8:01."""
        rano = {"android": ust(od=9, do=10), "iphone": ust(od=23, do=7)}
        wieczor = {"android": ust(), "iphone": ust(od=23, do=7)}
        azalia = Doniczka("Azalia", "azalia", gleba=od(wawa("2026-10-12 19:00"), 30, 45))
        plik, dostal, teraz = WLACZONE, [], wawa("2026-10-12 19:01")
        while teraz <= wawa("2026-10-13 22:01"):
            u = rano if teraz >= wawa("2026-10-13 09:01") else wieczor
            plik, wpisy = przebieg([azalia], teraz, plik, ustawienia=u)
            dostal += [(teraz, bool(w.get("odlozone"))) for w in wpisy if "android" in w["telefony"]]
            teraz += GODZ
        self.assertEqual(dostal, [(wawa("2026-10-13 08:01"), True), (wawa("2026-10-13 21:01"), False)])

    def test_inne_rosliny_dalej_ida_do_telefonu_po_odlozonym(self):
        """Blokada dotyczy tylko rośliny doręczonej jako odłożona: gdy w tym samym przebiegu
        ponowienie obejmuje też fikusa, Android dostaje osobny wpis z samym fikusem. Limit
        dnia liczy te dwa wpisy jako jedną decyzję — skrzydłokwiat sucho od 10:00 dostaje
        o 12:01 drugie „podlej" tej doby, a nie trafia na limit."""
        u = {"android": ust(), "iphone": ust(od=23, do=7)}
        azalia = Doniczka("Azalia", "azalia", gleba=od(wawa("2026-10-12 19:00"), 30, 45))
        fikus = Doniczka(gleba=od(wawa("2026-10-13 07:00"), 21))
        skrzydlokwiat = Doniczka("Skrzydłokwiat", "skrzydlokwiat", gleba=od(wawa("2026-10-13 10:00"), 15))
        doniczki = [azalia, fikus, skrzydlokwiat]
        plik, teraz = WLACZONE, wawa("2026-10-12 19:01")
        while teraz < wawa("2026-10-13 09:01"):
            plik, _ = przebieg(doniczki, teraz, plik, ustawienia=u)
            teraz += GODZ
        plik, wpisy = przebieg(doniczki, teraz, plik, ustawienia=u)
        self.assertEqual([(w["rosliny"], w["telefony"]) for w in wpisy],
                         [(["Azalia", "Fikus"], ["iphone"]), (["Fikus"], ["android"])])
        self.assertEqual(wpisy[1]["tytul"], "Podlej: fikus")
        self.assertEqual(plik["stan_regul"]["Fikus"]["wyslano"], [rosliny.iso(teraz)])
        plik, _ = przebiegi(doniczki, [wawa("2026-10-13 10:01"), wawa("2026-10-13 11:01")], plik, ustawienia=u)
        _, wpisy = przebieg(doniczki, wawa("2026-10-13 12:01"), plik, ustawienia=u)
        self.assertEqual([(w["rosliny"], w["telefony"]) for w in wpisy], [(["Skrzydłokwiat"], OBA)])

    def test_ttl_doby_i_limit_kolejki(self):
        teraz = wawa("2026-10-12 12:00")
        pozycja = {"regula": "podsumowanie", "obiekt": None}
        plik = {**WLACZONE, "telefony": {
            "android": {"odlozone": [{**pozycja, "ts": rosliny.iso(teraz - DOBA - 1000)}]},
            "iphone": {"odlozone": [{**pozycja, "ts": rosliny.iso(teraz - DOBA)}]}}}
        _, wpisy = przebieg([Doniczka()], teraz, plik, ustawienia=oba(podsumowanie=True))
        self.assertEqual([(w["regula"], w["telefony"], w["odlozone"]) for w in wpisy],
                         [("podsumowanie", ["iphone"], True)], "starsze niż doba odpada")
        noc = wawa("2026-10-12 23:00")
        duzo = [{"regula": "podlej", "obiekt": f"R{i}", "ts": rosliny.iso(noc - (30 - i) * MIN)} for i in range(25)]
        plik, _ = przebieg([Doniczka()], noc, {**WLACZONE, "telefony": {"android": {"odlozone": duzo}}},
                           ustawienia=A_CISZA_B_BEZ)
        self.assertEqual([p["obiekt"] for p in odlozone(plik)], [f"R{i}" for i in range(5, 25)])
        self.assertEqual(telefony.ODLOZONE_MAKS, 20)

    def test_odlozone_nie_licza_sie_do_limitu_dnia(self):
        fikus = Doniczka(gleba=od(wawa("2026-10-12 11:00"), 21))
        historia = [{"id": f"x{i}", "ts": rosliny.iso(wawa(f"2026-10-12 {g}")), "przebieg": "0-1", "regula": "podlej",
                     "rosliny": ["Inna"], "na_sucho": False, "telefony": ["android"], **dodatek}
                    for i, (g, dodatek) in enumerate((("08:00", {"odlozone": True}), ("10:00", {})))]
        plik = {**WLACZONE, "historia": historia, "stan_regul": {"Fikus": {
            "ponizej_od": rosliny.iso(wawa("2026-10-12 11:00")), "wyslano": [], "na_sucho": []}}}
        _, wpisy = przebieg([fikus], wawa("2026-10-12 13:00"), plik)
        self.assertEqual(reguly(wpisy), ["podlej"])
        historia[0].pop("odlozone")
        _, wpisy = przebieg([fikus], wawa("2026-10-12 13:00"), plik)
        self.assertEqual(wpisy, [], "dwa zwykłe tego dnia — limit")

    def test_bez_zmian_plik_identyczny_takze_z_kolejka(self):
        fikus = self.fikus_od(wawa("2026-10-12 20:30"))
        plik, _ = przebiegi([fikus], [wawa("2026-10-12 20:30"), wawa("2026-10-12 22:30")], ustawienia=A_CISZA_B_BEZ)
        self.assertEqual(len(odlozone(plik)), 1, "kolejka ma na czym się nie zmienić")
        teraz = wawa("2026-10-12 23:30")
        wynik = rosliny.zaplanuj_powiadomienia([fikus.stan(teraz)], copy.deepcopy(plik), teraz, WAWA, "wlaczone",
                                               "9-1", A_CISZA_B_BEZ)
        self.assertEqual(json.dumps(wynik, ensure_ascii=False, indent=1),
                         json.dumps(plik, ensure_ascii=False, indent=1))


class TestPrzestaw(unittest.TestCase):
    """Reguła „przestaw": epizod kierunku z `swiatlo_ocena`, jedna wysyłka na epizod."""

    def test_przez_prawdziwa_ocene_jeden_wpis_bez_ponowien(self):
        """100 lx przez całą dobę to 2400 lx·h, 12% potrzeby fikusa. Sonda wbita 5.10, więc
        trzecia pełna doba (6–8.10) kończy się o północy 9.10 — w nocy nic, rano raz."""
        fikus = Doniczka(swiatlo=100)
        czasy = [wawa(t) for t in ("2026-10-08 12:00", "2026-10-09 07:59", "2026-10-09 08:00", "2026-10-10 12:00",
                                   "2026-10-12 12:00")]
        self.assertIsNone(fikus.stan(czasy[0])["swiatlo_ocena"])
        plik, wpisy = przebiegi([fikus], czasy)
        self.assertEqual([reguly(wpisy[t]) for t in czasy], [[], [], ["przestaw"], [], []])
        (w,) = wpisy[czasy[2]]
        self.assertEqual((w["tytul"], w["tag"], w["url"], w["rosliny"], w["telefony"]),
                         ("Fikus: przestaw bliżej okna", "przestaw-fikus", "#fikus", ["Fikus"], OBA))
        self.assertEqual(w["tresc"], "Ostatnie 3 doby: średnio 12% potrzebnego światła. Fikus gubi liście po każdej "
                                     "przeprowadzce — przestaw raz, w najjaśniejsze miejsce.")
        self.assertEqual(plik["stan_regul"]["Fikus"]["przestaw"],
                         {"kierunek": "jasniej", "od": rosliny.iso(czasy[1]), "wyslano": rosliny.iso(czasy[2])})

    def test_kilka_roslin_jeden_wpis(self):
        doniczki = [Doniczka(swiatlo=100), Doniczka("Skrzydłokwiat", "skrzydlokwiat", swiatlo=100)]
        _, wpisy = przebieg(doniczki, wawa("2026-10-09 12:00"))
        (w,) = wpisy
        self.assertEqual((w["tytul"], w["tag"], w["url"]),
                         ("Przestaw: fikus, skrzydłokwiat", "przestaw-fikus-skrzydlokwiat", "#rosliny"))
        self.assertEqual(w["tresc"].split("\n"), [
            "Fikus: przestaw bliżej okna. Ostatnie 3 doby: średnio 12% potrzebnego światła. Fikus gubi liście po "
            "każdej przeprowadzce — przestaw raz, w najjaśniejsze miejsce.",
            "Skrzydłokwiat: przestaw bliżej okna. Ostatnie 3 doby: średnio 24% potrzebnego światła."])

    def test_koniec_epizodu_z_histereza(self):
        """„malo" poniżej 0,45 nie kończy epizodu (powrót do „jaśniej" nie daje drugiego
        wpisu), 0,45 i „ok" kończą — następne „jaśniej" to nowy epizod."""
        fikus = Doniczka()
        przebiegi_ = [("jasniej", 0.30, ["przestaw"]), ("malo", 0.40, []), ("jasniej", 0.30, []),
                      ("malo", 0.449, []), ("malo", 0.45, []), ("jasniej", 0.30, ["przestaw"]), ("ok", 0.70, []),
                      ("jasniej", 0.34, ["przestaw"])]
        plik = WLACZONE
        for i, (kierunek, u, oczekiwane) in enumerate(przebiegi_):
            teraz = wawa("2026-10-12 09:00") + i * GODZ
            with self.subTest(i=i, kierunek=kierunek, u=u):
                plik, wpisy = przebieg(None, teraz, plik, stany=[z_ocena(fikus, teraz, kierunek, u)])
                self.assertEqual(reguly(wpisy), oczekiwane)
                trwa = "przestaw" in plik["stan_regul"]["Fikus"]
                self.assertEqual(trwa, i not in (4, 6), "epizod trwa / skończony")

    def test_zmiana_kierunku_otwiera_nowy_epizod(self):
        fikus = Doniczka()
        t1, t2, t3 = wawa("2026-10-12 10:00"), wawa("2026-10-12 11:00"), wawa("2026-10-12 12:00")
        plik, w1 = przebieg(None, t1, stany=[z_ocena(fikus, t1, "jasniej", 0.2)])
        plik, w2 = przebieg(None, t2, plik, stany=[z_ocena(fikus, t2, "ciemniej", 0.2, 5000, 4000)])
        plik, w3 = przebieg(None, t3, plik, stany=[z_ocena(fikus, t3, "jasniej", 0.2)])
        self.assertEqual([w["tytul"] for w in w1 + w2 + w3],
                         ["Fikus: przestaw bliżej okna", "Fikus: odsuń od okna", "Fikus: przestaw bliżej okna"])
        self.assertEqual(w2[0]["tresc"], "Wczoraj w szczycie 5 000 lx, a liście przypalają się już od 4 000 lx. "
                                         "Najlepiej jasne miejsce bez bezpośredniego słońca.")

    def test_bez_oceny_stan_zostaje(self):
        """Werdykt „czujnik" (stare światło) daje ocenę None — epizod nie kończy się i po
        powrocie czujnika nie wychodzi drugi raz."""
        fikus = Doniczka()
        t1, t2, t3 = wawa("2026-10-12 10:00"), wawa("2026-10-12 11:00"), wawa("2026-10-12 12:00")
        plik, _ = przebieg(None, t1, stany=[z_ocena(fikus, t1, "jasniej", 0.2)])
        epizod = plik["stan_regul"]["Fikus"]["przestaw"]
        plik, wpisy = przebieg(None, t2, plik, stany=[z_ocena(fikus, t2)])
        self.assertEqual((wpisy, plik["stan_regul"]["Fikus"]["przestaw"]), ([], epizod))
        self.assertEqual(przebieg(None, t3, plik, stany=[z_ocena(fikus, t3, "jasniej", 0.2)])[1], [])

    def test_w_nocy_nic_rano_raz(self):
        fikus = Doniczka()
        noc, rano = wawa("2026-10-12 21:30"), wawa("2026-10-13 08:00")
        plik, wpisy = przebieg(None, noc, stany=[z_ocena(fikus, noc, "jasniej", 0.2)])
        self.assertEqual(wpisy, [])
        self.assertEqual(plik["stan_regul"]["Fikus"]["przestaw"], {"kierunek": "jasniej", "od": rosliny.iso(noc)})
        plik, wpisy = przebieg(None, rano, plik, stany=[z_ocena(fikus, rano, "jasniej", 0.2)])
        self.assertEqual(reguly(wpisy), ["przestaw"])

    def test_w_pasmie_histerezy_nie_wysyla(self):
        """Epizod z nocy, rano u = 0,40 („malo"): epizod trwa, ale „przestaw bliżej okna" przy
        40% potrzeby byłoby nieprawdą — wpis dopiero, gdy ocena wróci do „jaśniej"."""
        fikus = Doniczka()
        noc, rano, potem = wawa("2026-10-12 22:00"), wawa("2026-10-13 08:00"), wawa("2026-10-13 09:00")
        plik, _ = przebieg(None, noc, stany=[z_ocena(fikus, noc, "jasniej", 0.3)])
        plik, wpisy = przebieg(None, rano, plik, stany=[z_ocena(fikus, rano, "malo", 0.40)])
        self.assertEqual(wpisy, [])
        self.assertIn("przestaw", plik["stan_regul"]["Fikus"])
        _, wpisy = przebieg(None, potem, plik, stany=[z_ocena(fikus, potem, "jasniej", 0.3)])
        self.assertEqual(reguly(wpisy), ["przestaw"])

    def test_na_sucho_znacznik_na_sucho(self):
        fikus = Doniczka()
        t1, t2 = wawa("2026-10-12 10:00"), wawa("2026-10-12 11:00")
        plik, wpisy = przebieg(None, t1, None, "na-sucho", stany=[z_ocena(fikus, t1, "jasniej", 0.2)])
        self.assertEqual([(w["regula"], w["na_sucho"]) for w in wpisy], [("przestaw", True)])
        self.assertEqual(plik["stan_regul"]["Fikus"]["przestaw"],
                         {"kierunek": "jasniej", "od": rosliny.iso(t1), "na_sucho": rosliny.iso(t1)})
        self.assertEqual(przebieg(None, t2, plik, "na-sucho", stany=[z_ocena(fikus, t2, "jasniej", 0.2)])[1], [])

    def test_telefony_i_kolejka(self):
        """Wyłączone „przestaw" na iPhonie — tylko Android. Android w ciszy dostaje rano,
        jeśli kierunek się utrzymał; gdy rano to już tylko „malo", pozycja odpada."""
        fikus = Doniczka()
        t = wawa("2026-10-12 12:00")
        _, wpisy = przebieg(None, t, stany=[z_ocena(fikus, t, "jasniej", 0.2)],
                            ustawienia={"android": ust(), "iphone": ust(przestaw=False)})
        self.assertEqual([w["telefony"] for w in wpisy], [["android"]])
        noc, rano = wawa("2026-10-12 22:00"), wawa("2026-10-13 08:00")
        plik, wpisy = przebieg(None, noc, stany=[z_ocena(fikus, noc, "jasniej", 0.2)], ustawienia=A_CISZA_B_BEZ)
        self.assertEqual([w["telefony"] for w in wpisy], [["iphone"]])
        self.assertEqual(odlozone(plik)[0]["kierunek"], "jasniej")
        for kierunek, u, oczekiwane in (("jasniej", 0.25, [["android"]]), ("malo", 0.40, [])):
            with self.subTest(kierunek=kierunek):
                wynik, wpisy = przebieg(None, rano, plik, stany=[z_ocena(fikus, rano, kierunek, u)],
                                        ustawienia=A_CISZA_B_BEZ)
                self.assertEqual([w["telefony"] for w in wpisy], oczekiwane)
                self.assertEqual(odlozone(wynik), [])
        self.assertIn("25%", przebieg(None, rano, plik, stany=[z_ocena(fikus, rano, "jasniej", 0.25)],
                                      ustawienia=A_CISZA_B_BEZ)[1][0]["tresc"], "treść ze świeżej oceny")

    def test_procent_jak_na_karcie(self):
        """Karta pokazuje `swiatlo_ocena.proc`, a treść „przestaw" liczy procent z tego
        samego zapisanego u tą samą regułą (połówka w górę). u = 0,185 dawało w powiadomieniu
        „18%", a na karcie „19%" (przegląd, C1); u = 0,18451 zapisuje się jako 0,185."""
        fikus = Doniczka()
        t = wawa("2026-10-12 12:00")
        _, wpisy = przebieg(None, t, stany=[z_ocena(fikus, t, "jasniej", 0.185)])
        self.assertIn("średnio 19% potrzebnego światła", wpisy[0]["tresc"])
        s = fikus.stan(t)
        doby = [{"data": f"2026-10-{d:02d}", "lxh": 0.18451 * 20000, "pokrycie": 1.0, "szczyt_lx": 900}
                for d in (9, 10, 11)]
        s["swiatlo_ocena"] = rosliny.ocena_swiatla(doby, 20000, None, fikus.start, t, WAWA)
        self.assertEqual((s["swiatlo_ocena"]["u"], s["swiatlo_ocena"]["proc"]), (0.185, 19))
        _, wpisy = przebieg(None, t, stany=[s])
        self.assertIn(f"średnio {s['swiatlo_ocena']['proc']}% potrzebnego światła", wpisy[0]["tresc"])

    def test_powitanie_niesie_przestaw(self):
        fikus = Doniczka()
        t1, t2 = wawa("2026-10-12 12:00"), wawa("2026-10-12 13:00")
        plik, wpisy = przebieg(None, t1, None, stany=[z_ocena(fikus, t1, "jasniej", 0.3)])
        self.assertEqual(wpisy[0]["tresc"], "Już trwa:\nFikus: przestaw bliżej okna. Ostatnie 3 doby: średnio 30% "
                                            "potrzebnego światła. Fikus gubi liście po każdej przeprowadzce — przestaw "
                                            "raz, w najjaśniejsze miejsce.")
        self.assertEqual(przebieg(None, t2, plik, stany=[z_ocena(fikus, t2, "jasniej", 0.3)])[1], [])


class TestZgodnoscPliku(unittest.TestCase):
    """Strażnik zmiany formatu: plik z produkcji po włączeniu wysyłki (11.10, 16:24 UTC)
    nie ma pola `telefony` — nowy planer nie może z tego powodu wysłać drugiego powitania.
    Część o `wlaczone_od` przechodzi też na wersji sprzed ustawień per telefon (pilnuje,
    żeby tak zostało); stara wersja pada tu tylko na braku pola `telefony`."""
    PRODUKCJA = {
        "tryb": "wlaczone", "wlaczone_od": "2026-10-11T16:24:46Z",
        "historia": [{"id": "20261011T162446Z-wlaczone", "ts": "2026-10-11T16:24:46Z", "przebieg": "38155341006-1",
                      "regula": "wlaczone", "rosliny": [], "tytul": "Powiadomienia włączone",
                      "tresc": "Teraz nic nie wymaga uwagi.", "tag": "wlaczone", "url": "rosliny.html",
                      "na_sucho": False}],
        "stan_regul": {n: {"ponizej_od": None, "wyslano": [], "na_sucho": [], "czujnik": {}, "noc": []}
                       for n in ("Fikus", "Skrzydłokwiat", "Azalia")},
        "podsumowanie_ostatnie": "2026-10-11"}

    def test_stary_plik_po_wlaczeniu_bez_drugiego_powitania(self):
        doniczki = [Doniczka(), Doniczka("Skrzydłokwiat", "skrzydlokwiat"), Doniczka("Azalia", "azalia", gleba=45)]
        plik, wpisy = przebieg(doniczki, ms("2026-10-11T17:01:00Z"), self.PRODUKCJA)
        self.assertEqual(wpisy, [])
        self.assertEqual((plik["tryb"], plik["wlaczone_od"]), ("wlaczone", "2026-10-11T16:24:46Z"))
        self.assertEqual(plik["historia"], self.PRODUKCJA["historia"])
        self.assertEqual(plik["telefony"], {t: {"odlozone": []} for t in telefony.TELEFONY})
        # nowe pole dochodzi raz — drugi przebieg bez zmian daje ten sam plik
        drugi, _ = przebieg(doniczki, ms("2026-10-11T18:01:00Z"), plik)
        self.assertEqual(drugi, plik)

    def test_zywy_plik_z_repozytorium(self):
        """Strażnik na prawdziwym data/rosliny/powiadomienia.json: przeliczenie w trybie
        „wlaczone" nie zmienia `wlaczone_od` i nie daje powitania."""
        sciezka = REPO / "data" / "rosliny" / "powiadomienia.json"
        if not sciezka.exists():
            self.skipTest("brak data/rosliny/powiadomienia.json")
        plik = json.loads(sciezka.read_text(encoding="utf-8"))
        if plik.get("tryb") != "wlaczone" or not plik.get("wlaczone_od"):
            self.skipTest("plik sprzed włączenia wysyłki")
        teraz = rosliny._ms(plik["wlaczone_od"]) + GODZ
        wynik, wpisy = przebieg([], teraz, plik)
        self.assertEqual(wynik["wlaczone_od"], plik["wlaczone_od"])
        self.assertNotIn("wlaczone", reguly(wpisy))


if __name__ == "__main__":
    unittest.main()
