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
import statistics
from collections import deque
from datetime import datetime, timedelta, timezone
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
