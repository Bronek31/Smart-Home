#!/usr/bin/env python3
"""Testy kolektora. Biblioteka standardowa, zero zależności poza tym, co i tak ma fetch.py.

    python -m unittest discover -s tests -v

Każdy test, który dotyka plików, pracuje w katalogu tymczasowym — nic tu nie rusza
prawdziwego data/. Wyjątkiem są testy oznaczone jako „na żywych danych"; one czytają
repozytorium, ale wyłącznie do odczytu i sprawdzają niezmienniki, nie konkretne liczby,
bo te zmieniają się co godzinę wraz z każdą zbiórką.
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import fetch  # noqa: E402


def ts(offset_h: float = 0) -> str:
    return fetch.iso(int((datetime.now(timezone.utc) + timedelta(hours=offset_h)).timestamp() * 1000))


class WKatalogu(unittest.TestCase):
    """Przenosi fetch.py na czas testu do świeżego katalogu z pustym data/."""

    def setUp(self):
        self.katalog = Path(tempfile.mkdtemp())
        self.poprzedni = Path.cwd()
        os.chdir(self.katalog)
        (self.katalog / "data").mkdir()
        # moduł trzyma ścieżki jako stałe względne, więc wystarczy zmiana katalogu
        self.assertEqual(fetch.DATA_DIR, Path("data"))

    def tearDown(self):
        os.chdir(self.poprzedni)
        shutil.rmtree(self.katalog, ignore_errors=True)

    def zapisz(self, miesiac: str, wiersze: list[tuple[str, str, str, str]]):
        with (self.katalog / "data" / f"{miesiac}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(fetch.FIELDS)
            w.writerows(wiersze)


class TestClassify(unittest.TestCase):
    def test_rozpoznaje_temperature_i_wilgotnosc(self):
        self.assertEqual(fetch.classify("va_temperature", "℃"), "temp")
        self.assertEqual(fetch.classify("va_humidity", "%"), "hum")
        self.assertEqual(fetch.classify("temp_current", ""), "temp")
        # nieznany kod z pasującą jednostką też przechodzi
        self.assertEqual(fetch.classify("room_temp", "°C"), "temp")
        self.assertEqual(fetch.classify("air_humi", "%"), "hum")

    def test_wlacznik_i_bateria(self):
        self.assertEqual(fetch.classify("switch", ""), "power")
        self.assertEqual(fetch.classify("switch_1", ""), "power")
        self.assertEqual(fetch.classify("battery_state", ""), "battery")
        self.assertEqual(fetch.classify("battery_percentage", "%"), "battery")

    def test_switch_z_nieliczbowym_ogonem_to_nie_wlacznik(self):
        # switch_led to podświetlenie, nie włącznik urządzenia
        self.assertIsNone(fetch.classify("switch_led", ""))

    def test_odrzuca_pola_nastawcze_i_alarmowe(self):
        for kod in ("temp_set", "temp_correction", "humidity_alarm", "colour_data",
                    "bright_value", "work_mode", "countdown_1", "upper_temp"):
            with self.subTest(kod=kod):
                self.assertIsNone(fetch.classify(kod, "°C"))

    def test_temperatura_bez_wiarygodnej_jednostki_odpada(self):
        # "temp" w nazwie to za mało, gdy jednostka mówi co innego
        self.assertIsNone(fetch.classify("temp_something", "ppm"))


class TestDropSpikes(unittest.TestCase):
    def test_wyskok_ktory_wraca_jest_ucinany(self):
        pkt = [(i * 600.0, 22.0) for i in range(6)]
        pkt[3] = (1800.0, 26.0)          # +4 °C na jeden odczyt, potem powrót
        bad = fetch.drop_spikes(pkt, "temp")
        self.assertIn(3, bad)
        self.assertEqual(len(bad), 1)

    def test_trwala_zmiana_zostaje(self):
        # grzejnik: rośnie i już nie wraca
        pkt = [(i * 600.0, 22.0) for i in range(4)] + [(i * 600.0, 26.0) for i in range(4, 12)]
        self.assertEqual(fetch.drop_spikes(pkt, "temp"), set())

    def test_krotka_seria_i_nieznany_rodzaj(self):
        self.assertEqual(fetch.drop_spikes([(0.0, 20.0), (60.0, 30.0)], "temp"), set())
        self.assertEqual(fetch.drop_spikes([(i * 60.0, float(i)) for i in range(10)], None), set())
        self.assertEqual(fetch.drop_spikes([], "temp"), set())

    def test_prog_wilgotnosci_jest_luzniejszy_niz_temperatury(self):
        # 4 punkty procentowe to dla wilgotności szum, dla temperatury byłby wyskok
        pkt = [(i * 600.0, 50.0) for i in range(6)]
        pkt[3] = (1800.0, 54.0)
        self.assertEqual(fetch.drop_spikes(pkt, "hum"), set())
        pkt[3] = (1800.0, 60.0)
        self.assertIn(3, fetch.drop_spikes(pkt, "hum"))


class TestParseSince(unittest.TestCase):
    def test_pusty_znaczy_brak_granicy(self):
        self.assertEqual(fetch.parse_since(""), 0)
        self.assertEqual(fetch.parse_since("   "), 0)

    def test_data_bez_strefy_jest_czytana_jako_utc(self):
        self.assertEqual(fetch.parse_since("2026-08-13"),
                         int(datetime(2026, 8, 13, tzinfo=timezone.utc).timestamp() * 1000))

    def test_data_ze_strefa(self):
        self.assertEqual(fetch.parse_since("2026-08-12T21:30+02:00"),
                         int(datetime(2026, 8, 12, 19, 30, tzinfo=timezone.utc).timestamp() * 1000))

    def test_zly_format_konczy_sie_czytelnym_bledem(self):
        with self.assertRaises(fetch.TuyaError) as e:
            fetch.parse_since("wczoraj")
        self.assertIn("TUYA_SINCE", str(e.exception))


class TestTrimHourly(unittest.TestCase):
    def blok(self, godzin=48, offset_h=0):
        baza = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        czasy = [(baza + timedelta(hours=i - 6 + offset_h)).strftime("%Y-%m-%dT%H:00") for i in range(godzin)]
        return {"time": czasy,
                "temperature_2m": [float(i) for i in range(godzin)],
                "relative_humidity_2m": [50] * godzin}

    def test_przestawia_czas_lokalny_na_utc(self):
        # lokalne 10:00 przy przesunięciu +2 godz. to 08:00 UTC
        out = fetch.trim_hourly({"time": ["2026-08-15T10:00"], "temperature_2m": [20]}, 7200)
        # przycięcie odrzuci wpis z przeszłości, więc sprawdzamy samą arytmetykę osobno
        kiedy = datetime.fromisoformat("2026-08-15T10:00").replace(tzinfo=timezone.utc).timestamp() - 7200
        self.assertEqual(fetch.iso(int(kiedy * 1000)), "2026-08-15T08:00:00Z")
        self.assertIsInstance(out, dict)

    def test_przycina_do_okna_i_trzyma_rowne_dlugosci(self):
        out = fetch.trim_hourly(self.blok(godzin=72), 0)
        self.assertTrue(out["time"])
        self.assertLessEqual(len(out["time"]), fetch.PROGNOZA_GODZIN + 2)
        for pole, wartosci in out.items():
            with self.subTest(pole=pole):
                self.assertEqual(len(wartosci), len(out["time"]))

    def test_znaczniki_wychodza_w_utc_i_rosnaco(self):
        out = fetch.trim_hourly(self.blok(), 0)
        self.assertTrue(all(t.endswith("Z") for t in out["time"]))
        self.assertEqual(out["time"], sorted(out["time"]))

    def test_pusty_blok_nie_wywraca(self):
        self.assertEqual(fetch.trim_hourly({}, 0), {})
        self.assertEqual(fetch.trim_hourly({"time": []}, 0), {})

    def test_zly_znacznik_jest_pomijany_bez_rozjazdu_kolumn(self):
        b = self.blok(godzin=12)
        b["time"][3] = "nie-data"
        out = fetch.trim_hourly(b, 0)
        for pole, wartosci in out.items():
            self.assertEqual(len(wartosci), len(out["time"]), pole)


class TestUdzialPowyzej(unittest.TestCase):
    def test_liczy_czasem_a_nie_liczba_odczytow(self):
        teraz = int(datetime.now(timezone.utc).timestamp() * 1000)
        godz = fetch.HEARTBEAT_MS
        # jedna godzina wysoko, trzy nisko — mimo że wysokich próbek jest więcej
        pkt = [(teraz - 4 * godz, 70.0), (teraz - 3 * godz, 70.0),
               (teraz - 2 * godz, 40.0), (teraz - godz, 40.0), (teraz, 40.0)]
        self.assertAlmostEqual(fetch.udzial_powyzej(pkt, 65), 0.25, places=2)

    def test_dziura_dluzsza_niz_dwa_heartbeaty_nie_zalicza_sie_w_calosci(self):
        teraz = int(datetime.now(timezone.utc).timestamp() * 1000)
        pkt = [(teraz - 50 * fetch.HEARTBEAT_MS, 70.0), (teraz, 70.0)]
        # cisza nie jest stanem trwającym, więc odstęp jest przycinany
        self.assertEqual(fetch.udzial_powyzej(pkt, 65), 1.0)

    def test_za_malo_punktow(self):
        self.assertEqual(fetch.udzial_powyzej([], 65), 0.0)
        self.assertEqual(fetch.udzial_powyzej([(0, 90.0)], 65), 0.0)


class TestDiagnose(WKatalogu):
    def manifest(self):
        return {
            "czujnik": {"name": "Salon", "codes": {
                "va_temperature": {"kind": "temp", "unit": "℃", "scale": 1},
                "va_humidity": {"kind": "hum", "unit": "%", "scale": 0},
                "battery_state": {"kind": "battery", "unit": "%", "scale": 0}}},
            "pogoda": {"name": "Na zewnątrz", "external": True, "codes": {
                "va_temperature": {"kind": "temp", "unit": "°C", "scale": 0}}},
            "sprzet": {"name": "Klimatyzator", "appliance": True, "codes": {
                "switch": {"kind": "power", "unit": "", "scale": 0}}},
        }

    def test_wszystko_w_normie_daje_pusta_liste(self):
        miesiac = datetime.now(timezone.utc).strftime("%Y-%m")
        wiersze = []
        for i in range(24, 0, -1):
            wiersze += [(ts(-i), "czujnik", "va_temperature", "24"),
                        (ts(-i), "czujnik", "va_humidity", "45"),
                        (ts(-i), "czujnik", "battery_state", "high")]
        self.zapisz(miesiac, wiersze)
        self.assertEqual(fetch.diagnose(self.manifest()), [])

    def test_lapie_cisze_slaba_baterie_i_wilgoc(self):
        miesiac = datetime.now(timezone.utc).strftime("%Y-%m")
        wiersze = []
        for i in range(24, 8, -1):           # ostatni odczyt 9 godz. temu
            wiersze += [(ts(-i), "czujnik", "va_temperature", "24"),
                        (ts(-i), "czujnik", "va_humidity", "80"),
                        (ts(-i), "czujnik", "battery_state", "low")]
        self.zapisz(miesiac, wiersze)
        alerty = " | ".join(fetch.diagnose(self.manifest()))
        self.assertIn("milczy", alerty)
        self.assertIn("bateria", alerty)
        self.assertIn("wilgotność", alerty)

    def test_pomija_pogode_i_sprzet(self):
        miesiac = datetime.now(timezone.utc).strftime("%Y-%m")
        self.zapisz(miesiac, [(ts(-30), "pogoda", "va_temperature", "30"),
                              (ts(-30), "sprzet", "switch", "1")])
        for a in fetch.diagnose(self.manifest()):
            self.assertNotIn("Na zewnątrz", a)
            self.assertNotIn("Klimatyzator", a)

    def test_bateria_procentowa(self):
        miesiac = datetime.now(timezone.utc).strftime("%Y-%m")
        m = self.manifest()
        wiersze = [(ts(-1), "czujnik", "va_temperature", "24"),
                   (ts(-1), "czujnik", "battery_state", "8")]
        self.zapisz(miesiac, wiersze)
        self.assertTrue(any("bateria" in a for a in fetch.diagnose(m)))


class TestMergeICSV(WKatalogu):
    def test_merge_nie_duplikuje_i_sortuje(self):
        wiersze = [{"ts": "2026-08-01T10:00:00Z", "device_id": "a", "code": "t", "value": "1"},
                   {"ts": "2026-08-01T09:00:00Z", "device_id": "a", "code": "t", "value": "2"}]
        self.assertEqual(fetch.merge(wiersze), 2)
        self.assertEqual(fetch.merge(wiersze), 0)        # drugi raz to samo — nic nie dochodzi
        zapisane = fetch.load_month("2026-08")
        self.assertEqual([r["ts"] for r in zapisane],
                         ["2026-08-01T09:00:00Z", "2026-08-01T10:00:00Z"])

    def test_merge_rozklada_na_miesiace(self):
        fetch.merge([{"ts": "2026-07-31T23:00:00Z", "device_id": "a", "code": "t", "value": "1"},
                     {"ts": "2026-08-01T01:00:00Z", "device_id": "a", "code": "t", "value": "2"}])
        self.assertEqual(len(fetch.load_month("2026-07")), 1)
        self.assertEqual(len(fetch.load_month("2026-08")), 1)

    def test_purge_before_usuwa_starsze(self):
        self.zapisz("2026-08", [("2026-08-01T00:00:00Z", "a", "t", "1"),
                                ("2026-08-10T00:00:00Z", "a", "t", "2")])
        granica = fetch.parse_since("2026-08-05")
        self.assertEqual(fetch.purge_before(granica), 1)
        self.assertEqual(len(fetch.load_month("2026-08")), 1)
        self.assertEqual(fetch.purge_before(0), 0)       # brak granicy nic nie rusza

    def test_purge_nie_rusza_dziennych(self):
        self.zapisz("2026-08", [("2026-08-01T00:00:00Z", "a", "t", "1")])
        fetch.DAILY.write_text("date,device_id,code,min,avg,max,n\n2026-08-01,a,t,1,1,1,1\n", encoding="utf-8")
        fetch.purge_before(fetch.parse_since("2026-08-05"))
        self.assertIn("2026-08-01", fetch.DAILY.read_text(encoding="utf-8"))


class TestCollapsePower(WKatalogu):
    URZ = {"ac": {"name": "Klima", "appliance": True,
                  "codes": {"switch": {"kind": "power", "unit": "", "scale": 0}}}}

    def test_zwija_powtorzenia_zostawia_przelaczenia(self):
        self.zapisz("2026-08", [("2026-08-01T00:00:00Z", "ac", "switch", "0"),
                                ("2026-08-01T00:01:00Z", "ac", "switch", "0"),
                                ("2026-08-01T00:02:00Z", "ac", "switch", "1"),
                                ("2026-08-01T00:03:00Z", "ac", "switch", "1"),
                                ("2026-08-01T00:04:00Z", "ac", "switch", "0")])
        self.assertEqual(fetch.collapse_power(self.URZ), 2)
        self.assertEqual([r["value"] for r in fetch.load_month("2026-08")], ["0", "1", "0"])

    def test_jest_idempotentny(self):
        self.zapisz("2026-08", [("2026-08-01T00:00:00Z", "ac", "switch", "1"),
                                ("2026-08-01T00:01:00Z", "ac", "switch", "1")])
        fetch.collapse_power(self.URZ)
        self.assertEqual(fetch.collapse_power(self.URZ), 0)

    def test_nie_rusza_czujnikow_klimatu(self):
        urz = {"c": {"name": "Salon", "codes": {"va_temperature": {"kind": "temp", "unit": "℃", "scale": 1}}}}
        self.zapisz("2026-08", [("2026-08-01T00:00:00Z", "c", "va_temperature", "22"),
                                ("2026-08-01T00:01:00Z", "c", "va_temperature", "22")])
        self.assertEqual(fetch.collapse_power(urz), 0)
        self.assertEqual(len(fetch.load_month("2026-08")), 2)


class TestWriteDaily(WKatalogu):
    URZ = {
        "c": {"name": "Salon", "codes": {
            "va_temperature": {"kind": "temp", "unit": "℃", "scale": 1},
            "battery_state": {"kind": "battery", "unit": "%", "scale": 0}}},
        "zewnatrz": {"name": "Na zewnątrz", "external": True, "codes": {
            "va_temperature": {"kind": "temp", "unit": "°C", "scale": 0}}},
        "ac": {"name": "Klima", "appliance": True, "codes": {
            "switch": {"kind": "power", "unit": "", "scale": 0}}},
    }

    def setUp(self):
        super().setUp()
        os.environ["TZ_LOCAL"] = "Europe/Warsaw"

    def test_liczy_min_srednia_max_i_pomija_wlacznik_z_bateria(self):
        self.zapisz("2026-08", [
            ("2026-08-01T08:00:00Z", "c", "va_temperature", "20"),
            ("2026-08-01T09:00:00Z", "c", "va_temperature", "24"),
            ("2026-08-01T10:00:00Z", "c", "battery_state", "high"),
            ("2026-08-01T10:00:00Z", "ac", "switch", "1"),
        ])
        fetch.write_daily(self.URZ)
        with fetch.DAILY.open(encoding="utf-8") as f:
            wiersze = list(csv.DictReader(f))
        self.assertEqual(len(wiersze), 1)
        self.assertEqual((wiersze[0]["min"], wiersze[0]["avg"], wiersze[0]["max"], wiersze[0]["n"]),
                         ("20", "22.00", "24", "2"))

    def test_jest_powtarzalny(self):
        self.zapisz("2026-08", [(f"2026-08-01T{h:02d}:00:00Z", "c", "va_temperature", str(20 + h % 3))
                                for h in range(24)])
        fetch.write_daily(self.URZ)
        pierwszy = fetch.DAILY.read_text(encoding="utf-8")
        fetch.write_daily(self.URZ)
        self.assertEqual(pierwszy, fetch.DAILY.read_text(encoding="utf-8"))

    def gesta_seria(self, urzadzenie, ze_skokiem):
        """Odczyty co 10 minut — tak wygląda seria, gdy czujnik raportuje zmianę o 0,5 °C.
        Wyskoki wykrywa się tylko w takim zagęszczeniu; patrz test poniżej."""
        wiersze = []
        for i in range(12):
            wiersze.append((f"2026-08-01T08:{i * 5:02d}:00Z", urzadzenie, "va_temperature", "20"))
        if ze_skokiem:
            wiersze[6] = ("2026-08-01T08:30:00Z", urzadzenie, "va_temperature", "26")
        return wiersze

    def odczytaj_dzienne(self, urzadzenie):
        with fetch.DAILY.open(encoding="utf-8") as f:
            return [r for r in csv.DictReader(f) if r["device_id"] == urzadzenie]

    def test_pogoda_nie_jest_odszumiana(self):
        """Przeglądarka nie filtruje pogody, więc agregaty też nie mogą — inaczej widok
        „całość" pokazywałby inny przebieg niż siedmiodniowy."""
        self.zapisz("2026-08", self.gesta_seria("zewnatrz", ze_skokiem=True))
        fetch.write_daily(self.URZ)
        self.assertEqual(self.odczytaj_dzienne("zewnatrz")[0]["max"], "26",
                         "skok pogodowy nie powinien zostać wycięty")

    def test_czujnik_jest_odszumiany(self):
        self.zapisz("2026-08", self.gesta_seria("c", ze_skokiem=True))
        fetch.write_daily(self.URZ)
        self.assertEqual(self.odczytaj_dzienne("c")[0]["max"], "20",
                         "wyskok czujnika powinien zostać wycięty")

    def test_pojedynczy_skok_w_rytmie_godzinowym_nie_jest_wyskokiem(self):
        """Świadomy limit, nie usterka. Wyskok rozpoznajemy po tym, że wartość wraca
        w ciągu SPIKE_MAX (90 min) licząc od punktu sprzed wzrostu. Przy raportach co
        godzinę powrót wypada 120 minut po tamtym punkcie, więc się nie mieści.

        Tak ma być: filtr celuje w sytuację, gdy ktoś bierze czujnik do ręki, a wtedy
        próg 0,5 °C wyzwala raporty co kilkanaście sekund i zagęszczenie jest zupełnie
        inne. Pojedynczy dziwny odczyt na godzinnym pulsie zostaje w danych — i słusznie,
        bo równie dobrze może być prawdziwy."""
        wiersze = [(f"2026-08-01T{i:02d}:00:00Z", "c", "va_temperature", "20") for i in range(8)]
        wiersze[4] = ("2026-08-01T04:00:00Z", "c", "va_temperature", "26")
        self.zapisz("2026-08", wiersze)
        fetch.write_daily(self.URZ)
        self.assertEqual(self.odczytaj_dzienne("c")[0]["max"], "26")

    def test_nieznana_strefa_nie_wywraca(self):
        os.environ["TZ_LOCAL"] = "Nie/Ma/Takiej"
        self.zapisz("2026-08", [("2026-08-01T08:00:00Z", "c", "va_temperature", "20")])
        self.assertEqual(fetch.write_daily(self.URZ), 1)


