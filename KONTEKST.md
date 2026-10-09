# Kontekst pracy

Notatka przekazania: co zostało zrobione, co świadomie odrzucone i o czym trzeba
wiedzieć, zanim ruszy się ten projekt dalej. `README.md` opisuje, **jak to działa**;
ten plik mówi, **dlaczego tak** i **na co uważać**. Pomysły na przyszłość siedzą
w `TODO.md`.

Stan na 8.10.2026: pobieranie przyrostowe w kolektorze, czujniki w doniczkach
w przygotowaniu (`ROSLINY.md`). Przegląd wrześniowy niżej, sekcje z sierpnia jako historia
decyzji.

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

## 8.10 — rośliny w przygotowaniu, kolektor pobiera przyrostowo

Właściciel kupił trzy czujniki Tuya do doniczek (fikus i skrzydłokwiat w Salonie,
azalia w Kuchni) i chce powiadomień „podlej" / „przestaw" na Androida i iPhone'a.
Warunek wprost: **odczyty z doniczek nie mieszają się z dzisiejszą stroną**, rośliny
dostają osobną zakładkę. Plan, pomiary i otwarte pytania są w `ROSLINY.md`, czynności
właściciela w `ROSLINY-INSTRUKCJA.md`.

**Limit Tuya to dolary, nie liczba zapytań.** Wyszukiwarka podawała „26 000 zapytań na
miesiąc" i plan zaczynał się od alarmu „98% limitu". Zrzut z panelu, który przysłał
właściciel, pokazał coś innego:
- trial to pakiet 0,20 USD na miesiąc kalendarzowy;
- zapytania z runnerów GitHuba idą jako `CLOUD_API_FOREIGN`, 3,71 USD za milion,
  czyli pakiet starcza na ok. 54 000 zapytań;
- 6229 zapytań od 1.10 = 0,0231 USD, co do kilku zgodne z wyliczeniem 29 zapytań ×
  liczba przebiegów. Liczy się więc każde zapytanie, także o token i nieudane;
- prognoza na październik przy dawnym pobieraniu to ok. 47%; po zmianie 8.10 ok. 20%.
  **Znowu: najpierw zmierz.**

**Dlaczego mimo to pobieranie przyrostowe.** Czujnik w doniczce przy pełnym oknie 7 dni
kosztowałby ok. 50 stron na przebieg, czyli więcej niż wszystkie pokoje razem. Model
z naklejki (C3007) według Zigbee2MQTT potrafi zalewać logi.

Kursor `pobrane_do` w manifeście, zakładka 6 godz., okno czytane odcinkami po jednej
stronie:
- odcinek zmieścił się na stronie: następny dwa razy dłuższy;
- nie zmieścił się, a wpisy przyszły rosnąco: przesunięcie po znacznikach czasu;
- inaczej: odcinek o połowę krótszy;
- zakładkę porzuca się, gdy sama się nie mieści.

Kursor nigdy się nie cofa i nie przeskakuje za „najnowszy widziany wpis". Pierwsza wersja
dzieliła okno na pół przy 10 stronach na odcinek i przy kolejności od najnowszego utykała
na zawsze: każdy przebieg zjadał budżet na te same podziały. Wyłapał to test
`test_kolejnosc_malejaca`, zanim kod trafił na main. Symulacja przy domyślnym budżecie
(30 zapytań na czujnik): zalew co 2 s przez 3 godz. domyka się w 2 przebiegach przy
kolejności rosnącej i w 7 przy malejącej.

Przegląd przed wdrożeniem (dwóch recenzentów, każde znalezisko odtworzone na atrapie)
znalazł jeszcze sześć dróg do zgubienia wpisów. Każda ma teraz test, który odrzuca
pierwszą wersję:
- **krótka strona z jedną chwilą** (jeden wiersz albo trójka z jednego znacznika) przy
  kolejności od najnowszego wyglądała na „rosnąco" i kursor przeskakiwał starsze wpisy;
- **otwarty `start_time`**: strona po 100 wpisów kończy się w środku trójki odczytów,
  więc wznawiamy od milisekundy przed ostatnim wpisem, a nie od niego;
- **zakładka po długiej przerwie** jest teraz czytana osobno, zamiast porzucana razem
  z przepełnionym oknem;
- **zerwana sieć w połowie** nie wyrzuca już tego, co przyszło, ani postępu kursora;
- **v2 „sukces, zero wpisów"** nie zostaje zamkiem na cały przebieg: przyrostowe idzie
  tylko przez v1;
- **ponad 100 wpisów w dwie minuty**: tu jedyny raz stronicujemy (do 5 stron).

Do tego `--discover` przeżywa dziwne specyfikacje (`null`, `values` niebędące
obiektem) — każde urządzenie osobno, jedno nie przerwie przebiegu.

**Pierwszy przebieg na żywo** (8.10, 16:19 UTC, przebieg 37807716639): 75 zapytań,
ok. 17 na pokój, i 9 nowych odczytów przy 6418 już zapisanych, czyli bez dziur.
- 17 zapytań na pokój to dokładnie wariant „od najnowszego" z symulacji przeglądu
  (od najstarszego byłoby 6–7), więc **Tuya v1 oddaje logi najpewniej od
  najnowszego**.
- Dawny komentarz o „ucinanych najnowszych" był mylącą poszlaką. Dobrze, że algorytm
  nie zakładał żadnej kolejności.
