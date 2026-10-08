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

import json
import statistics
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
               "swiatlo_lxh": 28000},
}
ZIMA = {10, 11, 12, 1, 2}

# Ile czasu po ostatnim kept odczycie trzymamy wiersz, nawet jeśli wartość się nie
# zmieniła. Gleba przychodzi co ok. 30 s ze stałą wartością (pomiar 8.10), więc bez
# przerzedzania byłoby ok. 3000 wierszy na dobę na czujnik, a godzinny wiersz wystarcza,
# żeby odróżnić „stoi" od „milczy".
PRZERZEDZENIE_MS = GODZ
# Dłużej niż tyle bez odczytu to cisza, a nie stan trwający — w szeregu godzinowym
# i w sumie światła nie przeciągamy ostatniej wartości dalej.
MAKS_PRZERWA_MS = 2 * GODZ
# Skok gleby o co najmniej tyle punktów w ciągu OKNO_PODLANIA_MS to podlanie.
SKOK_PODLANIA = 10.0
OKNO_PODLANIA_MS = 2 * GODZ
# Szczyt po podlaniu: mediana odczytów w tym oknie po wykrytym podlaniu, kiedy woda już
# spłynęła, a ziemia jeszcze nie zaczęła schnąć.
SZCZYT_OD_MS, SZCZYT_DO_MS = 2 * GODZ, 6 * GODZ
# Cisza dłuższa niż to — czujnik wymaga uwagi.
CISZA_MS = 12 * GODZ
DNI_HISTORII = 30


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
    return wartosc if wartosc == wartosc else None          # NaN to brak


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
    out, widziane = [], set()
    for i, r in enumerate(lista, 1):
        if not isinstance(r, dict):
            raise ValueError(f"rosliny.json: wpis {i} nie jest obiektem")
        czujnik, nazwa, gatunek = r.get("czujnik"), r.get("nazwa"), r.get("gatunek")
        if not czujnik or not nazwa:
            raise ValueError(f"rosliny.json: wpis {i} bez „czujnik\" albo „nazwa\"")
        if czujnik in widziane:
            raise ValueError(f"rosliny.json: czujnik {czujnik} wpisany dwa razy")
        widziane.add(czujnik)
        if gatunek not in GATUNKI:
            raise ValueError(f"rosliny.json: {nazwa} — nieznany gatunek {gatunek!r} "
                             f"(znane: {', '.join(GATUNKI)})")
        kody = r.get("kody")
        if not isinstance(kody, dict) or not kody.get("gleba"):
            raise ValueError(f"rosliny.json: {nazwa} — brak „kody\" z kodem gleby")
        obce = set(kody) - set(RODZAJE)
        if obce:
            raise ValueError(f"rosliny.json: {nazwa} — nieznane rodzaje kodów: {', '.join(sorted(obce))}")
        if len(set(kody.values())) != len(kody):
            raise ValueError(f"rosliny.json: {nazwa} — jeden kod chmury wpisany pod dwa rodzaje")
        sucho = r.get("sucho")
        if sucho is not None and _liczba(sucho) is None:
            raise ValueError(f"rosliny.json: {nazwa} — „sucho\" musi być liczbą")
        od = r.get("od")
        if od is not None and _ms(od) is None:
            raise ValueError(f"rosliny.json: {nazwa} — „od\" to nie data ISO")
        out.append({
            "czujnik": str(czujnik), "nazwa": str(nazwa), "gatunek": gatunek,
            "pokoj": r.get("pokoj"), "kody": {k: str(v) for k, v in kody.items()},
            "sucho": _liczba(sucho), "od": od,
        })
    return out


def zwin(wiersze: list[dict], co_ile_ms: int = PRZERZEDZENIE_MS) -> list[dict]:
    """Przerzedza odczyty: z każdej serii (czujnik, kod) zostaje wiersz, gdy wartość się
    zmieniła albo od ostatniego zostawionego minęło `co_ile_ms`.

    Idempotentne: przerzedzenie przerzedzonego niczego nie zmienia — kolektor może więc
    przerzedzać cały plik miesięczny przy każdym przebiegu, także gdy zakładka dołożyła
    z powrotem wiersze wycięte w poprzednim.
    """
    def klucz(w):
        return (w["device_id"], w["code"], w["ts"])

    out, ostatni = [], {}
    for w in sorted(wiersze, key=klucz):
        seria = (w["device_id"], w["code"])
        teraz = _ms(w["ts"])
        poprzedni = ostatni.get(seria)
        if (poprzedni is None or teraz is None or poprzedni[1] is None
                or str(w["value"]) != poprzedni[0] or teraz - poprzedni[1] >= co_ile_ms):
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

    Światło przychodzi rzadko (1–2 wpisy na godzinę, pomiar 8.10), więc trzymamy ostatnią
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


def podlania(gleba: list[tuple[int, float]], skok: float = SKOK_PODLANIA,
             okno_ms: int = OKNO_PODLANIA_MS) -> list[dict]:
    """Wykryte podlania: wzrost gleby o co najmniej `skok` punktów względem najniższego
    odczytu z ostatnich `okno_ms`. Znacznik to pierwszy odczyt, który przekroczył próg;
    `przed` to ten najniższy odczyt, `szczyt` — mediana odczytów 2–6 godz. później (None,
    dopóki tyle czasu nie minęło albo brak odczytów)."""
    wydarzenia: list[dict] = []
    for i, (t, v) in enumerate(gleba):
        poprzednie = [w for (tp, w) in gleba[:i] if t - tp <= okno_ms]
        if not poprzednie:
            continue
        najnizej = min(poprzednie)
        if v - najnizej >= skok and (not wydarzenia or t - wydarzenia[-1]["ms"] > okno_ms):
            wydarzenia.append({"ms": t, "przed": najnizej})
    for w in wydarzenia:
        po = [v for (t, v) in gleba if w["ms"] + SZCZYT_OD_MS <= t <= w["ms"] + SZCZYT_DO_MS]
        w["szczyt"] = round(statistics.median(po), 1) if po else None
    return [{"ts": iso(w["ms"]), "przed": round(w["przed"], 1), "szczyt": w["szczyt"]}
            for w in wydarzenia]


