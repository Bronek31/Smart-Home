"""
Reguły domu — obliczenia bez sieci i bez plików, tak jak rosliny.py dla doniczek.

Kolektor (fetch.py) podaje surowe odczyty pokoi z ostatnich 8 dób, manifest, prognozę
i chwilę zbiórki, a dostaje z powrotem dwie rzeczy:

- `stan_domu()` — zawartość data/dom/stan.json: dla każdego pokoju „przewietrz",
  „okno", „noc" (przewietrz przed snem), „milczy_od" i „bateria". Strona tylko to
  wyświetla — nie liczy tych reguł drugi raz w JS, bo karta i powiadomienie nie mogą
  mówić co innego.
- `zaplanuj_powiadomienia()` — NOWA zawartość data/dom/powiadomienia.json, w tym samym
  formacie co plik roślin: kto dostaje wpis teraz, komu się go odkłada na koniec ciszy
  nocnej (telefony.py), co już poszło w tym epizodzie.

Moduł nie importuje fetch.py: kolektor chodzi jako `__main__`, więc `import fetch` dałby
drugą kopię modułu. Wzór granicy jest tu powtórzony, a test pilnuje, że zgadza się
z `fetch.prog_plesni`.
"""

from __future__ import annotations

import bisect
import json
import math
import re
import statistics
import unicodedata
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import telefony

GODZ = 3600 * 1000
MINUTA = 60 * 1000
DOBA = 24 * GODZ

# Odczyty, na których stoją reguły: 7 nocy „zwykle" plus noc liczona — 8 dób wstecz.
OKNO_ODCZYTOW_MS = 8 * DOBA

# Granica „za wilgotno" (PN-EN ISO 13788): wilgotność powietrza w pokoju, przy której
# w najzimniejszym narożniku ściany zewnętrznej robi się 80%. Te same liczby co FRSI
# i WILG_POWIERZCHNI w fetch.py i index.html — test porównuje wzory na siatce.
FRSI = 0.70
WILG_POWIERZCHNI = 80.0
# Starszego odczytu nie wolno brać za „wtedy" — jak BLISKO_MS w fetch.py.
BLISKO_MS = int(2.5 * GODZ)

# Przewietrz: wilgotność nad granicą bez przerwy co najmniej 2 godz. Zapas 10 min, bo
# przebiegi startują od :00 do :06 po pełnej godzinie (pomiar commitów 2–9.10 w
# rosliny.py, ZAPAS_PRZEBIEGU_MS) — inaczej 2 godz. raz po raz czekałyby przebieg dłużej.
PRZEWIETRZ_TRWA_MS = 2 * GODZ
ZAPAS_PRZEBIEGU_MS = 10 * MINUTA
# Ostatni odczyt starszy niż to nie mówi już, co jest w pokoju teraz.
PRZEWIETRZ_SWIEZY_MS = 3 * GODZ
# Dwa odczyty dalej od siebie to dziura, a nie „cały czas nad granicą".
PRZEWIETRZ_PRZERWA_MS = BLISKO_MS

# Zamknij okno (sezon grzewczy) — oknoOtwarte z prototypu, na surowych odczytach.
OKNO_WSTECZ_MS = 6 * GODZ          # A musi leżeć w ostatnich 6 godz.
OKNO_ODCZYTY_MS = 9 * GODZ         # i mieć przed sobą 3 godz. na poziom bazowy
OKNO_BAZA_MS = 3 * GODZ
OKNO_SPADEK_W_MS = GODZ
OKNO_SPADEK = 1.5
# A nie może być szczytem grzania, a ostatni odczyt musi leżeć ≥ 1,5° pod poziomem
# bazowym (mediana 3 godz. przed A): farelka w Łazience 8.10 rano grzała 21,9 → 26,5 °C
# w 12 min i stygła do 22,4 °C w godzinę — bez poziomu bazowego to „zamknij okno"
# (test na tych odczytach; w prototypie 6 fałszywych godzin, OPIS4.md).
OKNO_PONAD_BAZE = 1.0
OKNO_PONIZEJ_BAZY = 1.5
OKNO_DWOR_CHLODNIEJ = 4.0
# „Robi się zimno": poniżej dolnej granicy pola komfortu (20 °C) + 0,5° albo wilgotność
# spadła o 2 pkt — świeże powietrze z dworu jest suche.
OKNO_ZIMNO_PONIZEJ = 20.5
OKNO_SPADEK_WILGOTNOSCI = 2.0
# Temperatura już wraca, więc okno jest zamknięte. Salon 6.10: wietrzenie 22:50–23:35,
# 21,3 → 18,8 °C, potem 19,3 i 19,8 °C o 23:49 — przebieg o północy powiedziałby
# „Zamknij okno w salonie?" ok. 25 min po zamknięciu (pomiar 14 dób, jedyne trafienie).
# Czujnik zgłasza zmianę skokiem 0,5° (odczyty < 50 min po poprzednim, 27.09–11.10,
# wszystkie pokoje: 70 ze 160 różni się o dokładnie 0,5°, to najczęstsza różnica), więc
# jeden skok w górę to jeszcze szum, a dwa to powrót.
OKNO_JUZ_WRACA = 1.0
# Tylko w sezonie grzewczym. Latem okno otwiera się po to, żeby schłodzić mieszkanie:
# Kuchnia 23.08 wieczorem 25,2 → 22,5 °C, wilgotność 56 → 48%, i reguła trzymała
# „Zamknij okno w kuchni?" przez 6 godzin (przeliczenie co godzinę 16.08–11.10 — jedyny
# epizod poza tym, który usuwa OKNO_JUZ_WRACA). Średnia doba na dworze tego nie odróżnia:
# 23.08 miała 17,6 °C, a 1–8.10, już z kaloryferami, 16,25–17,2 °C (dzienne.csv). Początek
# to 1.10, kiedy w budynku ruszają kaloryfery (KONTEKST.md, 27.09); koniec — kwiecień —
# przyjęty, nie zmierzony: do sprawdzenia wiosną, kiedy kaloryfery staną.
SEZON_GRZEWCZY = (10, 11, 12, 1, 2, 3, 4)

