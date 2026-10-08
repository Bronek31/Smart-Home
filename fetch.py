#!/usr/bin/env python3
"""
Pobiera historyczne odczyty czujników z chmury Tuya i dopisuje je do plików CSV.

Tuya trzyma 7 dni logów za darmo. Każde uruchomienie pobiera odcinek od chwili, do
której poprzednie pobrało wszystko (pole `pobrane_do` w manifeście), z kilkugodzinną
zakładką, i dokłada tylko te odczyty, których jeszcze nie ma. Nieudany albo pominięty
przebieg niczego nie kosztuje — kursor stoi, więc następny nadrobi zaległości, dopóki
nie minie 7 dni.

Użycie:
    python fetch.py --discover     # wypisz urządzenia widoczne na koncie
    python fetch.py                # dociągnij nowe odczyty (najdalej 7 dni wstecz) do data/
    python fetch.py --days 3       # bliższa granica wstecz
    python fetch.py --dry-run      # policz, ale nie zapisuj
"""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import hmac
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import requests

REGIONS = {
    "eu": "https://openapi.tuyaeu.com",
    "we": "https://openapi-weaz.tuyaeu.com",
    "us": "https://openapi.tuyaus.com",
    "ue": "https://openapi-ueaz.tuyaus.com",
    "in": "https://openapi.tuyain.com",
    "cn": "https://openapi.tuyacn.com",
}

DATA_DIR = Path("data")
MANIFEST = DATA_DIR / "index.json"
# Znane artefakty leżą obok fetch.py, nie w data/: to ręczna konfiguracja, nie odczyt.
# Ścieżka od pliku, nie od katalogu roboczego — test agregatów liczy je w kopii data/
# w katalogu tymczasowym i musi widzieć tę samą listę co kolektor.
ARTEFAKTY_PLIK = Path(__file__).resolve().parent / "artefakty.json"
DAILY = DATA_DIR / "dzienne.csv"
FIELDS = ["ts", "device_id", "code", "value"]
DAILY_FIELDS = ["date", "device_id", "code", "min", "avg", "max", "n"]
# Jak głęboko wstecz dociągamy stan urządzeń z włącznikiem. Raportują co kilka sekund,
# więc tydzień to tysiące stron logów; kolektor chodzi co godzinę, więc pół doby zapasu
# w zupełności starcza. Po dłuższym postoju historia włączeń sprzed tego okna przepada —
# odczyty czujników nie, bo one nadal lecą z pełnym oknem.
SPRZET_OKNO = 12 * 3600 * 1000
# Pobieranie przyrostowe czujników. Do 8.10.2026 każdy przebieg ciągnął pełne 7 dni:
# 29 zapytań na przebieg. Trial IoT Core to pakiet 0,20 USD na miesiąc kalendarzowy,
# a zapytania z runnerów GitHuba Tuya liczy jako zagraniczne (CLOUD_API_FOREIGN,
# 3,71 USD za milion), czyli ok. 54 000 zapytań. Panel 8.10 po południu: 6229 zapytań,
# 0,0231 USD — co do kilku zgodne z 29 × liczba przebiegów, więc liczy się każde
# zapytanie, także o token i nieudane. Przy 28 przebiegach na dobę to ok. 47% pakietu,
# a czujnik w doniczce, który raportuje co 10 minut, kosztowałby przy pełnym oknie
# ok. 50 stron na przebieg — więcej niż wszystkie pokoje razem. Teraz pytamy tylko
# o odcinek od `pobrane_do` z manifestu, cofnięty o zakładkę. Zakładka łapie odczyty,
# które dotarły do chmury z opóźnieniem; sześć godzin czujnika pokojowego to kilkanaście
# wierszy, czyli wciąż jedna strona.
ZAKLADKA_MS = 6 * 3600 * 1000
# Twardy sufit zapytań na urządzenie w jednym przebiegu. Gdy czujnik zaleje logi,
# dostaje tyle, a resztę dociąga następny przebieg — pakiet miesięczny jest wspólny.
BUDZET_URZADZENIA = 30
# Odcinka krótszego niż to już nie połowimy: ponad sto wpisów w dwie minuty to zalew,
# którego i tak nie da się przeczytać w całości, więc bierzemy, co przyszło.
NAJKROTSZY_ODCINEK_MS = 2 * 60 * 1000
OUTDOOR_ID = "zewnatrz"
OUTDOOR_URL = "https://api.open-meteo.com/v1/forecast"
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER = DATA_DIR / "pogoda.json"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
RATE_LIMIT_CODES = {40000309, 1104, 2009}
TEMP_UNITS = {"°c", "℃", "c", "°f", "℉", "f"}
HUM_UNITS = {"%", "％"}
KNOWN_TEMP = {"va_temperature", "temp_current", "temper_value"}
KNOWN_HUM = {"va_humidity", "humidity_value", "humidity_current"}
NOT_A_SENSOR = (
    "colour", "color", "bright", "work_mode", "scene", "countdown",
    "set", "correct", "calibration", "alarm", "upper", "lower", "unit_convert",
)


def classify(code: str, unit: str) -> str | None:
    low, u = code.lower(), (unit or "").strip().lower()
    if any(bad in low for bad in NOT_A_SENSOR):
        return None
    if low == "switch" or (low.startswith("switch_") and low[7:].isdigit()):
        return "power"          # włącznik urządzenia: klimatyzator, oczyszczacz, grzejnik
    if "battery" in low:
        return "battery"
    if low in KNOWN_TEMP or ("temp" in low and u in TEMP_UNITS):
        return "temp"
    if low in KNOWN_HUM or ("humi" in low and u in HUM_UNITS):
        return "hum"
    return None


class TuyaError(RuntimeError):
    pass


class Tuya:
    def __init__(self, client_id: str, secret: str, region: str):
        if region not in REGIONS:
            raise TuyaError(
                f"Nieznany region {region!r}. Dozwolone: {', '.join(REGIONS)}"
            )
        self.client_id = client_id
        self.secret = secret
        self.base = REGIONS[region]
        self.token = ""
        self.token_expires = 0.0
        self.session = requests.Session()
        self.min_gap = float(os.environ.get("TUYA_MIN_GAP", "1.2"))
        self.last_call = 0.0
        self.log_api = None
        # Każde zapytanie HTTP, także o token i ponowione przy limicie — tyle zjada
        # z miesięcznego limitu triala. Wypisywane na końcu przebiegu.
        self.zapytan = 0

    def _headers(self, method: str, path: str, with_token: bool) -> dict:
        t = str(int(time.time() * 1000))
        string_to_sign = "\n".join([method, EMPTY_SHA256, "", path])
        token = self.token if with_token else ""
        message = self.client_id + token + t + string_to_sign
        sign = hmac.new(
            self.secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest().upper()
        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": t,
            "sign_method": "HMAC-SHA256",
        }
        if with_token:
            headers["access_token"] = self.token
        return headers

    def _refresh_token(self) -> None:
        path = "/v1.0/token?grant_type=1"
        self.zapytan += 1
        resp = self.session.get(
            self.base + path, headers=self._headers("GET", path, False), timeout=30
        )
        data = resp.json()
        if not data.get("success"):
            raise TuyaError(explain(data))
        result = data["result"]
        self.token = result["access_token"]
        self.token_expires = time.time() + int(result.get("expire_time", 7200))

    def _throttle(self) -> None:
        wait = self.min_gap - (time.monotonic() - self.last_call)
        if wait > 0:
            time.sleep(wait)
        self.last_call = time.monotonic()

    def get(self, path: str, params: dict | None = None, _retry: bool = True) -> dict:
        if not self.token or time.time() > self.token_expires - 60:
            self._refresh_token()
        full = path
        if params:
            query = "&".join(
                f"{k}={params[k]}" for k in sorted(params) if params[k] is not None
            )
            full = f"{path}?{query}"
        for attempt in range(5):
            self._throttle()
            self.zapytan += 1
            resp = self.session.get(
                self.base + full, headers=self._headers("GET", full, True), timeout=30
            )
            data = resp.json()
            if data.get("success"):
                return data
            if data.get("code") in RATE_LIMIT_CODES:
                pause = min(3 * (2 ** attempt), 30)
                print(f"  limit zapytań Tuya, czekam {pause} s…", flush=True)
                time.sleep(pause)
                continue
            if data.get("code") in (1010, 1013) and _retry:
                self.token = ""
                return self.get(path, params, _retry=False)
            return data
        return data


