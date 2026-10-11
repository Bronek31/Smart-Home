"""
Ustawienia powiadomień każdego telefonu — obliczenia bez sieci i bez plików.

Każdy telefon ma własną zmienną repozytorium (POWIADOMIENIA_ANDROID, POWIADOMIENIA_IPHONE)
z JSON-em, który zapisuje aplikacja (zakładka „Powiadomienia") kluczem z jednym
uprawnieniem: Variables, odczyt i zapis. Kolektor dostaje obie zmienne przez `env:`
kroku „Pobierz…" i tu zamienia je na słowniki, z których planery (rosliny.py, dom.py)
biorą trzy rzeczy:

- które reguły ten telefon chce dostawać,
- kiedy ma ciszę nocną,
- komu wysłać wpis teraz, a komu odłożyć go na koniec jego ciszy.

Decyzja zapada w kolektorze, przed commitem, razem z wpisem — nadawca (wyslij.py) jest
bezstanowy i tylko wykonuje pole `telefony` wpisu. Inaczej „dostaniesz rano" wymagałoby
drugiego commita z nadawcy, a z nim wyścigu i dublowania („co najwyżej raz",
ROSLINY.md, „Etap 4").

Na iPhonie każdy push musi pokazać powiadomienie, bo inaczej Safari cofa zgodę — dlatego
filtr działa u nadawcy, a nie w service workerze.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

GODZ = 3600 * 1000

# Kolejność ma znaczenie tylko dla czytelności wpisów („telefony": ["android", "iphone"]).
TELEFONY = ("android", "iphone")
ZMIENNE = {"android": "POWIADOMIENIA_ANDROID", "iphone": "POWIADOMIENIA_IPHONE"}

# Te same wartości co DOMYSLNE w index.html (zakładka „Powiadomienia"). Brak zmiennej,
# zły JSON albo zła wartość pojedynczego pola dają te wartości — nigdy wyjątek ani „nic nie
# wysyłaj". Podsumowanie tygodnia jest domyślnie wyłączone: tak wygląda zatwierdzony ekran.
DOMYSLNE = {"przewietrz": True, "okno": True, "czujniki": True, "podlej": True, "przestaw": True,
            "czujnik": True, "podsumowanie": False, "cisza": True, "od": 21, "do": 8}
KLUCZE_REGUL = ("przewietrz", "okno", "czujniki", "podlej", "przestaw", "czujnik", "podsumowanie")

# „Przewietrz przed snem" wychodzi w ostatnich 2 godz. przed ciszą danego telefonu — rano
# byłoby bezużyteczne, więc nigdy się go nie odkłada. Okno zawsze kończy się przed północą:
# karta pokoju daje radę „przewietrz przed snem" tylko przed północą, więc push po północy
# polecałby coś, czego otwarta z niego karta już nie mówi (przegląd, C4). Stąd:
# - cisza od 14:00 do 23:00 — dwie godziny przed nią (cisza 18–8: 16:00–18:00; dawniej
#   cisza od 14 do 18 dostawała zapasowe 19–21, które przy zwykłej nocy, np. 18–8, leżało
#   w jej środku, więc „przed snem" nie przychodziło nigdy — przegląd, B3);
# - cisza od 0:00, 1:00 albo 2:00 — 22:00–24:00;
# - cisza wyłączona albo zaczynająca się 3:00–13:00 (to nie jest „sen" wieczorem) —
#   zapasowe 19:00–21:00.
# Okno nie sprawdza ciszy: przy bardzo długiej ciszy (np. 4–20 albo 18–17) zachodzi na nią,
# a wtedy telefon nic nie dostaje — pilnuje tego planer (dom.py: `not w_ciszy`).
PRZED_SNEM_GODZ = 2
PRZED_SNEM_ZAPAS = (19, 21)
WIECZOR_OD_H = range(14, 24)
PO_POLNOCY_OD_H = (0, 1, 2)
PRZED_POLNOCA = (22, 24)

# Kolejka odłożonych: pozycja starsza niż doba jest już nieaktualna, a limit chroni plik
# przed błędem reguły, który dokładałby pozycję co przebieg.
ODLOZONE_TTL_MS = 24 * GODZ
ODLOZONE_MAKS = 20


def _godzina(wartosc) -> int | None:
    # bool jest w Pythonie podklasą int — `true` z JSON-a to nie godzina 1
    if isinstance(wartosc, bool) or not isinstance(wartosc, int):
        return None
    return wartosc if 0 <= wartosc <= 23 else None


def ustawienia_telefonu(tekst) -> dict:
    """JSON ze zmiennej repozytorium → pełny słownik ustawień.

    Brakujące i złe pola biorą wartość domyślną, nieznane klucze odpadają. Funkcja nie
    rzuca: zmienną może zepsuć ręczna edycja na GitHubie albo przerwany zapis.
    """
    wynik = dict(DOMYSLNE)
    if not isinstance(tekst, str) or not tekst.strip():
        return wynik
    try:
        dane = json.loads(tekst)
    except (ValueError, RecursionError):
        return wynik
    if not isinstance(dane, dict):
        return wynik
    for klucz in KLUCZE_REGUL + ("cisza",):
        if isinstance(dane.get(klucz), bool):
            wynik[klucz] = dane[klucz]
    for klucz in ("od", "do"):
        godz = _godzina(dane.get(klucz))
        if godz is not None:
            wynik[klucz] = godz
    return wynik


def ustawienia_z_env(env) -> dict:
    """{"android": {...}, "iphone": {...}} ze zmiennych środowiska kroku „Pobierz…"."""
    return {t: ustawienia_telefonu(env.get(ZMIENNE[t])) for t in TELEFONY}


