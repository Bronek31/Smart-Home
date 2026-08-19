# Kontekst pracy

Notatka przekazania: co zostało zrobione, co świadomie odrzucone i o czym trzeba
wiedzieć, zanim ruszy się ten projekt dalej. `README.md` opisuje, **jak to działa**;
ten plik mówi, **dlaczego tak** i **na co uważać**. Pomysły na przyszłość siedzą
w `TODO.md`.

Stan na 19.08.2026, po przeglądzie wykrywania wietrzenia. Wszystkie workflowy zielone.

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

## Przegląd wykrywania wietrzenia (19.08, wieczór)

**Detektor wietrzenia nie zawiódł raz — on nie zadziałał ani razu.** Przez pięć dób
zbierania narysował dokładnie trzy pasma, wszystkie 19.08 między 12:49 a 15:23, czyli
w godzinach, w których czujniki były przenoszone i trzymane w rękach. Prawdziwego,
kilkugodzinnego wietrzenia tego samego wieczoru nie zobaczył wcale.

Powód jest arytmetyczny, nie subtelny. Próg wynosił **0,7 g/m³ wilgotności bezwzględnej
w oknie dwóch godzin**, a zmierzony na pełnej historii największy ruch dwugodzinny
w mieszkaniu — po odjęciu jednego okna z przenoszenia czujników — to **0,50 g/m³**;
w Salonie 0,33, w Kuchni 0,46. Próg stał wyżej niż fizycznie osiągalne maksimum, więc
mógł się odezwać wyłącznie na artefakcie. Tak też się stało.

### Co jest teraz

- **λ zamiast gramów.** Wykrywamy ułamek dostępnej różnicy domykany na godzinę
  (`d(x)/dt = λ·(x_dwór − x_pokój)`), więc próg znaczy to samo przy różnicy 4 g/m³
  w upał i przy 0,6 g/m³ w parny wieczór. `WIETRZ.tempo = 0,10/godz.`
- **Dwa kanały.** Temperatura i wilgotność bezwzględna; wystarczy jeden. 19.08 różnica
  wilgotności z dworem spadła poniżej 0,5 g/m³ — okno nie miało czego wymieniać w tym
  kanale — a temperatura Sypialni zjechała o 1,9 °C. Łazienka, jedyny pokój bez okna,
  nie ruszyła się o 0,1 °C. Trudno o czystszy sygnał, a stary algorytm patrzył obok.
- **Strażnik odbicia.** To on odsiewa rękę na czujniku, i **tylko on** — filtr skoków
  tu nie pomaga. Ciepła dłoń podnosi naraz temperaturę i wilgotność względną, a w
  wilgotności bezwzględnej te dwa umiarkowane skoki mnożą się (19.08 w Sypialni
  +0,5 °C i +5 punktów dało +1,57 g/m³, ponad trzy razy więcej, niż ten pokój
  kiedykolwiek zrobił naturalnie). Potem wartość opada — a opadanie w stronę dworu
  to dokładnie to, czego detektor szuka. Zasada: **jeśli pokój przed chwilą oddalił
  się od dworu szybciej, niż potrafi sam z siebie, to powrót nie jest wietrzeniem.**
  Baza strażnika zostaje ta najwcześniejsza; gdyby szczyt zaburzenia stawał się nowym
  punktem odniesienia, przepuszczony zostałby cały ogon artefaktu.
- **Próg szumu.** Bez niego dzielenie małego ruchu przez małą różnicę robi z jednego
  kroku kwantyzacji czujnika λ = 0,19/godz. Zmierzone i wstawione: `WIETRZ.ruch`.
- **Odniesienie z dworu liczone w każdym punkcie**, nie zamrażane na starcie epizodu.
  19.08 dwór stygł razem z mieszkaniem i przy zamrożonym odniesieniu Sypialnia
  „domknęła" 106% różnicy — ułamek przebijał jedynkę i logarytm zwracał śmieci.
- **`wartoscW()` ma tolerancję.** Wcześniej brało najbliższy odczyt z dworu niezależnie
  od tego, jak odległy — przy dłuższej ciszy Open-Meteo pokój porównywałby się z pogodą
  sprzed wielu godzin i nikt by się o tym nie dowiedział.