- Kursory `pobrane_do` są w manifeście; następne przebiegi pytają o jedną stronę na
  czujnik.

Przy okazji:
- **Najpierw v1, potem v2.** Dawna próba v2 kosztowała najpewniej zapytanie w każdym
  przebiegu: v2 wymaga parametru `codes`, którego nie wysyłamy.
- **Licznik zapytań na końcu logu przebiegu.**
- **`--discover` czyta specyfikację raz, nie dwa razy.** Dla urządzeń spoza manifestu
  dochodzą pola do ustawiania, bieżące wartości i tempo wpisów z ostatniej godziny (do
  3 stron).
- **Integracja Claude'a z GitHubem czyta przebiegi, ale nie może ich uruchamiać (403).**
  Dlatego `odkryj.yml` rusza też po zmianie własnego pliku na main.

**Tor roślin (etap 2, wieczorem 8.10).** `fetch.py` zbiera czujniki z `rosliny.json`
osobno: do `data/rosliny/`, z kursorami i skalami w `data/rosliny/stan.json`.
- Tor pokoi pomija je zawsze — także przy pustym `TUYA_DEVICE_IDS` i także wtedy, gdy
  `rosliny.json` jest zepsuty (kategoria Tuya `zwjcy`).
- Tor roślin rusza po zapisaniu manifestu pokoi, w `try/except` i z limitem 300 s
  (`SIGALRM`). Literówka w ręcznym pliku, wyjątek w obliczeniach czy odmowa Tuya
  kończą się wpisem `blad` i alertem w stanie, a nie czerwonym kolektorem. Kursory
  i skale przy tym zostają.
- Obliczenia (`rosliny.py`) są czyste i to one wydają werdykt. Strona będzie go tylko
  wyświetlać, więc nie powstaje nowa para bliźniaczych stałych JS/Python.
- W godzinie parowania gleba przychodziła co ok. 30 s, w spokoju 1–3 razy na godzinę.
  Zakładka 1 godz. i przerzedzanie do zmian plus wiersza na godzinę i tak zostają.

**Przegląd toru roślin (8.10 wieczorem)** — dwóch recenzentów, wszystko odtworzone
na atrapach. Przed scaleniem na main poprawione:
- **Błąd toru gubił kursory i nie docierał do watchdoga.** Stan nadpisywało samo
  `{updated, blad}`, więc następny przebieg ciągnął logi od nowa, a watchdog bez
  `alerty` zamykał zgłoszenie. Teraz stan zostaje, dochodzi `blad` i alert; kursory
  zapisują się zaraz po dopisaniu CSV.
- **`podlania()` było kwadratowe.** Przy glebie co 30 s 60 dni to dziesiątki minut,
  czyli zabite zadanie przed commitem pokoi. Teraz liniowe (kolejka monotoniczna),
  plus limit czasu toru i martwa strefa ±1 dla gleby w przerzedzaniu.
- **Pokój wpisany jako „czujnik" wyłączał się po cichu.** Teraz zostaje pokojem,
  a tor roślin zgłasza błąd konfiguracji.
- **Wbicie sondy uczyło się jako podlanie,** gdy „od" było choć trochę za wcześnie
  albo bez strefy. Teraz „od" musi mieć godzinę i strefę, a nauka startuje godzinę
  później.
- **„Przed" brało najniższy odczyt tuż przed skokiem.** Przy zanurzaniu azalii to
  sonda w powietrzu. Teraz to mediana 2–6 godz. przed skokiem, a podlanie uczy tylko
  wtedy, gdy mediany różnią się o 10 punktów (poprawienie sondy 30 → 18 → 30 nie
  uczy).
- Drobniejsze: szczyt dopiero 6 godz. po podlaniu, werdykt „czujnik" przy wyjętej
  sondzie i przy starej glebie, „nauka" bez `sucho`, doby światła od lokalnej
  północy, brak `Infinity` w stanie, pusta lista czyści alerty, pierwszy przebieg
  bierze dobę, a nie 7 dni.

---

## Przegląd z 27.09 — wietrzenie odchodzi, przychodzi zima