def nauka(podl: list[dict], sucho: float | None) -> dict:
    """Szczyt i punkt podlewania z trzech ostatnich podlań (mediany)."""
    szczyty = [p["szczyt"] for p in podl if p.get("szczyt") is not None][-3:]
    przed = [p["przed"] for p in podl][-3:]
    szczyt = statistics.median(szczyty) if szczyty else None
    punkt = statistics.median(przed) if len(przed) >= 3 else None
    if szczyt is not None and sucho is not None and szczyt - sucho < SKOK_PODLANIA:
        szczyt = None          # „szczyt" ledwie nad suchym — to nie skala, tylko szum
    return {"szczyt": szczyt, "punkt_podlewania": punkt, "podlan": len(podl)}


def prog_rosliny(gatunek: str, miesiac: int, sucho: float | None, szczyt: float | None,
                 punkt: float | None) -> float:
    """Próg R: nauczony z podlań właściciela (przycięty do granic gatunku) albo z literatury."""
    g = GATUNKI[gatunek]
    if punkt is not None and szczyt is not None and sucho is not None and szczyt > sucho:
        nauczony = (punkt - sucho) / (szczyt - sucho)
        return round(min(max(nauczony, g["granice"][0]), g["granice"][1]), 2)
    return g["prog_zima"] if miesiac in ZIMA else g["prog"]


def stan_rosliny(konf: dict, wiersze: list[dict], teraz_ms: int, strefa: ZoneInfo) -> dict:
    """Wszystko, co zakładka pokazuje o jednej roślinie, i werdykt."""
    czujnik, kody = konf["czujnik"], konf["kody"]
    od_nauki = _ms(konf["od"]) if konf.get("od") else None
    serie = {r: punkty(wiersze, czujnik, kod) for r, kod in kody.items() if r in LICZBOWE}

    ostatnie = {}
    for rodzaj, kod in kody.items():
        moje = [w for w in wiersze if w.get("device_id") == czujnik and w.get("code") == kod]
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
    if od_nauki:
        gleba_nauki = [(t, v) for (t, v) in gleba if t >= od_nauki]
    else:
        gleba_nauki = []          # bez daty wbicia sondy nie uczymy się niczego
    podl = podlania(gleba_nauki)
    sucho = konf.get("sucho")
    wynik_nauki = nauka(podl, sucho)
    miesiac = datetime.fromtimestamp(teraz_ms / 1000, strefa).month
    prog = prog_rosliny(konf["gatunek"], miesiac, sucho, wynik_nauki["szczyt"],
                        wynik_nauki["punkt_podlewania"])

    teraz_gleba = ostatnie.get("gleba", {}).get("v")
    szczyt = wynik_nauki["szczyt"]
    r = None
    if teraz_gleba is not None and szczyt is not None and sucho is not None:
        r = round((teraz_gleba - sucho) / (szczyt - sucho), 2)

    uwagi = []
    najnowszy = max((_ms(o["ts"]) or 0 for o in ostatnie.values()), default=0)
    if not ostatnie:
        werdykt = "czujnik"
        uwagi.append("Brak jakichkolwiek odczytów.")
    elif teraz_ms - najnowszy > CISZA_MS:
        werdykt = "czujnik"
        uwagi.append(f"Czujnik milczy od {(teraz_ms - najnowszy) / GODZ:.0f} godz.")
    elif not od_nauki:
        werdykt = "nauka"
        uwagi.append("Czekam na wbicie sondy do ziemi (data „od\" w rosliny.json).")
    elif szczyt is None:
        werdykt = "nauka"
        uwagi.append("Czekam na pierwsze podlanie — z niego bierze się skala.")
    else:
        pilne = GATUNKI[konf["gatunek"]]["pilne"]
        if pilne is not None and r is not None and r <= pilne:
            werdykt = "pilne"
        elif r is not None and r <= prog:
            werdykt = "podlej"
        else:
            werdykt = "ok"
    if str(ostatnie.get("bateria", {}).get("v", "")).lower() == "low":
        uwagi.append("Bateria na wyczerpaniu.")

    swiatlo = luksogodziny(serie.get("swiatlo", []), strefa, od_ms, teraz_ms)
    return {
        "czujnik": czujnik, "nazwa": konf["nazwa"], "gatunek": konf["gatunek"],
        "pokoj": konf.get("pokoj"), "sucho": sucho, "od": konf.get("od"),
        "ostatnie": ostatnie, "szereg": szereg, "swiatlo_dobowe": swiatlo,
        "swiatlo_potrzeba_lxh": GATUNKI[konf["gatunek"]]["swiatlo_lxh"],
        "podlania": podl, "szczyt": szczyt, "punkt_podlewania": wynik_nauki["punkt_podlewania"],
        "R": r, "prog": prog, "werdykt": werdykt, "uwagi": uwagi,
    }
