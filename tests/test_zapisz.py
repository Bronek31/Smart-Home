"""Zapis odczytów do repozytorium — zachowanie przy wyścigu dwóch przebiegów.

Kolektor rusza z harmonogramu i z pusha na main, więc dwie jego kopie potrafią
działać naraz. 15.08 tak się stało: przegrany dostał odmowę pusha, spróbował
`pull --rebase` i stanął na konflikcie w data/index.json, bo oba przebiegi
przepisują ten sam plik. Przebieg poszedł na czerwono.

Tutaj odtwarzamy ten wyścig na prawdziwym repozytorium git w katalogu tymczasowym.
Rolę fetch.py gra podstawka, która robi to samo co on w istotnym punkcie: dokłada
swój wiersz do tego, co zastanie na dysku, i przepisuje plik ze znacznikiem czasu.
"""

import os
import shutil
import subprocess
import tempfile
import unittest

KORZEN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZAPISZ = os.path.join(KORZEN, "zapisz.sh")

# Podstawka za fetch.py: dokłada wiersz do istniejącego pliku (tak jak kolektor dokłada
# swoje okno do zebranych już odczytów) i przepisuje manifest z własnym znacznikiem —
# to ten drugi plik powodował konflikt.
PODSTAWKA = """#!/bin/sh
set -e
mkdir -p data
echo "$WPIS" >> data/odczyty.csv
printf '{"updated":"%s"}\\n' "$WPIS" > data/index.json
"""


def git(*args, cwd, **kw):
    return subprocess.run(("git",) + args, cwd=cwd, check=True,
                          capture_output=True, text=True, **kw)


class TestZapisz(unittest.TestCase):
    def setUp(self):
        self.baza = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.baza, ignore_errors=True)
        self.zdalne = os.path.join(self.baza, "zdalne.git")
        subprocess.run(["git", "init", "--bare", "-b", "main", self.zdalne],
                       check=True, capture_output=True)
        # pierwszy commit, żeby gałąź main w ogóle istniała
        zasiew = self.klon("zasiew")
        os.makedirs(os.path.join(zasiew, "data"))
        self.pisz(zasiew, "data/odczyty.csv", "start\n")
        self.pisz(zasiew, "data/index.json", '{"updated":"start"}\n')
        git("add", "-A", cwd=zasiew)
        git("commit", "-qm", "start", cwd=zasiew)
        git("push", "-q", "origin", "main", cwd=zasiew)

        self.podstawka = os.path.join(self.baza, "pobierz.sh")
        self.pisz(self.baza, "pobierz.sh", PODSTAWKA)

    def klon(self, nazwa):
        sciezka = os.path.join(self.baza, nazwa)
        subprocess.run(["git", "clone", "-q", self.zdalne, sciezka],
                       check=True, capture_output=True)
        git("config", "user.name", "test", cwd=sciezka)
        git("config", "user.email", "test@example.com", cwd=sciezka)
        return sciezka

    @staticmethod
    def pisz(katalog, nazwa, tresc):
        with open(os.path.join(katalog, nazwa), "w", encoding="utf-8") as f:
            f.write(tresc)

    def uruchom(self, katalog, wpis, proby="3"):
        srodowisko = dict(os.environ,
                          KOMENDA_POBIERZ=f"sh {self.podstawka}",
                          WPIS=wpis, PROBY=proby, GALAZ="main")
        return subprocess.run(["sh", ZAPISZ], cwd=katalog, env=srodowisko,
                              capture_output=True, text=True)

    def na_zdalnym(self, plik):
        return git("show", f"main:{plik}", cwd=self.zdalne).stdout

    # ------------------------------------------------------------------

    def test_zwykly_zapis_idzie_za_pierwszym_razem(self):
        nasz = self.klon("nasz")
        wynik = self.uruchom(nasz, "nasz-odczyt")
        self.assertEqual(wynik.returncode, 0, wynik.stderr)
        self.assertIn("nasz-odczyt", self.na_zdalnym("data/odczyty.csv"))

    def test_brak_zmian_nie_robi_pustego_commita(self):
        nasz = self.klon("nasz")
        # podstawka, która niczego nie zmienia
        self.pisz(self.baza, "pobierz.sh", "#!/bin/sh\nexit 0\n")
        wynik = self.uruchom(nasz, "nieważne")
        self.assertEqual(wynik.returncode, 0, wynik.stderr)
        self.assertIn("Brak nowych odczytów", wynik.stdout)
        self.assertEqual(
            git("rev-list", "--count", "main", cwd=self.zdalne).stdout.strip(), "1")

    def test_przegrany_wyscig_nie_gubi_ani_naszych_ani_cudzych_odczytow(self):
        """Sedno: to jest przebieg, który 15.08 poszedł na czerwono."""
        nasz = self.klon("nasz")
        # rywal zapisuje, gdy my mamy już swoje drzewo wczytane — dokładnie jak dwa
        # przebiegi kolektora, które wystartowały w odstępie czterech sekund
        rywal = self.klon("rywal")
        self.assertEqual(self.uruchom(rywal, "rywal-odczyt").returncode, 0)

        wynik = self.uruchom(nasz, "nasz-odczyt")
        self.assertEqual(wynik.returncode, 0, wynik.stdout + wynik.stderr)
        self.assertIn("Push odrzucony (próba 1)", wynik.stdout)

        odczyty = self.na_zdalnym("data/odczyty.csv")
        self.assertIn("rywal-odczyt", odczyty, "zgubiliśmy odczyty rywala")
        self.assertIn("nasz-odczyt", odczyty, "zgubiliśmy własne odczyty")
        # i żadnego śladu po konflikcie
        self.assertNotIn("<<<<<<<", odczyty)
        self.assertNotIn("<<<<<<<", self.na_zdalnym("data/index.json"))

    def test_konflikt_w_manifescie_nie_zatrzymuje_zapisu(self):
        """index.json przepisują oba przebiegi w całości — to on wywracał rebase."""
        nasz = self.klon("nasz")
        rywal = self.klon("rywal")
        self.uruchom(rywal, "rywal-odczyt")
        wynik = self.uruchom(nasz, "nasz-odczyt")
        self.assertEqual(wynik.returncode, 0, wynik.stdout + wynik.stderr)
        # zwycięzcą manifestu jest ten, kto pisał ostatni — bo liczył na cudzym drzewie
        self.assertIn("nasz-odczyt", self.na_zdalnym("data/index.json"))

    def test_gdy_ktos_wygrywa_bez_konca_przebieg_konczy_sie_bledem(self):
        # PROBY=1: pierwszy push odrzucony i nie ma już kolejnego podejścia
        nasz = self.klon("nasz")
        rywal = self.klon("rywal")
        self.uruchom(rywal, "rywal-odczyt")
        wynik = self.uruchom(nasz, "nasz-odczyt", proby="1")
        self.assertEqual(wynik.returncode, 1)
        self.assertIn("Nie udało się zapisać odczytów", wynik.stderr)

    def test_bledne_pobranie_przerywa_bez_zapisu(self):
        nasz = self.klon("nasz")
        self.pisz(self.baza, "pobierz.sh", "#!/bin/sh\necho awaria >&2\nexit 3\n")
        wynik = self.uruchom(nasz, "nieważne")
        self.assertNotEqual(wynik.returncode, 0)
        self.assertEqual(
            git("rev-list", "--count", "main", cwd=self.zdalne).stdout.strip(), "1")


if __name__ == "__main__":
    unittest.main()