def czy_wlasne(env) -> dict:
    """Do logu: "własne", "domyślne" (brak zmiennej) albo "nieczytelne" (zmienna jest, ale
    to nie obiekt JSON — działają wtedy domyślne). Bez treści: repo jest publiczne, a log
    Actions też. Samo „własne” przy zepsutej zmiennej kłamałoby, że ustawienia działają."""
    wynik = {}
    for t in TELEFONY:
        tekst = str(env.get(ZMIENNE[t]) or "").strip()
        if not tekst:
            wynik[t] = "domyślne"
            continue
        try:
            wynik[t] = "własne" if isinstance(json.loads(tekst), dict) else "nieczytelne"
        except (ValueError, RecursionError):
            wynik[t] = "nieczytelne"
    return wynik


def w_ciszy(u: dict, lokalnie: datetime) -> bool:
    """Czy telefon ma teraz ciszę nocną. Godziny są pełne i lokalne (`lokalnie` niesie
    strefę); `od == do` znaczy ciszę bez długości, czyli żadną."""
    if not u.get("cisza"):
        return False
    od, do, h = u["od"], u["do"], lokalnie.hour
    if od == do:
        return False
    return od <= h < do if od < do else (h >= od or h < do)


def noc_wszystkich(ustawienia: dict, lokalnie: datetime) -> bool:
    """Wszystkie telefony mają teraz ciszę — wtedy reguły zachowują się jak dawna
    globalna noc 21–8 (przy domyślnych ustawieniach to dokładnie ona)."""
    return all(w_ciszy(ustawienia[t], lokalnie) for t in TELEFONY)


def koniec_nocy_ms(ustawienia: dict, teraz_ms: int, strefa: ZoneInfo) -> int | None:
    """Koniec ostatniej wspólnej nocy wszystkich telefonów przed `teraz_ms`, nie dalej niż
    dobę wstecz — dawne „8:00 dziś", od którego reguła „podlej" odlicza poranne 2 godz.
    None, gdy w ostatniej dobie wspólnej nocy nie było (albo trwa teraz).

    Liczone po pełnych godzinach lokalnych, wstecz od początku bieżącej godziny, z osobnym
    przeliczeniem strefy dla każdej godziny — 25.10 i 28.03 doba ma 25 i 23 godziny.
    """
    teraz = datetime.fromtimestamp(teraz_ms / 1000, strefa)
    if noc_wszystkich(ustawienia, teraz):
        return None
    poczatek = int(teraz.replace(minute=0, second=0, microsecond=0).timestamp() * 1000)
    t = poczatek
    for _ in range(25):
        godzina_wczesniej = t - GODZ
        if noc_wszystkich(ustawienia, datetime.fromtimestamp(godzina_wczesniej / 1000, strefa)):
            return t
        t = godzina_wczesniej
    return None


