#!/usr/bin/env python3
"""Nadawca powiadomień (wyslij.py) — bez prawdziwej sieci.

Testy jednostkowe w CI mają tylko `requests`, więc pywebpush gra tu atrapa modułu
podstawiona w sys.modules. Atrapa zachowuje się jak pywebpush 2.5.0 w tym, co ma
znaczenie dla pułapek: dopisuje `aud` i `exp` do podanego słownika w miejscu i rzuca
WebPushException z odpowiedzią przy kodzie > 202. Że prawdziwa biblioteka naprawdę tak
robi, sprawdza klasa TestPrawdziwaBiblioteka na końcu — w CI pominięta, lokalnie:

    python3 -m venv /tmp/venv-push && /tmp/venv-push/bin/pip install -r requirements-powiadomienia.txt
    /tmp/venv-push/bin/python -m unittest discover -s tests -p test_wyslij.py -v

wyslij.py jest nowy, więc wersja sprzed zmiany nie przechodzi żadnego testu; każdy test
niżej odrzuca też konkretną, łatwą do popełnienia pomyłkę — jaką, mówi jego opis.
Jedyny strażnik (przechodzi także bez stałej na stronie) jest tak podpisany.
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
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

WPIS = {"id": "20261009T140112Z-podlej", "ts": "2026-10-09T14:01:12Z", "przebieg": "123-1",
        "regula": "podlej", "rosliny": ["Azalia"], "tytul": "Podlej: azalia",
        "tresc": "Azalia: gleba 41% (podlewaj przy ok. 45%).", "tag": "podlej",
        "url": "rosliny.html#roslina=Azalia", "na_sucho": False}


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
        self.strona = self.katalog / "rosliny.html"
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

    def test_strona_w_repozytorium_ma_czytelna_stala(self):
        """STRAŻNIK: przechodzi też dziś, gdy rosliny.html stałej jeszcze nie ma. Pilnuje,
        żeby po jej dopisaniu zapis dał się przeczytać nadawcy (jedna linia, apostrofy,
        średnik; pusta albo klucz 65 B) — inaczej każdy przebieg kończyłby się błędem."""
        html = (REPO / "rosliny.html").read_text(encoding="utf-8")
        if "VAPID_PUBLICZNY" in html:
            wyslij.klucz_ze_strony(REPO / "rosliny.html")


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

    def test_najwyzej_trzy_wpisy_na_przebieg(self):
        """Błąd w regułach nie zasypie telefonów: z pięciu wpisów idą trzy, reszta do
        zgłoszenia — ale kolektor zostaje zielony."""
        self.ustaw_historie([wpis(id=str(i)) for i in range(5)])
        kod, _, atrapa = self.uruchom()
        self.assertEqual(kod, 0)
        self.assertEqual(len(atrapa.wywolania), 3 * 2)
        self.assertIn("Reguły", self.gh.tresci())


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
                                            "tag": "podlej", "url": "rosliny.html#roslina=Azalia",
                                            "id": "20261009T140112Z-podlej"})

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
        self.assertEqual(tresc["url"], "rosliny.html")

    def test_blad_w_trybie_testowym_na_czerwono(self):
        """Martwa subskrypcja przy ręcznym teście to czerwony przebieg, nie tylko zgłoszenie."""
        kod, log, _ = self.uruchom("--test", atrapa=zrob_atrape({IPHONE: [410]}))
        self.assertEqual(kod, 1)
        self.assertIn("::error::iPhone", log)

    def test_bez_test_potrzebny_plik_i_przebieg(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as kontekst:
            wyslij.main(["--przebieg", "1-1"], env={}, gh=AtrapaGh())
        self.assertEqual(kontekst.exception.code, 2)


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
