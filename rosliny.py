"""
Czujniki w doniczkach — obliczenia bez sieci i bez plików.

Kolektor (fetch.py) pobiera odczyty, zapisuje je do data/rosliny/ i woła stąd funkcje,
które z odczytów robią to, co pokazuje zakładka „Rośliny" i z czego biorą się
powiadomienia: przerzedzone serie, dobową sumę światła, wykryte podlania, nauczone
progi i werdykt. Wszystko tu jest czystą funkcją od danych, żeby dało się to sprawdzić
testem bez atrapy Tuya — i żeby strona niczego nie liczyła drugi raz: werdykt liczy
Python, strona go tylko wyświetla (żadnych nowych bliźniaczych stałych JS/Python).

Plan, pomiary i powody progów: ROSLINY.md.
"""

from __future__ import annotations

import bisect
import copy
import json
import math
import re
import statistics
import unicodedata
from collections import deque
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import telefony

GODZ = 3600 * 1000
DOBA = 24 * GODZ

# Rodzaje odczytów czujnika w doniczce. Kody chmury Tuya do nich wpisuje się jawnie
# w rosliny.json — classify() z fetch.py wzięłoby glebę (`humidity`) i powietrze
# (`env_humidity`) za to samo, a światło (`illumiance`) by odrzuciło.
RODZAJE = ("gleba", "temp", "wilg", "swiatlo", "bateria", "alarm")
LICZBOWE = ("gleba", "temp", "wilg", "swiatlo")

# Progi wyjściowe z literatury — [zgadnięte], patrz ROSLINY.md, „Uczenie progów".
# R = (gleba − sucho) ÷ (szczyt − sucho): 0 to sonda w suchym, 1 to ziemia zaraz po
# porządnym podlaniu. `granice` przycinają próg nauczony z podlań właściciela, żeby nauka
# nie utrwaliła nawyku przelewania ani przesuszania. `swiatlo_lxh` to dzienna potrzeba
# światła w luksogodzinach (dla światła dziennego 1 mol/m²/dobę ≈ 15 000 lx·h).
#
# `nazwa_pelna`, `temp_zakres` i `wilg_zakres` to stałe karty rośliny (zatwierdzony
# projekt aplikacji). Idą do stan.json, żeby strona nie miała ich drugiej kopii w JS.
# `swiatlo_za_duzo_lx` (próg „odsuń od okna") jest uśpiony: czujnik mierzy 0–10 000 lx
# (specyfikacja `illumiance`), więc progi z projektu (fikus 40 000, azalia 20 000,
# skrzydłokwiat 10 000) przy warunku „>" nigdy by nie zadziałały, a ROSLINY.md przenosi
# „za dużo słońca" na wiosnę, po zmierzeniu, przy ilu lx czujnik się nasyca. Gałąź reguły
# istnieje i ma test na sztucznym progu.
GATUNKI = {
    "fikus": {"prog": 0.45, "prog_zima": 0.35, "pilne": None, "granice": (0.20, 0.55),
              "swiatlo_lxh": 20000,
              "nazwa_pelna": "Fikus 'Ginseng' (Ficus microcarpa)", "temp_zakres": (16, 24),
              "wilg_zakres": (40, 70), "swiatlo_za_duzo_lx": None,
              # ROSLINY.md, „Rady": po każdym przestawieniu gubi liście przez 2–4 tygodnie,
              # więc „nie przestawiać na ślepo" — raz, do najjaśniejszego miejsca
              "rada_przestaw": "Fikus gubi liście po każdej przeprowadzce — przestaw raz, "
                               "w najjaśniejsze miejsce."},
    "skrzydlokwiat": {"prog": 0.60, "prog_zima": 0.50, "pilne": None, "granice": (0.40, 0.70),
                      "swiatlo_lxh": 10000,
                      "nazwa_pelna": "Skrzydłokwiat (Spathiphyllum)", "temp_zakres": (18, 27),
                      "wilg_zakres": (50, 80), "swiatlo_za_duzo_lx": None},
    "azalia": {"prog": 0.75, "prog_zima": 0.75, "pilne": 0.60, "granice": (0.60, 0.85),
               "swiatlo_lxh": 28000,
               "nazwa_pelna": "Azalia doniczkowa (Rhododendron simsii), forma drzewka",
               "temp_zakres": (10, 18), "wilg_zakres": (50, 80), "swiatlo_za_duzo_lx": None,
               # przesuszony torf nie przyjmuje wody z góry — ratunek z ROSLINY.md, „Rady"
               "rada_pilne": "Wyjmij czujnik, wyjmij plastikową doniczkę z osłonki i zanurz ją "
                             "w letniej wodzie, aż przestaną lecieć bąbelki (15–30 min). Odsącz, "
                             "wylej wodę z osłonki i wbij czujnik w to samo miejsce."},
}
ZIMA = {10, 11, 12, 1, 2}

# Ile czasu po ostatnim zostawionym odczycie trzymamy wiersz, nawet jeśli wartość się nie
# zmieniła. W godzinie parowania gleba przychodziła co ok. 30 s ze stałą wartością
# (pomiar 8.10), więc bez przerzedzania byłoby do 3000 wierszy na dobę na czujnik,
# a godzinny wiersz wystarcza, żeby odróżnić „stoi" od „milczy".
PRZERZEDZENIE_MS = GODZ
# Gleba skacząca 10↔11 to nie zmiana: bez tego każde drgnięcie zostawałoby w CSV
# (przegląd 8.10: ok. 900 wierszy na dobę zamiast 25). Tylko dla gleby — alarm to 1/0.
MARTWA_STREFA_GLEBY = 1.0
# Dłużej niż tyle bez odczytu to cisza, a nie stan trwający — w szeregu godzinowym
# i w sumie światła nie przeciągamy ostatniej wartości dalej. Noc 8/9.10 (czujniki
# obok siebie, próbkowanie 1200 s): światło przychodziło co 61–116 min, bo czujnik nie
# wysyła każdego kodu przy każdym wybudzeniu, a wilgotność powietrza raz po 2 godz.
# 1 min. Dwie godziny to było na styk — w doniczce, przy słabszym zasięgu, dziury
# zjadałyby pokrycie doby i wyłączały regułę „za ciemno".
MAKS_PRZERWA_MS = 3 * GODZ
# Skok gleby o co najmniej tyle punktów w ciągu OKNO_PODLANIA_MS to podlanie.
SKOK_PODLANIA = 10.0
OKNO_PODLANIA_MS = 2 * GODZ
# Szczyt po podlaniu: mediana odczytów w tym oknie po wykrytym podlaniu, kiedy woda już
# spłynęła, a ziemia jeszcze nie zaczęła schnąć.
SZCZYT_OD_MS, SZCZYT_DO_MS = 2 * GODZ, 6 * GODZ
# Przed podlaniem: mediana z tego okna przed wykrytym skokiem — nie najniższy odczyt
# tuż przed nim, bo przy zanurzaniu azalii sonda leży wtedy w powietrzu.
PRZED_OD_MS, PRZED_DO_MS = 2 * GODZ, 6 * GODZ
# Nauka startuje godzinę po wbiciu sondy: wbicie (z powietrza do wilgotnej ziemi) to
# skok jak przy podlaniu, a godzina wbicia podana z pamięci bywa o kilka minut za wczesna.
ZAPAS_PO_WBICIU_MS = GODZ
# Gleba najwyżej tyle nad „sucho" to sonda w powietrzu albo ziemia sucha jak pieprz;
# rozstrzyga, czy spadek był nagły (sonda wyjęta), czy powolny (schnięcie).
ZAPAS_SUCHO = 3.0
# Sonda wyjęta na krótko (zanurzanie azalii trwa ok. 30 min) to nie sprawa dla watchdoga.
ZGLOS_WYJETA_MS = 2 * GODZ
# Cisza dłuższa niż to — czujnik wymaga uwagi.
CISZA_MS = 12 * GODZ
DNI_HISTORII = 30
# Nauka patrzy tyle dni wstecz: trzy podlania fikusa zimą to 6–8 tygodni.
DNI_NAUKI = 60

# Doba z mniejszym pokryciem pomiarem to nie „pełna doba": doba zmierzona w jednej czwartej
# wyglądałaby na ciemną. Jedyny taki próg w projekcie — korzystają z niego ocena światła
# (karta rośliny i reguła „przestaw") i podsumowanie tygodnia; strona dostaje gotowe
# `swiatlo_pelne_doby` i `swiatlo_ocena`, a nie próg.
POKRYCIE_PELNEJ_DOBY = 0.8
# Ocena światła dopiero z tylu pełnych dób, z tych samych progów co zatwierdzony projekt
# karty: poniżej 0,35 potrzeby „przestaw bliżej okna", poniżej 0,6 na karcie tylko „mało
# światła". Koniec epizodu „przestaw" dopiero przy 0,45, bo suma światła skacze z doby na
# dobę: skrzydłokwiat miał 9 i 10.10 2670 i 5138 lx·h, czyli 0,27 i 0,51 potrzeby
# (stan.json 11.10) — bez histerezy epizod na granicy otwierałby się co parę dni od nowa.
DOBY_OCENY_SWIATLA = 3
SWIATLO_JASNIEJ_U = 0.35
SWIATLO_MALO_U = 0.6
PRZESTAW_KONIEC_U = 0.45
KIERUNKI_PRZESTAW = ("jasniej", "ciemniej")


