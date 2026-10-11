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
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fetch  # noqa: E402
import rosliny  # noqa: E402
import telefony  # noqa: E402
from test_przyrostowe import (AtrapaTuya, GODZ, KODY, PrzebiegKolektora,  # noqa: E402
                              tydzien_odczytow)

WAWA = ZoneInfo("Europe/Warsaw")
DOBA_MS = 24 * 3600 * 1000
KODY_ROSLINY = {"gleba": "humidity", "temp": "temp_current", "wilg": "env_humidity",
                "swiatlo": "illumiance", "bateria": "battery_state", "alarm": "water_warning"}


def ms(tekst: str) -> int:
    return int(datetime.fromisoformat(tekst.replace("Z", "+00:00")).timestamp() * 1000)


def wiersz(ts_ms: int, kod: str, wartosc, czujnik: str = "fikus") -> dict:
    return {"ts": rosliny.iso(ts_ms), "device_id": czujnik, "code": kod, "value": str(wartosc)}


def seria(od: int, do: int, krok: int, wartosc, kod: str = "humidity") -> list[dict]:
    """Wiersze CSV jednej serii co `krok` od `od` (włącznie) do `do` (bez); `wartosc`
    to liczba albo funkcja numeru odczytu."""
    out, k = [], 0
    while od + k * krok < do:
        out.append(wiersz(od + k * krok, kod, wartosc(k) if callable(wartosc) else wartosc))
        k += 1
    return out


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

    def test_od_wymaga_godziny_i_strefy(self):
        """Sama data to północ UTC, godzina bez strefy — czas maszyny (w Actions UTC).
        Jedno i drugie po cichu cofa wbicie sondy, a wtedy wbicie uczy się jako podlanie."""
        for zle in ("2026-10-09", "2026-10-09T19:10:00"):
            with self.subTest(zle), self.assertRaisesRegex(ValueError, "strefą"):
                self.wczytaj(self.poprawna(od=zle))
        for dobre in ("2026-10-09T19:10:00+02:00", "2026-10-09T17:10:00Z"):
            self.assertEqual(self.wczytaj(self.poprawna(od=dobre))[0]["od"], dobre)

    def test_zle_typy_to_czytelny_blad_a_nie_typeerror(self):
        """Lista zamiast tekstu dawała TypeError, którego nie łapała obsługa błędów
        konfiguracji; nieskończoność w „sucho" trafiała do stan.json jako Infinity."""
        przypadki = {
            "„czujnik\"": self.poprawna(czujnik=["a"]),
            "nieznany gatunek": self.poprawna(gatunek=["fikus"]),
            "niepustym tekstem": self.poprawna(kody={**KODY_ROSLINY, "gleba": ["humidity"]}),
            "skończoną liczbą": self.poprawna(sucho=float("inf")),
        }
        for oczekiwane, wpis in przypadki.items():
            with self.subTest(oczekiwane), self.assertRaisesRegex(ValueError, oczekiwane):
                self.wczytaj(wpis)

    def test_pomin_podlania_wymaga_daty_ze_strefa(self):
        for zle in ("2026-10-09T09:51:00", [{"kiedy": "wczoraj"}], [{"dlaczego": "woda"}], ["2026-10-09T09:51:00Z"]):
            with self.subTest(zle), self.assertRaisesRegex(ValueError, "pomin_podlania"):
                self.wczytaj(self.poprawna(pomin_podlania=zle))
        k = self.wczytaj(self.poprawna(pomin_podlania=[{"kiedy": "2026-10-09T09:51:00+02:00", "dlaczego": "osłonka"}]))
        self.assertEqual(k[0]["pomin_podlania"], [ms("2026-10-09T07:51:00Z")])

    def test_zly_json_i_dwa_razy_ten_sam_czujnik(self):
        with self.assertRaisesRegex(ValueError, "poprawny JSON"):
            rosliny.wczytaj_konfiguracje("{to nie json")
        with self.assertRaisesRegex(ValueError, "dwa razy"):
            self.wczytaj(self.poprawna(), self.poprawna(nazwa="Drugi"))
        # ta sama nazwa przy różnych czujnikach — zakładka i powiadomienia wybierają po nazwie
        with self.assertRaisesRegex(ValueError, "Fikus wpisana dwa razy"):
            self.wczytaj(self.poprawna(), self.poprawna(czujnik="b"))

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

    def test_drgajaca_gleba_to_nie_zmiana(self):
        t0 = ms("2026-10-08T00:00:00Z")
        drga = [wiersz(t0 + k * 20 * 60_000, "humidity", 10 + k % 2) for k in range(72)]   # doba co 20 min
        drga += [wiersz(t0 + 24 * GODZ + 60_000, "humidity", 14)]
        strefa = {("fikus", "humidity"): rosliny.MARTWA_STREFA_GLEBY}
        wynik = rosliny.zwin(drga, martwa_strefa=strefa)
        self.assertLessEqual(len(wynik), 26, "drgnięcie 10↔11 zostaje w CSV jak zmiana")
        self.assertEqual(wynik[-1]["value"], "14", "zmiana o 3 punkty musi zostać")
        self.assertEqual(rosliny.zwin(wynik, martwa_strefa=strefa), wynik)
        # zakładka dokłada wycięte wiersze z powrotem — wynik ten sam
        self.assertEqual(rosliny.zwin(wynik + drga[30:40], martwa_strefa=strefa), wynik)


