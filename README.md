# Smart Home

Temperatura i wilgotność z czterech czujników Zigbee w pokojach i trzech w doniczkach
(Tuya / Smart Life), zbierane za darmo przez GitHub Actions. Aplikacja na GitHub Pages
pokazuje dom i rośliny, a powiadomienia („przewietrz”, „zamknij okno?”, „podlej”,
„przestaw”) przychodzą na Androida i iPhone'a.

Smart Life nie przechowuje historii — ten projekt to nadrabia: raz na godzinę
pobiera logi z chmury Tuya, dopisuje je do plików CSV w repozytorium, liczy z nich
reguły i wysyła powiadomienia. Żadnego serwera, bazy danych ani Raspberry Pi.

**Aplikacja:** https://bronek31.github.io/Smart-Home/

---

## Jak to działa

```
czujniki Zigbee → bramka → chmura Tuya → fetch.py (GitHub Actions, co godzinę)
                                            ↓
   pokoje      data/*.csv, data/dzienne.csv, data/index.json, data/pogoda.json
   dom.py      data/dom/stan.json, data/dom/powiadomienia.json
   rosliny.py  data/rosliny/*.csv, data/rosliny/stan.json, data/rosliny/powiadomienia.json
                                            ↓  commit na main (zapisz.sh)
            index.html (GitHub Pages)            wyslij.py → Web Push → Android, iPhone
```

Tuya udostępnia **7 dni logów wstecz**. Każdy przebieg pobiera odcinek od miejsca,
w którym skończył poprzedni udany (`pobrane_do` w manifeście), z sześciogodzinną
zakładką na spóźnione odczyty, i dokłada tylko to, czego jeszcze nie ma. Pominięty
albo nieudany przebieg niczego nie kosztuje — kursor stoi, więc następny nadrabia
zaległości. Dziura w danych powstaje
dopiero wtedy, gdy kolektor milczy dłużej niż tydzień. Właśnie po to jest watchdog.

Czujniki raportują **przy zmianie temperatury o 0,5 °C** albo **raz na godzinę**,
cokolwiek wypadnie pierwsze. Odstępy 60-minutowe to norma, nie awaria.

Poza czujnikami klimatu kolektor zbiera też **włączniki urządzeń** — z klimatyzatora
w salonie bierze wyłącznie to, kiedy chodził. Aplikacja tego nie pokazuje; wiersze
zostają w CSV, gdyby urządzenie wróciło do łask.

---

## Pliki

