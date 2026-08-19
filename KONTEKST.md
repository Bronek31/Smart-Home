# Kontekst pracy

Notatka przekazania: co zostało zrobione, co świadomie odrzucone i o czym trzeba
wiedzieć, zanim ruszy się ten projekt dalej. `README.md` opisuje, **jak to działa**;
ten plik mówi, **dlaczego tak** i **na co uważać**. Pomysły na przyszłość siedzą
w `TODO.md`.

Stan na 19.08.2026, commit `b67a533`. Wszystkie workflowy zielone.

---

## Jak pracujemy

| Zasada | Dlaczego |
|---|---|
| **Wszystko po polsku** — commity, komentarze, nazwy funkcji, testy, dokumentacja | jednolitość; kod czyta się jak tekst |
| **Mierz, nie zgaduj** | prawie każda decyzja w tym projekcie została podjęta po pomiarze, nie po intuicji. Kilka razy pomiar obalił moją pierwszą hipotezę |
| **Po każdym pushu sprawdź Actions** | bramki po stronie GitHuba nie ma (patrz niżej), więc czerwony przebieg zauważy tylko ten, kto zajrzy |
| **Test musi odrzucać starą wersję** | nowy test puszczamy przeciwko kodowi sprzed poprawki. Jeśli przechodzi w obie strony, jest strażnikiem, nie testem — i trzeba to powiedzieć wprost |
| **Commit tłumaczy powód, nie treść diffa** | diff widać w gicie; w wiadomości ma być to, czego z niego nie widać |

### Bramka przed pushem

`.githooks/pre-push` uruchamia oba zestawy i nie przepuszcza pusha przy czerwonym.
W świeżym klonie trzeba go włączyć raz:

```
git config core.hooksPath .githooks
```