class TestSwiatlo(unittest.TestCase):
    def test_stala_wartosc_daje_iloczyn_i_pokrycie(self):
        poczatek = ms("2026-10-08T08:00:00Z")          # 10:00 w Warszawie
        pkt = [(poczatek + k * GODZ, 600.0) for k in range(5)]
        doby = rosliny.luksogodziny(pkt, WAWA, ms("2026-10-07T22:00:00Z"), ms("2026-10-08T21:59:59Z"))
        doba = {d["data"]: d for d in doby}["2026-10-08"]
        # 5 punktów co godzinę, ostatni trzymany 3 godz.: 7 godz. po 600 lx
        self.assertEqual(doba["lxh"], 4200)
        self.assertAlmostEqual(doba["pokrycie"], 7 / 24, places=2)

    def test_dluga_przerwa_to_brak_pomiaru_a_nie_ciemnosc_ani_swiatlo(self):
        pkt = [(ms("2026-10-08T08:00:00Z"), 1000.0), (ms("2026-10-08T14:00:00Z"), 0.0)]
        doby = rosliny.luksogodziny(pkt, WAWA, ms("2026-10-07T22:00:00Z"), ms("2026-10-08T21:59:59Z"))
        doba = {d["data"]: d for d in doby}["2026-10-08"]
        self.assertEqual(doba["lxh"], 3000, "1000 lx przeciągnięte dalej niż 3 godz.")

    def test_swiatlo_co_dwie_godziny_to_pelna_doba(self):
        # Noc 8/9.10: czujnik nie wysyła światła przy każdym wybudzeniu, przerwy do 116 min.
        # W doniczce może być rzadziej; przy trzymaniu 2 godz. każda przerwa 130 min
        # dziurawiła dobę i wyłączała regułę „za ciemno".
        polnoc = ms("2026-10-08T22:00:00Z")                  # 9.10, 00:00 w Warszawie
        pkt = [(polnoc + k * 130 * 60_000, 0.0) for k in range(12)]
        doba = rosliny.luksogodziny(pkt, WAWA, polnoc, polnoc + DOBA_MS)[0]
        self.assertEqual(doba["pokrycie"], 1.0)

    def test_doba_dzieli_sie_o_lokalnej_polnocy(self):
        # 23:00–01:00 czasu warszawskiego po 100 lx: po godzinie w każdej dobie
        pkt = [(ms("2026-10-07T21:00:00Z"), 100.0), (ms("2026-10-07T23:00:00Z"), 0.0)]
        doby = {d["data"]: d["lxh"] for d in
                rosliny.luksogodziny(pkt, WAWA, ms("2026-10-07T00:00:00Z"), ms("2026-10-08T20:00:00Z"))}
        self.assertEqual(doby["2026-10-07"], 100)
        self.assertEqual(doby["2026-10-08"], 100)

    def test_szczyt_trzymany_przez_polnoc(self):
        """5000 lx o 23:00 trzymane do odczytu o 1:00 — szczyt ma też następna doba, bo
        suma lx·h liczy tam tę samą godzinę."""
        pkt = [(ms("2026-10-07T21:00:00Z"), 5000.0), (ms("2026-10-07T23:00:00Z"), 300.0),
               (ms("2026-10-08T08:00:00Z"), 1200.0)]
        doby = {d["data"]: d for d in
                rosliny.luksogodziny(pkt, WAWA, ms("2026-10-06T22:00:00Z"), ms("2026-10-08T21:59:59Z"))}
        self.assertEqual(doby["2026-10-07"]["szczyt_lx"], 5000)
        self.assertEqual(doby["2026-10-08"]["szczyt_lx"], 5000)
        self.assertEqual(doby["2026-10-08"]["lxh"], 5000 + 300 * 3 + 1200 * 3)

    def test_dziura_nie_przedluza_szczytu(self):
        """Odczyt sprzed dziury dłuższej niż 3 godz. nie sięga za nią: 5000 lx o 20:00 nie
        jest szczytem doby, która zaczyna się po 23:00 bez pomiaru."""
        pkt = [(ms("2026-10-07T18:00:00Z"), 5000.0), (ms("2026-10-08T01:30:00Z"), 100.0)]
        doby = {d["data"]: d for d in
                rosliny.luksogodziny(pkt, WAWA, ms("2026-10-05T22:00:00Z"), ms("2026-10-08T21:59:59Z"))}
        self.assertEqual(doby["2026-10-07"]["szczyt_lx"], 5000)
        self.assertEqual(doby["2026-10-08"]["szczyt_lx"], 100)
        self.assertIsNone(doby["2026-10-06"]["szczyt_lx"], "doba bez pomiaru to brak szczytu, nie 0")

    def test_szczyt_w_lokalnej_dobie_przy_zmianie_czasu(self):
        """25.10.2026 ma 25 godz. 23:30 UTC to już 26.10 (0:30 CET), a 22:30 UTC jeszcze
        25.10. Doba według UTC (prototyp w Actions) albo stałego +2 pomyliłaby oba."""
        pkt = [(ms("2026-10-25T22:30:00Z"), 4000.0), (ms("2026-10-25T22:45:00Z"), 0.0),
               (ms("2026-10-25T23:30:00Z"), 6000.0), (ms("2026-10-25T23:45:00Z"), 0.0)]
        doby = {d["data"]: d for d in
                rosliny.luksogodziny(pkt, WAWA, ms("2026-10-24T22:00:00Z"), ms("2026-10-26T22:59:59Z"))}
        self.assertEqual((doby["2026-10-25"]["szczyt_lx"], doby["2026-10-26"]["szczyt_lx"]), (4000, 6000))


def doby_swiatla(*doby, od="2026-10-01") -> list[dict]:
    """swiatlo_dobowe od daty `od`: (lxh, pokrycie, szczyt) na kolejne doby."""
    start = datetime.fromisoformat(od).date()
    return [{"data": (start + timedelta(days=i)).isoformat(), "lxh": lxh, "pokrycie": pokrycie, "szczyt_lx": szczyt}
            for i, (lxh, pokrycie, szczyt) in enumerate(doby)]