| Plik | Do czego |
|---|---|
| `fetch.py` | kolektor: pobiera logi z Tuya, pogodę i smog z Open-Meteo, przelicza agregaty, woła tor roślin i reguły domu |
| `dom.py` | reguły domu bez sieci i plików: przewietrz, przed snem, zamknij okno, czujniki w pokojach — stan dla strony i plan powiadomień |
| `rosliny.py` | obliczenia dla doniczek bez sieci i plików: przerzedzanie, światło dobowe i jego ocena, podlania, progi, werdykt, plan powiadomień |
| `telefony.py` | ustawienia każdego telefonu (które reguły, cisza nocna) i kolejka odłożonych na koniec jego ciszy — wspólne dla `dom.py` i `rosliny.py` |
| `wyslij.py` | nadawca Web Push: z obu plików powiadomień wysyła tylko wpisy tego przebiegu, każdemu telefonowi tylko jego; sekrety `VAPID_KLUCZ_PRYWATNY`, `PUSH_ANDROID`, `PUSH_IPHONE` |
| `requirements-powiadomienia.txt` | biblioteki nadawcy (pywebpush), instalowane tylko w kroku wysyłki |
| `index.html` | cała aplikacja: zakładki Dom · Rośliny · Historia · Powiadomienia, strony pokoi i roślin, obsługa powiadomień. Jeden plik, bez budowania i bez bibliotek z CDN |
| `rosliny.html` | tylko przekierowanie starych adresów (`rosliny.html#roslina=…` z dawnych powiadomień i zakładek) na `./#…` |
| `pokoje.json` | pokoje po identyfikatorze czujnika: adres (`slug`), nazwa, odmiany do zdań, strona świata okna, wywiew. Ręczna lista; czyta ją strona i `dom.py` |
| `zapisz.sh` | pobiera odczyty i zapisuje je na gałąź, przeżywając wyścig dwóch przebiegów |
| `artefakty.json` | znane artefakty: przedziały, w których czujnik mierzył coś innego niż pokój. Ręczna lista |
| `rosliny.json` | czujniki w doniczkach: identyfikator, roślina, gatunek, kody pól Tuya, odczyt „sucho” i data wbicia. Ręczna lista |
| `manifest.json`, `sw.js`, `ikona*` | instalacja na ekranie głównym telefonu, tryb offline, powiadomienia (push, kliknięcie, licznik na ikonie) |
| `.nojekyll` | pusty plik, który mówi Pages: serwuj repozytorium jak jest, bez Jekylla |
| `KONTEKST.md` | notatka przekazania: dlaczego jest tak, jak jest, i na co uważać przy dalszej pracy |
| `TODO.md` | pomysły na później i te świadomie odrzucone, wraz z powodami; terminy właściciela |
| `ROSLINY.md` | czujniki w doniczkach i powiadomienia: plan, pomiary, reguły |
| `ROSLINY-INSTRUKCJA.md` | czynności właściciela krok po kroku: czujniki, podpięcie telefonów, klucz do ustawień |
| `tests/` | testy kolektora, reguł, nadawcy i aplikacji; nie trafiają na Pages, bo Pages serwuje tylko katalog główny |
| `.githooks/pre-push` | nie przepuszcza pusha, dopóki testy nie przejdą |
| `.github/workflows/zbieraj.yml` | zbieranie i wysyłka powiadomień; zapasowy harmonogram co godzinę o :19, właściwym zegarem jest zewnętrzny cron co godzinę (patrz „Kolektor co godzinę”) |
| `.github/workflows/watchdog.yml` | co 6 godzin sprawdza, czy kolektor żyje i czy czujniki (także w doniczkach) nie wołają o rękę |
| `.github/workflows/powiadomienie-testowe.yml` | jedno powiadomienie „Powiadomienia działają” na każdy podpięty telefon. Na żądanie i po zmianie swojego pliku na `main` |
| `.github/workflows/odkryj.yml` | wypisuje urządzenia w Tuya i ich pola, a dla nowych także bieżące wartości i liczbę wpisów z ostatniej godziny (ok. 20 zapytań). Na żądanie i sam po każdej zmianie swojego pliku na `main` |
| `.github/workflows/testy.yml` | testy przy każdej zmianie kodu i raz na dobę na żywych danych |
| `data/RRRR-MM.csv` | surowe odczyty pokoi: `ts,device_id,code,value` |
| `data/dzienne.csv` | dobowe min/średnia/max — z tego „Zakresy 7 dni” i „Ostatnie 30 dni” |
| `data/pogoda.json` | migawka: teraz, prognoza na 3 dni i godzinowa na dobę, jakość powietrza. Nadpisywana co przebieg |
| `data/index.json` | lista urządzeń, miesięcy, czas ostatniej zbiórki, kursory i diagnostyka (`alerty`) dla watchdoga |
| `data/dom/stan.json` | reguły domu dla strony, po pokoju: `przewietrz`, `okno`, `noc` (przed snem), `milczy_od`, `bateria`. Nadpisywany co przebieg |
| `data/dom/powiadomienia.json` | powiadomienia o domu: historia z 60 dni, stan reguł, kolejki odłożonych i znacznik „przed snem” każdego telefonu. Zmienia się tylko przy wpisie albo zmianie epizodu |
| `data/rosliny/RRRR-MM.csv` | odczyty czujników w doniczkach, przerzedzone (zmiany plus jeden wiersz na godzinę). Osobno od pokoi |
| `data/rosliny/stan.json` | to, co pokazuje zakładka „Rośliny”: ostatnie odczyty, szereg godzinowy z 30 dni, światło dobowe i jego ocena, podlania, werdykty, alarmy dla watchdoga; do tego kursory i skale toru roślin |
| `data/rosliny/powiadomienia.json` | powiadomienia o roślinach: historia z 60 dni, stan reguł, kolejki odłożonych każdego telefonu |

---

## Uruchomienie od zera

