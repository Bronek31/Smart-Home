#!/usr/bin/env python3
"""Czujniki w doniczkach — obliczenia (rosliny.py) i osobny tor w kolektorze.

Warunek właściciela z 8.10: odczyty z doniczek nie mieszają się z tym, co strona pokazuje
dziś. Testy integracyjne sprawdzają to tam, gdzie mogłoby pęknąć: w plikach data/*.csv,
w data/index.json i w kodzie wyjścia kolektora, gdy tor roślin się wywróci.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch  # noqa: E402
import rosliny  # noqa: E402
from test_przyrostowe import (AtrapaTuya, GODZ, KODY, PrzebiegKolektora,  # noqa: E402
                              tydzien_odczytow)

WAWA = ZoneInfo("Europe/Warsaw")
KODY_ROSLINY = {"gleba": "humidity", "temp": "temp_current", "wilg": "env_humidity",
                "swiatlo": "illumiance", "bateria": "battery_state", "alarm": "water_warning"}


def ms(tekst: str) -> int:
    return int(datetime.fromisoformat(tekst.replace("Z", "+00:00")).timestamp() * 1000)


def wiersz(ts_ms: int, kod: str, wartosc, czujnik: str = "fikus") -> dict:
    return {"ts": rosliny.iso(ts_ms), "device_id": czujnik, "code": kod, "value": str(wartosc)}


def konf(**zmiany) -> dict:
    k = {"czujnik": "fikus", "nazwa": "Fikus", "gatunek": "fikus", "pokoj": None,
         "kody": dict(KODY_ROSLINY), "sucho": 10.0, "od": None}
    k.update(zmiany)
    return k


class TestKonfiguracja(unittest.TestCase):
    def poprawna(self, **zmiany) -> dict:
        r = {"czujnik": "a", "nazwa": "Fikus", "gatunek": "fikus", "sucho": 10,
             "kody": dict(KODY_ROSLINY)}
        r.update(zmiany)
        return r

    def wczytaj(self, *wpisy) -> list[dict]:
        return rosliny.wczytaj_konfiguracje(json.dumps({"rosliny": list(wpisy)}))

    def test_poprawny_wpis(self):
        k = self.wczytaj(self.poprawna())
        self.assertEqual(k[0]["kody"]["gleba"], "humidity")
        self.assertEqual(k[0]["sucho"], 10.0)

    def test_bledy_maja_polski_opis(self):
        przypadki = {
            "nieznany gatunek": self.poprawna(gatunek="kaktus"),
            "brak „kody\"": self.poprawna(kody={"temp": "temp_current"}),
            "nieznane rodzaje": self.poprawna(kody={**KODY_ROSLINY, "co2": "x"}),
            "jeden kod chmury": self.poprawna(kody={"gleba": "humidity", "wilg": "humidity"}),
            "„sucho\" musi": self.poprawna(sucho="mokro"),
            "„od\" to nie data": self.poprawna(od="wczoraj"),
        }
        for oczekiwane, wpis in przypadki.items():
            with self.subTest(oczekiwane), self.assertRaisesRegex(ValueError, oczekiwane):
                self.wczytaj(wpis)

    def test_zly_json_i_dwa_razy_ten_sam_czujnik(self):
        with self.assertRaisesRegex(ValueError, "poprawny JSON"):
            rosliny.wczytaj_konfiguracje("{to nie json")
        with self.assertRaisesRegex(ValueError, "dwa razy"):
            self.wczytaj(self.poprawna(), self.poprawna(nazwa="Drugi"))

    def test_prawdziwy_plik_jest_poprawny(self):
        """Strażnik: ręczny rosliny.json w repozytorium musi się wczytać — lekcja
        z artefakty.json, gdzie zły cudzysłów po cichu wyłączył całą listę."""
        k = rosliny.wczytaj_konfiguracje((REPO / "rosliny.json").read_text(encoding="utf-8"))
        self.assertEqual({r["gatunek"] for r in k}, {"fikus", "skrzydlokwiat", "azalia"})


class TestPrzerzedzanie(unittest.TestCase):
    def test_zostaja_zmiany_i_jeden_wiersz_na_godzine(self):
        t0 = ms("2026-10-08T10:00:00Z")
        stale = [wiersz(t0 + k * 30_000, "humidity", 10) for k in range(240)]       # 2 godz. co 30 s
        zmiana = [wiersz(t0 + 7_200_000 + 30_000, "humidity", 12)]
        wynik = rosliny.zwin(stale + zmiana)
        self.assertEqual([w["value"] for w in wynik], ["10", "10", "12"])
        self.assertEqual(wynik[1]["ts"], rosliny.iso(t0 + 3_600_000))

    def test_idempotentne_i_rozdzielne_miedzy_seriami(self):
        t0 = ms("2026-10-08T10:00:00Z")
        dane = [wiersz(t0 + k * 30_000, "humidity", 10 + (k // 50)) for k in range(400)]
        dane += [wiersz(t0 + k * 30_000, "temp_current", 22.5) for k in range(400)]
        raz = rosliny.zwin(dane)
        self.assertEqual(rosliny.zwin(raz), raz)
        self.assertEqual({w["code"] for w in raz}, {"humidity", "temp_current"})
        self.assertLess(len(raz), 30)


class TestSwiatlo(unittest.TestCase):
    def test_stala_wartosc_daje_iloczyn_i_pokrycie(self):
        poczatek = ms("2026-10-08T08:00:00Z")          # 10:00 w Warszawie
        pkt = [(poczatek + k * GODZ, 600.0) for k in range(5)]
        doby = rosliny.luksogodziny(pkt, WAWA, ms("2026-10-07T22:00:00Z"), ms("2026-10-08T21:59:59Z"))
        doba = {d["data"]: d for d in doby}["2026-10-08"]
        # 5 punktów co godzinę, ostatni trzymany 2 godz.: 6 godz. po 600 lx
        self.assertEqual(doba["lxh"], 3600)
        self.assertAlmostEqual(doba["pokrycie"], 6 / 24, places=2)

    def test_dluga_przerwa_to_brak_pomiaru_a_nie_ciemnosc_ani_swiatlo(self):
        pkt = [(ms("2026-10-08T08:00:00Z"), 1000.0), (ms("2026-10-08T14:00:00Z"), 0.0)]
        doby = rosliny.luksogodziny(pkt, WAWA, ms("2026-10-07T22:00:00Z"), ms("2026-10-08T21:59:59Z"))
        doba = {d["data"]: d for d in doby}["2026-10-08"]
        self.assertEqual(doba["lxh"], 2000, "1000 lx przeciągnięte dalej niż 2 godz.")

    def test_doba_dzieli_sie_o_lokalnej_polnocy(self):
        # 23:00–01:00 czasu warszawskiego po 100 lx: po godzinie w każdej dobie
        pkt = [(ms("2026-10-07T21:00:00Z"), 100.0), (ms("2026-10-07T23:00:00Z"), 0.0)]
        doby = {d["data"]: d["lxh"] for d in
                rosliny.luksogodziny(pkt, WAWA, ms("2026-10-07T00:00:00Z"), ms("2026-10-08T20:00:00Z"))}
        self.assertEqual(doby["2026-10-07"], 100)
        self.assertEqual(doby["2026-10-08"], 100)


class TestPodlania(unittest.TestCase):
    def gleba(self) -> list[tuple[int, float]]:
        t0 = ms("2026-10-08T00:00:00Z")
        pkt = [(t0 + k * 30 * 60_000, 30.0 - k * 0.2) for k in range(48)]   # schnie przez dobę
        podlanie = t0 + 24 * GODZ
        pkt += [(podlanie + k * 30 * 60_000, 60.0 if k < 4 else 55.0) for k in range(20)]
        return pkt

    def test_skok_to_podlanie_ze_szczytem_po_odcieknieciu(self):
        p = rosliny.podlania(self.gleba())
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["ts"], "2026-10-09T00:00:00Z")
        self.assertAlmostEqual(p[0]["przed"], 20.6, places=1)
        self.assertEqual(p[0]["szczyt"], 55.0, "szczyt to mediana 2–6 godz. po podlaniu")

    def test_powolne_wilgotnienie_to_nie_podlanie(self):
        t0 = ms("2026-10-08T00:00:00Z")
        pkt = [(t0 + k * GODZ, 20.0 + k) for k in range(30)]      # +1 pkt na godzinę
        self.assertEqual(rosliny.podlania(pkt), [])

    def test_nauka_i_prog_przyciety_do_granic(self):
        podl = [{"przed": 12.0, "szczyt": 50.0}, {"przed": 13.0, "szczyt": 52.0},
                {"przed": 11.0, "szczyt": 51.0}]
        n = rosliny.nauka(podl, 10.0)
        self.assertEqual(n["szczyt"], 51.0)
        self.assertEqual(n["punkt_podlewania"], 12.0)
        # nawyk „podlewam dopiero, gdy zupełnie suche" — próg nie spada poniżej granicy
        self.assertEqual(rosliny.prog_rosliny("fikus", 10, 10.0, 51.0, 12.0), 0.20)
        # bez trzech podlań — próg zimowy z literatury
        self.assertEqual(rosliny.prog_rosliny("fikus", 11, 10.0, 51.0, None), 0.35)


class TestWerdykt(unittest.TestCase):
    TERAZ = ms("2026-10-12T12:00:00Z")

    def wiersze(self, gleba_teraz: float, podlanie: bool = True, ostatni_ms: int | None = None) -> list[dict]:
        t0 = ms("2026-10-09T00:00:00Z")
        out = [wiersz(t0 + k * GODZ, "humidity", 15) for k in range(4)]
        if podlanie:
            out += [wiersz(t0 + (4 + k) * GODZ, "humidity", 50) for k in range(8)]
        out.append(wiersz(ostatni_ms or self.TERAZ - GODZ, "humidity", gleba_teraz))
        out.append(wiersz(self.TERAZ - GODZ, "battery_state", "high"))
        return out

    def werdykt(self, k: dict, wiersze: list[dict]) -> dict:
        return rosliny.stan_rosliny(k, wiersze, self.TERAZ, WAWA)

    def test_bez_daty_wbicia_tylko_nauka(self):
        s = self.werdykt(konf(), self.wiersze(12))
        self.assertEqual(s["werdykt"], "nauka")
        self.assertEqual(s["podlania"], [], "odczyty sprzed wbicia sondy nie uczą")

    def test_po_podlaniu_skala_i_podlej(self):
        k = konf(od="2026-10-08T00:00:00Z")
        s = self.werdykt(k, self.wiersze(20))           # R = (20−10)/(50−10) = 0,25
        self.assertEqual(s["szczyt"], 50.0)
        self.assertEqual(s["R"], 0.25)
        self.assertEqual(s["werdykt"], "podlej")
        self.assertEqual(self.werdykt(k, self.wiersze(40))["werdykt"], "ok")

    def test_azalia_ponizej_pilnego(self):
        k = konf(gatunek="azalia", od="2026-10-08T00:00:00Z")
        self.assertEqual(self.werdykt(k, self.wiersze(30))["werdykt"], "pilne")   # R = 0,5

    def test_cisza_to_czujnik(self):
        k = konf(od="2026-10-08T00:00:00Z")
        w = [x for x in self.wiersze(40, ostatni_ms=self.TERAZ - 20 * GODZ) if x["code"] != "battery_state"]
        s = self.werdykt(k, w)
        self.assertEqual(s["werdykt"], "czujnik")
        self.assertIn("milczy", " ".join(s["uwagi"]))

    def test_szereg_i_swiatlo_maja_dlugosc_historii(self):
        s = self.werdykt(konf(), self.wiersze(20))
        self.assertEqual(len(s["swiatlo_dobowe"]), 31)
        self.assertEqual(len(s["szereg"]["gleba"]), 30 * 24 + 1)


class TorRoslin(PrzebiegKolektora):
    """Kolektor z pokojem i dwiema roślinami: jedną z listy, jedną tylko z kategorii.

    Ścieżki wpisane wprost, nie przez stałe z fetch.py: na wersji sprzed toru roślin
    test ma polec na zachowaniu (rośliny w pokojach, brak stanu), a nie na AttributeError.
    """

    URZADZENIA = ("salon",)
    KATALOG = Path("data") / "rosliny"
    STAN = KATALOG / "stan.json"
    SPEC_ROSLINY = {"status": [
        {"code": "humidity", "type": "Integer", "values": '{"unit":"%","min":0,"max":100,"scale":0}'},
        {"code": "temp_current", "type": "Integer", "values": '{"unit":"℃","min":0,"max":1000,"scale":1}'},
        {"code": "env_humidity", "type": "Integer", "values": '{"unit":"%","min":0,"max":100,"scale":0}'},
        {"code": "illumiance", "type": "Integer", "values": '{"min":0,"max":10000,"scale":0}'},
        {"code": "battery_state", "type": "Enum", "values": '{"range":["low","middle","high"]}'},
        {"code": "water_warning", "type": "Boolean", "values": "{}"},
    ]}

    def doniczka(self) -> list[dict]:
        """Jak prawdziwy czujnik 8.10: gleba co 30 s ze stałą wartością, reszta rzadko."""
        out, t = [], self.teraz - 3 * GODZ
        while t < self.teraz - 60_000:
            out.append({"code": "humidity", "value": 10, "event_time": t})
            t += 30_000
        for k in range(3):
            t = self.teraz - (3 - k) * GODZ + 5_000
            out += [{"code": "temp_current", "value": 225, "event_time": t},
                    {"code": "env_humidity", "value": 52, "event_time": t},
                    {"code": "illumiance", "value": 120, "event_time": t},
                    {"code": "battery_state", "value": "high", "event_time": t},
                    {"code": "water_warning", "value": True, "event_time": t}]
        return out

    def napisz_rosliny(self, tekst: str | None = None):
        tresc = tekst if tekst is not None else json.dumps({"rosliny": [
            {"czujnik": "fikus", "nazwa": "Fikus", "gatunek": "fikus", "sucho": 10, "kody": KODY_ROSLINY}]})
        (self.katalog / "rosliny.json").write_text(tresc, encoding="utf-8")

    def atrapa(self, **kw) -> AtrapaTuya:
        logi = {"salon": tydzien_odczytow(self.teraz), "fikus": self.doniczka(),
                "obca": self.doniczka()}
        return AtrapaTuya(logi, kategorie={"fikus": "zwjcy", "obca": "zwjcy"},
                          specyfikacje={"fikus": self.SPEC_ROSLINY, "obca": self.SPEC_ROSLINY}, **kw)

    def _przebieg(self, atrapa: AtrapaTuya, lista: str) -> str:
        """main() z własną listą TUYA_DEVICE_IDS — pusta to najgorszy przypadek, w którym
        kolektor bierze całe konto."""
        srodowisko = {"TUYA_CLIENT_ID": "x", "TUYA_CLIENT_SECRET": "y", "TUYA_DEVICE_IDS": lista,
                      "TUYA_SINCE": "", "TZ_LOCAL": "Europe/Warsaw"}
        wyjscie = io.StringIO()
        with mock.patch.dict(os.environ, srodowisko), \
                mock.patch.object(fetch, "Tuya", lambda *a, **k: atrapa), \
                mock.patch.object(fetch, "fetch_outdoor", return_value=([], None)), \
                mock.patch.object(fetch, "fetch_weather", return_value=None), \
                mock.patch.object(sys, "argv", ["fetch.py"]), \
                mock.patch.object(fetch, "ROSLINY_PLIK", self.katalog / "rosliny.json", create=True), \
                redirect_stdout(wyjscie):
            self.kod = fetch.main()
        return wyjscie.getvalue()

    def csv_pokoi(self) -> set[str]:
        out = set()
        for plik in fetch.DATA_DIR.glob("[0-9]*.csv"):
            with plik.open(encoding="utf-8") as f:
                out |= {r["device_id"] for r in csv.DictReader(f)}
        return out

    def csv_roslin(self) -> list[dict]:
        out = []
        for plik in self.KATALOG.glob("[0-9]*.csv"):
            with plik.open(encoding="utf-8") as f:
                out += list(csv.DictReader(f))
        return out

    def stan(self) -> dict:
        if not self.STAN.exists():
            return {"blad": "", "rosliny": [], "urzadzenia": {}}
        return json.loads(self.STAN.read_text(encoding="utf-8"))


class TestTorRoslin(TorRoslin):

    def test_rosliny_nie_trafiaja_do_pokoi_nawet_przy_pustej_liscie_urzadzen(self):
        self.napisz_rosliny()
        self._przebieg(self.atrapa(), "")
        self.assertEqual(self.kod, 0)
        manifest = json.loads(fetch.MANIFEST.read_text(encoding="utf-8"))["devices"]
        self.assertNotIn("fikus", manifest)
        self.assertNotIn("obca", manifest, "czujnik zwjcy spoza rosliny.json wszedł jako pokój")
        self.assertEqual(self.csv_pokoi(), {"salon"})
        self.assertEqual({r["device_id"] for r in self.csv_roslin()}, {"fikus"})

    def test_stan_i_przerzedzone_csv(self):
        self.napisz_rosliny()
        self._przebieg(self.atrapa(), "salon")
        stan = self.stan()
        self.assertTrue(stan["rosliny"], "brak stanu roślin")
        self.assertIsNone(stan["blad"])
        fikus = stan["rosliny"][0]
        self.assertEqual(fikus["ostatnie"]["gleba"]["v"], 10.0)
        self.assertEqual(fikus["ostatnie"]["temp"]["v"], 22.5)
        self.assertEqual(fikus["ostatnie"]["swiatlo"]["v"], 120.0)
        self.assertEqual(fikus["ostatnie"]["alarm"]["v"], "1")
        self.assertEqual(fikus["werdykt"], "nauka")
        gleba = [r for r in self.csv_roslin() if r["code"] == "humidity"]
        self.assertLessEqual(len(gleba), 4, "ok. 360 stałych odczytów gleby powinno się zwinąć do kilku")
        self.assertIn("pobrane_do", stan["urzadzenia"]["fikus"])

    def test_drugi_przebieg_bez_specyfikacji_i_z_krotka_zakladka(self):
        self.napisz_rosliny()
        atrapa = self.atrapa()
        self._przebieg(atrapa, "salon")
        przed = len(atrapa.zapytania)
        self._przebieg(atrapa, "salon")
        drugie = atrapa.zapytania[przed:]
        self.assertFalse([p for p, _ in drugie if p == "/v1.0/devices/fikus/specifications"],
                         "skale roślin mają być zapamiętane w stan.json")
        logi = [prm for p, prm in drugie if p == "/v1.0/devices/fikus/logs"]
        self.assertTrue(logi, "drugi przebieg nie pobrał logów doniczki")
        self.assertGreaterEqual(int(logi[0]["start_time"]), self.teraz - int(1.5 * GODZ))

    def test_zepsuty_rosliny_json_nie_zatrzymuje_pokoi(self):
        self.napisz_rosliny("{zepsuty")
        self._przebieg(self.atrapa(), "salon")
        self.assertEqual(self.kod, 0)
        self.assertEqual(self.csv_pokoi(), {"salon"})
        self.assertIn("JSON", self.stan()["blad"] or "")

    def test_wyjatek_w_obliczeniach_nie_zatrzymuje_pokoi(self):
        self.napisz_rosliny()
        with mock.patch.object(rosliny, "stan_rosliny", side_effect=ZeroDivisionError("atrapa")):
            wyjscie = self._przebieg(self.atrapa(), "salon")
        self.assertEqual(self.kod, 0)
        self.assertEqual(self.csv_pokoi(), {"salon"})
        self.assertIn("ZeroDivisionError", self.stan()["blad"] or "")
        self.assertIn("błąd toru", wyjscie)

    def test_odmowa_tuya_dla_doniczki_zapisuje_blad_a_pokoje_ida_dalej(self):
        self.napisz_rosliny()
        atrapa = self.atrapa(odmowa=lambda path, params: path == "/v1.0/devices/fikus/logs")
        self._przebieg(atrapa, "salon")
        self.assertEqual(self.kod, 0)
        self.assertEqual(self.csv_pokoi(), {"salon"})
        self.assertIn("Fikus", self.stan()["blad"] or "")

    def test_brak_pola_w_specyfikacji_to_czytelny_blad(self):
        # tak było 8.10 przed przełączeniem na DP Instruction: chmura nie znała światła
        self.napisz_rosliny()
        atrapa = self.atrapa()
        atrapa.specyfikacje["fikus"] = {"status": [s for s in self.SPEC_ROSLINY["status"]
                                                  if s["code"] not in ("illumiance", "env_humidity")]}
        self._przebieg(atrapa, "salon")
        self.assertEqual(self.kod, 0)
        self.assertIn("DP Instruction", self.stan()["blad"] or "")

    def test_bez_rosliny_json_nic_nie_powstaje(self):
        """Strażnik: dopóki nie ma konfiguracji, tor roślin nie dotyka data/."""
        self._przebieg(self.atrapa(), "salon")
        self.assertFalse(self.KATALOG.exists())


if __name__ == "__main__":
    unittest.main()