def explain(data: dict) -> str:
    code = data.get("code")
    msg = data.get("msg", "brak treści błędu")
    hints = {
        1004: "Zły podpis. Sprawdź, czy Access Secret jest przepisany w całości.",
        1106: "Brak uprawnień. Czy urządzenie na pewno należy do podpiętego konta?",
        1114: "Zły region. Projekt jest w innym data center, niż podałeś w TUYA_REGION.",
        2007: "Zły region albo Access ID nie pasuje do data center.",
        28841002: (
            "Wygasł trial IoT Core. Wejdź na iot.tuya.com → Cloud → Development, "
            "otwórz projekt i złóż wniosek o przedłużenie. Zatwierdzają w 1-2 dni robocze."
        ),
        28841004: (
            "Wyczerpany miesięczny pakiet triala IoT Core (0,20 USD). Zużycie widać na "
            "iot.tuya.com → IoT Core → My Subscriptions; pakiet odnawia się 1. dnia miesiąca. "
            "Do tego czasu kolektor stoi, a logi starsze niż 7 dni przepadają."
        ),
    }
    hint = hints.get(code, "")
    return f"Tuya odrzuciła zapytanie (kod {code}): {msg}. {hint}".strip()


def list_devices(client: Tuya) -> list[dict]:
    devices, last_key = [], None
    while True:
        params = {"page_size": 100}
        if last_key:
            params["last_row_key"] = last_key
        data = client.get("/v1.0/iot-01/associated-users/devices", params)
        if not data.get("success"):
            raise TuyaError(explain(data))
        result = data.get("result") or {}
        devices.extend(result.get("devices", []))
        if not result.get("has_more"):
            break
        last_key = result.get("last_row_key")
        if not last_key:
            break
    return devices


def specyfikacja(client: Tuya, device_id: str) -> dict:
    """Surowa specyfikacja urządzenia (pola `status` i `functions`); {} przy odmowie."""
    data = client.get(f"/v1.0/devices/{device_id}/specifications")
    if not data.get("success"):
        return {}
    wynik = data.get("result")
    return wynik if isinstance(wynik, dict) else {}


def _wartosci(item: dict) -> dict:
    """Pole `values` ze specyfikacji jako słownik. Tuya podaje je jako tekst JSON,
    czasem jako gotowy obiekt; wszystko inne (lista, liczba, śmieci) to pusty słownik."""
    wartosci = item.get("values")
    if isinstance(wartosci, str):
        try:
            wartosci = json.loads(wartosci or "{}")
        except (ValueError, TypeError):
            wartosci = {}
    return wartosci if isinstance(wartosci, dict) else {}


def describe_codes(client: Tuya, device_id: str, spec: dict | None = None) -> dict:
    pola = (specyfikacja(client, device_id) if spec is None else spec).get("status") or []
    codes = {}
    for item in pola:
        if not isinstance(item, dict):
            continue
        code = item.get("code", "")
        spec = _wartosci(item)
        unit = spec.get("unit") or ""
        kind = classify(code, unit)
        if kind is None:
            continue
        codes[code] = {
            "kind": kind,
            "unit": unit or {"temp": "°C", "hum": "%", "battery": "%"}.get(kind, ""),
            "scale": int(spec.get("scale", 0) or 0),
        }
    return codes


def all_codes(client: Tuya, device_id: str, spec: dict | None = None,
              sekcja: str = "status") -> list[tuple[str, str, str]]:
    """Wszystkie pola urządzenia, także te, których kolektor nie zbiera.

    Potrzebne przy --discover: żeby podpiąć cokolwiek poza czujnikiem klimatu —
    klimatyzator, czajnik, kontaktron, czujnik w doniczce — trzeba najpierw zobaczyć,
    jak nazywają się jego pola, jakiego są typu i w jakiej skali przychodzą.
    `sekcja` "functions" to pola do ustawiania (kalibracja, odstęp próbkowania).
    """
    pola = (specyfikacja(client, device_id) if spec is None else spec).get(sekcja) or []
    out = []
    for item in pola:
        if not isinstance(item, dict):
            continue
        code = item.get("code", "")
        spec = _wartosci(item)
        opis = str(spec.get("unit") or spec.get("range") or "")
        if "min" in spec and "max" in spec:
            opis = f"{opis} {spec['min']}…{spec['max']}".strip()
        if "scale" in spec:
            opis = f"{opis} scale={spec['scale']}".strip()
        out.append((code, item.get("type", "?"), opis))
    return out


