#!/usr/bin/env python3
"""Pobieranie przyrostowe — testy na atrapie chmury Tuya.

Do 8.10.2026 każdy przebieg ciągnął pełne 7 dni logów: 29 zapytań, ok. 47% miesięcznego
pakietu triala, a czujniki w doniczkach dołożyłyby kilkakrotność tego. Teraz kolektor
pamięta w manifeście, do kiedy pobrał wszystko (`pobrane_do`), i pyta tylko o odcinek
od tej chwili, z zakładką na spóźnione odczyty.

Atrapa udaje dokładnie to, z czego korzysta kolektor: listę urządzeń i logi v1 ze
stronicowaniem `start_row_key` / `next_row_key`, w kolejności rosnącej albo malejącej —
prawdziwej kolejności Tuya nie dokumentuje, więc testy sprawdzają obie. Endpoint v2
odmawia, tak jak (najpewniej) robi to dziś, bo kolektor nie wysyła parametru `codes`.

Testy uruchamiają całe main() w katalogu tymczasowym, a nie pojedyncze funkcje:
przedmiotem testu jest to, ile zapytań idzie do Tuya i co zostaje w CSV i manifeście.
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import fetch  # noqa: E402
import requests  # noqa: E402

GODZ = 3600 * 1000
DOBA = 24 * GODZ
KODY = {"va_temperature": {"kind": "temp", "unit": "℃", "scale": 1},
        "va_humidity": {"kind": "hum", "unit": "%", "scale": 0}}


class AtrapaTuya:
    """Chmura Tuya w pamięci: lista urządzeń i logi v1. v2 odmawia."""

    def __init__(self, logi: dict[str, list[dict]], kolejnosc: str = "rosnaco", odmowa=None,
                 granica_stron: int | None = None, start_otwarty: bool = False,
                 v2_pusto: bool = False, awaria=None, kategorie: dict | None = None,
                 specyfikacje: dict | None = None):
        self.logi = logi
        # kategoria Tuya urządzenia (domyślnie czujnik pokojowy) i specyfikacje do toru roślin
        self.kategorie = kategorie or {}
        self.specyfikacje = specyfikacje or {}
        self.kolejnosc = kolejnosc
        self.odmowa = odmowa or (lambda path, params: False)
        # strona nigdy nie przechodzi przez tę chwilę — krótsza strona z has_next,
        # jak u Tuya przy przejściu przez dobę (tak pisze się pętlę w tinytuya)
        self.granica_stron = granica_stron
        # start_time bez równości: nikt nie sprawdził, jak jest naprawdę
        self.start_otwarty = start_otwarty
        # v2 odpowiada „sukces, zero wpisów" zamiast odmowy
        self.v2_pusto = v2_pusto
        # wywoływane przed każdym zapytaniem; może rzucić wyjątkiem sieci
        self.awaria = awaria or (lambda path, params, n: None)
        self.zapytan = 0
        self.log_api = None
        self.zapytania: list[tuple[str, dict]] = []

    def get(self, path: str, params: dict | None = None) -> dict:
        params = dict(params or {})
        self.zapytan += 1
        self.zapytania.append((path, params))
        self.awaria(path, params, self.zapytan)
        if self.odmowa(path, params):
            return {"success": False, "code": 500, "msg": "atrapa: odmowa"}
        if path == "/v1.0/iot-01/associated-users/devices":
            urzadzenia = [{"id": i, "name": i.capitalize(), "category": self.kategorie.get(i, "wsdcg")}
                          for i in self.logi]
            return {"success": True, "result": {"devices": urzadzenia, "has_more": False}}
        if path.endswith("/specifications") and path.split("/")[3] in self.specyfikacje:
            return {"success": True, "result": self.specyfikacje[path.split("/")[3]]}
        if path.startswith("/v2.0/"):
            if self.v2_pusto:
                return {"success": True, "result": {"logs": [], "has_more": False}}
            return {"success": False, "code": 1108, "msg": "uri path invalid"}
        if path.startswith("/v1.0/devices/") and path.endswith("/logs"):
            ident = path.split("/")[3]
            od, do = int(params["start_time"]), int(params["end_time"])
            wybrane = [w for w in self.logi.get(ident, [])
                       if (od < w["event_time"] if self.start_otwarty else od <= w["event_time"])
                       and w["event_time"] <= do]
            wybrane.sort(key=lambda w: w["event_time"], reverse=self.kolejnosc == "malejaco")
            poz = int(params.get("start_row_key") or 0)
            rozmiar = int(params["size"])
            strona = wybrane[poz:poz + rozmiar]
            if self.granica_stron is not None and strona:
                po_tej_stronie = strona[0]["event_time"] >= self.granica_stron
                strona = [w for w in strona if (w["event_time"] >= self.granica_stron) == po_tej_stronie]
            dalej = poz + len(strona) < len(wybrane)
            return {"success": True, "result": {
                "logs": [dict(w) for w in strona],
                "has_next": dalej,
                "next_row_key": str(poz + len(strona)) if dalej else None,
            }}
        return {"success": False, "code": 404, "msg": f"atrapa nie zna {path}"}

    def zapytania_o_logi(self, od: int = 0) -> list[dict]:
        return [p for path, p in self.zapytania[od:] if path.endswith("/logs")]


def tydzien_odczytow(teraz: int, co_ile_min: int = 60, dni: float = 7,
                     bateria: bool = False) -> list[dict]:
    """Czujnik pokojowy: temperatura i wilgotność co godzinę, jak prawdziwe. Z `bateria`
    każdy raport to trójka, jak u prawdziwych czujników — strona po 100 wpisów kończy
    się wtedy w środku trójki."""
    out = []
    t = teraz - int(dni * DOBA) + 60_000
    while t <= teraz - 60_000:
        out.append({"code": "va_temperature", "value": "215", "event_time": t})
        out.append({"code": "va_humidity", "value": "55", "event_time": t})
        if bateria:
            out.append({"code": "battery_state", "value": "high", "event_time": t})
        t += co_ile_min * 60_000
    return out


class PrzebiegKolektora(unittest.TestCase):
    """main() w świeżym katalogu, z atrapą zamiast Tuya i bez pogody."""

    URZADZENIA = ("salon", "kuchnia")

    def setUp(self):
        self.katalog = Path(tempfile.mkdtemp())
        self.poprzedni = Path.cwd()
        os.chdir(self.katalog)
        (self.katalog / "data").mkdir()
        # Kody już znane z poprzedniego przebiegu — bez tego kolektor pytałby atrapę
        # o specyfikację, a to nie jest przedmiotem tych testów.
        fetch.MANIFEST.write_text(json.dumps({"devices": {
            i: {"name": i.capitalize(), "codes": KODY} for i in self.URZADZENIA
        }}), encoding="utf-8")
        self.teraz = int(time.time() * 1000)

    def tearDown(self):
        os.chdir(self.poprzedni)
        shutil.rmtree(self.katalog, ignore_errors=True)

    def przebieg(self, atrapa: AtrapaTuya, **stale) -> str:
        srodowisko = {"TUYA_CLIENT_ID": "x", "TUYA_CLIENT_SECRET": "y",
                      "TUYA_DEVICE_IDS": ",".join(atrapa.logi), "TUYA_SINCE": "",
                      "TZ_LOCAL": "Europe/Warsaw"}
        wyjscie = io.StringIO()
        latki = [
            mock.patch.dict(os.environ, srodowisko),
            mock.patch.object(fetch, "Tuya", lambda *a, **k: atrapa),
            mock.patch.object(fetch, "fetch_outdoor", return_value=([], None)),
            mock.patch.object(fetch, "fetch_weather", return_value=None),
            mock.patch.object(sys, "argv", ["fetch.py"]),
            # bez prawdziwego rosliny.json: tor roślin rusza tylko w testach, które go piszą
            mock.patch.object(fetch, "ROSLINY_PLIK", self.katalog / "rosliny.json", create=True),
        ]
        # create=True: na wersji sprzed zmiany tych stałych nie ma, a test ma wtedy
        # polec na zachowaniu, nie na AttributeError przy łatce
        latki += [mock.patch.object(fetch, k, v, create=True) for k, v in stale.items()]
        for latka in latki:
            latka.start()
        try:
            with redirect_stdout(wyjscie):
                self.assertEqual(fetch.main(), 0)
        finally:
            for latka in reversed(latki):
                latka.stop()
        return wyjscie.getvalue()

    def w_csv(self, urzadzenie: str) -> set[tuple[str, str]]:
        out = set()
        for plik in fetch.DATA_DIR.glob("[0-9]*.csv"):
            with plik.open(encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if r["device_id"] == urzadzenie:
                        out.add((r["ts"], r["code"]))
        return out

    def oczekiwane(self, logi: list[dict]) -> set[tuple[str, str]]:
        """Kolektor zapisuje tylko kody z manifestu — bateria w atrapie zajmuje miejsce
        na stronach, ale do CSV nie trafia."""
        return {(fetch.iso(w["event_time"]), w["code"]) for w in logi if w["code"] in KODY}

    def kursor(self, urzadzenie: str) -> str | None:
        return json.loads(fetch.MANIFEST.read_text(encoding="utf-8"))["devices"][urzadzenie].get("pobrane_do")

    def do_skutku(self, atrapa: "AtrapaTuya", urzadzenie: str, przebiegow: int = 15) -> list:
        kursory = []
        for _ in range(przebiegow):
            self.przebieg(atrapa)
            kursory.append(self.kursor(urzadzenie))
            if self.w_csv(urzadzenie) == self.oczekiwane(atrapa.logi[urzadzenie]):
                break
        brak = self.oczekiwane(atrapa.logi[urzadzenie]) - self.w_csv(urzadzenie)
        self.assertFalse(brak, f"po {len(kursory)} przebiegach brakuje {len(brak)} wpisów, "
                               f"np. {sorted(brak)[:3]}; kursory: {kursory}")
        self.assertEqual(kursory, sorted(kursory), "kursor cofnął się")
        return kursory


class TestPobieraniePrzyrostowe(PrzebiegKolektora):

    def atrapa(self, **kw) -> AtrapaTuya:
        return AtrapaTuya({i: tydzien_odczytow(self.teraz) for i in self.URZADZENIA}, **kw)

    def test_drugi_przebieg_pyta_tylko_o_ostatnie_godziny(self):
        atrapa = self.atrapa()
        self.przebieg(atrapa)
        przed = len(atrapa.zapytania)
        self.przebieg(atrapa)
        drugie = atrapa.zapytania_o_logi(przed)
        self.assertTrue(drugie)
        najdalej = self.teraz - int(6.5 * GODZ)
        for p in drugie:
            self.assertGreaterEqual(int(p["start_time"]), najdalej,
                                    "drugi przebieg znów sięga dalej niż zakładka — pełne okno 7 dni")

    def test_drugi_przebieg_to_jedna_strona_logow_na_czujnik(self):
        """Pełny tydzień czujnika to ok. 340 wpisów, czyli 4 strony; zakładka to jedna."""
        atrapa = self.atrapa()
        self.przebieg(atrapa)
        przed = len(atrapa.zapytania)
        self.przebieg(atrapa)
        self.assertEqual(len(atrapa.zapytania_o_logi(przed)), len(self.URZADZENIA))

    def test_bez_proby_v2_gdy_v1_dziala(self):
        atrapa = self.atrapa()
        self.przebieg(atrapa)
        v2 = [path for path, _ in atrapa.zapytania if path.startswith("/v2.0/")]
        self.assertEqual(v2, [], "każda próba v2 to zapytanie zjadające limit, w każdym przebiegu")

    def test_pierwszy_przebieg_bez_kursora_bierze_pelne_okno(self):
        """Strażnik: bez kursora w manifeście zachowanie jak dawniej — pełne 7 dni.
        Przechodzi także na wersji sprzed zmiany i tak ma być."""
        atrapa = self.atrapa()
        self.przebieg(atrapa)
        for i in self.URZADZENIA:
            self.assertEqual(self.w_csv(i), self.oczekiwane(atrapa.logi[i]))

    def test_nieudany_przebieg_nie_gubi_kursora(self):
        atrapa = self.atrapa()
        self.przebieg(atrapa)
        # drugi przebieg: Tuya odmawia logów salonu w całości
        atrapa.odmowa = lambda path, params: path == "/v1.0/devices/salon/logs"
        wyjscie = self.przebieg(atrapa)
        self.assertIn("Salon: pominięty", wyjscie)
        # trzeci: wszystko działa i salon zaczyna od miejsca sprzed awarii, nie od 7 dni
        atrapa.odmowa = lambda path, params: False
        przed = len(atrapa.zapytania)
        self.przebieg(atrapa)
        salon = [p for path, p in atrapa.zapytania[przed:] if path == "/v1.0/devices/salon/logs"]
        self.assertTrue(salon)
        self.assertGreaterEqual(int(salon[0]["start_time"]), self.teraz - int(6.5 * GODZ))

    def test_spozniony_odczyt_z_zakladki_trafia_do_csv(self):
        """Strażnik: zakładka nie może zgubić odczytu, który dotarł do chmury po
        poprzednim przebiegu. Przechodzi też na wersji z pełnym oknem — i ma."""
        atrapa = self.atrapa()
        self.przebieg(atrapa)
        spozniony = {"code": "va_temperature", "value": "222", "event_time": self.teraz - 2 * GODZ + 7}
        atrapa.logi["salon"].append(spozniony)
        self.przebieg(atrapa)
        self.assertIn((fetch.iso(spozniony["event_time"]), "va_temperature"), self.w_csv("salon"))

    def test_przebieg_wypisuje_liczbe_zapytan(self):
        atrapa = self.atrapa()
        wyjscie = self.przebieg(atrapa)
        self.assertIn(f"Zapytań do Tuya w tym przebiegu: {atrapa.zapytan}", wyjscie)


class TestZalewLogow(PrzebiegKolektora):
    """Czujnik, który zalewa logi (model C3007 według Zigbee2MQTT: ok. 1 wpis na sekundę).

    Kolektor ma wtedy: nie przekraczać budżetu zapytań w jednym przebiegu, przesuwać
    kursor w każdym przebiegu i po kilku przebiegach mieć w CSV wszystko — w obu
    kolejnościach, w jakich Tuya może oddawać strony.
    """

    URZADZENIA = ("salon",)
    BUDZET = 8

    def zalew(self) -> list[dict]:
        logi = tydzien_odczytow(self.teraz)
        t = self.teraz - 3 * GODZ
        while t < self.teraz - 60_000:
            logi.append({"code": "va_temperature", "value": "230", "event_time": t})
            t += 10_000
        return logi

    def sprawdz(self, kolejnosc: str):
        atrapa = AtrapaTuya({"salon": self.zalew()}, kolejnosc=kolejnosc)
        kursory = []
        for _ in range(30):
            przed = atrapa.zapytan
            self.przebieg(atrapa, BUDZET_URZADZENIA=self.BUDZET)
            zuzyte = atrapa.zapytan - przed
            # lista urządzeń + budżet czujnika
            self.assertLessEqual(zuzyte, 1 + self.BUDZET,
                                 "jeden zalany czujnik zjada limit całego przebiegu")
            stan = json.loads(fetch.MANIFEST.read_text(encoding="utf-8"))["devices"]["salon"]
            kursory.append(stan.get("pobrane_do"))
            if self.w_csv("salon") == self.oczekiwane(atrapa.logi["salon"]):
                break
        self.assertEqual(self.w_csv("salon"), self.oczekiwane(atrapa.logi["salon"]),
                         f"po {len(kursory)} przebiegach nadal brakuje wpisów; kursory: {kursory}")
        self.assertEqual(kursory, sorted(kursory), "kursor cofnął się")

    def test_kolejnosc_rosnaca(self):
        self.sprawdz("rosnaco")

    def test_log_mowi_jak_gesto(self):
        """Gęstość zalewu z tego, co i tak przyszło: 100 wpisów co 10 s to 990 s na stronę.
        8.10 tylko z niej dało się wyczytać, że godzina parowania nie miała 134 wpisów."""
        wyjscie = self.przebieg(AtrapaTuya({"salon": self.zalew()}, kolejnosc="malejaco"),
                                BUDZET_URZADZENIA=self.BUDZET)
        self.assertRegex(wyjscie, r"salon: najgęstsza pełna strona — 100 wpisów w 990 s .*va_temperature 100")

    def test_kolejnosc_malejaca(self):
        self.sprawdz("malejaco")


class TestPrzypadkiZPrzegladu(PrzebiegKolektora):
    """Sytuacje znalezione w przeglądzie przed wdrożeniem 8.10. Każda gubiła wpisy
    na pierwszej wersji pobierania przyrostowego, a Tuya trzyma logi tylko 7 dni."""

    URZADZENIA = ("salon",)

    def test_krotka_strona_z_jedna_chwila_przy_kolejnosci_od_najnowszego(self):
        # Ostatni raport przed „teraz" jest za granicą stron, więc pierwsza strona to
        # jedna para z jednej chwili i has_next. Dawniej czytane jako „rosnąco"
        # i kursor przeskakiwał cały tydzień.
        atrapa = AtrapaTuya({"salon": tydzien_odczytow(self.teraz)}, kolejnosc="malejaco",
                            granica_stron=self.teraz - 90 * 60_000)
        self.do_skutku(atrapa, "salon")

    def test_otwarty_start_time_nie_gubi_reszty_trojki(self):
        atrapa = AtrapaTuya({"salon": tydzien_odczytow(self.teraz, bateria=True)},
                            start_otwarty=True)
        self.do_skutku(atrapa, "salon")

    def test_po_dlugiej_przerwie_zakladka_nadal_lapie_spoznione(self):
        atrapa = AtrapaTuya({"salon": tydzien_odczytow(self.teraz, co_ile_min=10)},
                            kolejnosc="malejaco")
        self.przebieg(atrapa)
        # udajemy, że ostatni udany przebieg był 30 godz. temu, a w zakładce przed nim
        # dociera do chmury odczyt, którego wtedy jeszcze nie było
        m = json.loads(fetch.MANIFEST.read_text(encoding="utf-8"))
        m["devices"]["salon"]["pobrane_do"] = fetch.iso(self.teraz - 30 * GODZ)
        fetch.MANIFEST.write_text(json.dumps(m), encoding="utf-8")
        spozniony = {"code": "va_temperature", "value": "199", "event_time": self.teraz - 33 * GODZ + 7}
        atrapa.logi["salon"].append(spozniony)
        self.przebieg(atrapa)
        self.assertIn((fetch.iso(spozniony["event_time"]), "va_temperature"), self.w_csv("salon"))

    def test_zerwana_siec_w_polowie_nie_wyrzuca_tego_co_przyszlo(self):
        def awaria(path, params, n):
            if path.endswith("/logs") and params.get("start_time") and n > 3:
                raise requests.ConnectionError("atrapa: sieć")
        atrapa = AtrapaTuya({"salon": tydzien_odczytow(self.teraz, co_ile_min=20)}, awaria=awaria)
        self.przebieg(atrapa)
        self.assertGreaterEqual(len(self.w_csv("salon")), 100, "przebieg wyrzucił pobrane strony")
        self.assertIsNotNone(self.kursor("salon"), "kursor nie zapamiętał postępu")
        atrapa.awaria = lambda path, params, n: None
        self.do_skutku(atrapa, "salon")

    def test_puste_v2_nie_przesuwa_kursora(self):
        # v1 odmawia raz, na samym początku; v2 odpowiada „sukces, zero wpisów".
        # Dawniej v2 zostawało na cały przebieg, a kursor skakał na „teraz".
        stan = {"odmowa": True}
        def odmowa(path, params):
            if path.startswith("/v1.0/devices/") and stan["odmowa"]:
                stan["odmowa"] = False
                return True
            return False
        atrapa = AtrapaTuya({"salon": tydzien_odczytow(self.teraz)}, odmowa=odmowa, v2_pusto=True)
        self.przebieg(atrapa)
        self.do_skutku(atrapa, "salon")

    def test_ponad_sto_wpisow_w_dwie_minuty_od_najnowszego(self):
        logi = tydzien_odczytow(self.teraz)
        t = self.teraz - 40 * 60_000
        while t < self.teraz - 30 * 60_000:
            logi.append({"code": "va_temperature", "value": "230", "event_time": t})
            t += 500
        atrapa = AtrapaTuya({"salon": logi}, kolejnosc="malejaco")
        self.do_skutku(atrapa, "salon", przebiegow=25)


class AtrapaZeSpecyfikacja(AtrapaTuya):
    """Do --discover: lista urządzeń z kategorią i stanem oraz specyfikacje."""

    SPEC = {
        "salon": {"status": [
            {"code": "va_temperature", "type": "Integer", "values": '{"unit":"℃","min":-200,"max":600,"scale":1}'},
            {"code": "va_humidity", "type": "Integer", "values": '{"unit":"%","min":0,"max":100,"scale":0}'}]},
        "fikus": {"status": [
            {"code": "humidity", "type": "Integer", "values": '{"unit":"%","min":0,"max":100,"scale":0}'},
            {"code": "temp_current", "type": "Integer", "values": '{"unit":"℃","min":-400,"max":1200,"scale":1}'},
            {"code": "dimmer", "type": "Integer", "values": '{"unit":"Lux","min":0,"max":10000,"scale":0}'}],
            "functions": [{"code": "adjust_sample_time", "type": "Integer", "values": '{"unit":"s","min":30,"max":1200,"scale":0}'}]},
    }

    def get(self, path, params=None):
        if path == "/v1.0/iot-01/associated-users/devices":
            self.zapytan += 1
            self.zapytania.append((path, dict(params or {})))
            return {"success": True, "result": {"has_more": False, "devices": [
                {"id": "salon", "name": "Salon", "category": "wsdcg"},
                {"id": "fikus", "name": "Fikus", "category": "zwjcy", "product_name": "Soil sensor",
                 "status": [{"code": "humidity", "value": 41}, {"code": "dimmer", "value": 230}]},
            ]}}
        if path.endswith("/specifications"):
            self.zapytan += 1
            self.zapytania.append((path, dict(params or {})))
            return {"success": True, "result": self.SPEC[path.split("/")[3]]}
        return super().get(path, params)


class TestOdkryj(PrzebiegKolektora):
    """--discover ma odpowiedzieć na pytania o nowy czujnik w jednym przebiegu i tanio."""

    URZADZENIA = ("salon",)

    def odkryj(self) -> tuple[AtrapaZeSpecyfikacja, str]:
        teraz = self.teraz
        fikus = [{"code": "humidity", "value": "41", "event_time": teraz - k * 60_000} for k in range(1, 50)]
        atrapa = AtrapaZeSpecyfikacja({"salon": tydzien_odczytow(teraz), "fikus": fikus})
        wyjscie = io.StringIO()
        with mock.patch.dict(os.environ, {"TUYA_CLIENT_ID": "x", "TUYA_CLIENT_SECRET": "y"}), \
                mock.patch.object(fetch, "Tuya", lambda *a, **k: atrapa), \
                mock.patch.object(sys, "argv", ["fetch.py", "--discover"]), \
                redirect_stdout(wyjscie):
            self.assertEqual(fetch.main(), 0)
        return atrapa, wyjscie.getvalue()

    def test_jedna_specyfikacja_na_urzadzenie(self):
        atrapa, _ = self.odkryj()
        spec = [path for path, _ in atrapa.zapytania if path.endswith("/specifications")]
        self.assertEqual(len(spec), 2, "dawniej dwie specyfikacje na urządzenie")

    def test_nowy_czujnik_dostaje_tempo_wpisow_a_znany_nie(self):
        atrapa, wyjscie = self.odkryj()
        self.assertIn("49 wpisów w ostatnich 60 min", wyjscie)
        logi = [path for path, _ in atrapa.zapytania if path.endswith("/logs")]
        self.assertEqual(logi, ["/v1.0/devices/fikus/logs"], "pomiar tylko dla urządzeń spoza manifestu")

    def test_czujnik_w_doniczce_nie_do_tuya_device_ids(self):
        _, wyjscie = self.odkryj()
        self.assertIn("czujnik w doniczce", wyjscie)
        self.assertIn("NIE dopisuj ich", wyjscie)
        self.assertIn("ustawienie: adjust_sample_time", wyjscie)
        self.assertIn("0…10000", wyjscie)


class TestOdkryjDziwneOdpowiedzi(PrzebiegKolektora):
    """Jedno urządzenie z nietypową specyfikacją nie może przerwać całego --discover."""

    URZADZENIA = ("salon",)

    def test_dziwna_specyfikacja_nie_przerywa(self):
        class Dziwna(AtrapaZeSpecyfikacja):
            SPEC = dict(AtrapaZeSpecyfikacja.SPEC, fikus={
                "status": [{"code": "humidity", "type": "Integer", "values": "[]"}, "nie-słownik"],
                "functions": None})
        logi = {"salon": tydzien_odczytow(self.teraz), "fikus": []}
        atrapa = Dziwna(logi)
        wyjscie = io.StringIO()
        with mock.patch.dict(os.environ, {"TUYA_CLIENT_ID": "x", "TUYA_CLIENT_SECRET": "y"}), \
                mock.patch.object(fetch, "Tuya", lambda *a, **k: atrapa), \
                mock.patch.object(sys, "argv", ["fetch.py", "--discover"]), \
                redirect_stdout(wyjscie):
            self.assertEqual(fetch.main(), 0)
        self.assertIn("pole: humidity", wyjscie.getvalue())
        self.assertIn("Zapytań do Tuya", wyjscie.getvalue())


class TestPodpowiedzi(unittest.TestCase):
    def test_wyczerpany_pakiet_ma_podpowiedz(self):
        tekst = fetch.explain({"code": 28841004, "msg": "quota exhausted"})
        self.assertIn("IoT Core", tekst)
        self.assertIn("1. dnia miesiąca", tekst)


if __name__ == "__main__":
    unittest.main()
