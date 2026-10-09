#!/usr/bin/env python3
"""
Nadawca powiadomień Web Push — osobny krok w zbieraj.yml, po udanym zapisz.sh.

Wywołanie (tylko ten krok dostaje sekrety powiadomień):

    git show origin/main:data/rosliny/powiadomienia.json > "$RUNNER_TEMP/powiadomienia.json" || true
    pip install -r requirements-powiadomienia.txt
    python wyslij.py --plik "$RUNNER_TEMP/powiadomienia.json" \\
                     --przebieg "$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"

a z powiadomienie-testowe.yml (ręcznie, „czy telefon w ogóle coś dostaje"):

    python wyslij.py --test --przebieg "$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"

Wysyła wyłącznie wpisy z `historia`, które zapisał TEN przebieg (`przebieg` ==
--przebieg) i które nie są na sucho (`na_sucho` dokładnie false). Plik pochodzi
z opublikowanego commita, więc wpis albo jest w historii main, albo nie ma go wcale:
dwa przebiegi naraz, przegrany wyścig ani „Re-run" nie mają czego wysłać drugi raz.
Zasada: co najwyżej raz — nieudanej wysyłki następny przebieg nie ponawia (ROSLINY.md,
„Etap 4"). Brak pliku albo pusty plik to „nic do wysłania".

Środowisko:
- VAPID_KLUCZ_PRYWATNY — base64url surowego klucza P-256 (32 B), czyli pole `d` z JWK,
  które eksportuje strona;
- PUSH_ANDROID, PUSH_IPHONE — JSON z PushSubscription.toJSON(); pusty albo brak →
  ten telefon pomijany;
- GH_TOKEN (+ program gh) — do zgłoszeń z etykietą „powiadomienia"; bez nich błąd
  zostaje tylko w logu.

Kody wyjścia:
- 0 — wysłane, nic do wysłania, „brak subskrypcji" (brak klucza albo obu subskrypcji)
  oraz błędy pojedynczej subskrypcji (404/410, 429/5xx po trzech próbach, sieć, inne
  kody): zgłoszenie wystarczy, kolektor nie ma świecić na czerwono co godzinę;
- 1 — błąd konfiguracji: zły JSON sekretu, zły format klucza, pusta albo inna niż
  wyliczona stała VAPID_PUBLICZNY w rosliny.html („klucz w sekrecie nie pasuje do
  strony"), 403 od serwera push (ten sam klucz nie pasuje do subskrypcji), brak
  biblioteki, nieczytelny plik, nieoczekiwany wyjątek;
- 2 — złe argumenty (argparse);
- w trybie --test każdy błąd i brak subskrypcji to 1, bo jedynym sensem tego trybu
  jest sprawdzenie, czy powiadomienie doszło.

Logi Actions są publiczne. Adres subskrypcji (endpoint) to jedyna rzecz, która
pozwala wysyłać na telefon, a biblioteki wkładają go w treść wyjątków i ostrzeżeń.
Dlatego: na starcie `::add-mask::` dla adresu, jego ścieżki i kluczy subskrypcji;
telefony występują w logu i zgłoszeniu wyłącznie jako „Android"/„iPhone"; z wyjątków
wypisujemy tylko nazwę typu; wszystko, co biblioteka wypisze w trakcie wysyłki
(print, logging jak w urllib3, warnings — każde trafia na sys.stdout/sys.stderr),
idzie w próżnię.

Zmierzone 9.10.2026 na prawdziwej bibliotece (pywebpush 2.5.0, py-vapid 1.9.4,
http-ece 1.2.1, cryptography 50.0.2; sieć podmieniona atrapą requests.post — powtarza
to klasa TestPrawdziwaBiblioteka w tests/test_wyslij.py, gdy pywebpush jest
zainstalowany):
- webpush() dopisuje `aud` i `exp` do podanego słownika vapid_claims W MIEJSCU. Ten sam
  słownik użyty drugi raz dla subskrypcji Apple wysłał token z
  aud=https://fcm.googleapis.com — drugi telefon dostałby cudzy `aud`. Stąd świeży
  słownik przy każdym wywołaniu;
- bez `ttl` nagłówek TTL to „0" (według ROSLINY.md Apple takie odrzuca), a bez
  `timeout` requests.post dostaje timeout=None, czyli czekałby bez końca. Oba podajemy
  jawnie;
- `sub` ze ścieżką („https://bronek31.github.io/Smart-Home/"), a nawet z samym końcowym
  ukośnikiem, py_vapid odrzuca już lokalnie (VapidException „Missing 'sub'");
- Urgency i Topic dochodzą do requests.post (małymi literami — w HTTP bez znaczenia),
  TTL jako „43200", treść jako aes128gcm;
- pola `d` z JWK par wygenerowanych WebCrypto (Chromium 141 i Node 22, ECDSA P-256)
  Vapid.from_string przyjmuje jako klucz surowy (32 B), a jego klucz publiczny (X9.62,
  nieskompresowany) jest bajt w bajt eksportem 'raw' tej samej pary: 65 B, pierwszy
  bajt 0x04, base64url bez dopełnienia. To samo daje publiczny_z_prywatnego() niżej;
- szyfrowanie dokłada 103 B: treść 3993 B daje ciało 4096 B, czyli tyle, ile serwer push
  musi przyjąć (RFC 8030); 3994 B daje już 4097 B.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

STRONA = Path(__file__).resolve().parent / "rosliny.html"
# Klucz publiczny VAPID leży w jednym miejscu — w rosliny.html. Strona z niego zakłada
# subskrypcje, nadawca tylko sprawdza, czy sekret do niego pasuje. Zapis musi zostać
# dokładnie taki (pojedyncze apostrofy, średnik), bo czytamy go tym wzorcem.
WZOR_STALEJ = re.compile(r"const VAPID_PUBLICZNY='([^']*)';")

# `sub` to adres strony bez ścieżki: py_vapid przyjmuje tylko mailto: albo https://host
# (zmierzone, patrz wyżej), a mailto z adresem właściciela trafiłby do każdego serwera push.
SUB = "https://bronek31.github.io"
# 12 godz.: telefon wyłączony na noc dostanie rano to, co ma jeszcze sens. Domyślne 0
# biblioteki znaczy „teraz albo wcale" i Apple je odrzuca.
TTL_S = 12 * 3600
LIMIT_SIECI_S = 30
# 429, 5xx i zerwane połączenie: dwie ponowne próby w tym samym kroku. Duplikat jest
# nieszkodliwy — ten sam Topic zastępuje na serwerze push czekające powiadomienie,
# a ten sam `tag` w sw.js podmienia pokazane.
PRZERWY_S = (2, 10)
# Największa treść, której ciało po zaszyfrowaniu mieści się w 4096 B (zmierzone).
MAKS_TRESCI_B = 3993
# Reguły dokładają na przebieg najwyżej trzy wpisy (zwykły, czujnik, podsumowanie).
# Więcej to błąd w regułach, a nie powód, żeby zasypać telefony.
MAKS_WPISOW = 3
ETYKIETA = "powiadomienia"
TELEFONY = (("Android", "PUSH_ANDROID"), ("iPhone", "PUSH_IPHONE"))
# RFC 8030: Topic to najwyżej 32 znaki z alfabetu base64url, inaczej serwer odrzuci całość.
WZOR_TOPIC = re.compile(r"[A-Za-z0-9_-]{1,32}")

TESTOWE = {"tytul": "Powiadomienia działają",
           "tresc": "Powiadomienie testowe z GitHub Actions. Skoro je widać, na ten telefon "
                    "dojdą też „Podlej” i alarmy czujników.",
           "tag": "test", "url": "rosliny.html"}

# Krzywa P-256 (SEC 2, secp256r1): pole, współczynnik a, rząd grupy i punkt bazowy.
# Klucz publiczny liczymy sami, bo testy jednostkowe w CI mają tylko `requests`, a to
# porównanie z kluczem ze strony jest dokładnie tym, czego pomyłka po cichu wyłączyłaby
# powiadomienia — ma być sprawdzone na prawdziwej parze z WebCrypto także tam. Że wynik
# to bajt w bajt klucz, którym py_vapid podpisuje, pilnuje TestPrawdziwaBiblioteka.
# Mnożenie nie jest w stałym czasie: liczy się raz na przebieg, na maszynie, której czasu
# nikt z zewnątrz nie mierzy.
_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_A = _P - 3
_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
      0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


class BladKonfiguracji(Exception):
    """Komunikat w środku jest bezpieczny do logu: nigdy nie zawiera wartości sekretu."""


@dataclass
class Telefon:
    nazwa: str          # „Android"/„iPhone" — jedyne, czym telefon występuje w logu
    sekret: str         # nazwa sekretu, do podpowiedzi w zgłoszeniu
    subskrypcja: dict


@dataclass
class Blad:
    kto: str            # „Android", „iPhone" albo „Konfiguracja"
    opis: str           # do logu i zgłoszenia — bez adresu i bez treści wyjątku
    rada: str = ""
    konfiguracja: bool = False


def z_base64url(tekst: str) -> bytes:
    tekst = tekst.strip().rstrip("=")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", tekst) or len(tekst) % 4 == 1:
        raise ValueError("to nie jest base64url")
    return base64.urlsafe_b64decode(tekst + "=" * (-len(tekst) % 4))


def do_base64url(bajty: bytes) -> str:
    return base64.urlsafe_b64encode(bajty).rstrip(b"=").decode("ascii")


def _dodaj(p, q):
    if p is None:
        return q
    if q is None:
        return p
    (x1, y1), (x2, y2) = p, q
    if x1 == x2:
        if (y1 + y2) % _P == 0:
            return None
        nachylenie = (3 * x1 * x1 + _A) * pow(2 * y1, -1, _P) % _P
    else:
        nachylenie = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
    x3 = (nachylenie * nachylenie - x1 - x2) % _P
    return x3, (nachylenie * (x1 - x3) - y1) % _P


def publiczny_z_prywatnego(prywatny: str) -> str:
    """base64url klucza publicznego w formacie eksportu 'raw' z WebCrypto
    (0x04 || X || Y, 65 B) dla klucza prywatnego podanego jak JWK `d`."""
    try:
        surowy = z_base64url(prywatny)
    except ValueError:
        surowy = b""
    d = int.from_bytes(surowy, "big")
    if len(surowy) != 32 or not 0 < d < _N:
        raise BladKonfiguracji(
            "sekret VAPID_KLUCZ_PRYWATNY ma zły format — oczekuję 43 znaków base64url "
            "(pole d klucza z przycisku „Utwórz klucze”), bez cudzysłowów")
    wynik, punkt = None, _G
    while d:
        if d & 1:
            wynik = _dodaj(wynik, punkt)
        punkt = _dodaj(punkt, punkt)
        d >>= 1
    x, y = wynik
    return do_base64url(b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big"))


def klucz_ze_strony(strona: Path) -> str:
    """Stała VAPID_PUBLICZNY z rosliny.html; '' = jeszcze nieskonfigurowana."""
    try:
        html = Path(strona).read_text(encoding="utf-8")
    except OSError:
        raise BladKonfiguracji(f"nie da się odczytać {Path(strona).name}") from None
    znalezione = WZOR_STALEJ.findall(html)
    if len(znalezione) != 1:
        raise BladKonfiguracji(
            f"w {Path(strona).name} powinna być dokładnie jedna linia "
            f"const VAPID_PUBLICZNY='…'; — jest {len(znalezione)}")
    klucz = znalezione[0].strip()
    if klucz:
        try:
            surowy = z_base64url(klucz)
        except ValueError:
            surowy = b""
        if len(surowy) != 65 or surowy[0] != 4:
            raise BladKonfiguracji("stała VAPID_PUBLICZNY w rosliny.html to nie jest klucz "
                                   "publiczny P-256 (65 B base64url, eksport 'raw')")
    return klucz


def sprawdz_klucz(klucz: str, strona: Path) -> None:
    """Rzuca BladKonfiguracji, gdy sekret nie pasuje do strony albo strona nie ma klucza."""
    wyliczony = publiczny_z_prywatnego(klucz)
    na_stronie = klucz_ze_strony(strona)
    if not na_stronie:
        raise BladKonfiguracji(
            "stała VAPID_PUBLICZNY w rosliny.html jest pusta, a sekret VAPID_KLUCZ_PRYWATNY "
            "już jest — przekaż Claude'owi klucz publiczny z przycisku „Utwórz klucze”")
    if z_base64url(na_stronie) != z_base64url(wyliczony):
        raise BladKonfiguracji(
            "klucz w sekrecie nie pasuje do strony — VAPID_KLUCZ_PRYWATNY i stała "
            "VAPID_PUBLICZNY w rosliny.html pochodzą z różnych par; wygeneruj parę jeszcze "
            "raz i podmień oba")


def _maskuj(wartosc) -> None:
    # Dane polecenia Actions trzeba zakodować jak @actions/core (escapeData), inaczej
    # „%0A” w wartości runner zamieniłby na nową linię i zamaskował coś innego.
    if isinstance(wartosc, str) and len(wartosc) >= 8:
        bezpieczna = wartosc.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::add-mask::{bezpieczna}", flush=True)


def wczytaj_telefony(env) -> tuple[list[Telefon], list[Blad]]:
    """Subskrypcje z sekretów. Najpierw maski — zanim cokolwiek innego trafi do logu."""
    telefony, bledy = [], []
    for nazwa, sekret in TELEFONY:
        tekst = (env.get(sekret) or "").strip()
        if not tekst:
            continue
        try:
            sub = json.loads(tekst)
        except ValueError:
            sub = None
        if isinstance(sub, dict):
            # adres w całości, sama ścieżka (tak go cytuje urllib3: „…with url: /fcm/send/…”)
            # i klucze — maskujemy wszystko, co da się wyłuskać, nawet z wadliwego sekretu
            endpoint = sub.get("endpoint")
            _maskuj(endpoint)
            try:
                _maskuj(urlsplit(endpoint).path if isinstance(endpoint, str) else None)
            except ValueError:
                pass        # adres, którego nie da się rozebrać, i tak odpadnie niżej
            klucze = sub.get("keys") if isinstance(sub.get("keys"), dict) else {}
            _maskuj(klucze.get("auth"))
            _maskuj(klucze.get("p256dh"))
        try:
            telefony.append(Telefon(nazwa, sekret, _subskrypcja(sub)))
        except ValueError as blad:
            bledy.append(Blad(nazwa, f"sekret {sekret} {blad}",
                              f"Skopiuj JSON subskrypcji ze strony jeszcze raz i podmień nim "
                              f"sekret `{sekret}`.", konfiguracja=True))
    return telefony, bledy


def _subskrypcja(sub) -> dict:
    """Sprawdza kształt PushSubscription.toJSON(); komunikat błędu nie cytuje treści."""
    if not isinstance(sub, dict):
        raise ValueError("to nie jest JSON subskrypcji")
    endpoint = sub.get("endpoint")
    klucze = sub.get("keys")
    if not isinstance(endpoint, str) or not endpoint.startswith("https://"):
        raise ValueError("nie ma poprawnego pola endpoint")
    if not isinstance(klucze, dict):
        raise ValueError("nie ma pola keys")
    try:
        p256dh = z_base64url(str(klucze.get("p256dh") or ""))
        auth = z_base64url(str(klucze.get("auth") or ""))
    except ValueError:
        raise ValueError("ma uszkodzone klucze p256dh/auth") from None
    if len(p256dh) != 65 or p256dh[0] != 4 or len(auth) != 16:
        raise ValueError("ma klucze p256dh/auth złej długości")
    return {"endpoint": endpoint, "keys": {"p256dh": klucze["p256dh"], "auth": klucze["auth"]}}


def wpisy_przebiegu(plik: Path, przebieg: str) -> list[dict]:
    """Wpisy do wysłania w tym przebiegu: z jego numerem i wysłane naprawdę (nie na sucho)."""
    plik = Path(plik)
    if not plik.exists() or plik.stat().st_size == 0:
        return []
    try:
        dane = json.loads(plik.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BladKonfiguracji(f"nie da się odczytać {plik.name} jako JSON") from None
    historia = dane.get("historia") if isinstance(dane, dict) else None
    if not isinstance(historia, list):
        raise BladKonfiguracji(f"{plik.name} nie ma listy „historia”")
    # `is False`, nie „nie prawda": wpis bez pola na_sucho to wpis, o którym nie wiemy,
    # czy miał pójść — a zasada brzmi „co najwyżej raz", nie „co najmniej raz".
    return [w for w in historia if isinstance(w, dict)
            and w.get("przebieg") == przebieg and w.get("na_sucho") is False]


def tresc_push(wpis: dict) -> str:
    """JSON dla sw.js: {title, body, tag, url, id}; za długie `body` przycięte z „…”."""
    tresc = {"title": str(wpis.get("tytul") or "Rośliny"),
             "body": str(wpis.get("tresc") or ""),
             "tag": str(wpis.get("tag") or "rosliny"),
             "url": str(wpis.get("url") or "rosliny.html"),
             "id": str(wpis.get("id") or "")}
    dane = json.dumps(tresc, ensure_ascii=False)
    # Każdy usunięty znak to co najmniej bajt, więc pętla kończy się po jednym, dwóch
    # obrotach. Za długa treść to 413 od serwera i powiadomienie przepada w całości.
    while len(dane.encode("utf-8")) > MAKS_TRESCI_B and tresc["body"]:
        nadmiar = len(dane.encode("utf-8")) - MAKS_TRESCI_B
        krotsze = tresc["body"][:max(0, len(tresc["body"]) - nadmiar - 3)].rstrip()
        tresc["body"] = krotsze + "…" if krotsze else ""
        dane = json.dumps(tresc, ensure_ascii=False)
    return dane


def wyslij_jedno(biblioteka, telefon: Telefon, dane: str, tag: str, vapid, spij) -> int | Blad:
    """Jedno powiadomienie na jeden telefon; kod HTTP przy sukcesie, Blad przy porażce."""
    import requests

    naglowki = {"Urgency": "normal"}
    if WZOR_TOPIC.fullmatch(tag):
        naglowki["Topic"] = tag
    for proba in range(len(PRZERWY_S) + 1):
        # każda gałąź niżej albo kończy funkcję, albo ustawia blad_proby i idzie na ponowienie
        try:
            # Wyjście biblioteki w trakcie wysyłki idzie w próżnię: gdyby cokolwiek
            # w środku coś wypisało, wypisałoby to z adresem.
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                odpowiedz = biblioteka.webpush(
                    subscription_info=telefon.subskrypcja,
                    data=dane,
                    vapid_private_key=vapid,
                    # świeży słownik przy KAŻDYM wywołaniu — biblioteka dopisuje do niego
                    # aud pierwszego telefonu i drugi poszedłby z cudzym (zmierzone)
                    vapid_claims={"sub": SUB},
                    ttl=TTL_S,
                    timeout=LIMIT_SIECI_S,
                    headers=dict(naglowki),
                )
            return getattr(odpowiedz, "status_code", 201)
        except biblioteka.WebPushException as blad:
            kod = getattr(getattr(blad, "response", None), "status_code", None)
            if kod in (404, 410):
                return Blad(telefon.nazwa, f"subskrypcja wygasła ({kod})",
                            f"Na tym telefonie: zakładka „Rośliny” → „Włącz powiadomienia na tym "
                            f"telefonie”, skopiuj pokazany JSON i podmień nim sekret `{telefon.sekret}`.")
            if kod == 403:
                return Blad(telefon.nazwa, "serwer push odrzucił podpis VAPID (403)",
                            f"Subskrypcja powstała przy innym kluczu publicznym niż ten, który "
                            f"pasuje do VAPID_KLUCZ_PRYWATNY. Włącz powiadomienia na telefonie "
                            f"jeszcze raz i podmień sekret `{telefon.sekret}`.", konfiguracja=True)
            if kod is None:
                return Blad(telefon.nazwa, "biblioteka odrzuciła dane subskrypcji",
                            f"Skopiuj JSON subskrypcji ze strony jeszcze raz i podmień sekret "
                            f"`{telefon.sekret}`.", konfiguracja=True)
            if kod != 429 and kod < 500:
                return Blad(telefon.nazwa, f"serwer push odrzucił powiadomienie ({kod})",
                            "Kod spoza znanych — trzeba zajrzeć do nadawcy (wyslij.py).")
            blad_proby = f"serwer push odmawia ({kod})"
        except (requests.ConnectionError, requests.Timeout) as blad:
            blad_proby = f"błąd sieci ({type(blad).__name__})"
        except Exception as blad:  # noqa: BLE001 — treść wyjątku może zawierać adres
            return Blad(telefon.nazwa, f"nieoczekiwany błąd ({type(blad).__name__})",
                        "Trzeba zajrzeć do nadawcy (wyslij.py).", konfiguracja=True)
        if proba < len(PRZERWY_S):
            print(f"{telefon.nazwa}: {blad_proby}, ponawiam za {PRZERWY_S[proba]} s", flush=True)
            spij(PRZERWY_S[proba])
    return Blad(telefon.nazwa, f"{blad_proby} także po {len(PRZERWY_S) + 1} próbach",
                "Serwer push był przeciążony albo nieosiągalny. Nieudanej wysyłki nikt nie "
                "ponawia; reguły z ponowieniem nadrobią „Podlej” same.")


def uruchom_gh(argumenty: list[str]) -> tuple[int, str]:
    wynik = subprocess.run(["gh", *argumenty], capture_output=True, text=True, timeout=60)
    return wynik.returncode, wynik.stdout


def _adres_przebiegu(env) -> str:
    czesci = [env.get(k) for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID")]
    return f"{czesci[0]}/{czesci[1]}/actions/runs/{czesci[2]}" if all(czesci) else ""


def tresc_zgloszenia(bledy: list[Blad], przebieg: str, env, wpisy: list[dict]) -> str:
    linie = [f"Wysyłka powiadomień w przebiegu `{przebieg}` nie poszła gładko:", ""]
    for b in bledy:
        linie.append(f"- **{b.kto}** — {b.opis}." + (f" {b.rada}" if b.rada else ""))
    if wpisy:
        tytuly = ", ".join(f"„{w.get('tytul') or '?'}”" for w in wpisy)
        linie += ["", f"Powiadomienia z tego przebiegu: {tytuly}."]
    adres = _adres_przebiegu(env)
    if adres:
        linie += ["", f"Log przebiegu: {adres}"]
    linie += ["", "Adresów subskrypcji tu nie ma i nie będzie — zgłoszenia i logi Actions są "
                  "publiczne. Treść odświeża się przy kolejnych błędach, a zgłoszenie zamknie "
                  "się samo po pierwszej wysyłce, która dojdzie do wszystkich telefonów."]
    return "\n".join(linie) + "\n"


def _otwarte_zgloszenie(gh) -> str:
    kod, wyjscie = gh(["issue", "list", "--label", ETYKIETA, "--state", "open", "--limit", "1",
                       "--json", "number", "--jq", ".[0].number // empty"])
    numer = (wyjscie or "").strip() if kod == 0 else ""
    return numer if numer.isdigit() else ""


def zglos(tresc: str, env, gh) -> None:
    """Zakłada albo odświeża zgłoszenie. Odświeża podmianą treści, nie komentarzem: błąd
    konfiguracji wraca co godzinę, a cogodzinny mail o tym samym przestaje się czytać."""
    if gh is None or not env.get("GH_TOKEN"):
        print("Zgłoszenie pominięte: brak programu gh albo GH_TOKEN — błąd zostaje tylko w logu.",
              flush=True)
        return
    try:
        gh(["label", "create", ETYKIETA, "--color", "FBCA04",
            "--description", "Powiadomienia na telefon nie dochodzą"])
        numer = _otwarte_zgloszenie(gh)
        if numer:
            kod, _ = gh(["issue", "edit", numer, "--body", tresc])
            opis = f"odświeżono zgłoszenie #{numer}"
        else:
            kod, _ = gh(["issue", "create", "--title", "Powiadomienia nie dochodzą",
                         "--label", ETYKIETA, "--body", tresc])
            opis = "założono zgłoszenie"
        print(f"Zgłoszenie: {opis}." if kod == 0 else f"Zgłoszenie: gh skończył z kodem {kod}.",
              flush=True)
    except Exception as blad:  # noqa: BLE001 — zgłoszenie to dodatek, nie powód do wywrotki
        print(f"Zgłoszenie: nie wyszło ({type(blad).__name__}).", flush=True)


def zamknij_zgloszenie(env, gh) -> None:
    if gh is None or not env.get("GH_TOKEN"):
        return
    try:
        numer = _otwarte_zgloszenie(gh)
        if numer:
            gh(["issue", "close", numer, "--comment",
                "Powiadomienia znowu dochodzą do wszystkich telefonów."])
            print(f"Zgłoszenie #{numer} zamknięte — wysyłka przeszła.", flush=True)
    except Exception as blad:  # noqa: BLE001
        print(f"Zgłoszenie: nie udało się zamknąć ({type(blad).__name__}).", flush=True)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Wysyła powiadomienia Web Push zapisane przez ten przebieg.")
    p.add_argument("--plik", type=Path, help="powiadomienia.json z opublikowanego commita")
    p.add_argument("--przebieg", default="", help="$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT")
    p.add_argument("--test", action="store_true",
                   help="jedno powiadomienie testowe do wszystkich telefonów, bez pliku")
    p.add_argument("--strona", type=Path, default=STRONA, help=argparse.SUPPRESS)
    return p


def main(argv=None, *, env=None, spij=time.sleep, gh=None, strona=None) -> int:
    """`env`, `spij`, `gh` i `strona` podstawiają testy; `gh` to funkcja
    (lista argumentów) → (kod wyjścia, stdout)."""
    parser = _parser()
    args = parser.parse_args(argv)
    if not args.test and (args.plik is None or not args.przebieg):
        parser.error("bez --test potrzebne są --plik i --przebieg")
    env = os.environ if env is None else env
    if gh is None and shutil.which("gh"):
        gh = uruchom_gh
    try:
        return _main(args, env, spij, gh, strona or args.strona)
    except Exception as blad:  # noqa: BLE001
        # Bez treści wyjątku, ale z miejscem: nazwa pliku, linia i funkcja nie zdradzą adresu.
        print(f"::error::Nadawca przerwał pracę: {type(blad).__name__} (treść błędu pomijam — "
              f"mogłaby zawierać adres subskrypcji)", flush=True)
        for ramka in traceback.extract_tb(blad.__traceback__):
            print(f"  {Path(ramka.filename).name}:{ramka.lineno} w {ramka.name}", flush=True)
        return 1


def _main(args, env, spij, gh, strona: Path) -> int:
    telefony, bledy = wczytaj_telefony(env)
    klucz = (env.get("VAPID_KLUCZ_PRYWATNY") or "").strip()
    if not klucz or (not telefony and not bledy):
        powod = ("brak sekretu VAPID_KLUCZ_PRYWATNY" if not klucz
                 else "sekrety PUSH_ANDROID i PUSH_IPHONE puste")
        print(f"{'::error::' if args.test else ''}brak subskrypcji — nic nie wysyłam ({powod}).",
              flush=True)
        for b in bledy:
            print(f"Uwaga: {b.kto}: {b.opis}.", flush=True)
        if klucz:
            # Etap przejściowy: klucz już w sekrecie, telefony jeszcze nie. Nie na czerwono,
            # ale powiedzmy, czy strona jest gotowa na subskrypcje.
            try:
                sprawdz_klucz(klucz, strona)
            except BladKonfiguracji as blad:
                print(f"Uwaga: {blad}.", flush=True)
        return 1 if args.test else 0

    wpisy: list[dict] = []
    try:
        sprawdz_klucz(klucz, strona)
        if args.test:
            wpisy = [dict(TESTOWE, id=f"test-{args.przebieg}" if args.przebieg else "test")]
        else:
            wpisy = wpisy_przebiegu(args.plik, args.przebieg)
    except BladKonfiguracji as blad:
        bledy.append(Blad("Konfiguracja", str(blad), konfiguracja=True))

    if len(wpisy) > MAKS_WPISOW:
        bledy.append(Blad("Reguły", f"przebieg zapisał {len(wpisy)} wpisy do wysłania, "
                                    f"wysyłam pierwsze {MAKS_WPISOW}",
                          "To błąd w zaplanuj_powiadomienia() (rosliny.py)."))
        wpisy = wpisy[:MAKS_WPISOW]
    wyslane = 0
    if wpisy and telefony and not any(b.kto == "Konfiguracja" for b in bledy):
        try:
            import pywebpush as biblioteka
        except ImportError:
            biblioteka = None
            bledy.append(Blad("Konfiguracja", "brak biblioteki pywebpush",
                              "Krok wysyłki musi zrobić pip install -r requirements-powiadomienia.txt.",
                              konfiguracja=True))
        if biblioteka is not None:
            # Instancja, a nie tekst klucza: przy tekście webpush() najpierw sprawdza
            # os.path.isfile(klucz), dopiero potem woła Vapid.from_string.
            vapid = biblioteka.Vapid.from_string(klucz)
            for wpis in wpisy:
                dane = tresc_push(wpis)
                tag = json.loads(dane)["tag"]
                if not WZOR_TOPIC.fullmatch(tag):
                    print(f"Tag {tag!r} nie nadaje się na nagłówek Topic — wysyłam bez niego.",
                          flush=True)
                for telefon in telefony:
                    wynik = wyslij_jedno(biblioteka, telefon, dane, tag, vapid, spij)
                    if isinstance(wynik, Blad):
                        bledy.append(wynik)
                    else:
                        wyslane += 1
                        print(f"{telefon.nazwa}: wysłano „{json.loads(dane)['title']}” ({wynik}).",
                              flush=True)
    elif not wpisy and not any(b.kto == "Konfiguracja" for b in bledy):
        print(f"Przebieg {args.przebieg}: nic do wysłania.", flush=True)

    for b in bledy:
        poziom = "error" if b.konfiguracja or args.test else "warning"
        print(f"::{poziom}::{b.kto}: {b.opis}." + (f" {b.rada}" if b.rada else ""), flush=True)
    if bledy:
        zglos(tresc_zgloszenia(bledy, args.przebieg or "?", env, wpisy), env, gh)
    elif wyslane:
        zamknij_zgloszenie(env, gh)
    if args.test:
        return 1 if bledy or not wyslane else 0
    return 1 if any(b.konfiguracja for b in bledy) else 0


if __name__ == "__main__":
    sys.exit(main())