1. **Projekt w chmurze Tuya.** Na [iot.tuya.com](https://iot.tuya.com) załóż projekt
   (Smart Home, data center **Central Europe**), podepnij konto Smart Life przez
   kod QR i sprawdź, czy w zakładce *Devices* widać czujniki. W *Service API*
   musi być **IoT Core** — to z niego biorą się logi.
2. **Sekrety repozytorium.** *Settings → Secrets and variables → Actions*:
   `TUYA_CLIENT_ID` i `TUYA_CLIENT_SECRET` z zakładki *Overview → Authorization Key*.
3. **Identyfikatory czujników.** `python fetch.py --discover` wypisze listę.
   Wklej je do `TUYA_DEVICE_IDS` w `zbieraj.yml`, a pokoje opisz w `pokoje.json`
   (adres, odmiany nazwy, strona świata okna).
4. **GitHub Pages.** *Settings → Pages → Source: Deploy from a branch → main / (root)*.
5. **Pierwszy przebieg.** *Actions → Zbieranie odczytów → Run workflow*.
   Po minucie w `data/` pojawią się pliki, a aplikacja zacznie coś pokazywać.
6. **Powiadomienia** (nieobowiązkowe): klucz VAPID i subskrypcje telefonów w sekretach,
   klucz do ustawień na każdym telefonie — `ROSLINY-INSTRUKCJA.md`, kroki 9 i 10.

Repozytorium musi być **publiczne** — przy prywatnym Pages wymaga płatnego planu.

---

## Ustawienia

W sekcji `env` kroku „Pobierz…” w `.github/workflows/zbieraj.yml`:

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `TUYA_REGION` | `eu` | data center projektu Tuya |
| `TUYA_DEVICE_IDS` | — | identyfikatory czujników po przecinku |
| `TUYA_SINCE` | puste | granica: starsze odczyty są kasowane i nie wracają |
| `OUTDOOR_LAT` / `OUTDOOR_LON` | Katowice | pogoda i smog z Open-Meteo. Puste = wyłączone |
| `TZ_LOCAL` | `Europe/Warsaw` | według tej strefy tną się doby w agregatach i przelicza się prognoza godzinowa. Musi być nazwą strefy, nie przesunięciem: prognoza sięga 36 godz. naprzód, więc dwa razy w roku przechodzi przez zmianę czasu |
| `POWIADOMIENIA` | `wlaczone` | globalny wyłącznik powiadomień o domu i roślinach: `na-sucho` liczy reguły i zapisuje wpisy, ale nic nie wysyła |
| `POWIADOMIENIA_ANDROID` / `POWIADOMIENIA_IPHONE` | brak = domyślne | ustawienia każdego telefonu — patrz niżej |

**Ustawienia telefonów** to zmienne repozytorium (*Settings → Secrets and variables →
Actions → Variables*), JSON w kształcie `DOMYSLNE` z `telefony.py`: siedem reguł
(`przewietrz`, `okno`, `czujniki`, `podlej`, `przestaw`, `czujnik`, `podsumowanie`)
i cisza nocna (`cisza`, `od`, `do`). Domyślnie wszystko poza podsumowaniem, cisza 21–8.
- Zapisuje je aplikacja (zakładka Powiadomienia) przez API GitHuba kluczem fine-grained
  z jednym uprawnieniem — **Variables: Read and write**, tylko to repozytorium.
  Klucz wkleja się raz na każdym telefonie (`ROSLINY-INSTRUKCJA.md`, krok 10).
- Do kroku „Pobierz…” trafiają wyłącznie przez `env:`. **Nigdy `${{ vars.X }}` wewnątrz
  `run:`** — treść ustawia każdy, kto ma klucz z telefonu, a wyrażenie w `run:` stałoby
  się kodem powłoki.
- Brak zmiennej albo zły JSON to wartości domyślne, nigdy błąd. Log kolektora mówi tylko
  „Android: własne / domyślne / nieczytelne”.
- **Ich treść widać w publicznym logu** kroku „Pobierz…”: Actions wypisuje env kroku,
  a zmiennych, inaczej niż sekretów, nie maskuje. Przyjęte świadomie — to nie sekret,
  a godziny ciszy i tak da się wyczytać z publicznych plików powiadomień.

**Pokoje** opisuje `pokoje.json`, po identyfikatorze czujnika, a nie po nazwie ze Smart
Life — zmiana nazwy w aplikacji Tuya nie psuje adresów ani zdań. `slug` to adres
(`#lazienka`), `dop`, `bier`, `miejsc` to odmiany wklejane wprost w zdania („przewietrz
łazienkę”, „zamknij okno w sypialni?”), `okno` to strona świata (`pld`, `pln`). Sypialnia
wychodzi na południe, Salon i Kuchnia na północ, Łazienka okna nie ma — z tego bierze się
rada, od którego pokoju zacząć wietrzenie na przestrzał. Pokój bez wpisu dostaje adres
z nazwy z manifestu.

**Bliźniacze stałe** — każda para ma test zgodności:
- granica „za wilgotno” (`FRSI`, `WILG_POWIERZCHNI`, `HUM_ALERT`) w `index.html`
  i `fetch.py`, a jej wzór w `dom.py` równy `fetch.prog_plesni` na siatce;
- filtr chwilowych skoków (`SPIKE` w `index.html`, `SPIKE_JUMP`, `SPIKE_RISE`, `SPIKE_MAX`
  w `fetch.py`) — inaczej agregaty dobowe pokazują co innego niż wykres;
- próg pełnej doby światła (`POKRYCIE_PELNEJ_DOBY`) w `index.html` i `rosliny.py`;
- ustawienia domyślne telefonów (`DOMYSLNE`) w `index.html` i `telefony.py`.

---

## Aplikacja

Jeden plik `index.html`, bez budowania i bez bibliotek z CDN — wykresy rysuje sam.
Cztery zakładki, każdy widok ma własny adres:

| Widok | Co pokazuje |
|---|---|
| **Dom** (`#dom`) | jedno zdanie stanu (zamknij okno? / przewietrz / czujnik milczy / wszystko w normie), kafle pokoi, dwór, wykres doby wszystkich pokoi. Zbiórka spóźniona o ponad 3 godz. to jedna linia „Ostatnia zbiórka N godz. temu” |
| pokój (`#lazienka`, `#sypialnia`, `#salon`, `#kuchnia`) | wartości teraz, reguły z `data/dom/stan.json` (przewietrz, okno, linia nocna „przed snem”), wykres doba / 7 dni / 30 dni, komfort dziś, rytm doby, czujnik |
| dwór (`#zewnatrz`) | odczyty, prognoza i powietrze z Open-Meteo |
| **Rośliny** (`#rosliny`, roślina `#fikus`, `#skrzydlokwiat`, `#azalia`) | karty z werdyktem, glebą wobec progu, prognozą podlewania i światłem; szczegół z wykresami gleby i światła z 30 dni |
| **Historia** (`#historia`) | komfort dziś, zakresy 7 dni, ostatnie 30 dni (paski min–maks doby), czujniki i zbiórka |
| **Powiadomienia** (`#powiadomienia`) | ten telefon (subskrypcja Web Push), przełączniki reguł i cisza nocna osobno dla Androida i iPhone'a, lista „Ostatnie”, klucz dostępu |

Między pokojami i między roślinami przechodzi się też palcem w bok. Nieznany adres
prowadzi na Dom. Stare adresy (`#roslina=Fikus`, `rosliny.html#roslina=…`) prowadzą do
nowych — tak trafiają tu dawne powiadomienia i zakładki.

**Zasady, których pilnują testy:**
- **Reguły liczy Python, strona tylko wyświetla.** „Przewietrz”, „zamknij okno?”, „przed
  snem” i „czujnik milczy” przychodzą z `data/dom/stan.json`, werdykty i ocena światła
  roślin z `data/rosliny/stan.json` — karta i powiadomienie nie mogą mówić co innego.
  Strona sama liczy tylko wyświetlanie: wykresy, komfort, zakresy, 30 dni. Połówki
  zaokrągla w górę, tak samo jak Python w treściach powiadomień.
- **Seria godzinowa:** punkt godziny to średnia surowych odczytów z tej godziny, po
  filtrze skoków i bez znanych artefaktów. Pusta godzina to dziura, a nie przeciągnięta
  wartość.
- **„Czujnik milczy”** na ekranie po 3 godz. ciszy liczonej do ostatniej zbiórki, nie do
  „teraz” — spóźniony kolektor nie robi z czujników martwych. Powiadomienie dopiero po
  6 godz.
- **Na Domu, stronach pokoi i w Historii nie ma żadnych wartości z doniczek.** Wolno
  tylko kropkę na zakładce Rośliny i licznik na ikonie.
- Bez plików nieobowiązkowych (pogoda, `data/dom/`, rośliny, powiadomienia) aplikacja
  działa, tylko bez tych części. Błąd toru roślin to linia „Kolektor zgłosił błąd przy
  roślinach: …”, a stan roślin starszy od zbiórki o ponad 3 godz. — „stan sprzed N godz.”
  zamiast werdyktu.
- JS zachowawczy (ES2019, bez modułów), skrypty zewnętrzne tylko po https (strażnik
  w `testy.yml`).

**Odświeżanie:** przy powrocie do karty po co najmniej 2 minutach, co 10 minut przy
widocznej karcie i po powrocie sieci. Widok (zakładka, pokój, zakres) zostaje, a błąd
sieci albo serwera przy odświeżaniu niczego nie kasuje — zostaje ostatni dobry stan. Bez
nowych danych przerysowują się same „N min temu” i doby, żeby karta otwarta godzinami nie
stała w miejscu.

**Offline:** `sw.js` (v6) trzyma szkielet aplikacji, `pokoje.json` i ostatnie `data/`, więc
bez zasięgu aplikacja otwiera się z ostatnimi odczytami. Podbicie wersji workera kasuje
ten zapas raz.

**Licznik na ikonie:** liczba spraw wymagających uwagi — pokoje z oknem, przewietrz albo
milczącym czujnikiem i rośliny do podlania. Tylko przy zgodzie na powiadomienia; na
Androidzie zwykle go nie ma.

**Dawna strona** (do 11.10.2026) — rzut mieszkania, odtwarzanie historii, łuk doby,
wykresy Chart.js z przybliżaniem gestem, rada „czy wietrzyć teraz”, kafel trendu, strefa
komfortu, noce w sypialni, kalendarz całej historii — odeszła razem ze swoim opisem w tym
pliku. Dlaczego była zbudowana tak, a nie inaczej, mówi `KONTEKST.md`; kod:
`git show 6b5c01b:index.html`.

### Granica „za wilgotno”

Kiedy w pokoju jest za wilgotno, nie mówi stały próg. Pleśń nie rośnie w powietrzu
pokoju, tylko na najzimniejszym kawałku ściany zewnętrznej — w narożniku, za szafą, przy
nadprożu — a ten jest tym zimniejszy, im zimniej na dworze. Rachunek z PN-EN ISO 13788:
temperatura powierzchni `θsi = θe + fRsi·(θi − θe)`, a kłopot zaczyna się, gdy wilgotność
przy niej trwale przekracza 80%. Z tego wychodzi wilgotność powietrza w pokoju, od której
robi się niebezpiecznie — dla pokoju o 20 °C:

| Na dworze | 15 °C | 11 °C | 5 °C | 0 °C | −5 °C | −10 °C |
|---|---|---|---|---|---|---|
| Granica w pokoju | 73% | 68% | 60% | 55% | 50% | 45% |

Każdy odczyt porównywany jest z temperaturą pokoju i dworu z tej samej chwili. Z tej
granicy korzystają trzy miejsca: alarm watchdoga (pokój przez ponad ćwierć doby nad nią),
reguły „przewietrz” i „przed snem” w `dom.py` oraz linia granicy na wykresie wilgotności.
W aplikacji i powiadomieniach mówi się „za wilgotno” i „granica”.

`FRSI = 0,70` to liczba z normy, nie z pomiaru. Da się ją zmierzyć (czujnik na dobę
w najzimniejszym narożniku, drugi w środku pokoju, odczyt z dworu:
`fRsi = (θnarożnik − θdwór) / (θpokój − θdwór)`), ale czujniki zostają na swoich miejscach.

### Znane artefakty i farelka

`artefakty.json` w katalogu głównym to ręczna lista przedziałów, w których czujnik mierzył
coś innego niż pokój: farelkę tuż pod nim, przenoszenie. Wiersze **zostają** w `data/*.csv`.
Kolektor pomija je w agregatach dobowych i przekazuje listę w manifeście, a aplikacja
pomija je w serii godzinowej i w „Komfort dziś”. Po zmianie pliku wystarczy push —
kolektor przeliczy agregaty przy najbliższym przebiegu.

Farelka w łazience to prawdziwe grzanie, nie usterka czujnika, więc aplikacja ją pokazuje
— o ile czujnik nie wisi tuż nad nią (27.09 wisiał; tamten poranek jest na liście,
a czujnik przestawiony). Filtr chwilowych skoków odsiewa wyłącznie nagłe wyskoki **ze
spokojnego poziomu** (czujnik w dłoni), a reguła „zamknij okno” porównuje spadek
z poziomem sprzed niego, więc stygnięcie po farelce nie wygląda na otwarte okno (test na
odczytach z 8.10).

---

## Kolektor co godzinę

GitHub nie gwarantuje harmonogramu: przebiegi `schedule` bywają opóźniane i gubione
przy obciążeniu. Do 26.08.2026 zapis szedł co 55 minut, od 27.08 — bez żadnej zmiany
w kodzie — co 3,5–4,5 godziny; watchdog z harmonogramem co 6 godz. startował
z opóźnieniem 2,5–5,5 godz. Właściwym zegarem jest więc zewnętrzny cron, który co
godzinę woła `workflow_dispatch`. Harmonogram w `zbieraj.yml` zostaje jako zapas,
a dwa przebiegi naraz nic nie psują (`zapisz.sh`).

1. **Token.** GitHub → Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token. Repository access: *Only select
   repositories* → `Smart-Home`. Permissions → Repository → **Actions: Read and write**.
   Nic więcej. Taki token pozwala uruchamiać i przeglądać przebiegi tego jednego
   repozytorium; nie daje dostępu do kodu ani sekretów.
2. **cron-job.org** (darmowe konto) → Create cronjob:
   - URL: `https://api.github.com/repos/Bronek31/Smart-Home/actions/workflows/zbieraj.yml/dispatches`
   - harmonogram: co godzinę, minuta 19
   - Advanced → Request method: `POST`
   - nagłówki: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
     `X-GitHub-Api-Version: 2022-11-28`
   - Request body: `{"ref":"main"}`
3. **Sprawdzenie.** „Test run" w cron-job.org ma oddać status `204`, a w zakładce
   Actions pojawia się przebieg *Zbieranie odczytów* z wyzwalaczem `workflow_dispatch`.
   `401` = zły token, `404` = literówka w adresie albo token bez dostępu do repozytorium,
   `403` = token bez uprawnienia Actions.

Token ma datę ważności — przed nią trzeba wygenerować nowy i podmienić nagłówek.

**Stan:** postawiony 27.09.2026 na cron-job.org, co godzinę. Przez pierwsze godziny
chodził co 30 minut — zmienione, bo czujniki same raportują mniej więcej raz na
godzinę, więc częstsze pobieranie dawało dane świeższe średnio o kwadrans za cenę
dwa razy większej liczby zapytań do Tuya.

**Limit zapytań Tuya.** Trial IoT Core to pakiet **0,20 USD na miesiąc kalendarzowy**
(iot.tuya.com → IoT Core → My Subscriptions, „Cloud Develop Base Resource Trial").
Zapytania z runnerów GitHuba Tuya liczy jako zagraniczne (`CLOUD_API_FOREIGN`,
3,71 USD za milion), więc pakiet to ok. 54 000 zapytań. Liczy się każde: token,
lista urządzeń, każda strona logów, także nieudane.

Do 8.10.2026 przebieg pobierał pełne 7 dni logów — 29 zapytań, a przy ok. 28
przebiegach na dobę ok. 47% pakietu (panel 8.10 po południu: 6229 zapytań, co do kilku
zgodne z wyliczeniem). Od tego dnia kolektor pyta tylko o odcinek od `pobrane_do`:
token, lista urządzeń, po jednej stronie na czujnik i jedna na klimatyzator, czyli
ok. 7 zapytań na przebieg. Ile dokładnie, wypisuje sam na końcu logu przebiegu
(„Zapytań do Tuya w tym przebiegu"). Pierwszy przebieg po wdrożeniu, bez kursora
w manifeście, bierze jeszcze pełne 7 dni — 8.10 kosztował 75 zapytań (ok. 17 na
czujnik), co wskazuje, że Tuya oddaje logi od najnowszego.

Na jeden odcinek przypada jedna strona (100 wpisów). Gdy odcinek się nie mieści, kolektor
dzieli go albo przesuwa po znacznikach czasu — w obu kolejnościach, w jakich Tuya może
oddawać logi — i nigdy nie przekracza ok. 30 zapytań na czujnik w jednym przebiegu
(`BUDZET_URZADZENIA`). To zabezpieczenie przed czujnikiem, który zalewa logi. Jedyna
świadoma strata: ponad 500 wpisów w dwie minuty przy kolejności od najnowszego — reszta
z tych dwóch minut przepada, z ostrzeżeniem w logu (`NAJKROTSZY_ODCINEK_MS`). Czujniki
pokojowe robią kilka wpisów na godzinę.

## Na ekranie telefonu

Aplikacja instaluje się jak każda inna — własna ikona, pełny ekran, bez paska przeglądarki:

- **Android (Chrome):** menu ⋮ → **Zainstaluj aplikację** (albo „Dodaj do ekranu głównego”).
- **iPhone (Safari):** przycisk udostępniania (kwadrat ze strzałką) → **Do ekranu
  początkowego** → „Dodaj”. Musi to być Safari — inne przeglądarki na iPhonie tej opcji
  nie mają albo dodają zwykłą zakładkę. Powiadomienia działają tylko w aplikacji otwartej
  z tej ikony, a ma ona pamięć osobną od Safari.

Na iPhonie pasek stanu jest przezroczysty, więc aplikacja zostawia pod nim miejsce
(`viewport-fit=cover` i `env(safe-area-inset-*)`); bez tego nagłówek wchodził pod zegar.

**Nie zmieniać:** klucza VAPID, ścieżki i zakresu `sw.js`, `start_url` i `scope`
w manifeście, nazw `rosliny-subskrypcja`, bazy IDB `rosliny`/`odebrane` i cache
`cel-powiadomienia`. Każda z tych zmian gubi subskrypcje na obu telefonach (iOS kasuje
subskrypcję także przy ponownym dodaniu ikony).

## Powiadomienia

Reguły liczą `dom.py` i `rosliny.py` w każdym przebiegu kolektora. Decyzja „komu teraz,
komu po końcu jego ciszy nocnej” zapada też w kolektorze (`telefony.py`) i ląduje we wpisie
(`telefony`) w tym samym commicie co stan reguł — nadawca niczego nie zapamiętuje. Reguły
z pomiarami: `ROSLINY.md`, „Etap 4” i „Reguły powiadomień”; podpięcie telefonu i klucz do
ustawień: `ROSLINY-INSTRUKCJA.md`, kroki 9 i 10.

**Krok wysyłki** („Wyślij powiadomienia o domu i roślinach” w `zbieraj.yml`) rusza tylko
po udanym `zapisz.sh`:
1. bierze `data/rosliny/powiadomienia.json` i `data/dom/powiadomienia.json` z opublikowanego
   commita (`git show origin/main:…`); brakujący plik pomija;
2. jq liczy w każdym wpisy tego przebiegu (`przebieg`), nie na sucho i z niepustym
   `telefony`; przy zerze krok kończy się bez instalowania biblioteki;
3. inaczej `python wyslij.py --plik <rośliny> --plik <dom> --przebieg …`.

Tylko ten krok dostaje sekrety powiadomień, a nieudanej wysyłki nikt nie ponawia (co
najwyżej raz). Nadawca wysyła każdemu telefonowi tylko wpisy z jego id, najwyżej 13 na
przebieg. Wygasła subskrypcja, zły klucz albo zepsuty wpis zakłada zgłoszenie z etykietą
`powiadomienia`; zamyka się samo w przebiegu, w którym każdy podpięty telefon coś
dostał, bez błędów.

## Gdy coś nie działa

| Objaw | Co z tym |
|---|---|
| Aplikacja: „Nie ma jeszcze żadnych odczytów” | Kolektor nie zrobił jeszcze udanego przebiegu. Zakładka Actions |
| Dom: „Ostatnia zbiórka N godz. temu” | Problem po stronie Actions albo Tuya, nie czujników. Czujniki oceniane są do chwili ostatniej zbiórki, więc przy spóźnionym kolektorze nie „milkną” |
| Rośliny: „Kolektor zgłosił błąd przy roślinach: …” albo „stan sprzed N godz.” | Padł tor roślin (literówka w `rosliny.json`, odmowa Tuya, wyjątek w obliczeniach). Pokoje i reguły domu działają dalej; szczegóły w logu przebiegu i w zgłoszeniu z etykietą `rosliny` |
| Powiadomienia: „Klucz nie działa albo wygasł” | Klucz do ustawień wygasł albo został usunięty. Nowy: `ROSLINY-INSTRUKCJA.md`, krok 10, i wkleić na obu telefonach. Powiadomienia idą dalej według ostatnich zapisanych ustawień |
| Powiadomienia: „Subskrypcja się zmieniła” albo „Powiadomienia nie dochodzą do tego telefonu” | Ten telefon → Włącz powiadomienia → skopiuj subskrypcję → podmień sekret `PUSH_ANDROID` / `PUSH_IPHONE` (krok 9) |
| Zgłoszenie z etykietą `powiadomienia` | Wysyłka się nie udała: wygasła subskrypcja (404/410), klucz VAPID nie pasuje do strony (403) albo planer zapisał zepsuty wpis. Treść zgłoszenia mówi, co i dla którego telefonu |
| W zgłoszeniu „Czujniki wymagają uwagi”: „**Powiadomienia w domu** — błąd reguł” | Wyjątek w `dom.py`. Odczyty i rośliny zapisały się normalnie, nie ma tylko reguł domu; typ błędu i miejsce w logu przebiegu |
| „Zbieranie odczytów” na czerwono z „Push odrzucony” | Dwa przebiegi kolektora weszły sobie w drogę. `zapisz.sh` liczy wtedy odczyty jeszcze raz na drzewie zwycięzcy i próbuje trzy razy; czerwień znaczy, że nie udało się ani razu. Odczyty nie giną — kursor stoi, więc następny przebieg dociąga od tego samego miejsca |
| Zgłoszenie „brak nowej pogody od… , Open-Meteo nie odpowiada” | Dwór milczy dłużej niż zwykle. Czujniki i reguły domu działają dalej; „przed snem” czeka na świeżą prognozę |
| W aplikacji zniknął dwór, choć czujniki działają | Przebieg nie dostał odpowiedzi z Open-Meteo. Historia leży dalej w CSV, a `keep_known` w `fetch.py` trzyma urządzenie w manifeście, dopóki ma odczyty — wróci przy najbliższym udanym przebiegu. Jeśli mimo to zniknął, w logu przebiegu szukaj „Pogoda: pominięta” |
| Dane przychodzą co 3–5 godz. zamiast co godzinę, przebiegi zielone | GitHub opóźnia harmonogram (od końca sierpnia 2026 to norma). Odczyty nie giną — każdy przebieg dociąga od miejsca, w którym skończył poprzedni (do 7 dni wstecz) — ale aplikacja jest nieświeża, a watchdog potrafi zgłosić fałszywe „Kolektor stoi”. Lekarstwo: zewnętrzny zegar, patrz „Kolektor co godzinę” |
| Błąd `28841002` w logu | Wygasł trial IoT Core. Wniosek o przedłużenie na iot.tuya.com, 1-2 dni robocze. Pierwszy trial wygasł **po miesiącu** (12.09.2026). Obecny jest przedłużony do 13.03.2027 (panel 8.10) — wniosek ok. 6.03.2027 |
| Błąd `28841004` w logu | Najpewniej wyczerpany miesięczny pakiet triala (0,20 USD) — znaczenie kodu znane z wyszukiwarki, niepotwierdzone. Zużycie: iot.tuya.com → IoT Core → My Subscriptions. Pakiet odnawia się 1. dnia miesiąca; do tego czasu kolektor stoi, a odczyty starsze niż 7 dni przepadają |
| Błąd `1004` | Access Secret przepisany z ucięciem znaku |
| Błąd `1114` albo `2007` | Zły region w `TUYA_REGION` |
| Pusta lista przy `--discover` | Konto Smart Life podpięte do innego data center |
| Bateria: „słaba” | Wymień ogniwo. Słabnąca bateria gubi raporty, zanim czujnik zniknie zupełnie |
| Zgłoszenie „Czujniki wymagają uwagi” | Watchdog wyłapał słabą baterię, milczący czujnik albo wilgotność powyżej granicy przez ponad ćwierć doby. Treść odświeża się co kilka godzin, zgłoszenie zamknie się samo |
| Przebiegi w ogóle nie ruszają | GitHub wyłącza harmonogramy po 60 dniach bezczynności. Jedno ręczne uruchomienie je wskrzesza |

---

## Testy

```bash
python3 -m unittest discover -s tests             # kolektor, reguły, nadawca — sama biblioteka standardowa
cd tests/frontend && npm ci && npx playwright test
```

Stan na 11.10.2026: **430** testów Pythona (lokalnie 9 pominiętych: 6 bez biblioteki
`pywebpush`, 3 czekają na pliki z pierwszej zbiórki po wdrożeniu) i **148** testów
w przeglądarce (`strona.spec.js` — aplikacja, `rosliny.spec.js` — powiadomienia, service
worker i przekierowanie `rosliny.html`).

Dwie warstwy, bo są dwa różne rodzaje ryzyka.

**Python** ma testy czystych funkcji — rozpoznawanie pól Tuya, filtr wyskoków, pobieranie
przyrostowe na atrapie Tuya, reguły domu i roślin na prawdziwych epizodach (farelka 8.10,
wietrzenie Salonu 6.10, zmiana czasu 25.10), cisza i kolejka każdego telefonu, nadawca na
atrapie `pywebpush` — plus zestaw sprawdzający **prawdziwe `data/`**: czy pliki miesięczne
są posortowane i bez duplikatów, czy każde urządzenie z odczytów jest w manifeście, czy
`dzienne.csv` da się odtworzyć z surowych odczytów co do bajtu, czy pliki powiadomień
i stany trzymają kształt. Ta druga grupa nie zależy od żadnej zmiany w kodzie, więc chodzi
też raz na dobę z harmonogramu. Krok wysyłki z `zbieraj.yml` jest uruchamiany naprawdę
(`bash`, `git`, `jq`) i porównywany z nadawcą.

**Aplikacja** jest testowana w prawdziwej przeglądarce, bo `index.html` to jeden plik bez
budowania. Dane podstawia router po ścieżce (`tests/frontend/dane.js`; `data/rosliny/…` to
inny plik niż `data/…`), ułożone pod konkretne zjawisko: martwy czujnik, spóźniona
zbiórka, reguła domu w `data/dom/stan.json`, roślina do podlania. API GitHuba ma atrapę
(`page.route`: 200, 404 → POST, 401, 403), gesty idą prawdziwymi zdarzeniami dotyku przez
CDP. Każdy test wywraca się na dowolnym błędzie w konsoli.

Fikstury muszą trzymać się skali prawdziwych danych, bo inaczej test przestaje cokolwiek
sprawdzać, a znaczniki liczą się względem „teraz”, żeby wynik nie zależał od pory doby,
o której testy poszły.

### Testy nie wpuszczą złego pusha

GitHub Actions uruchamia testy **po** pushu, więc czerwony przebieg jest raportem,
a nie blokadą — sam z siebie niczego nie cofnie. Blokadą jest hook `pre-push`, który
odmawia wysłania, dopóki obie warstwy nie przejdą. W świeżym klonie trzeba go raz włączyć:

```bash
git config core.hooksPath .githooks
cd tests/frontend && npm ci     # bez tego hook nie przepuści, bo nie ma czym sprawdzić strony
```

Świadome obejście to `git push --no-verify`. Kolektora to nie dotyczy: w Actions hooki
się nie wykonują, a on i tak commituje wyłącznie `data/`.

Gdybyś kiedyś chciał twardej bramy po stronie serwera, trzeba włączyć ochronę gałęzi
`main` z wymaganymi statusami *Kolektor (Python)* i *Strona (przeglądarka)*. Wymaga to
jednak wyjątku dla `github-actions[bot]`, bo inaczej ochrona zatrzyma cogodzinny zapis
odczytów — a wtedy aplikacja przestanie się aktualizować.

### Rzeczy warte zapamiętania przy pisaniu kolejnych testów

- **Fikstura też potrafi kłamać.** Dwa razy przepuściła czerwone CI: raz dopisując
  odczyt na istniejący znacznik, raz rytmem dobowym tak żywym, że „spokojny pokój”
  przestawał być spokojny o niektórych porach doby. Osobny zestaw `dane testowe` pilnuje
  samej fikstury.
- **Service worker musi być zablokowany** (`serviceWorkers: 'block'` w konfiguracji).
  Inaczej przechwytuje `fetch` strony i idzie prosto do sieci, omijając podstawione dane.
  Testy samego workera włączają go jawnie.
- **Czekaj na `data-dane` na `#app`** (`gotowe` albo `blad`), nie na widoczność — start
  jest asynchroniczny, a pusty szkielet pojawia się przed danymi.

---

## Koszt

Zero. Publiczne repozytorium ma darmowe minuty Actions i darmowe Pages.
Open-Meteo nie wymaga klucza API (licencja CC BY 4.0 — podpis źródła stoi na dole strony dworu, `#zewnatrz`). Jedyne ograniczenie to darmowy trial
IoT Core u Tuya, który trzeba przedłużać wnioskiem na iot.tuya.com — pierwszy
wygasł po miesiącu, a zatwierdzenie trwa 1–2 dni robocze. Zewnętrzny zegar
(cron-job.org) i Web Push (serwery push Google i Apple) też są darmowe.