# Przewietrz przed snem: noc 22:00–7:00, „zwykle" z odczytów 23:00–7:00 z 7 nocy.
NOC_OD_H, NOC_DO_H = 22, 7
ZWYKLE_OD_H, ZWYKLE_DO_H = 23, 7
NOCY_ZWYKLE = 7
GODZIN_NOCY_MIN = 5
OSTRZEZENIE_PKT = 2.0

# Czujnik milczy — próg powiadomienia, liczony od kursora kolektora (CISZA_ALARM w fetch.py).
CISZA_MS = 6 * GODZ
BATERIE = ("low", "middle", "high")

# Planer
DNI_HISTORII = 60
MAKS_PRZEWIETRZ_NA_DOBE = 2        # na pokój, na lokalną dobę (bez dostarczeń odłożonych)
KLUCZ_USTAWIEN = {"przewietrz": "przewietrz", "przed-snem": "przewietrz", "okno": "okno",
                  "czujniki": "czujniki"}


# ---------- drobne ----------

def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ms(tekst) -> int | None:
    if not isinstance(tekst, str):
        return None
    try:
        kiedy = datetime.fromisoformat(tekst.replace("Z", "+00:00"))
    except ValueError:
        return None
    if kiedy.tzinfo is None:
        kiedy = kiedy.replace(tzinfo=timezone.utc)
    return int(kiedy.timestamp() * 1000)


def _liczba(wartosc) -> float | None:
    if isinstance(wartosc, bool):
        return None
    try:
        x = float(wartosc)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _r(x: float | None) -> float | None:
    return None if x is None else round(x, 1)


def _w_gore(x: float, miejsc: int = 0) -> Decimal:
    """Zaokrąglenie połówką w górę (od zera), jak `liczba()` na stronie (Intl.NumberFormat,
    tryb halfExpand) i Math.round dla liczb dodatnich.

    Format Pythona (`f"{62.5:.0f}"`, `round`) zaokrągla połówkę do parzystej: ta sama
    granica 62,5 z data/dom/stan.json dawała w powiadomieniu „62%", a na karcie „63%"
    (przegląd, B2/C1). Liczy się z dziesiętnego zapisu liczby (`repr`, ten sam co w JSON-ie),
    a nie z jej przybliżenia binarnego — strona też dostaje tekst z pliku."""
    return Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-miejsc), rounding=ROUND_HALF_UP)


def _pl(x: float, miejsc: int = 1) -> str:
    """Liczba z przecinkiem dziesiętnym, jak na stronie — z tą samą regułą zaokrąglania.
    Planer dostaje wartości ze stan.json (już po `_r`), więc treść i karta liczą z tej
    samej liczby."""
    return f"{_w_gore(x, miejsc):.{miejsc}f}".replace(".", ",")


def _slug(tekst: str) -> str:
    """ASCII [a-z0-9-] — ta sama funkcja co `_slug` w rosliny.py i na stronie (D7).
    Powtórzona, bo reguły domu nie mogą zależeć od toru roślin."""
    tekst = unicodedata.normalize("NFKD", tekst.replace("ł", "l").replace("Ł", "L"))
    tekst = "".join(z for z in tekst if not unicodedata.combining(z)).lower()
    return re.sub(r"[^a-z0-9]+", "-", tekst).strip("-")


def _mala(tekst: str) -> str:
    """Mała pierwsza litera w środku zdania — chyba że to skrót."""
    return tekst[:1].lower() + tekst[1:] if tekst[1:2].islower() else tekst


def _lista_slow(slowa: list[str]) -> str:
    return slowa[0] if len(slowa) == 1 else ", ".join(slowa[:-1]) + " i " + slowa[-1]


def _godzina(ms: int, strefa: ZoneInfo) -> str:
    """„7:05", „19:40" — godzina lokalna jak na stronie."""
    kiedy = datetime.fromtimestamp(ms / 1000, strefa)
    return f"{kiedy.hour}:{kiedy.minute:02d}"


# ---------- granica i wartości w chwili ----------

def _psat(t: float) -> float:
    """Ciśnienie pary nasyconej w Pa (wzór Magnusa)."""
    return 610.94 * math.exp(17.625 * t / (t + 243.04))


def granica(tp: float | None, td: float | None) -> float | None:
    """Wilgotność powietrza w pokoju (temperatura `tp`), przy której w najzimniejszym
    narożniku ściany zewnętrznej (dwór `td`) robi się 80%. Wzór `prog_plesni` z fetch.py,
    ale bez zapasu 65% — reguła bez danych milczy, zamiast zgadywać."""
    if tp is None or td is None:
        return None
    if td >= tp:
        return WILG_POWIERZCHNI      # ściana nie jest chłodniejsza od powietrza
    t_sciany = td + FRSI * (tp - td)
    return WILG_POWIERZCHNI * _psat(t_sciany) / _psat(tp)


class Szereg:
    """Odczyty jednej wielkości po czasie: (ms, wartość), rosnąco."""

    def __init__(self, punkty: list[tuple[int, float]]):
        punkty = sorted(punkty)
        self.czasy = [t for t, _ in punkty]
        self.wartosci = [v for _, v in punkty]

    def __len__(self):
        return len(self.czasy)

    def najblizsza(self, t: int) -> float | None:
        """Wartość najbliższa w czasie, o ile nie dalej niż BLISKO_MS (jak `_najblizsza`
        w fetch.py)."""
        if not self.czasy:
            return None
        i = bisect.bisect_left(self.czasy, t)
        kandydaci = [j for j in (i - 1, i) if 0 <= j < len(self.czasy)]
        j = min(kandydaci, key=lambda k: abs(self.czasy[k] - t))
        return self.wartosci[j] if abs(self.czasy[j] - t) <= BLISKO_MS else None

    def do(self, t: int) -> "Szereg":
        """Tylko odczyty nie późniejsze niż `t`."""
        k = bisect.bisect_right(self.czasy, t)
        s = Szereg([])
        s.czasy, s.wartosci = self.czasy[:k], self.wartosci[:k]
        return s


# ---------- reguły jednego pokoju ----------