def _ms(ts: str) -> int | None:
    try:
        return int(datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _liczba(tekst) -> float | None:
    try:
        wartosc = float(tekst)
    except (TypeError, ValueError):
        return None
    # NaN to brak, a nieskończoność też: JSON.parse w przeglądarce odrzuca Infinity
    return wartosc if math.isfinite(wartosc) else None


def _ms_ze_strefa(ts) -> int | None:
    """Data z godziną i jawną strefą. Sama data albo godzina bez strefy to None:
    pierwszą czyta się jako północ UTC, drugą w strefie maszyny (w Actions to UTC,
    a nie Warszawa) — i jedno, i drugie po cichu przesuwa wbicie sondy."""
    try:
        chwila = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if chwila.tzinfo is None or "T" not in str(ts):
        return None
    return int(chwila.timestamp() * 1000)


def _calk(x: float) -> int:
    """Liczba całkowita połówką w górę — jak `liczba()` na stronie (Intl.NumberFormat,
    tryb halfExpand) i Math.round dla liczb dodatnich (wszystkie tutaj takie są).

    Format Pythona (`f"{18.5:.0f}"`) zaokrągla połówkę do parzystej: u = 0,185 ze stan.json
    dawało w powiadomieniu „18%", a na karcie „19%" (przegląd, C1). Liczy się z dziesiętnego
    zapisu liczby (`repr`, ten sam co w JSON-ie), a nie z jej przybliżenia binarnego."""
    return int(Decimal(repr(float(x))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _proc_swiatla(u: float) -> int:
    """Procent potrzebnego światła z u ZAPISANEGO w stan.json (trzy miejsca po przecinku):
    karta i treść „przestaw" pokazują tę samą liczbę. Z nieprzyciętego u 0,18451 wyszłoby
    18%, a z zapisanego 0,185 — 19%. Mnożenie w Decimal, bo 0,185 · 100 w binarnym float
    bywa 18,499…"""
    return int((Decimal(repr(float(u))) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _lokalnie(ms: int, strefa: ZoneInfo) -> str:
    return datetime.fromtimestamp(ms / 1000, strefa).strftime("%d.%m %H:%M")


def wczytaj_konfiguracje(tekst: str) -> list[dict]:
    """rosliny.json → lista roślin. Każdy błąd to ValueError z polskim opisem.

    Plik jest ręczny (przepisuje się do niego kody z „Pokaż urządzenia w Tuya"), więc
    literówka jest realna. Kolektor łapie ten błąd, zapisuje go w stanie roślin i zbiera
    pokoje dalej — patrz zbierz_rosliny() w fetch.py.
    """
    try:
        dane = json.loads(tekst)
    except ValueError as err:
        raise ValueError(f"rosliny.json to nie jest poprawny JSON: {err}") from None
    lista = dane.get("rosliny") if isinstance(dane, dict) else None
    if not isinstance(lista, list):
        raise ValueError("rosliny.json: brak listy „rosliny\"")
    out, widziane, nazwy = [], set(), set()
    for i, r in enumerate(lista, 1):
        if not isinstance(r, dict):
            raise ValueError(f"rosliny.json: wpis {i} nie jest obiektem")
        czujnik, nazwa, gatunek = r.get("czujnik"), r.get("nazwa"), r.get("gatunek")
        if not czujnik or not nazwa or not isinstance(czujnik, str) or not isinstance(nazwa, str):
            raise ValueError(f"rosliny.json: wpis {i} bez „czujnik\" albo „nazwa\" (tekstem)")
        if czujnik in widziane:
            raise ValueError(f"rosliny.json: czujnik {czujnik} wpisany dwa razy")
        # Nazwa to klucz stanu reguł i adresu w aplikacji (#fikus, slug z nazwy) — dwie
        # takie same i druga roślina byłaby nie do wybrania.
        if nazwa in nazwy:
            raise ValueError(f"rosliny.json: roślina {nazwa} wpisana dwa razy")
        widziane.add(czujnik)
        nazwy.add(nazwa)
        if not isinstance(gatunek, str) or gatunek not in GATUNKI:
            raise ValueError(f"rosliny.json: {nazwa} — nieznany gatunek {gatunek!r} "
                             f"(znane: {', '.join(GATUNKI)})")
        kody = r.get("kody")
        if not isinstance(kody, dict) or not kody.get("gleba"):
            raise ValueError(f"rosliny.json: {nazwa} — brak „kody\" z kodem gleby")
        if not all(isinstance(v, str) and v for v in kody.values()):
            raise ValueError(f"rosliny.json: {nazwa} — kody chmury muszą być niepustym tekstem")
        obce = set(kody) - set(RODZAJE)
        if obce:
            raise ValueError(f"rosliny.json: {nazwa} — nieznane rodzaje kodów: {', '.join(sorted(obce))}")
        if len(set(kody.values())) != len(kody):
            raise ValueError(f"rosliny.json: {nazwa} — jeden kod chmury wpisany pod dwa rodzaje")
        sucho = r.get("sucho")
        if sucho is not None and (isinstance(sucho, bool) or _liczba(sucho) is None):
            raise ValueError(f"rosliny.json: {nazwa} — „sucho\" musi być skończoną liczbą")
        od = r.get("od")
        if od is not None and _ms_ze_strefa(od) is None:
            raise ValueError(f"rosliny.json: {nazwa} — „od\" to nie data ISO z godziną i strefą "
                             f"(np. 2026-10-09T08:30:00+02:00)")
        pokoj = r.get("pokoj")
        if pokoj is not None and not isinstance(pokoj, str):
            raise ValueError(f"rosliny.json: {nazwa} — „pokoj\" to identyfikator tekstem")
        pomin = r.get("pomin_podlania") or []
        if not isinstance(pomin, list) or not all(
                isinstance(x, dict) and _ms_ze_strefa(x.get("kiedy")) is not None for x in pomin):
            raise ValueError(f"rosliny.json: {nazwa} — „pomin_podlania\" to lista "
                             f"{{\"kiedy\": data ISO z godziną i strefą, \"dlaczego\": opis}}")
        out.append({
            "czujnik": str(czujnik), "nazwa": str(nazwa), "gatunek": gatunek,
            "pokoj": pokoj, "kody": {k: str(v) for k, v in kody.items()},
            "sucho": _liczba(sucho), "od": od,
            "pomin_podlania": [_ms_ze_strefa(x["kiedy"]) for x in pomin],
        })
    return out


def _inna(wartosc: str, poprzednia: str, strefa: float | None) -> bool:
    if wartosc == poprzednia:
        return False
    if strefa is None:
        return True
    a, b = _liczba(wartosc), _liczba(poprzednia)
    return a is None or b is None or abs(a - b) > strefa


def zwin(wiersze: list[dict], co_ile_ms: int = PRZERZEDZENIE_MS,
         martwa_strefa: dict[tuple[str, str], float] | None = None) -> list[dict]:
    """Przerzedza odczyty: z każdej serii (czujnik, kod) zostaje wiersz, gdy wartość się
    zmieniła albo od ostatniego zostawionego minęło `co_ile_ms`. W seriach z
    `martwa_strefa` ({(czujnik, kod): punkty}) zmiana o tyle lub mniej względem ostatniego
    zostawionego wiersza nie jest zmianą.

    Idempotentne: przerzedzenie przerzedzonego niczego nie zmienia — kolektor może więc
    przerzedzać cały plik miesięczny przy każdym przebiegu, także gdy zakładka dołożyła
    z powrotem wiersze wycięte w poprzednim. Każdy zostawiony wiersz porównuje się
    z poprzednim zostawionym, więc drugi przebieg podejmuje te same decyzje.
    """
    def klucz(w):
        return (w["device_id"], w["code"], w["ts"])

    martwa_strefa = martwa_strefa or {}
    out, ostatni = [], {}
    for w in sorted(wiersze, key=klucz):
        seria = (w["device_id"], w["code"])
        teraz = _ms(w["ts"])
        poprzedni = ostatni.get(seria)
        if (poprzedni is None or teraz is None or poprzedni[1] is None
                or teraz - poprzedni[1] >= co_ile_ms
                or _inna(str(w["value"]), poprzedni[0], martwa_strefa.get(seria))):
            out.append(w)
            ostatni[seria] = (str(w["value"]), teraz)
    out.sort(key=lambda w: (w["ts"], w["device_id"], w["code"]))
    return out


def punkty(wiersze: list[dict], czujnik: str, kod: str) -> list[tuple[int, float]]:
    """Liczbowe odczyty jednej serii, rosnąco w czasie."""
    out = []
    for w in wiersze:
        if w.get("device_id") != czujnik or w.get("code") != kod:
            continue
        t, v = _ms(w.get("ts")), _liczba(w.get("value"))
        if t is not None and v is not None:
            out.append((t, v))
    out.sort()
    return out


def wartosc_w(pkt: list[tuple[int, float]], t: int, maks_ms: int = MAKS_PRZERWA_MS) -> float | None:
    """Ostatni odczyt nie późniejszy niż t i nie starszy niż maks_ms (próbka trzymana)."""
    lo, hi = 0, len(pkt)
    while lo < hi:
        mid = (lo + hi) // 2
        if pkt[mid][0] <= t:
            lo = mid + 1
        else:
            hi = mid
    if lo == 0:
        return None
    tp, v = pkt[lo - 1]
    return v if t - tp <= maks_ms else None


def szereg_godzinowy(pkt: list[tuple[int, float]], od_ms: int, do_ms: int) -> list[float | None]:
    """Wartość na każdą pełną godzinę UTC od od_ms do do_ms — do wykresu na zakładce,
    żeby telefon nie ściągał miesięcznych CSV."""
    start = od_ms - od_ms % GODZ
    out = []
    t = start
    while t <= do_ms:
        v = wartosc_w(pkt, t)
        out.append(None if v is None else round(v, 1))
        t += GODZ
    return out


def luksogodziny(pkt: list[tuple[int, float]], strefa: ZoneInfo, od_ms: int, do_ms: int,
                 maks_ms: int = MAKS_PRZERWA_MS) -> list[dict]:
    """Dobowa suma światła [lx·h] w lokalnych dobach, z pokryciem pomiarem (0–1)
    i szczytem [lx].

    Światło przychodzi rzadko (co 1–2 godz., pomiar z nocy 8/9.10), więc trzymamy ostatnią
    wartość do następnego odczytu, ale najwyżej `maks_ms` — dłuższa przerwa to brak
    pomiaru, a nie ciemność. Pokrycie mówi, jaką część doby naprawdę zmierzono; doba
    z niskim pokryciem nie nadaje się do reguły „za ciemno".

    `szczyt_lx` to najwyższa wartość z tych samych odcinków co suma: odczyt sprzed północy
    trzymany po niej liczy się też do następnej doby, a odczyt sprzed dziury dłuższej niż
    `maks_ms` nie sięga za dziurę. Liczony tu, a nie z surowych wierszy, bo surowe wiersze
    trzeba by kroić na doby drugi raz (prototyp robił to w strefie maszyny — w Actions to
    UTC, czyli doba przesunięta o godzinę zimą i o dwie latem). None, gdy doby nie
    zmierzono wcale.
    """
    if od_ms >= do_ms:
        return []
    doby: dict[str, list[float]] = {}

    def dodaj(a: int, b: int, v: float):
        while a < b:
            lokalnie = datetime.fromtimestamp(a / 1000, strefa)
            nastepna = (lokalnie + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            koniec = min(b, int(nastepna.timestamp() * 1000))
            suma = doby.setdefault(lokalnie.date().isoformat(), [0.0, 0.0, 0.0])
            suma[0] += v * (koniec - a) / GODZ
            suma[1] += (koniec - a)
            suma[2] = max(suma[2], v)
            a = koniec

    for i, (t, v) in enumerate(pkt):
        nast = pkt[i + 1][0] if i + 1 < len(pkt) else do_ms
        a, b = max(t, od_ms), min(nast, t + maks_ms, do_ms)
        if a < b:
            dodaj(a, b, max(v, 0.0))
    out = []
    dzien = datetime.fromtimestamp(od_ms / 1000, strefa).date()
    ostatni = datetime.fromtimestamp((do_ms - 1) / 1000, strefa).date()
    while dzien <= ostatni:
        poczatek = datetime(dzien.year, dzien.month, dzien.day, tzinfo=strefa)
        dlugosc = ((poczatek + timedelta(days=1)).astimezone(timezone.utc)
                   - poczatek.astimezone(timezone.utc)).total_seconds() * 1000
        lxh, zmierzone, szczyt = doby.get(dzien.isoformat(), [0.0, 0.0, 0.0])
        out.append({"data": dzien.isoformat(), "lxh": round(lxh),
                    "pokrycie": round(min(1.0, zmierzone / dlugosc), 2),
                    "szczyt_lx": round(szczyt) if zmierzone > 0 else None})
        dzien += timedelta(days=1)
    return out


def pelne_doby_swiatla(swiatlo_dobowe, od_ms: int | None, teraz_ms: int, strefa: ZoneInfo) -> list[dict]:
    """Doby, z których wolno oceniać światło, rosnąco po dacie: zmierzone w co najmniej
    POKRYCIE_PELNEJ_DOBY, bez dzisiejszej (urwanej) i tylko po dniu wbicia sondy.

    Doba wbicia odpada w całości: do wbicia (9.10, 8:35) czujniki leżały obok siebie
    gdzie indziej (noc 8/9.10, pomiar „sucho" z rosliny.json), więc jej suma nie mówi nic
    o miejscu rośliny. Bez daty wbicia nie ma żadnej pełnej doby — czujnik leżący na
    stole nie może zlecić przestawienia rośliny.
    """
    if od_ms is None:
        return []
    od_data = datetime.fromtimestamp(od_ms / 1000, strefa).date().isoformat()
    dzis = datetime.fromtimestamp(teraz_ms / 1000, strefa).date().isoformat()
    doby = [d for d in _lista(swiatlo_dobowe) if isinstance(d, dict) and isinstance(d.get("data"), str)
            and od_data < d["data"] < dzis
            and (_liczba(d.get("pokrycie")) or 0) >= POKRYCIE_PELNEJ_DOBY
            and _liczba(d.get("lxh")) is not None]
    return sorted(doby, key=lambda d: d["data"])


def ocena_swiatla(swiatlo_dobowe, potrzeba, za_duzo_lx, od_ms: int | None, teraz_ms: int,
                  strefa: ZoneInfo, werdykt: str | None = None) -> dict | None:
    """Kierunek „przestaw" z trzech ostatnich pełnych dób — jedna decyzja dla karty
    rośliny i dla powiadomienia (strona jej nie liczy drugi raz).

    `u` to średnia suma światła tych dób przez dzienną potrzebę gatunku. Kierunek:
    "ciemniej", gdy jest próg „za dużo" i szczyt ostatniej z tych dób go przekracza
    (pierwszeństwo — ostre słońce w szczycie przy małej sumie to jedno spójne „odsuń od
    okna", nie sprzeczne „bliżej okna"); inaczej "jasniej" przy u < 0,35, "malo" przy
    u < 0,6, a poza tym "ok". None przy mniej niż trzech pełnych dobach i przy werdykcie
    „czujnik" — światło z milczącego czujnika jest stare.
    """
    if werdykt == "czujnik":
        return None
    potrzeba = _liczba(potrzeba)
    if not potrzeba or potrzeba <= 0:
        return None
    doby = pelne_doby_swiatla(swiatlo_dobowe, od_ms, teraz_ms, strefa)[-DOBY_OCENY_SWIATLA:]
    if len(doby) < DOBY_OCENY_SWIATLA:
        return None
    u = sum(_liczba(d["lxh"]) for d in doby) / len(doby) / potrzeba
    szczyt = _liczba(doby[-1].get("szczyt_lx"))
    prog = _liczba(za_duzo_lx)
    if prog is not None and szczyt is not None and szczyt > prog:
        kierunek = "ciemniej"
    elif u < SWIATLO_JASNIEJ_U:
        kierunek = "jasniej"
    elif u < SWIATLO_MALO_U:
        kierunek = "malo"
    else:
        kierunek = "ok"
    # Decyzja zapada na nieprzyciętym u. Zapis z trzema miejscami, a nie dwoma, żeby było
    # widać, po której stronie progu leży (0,349 → 0,35 wyglądałoby na „nie jaśniej").
    # `proc` to gotowy procent do wyświetlenia — karta bierze go wprost, a powiadomienie
    # „przestaw" liczy go tą samą funkcją z tego samego zapisanego u.
    u_zapis = round(u, 3)
    return {"kierunek": kierunek, "u": u_zapis, "proc": _proc_swiatla(u_zapis), "doby": [d["data"] for d in doby],
            "szczyt_lx": round(szczyt) if szczyt is not None else None}


def _mediana(pkt: list[tuple[int, float]], czasy: list[int], od: int, do: int) -> float | None:
    i, j = bisect.bisect_left(czasy, od), bisect.bisect_right(czasy, do)
    return round(statistics.median(v for _, v in pkt[i:j]), 1) if j > i else None


def podlania(gleba: list[tuple[int, float]], teraz_ms: int | None = None,
             skok: float = SKOK_PODLANIA, okno_ms: int = OKNO_PODLANIA_MS,
             od_ms: int | None = None, sucho: float | None = None) -> list[dict]:
    """Wykryte podlania, rosnąco w czasie.

    Podlanie to wzrost gleby o co najmniej `skok` punktów względem najniższego odczytu
    z ostatnich `okno_ms`; gdy w oknie nic nie ma (przerwa w danych tuż przed
    podlaniem), względem ostatniego odczytu sprzed najwyżej 6 godz. Znacznik to pierwszy
    odczyt, który przekroczył próg. Minimum okna trzyma kolejka monotoniczna, więc całość
    jest liniowa — nauka patrzy na 60 dni, a gleba potrafi przychodzić co 30 s
    (dawna wersja z listą na każdy punkt to były minuty i zabity przebieg).

    `przed` i `szczyt` to mediany odczytów 2–6 godz. przed skokiem i po nim:
    - nie najniższy odczyt z okna, bo przy zanurzaniu azalii sonda leży wtedy
      w powietrzu i „przed" wyszłoby suche jak powietrze;
    - `szczyt` jest None, dopóki od podlania nie minie 6 godz. — wcześniej ziemia
      jeszcze odcieka i szczyt skakałby między przebiegami.
    `liczy` mówi, czy podlanie uczy skali: także mediany muszą się różnić o `skok`.
    Poprawienie sondy (30 → 18 → 30) daje skok, ale nie wodę.

    Gdy w oknie 2–6 godz. przed nie ma odczytów (pierwsze podlanie zaraz po wbiciu
    sondy, przerwa w danych), `przed` to mediana z 2 godz. tuż przed skokiem. Odczyty
    na poziomie powietrza (≤ `sucho` + ZAPAS_SUCHO) nie wchodzą ani do `przed`, ani do
    `szczyt`. Podlania sprzed `od_ms` nie są zwracane — ale ich odczyty dalej służą za
    tło: 9.10 właściciel podlał 10 minut po starcie nauki, a dawna wersja, która
    dostawała szereg obcięty do startu nauki, nie miała wtedy ani jednego odczytu
    „przed" i pierwsze podlanie nigdy nie uczyło skali.
    """
    wydarzenia: list[int] = []
    okno: deque[int] = deque()            # indeksy, wartości rosnąco od lewej
    for i, (t, v) in enumerate(gleba):
        while okno and t - gleba[okno[0]][0] > okno_ms:
            okno.popleft()
        if okno:
            najnizej = gleba[okno[0]][1]
        elif i and t - gleba[i - 1][0] <= PRZED_DO_MS:
            najnizej = gleba[i - 1][1]
        else:
            najnizej = None
        if (najnizej is not None and v - najnizej >= skok
                and (not wydarzenia or t - wydarzenia[-1] > okno_ms)):
            wydarzenia.append(t)
        while okno and gleba[okno[-1]][1] >= v:
            okno.pop()
        okno.append(i)
    w_ziemi = gleba if sucho is None else [(t, v) for (t, v) in gleba if v > sucho + ZAPAS_SUCHO]
    czasy_w_ziemi = [t for t, _ in w_ziemi]
    out = []
    for ms in wydarzenia:
        if od_ms is not None and ms < od_ms:
            continue
        przed = _mediana(w_ziemi, czasy_w_ziemi, ms - PRZED_DO_MS, ms - PRZED_OD_MS)
        if przed is None:
            przed = _mediana(w_ziemi, czasy_w_ziemi, ms - PRZED_OD_MS, ms - 1)
        if przed is None:
            # Ziemia przeschnięta na wiór czyta tyle co powietrze (fikus 13 przy „sucho"
            # 10) — to też jest „przed", inaczej podlewanie na sucho nigdy nie uczy.
            przed = _mediana(gleba, [t for t, _ in gleba], ms - PRZED_DO_MS, ms - PRZED_OD_MS)
        gotowe = teraz_ms is None or teraz_ms >= ms + SZCZYT_DO_MS
        szczyt = (_mediana(w_ziemi, czasy_w_ziemi, ms + SZCZYT_OD_MS, ms + SZCZYT_DO_MS)
                  if gotowe else None)
        out.append({"ts": iso(ms), "przed": przed, "szczyt": szczyt,
                    "liczy": przed is not None and szczyt is not None and szczyt - przed >= skok})
    return out


def nauka(podl: list[dict], sucho: float | None) -> dict:
    """Szczyt i punkt podlewania z trzech ostatnich uczących podlań (mediany)."""
    uczace = [p for p in podl if p.get("liczy")][-3:]
    szczyty = [p["szczyt"] for p in uczace]
    przed = [p["przed"] for p in uczace]
    szczyt = statistics.median(szczyty) if szczyty else None
    punkt = statistics.median(przed) if len(przed) >= 3 else None
    if szczyt is not None and sucho is not None and szczyt - sucho < SKOK_PODLANIA:
        szczyt = None          # „szczyt" ledwie nad suchym — to nie skala, tylko szum
    return {"szczyt": szczyt, "punkt_podlewania": punkt, "podlan": len([p for p in podl if p.get("liczy")])}


def sonda_wyjeta(gleba: list[tuple[int, float]], sucho: float | None,
                 skok: float = SKOK_PODLANIA, okno_ms: int = OKNO_PODLANIA_MS) -> int | None:
    """Chwila, od której gleba stoi na poziomie powietrza po nagłym spadku — sonda wyjęta
    z ziemi. None, jeśli tak nie jest. Schnięcie tu nie wpada: ziemia traci kilka punktów
    na dobę, a nie `skok` w dwie godziny — więc zupełnie sucha doniczka to dalej „podlej"."""
    if sucho is None or not gleba:
        return None
    i = len(gleba)
    while i > 0 and gleba[i - 1][1] <= sucho + ZAPAS_SUCHO:
        i -= 1
    if i == len(gleba) or i == 0:
        return None
    t_spadku, v_spadku = gleba[i]
    j, najwyzej = i - 1, None
    while j >= 0 and t_spadku - gleba[j][0] <= okno_ms:
        najwyzej = gleba[j][1] if najwyzej is None else max(najwyzej, gleba[j][1])
        j -= 1
    return t_spadku if najwyzej is not None and najwyzej - v_spadku >= skok else None


def prog_rosliny(gatunek: str, miesiac: int, sucho: float | None, szczyt: float | None,
                 punkt: float | None) -> float:
    """Próg R: nauczony z podlań właściciela (przycięty do granic gatunku) albo z literatury."""
    g = GATUNKI[gatunek]
    if punkt is not None and szczyt is not None and sucho is not None and szczyt > sucho:
        nauczony = (punkt - sucho) / (szczyt - sucho)
        return round(min(max(nauczony, g["granice"][0]), g["granice"][1]), 2)
    return g["prog_zima"] if miesiac in ZIMA else g["prog"]


def stan_rosliny(konf: dict, wiersze: list[dict], teraz_ms: int, strefa: ZoneInfo) -> dict:
    """Wszystko, co zakładka pokazuje o jednej roślinie, werdykt i to, co ma trafić do
    watchdoga (`do_zgloszenia`: cisza, bateria, sonda długo poza ziemią)."""
    czujnik, kody = konf["czujnik"], konf["kody"]
    od_wbicia = _ms_ze_strefa(konf["od"]) if konf.get("od") else None
    serie = {r: punkty(wiersze, czujnik, kod) for r, kod in kody.items() if r in LICZBOWE}

    ostatnie = {}
    for rodzaj, kod in kody.items():
        moje = [w for w in wiersze if w.get("device_id") == czujnik and w.get("code") == kod
                and (rodzaj not in LICZBOWE or _liczba(w.get("value")) is not None)]
        if moje:
            w = max(moje, key=lambda x: x["ts"])
            v = _liczba(w["value"]) if rodzaj in LICZBOWE else w["value"]
            ostatnie[rodzaj] = {"v": v, "ts": w["ts"]}

    od_ms = teraz_ms - DNI_HISTORII * DOBA
    szereg = {"od": iso(od_ms - od_ms % GODZ), "krok_min": 60}
    for rodzaj in LICZBOWE:
        if rodzaj in serie:
            szereg[rodzaj] = szereg_godzinowy(serie[rodzaj], od_ms, teraz_ms)

    gleba = serie.get("gleba", [])
    od_nauki = None
    if od_wbicia is not None:
        od_nauki = od_wbicia + ZAPAS_PO_WBICIU_MS
        # Szereg od wbicia, nie od startu nauki: odczyty z pierwszej godziny w ziemi są
        # tłem dla podlania tuż po starcie nauki. Samo wbicie (skok z powietrza do ziemi)
        # wypada, bo podlania sprzed od_nauki nie są liczone.
        gleba_nauki = [(t, v) for (t, v) in gleba
                       if t >= max(od_wbicia, teraz_ms - DNI_NAUKI * DOBA)]
    else:
        gleba_nauki = []          # bez daty wbicia sondy nie uczymy się niczego
    sucho = konf.get("sucho")
    podl = podlania(gleba_nauki, teraz_ms, od_ms=od_nauki, sucho=sucho)
    # Podlania wskazane ręcznie w rosliny.json nie uczą skali — np. 9.10 woda stała
    # w osłonce fikusa i sonda pokazywała 100 przez 5 godz., więc „szczyt" był zawyżony.
    # Godzina wpisu może się różnić od wykrytej o jedno-dwa wybudzenia czujnika.
    for p in podl:
        if any(abs(_ms(p["ts"]) - kiedy) <= GODZ for kiedy in konf.get("pomin_podlania") or []):
            p["liczy"], p["pominiete"] = False, True
    wynik_nauki = nauka(podl, sucho)
    miesiac = datetime.fromtimestamp(teraz_ms / 1000, strefa).month
    prog = prog_rosliny(konf["gatunek"], miesiac, sucho, wynik_nauki["szczyt"],
                        wynik_nauki["punkt_podlewania"])

    teraz_gleba = ostatnie.get("gleba", {}).get("v")
    szczyt = wynik_nauki["szczyt"]
    r = None
    if teraz_gleba is not None and szczyt is not None and sucho is not None:
        r = round((teraz_gleba - sucho) / (szczyt - sucho), 2)

    uwagi, zglos = [], []
    najnowszy = max((_ms(o["ts"]) or 0 for o in ostatnie.values()), default=0)
    ts_gleby = _ms(ostatnie["gleba"]["ts"]) if "gleba" in ostatnie else None
    # Przed wbiciem sonda z definicji nie jest w ziemi (np. test w szklance wody), więc
    # spadek do poziomu powietrza liczy się dopiero od „od".
    wyjeta = (sonda_wyjeta([(t, v) for (t, v) in gleba if t >= od_wbicia], sucho)
              if od_wbicia is not None else None)
    if not ostatnie:
        werdykt = "czujnik"
        uwagi.append("Brak jakichkolwiek odczytów.")
        zglos.append(uwagi[-1])
    elif teraz_ms - najnowszy > CISZA_MS:
        werdykt = "czujnik"
        uwagi.append(f"Czujnik milczy od {(teraz_ms - najnowszy) / GODZ:.0f} godz.")
        zglos.append(uwagi[-1])
    elif ts_gleby is None or teraz_ms - ts_gleby > CISZA_MS:
        # reszta przychodzi, gleba nie — werdykt ze starej gleby byłby zmyślony
        werdykt = "czujnik"
        uwagi.append("Brak odczytów gleby." if ts_gleby is None else
                     f"Gleba nie przychodzi od {(teraz_ms - ts_gleby) / GODZ:.0f} godz.")
        zglos.append(uwagi[-1])
    elif wyjeta is not None:
        werdykt = "czujnik"
        uwagi.append(f"Od {_lokalnie(wyjeta, strefa)} gleba pokazuje tyle co sonda w powietrzu "
                     f"— sonda wyjęta z ziemi?")
        if teraz_ms - wyjeta >= ZGLOS_WYJETA_MS:
            zglos.append(uwagi[-1])
    elif sucho is None:
        werdykt = "nauka"
        uwagi.append("Brak „sucho\" w rosliny.json — bez odczytu w powietrzu nie ma skali.")
    elif od_wbicia is None:
        werdykt = "nauka"
        uwagi.append("Czekam na wbicie sondy do ziemi (data „od\" w rosliny.json).")
    elif teraz_ms < od_nauki:
        werdykt = "nauka"
        uwagi.append(f"Uczę się od {_lokalnie(od_nauki, strefa)} — godzinę po wbiciu sondy.")
    elif szczyt is None:
        werdykt = "nauka"
        if podl and podl[-1].get("pominiete"):
            uwagi.append(f"Podlanie {_lokalnie(_ms(podl[-1]['ts']), strefa)} pominięte w nauce "
                         f"(rosliny.json) — skala przyjdzie z następnego.")
        elif podl and podl[-1]["szczyt"] is None:
            uwagi.append(f"Podlanie {_lokalnie(_ms(podl[-1]['ts']), strefa)} — skala będzie "
                         f"znana 6 godz. po nim.")
        elif podl:
            uwagi.append("Ostatnie podlanie nie podniosło gleby wyraźnie — czekam na następne.")
        else:
            uwagi.append("Czekam na pierwsze podlanie — z niego bierze się skala.")
    else:
        pilne = GATUNKI[konf["gatunek"]]["pilne"]
        if pilne is not None and r is not None and r <= pilne:
            werdykt = "pilne"
            rada = GATUNKI[konf["gatunek"]].get("rada_pilne")
            if rada:
                uwagi.append(rada)
        elif r is not None and r <= prog:
            werdykt = "podlej"
        else:
            werdykt = "ok"
    if str(ostatnie.get("bateria", {}).get("v", "")).lower() == "low":
        uwagi.append("Bateria na wyczerpaniu.")
        zglos.append(uwagi[-1])

    # Doby od lokalnej północy: pierwsza doba liczona od „teraz − 30 dni" byłaby urwana
    # i wyglądałaby na ciemną. Dzisiejsza jest niepełna — mówi to `pokrycie`.
    pierwsza = datetime.fromtimestamp(teraz_ms / 1000, strefa).date() - timedelta(days=DNI_HISTORII - 1)
    od_dob = int(datetime(pierwsza.year, pierwsza.month, pierwsza.day, tzinfo=strefa).timestamp() * 1000)
    swiatlo = luksogodziny(serie.get("swiatlo", []), strefa, od_dob, teraz_ms)
    gat = GATUNKI[konf["gatunek"]]
    pelne = pelne_doby_swiatla(swiatlo, od_wbicia, teraz_ms, strefa)
    return {
        "czujnik": czujnik, "nazwa": konf["nazwa"], "gatunek": konf["gatunek"],
        "nazwa_pelna": gat["nazwa_pelna"], "temp_zakres": list(gat["temp_zakres"]),
        "wilg_zakres": list(gat["wilg_zakres"]),
        "pokoj": konf.get("pokoj"), "sucho": sucho, "od": konf.get("od"),
        "ostatnie": ostatnie, "szereg": szereg, "swiatlo_dobowe": swiatlo,
        "swiatlo_potrzeba_lxh": gat["swiatlo_lxh"],
        "swiatlo_za_duzo_lx": gat["swiatlo_za_duzo_lx"],
        "swiatlo_pelne_doby": len(pelne),
        "swiatlo_wczoraj_lxh": pelne[-1]["lxh"] if pelne else None,
        "swiatlo_szczyt_lx_wczoraj": pelne[-1].get("szczyt_lx") if pelne else None,
        "swiatlo_ocena": ocena_swiatla(swiatlo, gat["swiatlo_lxh"], gat["swiatlo_za_duzo_lx"], od_wbicia,
                                       teraz_ms, strefa, werdykt),
        "podlania": podl, "szczyt": szczyt, "punkt_podlewania": wynik_nauki["punkt_podlewania"],
        "R": r, "prog": prog, "werdykt": werdykt, "uwagi": uwagi, "do_zgloszenia": zglos,
        # Próg w jednostkach czujnika — ta sama liczba co duża wartość gleby na karcie
        # i dolna krawędź pasma na wykresie. Strona nie odwraca wzoru na R sama.
        "prog_gleba": (round(sucho + prog * (szczyt - sucho))
                       if szczyt is not None and sucho is not None else None),
    }


# Powiadomienia (etap 4) — reguły v1 z ROSLINY.md, „Reguły powiadomień". Tu zapada tylko
# decyzja: kolektor zapisuje wynik w data/rosliny/powiadomienia.json z numerem przebiegu,
# a osobny krok po udanym zapisz.sh wysyła wpisy tego przebiegu — więc co najwyżej raz
# (ROSLINY.md, „Etap 4").

# Cisza nocna jest osobna dla każdego telefonu (telefony.py, zmienne POWIADOMIENIA_ANDROID
# i POWIADOMIENIA_IPHONE). „Noc" dawnych reguł to chwila, gdy ciszę mają wszystkie telefony
# — przy domyślnych ustawieniach obu to dokładnie dawne 21:00–8:00.
PODSUMOWANIE_OD_H = 10                   # niedziela od 10:00
PONIZEJ = ("podlej", "pilne")
# Roślina „poniżej" musi tyle trwać, zanim pójdzie „podlej" — jeden odczyt na granicy to
# jeszcze nie sucho. Po nocy liczy się od 8:00 („po 8:00 reguły liczą się od nowa").
TRWA_PONIZEJ_MS = 2 * GODZ
PONOWIENIE_MS = 24 * GODZ
PONOWIENIE_GATUNKU_MS = {"azalia": 12 * GODZ}    # torf w osłonce schnie najszybciej
MAKS_WYSYLEK_EPIZODU = 3                 # potem już tylko karta
MAKS_PODLEJ_NA_DOBE = 2                  # „zwykłe" na lokalną dobę
# Koniec epizodu bez wykrytego podlania: gleba tyle punktów czujnika nad progiem. Przy
# schodkach po 3 punkty mniej by nie wystarczyło (ROSLINY.md, „Uczenie progów").
HISTEREZA_GLEBY = 6
# Rozrzut startu przebiegów: godzinne commity odczytów 2–9.10 na origin/main wypadają od
# :00 do :06 po pełnej godzinie; 9.10 między 3:01:33 a 5:01:23 minęło 1:59:50, a między
# 10:01:26 a 12:01:29 — 2:00:03. Bez zapasu „≥ 2 godz." i „co 24 godz." raz po raz
# czekałyby przebieg (godzinę) dłużej.
ZAPAS_PRZEBIEGU_MS = 10 * 60 * 1000
DNI_POWIADOMIEN = 60
# Reguła → przełącznik w ustawieniach telefonu (telefony.DOMYSLNE). Powitanie nie ma
# przełącznika: to pierwsze prawdziwe powiadomienie, po nim widać, czy telefon je dostaje.
KLUCZ_USTAWIEN = {"podlej": "podlej", "czujnik": "czujnik", "przestaw": "przestaw",
                  "podsumowanie": "podsumowanie", "wlaczone": None}
# Zakładki aplikacji. Roślina, której slug wypada jak zakładka, dostaje w adresie „-2" —
# tak samo liczy go index.html. Kolizję z pokojem wyklucza pokoje.json (slug pokoju jest
# tam unikalny także wobec roślin).
ZAKLADKI = ("dom", "rosliny", "historia", "powiadomienia")

# Powód zgłoszenia czujnika jako stały klucz. Tekst z do_zgloszenia zmienia się co
# przebieg („milczy od 13 godz.", „od 14 godz."), a „raz na powód" musi go rozpoznać.
POWODY_CZUJNIKA = (
    ("Brak jakichkolwiek odczytów", "brak-odczytow"),
    ("milczy", "cisza"),
    ("Gleba nie przychodzi", "gleba"),
    ("Brak odczytów gleby", "gleba"),
    ("sonda wyjęta", "sonda"),
    ("Bateria", "bateria"),
)
WERDYKT_SLOWNIE = {"ok": "w porządku", "podlej": "do podlania", "pilne": "pilnie do podlania",
                   "nauka": "uczę się", "czujnik": "sprawdź czujnik"}


def _slug(tekst: str) -> str:
    """ASCII [a-z0-9-] — znaczniki powiadomień idą do nagłówka Topic Web Push."""
    tekst = unicodedata.normalize("NFKD", tekst.replace("ł", "l").replace("Ł", "L"))
    tekst = "".join(z for z in tekst if not unicodedata.combining(z)).lower()
    return re.sub(r"[^a-z0-9]+", "-", tekst).strip("-")


def _znacznik(regula: str, nazwy: list[str]) -> str:
    """`podlej-azalia`: kolejne powiadomienie o tych samych roślinach zastępuje na
    telefonie poprzednie, a nie dokłada się obok. Najwyżej 32 znaki (limit Topic)."""
    return "-".join([regula] + [_slug(n) or "roslina" for n in nazwy])[:32].rstrip("-")


def _adres(nazwa: str | None) -> str:
    """Adres w aplikacji: `#fikus` dla jednej rośliny, `#rosliny` bez nazwy (kilka roślin,
    podsumowanie). Slug z nazwy, a nie z gatunku: nazwa jest unikalna (wczytaj_konfiguracje),
    gatunek nie — dwa fikusy dostałyby jeden adres. Względny i bez `http`: service worker
    rozwiązuje go względem zakresu aplikacji, a plik powiadomień jest publiczny. Stare
    `rosliny.html#roslina=…` z doręczonych powiadomień obsługuje strona."""
    slug = _slug(nazwa) if isinstance(nazwa, str) else ""
    if not slug:
        return "#rosliny"
    return "#" + (slug + "-2" if slug in ZAKLADKI else slug)


def _mala(tekst: str) -> str:
    """Mała pierwsza litera po „Nazwa: …" — chyba że to skrót."""
    return tekst[:1].lower() + tekst[1:] if tekst[1:2].islower() else tekst


def _powod(tekst: str) -> str:
    for fragment, klucz in POWODY_CZUJNIKA:
        if fragment in tekst:
            return klucz
    # nowy rodzaj zgłoszenia, którego tu jeszcze nie ma — bez cyfr, żeby był stały
    return ("inne-" + _slug(re.sub(r"\d", "", tekst)))[:32].rstrip("-")


def _gleba(stan: dict) -> float | None:
    ostatnie = stan.get("ostatnie")
    gleba = ostatnie.get("gleba") if isinstance(ostatnie, dict) else None
    return _liczba(gleba.get("v")) if isinstance(gleba, dict) else None


def _lista(wartosc) -> list:
    """Pole listowe z pliku albo ze stanu; cokolwiek innego to pusta lista."""
    return wartosc if isinstance(wartosc, list) else []


def _lista_ms(wartosci) -> list[int]:
    return sorted(m for m in (_ms(x) for x in _lista(wartosci)) if m is not None)


def _linia_podlej(stan: dict) -> str:
    gleba, prog = _gleba(stan), _liczba(stan.get("prog_gleba"))
    linia = f"{stan['nazwa']}: " + (f"gleba {_calk(gleba)}%" if gleba is not None else "czas podlać")
    if gleba is not None and prog is not None:
        linia += f" (podlewaj przy ok. {_calk(prog)}%)"
    linia += "."
    if stan.get("werdykt") == "pilne":
        # rada (zanurzenie azalii) już leży w uwagach — stan_rosliny ją dokłada
        zglos = _lista(stan.get("do_zgloszenia"))
        rady = [u for u in _lista(stan.get("uwagi")) if isinstance(u, str) and u not in zglos]
        if rady:
            linia += " " + " ".join(rady)
    return linia


def _linia_podsumowania(stan: dict, dzis, strefa: ZoneInfo) -> str:
    werdykt = stan.get("werdykt")
    czesci = [f"{stan['nazwa']}: "
              + (WERDYKT_SLOWNIE.get(werdykt, "bez werdyktu") if isinstance(werdykt, str) else "bez werdyktu")]
    gleba, prog = _gleba(stan), _liczba(stan.get("prog_gleba"))
    if gleba is not None:
        czesci[0] += f", gleba {_calk(gleba)}%" + (f" (podlewaj przy ok. {_calk(prog)}%)" if prog is not None else "")
    podlane = [m for m in (_ms(p.get("ts")) for p in _lista(stan.get("podlania")) if isinstance(p, dict))
               if m is not None]
    czesci.append(f"ostatnie podlanie {_lokalnie(max(podlane), strefa)}" if podlane
                  else "bez wykrytego podlania")
    # Pełne doby z ostatnich 7, bez dzisiejszej (urwanej) i bez dziurawych — doba
    # zmierzona w jednej czwartej wyglądałaby na ciemną.
    od = (dzis - timedelta(days=7)).isoformat()
    doby = [d for d in _lista(stan.get("swiatlo_dobowe")) if isinstance(d, dict)
            and od <= str(d.get("data")) < dzis.isoformat()
            and (_liczba(d.get("pokrycie")) or 0) >= POKRYCIE_PELNEJ_DOBY
            and _liczba(d.get("lxh")) is not None]
    if doby:
        srednio = sum(_liczba(d["lxh"]) for d in doby) / len(doby)
        potrzeba = _liczba(stan.get("swiatlo_potrzeba_lxh"))
        swiatlo = f"światło śr. {_tys(srednio)} lx·h na dobę"
        if potrzeba:
            swiatlo += f", {_calk(100 * srednio / potrzeba)}% potrzeby"
        czesci.append(swiatlo + f" (pełne doby: {len(doby)} z 7)")
    else:
        czesci.append("światło: za mało pomiaru z ostatnich 7 dób")
    return "; ".join(czesci) + "."


def _tys(liczba: float) -> str:
    return f"{_calk(liczba):,}".replace(",", " ")


def _przestaw_slowa(stan: dict, kierunek: str, u: float | None, szczyt: float | None) -> tuple[str, str]:
    """(co zrobić, dlaczego) dla jednej rośliny — tytuł i treść „przestaw"."""
    if kierunek == "ciemniej":
        prog = _liczba(stan.get("swiatlo_za_duzo_lx"))
        dlaczego = (f"Wczoraj w szczycie {_tys(szczyt)} lx" if szczyt is not None else "Wczoraj w szczycie dnia")
        dlaczego += f", a liście przypalają się już od {_tys(prog)} lx." if prog is not None else "."
        if u is not None and u < SWIATLO_MALO_U:
            dlaczego += " Najlepiej jasne miejsce bez bezpośredniego słońca."
        return "odsuń od okna", dlaczego
    dlaczego = (f"Ostatnie {DOBY_OCENY_SWIATLA} doby: średnio {_proc_swiatla(u)}% potrzebnego światła."
                if u is not None else f"Ostatnie {DOBY_OCENY_SWIATLA} doby: za mało światła.")
    gatunek = stan.get("gatunek")
    rada = GATUNKI[gatunek].get("rada_przestaw") if isinstance(gatunek, str) and gatunek in GATUNKI else None
    if rada:
        dlaczego += " " + rada
    return "przestaw bliżej okna", dlaczego


def _linia_przestaw(stan: dict, kierunek: str, u: float | None, szczyt: float | None) -> str:
    co, dlaczego = _przestaw_slowa(stan, kierunek, u, szczyt)
    return f"{stan['nazwa']}: {co}. {dlaczego}"


def _tresc_przestaw(lista: list[tuple]) -> tuple[str, str]:
    """Jedna roślina: „Fikus: przestaw bliżej okna" i powód w treści. Kilka: „Przestaw:
    fikus, skrzydłokwiat" i linia na roślinę."""
    if len(lista) == 1:
        stan, kierunek, u, szczyt = lista[0]
        co, dlaczego = _przestaw_slowa(stan, kierunek, u, szczyt)
        return f"{stan['nazwa']}: {co}", dlaczego
    return ("Przestaw: " + ", ".join(_mala(s["nazwa"]) for s, *_ in lista),
            "\n".join(_linia_przestaw(*x) for x in lista))


def _tresc_podlej(lista: list[dict]) -> tuple[str, str]:
    tytul = ", ".join(_mala(s["nazwa"]) + (" (pilne)" if s.get("werdykt") == "pilne" else "") for s in lista)
    return f"Podlej: {tytul}", "\n".join(_linia_podlej(s) for s in lista)


def _linie_czujnika(nazwa: str, powody: dict, minione: list[str]) -> list[str]:
    return [f"{nazwa}: {_mala(t)}" for t in powody.values()] + list(minione)


def _ocena(stan: dict) -> tuple[str | None, float | None, float | None]:
    """(kierunek, u, szczyt) z `swiatlo_ocena` stanu albo (None, None, None)."""
    ocena = stan.get("swiatlo_ocena")
    if not isinstance(ocena, dict):
        return None, None, None
    kierunek = ocena.get("kierunek")
    if not isinstance(kierunek, str) or kierunek not in KIERUNKI_PRZESTAW + ("malo", "ok"):
        return None, None, None
    return kierunek, _liczba(ocena.get("u")), _liczba(ocena.get("szczyt_lx"))


def _odstep(stan: dict) -> int:
    """Odstęp ponowień „podlej" gatunku (azalia 12 godz., reszta 24)."""
    gatunek = stan.get("gatunek")
    return PONOWIENIE_GATUNKU_MS.get(gatunek, PONOWIENIE_MS) if isinstance(gatunek, str) else PONOWIENIE_MS


def _podlej_dla(wartosc) -> dict:
    """`podlej_dla` ze stanu reguł: {telefon: chwila doręczenia odłożonego „podlej"}. Plik jest
    publiczny i edytowalny, więc tylko znane telefony z poprawną datą. Kolejność kluczy jak
    w pliku — inna kolejność po przepisaniu zmieniałaby plik bez zmiany danych."""
    if not isinstance(wartosc, dict):
        return {}
    return {t: v for t, v in wartosc.items() if t in telefony.TELEFONY and _ms(v) is not None}


def _ustawienia(ustawienia) -> dict:
    """Ustawienia obu telefonów. None (albo brak telefonu) to telefony.DOMYSLNE. Słownik
    przechodzi przez ten sam parser co zmienne repozytorium, więc zła wartość pola daje
    domyślną, a nie wyjątek w środku reguł."""
    zrodlo = ustawienia if isinstance(ustawienia, dict) else {}
    wynik = {}
    for t in telefony.TELEFONY:
        u = zrodlo.get(t)
        try:
            wynik[t] = telefony.ustawienia_telefonu(json.dumps(u)) if isinstance(u, dict) else dict(telefony.DOMYSLNE)
        except (TypeError, ValueError):
            wynik[t] = dict(telefony.DOMYSLNE)
    return wynik


def _odloz(kolejki: dict, do_kogo: list[str], pozycja: dict) -> None:
    """Pozycja do kolejki telefonów w ciszy. Gdy ten sam obiekt już czeka, pozycja zostaje
    jedna (z czasem pierwszego zdarzenia, telefony.odloz), ale dostaje świeże pola
    walidacji: nowy epizod „podlej" w tej samej nocy ma nowe `ponizej_od`, a nowy powód
    czujnika dopisuje się do starych — inaczej rano przepadłby albo jeden, albo drugi."""
    for t in do_kogo:
        stara = next((p for p in kolejki[t]["odlozone"]
                      if p.get("regula") == pozycja["regula"] and p.get("obiekt") == pozycja.get("obiekt")), None)
        if stara is None:
            telefony.odloz(kolejki, [t], pozycja)
        elif pozycja["regula"] == "czujnik":
            powody = [r for r in _lista(stara.get("powody")) if isinstance(r, dict)]
            znane = {r.get("powod") for r in powody}
            stara["powody"] = powody + [dict(r) for r in pozycja["powody"] if r["powod"] not in znane]
            stara["minione"] = list(dict.fromkeys([x for x in _lista(stara.get("minione")) if isinstance(x, str)]
                                                  + pozycja["minione"]))
        else:
            stara.update({k: v for k, v in pozycja.items() if k not in ("regula", "obiekt", "ts")})


def zaplanuj_powiadomienia(stany: list[dict], poprzednie: dict | None, teraz_ms: int,
                           strefa: ZoneInfo, tryb: str, przebieg: str, ustawienia: dict | None = None) -> dict:
    """Zwraca NOWĄ zawartość data/rosliny/powiadomienia.json.

    `stany` to wyniki stan_rosliny() z tego przebiegu, `poprzednie` — dotychczasowa
    zawartość pliku (albo None), `tryb` — "wlaczone" albo "na-sucho" (cokolwiek innego
    to na sucho), `przebieg` — "$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT", `ustawienia` —
    {"android": {...}, "iphone": {...}} z telefony.ustawienia_z_env (None: obu telefonom
    telefony.DOMYSLNE). Plik jest publiczny, więc nie ma w nim adresów subskrypcji.
    Wszystko liczy się od `teraz_ms`, a bez zmian w stanach wynik jest ten sam — plik nie
    zmienia się co przebieg.

    Reguły (ROSLINY.md, „Reguły powiadomień"):
    - **podlej** — werdykt `podlej`/`pilne` trwa ≥ 2 godz. od `ponizej_od` (po wspólnej
      nocy telefonów od jej końca). Epizod kończy wykryte podlanie po `ponizej_od` albo
      gleba ≥ próg + 6 pkt; w paśmie histerezy (werdykt już `ok`, gleba jeszcze poniżej
      progu + 6) epizod trwa, ale nic nie wychodzi. Ponowienie co 24 godz. (azalia co 12),
      najwyżej 3 razy na epizod, najwyżej 2 takie wpisy na lokalną dobę. `nauka` kończy
      epizod.
    - **czujnik** — każdy powód z `do_zgloszenia` raz; gdy zniknie, znika ze stanu
      i może wrócić. We wspólnej nocy trafia do `noc` i wychodzi rano — także gdy minął.
    - **przestaw** — `swiatlo_ocena` z kierunkiem „jasniej"/„ciemniej" otwiera epizod
      (inny kierunek niż zapisany — nowy epizod); kończy go „ok" albo u ≥ 0,45. Bez oceny
      (np. werdykt „czujnik") epizod stoi. Jedna wysyłka na epizod, bez ponowień: okna są
      północne i zimą „bliżej okna" będzie prawdą miesiącami (ROSLINY.md, „W skrócie").
    - **podsumowanie** — pierwszy przebieg w niedzielę od 10:00. Wpis powstaje zawsze, ale
      domyślnie nie idzie do nikogo (`telefony: []`): przełącznik jest domyślnie wyłączony.
    - **wspólna noc** (wszystkie telefony w ciszy, domyślnie 21:00–8:00): nic nie wychodzi.
    - **na sucho** — te same decyzje, wpisy z `na_sucho: true`, a w stanie reguł
      znaczniki `na_sucho` zamiast `wyslano`. Na sucho liczą się jedne i drugie (tak
      by było, gdyby wysyłka była włączona), po włączeniu tylko prawdziwe wysyłki.
      Pierwszy dzienny przebieg po włączeniu daje jeden wpis `wlaczone` z tym, co już
      trwa (podlej, czujnik, przestaw), zamiast osobnych — i zawsze, także gdy nic nie
      trwa: to pierwsze prawdziwe powiadomienie, po nim widać, czy telefon je dostaje.

    Telefony: każdy wpis ma pole `telefony` — komu nadawca wysyła go teraz (reguła
    włączona, telefon poza ciszą). Telefon z włączoną regułą, ale w ciszy, dostaje pozycję
    w kolejce `telefony.<t>.odlozone`; w pierwszym przebiegu po końcu jego ciszy pozycje
    sprawdza się na świeżym stanie (nieaktualne odpadają) i wychodzą jako wpis z
    `telefony: [t]`, `odlozone: true`, a kolejka czyści się w tym samym wyniku — więc
    „co najwyżej raz" działa jak dotąd: stan i wpis powstają w jednym commicie. Powitanie
    nigdy nie czeka w kolejce. Decyzje reguł (epizody, liczniki, limity) nie zależą od
    ustawień — ustawienia mówią tylko, kto dostaje wpis. Telefon, któremu doręczono
    odłożone „podlej", dostaje następne „podlej" tej rośliny (świeże albo z kolejki) dopiero
    po odstępie gatunku od tego doręczenia — chwila leży w `stan_regul[n].podlej_dla`
    i znika z końcem epizodu.

    Jeden przebieg dokłada najwyżej jeden świeży wpis na regułę („Podlej: azalia,
    skrzydłokwiat" to jeden wpis), a nie jeden wpis na wszystko: znacznik zastępuje na
    telefonie poprzednie powiadomienie o tym samym, a zbiorczy wpis „podlej + czujnik"
    zniknąłby pod następnym „podlej" razem z nieprzeczytanym alarmem czujnika. Limit
    „2 zwykłe na dobę" liczy się wtedy wprost z historii.
    """
    na_sucho = tryb != "wlaczone"
    tryb = "na-sucho" if na_sucho else "wlaczone"
    poprz = poprzednie if isinstance(poprzednie, dict) else {}
    ust = _ustawienia(ustawienia)
    lokalnie = datetime.fromtimestamp(teraz_ms / 1000, strefa)
    noc = telefony.noc_wszystkich(ust, lokalnie)
    dzis = lokalnie.date()
    # Dawne „8:00 dziś", od którego „podlej" odlicza poranne 2 godz. None: dziś wspólnej
    # nocy nie było (jeden telefon bez ciszy) — wtedy liczy się sam początek epizodu.
    rano_ms = telefony.koniec_nocy_ms(ust, teraz_ms, strefa)
    teraz_iso = iso(teraz_ms)
    znacznik_wysylki = "na_sucho" if na_sucho else "wyslano"

    historia = []
    for w in _lista(poprz.get("historia")):
        ts = _ms(w.get("ts")) if isinstance(w, dict) else None
        if ts is not None and teraz_ms - ts <= DNI_POWIADOMIEN * DOBA:
            historia.append(w)

    # Włączenie: pierwszy przebieg w trybie "wlaczone", który może coś wysłać. We wspólnej
    # nocy `wlaczone_od` zostaje puste i powitanie wychodzi rano.
    if na_sucho:
        wlaczone_od, wlaczanie = None, False
    elif poprz.get("tryb") == "wlaczone" and poprz.get("wlaczone_od"):
        wlaczone_od, wlaczanie = poprz["wlaczone_od"], False
    else:
        wlaczanie = not noc
        wlaczone_od = teraz_iso if wlaczanie else None

    # Stan roślin nieobecnych w tym przebiegu (błąd obliczeń jednej z nich) zostaje bez
    # zmian — inaczej jeden zły przebieg kasowałby liczniki ponowień.
    stan_regul = poprz.get("stan_regul") if isinstance(poprz.get("stan_regul"), dict) else {}
    stan_regul = {n: v for n, v in stan_regul.items() if isinstance(v, dict)}

    # Kopia: pozycje kolejki zmieniają się w miejscu (_odloz), a `poprzednie` ma zostać
    # nietknięte — kolektor porównuje z nim wynik, żeby nie pisać pliku bez zmian.
    kolejki = copy.deepcopy(telefony.stan_telefonow(poprz.get("telefony")))
    for t in telefony.TELEFONY:
        kolejki[t]["odlozone"] = telefony.przytnij_odlozone(kolejki[t]["odlozone"], teraz_ms, _ms)

    rosliny_teraz, do_podlania, ponizej, czujnik_nowe, czujnik_trwa = [], [], [], [], []
    do_przestawienia, przestaw_trwa = [], []
    obecne, powody_teraz = {}, {}
    for s in _lista(stany):
        if not isinstance(s, dict) or not isinstance(s.get("nazwa"), str) or not s["nazwa"]:
            continue
        nazwa, werdykt = s["nazwa"], s.get("werdykt")
        przed = stan_regul.get(nazwa) or {}
        rosliny_teraz.append(s)
        obecne[nazwa] = s

        # podlej: epizod
        od = _ms(przed.get("ponizej_od")) if przed.get("ponizej_od") else None
        wyslano, sucho = _lista_ms(przed.get("wyslano")), _lista_ms(przed.get("na_sucho"))
        dla = _podlej_dla(przed.get("podlej_dla"))
        if od is not None:
            gleba, prog = _gleba(s), _liczba(s.get("prog_gleba"))
            podlana = any((_ms(p.get("ts")) or 0) > od for p in _lista(s.get("podlania")) if isinstance(p, dict))
            mokro = gleba is not None and prog is not None and gleba >= prog + HISTEREZA_GLEBY
            # bez progu w jednostkach czujnika (stan sprzed etapu 4) nie ma histerezy
            bez_histerezy = werdykt == "ok" and prog is None
            if podlana or mokro or bez_histerezy or werdykt == "nauka":
                od = None
        if od is None:
            wyslano, sucho, dla = [], [], {}
            od = teraz_ms if werdykt in PONIZEJ else None
        moja = {"ponizej_od": iso(od) if od is not None else None,
                "wyslano": [iso(m) for m in wyslano], "na_sucho": [iso(m) for m in sucho]}
        if od is not None and werdykt in PONIZEJ:
            ponizej.append(s)
            licz = sorted(wyslano + sucho) if na_sucho else wyslano
            odstep = _odstep(s)
            # Poranne 2 godz. od końca nocy dotyczą tylko pierwszej wysyłki epizodu.
            # Ponowienie czekało na nie także, więc „azalia co 12 godz." w praktyce
            # wypadało raz na dobę około 10:00, jak u pozostałych (przegląd 9.10).
            start = od if rano_ms is None else max(od, rano_ms)
            if (not noc and (licz or teraz_ms - start >= TRWA_PONIZEJ_MS - ZAPAS_PRZEBIEGU_MS)
                    and len(licz) < MAKS_WYSYLEK_EPIZODU
                    and (not licz or teraz_ms - licz[-1] >= odstep - ZAPAS_PRZEBIEGU_MS)):
                do_podlania.append(s)

        # czujnik: raz na powód
        powody: dict[str, str] = {}
        for tekst in _lista(s.get("do_zgloszenia")):
            if isinstance(tekst, str) and tekst:
                powody.setdefault(_powod(tekst), tekst)
        czujnik = przed.get("czujnik") if isinstance(przed.get("czujnik"), dict) else {}
        # Bateria na granicy low/middle skakałaby co kilka godzin i za każdym powrotem do
        # „low" szedłby nowy alarm. Znacznik „bateria" trzyma się, dopóki czujnik nie zgłosi
        # „high", czyli do wymiany baterii (przegląd 9.10: 28 alarmów zamiast 1).
        ostatnie = s.get("ostatnie") if isinstance(s.get("ostatnie"), dict) else {}
        bateria = ostatnie.get("bateria") if isinstance(ostatnie.get("bateria"), dict) else {}
        trzymaj = {"bateria"} if str(bateria.get("v", "")).lower() not in ("high", "") else set()
        czujnik = {p: dict(v) for p, v in czujnik.items() if (p in powody or p in trzymaj) and isinstance(v, dict)}
        nocne = [n for n in _lista(przed.get("noc")) if isinstance(n, dict) and n.get("powod")]
        if not noc:
            # nocna „bateria" rano dalej trwa — idzie jako zwykły alarm, nie „do rana minęło"
            for n in nocne:
                if n["powod"] in trzymaj and n["powod"] not in powody:
                    powody[n["powod"]] = str(n.get("tekst", ""))
        powody_teraz[nazwa] = (powody, trzymaj)
        nowe = [p for p in powody if not (czujnik.get(p, {}).get("wyslano")
                                          or (na_sucho and czujnik.get(p, {}).get("na_sucho")))]
        if noc:
            znane = {n["powod"] for n in nocne}
            nocne += [{"powod": p, "tekst": powody[p], "ts": teraz_iso} for p in nowe if p not in znane]
        else:
            minione = [f"{nazwa}: w nocy ({_lokalnie(_ms(n.get('ts')) or teraz_ms, strefa)}) "
                       f"{_mala(str(n.get('tekst', '')))} Do rana minęło."
                       for n in nocne if n["powod"] not in powody]
            if nowe or minione:
                # Wpis niesie wszystkie trwające powody, nie tylko nowe: ten sam tag podmienia
                # na telefonie poprzedni alarm tej rośliny, więc inaczej nieprzeczytana
                # „bateria" znikałaby pod nowym „sonda wyjęta".
                czujnik_nowe.append((nazwa, dict(powody), minione))
            if powody or minione:
                czujnik_trwa.append((nazwa, dict(powody), minione))
            nocne = []                   # rano noc wychodzi — w tym wpisie albo w powitaniu
            for p in (powody if wlaczanie else nowe):
                czujnik.setdefault(p, {})[znacznik_wysylki] = teraz_iso
        moja.update({"czujnik": czujnik, "noc": nocne})

        # przestaw: epizod kierunku, jedna wysyłka
        kierunek, u, szczyt = _ocena(s)
        epizod = przed.get("przestaw")
        epizod = dict(epizod) if isinstance(epizod, dict) and epizod.get("kierunek") in KIERUNKI_PRZESTAW else None
        if kierunek in KIERUNKI_PRZESTAW:
            if epizod is None or epizod["kierunek"] != kierunek:
                epizod = {"kierunek": kierunek, "od": teraz_iso}
        elif kierunek is not None and epizod is not None and (kierunek == "ok" or (
                u is not None and u >= PRZESTAW_KONIEC_U)):
            epizod = None
        if epizod is not None:
            moja["przestaw"] = epizod
            # Treść potrzebuje świeżej oceny w kierunku epizodu: w paśmie histerezy („malo",
            # u < 0,45) epizod trwa, ale „przestaw bliżej okna" przy 40% już by kłamało.
            if kierunek == epizod["kierunek"]:
                przestaw_trwa.append((s, epizod, u, szczyt))
                if not (epizod.get("wyslano") or (na_sucho and epizod.get("na_sucho"))) and not noc:
                    do_przestawienia.append((s, epizod, u, szczyt))
        # Na końcu słownika: doręczenie w tym przebiegu dopisuje klucz na końcu, a następny
        # przebieg musi go odtworzyć w tym samym miejscu — inaczej plik zmieniałby się raz
        # bez zmiany danych. Bez doręczeń klucza nie ma wcale (plik jak dotąd).
        if dla:
            moja["podlej_dla"] = dla
        stan_regul[nazwa] = moja

    nowe_wpisy = []
    zajete = {w.get("id") for w in historia if isinstance(w.get("id"), str)}

    def wpis(regula: str, nazwy: list[str], tytul: str, tresc: str, tag: str, do_kogo: list[str],
             url: str | None = None, odlozone: bool = False) -> dict:
        baza = datetime.fromtimestamp(teraz_ms / 1000, timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + regula
        ident, n = baza, 1
        while ident in zajete:           # „Re-run" w tej samej sekundzie albo zegar cofnięty
            n += 1
            ident = f"{baza}-{n}"
        zajete.add(ident)
        w = {"id": ident, "ts": teraz_iso, "przebieg": str(przebieg), "regula": regula,
             "rosliny": nazwy, "tytul": tytul, "tresc": tresc, "tag": tag,
             "url": url or _adres(nazwy[0] if len(nazwy) == 1 else None), "na_sucho": na_sucho,
             "telefony": list(do_kogo)}
        if odlozone:
            w["odlozone"] = True
        nowe_wpisy.append(w)
        return w

    def rozeslij(regula: str, pozycje: list[dict]) -> list[str]:
        """Telefony, które dostają wpis teraz; tym w ciszy (z włączoną regułą) kolejka."""
        teraz_t, w_ciszy = telefony.adresaci(KLUCZ_USTAWIEN[regula], ust, lokalnie)
        for p in pozycje:
            _odloz(kolejki, w_ciszy, p)
        return teraz_t

    def wyslano_podlej(lista: list[dict]) -> None:
        for s in lista:
            stan_regul[s["nazwa"]][znacznik_wysylki].append(teraz_iso)

    def niedawno_doreczone(s: dict, t: str) -> bool:
        """Telefon `t` dostał odłożone „podlej" tej rośliny mniej niż odstęp gatunku temu.

        Ponowienia epizodu liczą się od wysyłki do telefonów poza ciszą, a odłożone wychodzi
        dopiero po ciszy danego telefonu — bez tego Android z ciszą 21–8 dostawał „Podlej:
        azalia" o 8:01 jako odłożone i znowu o 9:01 jako świeże ponowienie, 12 godz. po
        wysyłce do iPhone'a z ciszą 23–7 (przegląd, C3)."""
        kiedy = _ms((stan_regul.get(s["nazwa"]) or {}).get("podlej_dla", {}).get(t))
        return kiedy is not None and teraz_ms - kiedy < _odstep(s) - ZAPAS_PRZEBIEGU_MS

    if wlaczanie:
        nazwy = list(dict.fromkeys([s["nazwa"] for s in ponizej] + [n for n, _, _ in czujnik_trwa]
                                   + [s["nazwa"] for s, *_ in przestaw_trwa]))
        linie = ([_linia_podlej(s) for s in ponizej]
                 + [x for n, p, m in czujnik_trwa for x in _linie_czujnika(n, p, m)]
                 + [_linia_przestaw(s, e["kierunek"], u, sz) for s, e, u, sz in przestaw_trwa])
        # bez kolejki: powitanie po nocy byłoby już nieaktualne, a „Już trwa" i tak niesie
        # wszystko, co trwa
        do_kogo, _ = telefony.adresaci(None, ust, lokalnie)
        wpis("wlaczone", nazwy, "Powiadomienia włączone",
             ("Już trwa:\n" + "\n".join(linie)) if linie else "Teraz nic nie wymaga uwagi.", "wlaczone", do_kogo)
        wyslano_podlej(ponizej)
        for _, e, _, _ in przestaw_trwa:
            e[znacznik_wysylki] = teraz_iso
    elif not noc:
        if do_podlania:
            # Odłożone („dostaniesz po ciszy") nie zjadają limitu dnia — to ta sama decyzja,
            # która już raz się w nim policzyła. Liczone po przebiegach (`ts`), a nie po
            # wpisach: telefon, któremu niedawno doręczono jedną z roślin, dostaje w tym samym
            # przebiegu osobny wpis z resztą — to wciąż jedna decyzja.
            dzis_podlej = len({w["ts"] for w in historia
                               if w.get("regula") == "podlej" and not w.get("odlozone")
                               and (na_sucho or w.get("na_sucho") is False)
                               and datetime.fromtimestamp(_ms(w["ts"]) / 1000, strefa).date() == dzis})
            if dzis_podlej < MAKS_PODLEJ_NA_DOBE:
                nazwy = [s["nazwa"] for s in do_podlania]
                do_kogo = rozeslij("podlej", [{"regula": "podlej", "obiekt": s["nazwa"], "ts": teraz_iso,
                                               "ponizej_od": stan_regul[s["nazwa"]]["ponizej_od"]}
                                              for s in do_podlania])
                # Wpis decyzji idzie do telefonów, którym żadnej z tych roślin nie doręczono
                # niedawno jako odłożonej (może zostać z pustą listą — epizod i tak liczy
                # wysyłkę, jak przy wyłączonej regule). Telefon z takim doręczeniem dostaje
                # osobny wpis z pozostałymi roślinami albo nic. Kolejka bez zmian: telefon
                # w ciszy dostanie pozycję, a sprawdzenie zapada przy doręczeniu.
                pelne = [t for t in do_kogo if not any(niedawno_doreczone(s, t) for s in do_podlania)]
                wpis("podlej", nazwy, *_tresc_podlej(do_podlania), _znacznik("podlej", nazwy), pelne)
                czesciowe: dict[tuple, list[str]] = {}
                for t in do_kogo:
                    moje = tuple(s["nazwa"] for s in do_podlania if not niedawno_doreczone(s, t))
                    if moje and t not in pelne:
                        czesciowe.setdefault(moje, []).append(t)
                for moje, kto in czesciowe.items():
                    lista = [s for s in do_podlania if s["nazwa"] in moje]
                    wpis("podlej", list(moje), *_tresc_podlej(lista), _znacznik("podlej", list(moje)), kto)
                wyslano_podlej(do_podlania)
        if czujnik_nowe:
            nazwy = [n for n, _, _ in czujnik_nowe]
            do_kogo = rozeslij("czujnik", [{"regula": "czujnik", "obiekt": n, "ts": teraz_iso,
                                            "powody": [{"powod": k, "tekst": tekst, "ts": teraz_iso}
                                                       for k, tekst in p.items()],
                                            "minione": list(m)} for n, p, m in czujnik_nowe])
            wpis("czujnik", nazwy, "Czujnik: " + ", ".join(_mala(n) for n in nazwy),
                 "\n".join(x for n, p, m in czujnik_nowe for x in _linie_czujnika(n, p, m)),
                 _znacznik("czujnik", nazwy), do_kogo)
        if do_przestawienia:
            nazwy = [s["nazwa"] for s, *_ in do_przestawienia]
            do_kogo = rozeslij("przestaw", [{"regula": "przestaw", "obiekt": s["nazwa"], "ts": teraz_iso,
                                             "kierunek": e["kierunek"]} for s, e, _, _ in do_przestawienia])
            wpis("przestaw", nazwy, *_tresc_przestaw([(s, e["kierunek"], u, sz) for s, e, u, sz in do_przestawienia]),
                 _znacznik("przestaw", nazwy), do_kogo)
            for _, e, _, _ in do_przestawienia:
                e[znacznik_wysylki] = teraz_iso

    podsumowanie = poprz.get("podsumowanie_ostatnie")
    podsumowanie = podsumowanie if isinstance(podsumowanie, str) else None

    def tresc_podsumowania() -> str:
        return ("\n".join(_linia_podsumowania(s, dzis, strefa) for s in rosliny_teraz)
                or "Brak stanu roślin — sprawdź kolektor.")

    # Przebieg z powitaniem to jeden wpis; podsumowanie pójdzie w następnym.
    if (not noc and not wlaczanie and lokalnie.weekday() == 6 and lokalnie.hour >= PODSUMOWANIE_OD_H
            and podsumowanie != dzis.isoformat()):
        do_kogo = rozeslij("podsumowanie", [{"regula": "podsumowanie", "obiekt": None, "ts": teraz_iso}])
        wpis("podsumowanie", [s["nazwa"] for s in rosliny_teraz], "Rośliny — podsumowanie tygodnia",
             tresc_podsumowania(), "podsumowanie", do_kogo, url="#rosliny")
        podsumowanie = dzis.isoformat()

    # Koniec ciszy telefonu: kolejka wychodzi raz, sprawdzona na świeżym stanie.
    swieze = list(nowe_wpisy)
    for t in telefony.TELEFONY:
        kolejka = kolejki[t]["odlozone"]
        if not kolejka or telefony.w_ciszy(ust[t], lokalnie):
            continue
        kolejki[t]["odlozone"] = []
        if wlaczanie:
            continue                     # powitanie „Już trwa" niesie to, co jeszcze trwa

        def czeka(regula: str, t=t, kolejka=kolejka) -> list[dict]:
            """Pozycje reguły, której telefon dalej chce, i których świeży wpis tego
            przebiegu dla tego telefonu jeszcze nie niesie."""
            if not ust[t].get(KLUCZ_USTAWIEN[regula]):
                return []
            return [p for p in kolejka if p.get("regula") == regula
                    and (p.get("obiekt") is None or isinstance(p.get("obiekt"), str))
                    and not any(w["regula"] == regula and t in w["telefony"]
                                and (p.get("obiekt") is None or p.get("obiekt") in w["rosliny"]) for w in swieze)]

        podlej = []
        for p in czeka("podlej"):
            s = obecne.get(p.get("obiekt"))
            # podlana w nocy albo nowy epizod — to już nie ta sama sprawa
            if (s is not None and s.get("werdykt") in PONIZEJ and s["nazwa"] not in [x["nazwa"] for x in podlej]
                    and (stan_regul.get(s["nazwa"]) or {}).get("ponizej_od") == p.get("ponizej_od")
                    and not niedawno_doreczone(s, t)):
                podlej.append(s)
        if podlej:
            nazwy = [s["nazwa"] for s in podlej]
            wpis("podlej", nazwy, *_tresc_podlej(podlej), _znacznik("podlej", nazwy), [t], odlozone=True)
            # Chwila doręczenia, od której liczy się następne ponowienie dla tego telefonu.
            # Znika z końcem epizodu (nowe `ponizej_od`), więc bez doręczeń plik się nie zmienia.
            for s in podlej:
                stan_regul[s["nazwa"]].setdefault("podlej_dla", {})[t] = teraz_iso

        czujnik = []
        for p in czeka("czujnik"):
            nazwa = p.get("obiekt")
            if nazwa not in obecne or nazwa in [n for n, _ in czujnik]:
                continue
            akt, trzymaj = powody_teraz[nazwa]
            linie = []
            for r in _lista(p.get("powody")):
                if not isinstance(r, dict) or not isinstance(r.get("powod"), str):
                    continue
                tekst = str(r.get("tekst", ""))
                if r["powod"] in akt:
                    linie.append(f"{nazwa}: {_mala(akt[r['powod']])}")
                elif r["powod"] in trzymaj:
                    linie.append(f"{nazwa}: {_mala(tekst)}")
                else:
                    linie.append(f"{nazwa}: w nocy ({_lokalnie(_ms(r.get('ts')) or teraz_ms, strefa)}) "
                                 f"{_mala(tekst)} Do rana minęło.")
            linie += [x for x in _lista(p.get("minione")) if isinstance(x, str)]
            if linie:
                czujnik.append((nazwa, list(dict.fromkeys(linie))))
        if czujnik:
            nazwy = [n for n, _ in czujnik]
            wpis("czujnik", nazwy, "Czujnik: " + ", ".join(_mala(n) for n in nazwy),
                 "\n".join(x for _, ls in czujnik for x in ls), _znacznik("czujnik", nazwy), [t], odlozone=True)

        przestaw = []
        for p in czeka("przestaw"):
            s = obecne.get(p.get("obiekt"))
            if s is None or s["nazwa"] in [x[0]["nazwa"] for x in przestaw]:
                continue
            kierunek, u, szczyt = _ocena(s)
            epizod = (stan_regul.get(s["nazwa"]) or {}).get("przestaw")
            if (kierunek == p.get("kierunek") and isinstance(epizod, dict)
                    and epizod.get("kierunek") == kierunek):
                przestaw.append((s, kierunek, u, szczyt))
        if przestaw:
            nazwy = [s["nazwa"] for s, *_ in przestaw]
            wpis("przestaw", nazwy, *_tresc_przestaw(przestaw), _znacznik("przestaw", nazwy), [t], odlozone=True)

        if czeka("podsumowanie"):
            wpis("podsumowanie", [s["nazwa"] for s in rosliny_teraz], "Rośliny — podsumowanie tygodnia",
                 tresc_podsumowania(), "podsumowanie", [t], url="#rosliny", odlozone=True)

    for t in telefony.TELEFONY:
        kolejki[t]["odlozone"] = telefony.przytnij_odlozone(kolejki[t]["odlozone"], teraz_ms, _ms)

    return {"tryb": tryb, "wlaczone_od": wlaczone_od, "historia": historia + nowe_wpisy,
            "stan_regul": stan_regul, "podsumowanie_ostatnie": podsumowanie, "telefony": kolejki}
