#!/usr/bin/env python3
"""Nadawca powiadomień (wyslij.py) — bez prawdziwej sieci.

Testy jednostkowe w CI mają tylko `requests`, więc pywebpush gra tu atrapa modułu
podstawiona w sys.modules. Atrapa zachowuje się jak pywebpush 2.5.0 w tym, co ma
znaczenie dla pułapek: dopisuje `aud` i `exp` do podanego słownika w miejscu i rzuca
WebPushException z odpowiedzią przy kodzie > 202. Że prawdziwa biblioteka naprawdę tak
robi, sprawdza klasa TestPrawdziwaBiblioteka na końcu — w CI pominięta, lokalnie:

    python3 -m venv /tmp/venv-push && /tmp/venv-push/bin/pip install -r requirements-powiadomienia.txt
    /tmp/venv-push/bin/python -m unittest discover -s tests -p test_wyslij.py -v

Każdy test niżej odrzuca konkretną, łatwą do popełnienia pomyłkę — jaką, mówi jego opis.
Testy filtra `telefony`, kilku plików, limitu na telefon, zamykania zgłoszenia, adresów
nowej aplikacji i kroków workflowów puszczone na wersję sprzed tej zmiany (wyslij.py
i workflowy z 11.10) padają. Strażnicy — testy, które przechodzą w obie strony, bo pilnują
czegoś, co już działało — mają w opisie słowo STRAŻNIK.

Strażnik stałej VAPID w index.html jest ostry: pada, dopóki stałej tam nie ma (przenosi
ją druga część wdrożenia nowej aplikacji). Przejście „po cichu, gdy stałej nie ma"
schowałoby dokładnie tę pomyłkę, która zatrzymałaby wszystkie powiadomienia.
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import wyslij  # noqa: E402

# Pary kluczy wygenerowane 9.10 tak, jak zrobi to strona: WebCrypto, ECDSA P-256,
# prywatny = JWK `d`, publiczny = exportKey('raw'). Testowe — nigdzie nieużywane.
PARY_WEBCRYPTO = [
    # Chromium 141 (headless)
    ("TBQ1ueMh2Gg_Q-MwNzPjJlb8WV209PkmYHoZnKuyJ1w",
     "BJdP3xQaY9tj8B72z8uqNobWmqdx6_cX8hhIqq1zOkQ1l1ywVM9f59MNrN_aRLque4JflQYhoZDcUoIzToW6Ntc"),
    ("7b6-JvTsAftfr0nparBWpExnVjL55mxwLqEWTkdxE9E",
     "BFM0VjVmMK8SeTiGUnvsl7gjQ4qibgpRVIdM5lw5T92TeE36T8PLGBtN65HzuUtx-tZO9L6nQj8n1JtywVmt58Q"),
    ("F0V17bxMwlRwph53i6avr8Snrh1xad1-i2LGY0FQDyQ",
     "BHWtWAT89tH7Rlp7Rqs5yWTOwPf92MiqlzIe3x1Gp84q85tvPDKQ9XpKKE47Ym9EWLzMaWdg--QD4mXuee6Lve4"),
    # Node 22 (crypto.subtle)
    ("kqW8FbTkgfMmesp6YKS_L7amf9W6IJtLmeW1cFjCv4o",
     "BOg77HB1jqD5CDJKPq3PjD2AXl44QEJTuq8-z4JyAc4a6GTMfLjMhYEIeTyGIWlkdrJlcKPD-pkEWvxHJgxN5vs"),
    ("Htx14Flof4JeOBFYYQi6RNc2Y4lb3UpNh318OWiutPs",
     "BMUamB5L4xaP1hDVCJFSGxKHNqSXkPnUw5TdGsmtz3OSmA5rxTD4zbIxIOLLUzc_No158aZMpgWXuEnK35idSNE"),
]
PRYWATNY, PUBLICZNY = PARY_WEBCRYPTO[0]
INNY_PUBLICZNY = PARY_WEBCRYPTO[1][1]

ANDROID = "https://fcm.googleapis.com/fcm/send/dTajnyTokenAndroida:APA91bHsekretnaSciezkaAndroida123"
IPHONE = "https://web.push.apple.com/QGtajnyTokenIphoneaZaszyfrowanyXYZ987654321"


def subskrypcja(endpoint: str, p256dh: str, auth: str) -> dict:
    return {"endpoint": endpoint, "expirationTime": None, "keys": {"p256dh": p256dh, "auth": auth}}


# p256dh to dowolny punkt P-256 (65 B, 0x04…) — atrapa niczego nie szyfruje
SUB_ANDROID = subskrypcja(ANDROID, PARY_WEBCRYPTO[3][1], "QW5kcm9pZEF1dGhTZWtyZQ")
SUB_IPHONE = subskrypcja(IPHONE, PARY_WEBCRYPTO[4][1], "aVBob25lQXV0aFNla3JldA")
# wszystko, czego nie wolno zobaczyć w logu ani w zgłoszeniu
TAJNE = [ANDROID, IPHONE, urlsplit(ANDROID).path, urlsplit(IPHONE).path,
         "dTajnyTokenAndroida", "QGtajnyTokenIphonea",
         SUB_ANDROID["keys"]["auth"], SUB_IPHONE["keys"]["auth"]]

# Wpis bez pola `telefony` — tak wyglądały wszystkie przed ustawieniami per telefon
# i nadal mają iść na oba telefony.
WPIS = {"id": "20261009T140112Z-podlej", "ts": "2026-10-09T14:01:12Z", "przebieg": "123-1",
        "regula": "podlej", "rosliny": ["Azalia"], "tytul": "Podlej: azalia",
        "tresc": "Azalia: gleba 41% (podlewaj przy ok. 45%).", "tag": "podlej",
        "url": "#azalia", "na_sucho": False}
# Klucz publiczny VAPID, przy którym oba telefony założyły subskrypcje (9.10 i 10.10).
# Nie tajny — stoi na publicznej stronie. Inna wartość na stronie = obie subskrypcje do
# wyrzucenia i sekrety PUSH_* do podmiany, więc zmiana ma być świadoma, a nie przypadkowa.
KLUCZ_TELEFONOW = "BCkTpyOmwR5sNru3hotnkn_Im8wtcOuDqzQJEk3Izi0ywWbfwWHSNsdZTbjy1H6EZTaEiaILDjnU_QipTQ2EJIM"


def wpis(**zmiany) -> dict:
    return {**WPIS, **zmiany}


class Odpowiedz:
    def __init__(self, kod: int, tekst: str = ""):
        self.status_code, self.reason, self.text, self.headers = kod, "atrapa", tekst, {}


def zrob_atrape(plan: dict | None = None) -> types.ModuleType:
    """Atrapa pywebpush. `plan`: endpoint → kolejne wyniki (kod HTTP albo wyjątek do
    rzucenia); po wyczerpaniu planu 201."""
    modul = types.ModuleType("pywebpush")
    plan = {k: list(v) for k, v in (plan or {}).items()}

    class WebPushException(Exception):
        def __init__(self, message, response=None):
            super().__init__(message)
            self.message, self.response = message, response

    class Vapid:
        @classmethod
        def from_string(cls, private_key):
            v = cls()
            v.klucz = private_key
            return v

    def webpush(subscription_info, data=None, vapid_private_key=None, vapid_claims=None,
                ttl=0, timeout=None, headers=None, **reszta):
        endpoint = subscription_info["endpoint"]
        # jak pywebpush 2.5.0: uzupełnia słownik roszczeń W MIEJSCU i tylko, gdy pusto
        if vapid_claims is not None:
            if not vapid_claims.get("aud"):
                u = urlsplit(endpoint)
                vapid_claims["aud"] = f"{u.scheme}://{u.netloc}"
            if not vapid_claims.get("exp"):
                vapid_claims["exp"] = int(time.time()) + 12 * 3600
        modul.wywolania.append({"endpoint": endpoint, "roszczenia": dict(vapid_claims or {}),
                                "slownik": vapid_claims, "ttl": ttl, "timeout": timeout,
                                "naglowki": dict(headers or {}), "dane": data,
                                "vapid": vapid_private_key, "reszta": reszta})
        kolejka = plan.get(endpoint)
        wynik = kolejka.pop(0) if kolejka else 201
        if isinstance(wynik, BaseException):
            raise wynik
        if wynik > 202:
            # prawdziwa biblioteka wkłada w komunikat treść odpowiedzi — tu wprost adres
            raise WebPushException(f"Push failed: {wynik} for {endpoint}",
                                   response=Odpowiedz(wynik, endpoint))
        return Odpowiedz(wynik)

    modul.wywolania = []
    modul.WebPushException, modul.Vapid, modul.webpush = WebPushException, Vapid, webpush
    return modul


class AtrapaGh:
    """Zamiast programu gh: zapisuje wywołania; `otwarte` to numer otwartego zgłoszenia."""

    def __init__(self, otwarte: str = ""):
        self.otwarte, self.wywolania = otwarte, []

    def __call__(self, argumenty):
        self.wywolania.append(list(argumenty))
        if argumenty[:2] == ["issue", "list"]:
            return 0, f"{self.otwarte}\n" if self.otwarte else ""
        return 0, ""

    def polecenia(self) -> list[str]:
        return [" ".join(a[:2]) for a in self.wywolania]

    def tresci(self) -> str:
        """Wszystko, co poszło do GitHuba jako tytuł, treść albo komentarz."""
        out = []
        for a in self.wywolania:
            for i, x in enumerate(a[:-1]):
                if x in ("--body", "--title", "--comment"):
                    out.append(a[i + 1])
        return "\n".join(out)


def srodowisko(**zmiany) -> dict:
    env = {"VAPID_KLUCZ_PRYWATNY": PRYWATNY, "PUSH_ANDROID": json.dumps(SUB_ANDROID),
           "PUSH_IPHONE": json.dumps(SUB_IPHONE), "GH_TOKEN": "token-testowy"}
    env.update(zmiany)
    return {k: v for k, v in env.items() if v is not None}


class Baza(unittest.TestCase):
    def setUp(self):
        self.katalog = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.katalog, ignore_errors=True))
        self.strona = self.katalog / "index.html"
        self.ustaw_strone(PUBLICZNY)
        self.plik = self.katalog / "powiadomienia.json"
        self.ustaw_historie([WPIS])
        self.spane = []

    def ustaw_strone(self, klucz: str):
        self.strona.write_text(
            "<!doctype html><script>\nconst GODZ_MS=3600e3;\n"
            f"const VAPID_PUBLICZNY='{klucz}';\n</script>\n", encoding="utf-8")

    def ustaw_historie(self, historia):
        self.plik.write_text(json.dumps({"tryb": "wlaczone", "wlaczone_od": "2026-10-09T10:00:00Z",
                                         "historia": historia}, ensure_ascii=False),
                             encoding="utf-8")

    def uruchom(self, *argv, env=None, atrapa="domyslna", gh=None):
        """main() w tym procesie; zwraca (kod, stdout+stderr, atrapa)."""
        if atrapa == "domyslna":
            atrapa = zrob_atrape()
        self.gh = gh if gh is not None else AtrapaGh()
        argv = list(argv) or ["--plik", str(self.plik), "--przebieg", "123-1"]
        out = io.StringIO()
        with mock.patch.dict(sys.modules, {"pywebpush": atrapa}), \
                redirect_stdout(out), redirect_stderr(out):
            kod = wyslij.main(argv, env=srodowisko() if env is None else env,
                              spij=self.spane.append, gh=self.gh, strona=self.strona)
        return kod, out.getvalue(), atrapa

    def bez_tajemnic(self, tekst: str, gdzie: str):
        for tajne in TAJNE:
            self.assertNotIn(tajne, tekst, f"{gdzie} zdradza adres albo klucz subskrypcji")

    def log_bez_masek(self, log: str) -> str:
        return "\n".join(l for l in log.splitlines() if not l.startswith("::add-mask::"))


class TestKlucz(Baza):
    def test_publiczny_z_prywatnego_to_eksport_raw_z_webcrypto(self):
        """Odrzuca pomyłkę w arytmetyce krzywej i zły format wyniku (np. bez 0x04,
        z dopełnieniem „=", X||Y bez prefiksu) — porównanie z prawdziwym WebCrypto."""
        for d, raw in PARY_WEBCRYPTO:
            with self.subTest(d=d[:6]):
                wynik = wyslij.publiczny_z_prywatnego(d)
                self.assertEqual(wynik, raw)
                self.assertNotIn("=", wynik)
                self.assertEqual(len(wyslij.z_base64url(wynik)), 65)

    def test_klucz_z_bialymi_znakami_z_wklejenia(self):
        """Sekret wklejony z nową linią na końcu to nadal ten sam klucz."""
        self.assertEqual(wyslij.publiczny_z_prywatnego(f"  {PRYWATNY}\n"), PUBLICZNY)

    def test_zly_format_klucza(self):
        """Klucz w złym formacie to komunikat bez wartości sekretu, nie wyjątek z nią."""
        for zly in ("", "nie-klucz", f'"{PRYWATNY}"', PRYWATNY + "AAAA", "A" * 43,
                    wyslij.do_base64url(b"\xff" * 32)):
            with self.subTest(zly=zly[:10]):
                with self.assertRaises(wyslij.BladKonfiguracji) as kontekst:
                    wyslij.publiczny_z_prywatnego(zly)
                if zly:
                    self.assertNotIn(zly.strip('"'), str(kontekst.exception))

    def test_stala_ze_strony(self):
        """Czyta dokładnie zapis `const VAPID_PUBLICZNY='…';`; pusta to '' (jeszcze bez
        kluczy), brak albo dwie stałe i śmieci w środku to błąd, a nie cicha zgoda."""
        self.assertEqual(wyslij.klucz_ze_strony(self.strona), PUBLICZNY)
        self.ustaw_strone("")
        self.assertEqual(wyslij.klucz_ze_strony(self.strona), "")
        for html in ("<script>const INNA='x';</script>",
                     f"const VAPID_PUBLICZNY='{PUBLICZNY}';const VAPID_PUBLICZNY='';",
                     "const VAPID_PUBLICZNY='to-nie-klucz';"):
            with self.subTest(html=html[:30]):
                self.strona.write_text(html, encoding="utf-8")
                with self.assertRaises(wyslij.BladKonfiguracji):
                    wyslij.klucz_ze_strony(self.strona)

    def test_nadawca_czyta_klucz_z_index_html(self):
        """Stała przenosi się z rosliny.html (zostaje z niej przekierowanie bez skryptów)
        do index.html. Nadawca czytający starą stronę kończyłby każdy przebieg kodem 1
        i zgłoszeniem — odrzuca to STRONA i domyślne --strona."""
        self.assertEqual(wyslij.STRONA, REPO / "index.html")
        self.assertEqual(wyslij._parser().parse_args(["--test"]).strona, REPO / "index.html")

    def test_strona_w_repozytorium_ma_czytelna_stala(self):
        """STRAŻNIK, ostry: w index.html stała musi być DOKŁADNIE raz, w zapisie, który czyta
        nadawca (apostrofy, średnik), mieć 87 znaków (65 B base64url) i być tym kluczem, przy
        którym telefony założyły subskrypcje. Pada, dopóki stałej w index.html nie ma —
        cicha zgoda na jej brak to zatrzymane powiadomienia na obu telefonach."""
        strona = REPO / "index.html"
        html = strona.read_text(encoding="utf-8")
        znalezione = wyslij.WZOR_STALEJ.findall(html)
        self.assertEqual(len(znalezione), 1,
                         "index.html: const VAPID_PUBLICZNY='…'; ma być dokładnie raz")
        self.assertEqual(len(re.findall(r"VAPID_PUBLICZNY\s*=", html)), 1,
                         "drugi zapis stałej (np. przykład w komentarzu) myli nadawcę i stronę")
        self.assertEqual(len(znalezione[0]), 87)
        self.assertEqual(wyslij.klucz_ze_strony(strona), KLUCZ_TELEFONOW)


class TestBrakSubskrypcji(Baza):
    def test_bez_sekretow_zielono_i_cicho(self):
        """Etap 3 da się wdrożyć przed etapem 4: bez sekretów linia „brak subskrypcji",
        kod 0, nic nie wysłane, żadnego zgłoszenia."""
        kod, log, atrapa = self.uruchom(env={})
        self.assertEqual(kod, 0)
        self.assertIn("brak subskrypcji", log)
        self.assertEqual(atrapa.wywolania, [])
        self.assertEqual(self.gh.wywolania, [])

    def test_puste_sekrety_to_brak(self):
        """Sekret ustawiony na pusty tekst to brak, nie zły JSON."""
        kod, log, atrapa = self.uruchom(env=srodowisko(PUSH_ANDROID="", PUSH_IPHONE="  "))
        self.assertEqual(kod, 0)
        self.assertIn("brak subskrypcji", log)
        self.assertEqual(atrapa.wywolania, [])

    def test_telefony_bez_klucza(self):
        """Bez klucza nie ma czym podpisać — to też „brak subskrypcji", nie wyjątek."""
        kod, log, atrapa = self.uruchom(env=srodowisko(VAPID_KLUCZ_PRYWATNY=None))
        self.assertEqual(kod, 0)
        self.assertIn("brak subskrypcji", log)
        self.assertEqual(atrapa.wywolania, [])
        self.assertEqual(self.gh.wywolania, [])

    def test_klucz_bez_telefonow_przypomina_o_pustej_stalej(self):
        """Właściciel wkleił klucz, a strona jeszcze bez publicznego: zielono, ale z uwagą."""
        self.ustaw_strone("")
        kod, log, _ = self.uruchom(env=srodowisko(PUSH_ANDROID=None, PUSH_IPHONE=None))
        self.assertEqual(kod, 0)
        self.assertIn("brak subskrypcji", log)
        self.assertIn("pusta", log)

    def test_tryb_testowy_bez_subskrypcji_na_czerwono(self):
        """Ręczny test, który niczego nie wysłał, nie może wyglądać na udany."""
        kod, log, _ = self.uruchom("--test", env={})
        self.assertEqual(kod, 1)
        self.assertIn("brak subskrypcji", log)


class TestKonfiguracja(Baza):
    def test_pusta_stala_przy_obecnym_sekrecie(self):
        """Klucz i telefony są, a strona bez klucza publicznego → kod 1, nic nie wysłane."""
        self.ustaw_strone("")
        kod, log, atrapa = self.uruchom()
        self.assertEqual(kod, 1)
        self.assertIn("jest pusta", log)
        self.assertEqual(atrapa.wywolania, [])
        self.assertIn("issue create", self.gh.polecenia())

    def test_klucz_nie_pasuje_do_strony(self):
        """Sekret z innej pary niż strona → komunikat z ROSLINY.md, kod 1, bez wysyłki
        (każda wysyłka i tak skończyłaby się 403)."""
        self.ustaw_strone(INNY_PUBLICZNY)
        kod, log, atrapa = self.uruchom()
        self.assertEqual(kod, 1)
        self.assertIn("klucz w sekrecie nie pasuje do strony", log)
        self.assertEqual(atrapa.wywolania, [])
        self.assertIn("klucz w sekrecie nie pasuje do strony", self.gh.tresci())

    def test_zly_json_jednego_telefonu(self):
        """Zepsuty sekret iPhone'a: Android i tak dostaje powiadomienie (nieudanej wysyłki
        nikt nie ponowi), a przebieg kończy się kodem 1 z nazwą sekretu — bez jego treści."""
        zepsuty = '{"endpoint": "https://web.push.apple.com/QGtajnyTokenIphonea", "keys": '
        kod, log, atrapa = self.uruchom(env=srodowisko(PUSH_IPHONE=zepsuty))
        self.assertEqual(kod, 1)
        self.assertEqual([w["endpoint"] for w in atrapa.wywolania], [ANDROID])
        self.assertIn("PUSH_IPHONE", log)
        self.assertIn("PUSH_IPHONE", self.gh.tresci())
        self.bez_tajemnic(self.log_bez_masek(log), "log")
        self.bez_tajemnic(self.gh.tresci(), "zgłoszenie")

    def test_subskrypcja_bez_kluczy(self):
        """JSON poprawny, ale to nie subskrypcja (np. sam adres) → błąd konfiguracji."""
        kod, log, atrapa = self.uruchom(env=srodowisko(PUSH_ANDROID=json.dumps({"endpoint": ANDROID})))
        self.assertEqual(kod, 1)
        self.assertEqual([w["endpoint"] for w in atrapa.wywolania], [IPHONE])
        self.bez_tajemnic(self.log_bez_masek(log), "log")

    def test_zly_format_klucza_prywatnego(self):
        kod, log, atrapa = self.uruchom(env=srodowisko(VAPID_KLUCZ_PRYWATNY="to-nie-jest-klucz"))
        self.assertEqual(kod, 1)
        self.assertIn("VAPID_KLUCZ_PRYWATNY", log)
        self.assertNotIn("to-nie-jest-klucz", log)
        self.assertEqual(atrapa.wywolania, [])

    def test_brak_biblioteki(self):
        """Krok bez pip install → czytelny komunikat z nazwą pliku wymagań, kod 1."""
        kod, log, _ = self.uruchom(atrapa=None)
        self.assertEqual(kod, 1)
        self.assertIn("requirements-powiadomienia.txt", log)

    def test_import_leniwy(self):
        """Odrzuca `import pywebpush` na górze pliku: testy w CI nie mają tej paczki,
        a kolektor bez niej ma działać."""
        with mock.patch.dict(sys.modules, {"pywebpush": None}):
            importlib.reload(wyslij)


class TestWyborWpisow(Baza):
    def test_tylko_ten_przebieg_i_naprawde(self):
        """Wysyła wyłącznie wpisy tego przebiegu z na_sucho == false. Wpis na sucho,
        z innego przebiegu (Re-run, wyścig) albo bez pola na_sucho — nie."""
        self.ustaw_historie([
            wpis(id="a", przebieg="122-1"),
            wpis(id="b", na_sucho=True),
            wpis(id="c"),
            {k: v for k, v in wpis(id="d").items() if k != "na_sucho"},
            wpis(id="e", przebieg="123-2"),
            wpis(id="f", tag="czujnik"),
        ])
        kod, _, atrapa = self.uruchom()
        self.assertEqual(kod, 0)
        wyslane = [json.loads(w["dane"])["id"] for w in atrapa.wywolania]
        self.assertEqual(wyslane, ["c", "c", "f", "f"])

    def test_brak_pliku_albo_pusty(self):
        """`git show` nie znalazł pliku (etap 4 jeszcze bez historii) → nic do wysłania."""
        for zawartosc in (None, ""):
            with self.subTest(zawartosc=zawartosc):
                if zawartosc is None:
                    self.plik.unlink(missing_ok=True)
                else:
                    self.plik.write_text(zawartosc, encoding="utf-8")
                kod, log, atrapa = self.uruchom()
                self.assertEqual(kod, 0)
                self.assertIn("nic do wysłania", log)
                self.assertEqual(atrapa.wywolania, [])

    def test_zepsuty_plik(self):
        self.plik.write_text("{nie json", encoding="utf-8")
        kod, _, atrapa = self.uruchom()
        self.assertEqual(kod, 1)
        self.assertEqual(atrapa.wywolania, [])

    def test_limit_wpisow_na_telefon(self):
        """Błąd w regułach nie zasypie telefonu: z MAKS_WPISOW + 2 wpisów każdy telefon
        dostaje pierwsze MAKS_WPISOW, reszta do zgłoszenia — ale kolektor zostaje zielony.
        Odrzuca stary limit 3 na przebieg, który w niedzielę z regułami domu uciąłby
        prawdziwe powiadomienia."""
        m = wyslij.MAKS_WPISOW
        self.ustaw_historie([wpis(id=str(i)) for i in range(m + 2)])
        kod, _, atrapa = self.uruchom()
        self.assertEqual(kod, 0)
        wyslane = [(w["endpoint"], json.loads(w["dane"])["id"]) for w in atrapa.wywolania]
        for adres in (ANDROID, IPHONE):
            self.assertEqual([i for a, i in wyslane if a == adres], [str(i) for i in range(m)])
        self.assertIn("Reguły", self.gh.tresci())
        self.assertIn(f"{m + 2} wpisów dla telefonu Android", self.gh.tresci())

    def test_limit_liczy_sie_osobno_dla_kazdego_telefonu(self):
        """MAKS_WPISOW wpisów tylko dla Androida i tyle samo tylko dla iPhone'a to pełny
        limit na telefon — wszystko idzie, bez zgłoszenia. Odrzuca limit liczony na cały
        przebieg (ten uciąłby połowę), a wpis Androida ponad limit nie zabiera nic
        iPhone'owi."""
        m = wyslij.MAKS_WPISOW
        historia = ([wpis(id=f"a{i}", telefony=["android"]) for i in range(m)]
                    + [wpis(id=f"i{i}", telefony=["iphone"]) for i in range(m)])
        self.ustaw_historie(historia)
        kod, _, atrapa = self.uruchom()
        self.assertEqual(kod, 0)
        self.assertEqual(len(atrapa.wywolania), 2 * m)
        self.assertNotIn("issue create", self.gh.polecenia())

        self.ustaw_historie(historia + [wpis(id=f"a{m}", telefony=["android"])])
        kod, _, atrapa = self.uruchom()
        self.assertEqual(kod, 0)
        wyslane = [(w["endpoint"], json.loads(w["dane"])["id"]) for w in atrapa.wywolania]
        self.assertEqual(sum(a == IPHONE for a, _ in wyslane), m)
        self.assertNotIn((ANDROID, f"a{m}"), wyslane)
        self.assertIn(f"{m + 1} wpisów dla telefonu Android", self.gh.tresci())
        self.assertNotIn("iPhone", self.gh.tresci())


class TestPulapki(Baza):
    def test_swiezy_slownik_roszczen_dla_kazdego_telefonu(self):
        """Pułapka 1: biblioteka dopisuje `aud` do słownika w miejscu. Wspólny słownik
        dałby iPhone'owi aud Google'a — odrzuca to porównanie aud z hostem każdego adresu."""
        _, _, atrapa = self.uruchom()
        aud = [(w["endpoint"], w["roszczenia"]["aud"]) for w in atrapa.wywolania]
        self.assertEqual(aud, [(ANDROID, "https://fcm.googleapis.com"),
                               (IPHONE, "https://web.push.apple.com")])
        self.assertIsNot(atrapa.wywolania[0]["slownik"], atrapa.wywolania[1]["slownik"])

    def test_sub_to_strona_bez_sciezki(self):
        """Pułapka 3: `sub` bez ścieżki i bez mailto z adresem właściciela."""
        _, _, atrapa = self.uruchom()
        for w in atrapa.wywolania:
            self.assertEqual(w["roszczenia"]["sub"], "https://bronek31.github.io")

    def test_ttl_i_limit_czasu_jawnie(self):
        """Pułapka 2: domyślne ttl=0 Apple odrzuca; domyślny timeout biblioteki to brak
        limitu (zmierzone), więc zawieszony serwer trzymałby krok do limitu joba."""
        _, _, atrapa = self.uruchom()
        for w in atrapa.wywolania:
            self.assertEqual(w["ttl"], 43200)
            self.assertIsNotNone(w["timeout"])
            self.assertLessEqual(w["timeout"], 60)

    def test_naglowki_urgency_i_topic(self):
        """Topic = tag, więc nowe „Podlej" zastępuje na serwerze stare, niedoręczone."""
        _, _, atrapa = self.uruchom()
        for w in atrapa.wywolania:
            self.assertEqual(w["naglowki"], {"Urgency": "normal", "Topic": "podlej"})

    def test_tag_spoza_alfabetu_bez_topic(self):
        """Topic spoza base64url albo dłuższy niż 32 znaki serwer odrzuca razem
        z powiadomieniem — lepiej wysłać bez niego."""
        self.ustaw_historie([wpis(tag="podlej azalię"), wpis(id="x", tag="a" * 33)])
        kod, _, atrapa = self.uruchom()
        self.assertEqual(kod, 0)
        self.assertEqual(len(atrapa.wywolania), 4)
        for w in atrapa.wywolania:
            self.assertEqual(w["naglowki"], {"Urgency": "normal"})

    def test_klucz_przez_vapid_from_string(self):
        """Biblioteka dostaje klucz przetworzony przez Vapid.from_string (format JWK `d`)."""
        _, _, atrapa = self.uruchom()
        self.assertEqual(atrapa.wywolania[0]["vapid"].klucz, PRYWATNY)

    def test_tresc_push_z_wpisu(self):
        """sw.js czyta {title, body, tag, url, id} — dokładnie te pola, z wpisu, w UTF-8."""
        _, _, atrapa = self.uruchom()
        dane = atrapa.wywolania[0]["dane"]
        self.assertEqual(json.loads(dane), {"title": "Podlej: azalia",
                                            "body": "Azalia: gleba 41% (podlewaj przy ok. 45%).",
                                            "tag": "podlej", "url": "#azalia",
                                            "id": "20261009T140112Z-podlej"})

    def test_domyslne_pola_tresci_dla_nowej_aplikacji(self):
        """Wpis bez url/tytułu/tagu (planery zawsze je dają, to tylko siatka) prowadzi do
        zakładki Dom nowej aplikacji, a nie do rosliny.html, z której zostało samo
        przekierowanie. Wpis może być z domu, więc tytuł to nazwa aplikacji, nie „Rośliny”."""
        dane = json.loads(wyslij.tresc_push({"tresc": "x"}))
        self.assertEqual(dane["url"], "#dom")
        self.assertEqual(dane["title"], "Smart Home")
        self.assertTrue(wyslij.WZOR_TOPIC.fullmatch(dane["tag"]))
        self.assertNotIn("rosliny.html", json.dumps(dane))

    def test_dluga_tresc_przycieta_do_granicy(self):
        """Ciało powyżej 4096 B to 413 i powiadomienie przepada; przycinamy samą treść."""
        self.ustaw_historie([wpis(tresc="Źdźbło " * 1000, tytul="Podsumowanie tygodnia")])
        _, _, atrapa = self.uruchom()
        dane = atrapa.wywolania[0]["dane"]
        self.assertLessEqual(len(dane.encode("utf-8")), wyslij.MAKS_TRESCI_B)
        tresc = json.loads(dane)
        self.assertEqual(tresc["title"], "Podsumowanie tygodnia")
        self.assertTrue(tresc["body"].startswith("Źdźbło Źdźbło"))
        self.assertTrue(tresc["body"].endswith("…"))


class TestBledyWysylki(Baza):
    def test_wygasla_subskrypcja(self):
        """404/410: zgłoszenie z etykietą i nazwą sekretu do podmiany, iPhone dostaje
        swoje, kolektor zostaje zielony."""
        for kod_http in (404, 410):
            with self.subTest(kod=kod_http):
                kod, log, atrapa = self.uruchom(atrapa=zrob_atrape({ANDROID: [kod_http]}))
                self.assertEqual(kod, 0)
                self.assertEqual([w["endpoint"] for w in atrapa.wywolania], [ANDROID, IPHONE])
                self.assertIn("::warning::Android", log)
                create = [a for a in self.gh.wywolania if a[:2] == ["issue", "create"]]
                self.assertEqual(len(create), 1)
                self.assertIn("powiadomienia", create[0][create[0].index("--label") + 1])
                self.assertIn("PUSH_ANDROID", self.gh.tresci())
                self.assertIn("wygasła", self.gh.tresci())
                self.bez_tajemnic(self.gh.tresci(), "zgłoszenie")
                self.bez_tajemnic(self.log_bez_masek(log), "log")

    def test_403_to_klucz(self):
        """403: serwer nie przyjmuje podpisu — błąd konfiguracji, kod 1."""
        kod, log, _ = self.uruchom(atrapa=zrob_atrape({IPHONE: [403]}))
        self.assertEqual(kod, 1)
        self.assertIn("::error::iPhone", log)
        self.assertIn("PUSH_IPHONE", self.gh.tresci())

    def test_5xx_dwie_ponowne_proby_i_sukces(self):
        """503, 503, 201: dwie ponowne próby z krótką przerwą, potem sukces bez zgłoszenia."""
        kod, _, atrapa = self.uruchom(atrapa=zrob_atrape({ANDROID: [503, 502]}))
        self.assertEqual(kod, 0)
        self.assertEqual([w["endpoint"] for w in atrapa.wywolania], [ANDROID] * 3 + [IPHONE])
        self.assertEqual(self.spane, list(wyslij.PRZERWY_S))
        self.assertNotIn("issue create", self.gh.polecenia())

    def test_429_po_trzech_probach_zgloszenie(self):
        """Trzy razy 429 → koniec prób (nie czwarta), zgłoszenie, kod 0."""
        kod, log, atrapa = self.uruchom(atrapa=zrob_atrape({ANDROID: [429, 429, 429, 201]}))
        self.assertEqual(kod, 0)
        self.assertEqual([w["endpoint"] for w in atrapa.wywolania].count(ANDROID), 3)
        self.assertEqual(len(self.spane), 2)
        self.assertIn("issue create", self.gh.polecenia())
        self.assertIn("429", self.gh.tresci())

    def test_blad_sieci_ponawiany_bez_adresu_w_logu(self):
        """Wyjątek requests cytuje ścieżkę adresu („…with url: /fcm/send/…"). Ponawiamy go
        jak 5xx, a do logu idzie tylko nazwa typu."""
        blad = requests.ConnectionError(
            f"HTTPSConnectionPool(host='fcm.googleapis.com', port=443): Max retries exceeded "
            f"with url: {urlsplit(ANDROID).path} (Caused by NewConnectionError)")
        kod, log, atrapa = self.uruchom(atrapa=zrob_atrape({ANDROID: [blad, blad, blad]}))
        self.assertEqual(kod, 0)
        self.assertEqual(self.spane, list(wyslij.PRZERWY_S))
        self.assertIn("ConnectionError", log)
        self.bez_tajemnic(self.log_bez_masek(log), "log")
        self.bez_tajemnic(self.gh.tresci(), "zgłoszenie")

    def test_inny_kod_bez_ponowien(self):
        """400 to nie przeciążenie — jedna próba, zgłoszenie."""
        kod, _, atrapa = self.uruchom(atrapa=zrob_atrape({ANDROID: [400]}))
        self.assertEqual(kod, 0)
        self.assertEqual([w["endpoint"] for w in atrapa.wywolania].count(ANDROID), 1)
        self.assertEqual(self.spane, [])
        self.assertIn("issue create", self.gh.polecenia())

    def test_nieoczekiwany_wyjatek_z_adresem(self):
        kod, log, _ = self.uruchom(atrapa=zrob_atrape({ANDROID: [RuntimeError(f"boom {ANDROID}")]}))
        self.assertEqual(kod, 1)
        self.assertIn("RuntimeError", log)
        self.bez_tajemnic(self.log_bez_masek(log), "log")

    def test_otwarte_zgloszenie_odswiezone_a_nie_drugie(self):
        """Błąd, który wraca co przebieg, odświeża treść otwartego zgłoszenia."""
        self.uruchom(atrapa=zrob_atrape({ANDROID: [410]}), gh=AtrapaGh(otwarte="17"))
        self.assertIn(["issue", "edit", "17"], [a[:3] for a in self.gh.wywolania])
        self.assertNotIn("issue create", self.gh.polecenia())

    def test_bez_tokenu_tylko_log(self):
        kod, log, _ = self.uruchom(atrapa=zrob_atrape({ANDROID: [410]}),
                                   env=srodowisko(GH_TOKEN=None))
        self.assertEqual(kod, 0)
        self.assertEqual(self.gh.wywolania, [])
        self.assertIn("Zgłoszenie pominięte", log)

    def test_udana_wysylka_zamyka_zgloszenie(self):
        """Pierwsza wysyłka, która doszła do wszystkich telefonów, zamyka zgłoszenie —
        następna awaria założy nowe, czyli przyjdzie mail."""
        kod, _, _ = self.uruchom(gh=AtrapaGh(otwarte="17"))
        self.assertEqual(kod, 0)
        self.assertIn(["issue", "close", "17"], [a[:3] for a in self.gh.wywolania])

    def test_nic_do_wyslania_nie_rusza_zgloszen(self):
        self.ustaw_historie([])
        self.uruchom(gh=AtrapaGh(otwarte="17"))
        self.assertEqual(self.gh.wywolania, [])


class TestTrybTestowy(Baza):
    def test_wysyla_do_wszystkich_bez_pliku(self):
        kod, log, atrapa = self.uruchom("--test", "--przebieg", "99-1")
        self.assertEqual(kod, 0)
        self.assertEqual([w["endpoint"] for w in atrapa.wywolania], [ANDROID, IPHONE])
        tresc = json.loads(atrapa.wywolania[0]["dane"])
        self.assertEqual(tresc["title"], "Powiadomienia działają")
        self.assertEqual(tresc["id"], "test-99-1")
        # zakładka z ustawieniami i „Ten telefon” — tam właściciel sprawdza, co dalej
        self.assertEqual(tresc["url"], "#powiadomienia")

    def test_test_ignoruje_pliki_i_pole_telefony(self):
        """STRAŻNIK (stary nadawca też nie czytał plików przy --test): test idzie na każdy
        podpięty telefon niezależnie od ustawień — wpis „tylko Android” go nie ogranicza."""
        self.ustaw_historie([wpis(przebieg="99-1", telefony=["android"])])
        kod, _, atrapa = self.uruchom("--test", "--przebieg", "99-1", "--plik", str(self.plik))
        self.assertEqual(kod, 0)
        self.assertEqual([w["endpoint"] for w in atrapa.wywolania], [ANDROID, IPHONE])
        self.assertEqual({json.loads(w["dane"])["tag"] for w in atrapa.wywolania}, {"test"})

    def test_blad_w_trybie_testowym_na_czerwono(self):
        """Martwa subskrypcja przy ręcznym teście to czerwony przebieg, nie tylko zgłoszenie."""
        kod, log, _ = self.uruchom("--test", atrapa=zrob_atrape({IPHONE: [410]}))
        self.assertEqual(kod, 1)
        self.assertIn("::error::iPhone", log)

    def test_bez_test_potrzebny_przebieg(self):
        """STRAŻNIK (stary nadawca też tak robił): bez numeru przebiegu nie ma jak wybrać
        wpisów — argparse, kod 2. (--plik ma już wartość domyślną, więc jego brak nie jest
        błędem: patrz TestKilkaPlikow.)"""
        for argv in ([], ["--plik", str(self.plik)]):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as kontekst:
                wyslij.main(argv, env={}, gh=AtrapaGh())
            self.assertEqual(kontekst.exception.code, 2)


class TestFiltrTelefonow(Baza):
    """Pole `telefony` wpisu: komu ten przebieg wysyła (ustawienia i cisza nocna telefonu
    rozstrzygnięte w kolektorze). Nadawca sprzed tej zmiany wysyłał każdy wpis na każdy
    telefon — każdy test niżej to odrzuca."""

    def test_tylko_wskazany_telefon(self):
        """Wpis „tylko Android” nie budzi iPhone'a w jego ciszy nocnej; iPhone dostaje
        w logu jedną linię bez powodu (ustawienia czy cisza — to rozstrzygnął kolektor)."""
        self.ustaw_historie([wpis(telefony=["android"])])
        kod, log, atrapa = self.uruchom()
        self.assertEqual(kod, 0)
        self.assertEqual([w["endpoint"] for w in atrapa.wywolania], [ANDROID])
        o_iphonie = [l for l in self.log_bez_masek(log).splitlines() if "iPhone" in l]
        self.assertEqual(o_iphonie, ["iPhone: nic w tym przebiegu."])
        self.assertNotIn("issue create", self.gh.polecenia())

        self.ustaw_historie([wpis(telefony=["iphone"])])
        kod, log, atrapa = self.uruchom()
        self.assertEqual([w["endpoint"] for w in atrapa.wywolania], [IPHONE])
        self.assertIn("Android: nic w tym przebiegu.", log)

    def test_pusta_lista_to_nikt_i_bez_zgloszenia(self):
        """`telefony: []` (reguła wyłączona albo cisza na obu) — nic nie idzie, nie ma
        czego zgłaszać ani zamykać, a brak biblioteki nie jest wtedy błędem."""
        self.ustaw_historie([wpis(telefony=[])])
        kod, log, atrapa = self.uruchom(gh=AtrapaGh(otwarte="17"))
        self.assertEqual(kod, 0)
        self.assertEqual(atrapa.wywolania, [])
        self.assertEqual(self.gh.wywolania, [])
        self.assertIn("Android: nic w tym przebiegu.", log)
        self.assertIn("iPhone: nic w tym przebiegu.", log)
        kod, log, _ = self.uruchom(atrapa=None)
        self.assertEqual(kod, 0, log)
        self.assertNotIn("pywebpush", log)

    def test_mieszane_wpisy_brak_pola_to_oba(self):
        """Brak pola = oba telefony (wpisy sprzed ustawień per telefon); kolejność wysyłek
        idzie za wpisami, a w obrębie wpisu Android, potem iPhone — niezależnie od kolejności
        na liście."""
        self.ustaw_historie([wpis(id="stary"), wpis(id="a", telefony=["android"]),
                             wpis(id="oba", telefony=["iphone", "android"])])
        kod, _, atrapa = self.uruchom()
        self.assertEqual(kod, 0)
        wyslane = [(w["endpoint"], json.loads(w["dane"])["id"]) for w in atrapa.wywolania]
        self.assertEqual(wyslane, [(ANDROID, "stary"), (IPHONE, "stary"), (ANDROID, "a"),
                                   (ANDROID, "oba"), (IPHONE, "oba")])

    def test_zly_typ_pomija_wpis_i_zglasza(self):
        """Zepsute pole `telefony` to błąd planera: ten wpis nie idzie nigdzie (zgadywanie
        mogłoby obudzić telefon w ciszy), reszta idzie, zgłoszenie „Reguły”, kolektor
        zielony, żadnej wywrotki."""
        for zle in ("android", None, 5, True, {"android": True}, ["android", 1], ["ipad"],
                    [["android"]]):
            with self.subTest(telefony=zle):
                self.ustaw_historie([wpis(id="zepsuty", telefony=zle), wpis(id="dobry")])
                kod, log, atrapa = self.uruchom()
                self.assertEqual(kod, 0, log)
                self.assertEqual([json.loads(w["dane"])["id"] for w in atrapa.wywolania],
                                 ["dobry", "dobry"])
                self.assertIn("Reguły", self.gh.tresci())
                self.assertIn("zepsuty", self.gh.tresci())
                self.assertIn("::warning::Reguły", log)

    def test_powtorzony_telefon_dostaje_raz(self):
        self.ustaw_historie([wpis(telefony=["android", "android"])])
        _, _, atrapa = self.uruchom()
        self.assertEqual([w["endpoint"] for w in atrapa.wywolania], [ANDROID])

    def test_wpis_dla_niepodpietego_telefonu(self):
        """iPhone bez subskrypcji (pusty sekret): wpis tylko dla niego nie idzie nigdzie
        i nie jest błędem — telefonu po prostu nie ma."""
        self.ustaw_historie([wpis(telefony=["iphone"])])
        kod, log, atrapa = self.uruchom(env=srodowisko(PUSH_IPHONE=""))
        self.assertEqual(kod, 0)
        self.assertEqual(atrapa.wywolania, [])
        self.assertNotIn("issue create", self.gh.polecenia())
        self.assertIn("Android: nic w tym przebiegu.", log)

    def test_id_telefonow_jak_w_telefony_py(self):
        """STRAŻNIK: id w polu `telefony` pisze kolektor z telefony.TELEFONY. Literówka
        po jednej stronie po cichu odcięłaby telefon (nadawca uznałby wpis za zepsuty)."""
        import telefony
        self.assertEqual(wyslij.ID_TELEFONOW, telefony.TELEFONY)


class TestZamykanieZgloszenia(Baza):
    """Zgłoszenie zamyka się tylko, gdy w tym przebiegu każdy podpięty telefon dostał
    co najmniej jedno powiadomienie i nic nie zawiodło."""

    def test_wysylka_na_czesc_telefonow_nie_zamyka(self):
        """Przebieg tylko na Androida nic nie mówi o martwej subskrypcji iPhone'a — stary
        nadawca zamykał zgłoszenie po każdej udanej wysyłce i chował ją."""
        self.ustaw_historie([wpis(telefony=["android"])])
        kod, _, _ = self.uruchom(gh=AtrapaGh(otwarte="17"))
        self.assertEqual(kod, 0)
        self.assertNotIn("issue close", self.gh.polecenia())

    def test_kazdy_telefon_cos_dostal_zamyka(self):
        """STRAŻNIK (stary nadawca zamykał zawsze po wysyłce): różne wpisy, ale każdy
        telefon coś dostał — zamyka. Odrzuca warunek „każdy wpis na każdy telefon”."""
        self.ustaw_historie([wpis(id="a", telefony=["android"]), wpis(id="i", telefony=["iphone"])])
        self.uruchom(gh=AtrapaGh(otwarte="17"))
        self.assertIn(["issue", "close", "17"], [a[:3] for a in self.gh.wywolania])

    def test_jedyny_podpiety_telefon_zamyka(self):
        """STRAŻNIK (stary nadawca też zamykał): liczą się telefony z subskrypcją, nie
        wszystkie znane — bez iPhone'a w sekretach zgłoszenie zamyka sama wysyłka na Androida."""
        self.ustaw_historie([wpis(telefony=["android"])])
        self.uruchom(env=srodowisko(PUSH_IPHONE=None), gh=AtrapaGh(otwarte="17"))
        self.assertIn(["issue", "close", "17"], [a[:3] for a in self.gh.wywolania])

    def test_blad_regul_nie_zamyka(self):
        """Oba telefony dostały dobry wpis, ale inny był zepsuty — zgłoszenie się odświeża,
        nie zamyka."""
        self.ustaw_historie([wpis(id="zepsuty", telefony="android"), wpis(id="dobry")])
        self.uruchom(gh=AtrapaGh(otwarte="17"))
        self.assertNotIn("issue close", self.gh.polecenia())
        self.assertIn(["issue", "edit", "17"], [a[:3] for a in self.gh.wywolania])


class TestKilkaPlikow(Baza):
    """Rośliny i dom mają osobne pliki powiadomień; krok wysyłki podaje oba (--plik dwa
    razy). Stary nadawca brał jeden --plik — przy dwóch wygrywał ostatni."""

    def setUp(self):
        super().setUp()
        (self.katalog / "rosliny").mkdir()
        (self.katalog / "dom").mkdir()
        self.plik = self.katalog / "rosliny" / "powiadomienia.json"
        self.plik_dom = self.katalog / "dom" / "powiadomienia.json"
        self.ustaw_historie([wpis(id="r")])
        self.ustaw_dom([wpis(id="d", regula="przewietrz", rosliny=None, pokoje=["Łazienka"],
                             tag="przewietrz-lazienka", url="#lazienka")])

    def ustaw_dom(self, historia):
        self.plik_dom.write_text(json.dumps({"tryb": "wlaczone", "historia": historia},
                                            ensure_ascii=False), encoding="utf-8")

    def oba(self, *reszta):
        return ("--plik", str(self.plik), "--plik", str(self.plik_dom), "--przebieg", "123-1",
                *reszta)

    def wyslane(self, atrapa):
        return [(w["endpoint"], json.loads(w["dane"])["id"]) for w in atrapa.wywolania]

    def test_wpisy_z_obu_plikow_po_kolei(self):
        kod, _, atrapa = self.uruchom(*self.oba())
        self.assertEqual(kod, 0)
        self.assertEqual(self.wyslane(atrapa), [(ANDROID, "r"), (IPHONE, "r"),
                                                (ANDROID, "d"), (IPHONE, "d")])
        self.assertEqual(json.loads(atrapa.wywolania[2]["dane"])["url"], "#lazienka")

    def test_brak_pliku_domu_to_nic_z_niego(self):
        """Zanim dom.py zapisze pierwszy plik, krok wysyłki go nie poda — a gdyby podał
        nieistniejący, to „pusto”, nie błąd."""
        self.plik_dom.unlink()
        kod, log, atrapa = self.uruchom(*self.oba())
        self.assertEqual(kod, 0)
        self.assertEqual(self.wyslane(atrapa), [(ANDROID, "r"), (IPHONE, "r")])
        self.assertNotIn("issue create", self.gh.polecenia())

    def test_domyslnie_oba_pliki_z_data(self):
        with mock.patch.object(wyslij, "PLIKI", (self.plik, self.plik_dom)):
            kod, _, atrapa = self.uruchom("--przebieg", "123-1")
        self.assertEqual(kod, 0)
        self.assertEqual([i for _, i in self.wyslane(atrapa)], ["r", "r", "d", "d"])

    def test_jawny_plik_nie_dokleja_domyslnych(self):
        """Pułapka argparse: action="append" z listą domyślną DOKŁADA podane --plik do
        domyślnych. Jawne --plik ma czytać tylko to, co podano."""
        with mock.patch.object(wyslij, "PLIKI", (self.plik,)):
            kod, _, atrapa = self.uruchom("--plik", str(self.plik_dom), "--przebieg", "123-1")
        self.assertEqual(kod, 0)
        self.assertEqual([i for _, i in self.wyslane(atrapa)], ["d", "d"])

    def test_zepsuty_plik_nie_zatrzymuje_drugiego(self):
        """Zepsuty plik domu nie zabiera powiadomień o roślinach: te idą, a przebieg kończy
        się kodem 1 i zgłoszeniem, które mówi, który plik."""
        self.plik_dom.write_text("{nie json", encoding="utf-8")
        kod, log, atrapa = self.uruchom(*self.oba())
        self.assertEqual(kod, 1)
        self.assertEqual(self.wyslane(atrapa), [(ANDROID, "r"), (IPHONE, "r")])
        self.assertIn("dom/powiadomienia.json", self.gh.tresci())
        self.assertIn("::error::Dane", log)

    def test_limit_liczy_wpisy_z_obu_plikow(self):
        """Limit na telefon to suma z obu plików — inaczej dwa pliki dawałyby dwa limity."""
        polowa = wyslij.MAKS_WPISOW // 2 + 1          # każdy plik osobno mieści się w limicie
        self.ustaw_historie([wpis(id=f"r{i}") for i in range(polowa)])
        self.ustaw_dom([wpis(id=f"d{i}") for i in range(polowa)])
        kod, _, atrapa = self.uruchom(*self.oba())
        self.assertEqual(kod, 0)
        self.assertEqual(len(atrapa.wywolania), 2 * wyslij.MAKS_WPISOW)
        self.assertIn(f"{2 * polowa} wpisów dla telefonu Android", self.gh.tresci())

    def test_najgorszy_przebieg_obu_planerow_miesci_sie_w_limicie(self):
        """MAKS_WPISOW to realna górna granica, a nie zgadywanie: prawdziwe planery
        (rosliny.py, dom.py) w pierwszym przebiegu po ciszy Androida dają mu 13 wpisów —
        7 roślin (świeże podlej, czujnik i przestaw jednej rośliny, odłożone podlej, czujnik
        i przestaw drugiej, odłożone podsumowanie) i 6 domu (świeże przewietrz, przed snem,
        okno, czujniki, odłożone przewietrz i czujniki). Dawny limit 10 obcinał trzy z nich
        i zakładał zgłoszenie „Reguły" (przegląd, B5).

        Android: cisza 14–12 (koniec ciszy w oknie „przed snem" 12–14), podsumowanie
        włączone; iPhone bez ciszy, więc reguły idą świeżo także w ciszy Androida.
        Niedziela 18.10, przebiegi 9:01–12:01."""
        from datetime import datetime
        from zoneinfo import ZoneInfo

        import dom
        import rosliny
        import telefony
        strefa = ZoneInfo("Europe/Warsaw")
        ust = {"android": {**telefony.DOMYSLNE, "od": 14, "do": 12, "podsumowanie": True},
               "iphone": {**telefony.DOMYSLNE, "cisza": False}}

        def chwila(godz: int) -> int:
            return int(datetime(2026, 10, 18, godz, 1, tzinfo=strefa).timestamp() * 1000)

        def roslina(nazwa: str, gatunek: str, sucha: bool, bateria: bool, przestaw: bool) -> dict:
            return {"nazwa": nazwa, "gatunek": gatunek, "werdykt": "podlej" if sucha else "ok",
                    "ostatnie": {"gleba": {"v": 21.0 if sucha else 40.0},
                                 "bateria": {"v": "low" if bateria else "high"}},
                    "prog_gleba": 24, "podlania": [], "uwagi": [],
                    "do_zgloszenia": ["Bateria na wyczerpaniu."] if bateria else [],
                    "swiatlo_ocena": ({"kierunek": "jasniej", "u": 0.2, "proc": 20, "doby": [], "szczyt_lx": 50}
                                      if przestaw else None),
                    "swiatlo_dobowe": [], "swiatlo_potrzeba_lxh": 20000}

        def pokoj(**pola) -> dict:
            return {"przewietrz": None, "okno": None, "noc": None, "milczy_od": None, "bateria": "middle", **pola}

        przewietrz = {"od": "2026-10-18T06:00:00Z", "wilg": 71.0, "granica": 63.2}
        okno = {"od": "2026-10-18T09:40:00Z", "przed": 21.2, "teraz": 18.4, "spadek": 2.8}
        noc = {"noc": "2026-10-18", "t_min": 4.0, "granica": 60.4, "zwykle": 60.9, "ostrz": True}
        # godzina → (fikus, skrzydłokwiat) jako (sucha, słaba bateria, „jaśniej") i pokoje:
        # o 11:01 Android śpi — fikus i kuchnia idą świeżo do iPhone'a, a Androidowi do kolejki
        # (podsumowanie już o 10:01); o 12:01 skrzydłokwiat i pozostałe pokoje idą świeżo do obu.
        przebiegi = {
            9: (((True, False, False), (False, False, False)), {}),
            10: (((True, False, False), (True, False, False)), {}),
            11: (((True, True, True), (True, False, False)),
                 {"kuchnia": pokoj(przewietrz=przewietrz, bateria="low")}),
            12: (((True, True, True), (True, True, True)),
                 {"kuchnia": pokoj(przewietrz=przewietrz, bateria="low"),
                  "lazienka": pokoj(przewietrz=przewietrz, noc=noc),
                  "salon": pokoj(bateria="low"), "sypialnia": pokoj(okno=okno)}),
        }
        plik_r = {"tryb": "wlaczone", "wlaczone_od": "2026-10-01T00:00:00Z", "historia": [], "stan_regul": {},
                  "podsumowanie_ostatnie": None}
        plik_d = {"tryb": "wlaczone", "wlaczone_od": "2026-10-01T00:00:00Z", "historia": [], "stan_regul": {}}
        for godz, ((fikus, skrzydlokwiat), pokoje) in przebiegi.items():
            stany = [roslina("Fikus", "fikus", *fikus), roslina("Skrzydłokwiat", "skrzydlokwiat", *skrzydlokwiat)]
            nr = "123-1" if godz == 12 else f"{godz}-1"
            plik_r = json.loads(json.dumps(rosliny.zaplanuj_powiadomienia(
                stany, plik_r, chwila(godz), strefa, "wlaczone", nr, ust)))
            stan = {"updated": "", "pokoje": {d: pokoje.get(d, pokoj())
                                              for d in ("lazienka", "kuchnia", "salon", "sypialnia")}}
            plik_d = json.loads(json.dumps(dom.zaplanuj_powiadomienia(
                stan, plik_d, chwila(godz), strefa, "wlaczone", nr, ust)))
        self.plik.write_text(json.dumps(plik_r, ensure_ascii=False), encoding="utf-8")
        self.plik_dom.write_text(json.dumps(plik_d, ensure_ascii=False), encoding="utf-8")
        android = [(w["regula"], bool(w.get("odlozone"))) for p in (plik_r, plik_d) for w in p["historia"]
                   if w["przebieg"] == "123-1" and "android" in w["telefony"]]
        self.assertEqual(sorted(android), sorted([
            ("podlej", False), ("czujnik", False), ("przestaw", False),
            ("podlej", True), ("czujnik", True), ("przestaw", True), ("podsumowanie", True),
            ("przewietrz", False), ("przed-snem", False), ("okno", False), ("czujniki", False),
            ("przewietrz", True), ("czujniki", True)]))
        self.assertEqual(len(android), wyslij.MAKS_WPISOW, "limit = najgorszy przypadek, nie mniej i nie więcej")

        kod, log, atrapa = self.uruchom(*self.oba())
        self.assertEqual(kod, 0, log)
        self.assertEqual(sum(a == ANDROID for a, _ in self.wyslane(atrapa)), 13)
        self.assertNotIn("Reguły", self.gh.tresci())
        self.assertNotIn("issue create", self.gh.polecenia())


WORKFLOWY = REPO / ".github" / "workflows"


def kroki(plik: Path) -> list[dict]:
    """Kroki workflowu bez PyYAML (w CI testy mają tylko requests). Na nasze pliki
    wystarczy: lista pod `steps:`, klucze kroku dwie spacje za „- ”, `env:` jako
    NAZWA: wartość, `run:` w jednej linii albo jako blok `|`.
    Wynik: [{"nazwa", "klucze": set, "env": {…}, "run": tekst, "tekst": surowy krok}]."""
    linie = plik.read_text(encoding="utf-8").splitlines()
    surowe, i = [], 0
    while i < len(linie):
        m = re.match(r"^(\s*)steps:\s*$", linie[i])
        i += 1
        if not m:
            continue
        poziom = len(m.group(1)) + 2
        while i < len(linie):
            linia, bez = linie[i], linie[i].strip()
            wciecie = len(linia) - len(linia.lstrip())
            if bez and not bez.startswith("#") and wciecie < poziom:
                break
            if wciecie == poziom and bez.startswith("- "):
                surowe.append([" " * (poziom + 2) + linia[poziom + 2:]])
            elif surowe and (wciecie > poziom or not bez):
                surowe[-1].append(linia)
            i += 1
    wynik = []
    for krok in surowe:
        opis = {"nazwa": "", "klucze": set(), "env": {}, "run": "", "tekst": "\n".join(krok)}
        k = 0
        while k < len(krok):
            m = re.match(r"^\s*([A-Za-z_-]+):\s*(.*)$", krok[k])
            k += 1
            if not m or len(krok[k - 1]) - len(krok[k - 1].lstrip()) != len(krok[0]) - len(krok[0].lstrip()):
                continue
            klucz, wartosc = m.group(1), m.group(2).strip()
            opis["klucze"].add(klucz)
            glebiej = []
            while k < len(krok) and (not krok[k].strip() or
                                     len(krok[k]) - len(krok[k].lstrip()) > len(krok[0]) - len(krok[0].lstrip())):
                glebiej.append(krok[k])
                k += 1
            if klucz == "name":
                opis["nazwa"] = wartosc
            elif klucz == "env":
                for l in glebiej:
                    me = re.match(r"^\s*([A-Z0-9_]+):\s*(.*?)\s*$", l)
                    if me and not l.strip().startswith("#"):
                        opis["env"][me.group(1)] = me.group(2)
            elif klucz == "run":
                if wartosc == "|":
                    niepuste = [l for l in glebiej if l.strip()]
                    odsuniecie = min(len(l) - len(l.lstrip()) for l in niepuste)
                    opis["run"] = "\n".join(l[odsuniecie:] for l in glebiej).strip("\n") + "\n"
                else:
                    opis["run"] = wartosc
        wynik.append(opis)
    return wynik


def krok(plik: Path, poczatek_nazwy: str) -> dict:
    pasujace = [k for k in kroki(plik) if k["nazwa"].startswith(poczatek_nazwy)]
    if len(pasujace) != 1:
        raise AssertionError(f"{plik.name}: kroków „{poczatek_nazwy}…” jest {len(pasujace)}")
    return pasujace[0]


ZBIERAJ = WORKFLOWY / "zbieraj.yml"
KROK_POBIERZ = "Pobierz odczyty"
KROK_WYSYLKI = "Wyślij powiadomienia"


class TestWorkflowy(Baza):
    def test_ustawienia_telefonow_tylko_przez_env_kroku_pobierz(self):
        """Kolektor dostaje zmienne repozytorium POWIADOMIENIA_ANDROID/IPHONE (nazwy
        z telefony.ZMIENNE) w env: kroku „Pobierz…”, i tylko tam. Żaden run: w żadnym
        workflowie nie wkleja `vars.` — treść zmiennej ustawia każdy, kto ma klucz
        z telefonu, a wklejona w skrypt byłaby kodem powłoki."""
        import telefony
        pobierz = krok(ZBIERAJ, KROK_POBIERZ)
        for nazwa in telefony.ZMIENNE.values():
            self.assertEqual(pobierz["env"].get(nazwa), "${{ vars.%s }}" % nazwa)
        # globalny wyłącznik zostaje obok (jego wartość to decyzja właściciela, nie testu)
        self.assertIn("POWIADOMIENIA", pobierz["env"])
        for plik in sorted(WORKFLOWY.glob("*.yml")):
            for k in kroki(plik):
                with self.subTest(plik=plik.name, krok=k["nazwa"]):
                    self.assertNotIn("vars.", k["run"])
                    if k["nazwa"] != pobierz["nazwa"] and plik == ZBIERAJ:
                        self.assertNotIn("vars.", k["tekst"])

    def test_sekrety_tylko_w_kroku_wysylki_po_zapisie(self):
        """STRAŻNIK (tak było i ma zostać): sekrety powiadomień ma wyłącznie krok wysyłki,
        stoi po kroku z zapisz.sh i nie ma `if:` — `if: always()` wysłałby po nieudanym
        zapisie, czyli wpisy, których nie ma na main."""
        nazwy = [k["nazwa"] for k in kroki(ZBIERAJ)]
        wysylka = krok(ZBIERAJ, KROK_WYSYLKI)
        for k in kroki(ZBIERAJ):
            for sekret in ("VAPID_KLUCZ_PRYWATNY", "PUSH_ANDROID", "PUSH_IPHONE"):
                with self.subTest(krok=k["nazwa"], sekret=sekret):
                    if k["nazwa"] == wysylka["nazwa"]:
                        self.assertEqual(k["env"].get(sekret), "${{ secrets.%s }}" % sekret)
                    else:
                        self.assertNotIn(f"secrets.{sekret}", k["tekst"])
        self.assertGreater(nazwy.index(wysylka["nazwa"]),
                           nazwy.index(krok(ZBIERAJ, KROK_POBIERZ)["nazwa"]))
        self.assertIn("sh zapisz.sh", krok(ZBIERAJ, KROK_POBIERZ)["run"])
        self.assertNotIn("if", wysylka["klucze"])

    def test_powiadomienie_testowe_sprawdza_index_html(self):
        """Ręczny test pomija się przy pushu tylko wtedy, gdy stała jest pusta — w tym
        samym pliku i w tym samym zapisie, które czyta nadawca. Grep na rosliny.html
        (sam stub) nigdy by nie trafił i test świeciłby na czerwono."""
        k = krok(WORKFLOWY / "powiadomienie-testowe.yml", "Wyślij powiadomienie testowe")
        m = re.search(r'grep -q "([^"]+)" (\S+?);', k["run"])
        self.assertIsNotNone(m, k["run"])
        wzorzec, plik = m.groups()
        self.assertEqual(plik, "index.html")
        self.assertEqual(plik, wyslij.STRONA.name)
        self.ustaw_strone("")
        self.assertIn(wzorzec, self.strona.read_text(encoding="utf-8"))
        self.assertEqual(wyslij.klucz_ze_strony(self.strona), "")
        self.assertIn("wyslij.py --test", k["run"])

    def test_powiadomienie_testowe_nie_budzi_w_nocy(self):
        """Push zmieniający powiadomienie-testowe.yml scalony między 21:00 a 8:00 czasu Warszawy
        nie wysyła testu (domyślna cisza obu telefonów; wdrożenie 11.10 wypadło o 22:30),
        a ręczne „Run workflow” wysyła o każdej porze. Krok uruchomiony naprawdę w bash,
        z podstawionymi `date` i `python`."""
        if shutil.which("bash") is None:
            if os.environ.get("CI"):
                self.fail("w CI musi być bash")
            self.skipTest("brak bash")
        k = krok(WORKFLOWY / "powiadomienie-testowe.yml", "Wyślij powiadomienie testowe")
        robocze = self.katalog / "noc"
        atrapy = robocze / "atrapy"
        atrapy.mkdir(parents=True)
        shutil.copy(REPO / "index.html", robocze / "index.html")
        (atrapy / "date").write_text('#!/bin/sh\necho "$GODZINA_ATRAPY"\n', encoding="utf-8")
        (atrapy / "python").write_text('#!/bin/sh\necho wyslano >> "$ZNACZNIK"\n', encoding="utf-8")
        for plik in atrapy.iterdir():
            plik.chmod(0o755)

        def uruchom(zdarzenie, godzina):
            znacznik = robocze / f"znacznik-{zdarzenie}-{godzina}"
            env = dict(os.environ, PATH=f"{atrapy}:{os.environ['PATH']}", GITHUB_EVENT_NAME=zdarzenie,
                       GODZINA_ATRAPY=str(godzina), ZNACZNIK=str(znacznik),
                       GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1")
            wynik = subprocess.run(["bash", "-e", "-c", k["run"]], cwd=robocze, env=env,
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(wynik.returncode, 0, wynik.stdout + wynik.stderr)
            return znacznik.exists(), wynik.stdout

        for godzina in (21, 22, 0, 7):
            with self.subTest(zdarzenie="push", godzina=godzina):
                wyslano, log = uruchom("push", godzina)
                self.assertFalse(wyslano)
                self.assertIn("Cisza nocna", log)
        for godzina in (8, 12, 20):
            with self.subTest(zdarzenie="push", godzina=godzina):
                self.assertTrue(uruchom("push", godzina)[0])
        for godzina in (23, 3):
            with self.subTest(zdarzenie="workflow_dispatch", godzina=godzina):
                self.assertTrue(uruchom("workflow_dispatch", godzina)[0])

    def test_testy_yml_pilnuje_plikow_strony(self):
        """Strażnik „strona zostaje jednym plikiem” z testy.yml, wykonany naprawdę: brak
        pokoje.json (strona go pobiera) to błąd; rosliny.html dalej jest i dalej podlega
        zasadzie „skrypty tylko z HTTPS”."""
        k = krok(WORKFLOWY / "testy.yml", "Pilnuj, czym ta strona jest")
        m = re.search(r"python3 - <<'PY'\n(.*?)\nPY\n", k["run"], re.S)
        self.assertIsNotNone(m, k["run"])
        skrypt = m.group(1)
        strona = self.katalog / "strona"
        strona.mkdir()
        for plik in ("index.html", "rosliny.html", "manifest.json", "sw.js", "ikona.svg",
                     "ikona-192.png", "ikona-512.png", ".nojekyll"):
            (strona / plik).write_text("<!doctype html>\n", encoding="utf-8")

        def sprawdz():
            return subprocess.run([sys.executable, "-"], input=skrypt, cwd=strona,
                                  capture_output=True, text=True, timeout=60)

        wynik = sprawdz()
        self.assertEqual(wynik.returncode, 1)
        self.assertIn("brak pliku pokoje.json", wynik.stdout)
        (strona / "pokoje.json").write_text("{}", encoding="utf-8")
        self.assertEqual(sprawdz().returncode, 0, sprawdz().stdout)
        (strona / "rosliny.html").write_text('<script src="http://x/a.js"></script>', encoding="utf-8")
        wynik = sprawdz()
        self.assertEqual(wynik.returncode, 1)
        self.assertIn("rosliny.html: skrypt spoza HTTPS", wynik.stdout)
        # bez rosliny.html pętla stron wywraca się już na czytaniu — też na czerwono
        (strona / "rosliny.html").unlink()
        self.assertNotEqual(sprawdz().returncode, 0)


def _wymagaj(*programy):
    """Pomija test bez potrzebnych programów — ale nie w CI (ubuntu-latest ma jq, git
    i bash): tam pominięcie byłoby cichym wyłączeniem testu kroku wysyłki."""
    brak = [p for p in programy if not shutil.which(p)]
    if brak and os.environ.get("CI"):
        raise AssertionError(f"w CI brakuje programów: {', '.join(brak)}")
    if brak:
        raise unittest.SkipTest(f"brak programów: {', '.join(brak)} — strażnik tekstowy niżej")


# Sam select(...) z kroku wysyłki — strażnik tekstowy, gdy nie ma jq (BRIEF5, 4.3).
SELECT_JQ = ('select(.przebieg == $p and (.na_sucho | not) and '
             '(((.telefony // ["android","iphone"]) | length) > 0))')


class TestKrokWysylki(Baza):
    """Skrypt kroku „Wyślij powiadomienia…” z zbieraj.yml uruchomiony naprawdę (bash -e,
    jak w Actions): prawdziwy git i jq, a pip i python podmienione na rejestrujące atrapy."""

    def setUp(self):
        super().setUp()
        self.skrypt = krok(ZBIERAJ, KROK_WYSYLKI)["run"]

    def program_jq(self) -> str:
        m = re.search(r"""jq --arg p "\$PRZEBIEG" '([^']+)'""", self.skrypt)
        self.assertIsNotNone(m, "krok wysyłki nie liczy wpisów jq --arg p \"$PRZEBIEG\" '…'")
        return m.group(1)

    def test_straznik_tekstowy_wyrazenia_jq(self):
        """STRAŻNIK tekstowy (działa też bez jq): krok liczy wpisy z polem `telefony`,
        jak w BRIEF5, a domyślna lista to wszystkie telefony nadawcy."""
        self.assertIn(SELECT_JQ, self.program_jq())
        self.assertEqual(json.loads(re.search(r"\.telefony // (\[[^\]]*\])", SELECT_JQ).group(1)),
                         list(wyslij.ID_TELEFONOW))

    def test_jq_nie_gubi_niczego_co_wyslalby_nadawca(self):
        """jq oszczędza pip install w pustych przebiegach. Musi liczyć dokładnie te wpisy,
        które nadawca wyśle albo zgłosi (na poprawnych wpisach), i nigdy nie może być
        ostrzejszy od wysyłki — inaczej wpis przepada po cichu. Luźniejszy wolno: wpis bez
        `na_sucho` jq liczy, nadawca nie wysyła (co najwyżej raz), a „pusty” zły typ
        (`{}`, "", 0) jq uznaje za nikogo — nadawca też by go nie wysłał, przepada tylko
        zgłoszenie."""
        _wymagaj("jq")
        program = self.program_jq()

        def jq(historia) -> int:
            plik = self.katalog / "jq.json"
            plik.write_text(json.dumps({"historia": historia}), encoding="utf-8")
            wynik = subprocess.run(["jq", "--arg", "p", "123-1", program, str(plik)],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(wynik.returncode, 0, wynik.stderr)
            return int(wynik.stdout)

        def nadawca(historia) -> tuple[int, int]:
            """(wpisy, które nadawca wyśle komuś, wpisy, które wyśle albo zgłosi)."""
            self.ustaw_historie(historia)
            wpisy = wyslij.wpisy_przebiegu(self.plik, "123-1")
            komu = [wyslij.adresaci(w) for w in wpisy]
            return sum(bool(k) for k in komu), sum(k is None or bool(k) for k in komu)

        bez_na_sucho = {k: v for k, v in wpis().items() if k != "na_sucho"}
        poprawne = [wpis(), wpis(telefony=["android"]), wpis(telefony=["iphone"]),
                    wpis(telefony=["android", "iphone"]), wpis(telefony=[]),
                    wpis(na_sucho=True), wpis(na_sucho=True, telefony=["android"]),
                    wpis(przebieg="123-2"), wpis(przebieg="122-1", telefony=["iphone"]),
                    wpis(telefony="android"), wpis(telefony=None), wpis(telefony=["ipad"]),
                    wpis(telefony=[1])]
        luzniejsze = [bez_na_sucho, wpis(na_sucho=None)]
        puste_zle = [wpis(telefony={}), wpis(telefony=""), wpis(telefony=0)]
        for w in poprawne:
            with self.subTest(wpis={k: w.get(k) for k in ("przebieg", "na_sucho", "telefony")}):
                self.assertEqual(jq([w]), nadawca([w])[1])
        for w in luzniejsze + puste_zle:
            with self.subTest(wpis={k: w.get(k) for k in ("przebieg", "na_sucho", "telefony")}):
                self.assertGreaterEqual(jq([w]), nadawca([w])[0])
        for w in luzniejsze:
            self.assertEqual(jq([w]), 1)
        self.assertEqual(jq(poprawne), nadawca(poprawne)[1])
        self.assertGreaterEqual(jq(poprawne + luzniejsze + puste_zle),
                                nadawca(poprawne + luzniejsze + puste_zle)[0])
        self.assertEqual(jq([]), 0)

    # --- cały krok na prawdziwym git i jq ---

    def przygotuj_repo(self):
        _wymagaj("jq", "git", "bash")
        self.gitenv = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                       "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
                       "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com"}
        self.zdalne, self.praca = self.katalog / "zdalne", self.katalog / "praca"
        self.git("init", "-q", "-b", "main", str(self.zdalne))
        (self.zdalne / "README").write_text("x\n", encoding="utf-8")
        self.git("add", "-A", cwd=self.zdalne)
        self.git("commit", "-qm", "start", cwd=self.zdalne)
        self.git("clone", "-q", str(self.zdalne), str(self.praca))
        # atrapy pip i python: zapisują wywołanie, nic nie instalują i nie wysyłają
        self.atrapy = self.katalog / "bin"
        self.atrapy.mkdir()
        self.zapis = self.katalog / "wywolania.txt"
        for program in ("pip", "python"):
            sciezka = self.atrapy / program
            sciezka.write_text('#!/bin/sh\nprintf "%s\\n" "' + program + '" "$@" "--" >> "$ZAPIS"\n',
                               encoding="utf-8")
            sciezka.chmod(0o755)

    def git(self, *argumenty, cwd=None):
        subprocess.run(["git", *argumenty], cwd=cwd, env=self.gitenv, check=True,
                       capture_output=True, text=True, timeout=60)

    def opublikuj(self, **pliki):
        """Commit na „origin/main”: tor → historia (lista) albo surowy tekst; None usuwa."""
        for tor, tresc in pliki.items():
            sciezka = self.zdalne / "data" / tor / "powiadomienia.json"
            if tresc is None:
                sciezka.unlink(missing_ok=True)
                continue
            sciezka.parent.mkdir(parents=True, exist_ok=True)
            sciezka.write_text(tresc if isinstance(tresc, str) else
                               json.dumps({"tryb": "wlaczone", "historia": tresc}), encoding="utf-8")
        self.git("add", "-A", cwd=self.zdalne)
        self.git("commit", "-qm", "dane", "--allow-empty", cwd=self.zdalne)

    def uruchom_krok(self):
        temp = self.katalog / "runner_temp"
        temp.mkdir(exist_ok=True)
        self.zapis.unlink(missing_ok=True)
        env = {**self.gitenv, "PATH": f"{self.atrapy}{os.pathsep}{os.environ.get('PATH', '')}",
               "PRZEBIEG": "123-1", "RUNNER_TEMP": str(temp), "ZAPIS": str(self.zapis)}
        wynik = subprocess.run(["bash", "-e", "-c", self.skrypt], cwd=self.praca, env=env,
                               capture_output=True, text=True, timeout=120)
        wywolania, biezace = [], []
        if self.zapis.exists():
            for linia in self.zapis.read_text(encoding="utf-8").splitlines():
                if linia == "--":
                    wywolania.append(biezace)
                    biezace = []
                else:
                    biezace.append(linia)
        return wynik, wywolania, temp

    def test_oba_pliki_z_origin_main(self):
        """Wpisy tego przebiegu w obu plikach: nadawca dostaje oba, każdy osobnym --plik,
        w treści z origin/main — nie z drzewa roboczego, które może być starsze."""
        self.przygotuj_repo()
        (self.praca / "data" / "dom").mkdir(parents=True)
        (self.praca / "data" / "dom" / "powiadomienia.json").write_text("{}", encoding="utf-8")
        self.opublikuj(rosliny=[wpis(id="r")], dom=[wpis(id="d", telefony=["iphone"])])
        wynik, wywolania, temp = self.uruchom_krok()
        self.assertEqual(wynik.returncode, 0, wynik.stdout + wynik.stderr)
        r, d = temp / "rosliny" / "powiadomienia.json", temp / "dom" / "powiadomienia.json"
        self.assertEqual(wywolania, [
            ["pip", "install", "-q", "-r", "requirements-powiadomienia.txt"],
            ["python", "wyslij.py", "--plik", str(r), "--plik", str(d), "--przebieg", "123-1"]])
        self.assertEqual([w["id"] for w in json.loads(d.read_text(encoding="utf-8"))["historia"]], ["d"])
        self.assertEqual([w["id"] for w in wyslij.wpisy_przebiegu(r, "123-1")], ["r"])

    def test_brak_pliku_domu_pomija_go(self):
        """Do pierwszego zapisu dom.py na main nie ma data/dom/powiadomienia.json —
        rośliny i tak idą."""
        self.przygotuj_repo()
        self.opublikuj(rosliny=[wpis()])
        wynik, wywolania, temp = self.uruchom_krok()
        self.assertEqual(wynik.returncode, 0, wynik.stderr)
        self.assertIn("nie ma data/dom/powiadomienia.json", wynik.stdout)
        self.assertEqual(wywolania[-1], ["python", "wyslij.py", "--plik",
                                         str(temp / "rosliny" / "powiadomienia.json"),
                                         "--przebieg", "123-1"])

    def test_tylko_dom_ma_wpisy(self):
        """Pusty dla tego przebiegu plik roślin nie kończy kroku — liczy się suma."""
        self.przygotuj_repo()
        self.opublikuj(rosliny=[wpis(przebieg="122-1")], dom=[wpis(id="d")])
        wynik, wywolania, _ = self.uruchom_krok()
        self.assertEqual(wynik.returncode, 0, wynik.stderr)
        self.assertEqual([w[0] for w in wywolania], ["pip", "python"])

    def test_nic_do_wyslania_bez_pip_i_nadawcy(self):
        """Inny przebieg, na sucho, `telefony: []` — nic dla nikogo: krok kończy się na
        zielono, bez instalowania biblioteki i bez nadawcy. Stare jq liczyło `[]` jako
        wpis do wysłania."""
        self.przygotuj_repo()
        self.opublikuj(rosliny=[wpis(przebieg="122-1"), wpis(na_sucho=True),
                                wpis(id="nikt", telefony=[])],
                       dom=[wpis(telefony=[]), wpis(id="x", telefony=[])])
        wynik, wywolania, _ = self.uruchom_krok()
        self.assertEqual(wynik.returncode, 0, wynik.stderr)
        self.assertEqual(wywolania, [])
        self.assertIn("nie ma powiadomień do wysłania", wynik.stdout)

    def test_brak_obu_plikow(self):
        """STRAŻNIK (stary krok też tak kończył): pusty main — zielono, bez nadawcy."""
        self.przygotuj_repo()
        wynik, wywolania, _ = self.uruchom_krok()
        self.assertEqual(wynik.returncode, 0, wynik.stderr)
        self.assertEqual(wywolania, [])

    def test_zepsuty_plik_trafia_do_nadawcy(self):
        """Pliku, którego jq nie przeczyta, krok nie połyka po cichu ani nie wywraca się
        na nim (bash -e) — przekazuje go nadawcy, a ten zgłosi błąd i wyśle drugi plik."""
        self.przygotuj_repo()
        self.opublikuj(rosliny=[wpis()], dom="{nie json")
        wynik, wywolania, temp = self.uruchom_krok()
        self.assertEqual(wynik.returncode, 0, wynik.stderr)
        self.assertEqual(wywolania[-1][:6], ["python", "wyslij.py",
                                             "--plik", str(temp / "rosliny" / "powiadomienia.json"),
                                             "--plik", str(temp / "dom" / "powiadomienia.json")])


# Atrapa dla osobnego procesu: rozsiewa adres wszędzie, gdzie robią to biblioteki —
# logging (jak urllib3), warnings, print na stdout i stderr, treść wyjątku.
ATRAPA_PLIK = '''
import json, logging, os, sys, warnings

class WebPushException(Exception):
    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response

class _Odp:
    def __init__(self, kod, tekst):
        self.status_code, self.text = kod, tekst

class Vapid:
    @classmethod
    def from_string(cls, private_key):
        if os.environ.get("ATRAPA_WYWROTKA"):
            raise ValueError("zepsute: " + os.environ["PUSH_ANDROID"])
        return cls()

def webpush(subscription_info, **kw):
    adres = subscription_info["endpoint"]
    logging.getLogger("urllib3.connectionpool").warning("Retrying after %s", adres)
    warnings.warn("ostrzezenie " + adres)
    print("stdout " + adres)
    print("stderr " + adres, file=sys.stderr)
    if "apple" in adres:
        raise RuntimeError("nieznany blad dla " + adres)
    raise WebPushException("Push failed: 410 " + adres, response=_Odp(410, adres))
'''


class TestLogPubliczny(Baza):
    """Logi Actions są publiczne: cały stdout+stderr prawdziwego procesu, łącznie
    z tym, co wypisałby interpreter przy wywrotce."""

    def proces(self, **env_dodatkowe):
        atrapy = self.katalog / "atrapy"
        atrapy.mkdir(exist_ok=True)
        (atrapy / "pywebpush.py").write_text(ATRAPA_PLIK, encoding="utf-8")
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(atrapy),
               "PYTHONIOENCODING": "utf-8", **srodowisko(GH_TOKEN=None), **env_dodatkowe}
        return subprocess.run(
            [sys.executable, str(REPO / "wyslij.py"), "--plik", str(self.plik),
             "--przebieg", "123-1", "--strona", str(self.strona)],
            env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)

    def sprawdz_maski(self, wynik):
        linie = wynik.stdout.splitlines()
        maski = [l for l in linie if l.startswith("::add-mask::")]
        for tajne in (ANDROID, IPHONE, urlsplit(ANDROID).path, urlsplit(IPHONE).path,
                      SUB_ANDROID["keys"]["auth"], SUB_IPHONE["keys"]["auth"]):
            self.assertIn(f"::add-mask::{tajne}", maski)
        # maski przed czymkolwiek innym — runner maskuje dopiero od linii z poleceniem
        self.assertEqual(linie[:len(maski)], maski)

    def test_adres_nie_trafia_do_logu(self):
        wynik = self.proces()
        self.assertEqual(wynik.returncode, 1, wynik.stdout + wynik.stderr)   # RuntimeError → 1
        self.sprawdz_maski(wynik)
        self.bez_tajemnic(self.log_bez_masek(wynik.stdout + "\n" + wynik.stderr), "log procesu")
        self.assertIn("Android", wynik.stdout)
        self.assertIn("iPhone", wynik.stdout)

    def test_wywrotka_bez_adresu(self):
        """Wyjątek, który ucieka aż do main(), z całym sekretem w treści: kod 1, miejsce
        w kodzie w logu, treść nie."""
        wynik = self.proces(ATRAPA_WYWROTKA="1")
        self.assertEqual(wynik.returncode, 1)
        self.assertIn("ValueError", wynik.stdout)
        self.assertIn("wyslij.py:", wynik.stdout)
        self.bez_tajemnic(self.log_bez_masek(wynik.stdout + "\n" + wynik.stderr), "log procesu")


@unittest.skipUnless(importlib.util.find_spec("pywebpush"),
                     "pywebpush niezainstalowany (CI) — pomiar na prawdziwej bibliotece lokalnie")
class TestPrawdziwaBiblioteka(Baza):
    """Prawdziwy pywebpush/py_vapid/http_ece, tylko requests.post podmienione."""

    def setUp(self):
        super().setUp()
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        self.ec, self.serialization = ec, serialization
        self.wyslane, self.odpowiedzi = [], []
        self.odbiorcy = {}
        subskrypcje = {}
        for nazwa, adres in (("PUSH_ANDROID", ANDROID), ("PUSH_IPHONE", IPHONE)):
            klucz = ec.generate_private_key(ec.SECP256R1())
            auth = os.urandom(16)
            self.odbiorcy[adres] = (klucz, auth)
            subskrypcje[nazwa] = json.dumps(subskrypcja(adres, wyslij.do_base64url(self.surowy(klucz)),
                                                        wyslij.do_base64url(auth)))
        self.env = srodowisko(**subskrypcje)

        def post(url, **kw):
            self.wyslane.append((url, kw))
            wynik = self.odpowiedzi.pop(0) if self.odpowiedzi else Odpowiedz(201)
            if isinstance(wynik, BaseException):
                raise wynik
            return wynik

        lata = mock.patch("requests.post", post)
        lata.start()
        self.addCleanup(lata.stop)

    def surowy(self, klucz) -> bytes:
        return klucz.public_key().public_bytes(self.serialization.Encoding.X962,
                                               self.serialization.PublicFormat.UncompressedPoint)

    def uruchom_naprawde(self, *argv):
        out = io.StringIO()
        self.gh = AtrapaGh()
        argv = list(argv) or ["--plik", str(self.plik), "--przebieg", "123-1"]
        with redirect_stdout(out), redirect_stderr(out):
            kod = wyslij.main(argv, env=self.env, spij=self.spane.append, gh=self.gh,
                              strona=self.strona)
        return kod, out.getvalue()

    @staticmethod
    def jwt(naglowki) -> tuple[dict, str]:
        schemat, reszta = naglowki["authorization"].split(" ", 1)
        pola = dict(x.split("=", 1) for x in reszta.split(","))
        tresc = pola["t"].split(".")[1]
        return json.loads(wyslij.z_base64url(tresc)), pola["k"]

    def test_pomiar_pulapki_istnieja_w_tej_wersji(self):
        """POMIAR biblioteki, nie test nadawcy: gdyby po aktualizacji przestał przechodzić,
        pułapka zniknęła — obejście w wyslij.py nie szkodzi, ale docstring trzeba poprawić."""
        import pywebpush
        from py_vapid import VapidException
        sub_a, sub_i = (json.loads(self.env[k]) for k in ("PUSH_ANDROID", "PUSH_IPHONE"))
        wspolny = {"sub": wyslij.SUB}
        pywebpush.webpush(sub_a, data="x", vapid_private_key=PRYWATNY, vapid_claims=wspolny)
        pywebpush.webpush(sub_i, data="x", vapid_private_key=PRYWATNY, vapid_claims=wspolny)
        self.assertEqual(wspolny["aud"], "https://fcm.googleapis.com")      # zmiana w miejscu
        self.assertEqual(self.jwt(self.wyslane[1][1]["headers"])[0]["aud"],
                         "https://fcm.googleapis.com")                      # iPhone z cudzym aud
        self.assertEqual(self.wyslane[0][1]["headers"]["ttl"], "0")         # domyślne ttl
        self.assertIsNone(self.wyslane[0][1]["timeout"])                    # domyślnie bez limitu
        for zly_sub in ("https://bronek31.github.io/Smart-Home/", "https://bronek31.github.io/"):
            with self.assertRaises(VapidException):
                pywebpush.webpush(sub_a, data="x", vapid_private_key=PRYWATNY,
                                  vapid_claims={"sub": zly_sub})

    def test_wyliczony_publiczny_to_klucz_podpisu(self):
        """Klucz, z którym porównujemy stronę, to bajt w bajt klucz, którym py_vapid
        podpisuje — dla par z WebCrypto i dla losowych kluczy z cryptography."""
        from py_vapid import Vapid
        klucze = [d for d, _ in PARY_WEBCRYPTO]
        for _ in range(20):
            liczba = self.ec.generate_private_key(self.ec.SECP256R1()).private_numbers().private_value
            klucze.append(wyslij.do_base64url(liczba.to_bytes(32, "big")))
        for d in klucze:
            with self.subTest(d=d[:6]):
                v = Vapid.from_string(d)
                pub = v.public_key.public_bytes(self.serialization.Encoding.X962,
                                                self.serialization.PublicFormat.UncompressedPoint)
                self.assertEqual(wyslij.publiczny_z_prywatnego(d), wyslij.do_base64url(pub))

    def test_nadawca_na_prawdziwej_bibliotece(self):
        """Całość: nagłówki, token VAPID z właściwym aud dla każdego telefonu, podpis
        weryfikowalny kluczem ze strony, treść odszyfrowana kluczem telefonu."""
        import http_ece
        from py_vapid import Vapid
        teraz = time.time()
        kod, log = self.uruchom_naprawde()
        self.assertEqual(kod, 0, log)
        self.assertEqual([u for u, _ in self.wyslane], [ANDROID, IPHONE])
        for url, kw in self.wyslane:
            with self.subTest(url=urlsplit(url).netloc):
                naglowki = kw["headers"]
                self.assertEqual(naglowki["ttl"], "43200")
                self.assertEqual(naglowki["urgency"], "normal")
                self.assertEqual(naglowki["topic"], "podlej")
                self.assertEqual(naglowki["content-encoding"], "aes128gcm")
                self.assertEqual(kw["timeout"], wyslij.LIMIT_SIECI_S)
                roszczenia, k = self.jwt(naglowki)
                self.assertEqual(roszczenia["aud"], f"https://{urlsplit(url).netloc}")
                self.assertEqual(roszczenia["sub"], "https://bronek31.github.io")
                self.assertLess(abs(roszczenia["exp"] - (teraz + 12 * 3600)), 120)
                self.assertEqual(k, PUBLICZNY)
                self.assertTrue(Vapid.verify(naglowki["authorization"]))
                klucz, auth = self.odbiorcy[url]
                jawne = http_ece.decrypt(kw["data"], private_key=klucz, auth_secret=auth,
                                         version="aes128gcm")
                self.assertEqual(json.loads(jawne.decode("utf-8"))["title"], "Podlej: azalia")

    def test_filtr_telefonow_na_prawdziwej_bibliotece(self):
        """Wpis tylko dla iPhone'a: jedno żądanie, na adres Apple, z jego `aud` — filtr
        nie psuje świeżego słownika roszczeń ani kolejności telefonów."""
        self.ustaw_historie([wpis(telefony=["iphone"])])
        kod, log = self.uruchom_naprawde()
        self.assertEqual(kod, 0, log)
        self.assertEqual([u for u, _ in self.wyslane], [IPHONE])
        self.assertEqual(self.jwt(self.wyslane[0][1]["headers"])[0]["aud"],
                         "https://web.push.apple.com")
        self.assertIn("Android: nic w tym przebiegu.", log)

    def test_granica_rozmiaru(self):
        """Najdłuższa treść, jaką przepuści tresc_push(), mieści się w 4096 B ciała."""
        self.ustaw_historie([wpis(tresc="Źdźbło " * 1000)])
        kod, log = self.uruchom_naprawde()
        self.assertEqual(kod, 0, log)
        for _, kw in self.wyslane:
            self.assertLessEqual(len(kw["data"]), 4096)

    def test_410_i_blad_sieci_z_prawdziwymi_wyjatkami(self):
        """Klasyfikacja działa na prawdziwym WebPushException (kod z response) i na
        prawdziwym wyjątku requests; adres nie wycieka ani do logu, ani do zgłoszenia."""
        siec = requests.ConnectionError(f"Max retries exceeded with url: {urlsplit(IPHONE).path}")
        self.odpowiedzi = [Odpowiedz(410, f"expired {ANDROID}"), siec, siec, siec]
        kod, log = self.uruchom_naprawde()
        self.assertEqual(kod, 0, log)
        self.assertIn("wygasła (410)", log)
        self.assertIn("ConnectionError", log)
        self.assertEqual(self.spane, list(wyslij.PRZERWY_S))
        self.bez_tajemnic(self.log_bez_masek(log), "log")
        self.bez_tajemnic(self.gh.tresci(), "zgłoszenie")


if __name__ == "__main__":
    unittest.main()