def przewietrz(wilg: Szereg, temp: Szereg, dwor: Szereg, teraz_ms: int) -> dict | None:
    """Wilgotność nad granicą bez przerwy od ≥ 2 godz. (z zapasem przebiegu).

    Każdy odczyt porównuje się z granicą ze swojej chwili — pokój i dwór zmieniają się
    w ciągu doby, a z nimi temperatura narożnika. Seria cofa się od ostatniego odczytu,
    póki odczyty są nad granicą i nie dalej od siebie niż 2,5 godz.
    """
    if not len(wilg):
        return None
    t_ost, v_ost = wilg.czasy[-1], wilg.wartosci[-1]
    if teraz_ms - t_ost > PRZEWIETRZ_SWIEZY_MS:
        return None

    def nad(i: int) -> float | None:
        t = wilg.czasy[i]
        g = granica(temp.najblizsza(t), dwor.najblizsza(t))
        return g if g is not None and wilg.wartosci[i] > g else None

    g_ost = nad(len(wilg) - 1)
    if g_ost is None:
        return None
    i = len(wilg) - 1
    while i > 0 and wilg.czasy[i] - wilg.czasy[i - 1] <= PRZEWIETRZ_PRZERWA_MS and nad(i - 1) is not None:
        i -= 1
    od = wilg.czasy[i]
    if teraz_ms - od < PRZEWIETRZ_TRWA_MS - ZAPAS_PRZEBIEGU_MS:
        return None
    return {"od": iso(od), "wilg": _r(v_ost), "granica": _r(g_ost)}


def _roznica(a: float, b: float) -> float:
    """Różnica odczytów z jednym miejscem po przecinku, bez szumu float — 16,4 − 14,9
    liczone wprost to 1,4999999999999982 i próg 1,5 by nie przeszedł."""
    return round(a - b, 6)


def okno(temp: Szereg, wilg: Szereg, dwor_teraz: float | None, teraz_ms: int) -> dict | None:
    """„Zamknij okno?" — `oknoOtwarte` z prototypu na surowych temperaturach (bez filtra
    skoków: zjadłby krótkie wietrzenie).

    A to najwcześniejszy odczyt z ostatnich 6 godz., po którym w ≤ 1 godz. temperatura
    spadła o ≥ 1,5°. Poziom bazowy to mediana odczytów z 3 godz. przed A (co najmniej
    dwóch, inaczej samo A). Warunki: A ≤ baza + 1 (A nie jest szczytem grzania),
    ostatni odczyt ≥ 1,5° poniżej bazy i poniżej A, na dworze ≥ 4° chłodniej niż A,
    robi się zimno — ostatni odczyt < 20,5 °C albo wilgotność od A spadła o ≥ 2 pkt —
    i temperatura jeszcze nie wraca: ostatni odczyt mniej niż 1° nad najniższym po A.
    """
    if dwor_teraz is None:
        return None
    od = bisect.bisect_left(temp.czasy, teraz_ms - OKNO_ODCZYTY_MS)
    pk = list(zip(temp.czasy[od:], temp.wartosci[od:]))
    if len(pk) < 2:
        return None
    t_ost, ost = pk[-1]
    w_ost = wilg.najblizsza(t_ost)
    for a in range(len(pk) - 1):
        t_a, v_a = pk[a]
        if t_a < teraz_ms - OKNO_WSTECZ_MS:
            continue
        wczesniej = [v for t, v in pk[:a] if t >= t_a - OKNO_BAZA_MS]
        baza = statistics.median(wczesniej) if len(wczesniej) >= 2 else v_a
        spadek = max((_roznica(v_a, v) for t, v in pk[a + 1:] if t - t_a <= OKNO_SPADEK_W_MS), default=0.0)
        najnizej = min(v for _, v in pk[a + 1:])
        w_a = wilg.najblizsza(t_a)
        zimno = ost < OKNO_ZIMNO_PONIZEJ or (w_a is not None and w_ost is not None
                                             and _roznica(w_a, w_ost) >= OKNO_SPADEK_WILGOTNOSCI)
        if (spadek >= OKNO_SPADEK and _roznica(v_a, baza) <= OKNO_PONAD_BAZE
                and _roznica(baza, ost) >= OKNO_PONIZEJ_BAZY and _roznica(v_a, ost) >= OKNO_SPADEK
                and _roznica(v_a, dwor_teraz) >= OKNO_DWOR_CHLODNIEJ and zimno
                and _roznica(ost, najnizej) < OKNO_JUZ_WRACA):
            return {"od": iso(t_a), "przed": _r(v_a), "teraz": _r(ost), "spadek": _r(v_a - ost)}
    return None


def klucz_nocy(teraz_ms: int, strefa: ZoneInfo) -> str:
    """Noc, o którą chodzi: po 22:00 i przed 7:00 bieżąca, inaczej nadchodząca (dzisiejsza
    data). Ten sam klucz co `telefony.data_nocy` — data wieczoru."""
    lokalnie = datetime.fromtimestamp(teraz_ms / 1000, strefa)
    if lokalnie.hour >= NOC_OD_H or lokalnie.hour < NOC_DO_H:
        return telefony.data_nocy(lokalnie)
    return lokalnie.date().isoformat()


def najzimniej_w_nocy(pogoda: dict | None, teraz_ms: int, strefa: ZoneInfo) -> float | None:
    """Najniższa temperatura z prognozy godzinowej w nocy 22:00–7:00 (godzina 7:00 jeszcze
    się liczy, jak w prototypie), tylko godziny od teraz − 1 godz."""
    godzinowe = (pogoda or {}).get("hourly") if isinstance(pogoda, dict) else None
    if not isinstance(godzinowe, dict):
        return None
    czasy, temperatury = godzinowe.get("time"), godzinowe.get("temperature_2m")
    if not isinstance(czasy, list) or not isinstance(temperatury, list):
        return None
    noc = klucz_nocy(teraz_ms, strefa)
    t_min = None
    for stempel, v in zip(czasy, temperatury):
        t, v = _ms(stempel), _liczba(v)
        if t is None or v is None or t < teraz_ms - GODZ:
            continue
        lokalnie = datetime.fromtimestamp(t / 1000, strefa)
        if not (lokalnie.hour >= NOC_OD_H or lokalnie.hour <= NOC_DO_H):
            continue
        if telefony.data_nocy(lokalnie) != noc:
            continue
        t_min = v if t_min is None else min(t_min, v)
    return t_min