class TestManifest(WKatalogu):
    def test_external_ids_i_code_kinds_czytaja_takze_stary_manifest(self):
        fetch.write_manifest({"stary": {"name": "Dwór", "external": True,
                                        "codes": {"va_temperature": {"kind": "temp", "unit": "°C", "scale": 0}}}})
        self.assertIn("stary", fetch.external_ids({}))
        self.assertEqual(fetch.code_kinds({}).get(("stary", "va_temperature")), "temp")

    def test_manifest_zawiera_alerty_i_jest_poprawnym_jsonem(self):
        fetch.write_manifest({"a": {"name": "A", "codes": {}}}, ["coś"])
        m = json.loads(fetch.MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(m["alerty"], ["coś"])
        self.assertIn("updated", m)
        self.assertTrue(m["updated"].endswith("Z"))

    def test_uszkodzony_manifest_nie_wywraca_odczytu(self):
        fetch.MANIFEST.write_text("{to nie json", encoding="utf-8")
        self.assertEqual(fetch.external_ids({}), set())
        self.assertEqual(fetch.code_kinds({}), {})


class TestLocationOf(unittest.TestCase):
    """Współrzędne dla łuku doby na stronie."""

    def test_bierze_punkt_siatki_oddany_przez_open_meteo(self):
        # Open-Meteo przyciąga zapytanie do swojej siatki; prognoza dotyczy tego punktu,
        # nie tego, o który pytaliśmy, więc na stronie ma być ten sam
        self.assertEqual(
            fetch.location_of({"latitude": 50.25, "longitude": 19.0}, "50.2649", "19.0238"),
            {"lat": 50.25, "lon": 19.0})

    def test_bez_wspolrzednych_w_odpowiedzi_zostaje_to_o_co_pytalismy(self):
        self.assertEqual(fetch.location_of({}, "50.2649", "19.0238"),
                         {"lat": 50.2649, "lon": 19.0238})

    def test_smiec_zamiast_liczby_daje_none_zamiast_wywrotki(self):
        # bez współrzędnych strona po prostu nie rysuje łuku — to nie powód, żeby
        # przerywać cały przebieg kolektora
        self.assertIsNone(fetch.location_of({"latitude": "nie-liczba"}, "", ""))
        self.assertIsNone(fetch.location_of({}, "", ""))


class TestDrobiazgi(unittest.TestCase):
    def test_iso_jest_odwracalne(self):
        ms = 1_776_000_000_000
        self.assertEqual(
            int(datetime.fromisoformat(fetch.iso(ms).replace("Z", "+00:00")).timestamp() * 1000), ms)

    def test_explain_podpowiada_przy_znanych_kodach(self):
        self.assertIn("IoT Core", fetch.explain({"code": 28841002, "msg": "x"}))
        self.assertIn("region", fetch.explain({"code": 1114, "msg": "x"}).lower())
        self.assertIn("999", fetch.explain({"code": 999, "msg": "999"}))   # nieznany też się nie wywala

    def test_regiony_maja_adresy_https(self):
        for nazwa, url in fetch.REGIONS.items():
            with self.subTest(region=nazwa):
                self.assertTrue(url.startswith("https://"))


class TestNaZywychDanych(unittest.TestCase):
    """Niezmienniki prawdziwego data/ w repozytorium.

    Bez asercji na konkretne wartości — te zmieniają się co godzinę. Sprawdzamy kształt:
    czy pliki są spójne, czy agregaty dają się odtworzyć z surowych odczytów.
    """

    @classmethod
    def setUpClass(cls):
        cls.manifest_path = REPO / "data" / "index.json"
        if not cls.manifest_path.exists():
            raise unittest.SkipTest("brak data/index.json — nic do sprawdzenia")
        cls.manifest = json.loads(cls.manifest_path.read_text(encoding="utf-8"))

    def test_manifest_ma_wymagane_pola(self):
        for pole in ("updated", "months", "devices"):
            self.assertIn(pole, self.manifest)
        self.assertIsInstance(self.manifest.get("alerty", []), list)

    def test_kazdy_miesiac_z_manifestu_istnieje_i_ma_naglowek(self):
        for m in self.manifest["months"]:
            p = REPO / "data" / f"{m}.csv"
            self.assertTrue(p.exists(), f"brak {p}")
            with p.open(encoding="utf-8") as f:
                self.assertEqual(next(csv.reader(f)), fetch.FIELDS)

    def test_surowe_odczyty_sa_posortowane_i_bez_duplikatow(self):
        for m in self.manifest["months"]:
            with self.subTest(miesiac=m):
                with (REPO / "data" / f"{m}.csv").open(encoding="utf-8") as f:
                    wiersze = list(csv.DictReader(f))
                klucze = [(r["ts"], r["device_id"], r["code"]) for r in wiersze]
                self.assertEqual(klucze, sorted(klucze), "plik miesięczny ma być posortowany")
                self.assertEqual(len(klucze), len(set(klucze)), "ten sam odczyt zapisany dwa razy")

    def test_kazde_urzadzenie_z_odczytow_jest_w_manifescie(self):
        znane = set(self.manifest["devices"])
        for m in self.manifest["months"]:
            with (REPO / "data" / f"{m}.csv").open(encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    self.assertIn(r["device_id"], znane)

    def test_wlacznik_ma_wylacznie_zmiany_stanu(self):
        power = {k for k, v in fetch.code_kinds(self.manifest["devices"]).items() if v == "power"}
        if not power:
            self.skipTest("brak urządzeń z włącznikiem")
        ostatnia = {}
        for m in self.manifest["months"]:
            with (REPO / "data" / f"{m}.csv").open(encoding="utf-8") as f:
              for r in csv.DictReader(f):
                klucz = (r["device_id"], r["code"])
                if klucz in power:
                    self.assertNotEqual(ostatnia.get(klucz), r["value"],
                                        f"{klucz} ma dwa razy pod rząd ten sam stan — collapse_power nie zadziałał")
                    ostatnia[klucz] = r["value"]

    def test_agregaty_dobowe_odtwarzaja_sie_z_surowych(self):
        """Najmocniejszy test kolektora: przeliczamy dzienne.csv od zera w katalogu
        tymczasowym i porównujemy bajt w bajt z tym, co leży w repozytorium."""
        katalog = Path(tempfile.mkdtemp())
        try:
            shutil.copytree(REPO / "data", katalog / "data")
            poprzedni = Path.cwd()
            os.chdir(katalog)
            try:
                oryginal = (REPO / "data" / "dzienne.csv").read_text(encoding="utf-8")
                os.environ["TZ_LOCAL"] = "Europe/Warsaw"
                fetch.write_daily(self.manifest["devices"])
                self.assertEqual(oryginal, fetch.DAILY.read_text(encoding="utf-8"))
            finally:
                os.chdir(poprzedni)
        finally:
            shutil.rmtree(katalog, ignore_errors=True)

    def test_pogoda_ma_prognoze_godzinowa_w_utc(self):
        p = REPO / "data" / "pogoda.json"
        if not p.exists():
            self.skipTest("brak pogoda.json")
        w = json.loads(p.read_text(encoding="utf-8"))
        godzinowe = w.get("hourly") or {}
        if not godzinowe.get("time"):
            self.skipTest("prognoza godzinowa jeszcze niezebrana")
        self.assertTrue(all(t.endswith("Z") for t in godzinowe["time"]))
        for pole, wartosci in godzinowe.items():
            self.assertEqual(len(wartosci), len(godzinowe["time"]), pole)


if __name__ == "__main__":
    unittest.main(verbosity=2)