def tempo_wpisow(client: Tuya, device_id: str, teraz_ms: int, okno_ms: int = 3600 * 1000,
                 strony: int = 3) -> str:
    """Ile wpisów zrobiło urządzenie w ostatnim oknie — do --discover.

    Zigbee2MQTT ostrzega, że czujnik w doniczce C3007 potrafi wysyłać ok. 1 komunikat na
    sekundę. Zanim kolektor zacznie go zbierać, trzeba wiedzieć, ile stron logów
    kosztowałby na przebieg. Najwyżej `strony` zapytań, żeby sam pomiar nie zjadł pakietu.
    """
    logi, stan = _strony(client, "v1", device_id, teraz_ms - okno_ms, teraz_ms, strony)
    if logi is None:
        return "logi niedostępne (Tuya odmówiła)"
    if not logi:
        return f"0 wpisów w ostatnich {okno_ms // 60000} min"
    kody: dict[str, int] = {}
    for e in logi:
        kody[e.get("code", "?")] = kody.get(e.get("code", "?"), 0) + 1
    rozbicie = ", ".join(f"{k}: {n}" for k, n in sorted(kody.items()))
    if stan == "limit":
        czasy = [int(e["event_time"]) for e in logi if e.get("event_time") is not None]
        rozpietosc = max(1, (max(czasy) - min(czasy)) // 60000) if czasy else 0
        return (f"ponad {len(logi)} wpisów — tyle zmieściło się w {rozpietosc} min; "
                f"ZALEW, kolektor nie powinien czytać jego logów ({rozbicie})")
    na_dobe = len(logi) * (24 * 3600 * 1000 // okno_ms)
    return (f"{len(logi)} wpisów w ostatnich {okno_ms // 60000} min, ok. {na_dobe} na dobę, "
            f"ok. {na_dobe * 7 // 100 + 1} stron na tydzień ({rozbicie})")


def fetch_logs(client: Tuya, device_id: str, start_ms: int, end_ms: int) -> list[dict]:
    """Całe okno naraz, do 300 stron. Zostało dla urządzeń z włącznikiem, które mają
    własne, dwunastogodzinne okno; czujniki idą przez pobierz_przyrostowo()."""
    rows, stan = _strony_z_wyborem(client, device_id, start_ms, end_ms, 300)
    if rows is None:
        raise TuyaError(
            f"Endpoint logów ({client.log_api or 'v1 ani v2'}) odmówił dla urządzenia {device_id}."
        )
    if stan == "blad":
        print(f"  uwaga: {device_id} — błąd w trakcie stronicowania, biorę to, co przyszło", flush=True)
    return rows


def _strony_z_wyborem(client, device_id, start_ms, end_ms, limit):
    """Logi przez v1, a v2 tylko jako zapas dla sprzętu (fetch_logs).

    Kolektor czyta v1 od początku: dawna próba v2 przed v1 kosztowała zapytanie w każdym
    przebiegu (v2 wymaga parametru `codes`, którego nie wysyłamy), co potwierdził panel
    Tuya — 6229 zapytań to dokładnie 29, a nie 28, na przebieg. Zamek na v2 nie powstaje
    nigdy: gdyby v2 odpowiedziało „sukces, zero wpisów", pobieranie przyrostowe uznałoby
    okno za domknięte i przesunęło kursor ponad wszystko, czego nie przeczytało.
    """
    rows, stan = _strony(client, "v1", device_id, start_ms, end_ms, limit)
    if rows is not None:
        client.log_api = "v1"
        return rows, stan
    if client.log_api == "v1":
        return None, "blad"          # v1 działa w tym przebiegu, odmówiło tylko temu urządzeniu
    return _strony(client, "v2", device_id, start_ms, end_ms, limit)


def _strony(client, version, device_id, start_ms, end_ms, limit) -> tuple[list[dict] | None, str]:
    """Stronicuje jedno okno. Stan: „komplet" — przyszło wszystko; „limit" — po `limit`
    stronach były jeszcze następne; „blad" — Tuya odmówiła w trakcie. Przy odmowie na
    pierwszej stronie zamiast listy jest None."""
    out, cursor = [], None
    for _ in range(limit):
        params = {"start_time": start_ms, "end_time": end_ms, "size": 100}
        if version == "v2":
            path = f"/v2.0/cloud/thing/{device_id}/report-logs"
            if cursor:
                params["last_row_key"] = cursor
        else:
            path = f"/v1.0/devices/{device_id}/logs"
            params["type"] = 7
            if cursor:
                params["start_row_key"] = cursor
        data = client.get(path, params)
        if not data.get("success"):
            if out:
                print(f"  uwaga: {explain(data)}", flush=True)
                return out, "blad"
            return None, "blad"
        result = data.get("result") or {}
        out.extend(result.get("logs", []))
        if not (result.get("has_more") or result.get("has_next")):
            return out, "komplet"
        cursor = result.get("last_row_key") or result.get("next_row_key")
        if not cursor:
            # Tuya mówi „jest dalej", ale nie mówi skąd. Dawniej liczone jako komplet;
            # przy pobieraniu przyrostowym to by przesunęło kursor ponad niepobrane wpisy.
            return out, "limit"
    return out, "limit"


def pobierz_przyrostowo(client, device_id: str, od_ms: int, do_ms: int,
                        pewne_do: int | None = None,
                        budzet: int | None = None) -> tuple[list[dict], int | None]:
    """Logi z okna [od_ms, do_ms] i chwila, do której pobrano je na pewno w całości.

    `pewne_do` to kursor z poprzedniego przebiegu: wszystko sprzed niego już leży
    w CSV, a odcinek [od_ms, pewne_do] to tylko zakładka na spóźnione odczyty.

    Kolejność, w jakiej Tuya oddaje wpisy (od najstarszego czy od najnowszego), nie jest
    nigdzie opisana, a od niej zależy, która część okna przepada, gdy skończą się strony.
    Dlatego okno czytamy odcinkami, od najstarszego, po jednej stronie (100 wpisów) na
    zapytanie — tyle samo wpisów na zapytanie co przy zwykłym stronicowaniu:

    - odcinek zmieścił się na stronie: domknięty, następny może być dwa razy dłuższy;
    - nie zmieścił się, a sięga przed `pewne_do`: najpierw sama zakładka; jeśli i ona
      się nie mieści, porzucamy ją i idziemy od kursora — przy takim zalewie nie stać
      nas na sprawdzanie tego, co już mamy, a bez tego przebieg mógłby nie dojść dalej
      niż do kursora, ani razu;
    - nie zmieścił się, a wpisy przyszły rosnąco w czasie: wszystko sprzed najpóźniejszego
      z nich jest pobrane, więc domykamy do niego i czytamy dalej od tej chwili;
    - nie zmieścił się, a wpisy przyszły od najnowszego: ten sam początek, odcinek
      o połowę krótszy. Strona, która nie domknęła odcinka, kosztuje jedno zapytanie,
      a nie dziesięć — dlatego jedna strona, a nie pełne stronicowanie.

    Kursor dochodzi tylko do końca ostatniego odcinka, który przyszedł w całości i bez
    przerwy od początku — nigdy do „najnowszego widzianego wpisu". Wpisy z odcinków
    niedomkniętych też oddajemy: są prawdziwe, a merge() i tak odrzuca powtórki.

    Zwraca (logi, domknięte_do). domknięte_do to None, gdy nie udało się domknąć
    niczego — wtedy kursor zostaje, gdzie był. Odmowa Tuya albo błąd sieci na pierwszym
    zapytaniu to wyjątek, tak jak wcześniej w fetch_logs(); późniejsze kończą pobieranie
    tego urządzenia z tym, co już przyszło.
    """
    budzet = BUDZET_URZADZENIA if budzet is None else budzet
    if od_ms >= do_ms:
        return [], None
    logi: list[dict] = []
    domkniete = None
    pozycja, dlugosc = od_ms, do_ms - od_ms
    poczatek = client.zapytan
    while pozycja < do_ms:
        if client.zapytan - poczatek >= budzet:
            print(f"  {device_id}: wykorzystane {budzet} zapytań na ten przebieg, "
                  f"resztę od {iso(pozycja)} dociągnie następny", flush=True)
            break
        koniec = min(do_ms, pozycja + dlugosc)
        try:
            porcja, stan = _strony(client, "v1", device_id, pozycja, koniec, 1)
        except requests.RequestException as err:
            if not logi and domkniete is None:
                raise
            # To, co już przyszło, zostaje razem z kursorem — następny przebieg zacznie
            # od miejsca, w którym sieć się urwała, a nie od początku okna.
            print(f"  {device_id}: sieć urwała się w odcinku od {iso(pozycja)} "
                  f"({type(err).__name__}), kursor zostaje", flush=True)
            break
        if porcja is None:
            if not logi and domkniete is None:
                raise TuyaError(f"Endpoint logów (v1) odmówił dla urządzenia {device_id}.")
            print(f"  {device_id}: odmowa w odcinku od {iso(pozycja)}, kursor zostaje", flush=True)
            break
        client.log_api = "v1"
        logi.extend(porcja)
        if stan == "komplet":
            pozycja = domkniete = koniec
            dlugosc *= 2
            continue
        czasy = [int(e["event_time"]) for e in porcja if e.get("event_time") is not None]
        # „Rosnąco" tylko wtedy, gdy strona naprawdę obejmuje różne chwile: jeden wiersz
        # albo strona z jednym znacznikiem czasu pasują do obu kolejności, a przy
        # kolejności od najnowszego przeskok do czasy[-1] zgubiłby starsze wpisy.
        rosnaco = len(czasy) > 1 and czasy[0] < czasy[-1] and czasy == sorted(czasy)
        if pewne_do and pozycja < pewne_do:
            if koniec > pewne_do:
                # Najpierw sama zakładka, osobno — po długiej przerwie to nowa część okna
                # się nie mieści, a spóźnione odczyty sprzed kursora nadal da się złapać.
                dlugosc = pewne_do - pozycja
            else:
                print(f"  {device_id}: sama zakładka ma ponad 100 wpisów — pomijam ją, "
                      f"idę od kursora {iso(pewne_do)}", flush=True)
                pozycja = domkniete = pewne_do
        elif rosnaco and pozycja < czasy[-1] - 1 < koniec:
            # Od milisekundy przed ostatnim wpisem, a nie od niego: nikt nie sprawdził,
            # czy start_time u Tuya jest domknięty. Strona po 100 wpisów kończy się
            # zwykle w środku trójki odczytów z jednej chwili, więc przy otwartym
            # początku reszta tej trójki by przepadła.
            pozycja = domkniete = czasy[-1] - 1
        elif koniec - pozycja > NAJKROTSZY_ODCINEK_MS:
            dlugosc = max(NAJKROTSZY_ODCINEK_MS, (koniec - pozycja) // 2)
        else:
            # Ponad 100 wpisów w dwie minuty. Krótszego odcinka nie ma sensu ciąć, więc
            # tu jedyny raz idziemy za `next_row_key` — kilka stron domyka takie okno
            # w obu kolejnościach. Co się nie zmieści, przepada, i mówimy to w logu.
            reszta, stan = _strony(client, "v1", device_id, pozycja, koniec, 5)
            logi.extend(reszta or [])
            if stan != "komplet":
                print(f"  {device_id}: zalew — ponad 500 wpisów w {(koniec - pozycja) // 1000} s "
                      f"od {iso(pozycja)}, reszta z tego odcinka przepada", flush=True)
            pozycja = domkniete = koniec
    return logi, domkniete


def parse_since(text: str) -> int:
    text = (text or "").strip()
    if not text:
        return 0
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        raise TuyaError(
            f"TUYA_SINCE ma zły format: {text!r}.\n"
            "Użyj np. 2026-08-13 albo 2026-08-12T21:30+02:00 (czas polski latem)."
        )
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_month(month: str) -> list[dict]:
    path = DATA_DIR / f"{month}.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_month(month: str, rows: list[dict]) -> None:
    rows.sort(key=lambda r: (r["ts"], r["device_id"], r["code"]))
    path = DATA_DIR / f"{month}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def purge_before(since_ms: int) -> int:
    """Usuwa z istniejących CSV wszystkie rekordy wcześniejsze niż TUYA_SINCE."""
    if not since_ms:
        return 0
    removed = 0
    for path in DATA_DIR.glob("[0-9]*.csv"):   # tylko pliki miesięczne — dzienne.csv ma inne kolumny
        month = path.stem
        rows = load_month(month)
        if not rows:
            continue
        kept = []
        for row in rows:
            try:
                when = int(datetime.fromisoformat(row["ts"].replace("Z", "+00:00")).timestamp() * 1000)
            except (KeyError, ValueError, TypeError):
                kept.append(row)
                continue
            if when < since_ms:
                removed += 1
            else:
                kept.append(row)
        if len(kept) != len(rows):
            save_month(month, kept)
    return removed


def merge(new_rows: list[dict]) -> int:
    """Dokłada odczyty do plików miesięcznych, pomijając te już zapisane."""
    by_month: dict[str, list[dict]] = {}
    for row in new_rows:
        by_month.setdefault(row["ts"][:7], []).append(row)
    added = 0
    for month, incoming in by_month.items():
        existing = load_month(month)
        seen = {(r["ts"], r["device_id"], r["code"]) for r in existing}
        fresh = []
        for row in incoming:
            key = (row["ts"], row["device_id"], row["code"])
            if key in seen:
                continue
            seen.add(key)
            fresh.append(row)
        if fresh:
            save_month(month, existing + fresh)
            added += len(fresh)
    return added


def collapse_power(devices: dict) -> int:
    """Zostawia z włączników wyłącznie zmiany stanu.

    Klimatyzator raportuje swój włącznik co 10 sekund, także wtedy, gdy nic się nie
    dzieje — z pierwszego przebiegu przyszło 2143 wiersze, z czego 3 niosły
    informację. Do historii wystarczają momenty przełączenia; reszta to plik, który
    przeglądarka musi za każdym razem pobrać i przemielić.

    Przebieg jest globalny i idempotentny, więc czyści też to, co już leży w repo.
    """
    power = {key for key, kind in code_kinds(devices).items() if kind == "power"}
    if not power:
        return 0
    ostatnia: dict[tuple, str] = {}
    removed = 0
    for month in sorted(p.stem for p in DATA_DIR.glob("[0-9]*.csv")):
        rows = load_month(month)
        if not rows:
            continue
        kept = []
        for row in sorted(rows, key=lambda r: (r["ts"], r["device_id"], r["code"])):
            key = (row["device_id"], row["code"])
            if key in power:
                if ostatnia.get(key) == row["value"]:
                    removed += 1
                    continue
                ostatnia[key] = row["value"]
            kept.append(row)
        if len(kept) != len(rows):
            save_month(month, kept)
    return removed


def fetch_outdoor(days: int) -> tuple[list[dict], dict | None]:
    """Dociąga godzinową temperaturę i wilgotność z Open-Meteo (bez klucza API).

    Zwraca odczyty w tym samym formacie co czujniki, więc dalej płyną tym samym
    torem: trafiają do CSV, do agregatów i na wykres jako dodatkowa krzywa.
    """
    lat = os.environ.get("OUTDOOR_LAT", "").strip()
    lon = os.environ.get("OUTDOOR_LON", "").strip()
    if not lat or not lon:
        return [], None
    name = os.environ.get("OUTDOOR_NAME", "").strip() or "Na zewnątrz"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m",
        "past_days": max(1, min(days, 92)),
        "forecast_days": 1,
        "timezone": "UTC",
    }
    try:
        resp = requests.get(OUTDOOR_URL, params=params, timeout=30)
        block = (resp.json() or {}).get("hourly") or {}
    except (requests.RequestException, ValueError) as err:
        print(f"Pogoda: pominięta — {err}", flush=True)
        return [], None

    stamps = block.get("time") or []
    now = datetime.now(timezone.utc)
    rows = []
    pairs = (("temperature_2m", "va_temperature"), ("relative_humidity_2m", "va_humidity"))
    for source, code in pairs:
        values = block.get(source) or []
        for stamp, value in zip(stamps, values):
            if value is None:
                continue
            try:
                when = datetime.fromisoformat(stamp).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if when > now:          # prognoza na resztę doby nas nie interesuje
                continue
            rows.append({
                "ts": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "device_id": OUTDOOR_ID,
                "code": code,
                "value": f"{float(value):g}",
            })
    entry = {
        "name": name,
        "external": True,
        "codes": {
            "va_temperature": {"kind": "temp", "unit": "°C", "scale": 0},
            "va_humidity": {"kind": "hum", "unit": "%", "scale": 0},
        },
    }
    print(f"{name}: {len(rows)} odczytów pogodowych", flush=True)
    return rows, entry


# Progi trzymamy przy rodzaju odczytu, nie przy kodzie DP: ten sam czujnik u innego
# producenta zgłasza temperaturę jako temp_current albo temper_value. Frontend
# odszumia dokładnie tak samo i też po rodzaju — obie strony muszą się zgadzać,
# inaczej widok "całość" pokazywałby skok, którego widok 7-dniowy nie pokazuje.
SPIKE_JUMP = {"temp": 1.5, "hum": 8.0}
SPIKE_BACK = {"temp": 1.0, "hum": 5.0}
SPIKE_RISE = 15 * 60          # okno, w którym mierzymy wzrost — musi zgadzać się ze SPIKE.rise
                              # w index.html. Było 12 min; przy narastaniu przez kilkanaście
                              # minut (czujnik w dłoni) baza wypadała już wewnątrz wzrostu
                              # i skok chował się pod progiem.
SPIKE_MAX = 90 * 60           # i w którym musi wrócić do poziomu wyjściowego


def drop_spikes(points: list[tuple[float, float]], kind: str | None) -> set[int]:
    """Znajduje wyskoki: nagły wzrost, po którym wartość wraca tam, skąd wyszła.

    Trwała zmiana (włączony grzejnik, otwarte okno) nie wraca, więc zostaje.
    Dzięki temu dobowe min/max nie biorą się z chwili, w której ktoś wziął
    czujnik do ręki.

    Wyskok zaczyna się od spokojnego poziomu. 27.09.2026 farelka w łazience
    grzała przez pół godziny, 20,5 → 26,9 °C, i wracała przez dwie. Okno SPIKE_RISE
    przesuwało bazę w górę razem z rampą, więc w połowie wzrostu baza stała już
    na 21,7 °C, a do niej ogon „wracał" w 90 minut — i filtr wyciął środek
    prawdziwego grzania, zostawiając garb o złej godzinie. Baza, przed którą
    wartość już szła, leży w środku rampy, a nie przed skokiem.
    """
    jump, back = SPIKE_JUMP.get(kind), SPIKE_BACK.get(kind)
    if jump is None or len(points) < 3:
        return set()
    bad: set[int] = set()
    i = 1
    while i < len(points):
        k = i - 1
        while k > 0 and points[i][0] - points[k - 1][0] <= SPIKE_RISE:
            k -= 1
        base = points[k][1]
        spokojnie = True
        m = k - 1
        while m >= 0 and points[k][0] - points[m][0] <= SPIKE_RISE:
            if abs(points[m][1] - base) >= back:
                spokojnie = False
                break
            m -= 1
        if spokojnie and abs(points[i][1] - base) >= jump:
            j = i
            while (j < len(points) and points[j][0] - points[k][0] <= SPIKE_MAX
                   and abs(points[j][1] - base) >= back):
                j += 1
            if j < len(points) and points[j][0] - points[k][0] <= SPIKE_MAX:
                start = k + 1
                while start < j and abs(points[start][1] - base) < back:
                    start += 1
                bad.update(range(start, j))
                i = j + 1
                continue
        i += 1
    return bad


# Ile godzin prognozy trzymamy w pogoda.json. Doba z okładem wystarcza, żeby wskazać
# najbliższe okno na wietrzenie, a plik zostaje mały — przeglądarka ciągnie go co wejście.
PROGNOZA_GODZIN = 36


def strefa_prognozy(zone: str, offset_s: int):
    """Strefa, w której Open-Meteo oddaje znaczniki prognozy.

    Musi to być prawdziwa strefa, a nie stałe przesunięcie: prognoza sięga 36 godzin
    naprzód, więc dwa razy w roku przechodzi przez zmianę czasu i połowa okna ma inne
    przesunięcie niż druga. Stałe przesunięcie zabiera stąd całą wiedzę o tym, kiedy
    zegar się przestawia.
    """
    try:
        return ZoneInfo(zone)
    except Exception:
        print(f"Nieznana strefa {zone!r}, prognoza przeliczana stałym przesunięciem.", flush=True)
        return timezone(timedelta(seconds=offset_s))


def trim_hourly(block: dict, tz) -> dict:
    """Przycina prognozę godzinową do najbliższej doby i przestawia czas na UTC.

    Open-Meteo zwraca znaczniki w strefie, o którą prosiliśmy, i bez oznaczenia strefy
    ("2026-08-15T08:00"). Przeglądarka wzięłaby je za czas swojego zegara, więc telefon
    ustawiony na inną strefę pokazywałby wietrzenie o złej godzinie. Przeliczamy tutaj,
    bo tutaj wiemy, o jaką strefę prosiliśmy, i zapisujemy tak samo jak każdy inny
    znacznik w repozytorium.

    Przeliczamy każdą godzinę osobno, w prawdziwej strefie. Wcześniej szło to jednym
    przesunięciem wziętym z chwili zapytania i przy zmianie czasu 30 z 37 godzin lądowało
    o godzinę za wcześnie — przez półtorej doby dwa razy w roku rada „najlepiej wietrzyć
    5:00–8:00" wskazywała złą porę.

    Jesienią druga w nocy wypada dwa razy i sam znacznik jej nie rozróżnia. Open-Meteo
    oddaje godziny po kolei, więc drugie wystąpienie poznajemy po tym, że czas nie
    posunął się naprzód — i dopiero wtedy bierzemy tę po przestawieniu zegara (fold=1).
    """
    stamps = block.get("time") or []
    if not stamps:
        return {}
    pola = [k for k in block if k != "time"]
    teraz = time.time()
    out: dict[str, list] = {"time": []}
    for pole in pola:
        out[pole] = []
    poprzednio = None
    for index, stamp in enumerate(stamps):
        try:
            naiwny = datetime.fromisoformat(stamp)
        except ValueError:
            continue
        kiedy = naiwny.replace(tzinfo=tz).timestamp()
        if poprzednio is not None and kiedy <= poprzednio:
            kiedy = naiwny.replace(tzinfo=tz, fold=1).timestamp()
        poprzednio = kiedy
        # godzina, w której właśnie jesteśmy, jeszcze się liczy — stąd zapas 1 godz. wstecz
        if kiedy < teraz - 3600 or kiedy > teraz + PROGNOZA_GODZIN * 3600:
            continue
        out["time"].append(iso(int(kiedy * 1000)))
        for pole in pola:
            wartosci = block.get(pole) or []
            out[pole].append(wartosci[index] if index < len(wartosci) else None)
    return out


def location_of(data: dict, lat: str, lon: str) -> dict | None:
    """Współrzędne, z których strona liczy wschód i zachód słońca.

    Bierzemy punkt siatki oddany przez Open-Meteo, bo to jego dotyczy prognoza;
    gdyby go w odpowiedzi zabrakło, zostaje to, o co pytaliśmy. Bez współrzędnych
    strona po prostu nie rysuje łuku doby — nic poza tym się nie psuje.
    """
    try:
        return {"lat": float(data.get("latitude", lat)), "lon": float(data.get("longitude", lon))}
    except (TypeError, ValueError):
        return None


def fetch_weather() -> dict | None:
    """Migawka pogodowa: teraz + prognoza na 3 dni + jakość powietrza.

    To nie jest historia, tylko stan na chwilę obecną, więc ląduje w osobnym
    pliku nadpisywanym co przebieg, a nie w CSV z odczytami.
    """
    lat = os.environ.get("OUTDOOR_LAT", "").strip()
    lon = os.environ.get("OUTDOOR_LON", "").strip()
    if not lat or not lon:
        return None
    zone = os.environ.get("TZ_LOCAL", "Europe/Warsaw")
    snapshot = {"updated": iso(int(time.time() * 1000))}
    try:
        resp = requests.get(OUTDOOR_URL, params={
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                     "precipitation_probability_max,precipitation_sum",
            # godzinowa prognoza temperatury, wilgotności i słońca — z tego strona liczy,
            # o której dziś wietrzyć. Promieniowanie mówi, czy południowa strona stoi
            # w słońcu; samo "jest dzień" nie wystarczy, bo pod chmurami nic nie grzeje.
            "hourly": "temperature_2m,relative_humidity_2m,shortwave_radiation",
            "forecast_days": 3, "timezone": zone,
        }, timeout=30)
        data = resp.json() or {}
        if not data.get("current"):
            print(f"Prognoza: pominięta — {data.get('reason', 'brak danych')}", flush=True)
            return None
        snapshot["current"] = data["current"]
        snapshot["daily"] = data.get("daily") or {}
        snapshot["hourly"] = trim_hourly(
            data.get("hourly") or {},
            strefa_prognozy(zone, data.get("utc_offset_seconds") or 0))
        gdzie = location_of(data, lat, lon)
        if gdzie:
            snapshot["gdzie"] = gdzie
    except (requests.RequestException, ValueError) as err:
        print(f"Prognoza: pominięta — {err}", flush=True)
        return None
    try:
        resp = requests.get(AIR_URL, params={
            "latitude": lat, "longitude": lon,
            "current": "european_aqi,pm2_5,pm10", "timezone": zone,
        }, timeout=30)
        snapshot["air"] = (resp.json() or {}).get("current") or {}
    except (requests.RequestException, ValueError) as err:
        print(f"Jakość powietrza: pominięta — {err}", flush=True)
        snapshot["air"] = {}
    WEATHER.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    godzin = len((snapshot.get("hourly") or {}).get("time") or [])
    print(
        f"Prognoza zapisana ({snapshot['current'].get('temperature_2m')} °C teraz, "
        f"{godzin} godz. naprzód).",
        flush=True,
    )
    return snapshot


def device_sources(devices: dict) -> list[dict]:
    """Manifest z poprzedniego przebiegu, a po nim to, co widać teraz.

    Manifest wchodzi do gry, żeby czujnik zdjęty z TUYA_DEVICE_IDS nie stracił nagle
    odszumiania w historycznych agregatach.
    """
    sources = []
    if MANIFEST.exists():
        try:
            sources.append(json.loads(MANIFEST.read_text(encoding="utf-8")).get("devices") or {})
        except (ValueError, OSError):
            pass
    sources.append(devices or {})
    return sources


def code_kinds(devices: dict) -> dict[tuple[str, str], str]:
    """Mapa (urządzenie, kod DP) -> rodzaj odczytu."""
    kinds: dict[tuple[str, str], str] = {}
    for source in device_sources(devices):
        for device_id, entry in source.items():
            for code, meta in ((entry or {}).get("codes") or {}).items():
                kind = (meta or {}).get("kind")
                if kind:
                    kinds[(device_id, code)] = kind
    return kinds


def external_ids(devices: dict) -> set[str]:
    """Źródła spoza mieszkania — dziś tylko pogoda z Open-Meteo."""
    return {
        device_id
        for source in device_sources(devices)
        for device_id, entry in source.items()
        if (entry or {}).get("external")
    }


def wczytaj_artefakty() -> list[dict]:
    """Znane artefakty: przedziały, w których czujnik mierzył coś innego niż pokój
    (farelka tuż pod nim, przenoszenie). Wiersze zostają w CSV — pomija się je tylko
    w agregatach, tak jak wyskoki. Zły wpis jest pomijany, a nie wywraca przebiegu."""
    try:
        wpisy = json.loads(ARTEFAKTY_PLIK.read_text(encoding="utf-8")).get("artefakty") or []
    except (OSError, ValueError):
        return []
    out = []
    for w in wpisy:
        try:
            od = datetime.fromisoformat(w["od"].replace("Z", "+00:00")).timestamp()
            do = datetime.fromisoformat(w["do"].replace("Z", "+00:00")).timestamp()
        except (KeyError, TypeError, ValueError, AttributeError):
            print(f"Artefakty: pominięty wpis bez poprawnych dat: {w!r}", flush=True)
            continue
        if w.get("czujnik") and od < do:
            out.append({**w, "od_s": od, "do_s": do})
    return out


def w_artefakcie(artefakty: list[dict], device: str, t: float) -> bool:
    return any(a["czujnik"] == device and a["od_s"] <= t <= a["do_s"] for a in artefakty)


def write_daily(devices: dict | None = None) -> int:
    """Przelicza całą historię na dobowe min/średnią/max.

    Dzięki temu widok \"całość\" nie musi wczytywać wszystkich surowych odczytów —
    przy kilku latach zbierania to różnica między setkami tysięcy wierszy a setkami.
    """
    zone = os.environ.get("TZ_LOCAL", "Europe/Warsaw")
    kinds = code_kinds(devices or {})
    zewnetrzne = external_ids(devices or {})
    try:
        tz = ZoneInfo(zone)
    except Exception:
        print(f"Nieznana strefa {zone!r}, doba liczona według UTC.", flush=True)
        tz = timezone.utc

    series: dict[tuple, list] = {}
    for path in sorted(DATA_DIR.glob("[0-9]*.csv")):
        for row in load_month(path.stem):
            try:
                value = float(row["value"])
                when = datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
            except (KeyError, TypeError, ValueError):
                continue        # bateria bywa tekstem (low/middle/high) — do średniej się nie nadaje
            series.setdefault((row["device_id"], row["code"]), []).append(
                (when.timestamp(), value, when.astimezone(tz).strftime("%Y-%m-%d"))
            )

    buckets: dict[tuple, list] = {}
    skipped = artefaktowe = 0
    artefakty = wczytaj_artefakty()
    for (device, code), points in series.items():
        points.sort()
        # gdy manifest milczy o tym kodzie, próbujemy go jeszcze rozpoznać po nazwie
        kind = kinds.get((device, code)) or classify(code, "")
        if kind in ("power", "battery"):
            continue      # dobowa średnia z włącznika albo poziomu baterii nic nie znaczy
        # Pogoda przychodzi już wygładzona z modelu, a przeglądarka jej nie filtruje.
        # Filtr po tej stronie zjadałby prawdziwe załamania pogody i rozjeżdżał widok
        # "całość" z 7-dniowym — a te dwa mają pokazywać to samo.
        bad = set() if device in zewnetrzne else drop_spikes([(t, v) for t, v, _ in points], kind)
        skipped += len(bad)
        for index, (t, value, day) in enumerate(points):
            if index in bad:
                continue
            if w_artefakcie(artefakty, device, t):
                artefaktowe += 1
                continue
            key = (day, device, code)
            found = buckets.get(key)
            if found is None:
                buckets[key] = [1, value, value, value]
            else:
                found[0] += 1
                found[1] += value
                found[2] = min(found[2], value)
                found[3] = max(found[3], value)
    if skipped:
        print(f"Agregaty: pominięto {skipped} odczytów uznanych za wyskoki.", flush=True)
    if artefaktowe:
        print(f"Agregaty: pominięto {artefaktowe} odczytów ze znanych artefaktów.", flush=True)

    rows = [
        {
            "date": day, "device_id": device, "code": code,
            "min": f"{low:g}", "avg": f"{total / count:.2f}", "max": f"{high:g}", "n": count,
        }
        for (day, device, code), (count, total, low, high) in sorted(buckets.items())
    ]
    with DAILY.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DAILY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


# Progi diagnostyki. Te same, którymi kieruje się strona (HEARTBEAT, STALE_BAD, FRSI,
# WILG_POWIERZCHNI i HUM_ALERT w index.html) — muszą się zgadzać, bo inaczej watchdog
# zakładałby zgłoszenie o czymś, czego dashboard nie pokazuje, albo odwrotnie.
HEARTBEAT_MS = 60 * 60 * 1000
CISZA_ALARM = 6 * HEARTBEAT_MS
HUM_UDZIAL = 0.25          # ułamek doby powyżej progu, od którego warto się odezwać

# Próg pleśni. Pleśń nie rośnie w powietrzu pokoju, tylko na najzimniejszym kawałku
# ściany zewnętrznej — w narożniku, za szafą, przy nadprożu okna. Ten kawałek jest tym
# zimniejszy, im zimniej na dworze, więc stały próg wilgotności powietrza (dawniej 65%)
# był dobry w jedną porę roku: we wrześniu przypadkiem się zgadzał, w styczniu milczałby
# przy 55%, gdy w narożnikach pleśń już rośnie.
#
# Metoda z PN-EN ISO 13788: temperatura powierzchni θsi = θe + fRsi·(θi − θe), a pleśń
# grozi, gdy wilgotność przy tej powierzchni trwale przekracza 80%. Z tego wychodzi
# wilgotność powietrza w pokoju, przy której w narożniku robi się 80% — przy 20 °C
# w środku: 68% przy 11 °C na dworze, 55% przy 0 °C, 45% przy −10 °C.
#
# fRsi to liczba z normy, nie z pomiaru (warunki techniczne wymagają 0,72 od nowych
# budynków; starsze bywają gorsze). Da się ją zmierzyć: jeden czujnik na dobę
# w najzimniejszym narożniku ściany zewnętrznej, drugi w środku pokoju, i odczyt z dworu.
FRSI = 0.70
WILG_POWIERZCHNI = 80.0
HUM_ALERT = 65.0           # zapas, gdy nie ma temperatury pokoju albo dworu — dawny stały próg
BLISKO_MS = int(2.5 * HEARTBEAT_MS)   # starszego odczytu nie wolno już brać za „wtedy"


def _psat(t: float) -> float:
    """Ciśnienie pary nasyconej w Pa (wzór Magnusa)."""
    return 610.94 * math.exp(17.625 * t / (t + 243.04))


def prog_plesni(t_pokoj: float | None, t_dwor: float | None) -> float:
    """Wilgotność powietrza w pokoju, przy której w najzimniejszym narożniku ściany
    zewnętrznej robi się WILG_POWIERZCHNI procent."""
    if t_pokoj is None or t_dwor is None:
        return HUM_ALERT
    if t_dwor >= t_pokoj:
        return WILG_POWIERZCHNI      # ściana nie jest chłodniejsza od powietrza
    t_sciany = t_dwor + FRSI * (t_pokoj - t_dwor)
    return WILG_POWIERZCHNI * _psat(t_sciany) / _psat(t_pokoj)


def _najblizsza(czasy: list[int], wartosci: list[float], t: int) -> float | None:
    """Wartość najbliższa w czasie, o ile nie dalej niż BLISKO_MS."""
    if not czasy:
        return None
    i = bisect.bisect_left(czasy, t)
    kandydaci = [j for j in (i - 1, i) if 0 <= j < len(czasy)]
    j = min(kandydaci, key=lambda k: abs(czasy[k] - t))
    return wartosci[j] if abs(czasy[j] - t) <= BLISKO_MS else None
BATERIA_NISKA = {"low", "niski"}
BATERIA_PROC = 15.0


def recent_rows(since_ms: int) -> list[dict]:
    """Odczyty od podanej chwili. Dwa ostatnie pliki miesięczne, bo doba potrafi
    przypaść na przełom miesiąca."""
    out = []
    for path in sorted(DATA_DIR.glob("[0-9]*.csv"))[-2:]:
        for row in load_month(path.stem):
            try:
                when = int(datetime.fromisoformat(row["ts"].replace("Z", "+00:00")).timestamp() * 1000)
            except (KeyError, ValueError, TypeError):
                continue
            if when >= since_ms:
                out.append({**row, "ms": when})
    out.sort(key=lambda r: r["ms"])
    return out


def udzial_powyzej(punkty: list[tuple[int, float]], prog: float) -> float:
    """Jaka część doby minęła z wartością powyżej progu. Liczona czasem, nie liczbą
    odczytów, bo czujnik przy zmianie raportuje gęściej i przeważyłby wynik."""
    if len(punkty) < 2:
        return 0.0
    powyzej = calosc = 0
    for (t1, v1), (t2, v2) in zip(punkty, punkty[1:]):
        # dziura dłuższa niż dwa heartbeaty to cisza, nie stan trwający — nie zaliczamy jej
        odstep = min(t2 - t1, 2 * HEARTBEAT_MS)
        calosc += odstep
        if (v1 + v2) / 2 >= prog:
            powyzej += odstep
    return powyzej / calosc if calosc else 0.0


def diagnose(devices: dict) -> list[str]:
    """Problemy, których nie widać po samym tym, czy kolektor żyje.

    Strona liczy to samo w renderEvents(), ale dowiesz się o tym dopiero wtedy, gdy sam
    ją otworzysz — a słabnąca bateria daje o sobie znać właśnie wtedy, gdy nikt nie
    patrzy. Watchdog czyta tę listę i zakłada zgłoszenie, czyli maila od GitHuba.
    """
    teraz = int(time.time() * 1000)
    rows = recent_rows(teraz - 24 * 3600 * 1000 - BLISKO_MS)
    doba = [r for r in rows if r["ms"] >= teraz - 24 * 3600 * 1000]

    # temperatura dworu do progu pleśni — z pierwszego urządzenia zewnętrznego z temperaturą
    dwor_t: list[int] = []
    dwor_v: list[float] = []
    for device_id, entry in (devices or {}).items():
        if not entry.get("external"):
            continue
        kody = {c for c, m in (entry.get("codes") or {}).items() if m.get("kind") == "temp"}
        for r in rows:
            if r["device_id"] == device_id and r["code"] in kody and _liczba(r["value"]):
                dwor_t.append(r["ms"])
                dwor_v.append(float(r["value"]))
        if dwor_t:
            break

    alerty = []
    for device_id, entry in sorted((devices or {}).items(), key=lambda kv: kv[1].get("name") or kv[0]):
        if entry.get("appliance"):
            continue          # włącznik nie ma czym wietrzyć
        zewnetrzny = bool(entry.get("external"))
        name = entry.get("name") or device_id
        codes = entry.get("codes") or {}
        moje = [r for r in doba if r["device_id"] == device_id]
        rodzaj = {code: meta.get("kind") for code, meta in codes.items()}

        klimat = [r["ms"] for r in moje if rodzaj.get(r["code"]) in ("temp", "hum")]
        if not klimat:
            alerty.append(
                f"**{name}** — bez pogody od co najmniej doby, Open-Meteo nie odpowiada."
                if zewnetrzny else
                f"**{name}** — ani jednego odczytu w ostatniej dobie."
            )
        elif teraz - klimat[-1] > CISZA_ALARM:
            godzin = (teraz - klimat[-1]) / 3600000
            alerty.append(
                f"**{name}** — brak nowej pogody od {godzin:.1f} godz., Open-Meteo nie odpowiada."
                if zewnetrzny else
                f"**{name}** — ostatni raport {godzin:.1f} godz. temu, czujnik milczy."
            )

        # Dalej idą bateria i zawilgocenie, a pogoda nie ma ani ogniwa, ani ścian:
        # 80% wilgotności na dworze to pogoda, nie usterka. Ale samo milczenie dworu
        # trzeba było zgłaszać — 16.08 Open-Meteo przestało odpowiadać i nie dowiedział
        # się o tym nikt, bo cała diagnostyka pomijała urządzenia zewnętrzne w całości.
        if zewnetrzny:
            continue

        bateria = [r["value"] for r in moje if rodzaj.get(r["code"]) == "battery"]
        if bateria:
            stan = str(bateria[-1]).strip().lower()
            try:
                niska = float(stan) <= BATERIA_PROC
            except ValueError:
                niska = stan in BATERIA_NISKA
            if niska:
                alerty.append(f"**{name}** — bateria na wyczerpaniu ({bateria[-1]}), wymień ogniwo.")

        temp = [(r["ms"], float(r["value"])) for r in rows
                if r["device_id"] == device_id and rodzaj.get(r["code"]) == "temp" and _liczba(r["value"])]
        temp_t, temp_v = [t for t, _ in temp], [v for _, v in temp]
        # każdy odczyt wilgotności porównujemy z progiem z jego chwili: pokój i dwór
        # zmieniają się w ciągu doby, a z nimi temperatura narożnika
        nadwyzka, prog = [], None
        for r in moje:
            if rodzaj.get(r["code"]) != "hum" or not _liczba(r["value"]):
                continue
            prog = prog_plesni(_najblizsza(temp_t, temp_v, r["ms"]), _najblizsza(dwor_t, dwor_v, r["ms"]))
            nadwyzka.append((r["ms"], float(r["value"]) - prog))
        udzial = udzial_powyzej(nadwyzka, 0.0)
        if udzial >= HUM_UDZIAL:
            alerty.append(
                f"**{name}** — wilgotność powyżej progu pleśni przez {udzial * 100:.0f}% doby "
                f"(przy obecnej pogodzie to ok. {prog:.0f}%), przewietrz albo osusz."
            )
    return alerty


def _liczba(tekst: str) -> bool:
    try:
        float(tekst)
    except (TypeError, ValueError):
        return False
    return True


def ids_with_history() -> set[str]:
    """Identyfikatory, które mają jeszcze jakiekolwiek odczyty w plikach miesięcznych."""
    znalezione: set[str] = set()
    for plik in DATA_DIR.glob("[0-9]*.csv"):
        try:
            with plik.open(encoding="utf-8") as f:
                next(f, None)                       # nagłówek
                for wiersz in f:
                    czesci = wiersz.split(",", 2)
                    if len(czesci) > 1:
                        znalezione.add(czesci[1])
        except OSError:
            continue
    return znalezione


def keep_known(devices: dict) -> dict:
    """Nie wyrzuca urządzenia z manifestu tylko dlatego, że ten przebieg go nie odświeżył.

    Open-Meteo potrafi nie odpowiedzieć w trzydzieści sekund i fetch.py słusznie to
    przeżywa — jedna zadyszka cudzego API nie ma wywracać całego przebiegu. Manifest
    był jednak przepisywany wyłącznie z tego, co udało się zebrać teraz, więc taki
    timeout kasował z listy urządzenie zewnętrzne, a strona traciła przez to całą
    historię dworu, chociaż jej wiersze dalej leżały w CSV. Zdarzyło się to 16.08
    o 7:01 i wyglądało jak awaria strony, a nie jak zgubione trzydzieści sekund.

    Zostaje więc każdy wpis, który ma jeszcze odczyty w plikach. Kolejność bierzemy
    z poprzedniego manifestu, bo po niej strona przydziela pokojom kolory — bez tego
    zgubione i przywrócone urządzenie przestawiałoby barwy wszystkim pozostałym.

    Czujnik odłączony na stałe zostanie w manifeście, dopóki ma historię. To celowe:
    lepiej, żeby był widoczny jako milczący — i właśnie tym jest zgłoszenie watchdoga —
    niż żeby zniknął bez śladu razem ze swoimi odczytami.
    """
    if not MANIFEST.exists():
        return devices
    try:
        stare = json.loads(MANIFEST.read_text(encoding="utf-8")).get("devices") or {}
    except (OSError, ValueError):
        return devices

    z_historia = ids_with_history()
    polaczone = dict(devices)
    for ident, wpis in stare.items():
        if ident not in polaczone and ident in z_historia:
            print(f"{wpis.get('name', ident)}: nie odświeżony w tym przebiegu, "
                  f"zostaje w manifeście — ma jeszcze odczyty.")
            polaczone[ident] = wpis

    kolejnosc = [i for i in stare if i in polaczone] + [i for i in polaczone if i not in stare]
    return {i: polaczone[i] for i in kolejnosc}


def write_manifest(devices: dict, alerty: list[str] | None = None) -> None:
    devices = keep_known(devices)
    months = sorted(p.stem for p in DATA_DIR.glob("[0-9]*.csv"))
    MANIFEST.write_text(
        json.dumps(
            {
                "updated": iso(int(time.time() * 1000)),
                "months": months,
                "daily": DAILY.name if DAILY.exists() else None,
                "weather": WEATHER.name if WEATHER.exists() else None,
                # czyta to watchdog, żeby raz na dobę zgłosić to, co wymaga ręki
                "alerty": alerty or [],
                # strona chowa te przedziały razem z chwilowymi skokami
                "artefakty": [{k: a[k] for k in ("czujnik", "od", "do", "powod") if k in a}
                              for a in wczytaj_artefakty()],
                "devices": devices,
            },
            ensure_ascii=False, indent=2,
        ) + "\n", encoding="utf-8"
    )


def _odkryj_urzadzenie(client: Tuya, dev: dict, nowe: bool, teraz_ms: int) -> bool:
    """Wypisuje jedno urządzenie dla --discover. Zwraca True dla czujnika w doniczce."""
    spec = specyfikacja(client, dev["id"])
    codes = describe_codes(client, dev["id"], spec)
    roslina = dev.get("category") == "zwjcy"
    marker = "czujnik w doniczce" if roslina else ("czujnik klimatu" if codes else "inne urządzenie")
    produkt = str(dev.get("product_name") or "")
    if dev.get("product_id"):
        produkt = f"{produkt} ({dev['product_id']})".strip()
    print(f"  {dev['id']}   {dev.get('name') or '?'}" + ("" if nowe else "   [już zbierane]"))
    print(f"      kategoria: {dev.get('category', '?')}   rola: {marker}"
          + (f"   produkt: {produkt}" if produkt else "")
          + ("   OFFLINE" if dev.get("online") is False else ""))
    for code, typ, opis in all_codes(client, dev["id"], spec):
        meta = codes.get(code)
        ocena = f"zbierane jako {meta['kind']}, scale={meta['scale']}" if meta else "pomijane"
        print(f"      pole: {code:<22} typ={typ:<8} {opis:<26} {ocena}")
    if nowe:
        for code, typ, opis in all_codes(client, dev["id"], spec, "functions"):
            print(f"      ustawienie: {code:<16} typ={typ:<8} {opis}")
        stan = [s for s in (dev.get("status") or []) if isinstance(s, dict)]
        if stan:
            print("      teraz: " + ", ".join(f"{s.get('code')}={s.get('value')}" for s in stan))
        print(f"      wpisy: {tempo_wpisow(client, dev['id'], teraz_ms)}")
    print()
    return roslina


def odkryj(client: Tuya, all_devices: list[dict], region: str) -> int:
    """--discover: wszystko, czego trzeba, żeby podpiąć nowe urządzenie, w jednym przebiegu.

    Jedna specyfikacja na urządzenie (dawniej dwie). Dla urządzeń, których kolektor
    jeszcze nie zbiera, także pola do ustawiania, bieżące wartości z listy urządzeń
    (bez dodatkowych zapytań) i tempo wpisów z ostatniej godziny — od niego zależy,
    ile zbieranie będzie kosztować z miesięcznego pakietu.
    """
    znane = set()
    if MANIFEST.exists():
        try:
            znane = set(json.loads(MANIFEST.read_text(encoding="utf-8")).get("devices") or {})
        except (ValueError, OSError):
            pass
    teraz_ms = int(time.time() * 1000)
    rosliny = []
    print(f"Znaleziono {len(all_devices)} urządzeń w regionie {region}:\n")
    for dev in all_devices:
        try:
            if _odkryj_urzadzenie(client, dev, dev["id"] not in znane, teraz_ms):
                rosliny.append(dev.get("name") or dev["id"])
        except Exception as err:  # jedno dziwne urządzenie nie może zmarnować całego przebiegu
            print(f"  {dev.get('id')}: nie udało się opisać — {type(err).__name__}: {err}\n")
    if rosliny:
        print(f"Czujniki w doniczkach ({', '.join(rosliny)}) idą osobnym torem — NIE dopisuj ich")
        print("do TUYA_DEVICE_IDS: kolektor wziąłby glebę za wilgotność powietrza (patrz ROSLINY.md).")
    print("Żeby zbierać nowy czujnik klimatu, dopisz jego identyfikator do TUYA_DEVICE_IDS")
    print("w .github/workflows/zbieraj.yml.")
    print(f"\nZapytań do Tuya: {client.zapytan}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Kolektor odczytów z chmury Tuya")
    parser.add_argument("--discover", action="store_true", help="wypisz urządzenia i zakończ")
    parser.add_argument("--days", type=int, default=7, help="ile dni wstecz pobrać (Tuya trzyma maksymalnie 7)")
    parser.add_argument("--dry-run", action="store_true", help="pokaż, co by się zapisało, ale nie zapisuj")
    args = parser.parse_args()

    client_id = os.environ.get("TUYA_CLIENT_ID", "").strip()
    secret = os.environ.get("TUYA_CLIENT_SECRET", "").strip()
    region = os.environ.get("TUYA_REGION", "eu").strip().lower()
    if not client_id or not secret:
        print("Brakuje TUYA_CLIENT_ID albo TUYA_CLIENT_SECRET.", file=sys.stderr)
        print("Lokalnie: export TUYA_CLIENT_ID=... ; w Actions: sekrety repozytorium.", file=sys.stderr)
        return 2

    client = Tuya(client_id, secret, region)
    all_devices = list_devices(client)
    if args.discover:
        return odkryj(client, all_devices, region)

    wanted = [d.strip() for d in os.environ.get("TUYA_DEVICE_IDS", "").split(",") if d.strip()]
    if wanted:
        all_devices = [d for d in all_devices if d["id"] in wanted]

    end_ms = int(time.time() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() * 1000)
    since_ms = parse_since(os.environ.get("TUYA_SINCE", ""))
    if since_ms:
        start_ms = max(start_ms, since_ms)
        print(f"Zbieram wyłącznie odczyty od {iso(since_ms)}.\n", flush=True)
        if since_ms >= end_ms:
            print("Granica leży w przyszłości — na razie nie ma czego zbierać.", file=sys.stderr)

    DATA_DIR.mkdir(exist_ok=True)
    removed = purge_before(since_ms)
    if removed:
        print(f"Usunięto {removed} starych odczytów sprzed TUYA_SINCE.", flush=True)

    manifest_devices, collected = {}, []
    cached, ostatni_log, pobrane = {}, {}, {}
    if MANIFEST.exists():
        try:
            for dev_id, entry in json.loads(MANIFEST.read_text(encoding="utf-8")).get("devices", {}).items():
                known = entry.get("codes") or {}
                if all("scale" in meta for meta in known.values()) and known:
                    cached[dev_id] = {c: dict(m) for c, m in known.items()}
                for pole, dokad in (("last_log", ostatni_log), ("pobrane_do", pobrane)):
                    stamp = entry.get(pole)
                    if stamp:
                        try:
                            dokad[dev_id] = int(
                                datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() * 1000
                            )
                        except ValueError:
                            pass
        except (ValueError, OSError):
            pass

    failed = []
    for dev in all_devices:
        device_id = dev["id"]
        name = dev.get("name") or device_id
        codes = cached.get(device_id) or describe_codes(client, device_id)
        # Urządzenie z włącznikiem to sprzęt, nie czujnik klimatu: interesuje nas wyłącznie
        # to, kiedy chodziło. Jego własny termometr (klimatyzator ma temp_current) mierzy
        # powietrze na wlocie, a nie temperaturę pokoju, więc nie wpuszczamy go na wykresy.
        sprzet = any(m["kind"] == "power" for m in codes.values())
        if sprzet:
            codes = {c: m for c, m in codes.items() if m["kind"] == "power"}
        elif not any(m["kind"] in ("temp", "hum") for m in codes.values()):
            continue
        manifest_devices[device_id] = {
            "name": name,
            **({"appliance": True} if sprzet else {}),
            "codes": {c: {"kind": m["kind"], "unit": m["unit"], "scale": m["scale"]} for c, m in codes.items()},
        }
        # Sprzęt raportuje swój stan co kilka sekund, więc ciągnięcie całego tygodnia
        # przy każdym przebiegu to tysiące stron: przebieg puchł z 27 sekund do 10 minut
        # i dobijał do limitu stron, przez co najnowsze zmiany bywały ucinane. Wystarczy
        # dociągać od ostatniego widzianego wpisu — stąd last_log w manifeście, z oknem
        # najwyżej 12 godz. Czujniki klimatu mają własny kursor `pobrane_do` i zakładkę,
        # ale nadrabiają do pełnych 7 dni, bo u nich przerwa w zbieraniu to dziura
        # w wykresach.
        if sprzet:
            od_kiedy = max(start_ms, end_ms - SPRZET_OKNO)
            if ostatni_log.get(device_id):
                od_kiedy = max(od_kiedy, ostatni_log[device_id] + 1000)
                # Znacznik przepisujemy od razu: gdyby pobranie poniżej się wywaliło,
                # wypadnie z manifestu i następny przebieg znów ciągnąłby pełne 12 godz.
                manifest_devices[device_id]["last_log"] = iso(ostatni_log[device_id])
        else:
            kursor = min(pobrane[device_id], end_ms) if pobrane.get(device_id) else None
            od_kiedy = max(start_ms, kursor - ZAKLADKA_MS) if kursor else start_ms
            if kursor:
                # Jak przy last_log: kursor przepisany zawczasu przeżyje nieudane pobranie,
                # więc następny przebieg nadrobi od tego samego miejsca, a nie od 7 dni.
                manifest_devices[device_id]["pobrane_do"] = iso(kursor)
        try:
            if sprzet:
                logs = fetch_logs(client, device_id, od_kiedy, end_ms)
            else:
                logs, domkniete = pobierz_przyrostowo(client, device_id, od_kiedy, end_ms, pewne_do=kursor)
                # Kursor nigdy nie cofa się: to, co przed nim, jest już w CSV.
                nowy = max(x for x in (kursor, domkniete, 0) if x is not None)
                if nowy:
                    manifest_devices[device_id]["pobrane_do"] = iso(nowy)
        except (TuyaError, requests.RequestException) as err:
            failed.append(name)
            print(f"{name}: pominięty — {err}", flush=True)
            continue
        widziany = max((int(e["event_time"]) for e in logs if e.get("event_time")), default=0)
        if sprzet:
            znacznik = max(widziany, ostatni_log.get(device_id, 0))
            if znacznik:
                manifest_devices[device_id]["last_log"] = iso(znacznik)
        kept = 0
        for entry in logs:
            code = entry.get("code")
            meta = codes.get(code)
            if not meta:
                continue
            raw = entry.get("value")
            if meta["kind"] == "power":
                # Tuya raportuje włącznik jako "true"/"false"; w CSV trzymamy 1/0,
                # żeby przeglądarka nie musiała znać obu zapisów
                value = "1" if str(raw).strip().lower() in ("true", "1", "on") else "0"
            else:
                try:
                    value = f'{float(raw) / (10 ** meta["scale"]):g}'
                except (TypeError, ValueError):
                    if meta["kind"] != "battery" or raw is None:
                        continue
                    value = str(raw)
            when = int(entry["event_time"])
            if since_ms and when < since_ms:
                continue
            collected.append({"ts": iso(when), "device_id": device_id, "code": code, "value": value})
            kept += 1
        print(f"{name}: {kept} odczytów od {iso(od_kiedy)}", flush=True)

    if not manifest_devices:
        print("\nŻadne urządzenie nie zgłosiło temperatury ani wilgotności.", file=sys.stderr)
        print("Uruchom `python fetch.py --discover` i sprawdź listę.", file=sys.stderr)
        return 1
    if args.dry_run:
        extra, _ = fetch_outdoor(args.days)
        print(f"\n[dry-run] {len(collected) + len(extra)} odczytów, nic nie zapisano. "
              f"Zapytań do Tuya: {client.zapytan}.")
        return 0

    outdoor_rows, outdoor_entry = fetch_outdoor(args.days)
    if outdoor_entry:
        collected.extend(outdoor_rows)
        manifest_devices[OUTDOOR_ID] = outdoor_entry

    fetch_weather()

    added = merge(collected)
    zwiniete = collapse_power(manifest_devices)
    if zwiniete:
        print(f"Włączniki: zwinięto {zwiniete} powtórzeń tego samego stanu.")
    days_written = write_daily(manifest_devices)
    alerty = diagnose(manifest_devices)
    write_manifest(manifest_devices, alerty)
    print(f"\nDopisano {added} nowych odczytów ({len(collected) - added} już było).")
    print(f"Agregaty dobowe: {days_written} wierszy w {DAILY}.")
    if alerty:
        print(f"Diagnostyka: {len(alerty)} rzecz(y) do sprawdzenia —")
        for alert in alerty:
            print(f"  · {alert}")
    if failed:
        print(f"Pominięte czujniki: {', '.join(failed)}.")
        print("Dane pozostałych zostały zapisane. Następny przebieg nadrobi resztę — okno 7 dni jeszcze się nie zamknęło.")
    print(f"Zapytań do Tuya w tym przebiegu: {client.zapytan}.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except TuyaError as err:
        print(f"\n{err}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as err:
        print(f"\nProblem z siecią: {err}", file=sys.stderr)
        sys.exit(1)