def zwykle_w_nocy(wilg: Szereg, noc: str, strefa: ZoneInfo) -> float | None:
    """Ile pokój zwykle ma w nocy: średnia z nocnych maksimów wilgotności z odczytów
    23:00–7:00 w 7 nocach przed nocą `noc`. Liczą się noce z odczytami w ≥ 5 różnych
    godzinach — godzina to pełna godzina UTC, więc powtórzona 2:00 przy zmianie czasu
    25.10 jest osobną godziną."""
    pierwsza = (datetime.fromisoformat(noc) - timedelta(days=NOCY_ZWYKLE)).date().isoformat()
    noce: dict[str, tuple[set, list]] = {}
    for t, v in zip(wilg.czasy, wilg.wartosci):
        lokalnie = datetime.fromtimestamp(t / 1000, strefa)
        if not (lokalnie.hour >= ZWYKLE_OD_H or lokalnie.hour < ZWYKLE_DO_H):
            continue
        k = telefony.data_nocy(lokalnie)
        if not (pierwsza <= k < noc):
            continue
        godziny, wartosci = noce.setdefault(k, (set(), []))
        godziny.add(t // GODZ)
        wartosci.append(v)
    maksima = [max(w) for g, w in noce.values() if len(g) >= GODZIN_NOCY_MIN]
    return sum(maksima) / len(maksima) if maksima else None


def noc_pokoju(temp: Szereg, wilg: Szereg, t_min: float | None, teraz_ms: int, strefa: ZoneInfo) -> dict | None:
    """„Przewietrz przed snem": granica na najzimniejszą godzinę nocy przy dzisiejszej
    temperaturze pokoju, porównana z tym, ile pokój zwykle ma w nocy. Ostrzeżenie już
    przy zapasie < 2 pkt — liczone na liczbach przed zaokrągleniem."""
    if t_min is None:
        return None
    g = granica(temp.najblizsza(teraz_ms), t_min)
    noc = klucz_nocy(teraz_ms, strefa)
    zwykle = zwykle_w_nocy(wilg, noc, strefa)
    if g is None or zwykle is None:
        return None
    return {"noc": noc, "t_min": _r(t_min), "granica": _r(g), "zwykle": _r(zwykle),
            "ostrz": zwykle >= g - OSTRZEZENIE_PKT}


def milczy_od(ostatni_ms: int | None, pobrane_do_ms: int | None, teraz_ms: int,
              poczatek_ms: int) -> str | None:
    """Czujnik milczy, gdy jego ostatni odczyt jest o ≥ 6 godz. starszy niż kursor kolektora
    (`pobrane_do`) — a nie niż „teraz": po postoju kolektora albo spóźnionym harmonogramie
    GitHuba wszystkie pokoje wyglądałyby na milczące. Bez odczytu w całym oknie zwraca
    początek okna: czujnik milczy co najmniej od tej chwili."""
    odniesienie = min(pobrane_do_ms, teraz_ms) if pobrane_do_ms is not None else teraz_ms
    ostatni = ostatni_ms if ostatni_ms is not None else poczatek_ms
    return iso(ostatni) if odniesienie - ostatni >= CISZA_MS else None


# ---------- stan domu ----------

def _rodzaje(wpis: dict) -> dict[str, str]:
    kody = wpis.get("codes") if isinstance(wpis.get("codes"), dict) else {}
    return {kod: (m or {}).get("kind") for kod, m in kody.items() if isinstance(m, dict)}


def pokoje_z_manifestu(urzadzenia: dict) -> list[str]:
    """Pokoje w kolejności manifestu: bez dworu, bez sprzętu z włącznikiem, tylko
    z temperaturą albo wilgotnością."""
    out = []
    for dev, wpis in (urzadzenia or {}).items():
        if not isinstance(wpis, dict) or wpis.get("external") or wpis.get("appliance"):
            continue
        if any(r in ("temp", "hum") for r in _rodzaje(wpis).values()):
            out.append(dev)
    return out


def _dwor(wiersze: list[dict], urzadzenia: dict) -> Szereg:
    """Temperatura dworu z pierwszego urządzenia zewnętrznego, które ją ma (jak diagnose)."""
    for dev, wpis in (urzadzenia or {}).items():
        if not isinstance(wpis, dict) or not wpis.get("external"):
            continue
        kody = {k for k, r in _rodzaje(wpis).items() if r == "temp"}
        punkty = [(w["ms"], v) for w in wiersze if w.get("device_id") == dev and w.get("code") in kody
                  and (v := _liczba(w.get("value"))) is not None]
        if punkty:
            return Szereg(punkty)
    return Szereg([])


def stan_domu(wiersze: list[dict], urzadzenia: dict, pogoda: dict | None, teraz_ms: int,
              strefa: ZoneInfo, nieodswiezone=(), bez_okna=()) -> dict:
    """Zawartość data/dom/stan.json.

    `wiersze` — surowe odczyty z ostatnich 8 dób, `{"ms", "device_id", "code", "value"}`,
    już bez znanych artefaktów (artefakty.json), ale BEZ filtra skoków. `urzadzenia` —
    manifest (rodzaje kodów, `external`, `appliance`, kursor `pobrane_do`). `pogoda` —
    migawka z fetch_weather albo None. `nieodswiezone` — identyfikatory, których ten
    przebieg nie pobrał (błąd Tuya): ich dane są nieświeże, więc „milczy" nie przysługuje.
    `bez_okna` — pokoje bez okna (pokoje.json, `opisy_pokoi`): „zamknij okno" nie ma tam
    sensu, a spadek po gorącym prysznicu wygląda jak wietrzenie (Łazienka 13.10, 22,8 → 21,1 °C).
    """
    wiersze = [w for w in wiersze if isinstance(w.get("ms"), int) and w["ms"] <= teraz_ms]
    dwor = _dwor(wiersze, urzadzenia)
    dwor_teraz = dwor.najblizsza(teraz_ms)
    t_min = najzimniej_w_nocy(pogoda, teraz_ms, strefa)
    sezon_grzewczy = datetime.fromtimestamp(teraz_ms / 1000, strefa).month in SEZON_GRZEWCZY
    poczatek = teraz_ms - OKNO_ODCZYTOW_MS
    pokoje = {}
    for dev in pokoje_z_manifestu(urzadzenia):
        wpis = urzadzenia[dev]
        rodzaj = _rodzaje(wpis)
        moje = [w for w in wiersze if w.get("device_id") == dev and w["ms"] >= poczatek]
        temp = Szereg([(w["ms"], v) for w in moje if rodzaj.get(w.get("code")) == "temp"
                       and (v := _liczba(w.get("value"))) is not None])
        wilg = Szereg([(w["ms"], v) for w in moje if rodzaj.get(w.get("code")) == "hum"
                       and (v := _liczba(w.get("value"))) is not None])
        klimat = [w["ms"] for w in moje if rodzaj.get(w.get("code")) in ("temp", "hum")
                  and _liczba(w.get("value")) is not None]
        baterie = [str(w.get("value")).strip().lower() for w in moje if rodzaj.get(w.get("code")) == "battery"]
        bateria = baterie[-1] if baterie and baterie[-1] in BATERIE else None
        pokoje[dev] = {
            "przewietrz": przewietrz(wilg, temp, dwor, teraz_ms),
            "okno": okno(temp, wilg, dwor_teraz, teraz_ms) if sezon_grzewczy and dev not in bez_okna else None,
            "noc": noc_pokoju(temp, wilg, t_min, teraz_ms, strefa),
            "milczy_od": (None if dev in nieodswiezone else
                          milczy_od(max(klimat) if klimat else None, _ms(wpis.get("pobrane_do")),
                                    teraz_ms, poczatek)),
            "bateria": bateria,
        }
    return {"updated": iso(teraz_ms), "pokoje": pokoje}


def opisy_pokoi(urzadzenia: dict, konfig: dict | None) -> dict[str, dict]:
    """Nazwa i odmiany pokoju do zdań: z pokoje.json po identyfikatorze czujnika, a gdy
    go tam nie ma — z nazwy w manifeście (slug z nazwy, odmiany = nazwa). Zmiana nazwy
    w aplikacji Tuya nie psuje wtedy adresów ani zdań (D13). `okno`: czy pokój ma okno —
    pokój z pokoje.json bez strony świata nie ma; pokoju spoza pliku nie znamy, więc ma."""
    wpisy = (konfig or {}).get("pokoje") if isinstance(konfig, dict) else None
    wpisy = wpisy if isinstance(wpisy, dict) else {}
    out = {}
    for dev in pokoje_z_manifestu(urzadzenia):
        nazwa_tuya = str((urzadzenia[dev] or {}).get("name") or dev)
        k = wpisy.get(dev) if isinstance(wpisy.get(dev), dict) else {}
        nazwa = k.get("nazwa") if isinstance(k.get("nazwa"), str) and k.get("nazwa") else nazwa_tuya
        odm = {p: (k[p] if isinstance(k.get(p), str) and k.get(p) else _mala(nazwa))
               for p in ("dop", "bier", "miejsc")}
        slug = k.get("slug") if isinstance(k.get("slug"), str) and re.fullmatch(r"[a-z0-9-]+", k["slug"]) \
            else (_slug(nazwa) or "pokoj")
        okno = isinstance(k.get("okno"), str) if k else True
        out[dev] = {"nazwa": nazwa, "slug": slug, **odm, "okno": okno}
    return out


# ---------- planer powiadomień ----------

def _epizod(wartosc) -> dict | None:
    if not isinstance(wartosc, dict) or not isinstance(wartosc.get("od"), str):
        return None
    return {"od": wartosc["od"], "wyslano": wartosc.get("wyslano") if isinstance(wartosc.get("wyslano"), str) else None,
            "na_sucho": wartosc.get("na_sucho") if isinstance(wartosc.get("na_sucho"), str) else None}


def _powody(pozycja: dict) -> list[str]:
    """Powody czujnika z pozycji kolejki — plik jest publiczny i edytowalny, więc bez ufania typom."""
    powody = pozycja.get("powody")
    return [p for p in powody if isinstance(p, str)] if isinstance(powody, list) else []


def _ustawienia(ustawienia) -> dict:
    """Ustawienia obu telefonów; None albo brak telefonu to telefony.DOMYSLNE. Słownik idzie
    przez ten sam parser co zmienna repozytorium, więc zła wartość pola daje domyślną,
    a nie wyjątek w środku reguł."""
    zrodlo = ustawienia if isinstance(ustawienia, dict) else {}
    wynik = {}
    for t in telefony.TELEFONY:
        u = zrodlo.get(t)
        try:
            wynik[t] = telefony.ustawienia_telefonu(json.dumps(u)) if isinstance(u, dict) else dict(telefony.DOMYSLNE)
        except (TypeError, ValueError):
            wynik[t] = dict(telefony.DOMYSLNE)
    return wynik


def _znacznik(regula: str, slugi: list[str]) -> str:
    """`przewietrz-lazienka`: następne powiadomienie o tym samym pokoju zastępuje na
    telefonie poprzednie. Najwyżej 32 znaki (nagłówek Topic Web Push)."""
    return "-".join([regula] + slugi)[:32].rstrip("-")


def _adres(slugi: list[str]) -> str:
    return "#" + slugi[0] if len(slugi) == 1 else "#dom"


def _linia_przewietrz(o: dict, p: dict, teraz_ms: int) -> str:
    od = _ms(p["od"]) or teraz_ms
    godz = max(1, math.floor((teraz_ms - od) / GODZ + 0.5))
    # Granica po zaokrągleniu nie może zrównać się z wilgotnością („63%, za wilgotno
    # powyżej 63%") — wtedy z jednym miejscem po przecinku. Porównanie po tym samym
    # zaokrągleniu co tekst: `round` (do parzystej) przy granicy 62,5 i wilgotności 63
    # uznałby „63 > 62" i napisał „powyżej 63%".
    gr = _pl(p["granica"], 0) if _w_gore(p["wilg"]) > _w_gore(p["granica"]) else _pl(p["granica"], 1)
    return f"{o['nazwa']}: {_pl(p['wilg'], 0)}% od {godz} godz., za wilgotno powyżej {gr}%."


def _tekst_przewietrz(opisy: list[dict], stany: list[dict], teraz_ms: int) -> tuple[str, str]:
    linie = [_linia_przewietrz(o, s, teraz_ms) for o, s in zip(opisy, stany)]
    if len(opisy) == 1:
        return f"Przewietrz {opisy[0]['bier']}", linie[0]
    return "Przewietrz: " + ", ".join(_mala(o["nazwa"]) for o in opisy), "\n".join(linie)


def _tekst_przed_snem(opisy: list[dict], noce: list[dict]) -> tuple[str, str]:
    tytul = "Przewietrz przed snem: " + ", ".join(_mala(o["nazwa"]) for o in opisy)
    linie = [f"{o['nazwa']}: w nocy za wilgotno od ok. {_pl(n['granica'], 0)}%, "
             f"zwykle masz do {_pl(n['zwykle'], 0)}%." for o, n in zip(opisy, noce)]
    return tytul, "\n".join(linie)


def _tekst_okno(opisy: list[dict], okna: list[dict], strefa: ZoneInfo) -> tuple[str, str]:
    def zdanie(o: dict) -> str:
        return (f"od {_godzina(_ms(o['od']) or 0, strefa)} spadło {_pl(o['spadek'])}° "
                f"(z {_pl(o['przed'])} do {_pl(o['teraz'])}°).")
    if len(opisy) == 1:
        z = zdanie(okna[0])
        return f"Zamknij okno w {opisy[0]['miejsc']}?", z[:1].upper() + z[1:]
    return ("Zamknij okna? " + _lista_slow([_mala(o["nazwa"]) for o in opisy]),
            "\n".join(f"{o['nazwa']}: {zdanie(w)}" for o, w in zip(opisy, okna)))


def _linia_czujnika(o: dict, powod: str, stan_pokoju: dict, epizod: dict, strefa: ZoneInfo) -> str:
    if powod == "cisza":
        od = _ms(stan_pokoju.get("milczy_od")) or _ms(epizod.get("od"))
        if od is None:
            return f"{o['nazwa']}: czujnik milczy."
        kiedy = datetime.fromtimestamp(od / 1000, strefa)
        return f"{o['nazwa']}: ostatni odczyt {kiedy.day}.{kiedy.month:02d} o {_godzina(od, strefa)}."
    return f"{o['nazwa']}: bateria na wyczerpaniu, wymień ogniwo."


def _tekst_czujniki(opisy: list[dict], powody: list[list[str]], linie: list[list[str]]) -> tuple[str, str]:
    if len(opisy) == 1:
        o = opisy[0]
        tytul = (f"Czujnik w {o['miejsc']} milczy" if "cisza" in powody[0]
                 else f"Słaba bateria czujnika w {o['miejsc']}")
    else:
        tytul = "Czujniki: " + ", ".join(_mala(o["nazwa"]) for o in opisy)
    return tytul, "\n".join(x for ls in linie for x in ls)


def zaplanuj_powiadomienia(stan: dict, poprzednie: dict | None, teraz_ms: int, strefa: ZoneInfo,
                           tryb: str, przebieg: str, ustawienia: dict | None = None,
                           opisy: dict | None = None, nieodswiezone=()) -> dict:
    """Zwraca NOWĄ zawartość data/dom/powiadomienia.json.

    `stan` — wynik stan_domu() z tego przebiegu (te same reguły, które pokazuje strona),
    `poprzednie` — dotychczasowa zawartość pliku albo None, `tryb` — "wlaczone" albo
    cokolwiek innego (na sucho), `przebieg` — "$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT",
    `ustawienia` — {"android": {...}, "iphone": {...}} z telefony.py (None = domyślne obu),
    `opisy` — nazwy i odmiany pokoi (opisy_pokoi), `nieodswiezone` — identyfikatory, których
    ten przebieg nie pobrał. Wszystko liczy się od `teraz_ms`, a bez zmian w stanie wynik
    jest ten sam: plik nie zmienia się co przebieg.

    Reguły (BRIEF5, pkt 3):
    - **przewietrz** — epizod pokoju od pierwszego przebiegu z `przewietrz`; jedna wysyłka
      na epizod, nie we wspólnej nocy wszystkich telefonów; telefon w ciszy dostaje pozycję
      w kolejce. Koniec epizodu, gdy reguła zgaśnie w przebiegu, który pokój pobrał.
      Najwyżej 2 wpisy na pokój na lokalną dobę.
    - **przed-snem** — w oknie przed ciszą danego telefonu, raz na noc, pokoje z `noc.ostrz`
      i z oknem. Nigdy do kolejki: rano byłoby bezużyteczne.
    - **okno** — raz na epizod, tylko do telefonów poza ciszą; gdy wszyscy chętni są
      w ciszy, epizod czeka (rano, jeśli trwa, pójdzie). Nigdy do kolejki.
    - **czujniki** — milczy i słaba bateria (trzymana do „high"), raz na powód.
    - **na sucho** — te same decyzje, wpisy `na_sucho: true`, w stanie znacznik `na_sucho`.
      Pierwszy przebieg w trybie `wlaczone` tylko ustawia `wlaczone_od` — bez powitania,
      bo witają już rośliny.
    """
    na_sucho = tryb != "wlaczone"
    tryb = "na-sucho" if na_sucho else "wlaczone"
    poprz = poprzednie if isinstance(poprzednie, dict) else {}
    ustawienia = _ustawienia(ustawienia)
    lokalnie = datetime.fromtimestamp(teraz_ms / 1000, strefa)
    dzis = lokalnie.date()
    noc = telefony.noc_wszystkich(ustawienia, lokalnie)
    teraz_iso = iso(teraz_ms)
    znacznik_wysylki = "na_sucho" if na_sucho else "wyslano"
    pokoje_stan = stan.get("pokoje") if isinstance(stan, dict) and isinstance(stan.get("pokoje"), dict) else {}
    opisy = dict(opisy or {})
    for dev in pokoje_stan:
        opisy.setdefault(dev, {"nazwa": dev, "slug": _slug(dev) or "pokoj", "dop": dev, "bier": dev, "miejsc": dev})

    historia = []
    for w in poprz.get("historia") if isinstance(poprz.get("historia"), list) else []:
        ts = _ms(w.get("ts")) if isinstance(w, dict) else None
        if ts is not None and teraz_ms - ts <= DNI_HISTORII * DOBA:
            historia.append(w)

    if na_sucho:
        wlaczone_od = None
    elif poprz.get("tryb") == "wlaczone" and isinstance(poprz.get("wlaczone_od"), str):
        wlaczone_od = poprz["wlaczone_od"]
    else:
        wlaczone_od = teraz_iso

    def wyslane(ep: dict | None) -> bool:
        # na sucho liczą się oba znaczniki (tak by było przy włączonej wysyłce), po włączeniu
        # tylko prawdziwe wysyłki — epizod „wysłany na sucho" pójdzie naprawdę
        return bool(ep and (ep.get("wyslano") or (na_sucho and ep.get("na_sucho"))))

    def dzis_przewietrz(nazwa: str) -> int:
        n = 0
        for w in historia:
            if (w.get("regula") == "przewietrz" and not w.get("odlozone")
                    and nazwa in (w.get("pokoje") if isinstance(w.get("pokoje"), list) else [])
                    and (na_sucho or w.get("na_sucho") is False)
                    and datetime.fromtimestamp(_ms(w["ts"]) / 1000, strefa).date() == dzis):
                n += 1
        return n

    # Stan pokoi nieobecnych w tym przebiegu zostaje bez zmian.
    stare = poprz.get("stan_regul") if isinstance(poprz.get("stan_regul"), dict) else {}
    stan_regul = {d: v for d, v in stare.items() if isinstance(v, dict)}
    do_przewietrz, do_okna, do_czujnikow = [], [], []
    for dev, p in pokoje_stan.items():
        if not isinstance(p, dict):
            continue
        przed = stan_regul.get(dev) or {}
        pobrany = dev not in nieodswiezone

        ep = _epizod(przed.get("przewietrz"))
        if p.get("przewietrz"):
            ep = ep or {"od": teraz_iso, "wyslano": None, "na_sucho": None}
            if not wyslane(ep) and not noc and dzis_przewietrz(opisy[dev]["nazwa"]) < MAKS_PRZEWIETRZ_NA_DOBE:
                do_przewietrz.append(dev)
        elif pobrany:
            ep = None
        moja = {"przewietrz": ep}

        ep = _epizod(przed.get("okno"))
        if p.get("okno"):
            ep = ep or {"od": teraz_iso, "wyslano": None, "na_sucho": None}
            if not wyslane(ep):
                do_okna.append(dev)
        elif pobrany:
            ep = None
        moja["okno"] = ep

        czujniki_przed = przed.get("czujniki") if isinstance(przed.get("czujniki"), dict) else {}
        czujniki = {}
        cisza = _epizod(czujniki_przed.get("cisza"))
        if p.get("milczy_od"):
            czujniki["cisza"] = cisza or {"od": p["milczy_od"], "wyslano": None, "na_sucho": None}
        elif not pobrany and cisza:
            czujniki["cisza"] = cisza          # nieodświeżony nie kończy epizodu (D5)
        # Bateria na granicy low/middle skacze, a każdy powrót do „low" dawałby nowy alarm
        # (u roślin 28 zamiast 1, przegląd 9.10). Znacznik trzyma się do „high".
        bateria = _epizod(czujniki_przed.get("bateria"))
        if p.get("bateria") == "low" or (bateria and p.get("bateria") != "high"):
            czujniki["bateria"] = bateria or {"od": teraz_iso, "wyslano": None, "na_sucho": None}
        nowe = [powod for powod, e in czujniki.items() if not wyslane(e)]
        if nowe and not noc:
            do_czujnikow.append(dev)
        moja["czujniki"] = czujniki
        stan_regul[dev] = moja

    tel = telefony.stan_telefonow(poprz.get("telefony"))
    for t in telefony.TELEFONY:
        tel[t]["odlozone"] = telefony.przytnij_odlozone(tel[t]["odlozone"], teraz_ms, _ms)
        przed_snem = tel[t].get("przed_snem")
        tel[t]["przed_snem"] = przed_snem if isinstance(przed_snem, str) else None

    swieze, zajete = [], {w.get("id") for w in historia if isinstance(w.get("id"), str)}

    def wpis(regula: str, devs: list[str], tytul: str, tresc: str, tag: str, komu: list[str],
             odlozone: bool = False) -> dict:
        baza = datetime.fromtimestamp(teraz_ms / 1000, timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + regula
        ident, n = baza, 1
        while ident in zajete:           # „Re-run" w tej samej sekundzie albo kilka wpisów reguły
            n += 1
            ident = f"{baza}-{n}"
        zajete.add(ident)
        w = {"id": ident, "ts": teraz_iso, "przebieg": str(przebieg), "regula": regula,
             "pokoje": [opisy[d]["nazwa"] for d in devs], "tytul": tytul, "tresc": tresc, "tag": tag,
             "url": _adres([opisy[d]["slug"] for d in devs]), "na_sucho": na_sucho, "telefony": komu}
        if odlozone:
            w["odlozone"] = True
        return w

    def slugi(devs):
        return [opisy[d]["slug"] for d in devs]

    # przewietrz
    komu_przewietrz = []
    if do_przewietrz:
        komu, odloz = telefony.adresaci("przewietrz", ustawienia, lokalnie)
        tytul, tresc = _tekst_przewietrz([opisy[d] for d in do_przewietrz],
                                         [pokoje_stan[d]["przewietrz"] for d in do_przewietrz], teraz_ms)
        swieze.append(wpis("przewietrz", do_przewietrz, tytul, tresc, _znacznik("przewietrz", slugi(do_przewietrz)),
                           komu))
        komu_przewietrz = komu
        for d in do_przewietrz:
            stan_regul[d]["przewietrz"][znacznik_wysylki] = teraz_iso
            telefony.odloz(tel, odloz, {"regula": "przewietrz", "obiekt": d, "ts": teraz_iso})

    # przed snem: okno przed ciszą każdego telefonu, raz na noc, nigdy do kolejki
    noc_dzis = telefony.data_nocy(lokalnie)
    # Tylko pokoje z oknem: w łazience nie ma czego otworzyć (drzwi i tak stoją otwarte), więc
    # wieczorne ostrzeżenie było codziennym przypomnieniem bez rady — 9 wieczorów na 10
    # (12–21.10). Łazienka zostaje na ekranie (stan.json), na telefon idzie tylko to, co da się zrobić.
    ostrz = [d for d, p in pokoje_stan.items() if isinstance(p, dict) and isinstance(p.get("noc"), dict)
             and p["noc"].get("ostrz") and p["noc"].get("noc") == noc_dzis and opisy[d].get("okno", True)]
    odbiorcy = [t for t in telefony.TELEFONY if ustawienia[t].get("przewietrz")
                and telefony.przed_snem(ustawienia[t], lokalnie) and not telefony.w_ciszy(ustawienia[t], lokalnie)
                and tel[t]["przed_snem"] != noc_dzis]
    if ostrz and odbiorcy:
        tytul, tresc = _tekst_przed_snem([opisy[d] for d in ostrz], [pokoje_stan[d]["noc"] for d in ostrz])
        swieze.append(wpis("przed-snem", ostrz, tytul, tresc, "przed-snem", odbiorcy))
        for t in odbiorcy:
            tel[t]["przed_snem"] = noc_dzis

    # okno: tylko poza ciszą; gdy chętni śpią, epizod czeka na nich
    if do_okna:
        komu, odloz = telefony.adresaci("okno", ustawienia, lokalnie)
        if komu or not odloz:
            tytul, tresc = _tekst_okno([opisy[d] for d in do_okna], [pokoje_stan[d]["okno"] for d in do_okna], strefa)
            swieze.append(wpis("okno", do_okna, tytul, tresc, _znacznik("okno", slugi(do_okna)), komu))
            for d in do_okna:
                stan_regul[d]["okno"][znacznik_wysylki] = teraz_iso

    def tekst_czujnikow(devs: list[str]) -> tuple[str, str]:
        powody = [list(stan_regul[d]["czujniki"]) for d in devs]
        linie = [[_linia_czujnika(opisy[d], pw, pokoje_stan[d], stan_regul[d]["czujniki"][pw], strefa)
                  for pw in ps] for d, ps in zip(devs, powody)]
        return _tekst_czujniki([opisy[d] for d in devs], powody, linie)

    # czujniki: wpis niesie wszystkie trwające powody pokoju — ten sam znacznik podmienia na
    # telefonie poprzedni alarm, więc nieprzeczytana „bateria" nie może zniknąć pod „milczy"
    komu_czujniki = []
    if do_czujnikow:
        komu, odloz = telefony.adresaci("czujniki", ustawienia, lokalnie)
        tytul, tresc = tekst_czujnikow(do_czujnikow)
        swieze.append(wpis("czujniki", do_czujnikow, tytul, tresc, _znacznik("czujniki", slugi(do_czujnikow)),
                           komu))
        komu_czujniki = komu
        for d in do_czujnikow:
            nowe = [pw for pw, e in stan_regul[d]["czujniki"].items() if not wyslane(e)]
            for pw in nowe:
                stan_regul[d]["czujniki"][pw][znacznik_wysylki] = teraz_iso
            for t in odloz:
                kolejka = tel[t]["odlozone"]
                stara = next((p for p in kolejka if p.get("regula") == "czujniki" and p.get("obiekt") == d), None)
                if stara is not None:
                    stara["powody"] = sorted(set(_powody(stara)) | set(nowe))
                else:
                    kolejka.append({"regula": "czujniki", "obiekt": d, "ts": teraz_iso, "powody": sorted(nowe)})

    # Dostarczenie odłożonych: pierwszy przebieg po końcu ciszy telefonu. Pozycje sprawdza
    # się na świeżym stanie, nieaktualne odpadają, a kolejka czyści się w tym samym wyniku
    # („co najwyżej raz": po przegranym wyścigu przebieg liczy się na drzewie zwycięzcy,
    # gdzie kolejka jest już pusta).
    odlozone = []
    for t in telefony.TELEFONY:
        u = ustawienia[t]
        if telefony.w_ciszy(u, lokalnie) or not tel[t]["odlozone"]:
            continue
        przewietrz_t, czujniki_t = [], []
        for poz in tel[t]["odlozone"]:
            d, regula = poz.get("obiekt"), poz.get("regula")
            if not isinstance(d, str) or d not in pokoje_stan or not u.get(KLUCZ_USTAWIEN.get(regula, regula)):
                continue
            if regula == "przewietrz":
                # ten przebieg i tak wysyła temu telefonowi świeży wpis o tym pokoju
                if pokoje_stan[d].get("przewietrz") and not (d in do_przewietrz and t in komu_przewietrz) \
                        and d not in przewietrz_t:
                    przewietrz_t.append(d)
            elif regula == "czujniki":
                trwa = set(_powody(poz)) & set(stan_regul[d]["czujniki"])
                if trwa and not (d in do_czujnikow and t in komu_czujniki) and d not in czujniki_t:
                    czujniki_t.append(d)
        tel[t]["odlozone"] = []
        if przewietrz_t:
            tytul, tresc = _tekst_przewietrz([opisy[d] for d in przewietrz_t],
                                             [pokoje_stan[d]["przewietrz"] for d in przewietrz_t], teraz_ms)
            odlozone.append(("przewietrz", przewietrz_t, tytul, tresc, _znacznik("przewietrz", slugi(przewietrz_t)), t))
        if czujniki_t:
            tytul, tresc = tekst_czujnikow(czujniki_t)
            odlozone.append(("czujniki", czujniki_t, tytul, tresc, _znacznik("czujniki", slugi(czujniki_t)), t))
    # ta sama treść dla obu telefonów to jeden wpis
    scalone: list[list] = []
    for regula, devs, tytul, tresc, tag, t in odlozone:
        para = next((s for s in scalone if s[:5] == [regula, devs, tytul, tresc, tag]), None)
        if para:
            para[5].append(t)
        else:
            scalone.append([regula, devs, tytul, tresc, tag, [t]])
    dostarczone = [wpis(r, d, ty, tr, tg, k, odlozone=True) for r, d, ty, tr, tg, k in scalone]

    return {"tryb": tryb, "wlaczone_od": wlaczone_od, "historia": historia + dostarczone + swieze,
            "stan_regul": stan_regul, "telefony": tel}