def adresaci(klucz: str | None, ustawienia: dict, lokalnie: datetime) -> tuple[list[str], list[str]]:
    """(teraz, odloz): telefony z włączoną regułą `klucz` poza ciszą i w ciszy.

    `klucz` None to wpis bez przełącznika (powitanie „Powiadomienia włączone")."""
    teraz, odloz = [], []
    for t in TELEFONY:
        u = ustawienia[t]
        if klucz is not None and not u.get(klucz):
            continue
        (odloz if w_ciszy(u, lokalnie) else teraz).append(t)
    return teraz, odloz


def przed_snem(u: dict, lokalnie: datetime) -> bool:
    """Czy dla tego telefonu trwa teraz okno „przewietrz przed snem" (pełne godziny lokalne):
    [od − 2 godz., od) dla ciszy od 14:00 do 23:00, 22:00–24:00 dla ciszy od 0:00–2:00,
    a bez wieczornej ciszy 19:00–21:00. Zawsze przed północą. Ciszy samej w sobie nie
    sprawdza — robi to wołający (dom.py), patrz komentarz nad PRZED_SNEM_GODZ."""
    h = lokalnie.hour
    wieczorna = u.get("cisza") and u["od"] != u["do"]
    if wieczorna and u["od"] in WIECZOR_OD_H:
        od, do = u["od"] - PRZED_SNEM_GODZ, u["od"]
    elif wieczorna and u["od"] in PO_POLNOCY_OD_H:
        od, do = PRZED_POLNOCA
    else:
        od, do = PRZED_SNEM_ZAPAS
    return od <= h < do


def data_nocy(lokalnie: datetime) -> str:
    """Data wieczoru, od którego liczy się noc: 0:00–11:59 należy do nocy zaczętej
    poprzedniego dnia. Znacznik „przed snem raz na noc"."""
    return (lokalnie - timedelta(hours=12)).date().isoformat()


def stan_telefonow(poprzednie) -> dict:
    """Część `telefony` pliku powiadomień: {"android": {"odlozone": [...]}, ...}, z każdą
    pozycją sprawdzoną co do typu. Inne pola telefonu (np. `przed_snem` w pliku domu)
    przechodzą bez zmian."""
    wynik = {}
    stare = poprzednie if isinstance(poprzednie, dict) else {}
    for t in TELEFONY:
        s = stare.get(t) if isinstance(stare.get(t), dict) else {}
        s = dict(s)
        s["odlozone"] = [p for p in s.get("odlozone", []) if isinstance(p, dict)
                         and isinstance(p.get("regula"), str) and isinstance(p.get("ts"), str)]
        wynik[t] = s
    return wynik


def przytnij_odlozone(odlozone: list[dict], teraz_ms: int, ms) -> list[dict]:
    """Bez pozycji starszych niż doba i najwyżej ODLOZONE_MAKS najnowszych. `ms` zamienia
    ISO na milisekundy (planery mają własne, tolerancyjne parsowanie)."""
    swieze = [p for p in odlozone if (m := ms(p.get("ts"))) is not None and teraz_ms - m <= ODLOZONE_TTL_MS]
    return swieze[-ODLOZONE_MAKS:]


def odloz(stan: dict, telefony: list[str], pozycja: dict) -> None:
    """Dokłada pozycję do kolejki każdego z `telefony`, bez dubli tej samej reguły
    i obiektu (pierwsza zostaje — niesie czas pierwszego zdarzenia)."""
    for t in telefony:
        kolejka = stan[t]["odlozone"]
        if not any(p.get("regula") == pozycja.get("regula") and p.get("obiekt") == pozycja.get("obiekt")
                   for p in kolejka):
            kolejka.append(dict(pozycja))