class TestOcenaSwiatla(unittest.TestCase):
    """rosliny.ocena_swiatla — jedna decyzja dla karty rośliny i reguły „przestaw"."""
    OD = ms("2026-10-01T06:35:00Z")              # wbicie 1.10 rano
    TERAZ = ms("2026-10-05T10:00:00Z")           # 5.10 — pełne mogą być 2, 3 i 4.10

    def ocena(self, doby, potrzeba=1000, za_duzo=None, teraz=None, werdykt=None, od=None):
        return rosliny.ocena_swiatla(doby, potrzeba, za_duzo, self.OD if od is None else od,
                                     teraz or self.TERAZ, WAWA, werdykt)

    def test_trzy_ostatnie_pelne_doby_bez_dzisiejszej_i_dnia_wbicia(self):
        # 1.10 (wbicie, jasne), 2–4.10 pełne, 5.10 dzisiejsza (jasna)
        doby = doby_swiatla((9000, 1.0, 900), (100, 1.0, 50), (200, 1.0, 60), (300, 1.0, 70), (9000, 0.5, 900))
        o = self.ocena(doby)
        self.assertEqual(o, {"kierunek": "jasniej", "u": 0.2, "proc": 20,
                             "doby": ["2026-10-02", "2026-10-03", "2026-10-04"], "szczyt_lx": 70})

    def test_proc_z_zapisanego_u_polowka_w_gore(self):
        """`proc` to procent, który pokazuje karta i powiadomienie „przestaw". Liczony z u
        zapisanego w stan.json (trzy miejsca) połówką w górę, jak Math.round na stronie:
        0,185 → 19, a nie 18 (f"{18.5:.0f}" w Pythonie). u = 0,18451 zapisuje się jako
        0,185 — z nieprzyciętego wyszłoby 18, a karta pokazałaby 19 (przegląd, C1)."""
        for lxh, u, proc in ((185, 0.185, 19), (184.51, 0.185, 19), (125, 0.125, 13), (375, 0.375, 38),
                             (184.49, 0.184, 18), (349.9, 0.35, 35)):
            with self.subTest(lxh=lxh):
                doby = doby_swiatla((0, 0, None), *[(lxh, 1.0, 50)] * 3, (0, 0.5, None))
                o = json.loads(json.dumps(self.ocena(doby)))
                self.assertEqual((o["u"], o["proc"]), (u, proc))

    def test_mniej_niz_trzy_pelne_doby_to_brak_oceny(self):
        doby = doby_swiatla((9000, 1.0, 900), (100, 1.0, 50), (200, 1.0, 60), (300, 0.5, 70), (9000, 0.5, 900))
        self.assertIsNone(self.ocena(doby))
        self.assertIsNone(self.ocena(doby[:4], teraz=ms("2026-10-04T10:00:00Z")), "dzisiejsza się nie liczy")

    def test_bez_daty_wbicia_brak_pelnych_dob(self):
        doby = doby_swiatla(*[(100, 1.0, 50)] * 5)
        self.assertEqual(rosliny.pelne_doby_swiatla(doby, None, self.TERAZ, WAWA), [])
        self.assertIsNone(rosliny.ocena_swiatla(doby, 1000, None, None, self.TERAZ, WAWA))

    def test_granica_pokrycia_z_obu_stron(self):
        for pokrycie, pelna in ((0.79, False), (rosliny.POKRYCIE_PELNEJ_DOBY, True)):
            with self.subTest(pokrycie=pokrycie):
                doby = doby_swiatla((0, 0, None), (100, 1.0, 50), (200, pokrycie, 60), (300, 1.0, 70), (0, 0.5, None))
                self.assertEqual(self.ocena(doby) is not None, pelna)

    def test_progi_u(self):
        """u = 0,349 to „jaśniej", 0,35 już nie; 0,6 to „ok". Decyzja na nieprzyciętym u."""
        for lxh, kierunek in ((349, "jasniej"), (349.9, "jasniej"), (350, "malo"), (599, "malo"), (600, "ok")):
            with self.subTest(lxh=lxh):
                doby = doby_swiatla((0, 0, None), *[(lxh, 1.0, 50)] * 3, (0, 0.5, None))
                self.assertEqual(self.ocena(doby)["kierunek"], kierunek)

    def test_za_duzo_slonca_ma_pierwszenstwo(self):
        """Szczyt ostatniej pełnej doby ponad próg daje „ciemniej" także przy małej sumie;
        szczyt równy progowi — nie. Bez progu (D3: dziś wszystkie gatunki) nigdy."""
        doby = doby_swiatla((0, 0, None), (100, 1.0, 9000), (100, 1.0, 9000), (100, 1.0, 4001), (0, 0.5, None))
        self.assertEqual(self.ocena(doby, za_duzo=4000)["kierunek"], "ciemniej")
        self.assertEqual(self.ocena(doby, za_duzo=4001)["kierunek"], "jasniej")
        self.assertEqual(self.ocena(doby)["kierunek"], "jasniej")

    def test_czujnik_bez_oceny(self):
        doby = doby_swiatla((0, 0, None), *[(100, 1.0, 50)] * 3, (0, 0.5, None))
        self.assertIsNone(self.ocena(doby, werdykt="czujnik"))
        self.assertIsNotNone(self.ocena(doby, werdykt="nauka"), "w nauce światło liczy się normalnie")

    def test_gatunki_maja_stale_karty_i_uspiony_prog(self):
        """D3: czujnik mierzy do 10 000 lx, progi z projektu były nieosiągalne — `null`, aż
        wiosną zmierzymy nasycenie. Strażnik: nowy gatunek bez tych pól wywróciłby stan."""
        for nazwa, g in rosliny.GATUNKI.items():
            with self.subTest(nazwa):
                self.assertIsInstance(g["nazwa_pelna"], str)
                self.assertLess(g["temp_zakres"][0], g["temp_zakres"][1])
                self.assertLess(g["wilg_zakres"][0], g["wilg_zakres"][1])
                self.assertIn("swiatlo_za_duzo_lx", g)
                self.assertIsNone(g["swiatlo_za_duzo_lx"])


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
        # mediana 2–6 godz. przed skokiem (30 − 0,2 × 40), nie najniższy odczyt tuż przed nim
        self.assertEqual(p[0]["przed"], 22.0)
        self.assertEqual(p[0]["szczyt"], 55.0, "szczyt to mediana 2–6 godz. po podlaniu")
        self.assertTrue(p[0]["liczy"])

    def test_powolne_wilgotnienie_to_nie_podlanie(self):
        t0 = ms("2026-10-08T00:00:00Z")
        pkt = [(t0 + k * GODZ, 20.0 + k) for k in range(30)]      # +1 pkt na godzinę
        self.assertEqual(rosliny.podlania(pkt), [])

    def test_liniowo_przy_glebie_co_30_s(self):
        """Dawna wersja budowała listę poprzednich odczytów dla każdego punktu: 20 tys.
        punktów to 6 s, a 60 dni co 30 s — dziesiątki minut i zabite zadanie przed
        commitem pokoi."""
        t0 = ms("2026-08-10T00:00:00Z")
        pkt = [(t0 + k * 30_000, 10.0 + k % 2 + (25 if k % 5000 > 2500 else 0)) for k in range(30_000)]
        start = time.monotonic()
        p = rosliny.podlania(pkt)
        self.assertLess(time.monotonic() - start, 1.0)
        self.assertEqual(len(p), 6)

    def test_zanurzenie_azalii_przed_to_ziemia_a_nie_powietrze(self):
        # Azalię zanurza się po wyjęciu czujnika: pół godziny sonda leży w powietrzu (8),
        # a „przed" jako najniższy odczyt z okna wychodziło suche jak powietrze.
        t0 = ms("2026-10-08T00:00:00Z")
        pkt = [(t0 + k * 20 * 60_000, 37.0) for k in range(24)]                  # 8 godz.
        pkt += [(t0 + 8 * GODZ + k * 10 * 60_000, 8.0) for k in range(3)]       # sonda wyjęta
        pkt += [(t0 + 8.5 * GODZ + k * 20 * 60_000, 60.0 if k < 6 else 52.0) for k in range(24)]
        pkt = [(int(t), v) for t, v in pkt]
        p = rosliny.podlania(pkt)
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["przed"], 37.0)
        self.assertEqual(p[0]["szczyt"], 52.0)
        self.assertTrue(p[0]["liczy"])

    def test_przerwa_w_danych_tuz_przed_podlaniem(self):
        t0 = ms("2026-10-08T00:00:00Z")
        pkt = [(t0 + k * GODZ, 20.0) for k in range(8)]
        pkt += [(t0 + 10 * GODZ + k * GODZ, 50.0) for k in range(8)]           # 3 godz. bez odczytu
        self.assertEqual(len(rosliny.podlania(pkt)), 1, "podlanie po przerwie w danych przepadło")

    def test_nauka_i_prog_przyciety_do_granic(self):
        podl = [{"przed": 12.0, "szczyt": 50.0, "liczy": True}, {"przed": 13.0, "szczyt": 52.0, "liczy": True},
                {"przed": 11.0, "szczyt": 51.0, "liczy": True}]
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
        s = self.werdykt(k, self.wiersze(30))                                  # R = 0,5
        self.assertEqual(s["werdykt"], "pilne")
        # rada z ROSLINY.md, z wyjęciem czujnika — strona i powiadomienie biorą ją stąd
        self.assertIn("Wyjmij czujnik", " ".join(s["uwagi"]))

    def test_prog_w_jednostkach_czujnika(self):
        """Karta pokazuje glebę w surowych procentach czujnika, więc próg musi być w tych
        samych — „gleba na 85% skali, podlewanie przy 50%" obok odczytu 50% myliło."""
        s = self.werdykt(konf(od="2026-10-08T00:00:00Z"), self.wiersze(40))
        self.assertEqual(s["prog_gleba"], round(10 + s["prog"] * (50 - 10)))
        self.assertIsNone(self.werdykt(konf(), self.wiersze(40))["prog_gleba"])

    def test_cisza_to_czujnik(self):
        k = konf(od="2026-10-08T00:00:00Z")
        w = [x for x in self.wiersze(40, ostatni_ms=self.TERAZ - 20 * GODZ) if x["code"] != "battery_state"]
        s = self.werdykt(k, w)
        self.assertEqual(s["werdykt"], "czujnik")
        self.assertIn("milczy", " ".join(s["uwagi"]))

    def test_poprawienie_sondy_to_nie_podlanie(self):
        # 30 → 18 → 30 przez 20 min: skok jest, wody nie było. Jako pierwsze „podlanie"
        # dawało całą skalę (szczyt 30) i werdykty z niczego.
        t0 = ms("2026-10-11T00:00:00Z")
        w = seria(t0, t0 + 8 * GODZ, 20 * 60_000, 30)
        w += seria(t0 + 8 * GODZ, t0 + 8 * GODZ + 20 * 60_000, 10 * 60_000, 18)
        w += seria(t0 + 8 * GODZ + 20 * 60_000, self.TERAZ, 20 * 60_000, 30)
        s = self.werdykt(konf(od="2026-10-10T00:00:00Z"), w)
        self.assertEqual(len(s["podlania"]), 1)
        self.assertFalse(s["podlania"][0]["liczy"])
        self.assertIsNone(s["szczyt"])
        self.assertEqual(s["werdykt"], "nauka")

    def test_od_pare_minut_przed_wbiciem_nie_uczy_sie_wbicia(self):
        # Sonda w powietrzu (10), potem w wilgotnej ziemi (32). „od" podane z pamięci
        # o pół godziny za wcześnie dawało podlanie z przed=10 i szczytem 32 — cała
        # skala z wbicia, a nie z wody.
        wbicie = self.TERAZ - 30 * GODZ
        w = seria(self.TERAZ - 40 * GODZ, wbicie, 20 * 60_000, 10)
        w += seria(wbicie, self.TERAZ, 20 * 60_000, 32)
        s = self.werdykt(konf(od=rosliny.iso(wbicie - 30 * 60_000)), w)
        self.assertEqual(s["podlania"], [])
        self.assertEqual(s["werdykt"], "nauka")

    def test_pierwsze_podlanie_zaraz_po_starcie_nauki_uczy_skali(self):
        """9.10: sondy wbite 8:35, nauka od 9:35, podlanie ok. 9:40. Dawna wersja
        dostawała szereg obcięty do startu nauki: „przed" (2–6 godz. wcześniej) nie
        miało odczytów, więc pierwsze podlanie nigdy nie uczyło skali."""
        wbicie = self.TERAZ - 10 * GODZ
        podlanie = wbicie + 70 * 60_000
        w = seria(wbicie - 5 * GODZ, wbicie, 20 * 60_000, 10)              # sonda w powietrzu
        w += seria(wbicie, podlanie, 20 * 60_000, 17)                      # sucha ziemia
        w += seria(podlanie, self.TERAZ, 20 * 60_000, lambda k: 45 if k < 3 else 40)
        s = self.werdykt(konf(od=rosliny.iso(wbicie)), w)
        self.assertEqual(len(s["podlania"]), 1, "wbicie policzone jako podlanie albo podlanie zgubione")
        self.assertEqual(s["podlania"][0]["przed"], 17.0)
        self.assertTrue(s["podlania"][0]["liczy"])
        self.assertEqual(s["szczyt"], 40.0)
        self.assertNotEqual(s["werdykt"], "nauka")

    def test_przed_nie_bierze_odczytow_w_powietrzu(self):
        # zanurzenie azalii tuż po wbiciu: okna 2–6 godz. jeszcze nie ma, a w ostatnich
        # 2 godz. sonda leżała pół godziny w powietrzu
        t0 = ms("2026-10-09T06:35:00Z")
        pkt = [(t0, 30.0)]                                                       # w ziemi
        pkt += [(t0 + (40 + k * 10) * 60_000, 8.0) for k in range(3)]           # wyjęta
        pkt += [(t0 + (70 + k * 20) * 60_000, 55.0) for k in range(24)]
        p = rosliny.podlania(pkt, sucho=9.0)
        self.assertEqual(p[0]["przed"], 30.0, "bez filtra mediana wyszłaby 8 — powietrze")

    def test_podlanie_ziemi_suchej_jak_powietrze_tez_uczy(self):
        """Strażnik (przegląd 9.10): filtr odczytów „w powietrzu" wyrzucał też ziemię
        przeschniętą na wiór (fikus 13 przy „sucho" 10), więc rośliny podlewane na sucho
        zostawały w „nauce" na zawsze. Wersja z main sprzed filtra to przechodzi."""
        t0 = ms("2026-10-11T00:00:00Z")
        w = seria(t0, t0 + 8 * GODZ, GODZ, 13)
        w += seria(t0 + 8 * GODZ, self.TERAZ, 20 * 60_000, lambda k: 45 if k < 6 else 41)
        s = self.werdykt(konf(od="2026-10-10T00:00:00Z"), w)
        self.assertEqual(s["podlania"][0]["przed"], 13.0)
        self.assertTrue(s["podlania"][0]["liczy"])
        self.assertNotEqual(s["werdykt"], "nauka")

    def test_podlanie_wskazane_w_konfiguracji_nie_uczy(self):
        """9.10: woda stała w osłonce fikusa, sonda pokazywała 100 przez 5 godz. Takie
        podlanie dałoby zawyżony szczyt, a z nim „podlej" o wiele za wcześnie."""
        podlanie = self.TERAZ - 10 * GODZ
        w = seria(self.TERAZ - 20 * GODZ, podlanie, 20 * 60_000, 17)
        w += seria(podlanie, self.TERAZ, 20 * 60_000, 100)
        k = konf(od="2026-10-10T00:00:00Z",
                 pomin_podlania=[podlanie + 25 * 60_000])          # wpis o jedno wybudzenie obok
        s = self.werdykt(k, w)
        self.assertEqual(len(s["podlania"]), 1)
        self.assertFalse(s["podlania"][0]["liczy"])
        self.assertIsNone(s["szczyt"])
        self.assertEqual(s["werdykt"], "nauka")
        self.assertIn("pominięte", " ".join(s["uwagi"]))

    def test_szczyt_dopiero_6_godz_po_podlaniu(self):
        podlanie = self.TERAZ - 3 * GODZ
        w = seria(self.TERAZ - 20 * GODZ, podlanie, 20 * 60_000, 15)
        w += seria(podlanie, self.TERAZ, 20 * 60_000, lambda k: 60 if k < 4 else 50)
        s = self.werdykt(konf(od="2026-10-10T00:00:00Z"), w)
        self.assertIsNone(s["podlania"][0]["szczyt"], "ziemia jeszcze odcieka")
        self.assertEqual(s["werdykt"], "nauka")
        self.assertIn("6 godz.", " ".join(s["uwagi"]))

    def test_bez_sucho_to_nauka_a_nie_ok(self):
        s = self.werdykt(konf(od="2026-10-08T00:00:00Z", sucho=None), self.wiersze(12))
        self.assertEqual(s["werdykt"], "nauka")
        self.assertIn("sucho", " ".join(s["uwagi"]))

    def test_stara_gleba_przy_swiezej_baterii_to_czujnik(self):
        # bateria przychodzi, gleba od 20 godz. nie — „ok" z dawnej gleby byłoby zmyślone
        k = konf(od="2026-10-08T00:00:00Z")
        s = self.werdykt(k, self.wiersze(40, ostatni_ms=self.TERAZ - 20 * GODZ))
        self.assertEqual(s["werdykt"], "czujnik")
        self.assertIn("Gleba nie przychodzi", " ".join(s["uwagi"]))
        self.assertTrue(s["do_zgloszenia"])

    def test_nagly_spadek_do_powietrza_to_wyjeta_sonda(self):
        k = konf(od="2026-10-08T00:00:00Z")
        for minut, zglosic in ((180, True), (30, False)):
            with self.subTest(minut=minut):
                w = [x for x in self.wiersze(40, ostatni_ms=self.TERAZ - minut * 60_000 - GODZ)]
                w += seria(self.TERAZ - minut * 60_000, self.TERAZ, 10 * 60_000, 9)
                s = self.werdykt(k, w)
                self.assertEqual(s["werdykt"], "czujnik", "sonda w powietrzu to nie „podlej\"")
                self.assertIn("sonda wyjęta", " ".join(s["uwagi"]))
                # zanurzanie azalii trwa pół godziny — tego watchdog nie zgłasza
                self.assertEqual(bool(s["do_zgloszenia"]), zglosic)

    def test_test_w_wodzie_przed_wbiciem_to_nie_wyjeta_sonda(self):
        """Strażnik: przed „od" sonda nie jest w ziemi, więc powrót ze szklanki wody do
        powietrza nie może otworzyć zgłoszenia w watchdogu."""
        w = seria(self.TERAZ - 10 * GODZ, self.TERAZ - 4 * GODZ, 20 * 60_000, 10)
        w += seria(self.TERAZ - 4 * GODZ, self.TERAZ - 3.5 * GODZ, 10 * 60_000, 100)
        w += seria(self.TERAZ - int(3.5 * GODZ), self.TERAZ, 20 * 60_000, 10)
        for od in (None, rosliny.iso(self.TERAZ - GODZ)):
            with self.subTest(od=od):
                s = self.werdykt(konf(od=od), w)
                self.assertEqual(s["werdykt"], "nauka")
                self.assertEqual(s["do_zgloszenia"], [])

    def test_powolne_schniecie_do_sucha_to_podlej(self):
        """Strażnik: zupełnie sucha ziemia wygląda jak sonda w powietrzu, ale schła
        powoli — to dalej „podlej", nie „czujnik"."""
        k = konf(od="2026-10-08T00:00:00Z")
        w = self.wiersze(40)[:-2]
        w += seria(self.TERAZ - 40 * GODZ, self.TERAZ, GODZ, lambda n: 50 - n)
        w.append(wiersz(self.TERAZ - GODZ, "battery_state", "high"))
        self.assertEqual(self.werdykt(k, w)["werdykt"], "podlej")

    def test_nieskonczonosc_z_chmury_nie_trafia_do_stanu(self):
        w = self.wiersze(20) + [wiersz(self.TERAZ - 60_000, "humidity", "inf"),
                                wiersz(self.TERAZ - 60_000, "illumiance", "inf")]
        s = self.werdykt(konf(od="2026-10-08T00:00:00Z"), w)
        json.dumps(s, allow_nan=False)          # JSON.parse w przeglądarce nie zna Infinity
        self.assertEqual(s["R"], 0.25)

    def test_doby_swiatla_od_lokalnej_polnocy(self):
        # Stałe 100 lx przez cały miesiąc: każda pełna doba to 2400 lx·h. Dawniej pierwsza
        # doba zaczynała się o „teraz − 30 dni" i wyglądała na ciemną.
        w = self.wiersze(20) + seria(self.TERAZ - 32 * DOBA_MS, self.TERAZ, GODZ, 100, "illumiance")
        doby = self.werdykt(konf(), w)["swiatlo_dobowe"]
        self.assertEqual(doby[0]["lxh"], 2400)
        self.assertEqual(doby[0]["pokrycie"], 1.0)

    def test_szereg_i_swiatlo_maja_dlugosc_historii(self):
        s = self.werdykt(konf(), self.wiersze(20))
        self.assertEqual(len(s["swiatlo_dobowe"]), 30)
        self.assertEqual(len(s["szereg"]["gleba"]), 30 * 24 + 1)

    def test_pola_swiatla_i_gatunku_w_stanie(self):
        """Stan niesie wszystko, czego karta rośliny potrzebuje, żeby niczego nie liczyć:
        stałe gatunku, pełne doby, wczorajszą sumę i szczyt oraz ocenę światła."""
        w = self.wiersze(20) + seria(self.TERAZ - 32 * DOBA_MS, self.TERAZ, GODZ, 100, "illumiance")
        s = self.werdykt(konf(od="2026-10-08T00:00:00Z"), w)
        self.assertEqual((s["nazwa_pelna"], s["temp_zakres"], s["wilg_zakres"], s["swiatlo_za_duzo_lx"]),
                         ("Fikus 'Ginseng' (Ficus microcarpa)", [16, 24], [40, 70], None))
        # wbicie 8.10 (2:00 w Warszawie), teraz 12.10: pełne 9, 10 i 11.10
        self.assertEqual((s["swiatlo_pelne_doby"], s["swiatlo_wczoraj_lxh"], s["swiatlo_szczyt_lx_wczoraj"]),
                         (3, 2400, 100))
        self.assertEqual(s["swiatlo_ocena"], {"kierunek": "jasniej", "u": 0.12, "proc": 12,
                                              "doby": ["2026-10-09", "2026-10-10", "2026-10-11"], "szczyt_lx": 100})
        json.dumps(s, allow_nan=False)

    def test_bez_swiatla_i_przy_czujniku_ocena_pusta(self):
        s = self.werdykt(konf(od="2026-10-08T00:00:00Z"), self.wiersze(20))
        self.assertEqual((s["swiatlo_pelne_doby"], s["swiatlo_wczoraj_lxh"], s["swiatlo_szczyt_lx_wczoraj"],
                          s["swiatlo_ocena"]), (0, None, None, None))
        k = konf(od="2026-10-08T00:00:00Z")
        w = [x for x in self.wiersze(40, ostatni_ms=self.TERAZ - 20 * GODZ) if x["code"] != "battery_state"]
        w += seria(self.TERAZ - 32 * DOBA_MS, self.TERAZ - 20 * GODZ, GODZ, 100, "illumiance")
        s = self.werdykt(k, w)
        self.assertEqual(s["werdykt"], "czujnik")
        self.assertGreaterEqual(s["swiatlo_pelne_doby"], 3)
        self.assertIsNone(s["swiatlo_ocena"], "milczący czujnik — światło jest stare")


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
            self._przebieg(self.atrapa(), "salon")
        self.assertEqual(self.kod, 0)
        self.assertEqual(self.csv_pokoi(), {"salon"})
        stan = self.stan()
        self.assertIn("ZeroDivisionError", stan["blad"] or "")
        self.assertIn("ZeroDivisionError", " ".join(stan.get("alerty") or []), "watchdog nie zobaczy błędu")
        self.assertIn("pobrane_do", stan["urzadzenia"]["fikus"])

    def test_blad_toru_zostawia_kursory_i_alarmuje(self):
        """Dawniej błąd całego toru nadpisywał stan.json samym {updated, blad}: kursory
        przepadały (następny przebieg ciągnął logi od nowa), a watchdog bez `alerty`
        zamykał zgłoszenie z „tor roślin bez błędów"."""
        self.napisz_rosliny()
        atrapa = self.atrapa()
        self._przebieg(atrapa, "salon")
        with mock.patch.object(rosliny, "zwin", side_effect=RuntimeError("atrapa")):
            wyjscie = self._przebieg(atrapa, "salon")
        self.assertEqual(self.kod, 0)
        self.assertIn("błąd toru", wyjscie)
        stan = self.stan()
        self.assertIn("RuntimeError", " ".join(stan.get("alerty") or []))
        self.assertIn("pobrane_do", (stan.get("urzadzenia") or {}).get("fikus", {}))
        przed = len(atrapa.zapytania)
        self._przebieg(atrapa, "salon")
        logi = [prm for pth, prm in atrapa.zapytania[przed:] if pth == "/v1.0/devices/fikus/logs"]
        self.assertGreaterEqual(int(logi[0]["start_time"]), self.teraz - int(1.5 * GODZ))
        self.assertEqual(self.stan()["alerty"], [], "po naprawie alarm ma zniknąć")

    def test_literowka_w_konfiguracji_trafia_do_watchdoga(self):
        self.napisz_rosliny()
        self._przebieg(self.atrapa(), "salon")
        self.napisz_rosliny(json.dumps({"rosliny": [
            {"czujnik": "fikus", "nazwa": "Fikus", "gatunek": "fikus ", "sucho": 10, "kody": KODY_ROSLINY}]}))
        self._przebieg(self.atrapa(), "salon")
        stan = self.stan()
        self.assertIn("nieznany gatunek", " ".join(stan.get("alerty") or []))
        self.assertIn("fikus", stan.get("urzadzenia") or {}, "literówka skasowała kursory")

    def test_lista_zamiast_tekstu_w_konfiguracji(self):
        self.napisz_rosliny(json.dumps({"rosliny": [
            {"czujnik": ["fikus"], "nazwa": "Fikus", "gatunek": "fikus", "sucho": 10, "kody": KODY_ROSLINY}]}))
        self._przebieg(self.atrapa(), "salon")
        self.assertEqual(self.kod, 0)
        self.assertEqual(self.csv_pokoi(), {"salon"})
        self.assertTrue(self.stan().get("alerty"), "błąd konfiguracji nie dotarł do watchdoga")

    def test_pusta_lista_czysci_alerty(self):
        self.KATALOG.mkdir(parents=True)
        self.STAN.write_text(json.dumps({"alerty": ["**Fikus** — Czujnik milczy od 20 godz."]}),
                             encoding="utf-8")
        self.napisz_rosliny(json.dumps({"rosliny": []}))
        self._przebieg(self.atrapa(), "salon")
        self.assertEqual(self.stan().get("alerty"), [], "zgłoszenie o roślinie, której już nie ma")

    def test_pokoj_wpisany_jako_czujnik_zostaje_pokojem(self):
        # „pokoj" leży w rosliny.json tuż obok „czujnik" — pomyłka przy przepisywaniu
        # wyłączała pokój po cichu (kod 0, zero alertów)
        self.napisz_rosliny(json.dumps({"rosliny": [
            {"czujnik": "salon", "nazwa": "Fikus", "gatunek": "fikus", "sucho": 10, "kody": KODY_ROSLINY}]}))
        self._przebieg(self.atrapa(), "salon")
        self.assertEqual(self.kod, 0)
        self.assertEqual(self.csv_pokoi(), {"salon"})
        self.assertIn("czujnik pokojowy", " ".join(self.stan().get("alerty") or []))

    def test_pierwszy_przebieg_roslin_bierze_dobe(self):
        self.napisz_rosliny()
        atrapa = self.atrapa()
        self._przebieg(atrapa, "salon")
        logi = [prm for pth, prm in atrapa.zapytania if pth == "/v1.0/devices/fikus/logs"]
        self.assertGreaterEqual(int(logi[0]["start_time"]), self.teraz - 24 * GODZ - 60_000,
                                "historia sprzed wbicia sondy niczego nie uczy, a zjada budżet")

    def test_zawieszony_tor_roslin_nie_blokuje_zapisu_pokoi(self):
        """Wolność to nie wyjątek: bez limitu czasu zbyt wolny tor roślin dobijał do
        timeout-minutes i zadanie ginęło przed commitem pokoi."""
        self.napisz_rosliny()
        start = time.monotonic()
        with mock.patch.object(fetch, "LIMIT_ROSLIN_S", 0.5, create=True), \
                mock.patch.object(rosliny, "stan_rosliny", side_effect=lambda *a, **k: time.sleep(8)):
            self._przebieg(self.atrapa(), "salon")
        self.assertLess(time.monotonic() - start, 5)
        self.assertEqual(self.kod, 0)
        self.assertEqual(self.csv_pokoi(), {"salon"})
        self.assertIn("limit", self.stan()["blad"] or "")

    def test_absurdalny_rosliny_json_nie_wywraca_przebiegu(self):
        self.napisz_rosliny("[" * 100_000)            # RecursionError w json.loads
        self._przebieg(self.atrapa(), "salon")
        self.assertEqual(self.kod, 0)
        self.assertEqual(self.csv_pokoi(), {"salon"})

    def test_drgajaca_gleba_zwija_sie_w_csv(self):
        self.napisz_rosliny()
        atrapa = self.atrapa()
        atrapa.logi["fikus"] = [w for w in atrapa.logi["fikus"] if w["code"] != "humidity"]
        t, k = self.teraz - 3 * GODZ, 0
        while t < self.teraz - 60_000:
            atrapa.logi["fikus"].append({"code": "humidity", "value": 30 + k % 2, "event_time": t})
            t, k = t + 5 * 60_000, k + 1
        self._przebieg(atrapa, "salon")
        gleba = [r for r in self.csv_roslin() if r["code"] == "humidity"]
        self.assertLessEqual(len(gleba), 4, "drgnięcia 30↔31 zostały w CSV jak zmiany")

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

    def test_powiadomienia_licza_sie_w_kolektorze_na_sucho(self):
        """Etap 4: kolektor zapisuje decyzje reguł w data/rosliny/powiadomienia.json,
        a domyślny tryb to „na-sucho" — nic z tego przebiegu nie jest do wysłania."""
        self.napisz_rosliny()
        with mock.patch.dict(os.environ, {"PRZEBIEG": "123-1"}):
            self._przebieg(self.atrapa(), "salon")
        self.assertEqual(self.kod, 0)
        plik = self.KATALOG / "powiadomienia.json"
        self.assertTrue(plik.exists(), "kolektor nie zapisał decyzji powiadomień")
        dane = json.loads(plik.read_text(encoding="utf-8"))
        self.assertEqual(dane["tryb"], "na-sucho")
        self.assertFalse([w for w in dane["historia"] if w.get("na_sucho") is False],
                         "na sucho nic nie może być do wysłania")
        # plik jest publiczny — żadnych adresów subskrypcji
        self.assertNotIn("http", plik.read_text(encoding="utf-8"))

    def test_blad_regul_powiadomien_trafia_do_stanu_a_pokoje_ida_dalej(self):
        self.napisz_rosliny()
        with mock.patch.object(rosliny, "zaplanuj_powiadomienia", side_effect=KeyError("atrapa"), create=True):
            self._przebieg(self.atrapa(), "salon")
        self.assertEqual(self.kod, 0)
        self.assertEqual(self.csv_pokoi(), {"salon"})
        stan = self.stan()
        self.assertIn("powiadomienia", stan.get("blad") or "")
        self.assertTrue(stan.get("rosliny"), "błąd reguł nie może skasować stanu roślin")

    def test_ustawienia_telefonow_z_env_trafiaja_do_wpisow(self):
        """D11/D12: POWIADOMIENIA_ANDROID/IPHONE przez env kroku „Pobierz…". Bez ciszy na
        Androidzie i z ciszą iPhone'a od bieżącej godziny powitanie idzie tylko na Androida —
        niezależnie od pory, o której biegnie test. Treść zmiennych nie trafia do logu."""
        self.napisz_rosliny()
        godzina = datetime.now(WAWA).hour
        env = {"PRZEBIEG": "77-1", "POWIADOMIENIA": "wlaczone",
               "POWIADOMIENIA_ANDROID": '{"cisza": false}',
               "POWIADOMIENIA_IPHONE": json.dumps({"cisza": True, "od": godzina, "do": (godzina + 2) % 24})}
        with mock.patch.dict(os.environ, env):
            wyjscie = self._przebieg(self.atrapa(), "salon")
        self.assertEqual(self.kod, 0)
        dane = json.loads((self.KATALOG / "powiadomienia.json").read_text(encoding="utf-8"))
        self.assertEqual([(w["regula"], w["telefony"]) for w in dane["historia"] if w["przebieg"] == "77-1"],
                         [("wlaczone", ["android"])])
        self.assertNotIn('"cisza"', wyjscie)
        self.assertRegex(wyjscie, r"(?i)android:\s*własne")

    def test_zla_wartosc_ustawien_to_domyslne_i_kod_0(self):
        self.napisz_rosliny()
        env = {"PRZEBIEG": "78-1", "POWIADOMIENIA": "wlaczone", "POWIADOMIENIA_ANDROID": "{zepsute",
               "POWIADOMIENIA_IPHONE": "[1, 2]"}
        przed = datetime.now(WAWA)
        with mock.patch.dict(os.environ, env):
            wyjscie = self._przebieg(self.atrapa(), "salon")
        po = datetime.now(WAWA)
        self.assertEqual(self.kod, 0)
        self.assertNotIn("zepsute", wyjscie)
        self.assertRegex(wyjscie, r"(?i)iphone:\s*nieczytelne \(działają domyślne\)", "zła wartość musi być w logu nieczytelna, nie „własne”")
        dane = json.loads((self.KATALOG / "powiadomienia.json").read_text(encoding="utf-8"))
        cisza = telefony.w_ciszy(telefony.DOMYSLNE, przed)
        if cisza != telefony.w_ciszy(telefony.DOMYSLNE, po):
            self.skipTest("przebieg na granicy ciszy 21:00/8:00")
        wpisy = [w for w in dane["historia"] if w["przebieg"] == "78-1"]
        # domyślne obu telefonów: cisza 21–8 obu to wspólna noc — powitanie czeka do rana
        self.assertEqual([(w["regula"], w["telefony"]) for w in wpisy],
                         [] if cisza else [("wlaczone", ["android", "iphone"])])

    def test_bez_rosliny_json_nic_nie_powstaje(self):
        """Strażnik: dopóki nie ma konfiguracji, tor roślin nie dotyka data/."""
        self._przebieg(self.atrapa(), "salon")
        self.assertFalse(self.KATALOG.exists())


if __name__ == "__main__":
    unittest.main()
