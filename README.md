# Termohigrograf

Historia odczytów z czujników Zigbee podpiętych do Smart Life — bez kupowania
sprzętu i bez serwera chodzącego w domu. GitHub Actions odpytuje chmurę Tuya
co godzinę, dopisuje odczyty do plików CSV w repozytorium, a GitHub Pages
wystawia z tego wykres pod adresem, który otworzysz na telefonie.

```
  czujniki Zigbee ──► bramka ──► chmura Tuya (trzyma 7 dni)
                                        │
                          GitHub Actions │ co godzinę pobiera okno 3 dni
                                        ▼
                              data/RRRR-MM.csv w repo
                                        │
                                        ▼
                            GitHub Pages ──► wykres
```

**Dlaczego to działa bez serwera 24/7.** Tuya przechowuje logi odczytów przez
7 dni. Każdy przebieg pobiera całe to okno i dokłada tylko rekordy, których
jeszcze nie ma. Nieudany albo pominięty przebieg nic nie kosztuje — następny
nadrobi zaległości. Dziura w danych powstaje dopiero wtedy, gdy kolektor milczy
dłużej niż tydzień.

**Koszt:** zero. Publiczne repozytorium ma darmowe minuty Actions bez limitu
i darmowe Pages.

---

## Zanim zaczniesz

- Konto Smart Life z czujnikami, które już działają w aplikacji
- Konto na GitHubie
- Około 20 minut

Python lokalnie przyda się tylko do diagnozy — cała reszta dzieje się na serwerach GitHuba.

---

## Krok 1 — projekt w chmurze Tuya

### 1.1 Załóż konto dewelopera