**Nie ma ochrony gałęzi po stronie GitHuba.** Próbowaliśmy — wymaga rulesetu
z bypassem dla GitHub Actions, a ten nie pojawia się na liście aktorów w repozytorium
prywatnej osoby. Bez bypassu kolektor przestałby zapisywać dane (jego commity mają
`paths-ignore: data/**`, więc nie produkują żadnych checków, a reguła „wymagaj zielonych
checków" odrzuca commit bez checków). Alternatywa to deploy key z bypassem „Deploy keys"
— rozważona, nie wdrożona. Do tego czasu jedyną bramką jest hook lokalny plus zaglądanie
do Actions.

---

## Powtarzający się wzorzec błędu

**Cztery razy w tej sesji czerwone CI pochodziło z tego samego schematu: próg albo
gęstość porównywane z wartością już zaokrągloną do wyświetlenia, albo test dziedziczący
„co akurat jest teraz" zamiast ustalać własne warunki.** Za każdym razem aplikacja była
w porządku, a błąd siedział w teście albo w warstwie prezentacji.

1. **Fikstura na progu kroku animacji.** Historia miała równo `5 × 24 h`, a animacja
   liczy klatki przez `floor(rozpiętość / krok)` przy kroku 60 min — wynik skakał między
   119 a 120 zależnie od zaokrąglenia znacznika do pełnej sekundy. Naprawa: pół kroku
   zapasu w fiksturze (`ZAPAS` w `tests/frontend/dane.js`).
2. **Daty na osi poziomej.** Format podpisu brał się z wybranego zakresu, a krok
   podziałki z rzeczywistej rozpiętości danych — przy krótkiej historii wychodziło
   „14.08 14.08 15.08 15.08". Naprawa: format wynika z kroku (`fmtWhen(d, krokH)`).
3. **Podpisy osi pionowej.** Wilgotność wyświetlamy bez miejsc po przecinku, a pokoje
   stoją w paśmie pięciu punktów — Chart.js dzielił oś co pół procenta i dawał
   „51 51 50 50 49 49". Naprawa: `ticks.precision` równe liczbie miejsc.
4. **Zakres „dziś" w testach.** Wykresy startują od północy, więc o 4:54 miały pięć
   punktów, a wieczorem kilkanaście. Nocny przebieg z harmonogramu wywrócił się na
   `oczekiwano > 5, było 5`. Naprawa: `otworzTydzien()` — testy czytające serie same
   ustawiają zakres.

**Wniosek do zapamiętania:** jeśli coś wygląda dziwnie na wykresie albo w rysunku,
najpierw sprawdź, czy jakiś próg nie jest porównywany z liczbą już zaokrągloną.
A test tej strony musi sam ustalać swoje warunki — nigdy nie polegać na porze doby.

**Nocny przebieg z harmonogramu (`testy.yml`, cron `17 4 * * *`) jest najcenniejszy**,
bo jako jedyny zagląda o nietypowej godzinie i na żywych danych. To on złapał punkt 4.

---

## Co powstało w tej sesji

### Wykresy

- **Druga oś dla dworu** (temperatura i wilgotność względna). Dwór potrafi w tygodniu
  przejść 16 → 32 °C, a pokoje stoją w paśmie 25 → 26; na wspólnej osi cały ruch
  w mieszkaniu spłaszczał się do kilku pikseli. Zmierzone: prawa oś obejmuje ponad
  trzykrotnie szerszy zakres niż lewa.
- **Wilgotność bezwzględna zostaje na jednej osi** — i tak ma zostać. Tam sensem wykresu
  jest to, że przy wietrzeniu linia mieszkania zbliża się do linii dworu; na dwóch
  skalach ta odległość przestałaby cokolwiek znaczyć.
- **Wygładzenie linii pokoi** średnią z trzech kolejnych odczytów. Po rozdzieleniu osi
  krok czujnika (0,1 °C, 1%) urósł do kilkudziesięciu pikseli i krzywe zamieniły się
  w schodki. Zmierzone: średnia odsuwa linię najwyżej o **0,067 °C**, czyli mniej niż
  krok, o który czujnik i tak zaokrągla. Dwór zostaje surowy (uśrednienie jego stromej
  krzywej odsuwało linię o 1,17 °C), agregaty dobowe też nie są wygładzane.
  Rusza wyłącznie rysowana linia — tabela, kafle, rzut i wykrywanie wietrzeń liczą
  z surowych odczytów, a dymek pokazuje pole `v` z prawdziwym odczytem.
- **Dwór jako tło.** Brał kolor z palety pokoi tylko dlatego, że jest piątym
  urządzeniem na liście, i wyglądał na piąty pokój. Ma teraz własny stalowy kolor
  (`BARWA_DWORU`) i tam, gdzie ma osobną oś, rysuje się jako pasmo za pokojami.
  Zasada: **własna oś → tło, wspólna oś → linia.**

Sprawdzony i **odrzucony** wariant: mocniejsze wygładzenie samej krzywej
(interpolacja monotoniczna) wygląda praktycznie identycznie — między dwoma sąsiednimi
odczytami o tej samej wartości nie ma czego wygładzać.

### Łuk doby

Nad suwakiem odtwarzania biegnie rzeczywista droga słońca nad horyzontem tej doby,
na którą patrzy klatka. Wysokość słońca liczona wzorem NOAA, nie brana z prognozy
(dobowa prognoza sięga trzech dni w przód, a odtwarzanie chodzi tydzień wstecz).
Sprawdzone bisekcją i tożsamością przesileniową; dla Katowic 15.08 wychodzi wschód
5:31 i zachód 20:05 czasu lokalnego. Rysowana kreska to **próg wschodu (−0,833°)**,
nie zero — dzięki temu „słońce nad kreską" i „jest dzień" znaczą to samo.

Pułapka do zapamiętania: **`hidden` na elemencie SVG trzeba ustawiać atrybutem** —
`svg.hidden = false` tworzy tylko pole w JS, bo SVGElement nie dziedziczy po HTMLElement.

### Odtwarzanie historii

Jedno kliknięcie to jeden przebieg (wcześniej trzy okrążenia z przystankami). Po dojściu
do końca rzut wraca do stanu bieżącego, przycisk sam przełącza się na trójkąt. Cała
maszyneria pętli została usunięta, a nie tylko wyłączona.

### Kolektor i infrastruktura

- **`zapisz.sh`** — pobranie i zapis w jednym kroku, odporne na wyścig dwóch przebiegów.
  Kolektor rusza z harmonogramu i z pusha, więc dwie kopie potrafią działać naraz mimo
  grupy `concurrency`. Przegrany **nie godzi** dwóch wersji plików (rebase stawał na
  konflikcie w `index.json` i `pogoda.json`, bo oba przebiegi przepisują je w całości) —
  bierze stan zwycięzcy i liczy odczyty od nowa.
- **`keep_known()`** w `fetch.py` — manifest nie gubi urządzenia, które ma jeszcze
  odczyty. Timeout Open-Meteo kasował wpis dworu z listy i strona traciła całą jego
  historię, mimo że wiersze leżały w CSV. Kolejność wpisów bierze się z poprzedniego
  manifestu, bo po niej strona rozdaje pokojom kolory.
- **Alarm o milczącym dworze.** `diagnose()` pomijało urządzenia zewnętrzne w całości,
  więc awaria pogody nie docierała do nikogo. Cisza dworu jest teraz zgłaszana, z własnym
  brzmieniem; bateria i zawilgocenie nadal go nie dotyczą.
- **Strefa czasowa w prognozie godzinowej.** `trim_hourly` brało jedno przesunięcie na
  całe 37-godzinne okno, więc przy zmianie czasu 30 z 37 godzin lądowało o godzinę za
  wcześnie. Każda godzina przeliczana jest teraz osobno, w prawdziwej strefie; jesienna
  powtórzona druga w nocy rozpoznawana jest po tym, że czas nie posunął się naprzód.
- **`.nojekyll`** — Pages nie buduje już strony Jekyllem. Wtyczka `jekyll-github-metadata`
  odpytywała API GitHuba przy każdym wdrożeniu i gdy API oddało 500, wdrożenie szło na
  czerwono mimo że w repozytorium nic się nie zmieniło.

---

## Decyzje świadomie **nie** podjęte

Zanim któraś z nich wróci jako pomysł — oto powody.

- **Filtrowanie skoków po stronie strony zostaje.** Zmierzone: filtr uznał za wyskok
  0 z 1102 odczytów, a epizodu z czujnikiem w dłoni nie złapał w ogóle (jest napisany
  na pojedynczy odczyt, który skacze i wraca, a tam było narastanie przez 25 minut).
  Był raz usunięty razem z przyciskiem, potem **przywrócony na życzenie**.
- **Odczyty z przenoszenia czujników zostają w danych.** Próbowaliśmy dwóch podejść:
  usunięcia wierszy (`TUYA_POMIN`) i odtworzenia ich interpolacją (`TUYA_ODTWORZ`).
  Oba zostały cofnięte — nienaturalny moment przenoszenia ma zostać jako ślad tego,
  co się działo. Kod obu mechanizmów jest w historii gita, gdyby kiedyś był potrzebny:
  commity `c54379c` i `75720f9`, cofnięte przez `b67a533`.
- **Historia dworu sprzed `TUYA_SINCE` nie jest trwała.** `purge_before` kasuje ją przy
  każdym przebiegu, a wraca tylko dlatego, że Open-Meteo oddaje siedem dni wstecz.
  To skutek świadomie ustawionej granicy — „naprawa" znaczyłaby wyłamanie dworu spod niej.
- **Testy nie chodzą przy commitach z danymi** (`paths-ignore: data/**`). Odpalanie
  pełnego CI przy każdym zapisie to 24 przebiegi na dobę. Niezmienniki danych sprawdza
  nocny przebieg — z opóźnieniem do doby, i tak ma zostać.

---

## Pułapki środowiska

- **Katalog roboczy w powłoce nie wraca sam.** Po `cd tests/frontend` kolejne polecenia
  lecą stamtąd. Dwa razy w tej sesji dało to fałszywy wynik: raz Playwright wystartował
  bez swojej konfiguracji i zgłosił „No tests found", raz `git stash push index.html`
  nie trafił w plik. Używaj ścieżek bezwzględnych albo `cd` w tym samym poleceniu.
- **Playwright szuka przeglądarki po numerze budowy** przypisanym do swojej wersji.
  W kontenerze z gotowym katalogiem przeglądarek numer bywa inny i wszystkie testy padają
  na „Executable doesn't exist". Hook `pre-push` sam podstawia to, co leży na dysku;
  ręcznie: `PLAYWRIGHT_CHROMIUM_PATH=/opt/pw-browsers/chromium-*/chrome-linux/chrome`.
- **Skasowanie wierszy z `data/*.csv` nic nie daje.** Każdy przebieg pobiera z Tuya
  pełne okno 7 dni i dopisuje wszystko, czego nie ma w pliku — usunięte wracają w ciągu
  godziny. Zmiana **wartości** przy zachowanym znaczniku jest trwała, bo `merge()`
  kluczuje po `(ts, device_id, code)`.
- **`policzWietrzenia(od)` zwraca `{wietrz, klima, nazwy}`**, a nie mapę po
  identyfikatorze. Pomyliłem się na tym i zaraportowałem nieprawdziwe „zero wietrzeń";
  poprawny odczyt to `policzWietrzenia(od).wietrz[d.id]`.
- **`githubstatus.com` jest zablokowany** przez proxy tej sesji — awarii Pages nie da
  się stąd potwierdzić u źródła, zostaje wnioskowanie z treści błędu (500 przy metadanych,
  503 przy tworzeniu wdrożenia).

---

## Stan bieżący

| | |
|---|---|
| Testy kolektora | **73** (`python -m unittest discover -s tests`) |
| Testy strony | **72** (`cd tests/frontend && npx playwright test`) |
| Workflowy | `zbieraj` co godzinę o :19 · `watchdog` raz na dobę · `testy` przy zmianie kodu i o 4:17 · `odkryj` na żądanie |
| Orientacja mieszkania | Sypialnia na **południe**, Salon i Kuchnia na **północ** — to nie ozdoba, z tego bierze się rada o kolejności otwierania okien |
| Czujniki | cztery pokoje na wysokości ok. 80–90 cm (wyrównane 19.08) + klimatyzator FERSK VIND 2 w salonie |

## Co czeka

- **Przypomnienie na wrzesień** (Routine `trig_01SWg8Vf2tK6uTJ9afZzTQba`, 1.09 o 6:00 UTC)
  o dwóch pozycjach z `TODO.md`: „Skutek wietrzenia" i „Model cieplny pokój ↔ dwór".
- Ochrona gałęzi — opisana wyżej, wymaga decyzji o deploy key albo pozostania przy
  hooku lokalnym.