Właściciel poprosił o przegląd wrześniowych pomysłów i całej strony, potem zdecydował:
wykrywanie wietrzenia odpuścić, odtwarzanie historii schować, resztę zrobić według
najlepszej oceny i wypuścić na main. Po drodze przyszły dwie twarde informacje: rano
w łazience chodzi **farelka** (zimą codziennie, „jak idę się myć"), a **kaloryfery
ruszają 1.10**. Obie zmieniły kilka decyzji.

### Kolektor: winny jest harmonogram GitHuba

Do 26.08 mediana odstępu między zapisami wynosiła 55 min, od 27.08 — 3,5–4,5 godz.,
bez żadnej zmiany w kodzie. Przebiegi nie padają, tylko nie są tworzone na czas:
watchdog z cronem co 6 godz. startował z opóźnieniem 2,5–5,5 godz. Zgłoszenia #2 i #3
„Kolektor stoi" (27 i 28.08) były fałszywe z tego powodu; #6 (13.09) było prawdziwe —
wygasł trial Tuya, **po miesiącu**, a nie po pół roku, jak mówiło README.

Naprawa wymaga ręki właściciela (token + cron-job.org wołający `workflow_dispatch`),
instrukcja w README. Rozważone i odrzucone: łańcuch przebiegów, które same się
wywołują z `sleep` (godzina biegnącego runnera na każdy zapis — nadużycie Actions),
i Routine Claude'a (24 sesje dziennie na jedno wywołanie API).

**Czujniki liczone do chwili zbiórki.** Przy każdym opóźnieniu strona mówiła
„0/4 OK · 4 uwaga" obok zdarzenia „to nie wina czujników". Wiek raportu mierzy się
teraz do `updated` z manifestu, więc oba rodzaje zdarzeń mogą stać obok siebie
i żadne nie przeczy drugiemu.

### Wykrywanie wietrzenia — usunięte

7 epizodów w 44 dobach, zero od 8.09 — a w tym czasie wilgotność urosła z 50–55%
do 60–71%, a pokoje ostygły z 22 do 19,5 °C. Od 8.09 w żadnym pokoju z oknem
temperatura nie spadła o więcej niż 0,7 °C w dwie godziny. Właściciel nie pamiętał,
czy wietrzył — czyli nie było nawet etykiety, żeby rozstrzygnąć, czy detektor ślepnie
jesienią. Decyzja: **usunąć, nie wyłączyć** (odwrotnie niż odtwarzanie, które ma wrócić).
Razem z nim poszły pasma klimatyzatora, kolumna w tabeli, licznik i legenda, 9 testów.
Fikstury `wietrzenie` i `rekaNaCzujniku` zostają — korzystają z nich testy przybliżania
i filtra. Rada „czy wietrzyć teraz" zostaje, bo liczy się z prognozy, nie z detektora.

### Farelka, czyli trzy miejsca, które myliły impuls z trendem

Odczyty łazienki z 27.09: 20,5 → 26,9 °C w pół godziny, powrót do 21 w dwie. Zmierzone,
co z tym robiła strona:

| miejsce | co robiło | co robi teraz |
|---|---|---|
| filtr skoków | `SPIKE.rise` przesuwał bazę w górę razem z rampą; w połowie wzrostu baza stała na 21,7 °C, ogon do niej „wracał" w 90 min, więc wycięte zostało 17 odczytów z samego środka — na wykresie garb o złej godzinie | skok musi startować **ze spokojnego poziomu** (w oknie `rise` przed bazą nic nie odbiega od niej o `back`); ręka na czujniku z 19.08 łapie się dalej. Agregaty przeliczone: zmieniły się dwa wiersze, oba prawdziwe zdarzenia (farelka i prysznic z 24.08) |
| kafel trendu | przez godzinę „28° za 0,5–4 h", także gdy łazienka już stygła, potem „18° za 2 h" przy stałych 20,8 °C — w oknie regresji wciąż siedziała farelka | powyżej `TREND_MAX` = 0,7 °C/godz. milczy. Zmierzone na 44 dobach (regresja 4 h): ściany i słońce ≤ 0,5, letnie wietrzenia 0,86–1,81, farelka 2,24 |
| skala barw rzutu | skrajne odczyty → 19,2–27,0 °C, cztery pokoje w 19,9–21,0 w jednym odcieniu | 5. i 95. percentyl średnich godzinowych; średnia godzinowa, bo przy zmianie czujnik raportuje co 2 min i pół godziny farelki ważyłoby w surowych odczytach tyle, co pół doby spokoju |

**Cena, przyjęta świadomie:** w dniach z farelką oś temperatury obejmuje jej szczyt
(27.09: 19–27 °C) i pokoje dostają mniej wysokości. Obcięcie osi odpada — „nic nie może
wychodzić poza wykres" to warunek postawiony wprost 22.08 — a chowanie prawdziwego
grzania było właśnie tym, co tu naprawiamy. Zostają przybliżanie palcami i wyłączenie
łazienki przełącznikiem nad wykresami.

Pierwsza wersja komentarza przy `TREND_MAX` twierdziła „naturalny ruch nie przekroczył
1 °C/godz." — pomiar pokazał 1,81 przy letnim wietrzeniu. Znowu: **najpierw zmierz,
potem wpisz liczbę do komentarza.**

### Sezon grzewczy

- **Próg pleśni zamiast 65%.** PN-EN ISO 13788: `θsi = θe + fRsi·(θi − θe)`, kłopot przy
  80% na powierzchni; fRsi = 0,70 z normy (mierzyć nie będziemy — czujniki zostają na
  miejscach). Obie
  strony (kolektor i strona) mają te same stałe, pilnuje test. Na prawdziwych danych:
  alarm 23–26.09 (próg 65–72%), cisza 27.09 po południu — stary próg krzyczał w każdy
  z tych dni przez całą dobę. Zgłoszenie #7 (założone jeszcze według 65%) watchdog
  zamknie sam, gdy przez dobę żaden pokój nie przekroczy nowego progu.
- **Wykres wilgotności względnej bez dworu,** z kreskowaną linią progu dla średniej
  temperatury mieszkania. Kolor linii spoza palety pokoi — pierwszy pomysł (`--bad`)
  był identyczny z kolorem Salonu.
- **Rady wietrzenia:** poniżej `CIEPLO_W_DOMU` (24 °C) chłód z dworu jest kosztem, nie
  zaletą — werdykt „Przewietrz krótko i szeroko". Rada „sypialnię od południa otwieraj
  krótko, bo słońce" tylko w ciepłym mieszkaniu.

### Telefon

Pierwszy ekran to były cztery wiersze diagnostyki, pogoda z radą leżała ~4500 px niżej,
tabela zakresów przewijała się w bok bez wskazówki. Kolejność na wąskim ekranie
przestawia CSS (`display:contents` na obudowach układu dwukolumnowego i `order`),
bez ruszania DOM-u — na komputerze układ bez zmian, pilnuje tego strażnik. Tabela ma
wariant kompaktowy (min–max w jednej kolumnie), diagnostyka łączności jest w `<details>`
i rozwija się sama przy kłopocie.

### Strefa komfortu i noce w sypialni

Dwie nowe sekcje na życzenie, po tym, jak właściciel odrzucił prognozę pleśni („alerty
wystarczą") i poprosił o rzeczy „ładne i użyteczne". Wybrane spośród kilku, bo działają
na danych, które już są, i dają się sprawdzić własnym doświadczeniem:

- **Strefa komfortu** — wrzesień: Salon 80% czasu w polu, pozostałe 58–65%, poza polem
  głównie za wilgotno. Wykres trzymany poza `state.charts` (tam są wykresy z osią czasu,
  które przybliżanie przesuwa razem — strażnik testu to wyłapał).
- **Noce w sypialni** — wrzesień: średnio 22,6 °C nocą, 0 z 14 nocy w strefie optymalnej do snu (16–19 °C).
  Od 1.10 to liczba, na którą da się wpłynąć zaworem.

**Odrzucone po pomiarze: dziennik łazienki (prysznic, farelka).** Właściciel bierze
prysznic prawie codziennie, a przez 44 doby czujnik w łazience wyraźnie zobaczył
prysznic raz — czujniki raportują przy zmianie temperatury o 0,5 °C albo co godzinę,
więc sama para ich nie budzi.

Przy okazji `neededMonths()` ładuje zawsze ostatnie `RYTM_DNI` dób, nie tylko zakres
wykresów — na początku miesiąca w zakresie „dziś" rytm doby i noce widziały wcześniej
tylko bieżący miesiąc.

### Rzut „wilgotność a pleśń", kalendarz, widżety

- **Strefa optymalna do snu zostaje 16–19 °C.** Właściciel sprawdzał, czy to nie za
  zimno (jego komfort dzienny to 20,5 °C), i zdecydował: zalecenie to zalecenie, ma się
  tylko nazywać „strefą optymalną do snu". Źródła: NHS / Sleep Charity 16–18 °C,
  Sleep Foundation 15,6–19,4 °C (strony pierwotne zablokowane przez proxy sesji —
  wartości z wyników wyszukiwania, zgodne między sobą).
- **Rzut: tryb „wilgotność a pleśń"** — kolor to zapas do progu pleśni, nie sama
  wilgotność. Przy odtwarzaniu historii rzut wraca do temperatury (próg liczy się
  z bieżącej pogody).
- **Kalendarz historii** z `dzienne.csv` — nie potrzebuje plików miesięcznych.
- **Widżety — zrobione i wycofane tego samego dnia.** Były: `data/teraz.json` z kolektora,
  skrypt Scriptable na iPhone'a z testem na atrapie API, instrukcja KWGT na Androida.
  Właściciel zainstalował stronę w Chrome jako aplikację i uznał, że to wystarcza; kod
  jest w historii gita (commit „Widżety na telefon…"). Przy okazji wyszło, że na iPhonie
  dodana do ekranu strona wchodziła nagłówkiem pod pasek stanu (`black-translucent` bez
  `viewport-fit=cover`) — poprawione.

### Farelka pod czujnikiem i znane artefakty

Czujnik w łazience wisiał tuż nad farelką, więc 27.09 rano mierzył strumień gorącego
powietrza, nie łazienkę. Właściciel przestawił go 27.09 ok. 20:30 UTC poza nawiew,
a poranek trafił do `artefakty.json` — nowej, ręcznej listy przedziałów, które nie
opisują pokoju. To nie jest powrót odrzuconego `TUYA_POMIN`: wiersze zostają w CSV,
znika tylko widok i agregaty, dokładnie tak jak przy filtrze skoków, i jednym
przełącznikiem da się je pokazać.

Plik leży obok `fetch.py`, a nie w `data/`, bo to konfiguracja, nie odczyt; ścieżka liczy
się od pliku, żeby test odtwarzania agregatów w katalogu tymczasowym widział tę samą
listę. Pierwsza wersja pliku miała w opisie cudzysłów zamknięty zwykłym `"` — JSON się
nie parsował, a kolektor po cichu uznawał listę za pustą. Złapał to test
`test_prawdziwy_plik_artefaktow_jest_poprawny`; zostaje właśnie po to.

### Luka po artefakcie i odświeżanie

Pierwsza wersja artefaktów zostawiała na wykresie dziurę: po schowaniu farelki między
sąsiednimi odczytami były ponad 4 godziny, a linia łączy się tylko przez 3 (spanGaps).
Właściciel zobaczył to od razu jako „lukę w danych". Teraz `mostkuj()` dokłada przy
rysowaniu punkty pomocnicze co najwyżej godzinę od siebie, a odcinek rysuje się kropkami;
w rytmie doby kratki artefaktu są odtwarzane z sąsiadów. Granica zostaje: prawdziwą ciszę
czujnika dalej widać jako przerwę.

Odświeżanie: `odswiezDane()` przy powrocie do karty (≥ 2 min) i co 10 min; przerysowuje
tylko przy zmianie `updated`. Farelka 27.09 o 20:55 UTC była pierwszą po przestawieniu
czujnika — prawdziwe grzanie, na liście artefaktów jej nie ma.

### Odtwarzanie historii — schowane, nie usunięte

Na życzenie. Przełącznik `ODTWARZANIE`, a testy włączają kod flagą
`window.odtwarzanieWlaczone`, żeby nie zbutwiał — powrót to zmiana jednej linii.

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

### Fałszywe wietrzenie w upał — poprawka z 20.08

Zgłoszone przez użytkownika z twardą prawdą: okna zamknięte od 8 do 18, bo na dworze
było cieplej niż w domu, otwarte od 18. Detektor narysował wietrzenie od 13 do 16
w czterech pokojach naraz.

Przyczyna jest w modelu, nie w progu. Ściany i słońce robią to samo co otwarte okno —
przesuwają pokój w stronę dworu — tylko wolniej. A parę produkuje kuchnia i prysznic,
więc wilgotność bezwzględna też goni dwór bez żadnej wymiany powietrza. Zmierzone
na tej dobie, per krok:

| kanał | okna ZAMKNIĘTE | okna OTWARTE |
|---|---|---|
| wilgotność | λ do **2,45**/godz. | milczy (różnica poniżej progu) |
| temperatura | λ do **0,18**/godz. | pewne kroki od **0,25**/godz. |

Przemiatanie progu pokazało, że przy obu kanałach fałszywek nie da się zejść poniżej
sześciu przy ŻADNYM progu — bo to wilgotność je produkuje. Przy samej temperaturze
i progu 0,20 jest **zero fałszywek** i pięć epizodów, z których każdy trafia w okno
otwarte. Dlatego wyzwala już tylko temperatura, a kanał wilgotności zostaje wyłącznie
jako strażnik odbicia.

Wniosek ogólniejszy, wart zapamiętania: **„wystarczy, żeby którykolwiek kanał zadziałał"
to zła reguła, gdy kanały mają różne zaburzenia.** Suma dwóch czułych detektorów jest
czulsza na zaburzenia niż na zjawisko.

**Rada „czy wietrzyć teraz" miała tę samą ślepotę i też została naprawiona.** Patrzyła
wyłącznie na wilgotność, więc 19.08 o 20:30 mówiła „wietrzenie bez wpływu" — przy 21,0 °C
na dworze, 24,7 w mieszkaniu, otwartych oknach i mieszkaniu stygnącym o 2 °C. Kafel
przeczył pasmom rysowanym dwa ekrany wyżej. Przy okazji wyszedł drugi błąd: gdy na dworze
było suchsze, ale znacznie cieplejsze powietrze, wychodziło „dobry moment na wietrzenie",
mimo że `oknoWietrzenia()` takie godziny odrzuca od dawna i z tego samego powodu. Oba
doradcy patrzą teraz na to samo, a `airingTip(now, home, dom)` bierze temperaturę
mieszkania parametrem, żeby całą tabelkę ośmiu werdyktów dało się przejechać testem.

Ramka prognozy nazywa się teraz **„Najsuchsze powietrze"**, nie „Najlepiej wietrzyć".
Odpowiada wyłącznie na pytanie o suchość i dawny nagłówek obiecywał więcej, niż liczył —
w letni wieczór najlepiej otworzyć okno teraz, dla chłodu, a najsuchsze powietrze
przychodzi nad ranem. Oba zdania były prawdziwe, tylko o czym innym.

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

### Wygładzanie tylko przy pełnym oknie

Średnia z dwóch odczytów zamiast trzech to inna operacja i ma inne ograniczenie: przesuwa
punkt o **połowę kroku** do sąsiada, więc przy skoku 0,2 °C odsuwa linię o 0,1 °C, podczas
gdy wnętrze serii nie wychodzi poza 0,067. Punkt bez pełnego okna — pierwszy, ostatni
i każdy przy dłuższej przerwie w raportach — zostaje więc surowy.

Na prawdziwych danych brzegiem jest **ostatni odczyt**, czyli „teraz" — ten, na który się
patrzy — a przy wietrzeniu potrafi lecieć 0,5 °C w dwanaście minut. Rysowanie go z połową
tego skoku byłoby kłamstwem dokładnie tam, gdzie boli.

Usterka jest starsza niż ta sesja (siedzi w `23f0142`), a wyszła dopiero przy pushu o innej
porze doby niż poprzednie. Doszedł test bez zegara: podaje własną serię ze stromym skokiem
na brzegu i długą przerwą w środku, i sprawdza regułę, a nie liczbę.

### Krawędzie wykresu „dziś"

Zgłoszone jako „na początku i końcu wygląda to beznadziejnie". Zmierzone: 20.08 starty
serii rozjechane o 46 minut, końce o 53 — przy 8,5-godzinnym oknie po dziesiątej części
szerokości z każdej strony. Przyczyna jest strukturalna: każdy czujnik Tuya ma własną
fazę raportowania w godzinie i ta faza dryfuje. Nigdy się nie zejdą.

Lewą stronę da się wyrównać uczciwie i kod miał już na to precedens — krzywa dworu jest
od dawna przycinana do startu odczytów z mieszkania, *„żeby nie ciągnęła się samotnie"*.
Ta sama zasada, rozciągnięta na wszystkich: do rysowania dokładamy **jeden prawdziwy
odczyt sprzed granicy zakresu**, a oś ustawiona na najwcześniejszy odczyt z zakresu
chowa go za kadrem. Ważne: oś **nie** jest pinowana do granicy zakresu — przy „7 dniach"
historia bywa krótsza niż okno i zostawiłoby to kilkanaście godzin pustki.

Prawej strony wyrównać się nie da, bo przyszłych odczytów nie ma. Ostatni odczyt każdego
pokoju dostaje kropkę; dwór jej nie dostaje, bo rysuje się pasmem i kropka na jego
krawędzi czyta się jak brud.

Kotwica jest zabiegiem wyłącznie rysunkowym: nie wchodzi do statystyk tabeli ani do
wykrywania wietrzeń, i oba te wyłączenia mają swój test. Filtr skoków dostał za to
zapas 3 godzin przed granicą — pierwszy odczyt w zakresie ma się wreszcie z czym
porównać — ale licznik „ukryto N skoków" liczy dalej tylko to, co widać.

Fikstura dostała opcję `przesuniete`: każdy pokój raportuje w innej minucie godziny.
Bez tego wszystkie serie stały na jednej siatce co do sekundy i żaden test nie mógł
tego zjawiska złapać.

### Dziury w rytmie doby

Zgłoszone i zatwierdzone przez użytkownika: „nie możemy sobie na to pozwolić". Kratka bez
odczytu jest odtwarzana liniowo z sąsiadów i oznaczana kreskowaną ramką. Granica jest
twarda i ma swój test: przerwa dłuższa niż `MISS_GAP` zostaje czarna, bo martwego czujnika
nie wolno domalowywać — a to jest dokładnie ta różnica, o którą chodziło przy odrzuceniu
`TUYA_ODTWORZ` w danych źródłowych. Tam odtwarzanie dotyczyłoby zapisu na dysku; tutaj
wyłącznie jednej komórki w wizualizacji, oznaczonej jako odtworzona.

### Dwa panele zamiast dwóch osi (temperatura)

Zgłoszone jako „temperatura na zewnątrz jest zaznaczona tak, że psuje wszystko wizualnie"
i „tygodniowy wykres temperatury wygląda tak, że nic z niego nie da się przeczytać".
Użytkownik sam zapytał, czy jedna oś nie byłaby lepsza, i poprosił o warianty do wyboru.

Wyrenderowałem trzy na jego danych i to renderowanie rozstrzygnęło sprawę:

| wariant | wynik |
|---|---|
| jedna wspólna oś | cztery pokoje zlewają się w jedną wstążkę — dokładnie to, przed czym ostrzegała notatka z poprzedniej sesji |
| dwie osie (stan sprzed) | pasmo dworu przykrywa pół pola, przecięcia linii są przypadkowe |
| **dwa panele** | pokoje czytelne, dwór w kadrze, żadnych fałszywych przecięć |

Pierwsza wersja paska miała własną, niezależną skalę i użytkownik od razu wytknął, że
„ciężko zestawić ze sobą temperaturę w pokojach z temperaturą na zewnątrz". Miał rację
i problem nie leżał w wysokości: przy dwóch niezależnych skalach pytanie „o ile cieplej"
wymagało czytania dwóch osi i odejmowania w głowie. Druga runda wariantów: podniesiony
pasek, pasek z dwiema krzywymi na jednej skali, pasek samej różnicy wokół zera. Wybrany
został środkowy.

Rzeczy, które trzeba było zrobić, żeby panele naprawdę do siebie pasowały — i które są
osobnymi testami, bo bez nich całość jest tylko ładna:

- **Wspólny zakres poziomy** (`zakresOsi`). Bez niego każdy panel bierze krańce ze swoich
  danych, a pokoje i dwór kończą się o innych porach — panele rozjeżdżają się i porównanie
  chwil przestaje być prawdziwe.
- **Stała szerokość osi pionowej** (`OS_Y`). Chart.js dobiera ją do najdłuższego podpisu,
  więc „26,5" i „34" dałyby dwa różne lewe marginesy.
- **Podziałka czasu tylko w dolnym panelu.** Stykają się krawędziami, jeden komplet
  wystarcza, a dwa wyglądały jak dwa osobne wykresy postawione przypadkiem obok siebie.
- **Wyłączony czujnik zewnętrzny chowa pasek** i oddaje podpisy godzin na górę. Da się to
  zrobić z poziomu adresu (`#bez=na zewnątrz`), więc nie jest to przypadek teoretyczny.

Przy okazji pasma wietrzenia zamieniły prostokąty na całą wysokość na **wstążkę przy
dolnej krawędzi**: przy 7 dniach epizodów robi się kilkanaście i pełna wysokość
zamieniała wykres w pasy.

### Reszta wykresów, czyli koniec podwójnych osi

Użytkownik poprosił, żeby „pozostałe wykresy też dostosować", i dopytał o zakładkę
„całość". Pomiar zmienił odpowiedź: **wilgotności NIE należało dawać drugiego panelu.**

Decyduje jedna liczba — ile wysokości zajęłyby pokoje na wspólnej osi z dworem:

| wykres | pokoje na wspólnej osi | wniosek |
|---|---|---|
| temperatura | **20%** | dwa panele, jak zrobiono |
| wilgotność względna | **49%** | wystarczy zdjąć drugą oś |
| wilgotność bezwzględna | **58%** | już było dobrze, nic nie ruszać |

Czyli mechaniczne skopiowanie układu dwóch paneli na wszystkie wykresy byłoby błędem.
Wilgotność względna ma jeszcze drugi powód, żeby paska nie dostać: **porównywanie jej
z dworem jest fizycznie mylące**, bo skacze od samej temperatury — pasek obiecywałby
odpowiedź na pytanie, na które ten wykres nie odpowiada.

Skoro po tej zmianie żaden wykres nie ma już drugiej osi, maszyneria rysująca ją
w `draw()` została **usunięta, nie wyłączona** — tak samo, jak wcześniej z pętlą
odtwarzania. Zniknęły z nią `dwieOsie`, `DWOR_TLO`, oś `y2`, podpisy „lewa oś:
mieszkanie · prawa: dwór" i reguła „własna oś → tło": własnych osi nie ma już nigdzie,
więc dwór wszędzie, gdzie dzieli wykres z pokojami, jest kreskowaną linią.

**Usterka w „całość".** Pasek zestawienia miał `spanGaps` na sztywne 3 godziny, a agregaty
dobowe dzieli 24 — więc w tym widoku krzywa dworu nie rysowała się wcale, a razem z nią
znikało wypełnienie. Zostawał sam pasek z jedną linią i legenda obiecująca kolory, których
nie było. Warto zapamiętać wzorzec: **każda stała czasowa napisana pod widok godzinowy
musi mieć wariant dobowy**, tak jak ma go `spanGaps` w `draw()` od dawna.

### Czego nowy pasek omal nie zgubił

Kreska „jesteś tutaj" przy odtwarzaniu historii rysuje wtyczka `znacznik`, wpięta
w `draw()`. Pasek zestawienia ma własną funkcję rysującą i wtyczki trzeba było wpiąć
ręcznie — pierwsza wersja miała tylko `dotyk` i `pustka`, więc przy odtwarzaniu kreska
urywała się na górnej krawędzi paska. Wygląda to jak usterka renderowania, a nie jak
decyzja. Wniosek na przyszłość: **każda nowa funkcja rysująca wykres musi przejść listę
wtyczek z `draw()` i świadomie odrzucić te, których nie chce** — tu odrzucona jest tylko
`pasma`, bo wietrzenie ma wstążkę nad temperaturą, nie pod nią.

### Przy okazji

- **Watchdog chodzi co 6 godzin**, nie raz na dobę. Próg alarmu to 6 godzin ciszy, więc
  przy jednym sprawdzeniu dziennie awaria tuż po przebiegu leżała niezauważona prawie
  dobę — a Tuya trzyma tylko 7 dni logów.
- **`sw.js` podbity na `smart-home-v2`**, bo zmieniła się zawartość szkieletu.

### Czytelność „7 dni" na telefonie — trzy odrzucone pomysły i jeden przyjęty

Zgłoszenie brzmiało: na komputerze wykres wygląda dobrze, na telefonie widok „7 dni”
jest przez skalę nieczytelny. Pomiar: pole wykresu ma na szybie 390 px szerokość
356 pikseli, 96% odczytów mieści się w paśmie **2,3 °C**, a oś musi objąć **4,9 °C** —
bo dwa nurki wietrzenia sięgają 22,5 °C. Dwa nurki szerokie na dwa piksele zabierają
dolną połowę panelu.

Trzy statyczne podejścia poszły do niego jako wyrenderowane zrzuty na jego danych i
wszystkie trzy odpadły: wyższy panel (zysk 1,3× — puste pole rośnie razem z panelem),
oś ucięta do 24,0° (1,6× — ale nurki wychodziły poza wykres, co odrzucił wprost) i oś
łamana ze ściśniętym ogonem (1,4× — dużo maszynerii jak na tyle).

Rozwiązanie podsunął on sam: „może niech zostanie tak jak jest, ale jak się przybliża
palcami, to się przybliża oś X”. Pomysł był dobry w połowie — sam zoom osi czasu rozciąga
linie w poziomie i nic nie daje w pionie. Druga połowa to fakt, że **Chart.js liczy oś
pionową wyłącznie z punktów mieszczących się w oknie czasu**, więc zwężenie okna samo
z siebie rozciąga skalę pionową. Zmierzone: doba 21.08 → 2,3×, doba 17.08 → 4,1×,
sześć godzin → 4,6×. Rząd wielkości więcej niż cokolwiek statycznego, przy zerowej
zmianie widoku domyślnego.

Trzy rzeczy, które przy tym trzeba było ustawić:

- **Pion należy do przeglądarki.** `touch-action: pan-y` na polu wykresu: poziom i
  wielodotyk dostaje wykres, pion obsługuje przeglądarka. Bez tego przewijanie strony
  palcem po wykresie przestałoby działać — czyli zamiana jednego problemu na gorszy.
- **Dymek musiał się przenieść** z „każdego ruchu w poziomie" na „dotknięcie", bo poziom
  zajęło przesuwanie. Wtyczka `dotyk` ukrywa teraz przed Chart.js *wszystkie* zdarzenia
  dotyku, a przy dotknięciu podaje mu jedno sztuczne `mousemove`.
- **Domknięcie osi pionowej na krawędziach okna.** Linia wchodząca w kadr z boku ma na
  krawędzi wartość interpolowaną, której w rachunku Chart.js nie ma — i uciekała poza
  pole. To jest ten jeden warunek, który postawił wprost: nic nie może wychodzić poza
  wykres. Naprawia przy okazji kotwicę sprzed początku zakresu.

Gesty testujemy prawdziwymi zdarzeniami dotyku przez CDP, nie wywołaniem funkcji ze
środka strony — przedmiotem testu jest właśnie to, czy palec dochodzi do wykresu przez
`touch-action`, fazę przechwytywania i wtyczkę `dotyk`. Z dwunastu testów **osiem
odrzuca wersję sprzed zmiany na zachowaniu**, cztery to strażnicy i tak są podpisane.
Pierwsze podejście odrzucało starą wersję głównie `ReferenceError`-em na brakującej
zmiennej `okno` — to nie jest odrzucenie na zachowaniu, więc odczyt stanu w teście
został znieczulony na brak symbolu i przycisku.

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
  trzykrotnie szerszy zakres niż lewa. *(Dla temperatury **cofnięte 21.08** — patrz
  „Dwa panele zamiast dwóch osi" wyżej. Dla wilgotności względnej obowiązuje dalej.)*
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
- **Skasowanie wierszy z `data/*.csv` nie jest sposobem na ukrycie odczytu.** Do 8.10
  każdy przebieg pobierał pełne okno 7 dni, więc usunięte wracały w ciągu godziny. Od
  pobierania przyrostowego wracają tylko te z ostatnich ok. 6 godz. (zakładka), a po
  usunięciu kursora `pobrane_do` z manifestu — wszystkie z 7 dni. Do chowania artefaktów
  jest `artefakty.json`. Zmiana **wartości** przy zachowanym znaczniku jest trwała, bo
  `merge()` kluczuje po `(ts, device_id, code)`.
- *(Nieaktualne od 27.09 — wykrywanie wietrzenia usunięte.)* `policzWietrzenia(od)` zwracało `{wietrz, klima, nazwy}`, a nie mapę po identyfikatorze.
- **Piąty raz ten sam wzorzec: próg kontra liczba na jego krawędzi.** Test „wygładzenie
  nie odsuwa linii dalej niż o krok czujnika" wychodził dokładnie na 0,100 przy progu
  `< 0,1` i przechodził albo nie zależnie od pory doby, o której poszedł. Zmierzone:
  każde przekroczenie siedziało **na brzegu serii**, gdzie okno ma dwie próbki zamiast
  trzech; wnętrze nie wychodziło poza 0,067 o żadnej godzinie. Naprawa jest w aplikacji,
  nie w teście — patrz niżej.
- **„Cancelled" w Actions nie znaczy „ktoś anulował".** 19.08 przebieg `Testy` na
  commicie `2c4f574` ruszył o 21:43 i skończył się o 03:43 jako *cancelled* — dokładnie
  sześć godzin, czyli domyślny limit wykonania GitHuba. Testów nie oblał: ten sam zestaw
  przeszedł w 82 sekundy w nocnym przebiegu na kodzie zawierającym ten commit. Zanim
  zaczniesz szukać błędu w kodzie, sprawdź czas trwania — sześć godzin to zawieszenie,
  nie porażka. Wszystkie zadania mają teraz `timeout-minutes`, żeby to się nie powtórzyło.
- **Podgląd strony w tej sesji wymaga podstawienia Chart.js.** `cdn.jsdelivr.net`
  i Google Fonts nie przechodzą przez proxy, więc zrzut ekranu bez podstawienia pokazuje
  stronę bez wykresów — dokładnie tak, jak wygląda awaria CDN. Pliki leżą
  w `tests/frontend/node_modules`, tak jak bierze je Playwright.
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
| Testy kolektora | **162** (`python -m unittest discover -s tests`) |
| Testy strony | **160** (`cd tests/frontend && npx playwright test`) |
| Workflowy | `zbieraj` z cron-job.org co godzinę, harmonogram GitHuba co godzinę o :19 jako zapas; ok. 7 zapytań Tuya na przebieg (do 8.10: 29) z pakietu 0,20 USD na miesiąc · `watchdog` co 6 godz. o :41 · `testy` przy zmianie kodu i o 4:17 · `odkryj` na żądanie i po każdej zmianie swojego pliku na main. Akcje na wersjach z Node 24 |
| Orientacja mieszkania | Sypialnia na **południe**, Salon i Kuchnia na **północ** — to nie ozdoba, z tego bierze się rada o kolejności otwierania okien |
| Czujniki | cztery pokoje na wysokości ok. 80–90 cm (wyrównane 19.08) + klimatyzator FERSK VIND 2 w salonie |

## Co czeka

- **Po stronie właściciela** — zrobione 27.09: zegar z cron-job.org stoi, data triala
  sprawdzona. Cyklicznie: odnowienie tokenu i przedłużenie triala (`TODO.md`). Pomiaru
  fRsi nie będzie — właściciel nie przestawia czujników, zostaje 0,70 z normy.
- **Listopad:** przyłożyć `TREND_MAX` i `CIEPLO_W_DOMU` do danych z kaloryferami.
- **Maj 2027:** model cieplny pokój ↔ dwór.
- Ochrona gałęzi — opisana wyżej, wymaga decyzji o deploy key albo pozostania przy
  hooku lokalnym.
