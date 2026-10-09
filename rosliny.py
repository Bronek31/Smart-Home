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
import json
import math
import re
import statistics
import unicodedata
from collections import deque
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

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
GATUNKI = {
    "fikus": {"prog": 0.45, "prog_zima": 0.35, "pilne": None, "granice": (0.20, 0.55),
              "swiatlo_lxh": 20000},
    "skrzydlokwiat": {"prog": 0.60, "prog_zima": 0.50, "pilne": None, "granice": (0.40, 0.70),
                      "swiatlo_lxh": 10000},
    "azalia": {"prog": 0.75, "prog_zima": 0.75, "pilne": 0.60, "granice": (0.60, 0.85),
               "swiatlo_lxh": 28000,
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
        # Nazwa to klucz zakładki i powiadomień (rosliny.html#roslina=Fikus) — dwie takie
        # same i druga roślina byłaby nie do wybrania.
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
    """Dobowa suma światła [lx·h] w lokalnych dobach, z pokryciem pomiarem (0–1).

    Światło przychodzi rzadko (co 1–2 godz., pomiar z nocy 8/9.10), więc trzymamy ostatnią
    wartość do następnego odczytu, ale najwyżej `maks_ms` — dłuższa przerwa to brak
    pomiaru, a nie ciemność. Pokrycie mówi, jaką część doby naprawdę zmierzono; doba
    z niskim pokryciem nie nadaje się do reguły „za ciemno".
    """
    if od_ms >= do_ms:
        return []
    doby: dict[str, list[float]] = {}

    def dodaj(a: int, b: int, v: float):
        while a < b:
            lokalnie = datetime.fromtimestamp(a / 1000, strefa)
            nastepna = (lokalnie + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            koniec = min(b, int(nastepna.timestamp() * 1000))
            suma = doby.setdefault(lokalnie.date().isoformat(), [0.0, 0.0])
            suma[0] += v * (koniec - a) / GODZ
            suma[1] += (koniec - a)
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
        lxh, zmierzone = doby.get(dzien.isoformat(), [0.0, 0.0])
        out.append({"data": dzien.isoformat(), "lxh": round(lxh),
                    "pokrycie": round(min(1.0, zmierzone / dlugosc), 2)})
        dzien += timedelta(days=1)
    return out


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
    return {
        "czujnik": czujnik, "nazwa": konf["nazwa"], "gatunek": konf["gatunek"],
        "pokoj": konf.get("pokoj"), "sucho": sucho, "od": konf.get("od"),
        "ostatnie": ostatnie, "szereg": szereg, "swiatlo_dobowe": swiatlo,
        "swiatlo_potrzeba_lxh": GATUNKI[konf["gatunek"]]["swiatlo_lxh"],
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

# Cisza nocna czasu `strefa`: od 21:00 do 8:00 nic nie wychodzi.
NOC_OD_H, NOC_DO_H = 21, 8
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
# Doba z mniejszym pokryciem pomiarem to nie „pełna doba" w podsumowaniu — ta sama
# granica co „niepełny pomiar" na stronie (rosliny.html, `pokrycie<.8`).
POKRYCIE_PELNEJ_DOBY = 0.8

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
    if not nazwa:
        return "rosliny.html"
    # z tym `safe` quote koduje dokładnie jak encodeURIComponent, który strona odwraca
    return "rosliny.html#roslina=" + quote(nazwa, safe="!'()*")


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
    linia = f"{stan['nazwa']}: " + (f"gleba {gleba:.0f}%" if gleba is not None else "czas podlać")
    if gleba is not None and prog is not None:
        linia += f" (podlewaj przy ok. {prog:.0f}%)"
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
        czesci[0] += f", gleba {gleba:.0f}%" + (f" (podlewaj przy ok. {prog:.0f}%)" if prog is not None else "")
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
        swiatlo = f"światło śr. {srednio:,.0f} lx·h na dobę".replace(",", " ")
        if potrzeba:
            swiatlo += f", {100 * srednio / potrzeba:.0f}% potrzeby"
        czesci.append(swiatlo + f" (pełne doby: {len(doby)} z 7)")
    else:
        czesci.append("światło: za mało pomiaru z ostatnich 7 dób")
    return "; ".join(czesci) + "."


def zaplanuj_powiadomienia(stany: list[dict], poprzednie: dict | None, teraz_ms: int,
                           strefa: ZoneInfo, tryb: str, przebieg: str) -> dict:
    """Zwraca NOWĄ zawartość data/rosliny/powiadomienia.json.

    `stany` to wyniki stan_rosliny() z tego przebiegu, `poprzednie` — dotychczasowa
    zawartość pliku (albo None), `tryb` — "wlaczone" albo "na-sucho" (cokolwiek innego
    to na sucho), `przebieg` — "$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT". Plik jest publiczny,
    więc nie ma w nim adresów subskrypcji. Wszystko liczy się od `teraz_ms`, a bez
    zmian w stanach wynik jest ten sam — plik nie zmienia się co przebieg.

    Reguły (ROSLINY.md, „Reguły powiadomień"):
    - **podlej** — werdykt `podlej`/`pilne` trwa ≥ 2 godz. od `ponizej_od` (po nocy od
      8:00). Epizod kończy wykryte podlanie po `ponizej_od` albo gleba ≥ próg + 6 pkt;
      w paśmie histerezy (werdykt już `ok`, gleba jeszcze poniżej progu + 6) epizod
      trwa, ale nic nie wychodzi. Ponowienie co 24 godz. (azalia co 12), najwyżej
      3 razy na epizod, najwyżej 2 takie wpisy na lokalną dobę. `nauka` kończy epizod.
    - **czujnik** — każdy powód z `do_zgloszenia` raz; gdy zniknie, znika ze stanu
      i może wrócić. W nocy trafia do `noc` i wychodzi rano — także gdy w nocy minął.
    - **podsumowanie** — pierwszy przebieg w niedzielę od 10:00, zawsze.
    - **cisza nocna** 21:00–8:00: nic nie wychodzi.
    - **na sucho** — te same decyzje, wpisy z `na_sucho: true`, a w stanie reguł
      znaczniki `na_sucho` zamiast `wyslano`. Na sucho liczą się jedne i drugie (tak
      by było, gdyby wysyłka była włączona), po włączeniu tylko prawdziwe wysyłki.
      Pierwszy dzienny przebieg po włączeniu daje jeden wpis `wlaczone` z tym, co już
      trwa (podlej i czujnik), zamiast osobnych — i zawsze, także gdy nic nie trwa:
      to pierwsze prawdziwe powiadomienie, po nim widać, czy telefon je dostaje.

    Jeden przebieg dokłada najwyżej jeden wpis na regułę („Podlej: azalia,
    skrzydłokwiat" to jeden wpis), a nie jeden wpis na wszystko: znacznik zastępuje na
    telefonie poprzednie powiadomienie o tym samym, a zbiorczy wpis „podlej + czujnik"
    zniknąłby pod następnym „podlej" razem z nieprzeczytanym alarmem czujnika. Limit
    „2 zwykłe na dobę" liczy się wtedy wprost z historii.
    """
    na_sucho = tryb != "wlaczone"
    tryb = "na-sucho" if na_sucho else "wlaczone"
    poprz = poprzednie if isinstance(poprzednie, dict) else {}
    lokalnie = datetime.fromtimestamp(teraz_ms / 1000, strefa)
    noc = lokalnie.hour >= NOC_OD_H or lokalnie.hour < NOC_DO_H
    dzis = lokalnie.date()
    rano_ms = int(datetime(dzis.year, dzis.month, dzis.day, NOC_DO_H, tzinfo=strefa).timestamp() * 1000)
    teraz_iso = iso(teraz_ms)
    znacznik_wysylki = "na_sucho" if na_sucho else "wyslano"

    historia = []
    for w in _lista(poprz.get("historia")):
        ts = _ms(w.get("ts")) if isinstance(w, dict) else None
        if ts is not None and teraz_ms - ts <= DNI_POWIADOMIEN * DOBA:
            historia.append(w)

    # Włączenie: pierwszy przebieg w trybie "wlaczone", który może coś wysłać. W nocy
    # `wlaczone_od` zostaje puste i powitanie wychodzi rano.
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

    rosliny_teraz, do_podlania, ponizej, czujnik_nowe, czujnik_trwa = [], [], [], [], []
    for s in _lista(stany):
        if not isinstance(s, dict) or not isinstance(s.get("nazwa"), str) or not s["nazwa"]:
            continue
        nazwa, werdykt = s["nazwa"], s.get("werdykt")
        przed = stan_regul.get(nazwa) or {}
        rosliny_teraz.append(s)

        # podlej: epizod
        od = _ms(przed.get("ponizej_od")) if przed.get("ponizej_od") else None
        wyslano, sucho = _lista_ms(przed.get("wyslano")), _lista_ms(przed.get("na_sucho"))
        if od is not None:
            gleba, prog = _gleba(s), _liczba(s.get("prog_gleba"))
            podlana = any((_ms(p.get("ts")) or 0) > od for p in _lista(s.get("podlania")) if isinstance(p, dict))
            mokro = gleba is not None and prog is not None and gleba >= prog + HISTEREZA_GLEBY
            # bez progu w jednostkach czujnika (stan sprzed etapu 4) nie ma histerezy
            bez_histerezy = werdykt == "ok" and prog is None
            if podlana or mokro or bez_histerezy or werdykt == "nauka":
                od = None
        if od is None:
            wyslano, sucho = [], []
            od = teraz_ms if werdykt in PONIZEJ else None
        moja = {"ponizej_od": iso(od) if od is not None else None,
                "wyslano": [iso(m) for m in wyslano], "na_sucho": [iso(m) for m in sucho]}
        if od is not None and werdykt in PONIZEJ:
            ponizej.append(s)
            licz = sorted(wyslano + sucho) if na_sucho else wyslano
            gatunek = s.get("gatunek")
            odstep = PONOWIENIE_GATUNKU_MS.get(gatunek, PONOWIENIE_MS) if isinstance(gatunek, str) else PONOWIENIE_MS
            if (not noc and teraz_ms - max(od, rano_ms) >= TRWA_PONIZEJ_MS - ZAPAS_PRZEBIEGU_MS
                    and len(licz) < MAKS_WYSYLEK_EPIZODU
                    and (not licz or teraz_ms - licz[-1] >= odstep - ZAPAS_PRZEBIEGU_MS)):
                do_podlania.append(s)

        # czujnik: raz na powód
        powody: dict[str, str] = {}
        for tekst in _lista(s.get("do_zgloszenia")):
            if isinstance(tekst, str) and tekst:
                powody.setdefault(_powod(tekst), tekst)
        czujnik = przed.get("czujnik") if isinstance(przed.get("czujnik"), dict) else {}
        czujnik = {p: dict(v) for p, v in czujnik.items() if p in powody and isinstance(v, dict)}
        nocne = [n for n in _lista(przed.get("noc")) if isinstance(n, dict) and n.get("powod")]
        nowe = [p for p in powody if not (czujnik.get(p, {}).get("wyslano")
                                          or (na_sucho and czujnik.get(p, {}).get("na_sucho")))]
        if noc:
            znane = {n["powod"] for n in nocne}
            nocne += [{"powod": p, "tekst": powody[p], "ts": teraz_iso} for p in nowe if p not in znane]
        else:
            linie = [f"{nazwa}: {_mala(powody[p])}" for p in nowe]
            minione = [f"{nazwa}: w nocy ({_lokalnie(_ms(n.get('ts')) or teraz_ms, strefa)}) "
                       f"{_mala(str(n.get('tekst', '')))} Do rana minęło."
                       for n in nocne if n["powod"] not in powody]
            if linie or minione:
                czujnik_nowe.append((nazwa, linie + minione))
            if powody or minione:
                czujnik_trwa.append((nazwa, [f"{nazwa}: {_mala(t)}" for t in powody.values()] + minione))
            nocne = []                   # rano noc wychodzi — w tym wpisie albo w powitaniu
            for p in (powody if wlaczanie else nowe):
                czujnik.setdefault(p, {})[znacznik_wysylki] = teraz_iso
        moja.update({"czujnik": czujnik, "noc": nocne})
        stan_regul[nazwa] = moja

    nowe_wpisy = []
    zajete = {w.get("id") for w in historia if isinstance(w.get("id"), str)}

    def wpis(regula: str, nazwy: list[str], tytul: str, tresc: str, tag: str, url: str | None = None) -> None:
        baza = datetime.fromtimestamp(teraz_ms / 1000, timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + regula
        ident, n = baza, 1
        while ident in zajete:           # „Re-run" w tej samej sekundzie albo zegar cofnięty
            n += 1
            ident = f"{baza}-{n}"
        zajete.add(ident)
        nowe_wpisy.append({"id": ident, "ts": teraz_iso, "przebieg": str(przebieg), "regula": regula,
                           "rosliny": nazwy, "tytul": tytul, "tresc": tresc, "tag": tag,
                           "url": url or _adres(nazwy[0] if nazwy else None), "na_sucho": na_sucho})

    def wyslano_podlej(lista: list[dict]) -> None:
        for s in lista:
            stan_regul[s["nazwa"]][znacznik_wysylki].append(teraz_iso)

    if wlaczanie:
        nazwy = list(dict.fromkeys([s["nazwa"] for s in ponizej] + [n for n, _ in czujnik_trwa]))
        linie = [_linia_podlej(s) for s in ponizej] + [x for _, ls in czujnik_trwa for x in ls]
        wpis("wlaczone", nazwy, "Powiadomienia włączone",
             ("Już trwa:\n" + "\n".join(linie)) if linie else "Teraz nic nie wymaga uwagi.", "wlaczone")
        wyslano_podlej(ponizej)
    elif not noc:
        if do_podlania:
            dzis_podlej = sum(1 for w in historia
                              if w.get("regula") == "podlej" and (na_sucho or w.get("na_sucho") is False)
                              and datetime.fromtimestamp(_ms(w["ts"]) / 1000, strefa).date() == dzis)
            if dzis_podlej < MAKS_PODLEJ_NA_DOBE:
                nazwy = [s["nazwa"] for s in do_podlania]
                tytul = ", ".join(_mala(s["nazwa"]) + (" (pilne)" if s.get("werdykt") == "pilne" else "")
                                  for s in do_podlania)
                wpis("podlej", nazwy, f"Podlej: {tytul}", "\n".join(_linia_podlej(s) for s in do_podlania),
                     _znacznik("podlej", nazwy))
                wyslano_podlej(do_podlania)
        if czujnik_nowe:
            nazwy = [n for n, _ in czujnik_nowe]
            wpis("czujnik", nazwy, "Czujnik: " + ", ".join(_mala(n) for n in nazwy),
                 "\n".join(x for _, ls in czujnik_nowe for x in ls), _znacznik("czujnik", nazwy))

    podsumowanie = poprz.get("podsumowanie_ostatnie")
    podsumowanie = podsumowanie if isinstance(podsumowanie, str) else None
    # Przebieg z powitaniem to jeden wpis; podsumowanie pójdzie w następnym.
    if (not noc and not wlaczanie and lokalnie.weekday() == 6 and lokalnie.hour >= PODSUMOWANIE_OD_H
            and podsumowanie != dzis.isoformat()):
        tresc = "\n".join(_linia_podsumowania(s, dzis, strefa) for s in rosliny_teraz)
        wpis("podsumowanie", [s["nazwa"] for s in rosliny_teraz], "Rośliny — podsumowanie tygodnia",
             tresc or "Brak stanu roślin — sprawdź kolektor.", "podsumowanie", url="rosliny.html")
        podsumowanie = dzis.isoformat()

    return {"tryb": tryb, "wlaczone_od": wlaczone_od, "historia": historia + nowe_wpisy,
            "stan_regul": stan_regul, "podsumowanie_ostatnie": podsumowanie}