**Pasma poszły też nad temperaturę.** Dopóki liczyła się sama wilgotność, jedno miejsce
wystarczało. Od kiedy w letni wieczór całą robotę wykonuje temperatura, pasmo wyłącznie
pod wilgotnością bezwzględną zostawiało z pytaniem „to skąd to wietrzenie" — patrzącego
na wykres, na którym nic nie widać. Wilgotność względna pasm nie dostaje: nie jest
kanałem wykrywania. Licznik i legenda stoją teraz przy obu wykresach z pasmami.

**λ = 0,10/godz. jest dobrane pomiarem, nie z głowy.** Przy tej wartości wykryte zostają
wieczorne wietrzenia z 19.08 w Salonie i Sypialni, a Łazienka nie odzywa się ani razu.
Przy 0,08 dochodzi wprawdzie słaba Kuchnia, ale razem z nią nocne stygnięcie Łazienki
przez ściany. **Czego nadal nie widać:** Kuchnia 19.08 domknęła tylko 13% różnicy przez
trzy godziny i przy raportach co godzinę nie da się tego odróżnić od stygnięcia przez
ściany. To jest świadomy sufit, nie przeoczenie.

### Filtr skoków — pomylił się o 17 sekund

Notatka z poprzedniej sesji mówiła, że filtr uznał za wyskok 0 z 1102 odczytów i że
„jest napisany na pojedynczy odczyt, który skacze i wraca". Prawdziwy powód jest
ostrzejszy: `SPIKE.rise` wynosił **12 minut**, a 19.08 od odczytu bazowego (13:46:23)
do szczytu (13:58:40) upłynęło **12 min 17 s**. Cofnięcie po poziom sprzed wzrostu
zatrzymywało się o jeden odczyt za wcześnie, za bazę brało już podniesione 26,3 °C
i skok wychodził na 1,1 zamiast 1,6 °C — czyli pod progiem 1,5.

Przy 15 minutach filtr łapie ten epizod i — zmierzone na pełnej historii — **nie rusza
niczego innego**; wynik jest identyczny aż do 30 minut. Zmienione po obu stronach
(`index.html` i `fetch.py`), z testem pilnującym, że obie kopie się zgadzają.

**Wiersze zostają w CSV** — decyzja z poprzedniej sesji obowiązuje i nie była ruszana.
Zmieniło się tylko to, co widać na wykresie i co wchodzi do agregatów dobowych:
`data/dzienne.csv` przeliczone, maksimum Łazienki na 19.08 spadło z 27,4 na 26,6 °C
(n z 25 na 23). Nic innego się nie ruszyło. Filtr nadal ma swój przycisk i da się
wyłączyć — a wykrywanie wietrzenia odrzuca artefakt **także przy wyłączonym filtrze**,
co pilnuje osobny test.

### Testy, które naprawdę testują

Dawna fikstura wietrzenia zrzucała wilgotność Salonu z 46% na 30%, czyli o ok. 3,6 g/m³
— **dziewięć razy** więcej, niż ten pokój kiedykolwiek zrobił. Przechodziła przy progu
0,7, przeszłaby przy 2,0 i przy 3,0, więc sprawdzała wyłącznie, że kod się wykonuje.

Teraz pokój po prostu dąży do temperatury dworu, a wilgotność **bezwzględna** zostaje
stała (podnosimy względną dokładnie tyle, ile trzeba) — inaczej dawny algorytm wykryłby
epizod przez sam spadek wilgotności i test niczego by nie dowodził. Doszła fikstura
`rekaNaCzujniku`, odtworzona z prawdziwego epizodu.

Puszczone przeciwko kodowi sprzed poprawki, na wszystkich 24 godzinach doby:

| Test | Stara wersja |
|---|---|
| wietrzenie widać po samej temperaturze | **nie wykrywa w 24/24 godzin** → test odrzuca starą wersję |
| czujnik w dłoni nie jest liczony jako wietrzenie | **wykrywa w 24/24 godzin** → test odrzuca starą wersję |
| to samo bez filtra skoków | jw. |
| próg jest ułamkiem, nie skokiem w gramach | nie ma czego czytać → odrzuca |
| odczyt z dworu sprzed wielu godzin | brak tolerancji → odrzuca |
| **spokojne mieszkanie nie generuje wietrzeń** | przechodzi w obie strony — **to strażnik, nie test**, i tak ma być powiedziane wprost |

Okna epizodów fikstura wybiera z własnych danych, szukając godzin z odpowiednią
różnicą wobec dworu — nie odlicza ich od „teraz". Inaczej przy uruchomieniu o złej
porze doby dwór bywałby cieplejszy od pokoju i wietrzenia nie wykryłby żaden algorytm.
To ten sam błąd, na którym projekt przejechał się już przy zakresie „dziś".