Wejdź na [iot.tuya.com](https://iot.tuya.com) i zarejestruj się. To osobne konto
niż Smart Life — połączysz je za chwilę.

### 1.2 Utwórz projekt

**Cloud → Development → Create Cloud Project.** Wypełnij:

| Pole | Co wybrać |
|---|---|
| Project Name | cokolwiek, np. `termohigrograf` |
| Industry | Smart Home |
| Development Method | Smart Home |
| **Data Center** | **Central Europe** |

> **To jedyna rzecz, której nie zgadnę za ciebie.** Data center musi zgadzać się
> z tym, gdzie mieszka twoje konto Smart Life. Dla Polski to prawie zawsze
> **Central Europe**, ale jeśli w kroku 1.3 lista urządzeń wyjdzie pusta, to
> znaczy, że trafiłeś w złe. Możesz wtedy dołożyć kolejne data center w
> ustawieniach projektu albo założyć projekt od nowa.
>
> **Gdzie sprawdzić, co masz teraz:** otwórz projekt, zakładka **Overview** —
> pozycja *Data Center*. Widać to też jako selektor w prawym górnym rogu listy
> urządzeń.

Po utworzeniu projektu Tuya poprosi o autoryzację usług API. Zostaw domyślne.

### 1.3 Podepnij konto Smart Life

W projekcie: **Devices → Link App Account → Add App Account**. Pojawi się kod QR.

W telefonie otwórz **Smart Life → zakładka Ja → ikona skanowania w prawym górnym
rogu**, zeskanuj kod i potwierdź. Wróć do przeglądarki — w zakładce
**All Devices** powinny być twoje cztery czujniki i bramka.

Jeśli lista jest pusta, wróć do uwagi o data center powyżej.

### 1.4 Skopiuj klucze

**Overview → Authorization Key.** Potrzebujesz dwóch wartości:

- **Access ID / Client ID** → trafi do sekretu `TUYA_CLIENT_ID`
- **Access Secret / Client Secret** → trafi do sekretu `TUYA_CLIENT_SECRET`

Sekret pokazuje się po kliknięciu ikony oka. Przepisz go w całości — najczęstszy
błąd na tym etapie to ucięty znak i potem kod `1004` (zły podpis).

### 1.5 Sprawdź, czy masz IoT Core

Zakładka **Service API** — na liście musi być **IoT Core**. To z niego pochodzi
darmowy dostęp do 7 dni logów. Jeśli go nie ma, kliknij **Go to Authorize**
i dodaj.

---

## Krok 2 — repozytorium

Utwórz nowe repozytorium na GitHubie. **Wybierz publiczne** — przy prywatnym
GitHub Pages wymaga płatnego planu (patrz sekcja *Prywatne repozytorium* niżej).

Wgraj do niego pliki z tej paczki, zachowując strukturę:

```
├── fetch.py                       kolektor
├── requirements.txt
├── index.html                     wykres
├── data/                          tu będą lądować odczyty
└── .github/workflows/zbieraj.yml  harmonogram
```

Najprościej przez przeglądarkę: **Add file → Upload files**, przeciągnij
wszystko naraz. Katalog `.github` musi zachować nazwę razem z kropką.

---

## Krok 3 — wstaw klucze jako sekrety

**Settings → Secrets and variables → Actions → New repository secret.**
Dodaj dwa:

| Nazwa | Wartość |
|---|---|
| `TUYA_CLIENT_ID` | Access ID z kroku 1.4 |
| `TUYA_CLIENT_SECRET` | Access Secret z kroku 1.4 |

Sekrety nie są widoczne w logach ani dla nikogo, kto ogląda repozytorium —
także przy repo publicznym.

Jeśli twój projekt Tuya **nie** jest w Central Europe, otwórz
`.github/workflows/zbieraj.yml` i zmień `TUYA_REGION` na właściwy kod.
Tabela kodów jest w komentarzu w tym pliku.

---

## Krok 4 — pierwszy przebieg

**Actions → Zbieranie odczytów → Run workflow.**

Za minutę w logu kroku *Pobierz odczyty z chmury Tuya* powinno być coś takiego:

```
Salon: 412 odczytów z ostatnich 7 dni
Sypialnia: 388 odczytów z ostatnich 7 dni
Kuchnia: 401 odczytów z ostatnich 7 dni
Piwnica: 355 odczytów z ostatnich 7 dni

Dopisano 1556 nowych odczytów (0 już było).
```

W katalogu `data/` pojawi się plik `RRRR-MM.csv` i `index.json`.

Jeśli coś poszło nie tak, skrypt wypisuje kod błędu Tuya razem z podpowiedzią —
tabela na końcu tej instrukcji tłumaczy, co z tym zrobić.

> **Ile odczytów to normalne?** Bardzo różnie. Czujniki Zigbee raportują przy
> zmianie o mniej więcej 0,5 °C albo 3–6% wilgotności, a nie w stałym rytmie.
> W stabilnym pokoju potrafi to być kilkanaście wpisów na tydzień, w kuchni czy
> łazience kilkaset. Jeden odczyt to jeden wpis na pole, więc czujnik mierzący
> temperaturę i wilgotność generuje dwa wpisy naraz. Jeśli któryś czujnik ma
> podejrzanie mało, sprawdź w Smart Life, czy nie zgłasza słabej baterii albo
> nie stoi za daleko od bramki.

---

## Krok 5 — włącz stronę

**Settings → Pages → Source: Deploy from a branch → Branch: `main` / `(root)` → Save.**

Po dwóch, trzech minutach wykres jest pod adresem:

```
https://TWOJA-NAZWA.github.io/NAZWA-REPO/
```

Otwórz go na telefonie i dodaj do ekranu głównego — w Safari przez *Udostępnij →
Do ekranu początkowego*, w Chrome przez menu → *Dodaj do ekranu głównego*.
Wygląda wtedy jak zwykła aplikacja.

---

## Diagnostyka lokalna

Kiedy coś nie gra, najszybciej sprawdzisz to u siebie:

```bash
pip install requests

export TUYA_CLIENT_ID='...'
export TUYA_CLIENT_SECRET='...'
export TUYA_REGION='eu'

python fetch.py --discover     # co widać na koncie
python fetch.py --dry-run      # pobierz, ale nie zapisuj
python fetch.py --days 1       # węższe okno, szybciej
```

`--discover` wypisuje każde urządzenie razem z jego polami odczytu i skalą:

```
  bfa1b2c3d4e5f6a7b8   Salon
      kategoria: wsdcg   rola: czujnik
      pole: va_temperature (temp, °C, scale=1)
      pole: va_humidity (hum, %, scale=0)
```

`scale=1` znaczy, że czujnik raportuje `235` dla 23,5 °C. Skrypt czyta tę skalę
z API i przelicza sam — nie musisz nic ustawiać.

---

## Co trzeba robić później

**Raz na pół roku: przedłużenie dostępu do API.** Trial IoT Core wygasa.
Dostaniesz wtedy kod błędu `28841002`. Wejdź na iot.tuya.com → **Cloud →
Development**, otwórz projekt i złóż wniosek o przedłużenie. Zatwierdzają
w jeden, dwa dni robocze. Nic w tym czasie nie tracisz, jeśli zmieścisz się
w oknie 7 dni.

**Uwaga na wyłączony harmonogram.** GitHub wyłącza zaplanowane workflow po
60 dniach bezczynności w repozytorium, a commity robione przez bota często się
do tego nie liczą. Przyjdzie mail — kliknij *Enable workflow* i wszystko wraca.
Póki zrobisz to w ciągu tygodnia, nie tracisz żadnych danych.

**Miejsce.** Cztery czujniki to jakieś 1500 odczytów dziennie, czyli około
10 MB rocznie w CSV. Git ładnie to kompresuje. Nie ma się czym przejmować.

---

## Wyczyszczenie danych i start od nowa

Samo skasowanie plików nie wystarczy — przy następnym przebiegu okno kilkudniowe
pobierze te same odczyty z chmury i wpisze je z powrotem. Potrzebna jest granica.

W `.github/workflows/zbieraj.yml` ustaw moment, od którego liczysz:

```yaml
TUYA_SINCE: '2026-08-12T20:00+02:00'
```

Zapis `+02:00` to czas polski latem, zimą `+01:00`. Możesz też podać samą datę
(`2026-08-13`) — wtedy liczy się północ UTC.

Kolejność ma znaczenie: **najpierw zatwierdź granicę**, dopiero potem skasuj
`data/*.csv` i `data/index.json`. Odwrotnie skrypt zdąży wpisać dane z powrotem.

Operacja jest odwracalna przez tydzień: dopóki skasowane odczyty mieszczą się
w oknie Tuya, wyczyszczenie `TUYA_SINCE` z powrotem na `''` je przywróci.

---

## Prywatne repozytorium

GitHub Pages przy prywatnym repo wymaga planu Pro. Jeśli nie chcesz publikować
danych, zostaw repo prywatne i oglądaj wykres lokalnie:

```bash
git clone https://github.com/TWOJA-NAZWA/NAZWA-REPO.git
cd NAZWA-REPO
python -m http.server 8000
```

i otwórz `http://localhost:8000`. Samo otwarcie `index.html` podwójnym
kliknięciem nie zadziała — przeglądarka zablokuje wczytanie plików CSV.

Actions na prywatnym repo mają 2000 minut miesięcznie w darmowym planie.
Ten workflow zużywa jakieś 60.

Przy repo publicznym w plikach CSV widać temperaturę, wilgotność i nazwy
czujników — czyli też nazwy pokoi, jeśli tak je nazwałeś w Smart Life. Same
identyfikatory urządzeń bez klucza są bezużyteczne, ale nazwy warto przemyśleć.

---

## Kiedy coś nie działa

| Objaw | Co się dzieje |
|---|---|
| kod `1004` | Zły podpis. Access Secret przepisany z błędem albo z ucięciem. |
| kod `1106` | Brak uprawnień do urządzenia. Sprawdź, czy konto Smart Life jest wciąż podpięte w *Devices → Link App Account*. |
| kod `1114` lub `2007` | Złe data center. `TUYA_REGION` nie zgadza się z projektem — porównaj z zakładką *Overview*. |
| kod `28841002` | Wygasł trial IoT Core. Złóż wniosek o przedłużenie. |
| `limit zapytań Tuya, czekam N s` | Normalne przy pierwszym przebiegu. Skrypt sam odczeka i ponowi. Jeśli powtarza się w kółko, zwiększ `TUYA_MIN_GAP` w workflow do `2.5`. |
| bateria pokazuje `niski` | Wymień baterię. Słabnące ogniwo to najczęstsza przyczyna gubionych raportów, zanim czujnik zniknie zupełnie. |
| `pominięty — Endpoint logów odmówił` | Ten czujnik nie wszedł tym razem, reszta owszem, i dane zostały zapisane. Następny przebieg go nadrobi. |
| `Żadne urządzenie nie zgłosiło temperatury ani wilgotności` | Odpal `--discover`. Prawdopodobnie widać samą bramkę, bo konto podpięło się do złego data center. |
| Przebieg zielony, ale zero nowych odczytów | Normalne, jeśli czujniki nic nie zaraportowały od ostatniego razu. Zigbee raportuje przy zmianie o ~0,5 °C, nie w stałym rytmie. |
| Push kończy się błędem 403 | **Settings → Actions → General → Workflow permissions → Read and write permissions.** |
| Strona pokazuje „Nie ma jeszcze żadnych odczytów" | Pages wystawiło repo, zanim workflow zdążył coś zapisać. Odpal workflow ręcznie i odśwież za dwie minuty. |

---

## Czego to nie zrobi

**Siedem dni to twardy limit.** Jeśli kolektor przestanie działać i zauważysz to
po dwóch tygodniach, ten tydzień przepadł bezpowrotnie. Tuya go nie odda.

**Rozdzielczość to nie twoja decyzja.** W bazie ląduje dokładnie to, co czujnik
wysłał. Czujniki Zigbee raportują przy zmianie albo co jakiś czas — nie da się
poprosić o odczyt co minutę wstecz.

**Harmonogram GitHuba jest orientacyjny.** Przebiegi potrafią spóźnić się
o kilkadziesiąt minut albo zostać pominięte przy dużym obciążeniu. Dlatego
kolektor chodzi co godzinę i pobiera okno kilkudniowe — każdy przebieg nadrabia
wszystkie poprzednie, więc pojedyncze wypadnięcie nic nie kosztuje.

**Częstsze odpytywanie nie daje więcej danych.** Rozdzielczość zależy wyłącznie
od tego, jak często czujnik raportuje do chmury. Przebiegi co godzinę zmieniają
tylko to, jak świeży jest wykres i jak szybko zauważysz awarię.

---

## Struktura danych

`data/RRRR-MM.csv` — jeden plik na miesiąc:

```csv
ts,device_id,code,value
2026-08-12T14:31:07Z,bfa1b2c3d4e5f6a7b8,va_temperature,22.4
2026-08-12T14:31:07Z,bfa1b2c3d4e5f6a7b8,va_humidity,48
```

Czas w UTC, wartości już przeliczone przez skalę. Klucz unikalności to trójka
`ts + device_id + code` — na tym opiera się pomijanie duplikatów.

`data/index.json` — spis miesięcy i czujników, z którego korzysta strona.
Generowany automatycznie przy każdym przebiegu.

Format jest na tyle zwyczajny, że wciągniesz go do Excela, pandas albo
zaimportujesz do czegokolwiek innego, gdyby ten projekt kiedyś przestał ci
wystarczać.