### Przy okazji

- **Watchdog chodzi co 6 godzin**, nie raz na dobę. Próg alarmu to 6 godzin ciszy, więc
  przy jednym sprawdzeniu dziennie awaria tuż po przebiegu leżała niezauważona prawie
  dobę — a Tuya trzyma tylko 7 dni logów.
- **`sw.js` podbity na `smart-home-v2`**, bo zmieniła się zawartość szkieletu.

### Świadomie **nie** zrobione teraz

**Granica `purge_before` a stan włącznika.** `collapse_power` zostawia wyłącznie zmiany
stanu, więc gdyby klimatyzator przekroczył granicę `TUYA_SINCE` włączony, wiersz
„włączony" zostałby skasowany i strona uznałaby, że sprzęt stoi. Dziś to czysta teoria:
po ustawieniu granicy na 14.08 urządzenie nie ma w CSV ani jednego wiersza. Naprawa
wymaga wyłamania włączników spod granicy historii, czyli decyzji o tym, że `TUYA_SINCE`
przestaje znaczyć „nic starszego" — i to jest decyzja do podjęcia, nie oczywistość.

---

## Co powstało we wcześniejszej sesji

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

- **Filtrowanie skoków po stronie strony zostaje.** Był raz usunięty razem z przyciskiem,
  potem **przywrócony na życzenie**. *(Diagnoza „0 z 1102 odczytów, bo filtr jest napisany
  na pojedynczy odczyt" okazała się niepełna — prawdziwy powód to okno `SPIKE.rise`
  krótsze o kilkanaście sekund od rozstawu odczytów w narastaniu; opisane wyżej.)*
- **Odczyty z przenoszenia czujników zostają w danych.** Próbowaliśmy dwóch podejść:
  usunięcia wierszy (`TUYA_POMIN`) i odtworzenia ich interpolacją (`TUYA_ODTWORZ`).
  Oba zostały cofnięte — nienaturalny moment przenoszenia ma zostać jako ślad tego,
  co się działo. Kod obu mechanizmów jest w historii gita, gdyby kiedyś był potrzebny:
  commity `c54379c` i `75720f9`, cofnięte przez `b67a533`. **Decyzja obowiązuje** —
  naprawa filtra skoków jej nie ruszyła: wiersze nadal leżą w CSV, zmieniło się tylko
  to, co filtr ukrywa na wykresie i w agregatach dobowych.
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
  poprawny odczyt to `policzWietrzenia(od).wietrz[d.id]`. Testy strony korzystają z tego
  wprost, zamiast czytać ostatnią kolumnę tabeli — tabela ma własny przełącznik zakresu.
- **`python3 -m unittest` cache'uje bajtkod.** Po podmianie stałej w `fetch.py` w trakcie
  eksperymentu testy pokazywały wynik sprzed zmiany. `find . -name __pycache__ -prune
  -exec rm -rf {} +` przed rozstrzygającym przebiegiem.
- **`githubstatus.com` jest zablokowany** przez proxy tej sesji — awarii Pages nie da
  się stąd potwierdzić u źródła, zostaje wnioskowanie z treści błędu (500 przy metadanych,
  503 przy tworzeniu wdrożenia).

---

## Stan bieżący

| | |
|---|---|
| Testy kolektora | **75** (`python -m unittest discover -s tests`) |
| Testy strony | **80** (`cd tests/frontend && npx playwright test`) |
| Workflowy | `zbieraj` co godzinę o :19 · `watchdog` co 6 godz. o :41 · `testy` przy zmianie kodu i o 4:17 · `odkryj` na żądanie |
| Orientacja mieszkania | Sypialnia na **południe**, Salon i Kuchnia na **północ** — to nie ozdoba, z tego bierze się rada o kolejności otwierania okien |
| Czujniki | cztery pokoje na wysokości ok. 80–90 cm (wyrównane 19.08) + klimatyzator FERSK VIND 2 w salonie |

## Co czeka

- **Przypomnienie na wrzesień** (Routine `trig_01SWg8Vf2tK6uTJ9afZzTQba`, 1.09 o 6:00 UTC)
  o dwóch pozycjach z `TODO.md`: „Skutek wietrzenia" i „Model cieplny pokój ↔ dwór".
- Ochrona gałęzi — opisana wyżej, wymaga decyzji o deploy key albo pozostania przy
  hooku lokalnym.
