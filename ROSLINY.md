# Rośliny — przygotowanie

Plan przed wdrożeniem czujników w doniczkach. Stan na 8.10.2026. Czujniki są kupione,
ale jeszcze nie zbierają danych, a w kodzie nic się nie zmieniło. Ten plik zbiera to,
co wiadomo o czujniku, o roślinach i o tym, gdzie nowa funkcja zahacza o istniejący
kod. Liczby oznaczone **[do sprawdzenia]** pochodzą z wyszukiwarki albo z cudzych
pomiarów. Przed wpisaniem do kodu trzeba je zmierzyć u nas.

**Czego chce właściciel:** trzy czujniki w trzech doniczkach (mały fikus, azalia,
skrzydłokwiat). Na telefon mają przychodzić powiadomienia, gdy roślinę trzeba
**podlać** albo **przestawić**, bo ma za mało światła. Telefon to Android (strona
zainstalowana z Chrome jako aplikacja) i iPhone.

**Warunek właściciela (8.10):** odczyty z doniczek **nie mieszają się** z tym, co
strona pokazuje dziś. Wykresy, kafle, rzut, strefa komfortu i alarmy pleśni zostają
wyłącznie dla pokoi. Rośliny dostają **osobną zakładkę** w aplikacji.

---

## W skrócie

1. **Limit zapytań Tuya jest prawie wyczerpany już dziś, jeszcze bez roślin.**
   - Przebieg kosztuje ok. 29 zapytań. Liczba wynika z czasów w logach Actions.
   - Przebiegów jest ok. 28 na dobę: 24 z cron-job.org i 4–5 z zapasowego harmonogramu.
   - Prognoza na październik to ok. 25 400 zapytań przy limicie triala 26 000 na
     miesiąc **[do sprawdzenia na iot.tuya.com]**.
   - Trzy nowe czujniki przy dzisiejszym sposobie pobierania przekroczą limit
     kilkukrotnie.
   - Dlatego pierwszym krokiem, niezależnym od roślin, jest pobieranie tylko tego,
     co nowe (etap 0).
2. **Czujnik ma model „C3007" i to jest ta wersja, przed którą ostrzega Zigbee2MQTT.**
   - Według Zigbee2MQTT wysyła lawinę komunikatów, wyczerpuje baterie w kilka dni
     i nie pamięta ustawień.
   - Nikt nie sprawdził, czy tak samo zachowuje się za bramką Tuya.
   - **Zanim kolektor zacznie go zbierać, trzeba zmierzyć liczbę wpisów w logach.**
3. **Zwykłe dopisanie identyfikatorów do `TUYA_DEVICE_IDS` popsułoby stronę i watchdoga.**
   - `classify()` uzna wilgotność gleby (`humidity`, %) za wilgotność powietrza
     i wyrzuci światło.
   - Skutek na stronie: zmienią się wszystkie liczniki i wykresy, a rada o wietrzeniu
     zmieni werdykt (zmierzone na fiksturze).
   - Skutek u watchdoga: cała zima zgłoszeń „pleśń" od mokrej ziemi.
   - Rośliny idą więc **osobnym torem** — własna konfiguracja, własne pliki w
     `data/rosliny/` i własna strona — dokładnie tak, jak chce właściciel.
4. **Powiadomienia bez serwera da się zrobić.**
   - Nadawcą jest przebieg GitHub Actions, który i tak chodzi co godzinę.
   - Doręcza Web Push, czyli serwery Google (Android) i Apple (iPhone), wprost do
     zainstalowanej aplikacji.
   - Ani serwera, ani tokenu w przeglądarce. Odrzucenie z `TODO.md` („brak serwera")
     przestaje obowiązywać.
5. **Progi nie mogą być z głowy.** Procent wilgotności z takiej sondy to indeks
   względny, inny w każdej doniczce. Pierwsze 1–2 tygodnie aplikacja tylko pokazuje
   odczyty i uczy się:
   - „szczytu" po podlaniu,
   - poziomu, przy którym właściciel sam podlewa.

   Powiadomienia włączają się dopiero potem.
6. **Do czasu wdrożenia** podlewanie da się pilnować bez kodu. Wystarczy automatyzacja
   w Smart Life: „wilgotność gleby < X → powiadomienie".
7. **Rośliny już teraz:**
   - Azalia stoi w kuchni, która przez 21 dni **ani razu** nie zeszła do 18 °C
     (stale 20–21 °C). Kwitnąca azalia woli 10–18 °C.
   - Okna Salonu i Kuchni wychodzą na północ. Od dziś do ok. 20 marca nie zobaczą
     bezpośredniego słońca.

---

## Czujnik

Na pudełku: **TZ-TR-301Z#AT**, „Zigbee Soil Moisture Sensor Temperature Humidity
Luminance Detection, 4 in 1 (For tuya App)". Model **ZS-301Z**, na naklejce
**C3007**. Zasilanie to 2× AAA, łączność Zigbee 3.0. W Zigbee2MQTT ten czujnik
to `ZS-301Z` (Arteco), odcisk `TS0601` / `_TZE284_o9ofysmo` albo `_TZE284_xc3vwx5a`.

| Co mierzy | Punkt danych (Zigbee) | Prawdopodobny kod w chmurze Tuya | Uwagi |
|---|---|---|---|
| wilgotność gleby | 3 | `humidity` (%) | **nazwa myląca** — to gleba, nie powietrze; Home Assistant tak samo traktuje kategorię `zwjcy` |
| temperatura powietrza | 5 | `temp_current` (÷10) | czujnik w szyjce, kilka cm nad ziemią |
| bateria | 14 | `battery_state` (low/middle/high) | **brak procentów**; „low" = 1–25% |
| wilgotność powietrza | 101 | `env_humidity` (%RH) **[do sprawdzenia]** | nad mokrą ziemią będzie wyższa niż w pokoju |
| natężenie światła | 102 | `dimmer` (0–10 000 lx) **[do sprawdzenia]** | otwór na czole głowicy; **nasyca się przy 10 000 lx** |
| kalibracja gleby | 103 | `adjust_humidity` (±30) | ustawiana w Smart Life; przesuwa odczyt gleby |
| odstęp próbkowania | 104 | `adjust_sample_time` (30–1200 s) | domyślnie 600 s według zgłoszenia #29254 |

Źródła: konwerter Zigbee2MQTT (`zigbee-herdsman-converters`, `src/devices/tuya.ts`),
zgłoszenia [#27956](https://github.com/Koenkk/zigbee2mqtt/issues/27956) i
[#29254](https://github.com/Koenkk/zigbee2mqtt/issues/29254). Kody w chmurze pochodzą
z tabeli w #27956, a nie z naszego konta. Rozstrzygnie je dopiero `odkryj.yml`.

**Z instrukcji (V2.0):**
- Czujnik mierzy co 30 s. Wysyła odczyt, gdy gleba zmieni się o 3%, temperatura
  o 0,3 °C albo wilgotność powietrza o 5%. Seria gleby idzie więc **schodkami po co
  najmniej 3 punkty**.
- Instrukcja nie mówi, kiedy wysyła światło, ani czy ma raport okresowy.
- Krótkie wciśnięcie przycisku wymusza odczyt. Przytrzymanie 5 s włącza parowanie
  (miga czerwona dioda).
- Sondę wbija się na co najmniej 2/3 długości, powierzchnią pomiarową przy ziemi.
  Suchą ziemię najpierw zwilżyć, a potem odczekać 30–60 s.

**Wersja z pomiarem żyzności (EC 0–5000 µS/cm)** ma rozwidlony szpic sondy. Etykieta
„4 in 1" wskazuje na zwykłą wersję, która kończy się ostrzem. Do sprawdzenia przy
rozpakowaniu.

**Pułapki chmury Tuya:**
- Chmura zwraca logi tylko dla punktów danych z „oficjalnej" specyfikacji produktu.
  Punkty 101–104 są niestandardowe, więc w trybie *Standard Instruction* mogą nie
  przyjść wcale (tinytuya, `Cloud.getdevicelog`).
- Wtedy na iot.tuya.com trzeba przełączyć **wyłącznie produkt czujnika roślin** na
  *DP Instruction*.
- **Nie przełączać czujników pokojowych.** Zmieniłyby się ich kody (`va_temperature`
  i reszta), a kolektor zgubiłby serie.

**Zalewanie komunikatami (C3007, płytka „ZSSF01").** Opis Zigbee2MQTT: *„prohibitively
high amount of messages … very fast battery drain (matter of days) … set values not
persisting"*. W #29254 to ok. 1 komunikat na sekundę, a ustawiony odstęp wraca do 600 s.
Zgłoszenia dotyczą Zigbee2MQTT, nie bramki Tuya. U nas to niewiadoma i trzeba ją
zmierzyć (etap 1).

**Światło:**
- Otwór jest na czole głowicy. Przy pionowej sondzie czujnik patrzy najpewniej
  **w bok**, nie w górę **[do sprawdzenia]**.
- Mierzy więc światło w płaszczyźnie pionowej, zależnie od tego, w którą stronę
  obrócona jest głowica. Do tego zasłaniają go liście, najmocniej u skrzydłokwiatu.
- Wartości bezwzględne przeliczane na DLI będą niepewne ok. 2×. Wiarygodny jest
  **trend w jednym miejscu**.
- Głowicę ustawić czołem do okna i więcej jej nie ruszać.

---

## Rośliny

### Co widać na zdjęciach

| | Fikus 'Ginseng' (*Ficus microcarpa*) | Skrzydłokwiat (*Spathiphyllum*) | Azalia doniczkowa (*Rhododendron simsii*) |
|---|---|---|---|
| Doniczka | czarna ceramika z podstawką, ok. 12–14 cm; na wierzchu mech | biała, z rowkiem nisko na ściance — **możliwe dno z rezerwuarem**, czyli woda w spodzie, której sonda nie widzi | **plastikowa doniczka w osłonce**; woda w osłonce jest niewidoczna dla sondy; na wierzchu kora |
| Liście | zdrowe, ciemnozielone, przyrosty na czubkach | **brązowe, zaschnięte końcówki** na 4–5 liściach, kilka bladych | zdrowe; kwitnie, pąki i nowe przyrosty |
| Miejsce | stół, nieznany pokój | komoda, nieznany pokój | **blat w kuchni** (okno na północ) |

### Potrzeby

| | Fikus | Skrzydłokwiat | Azalia |
|---|---|---|---|
| Podlewanie | przesuszyć wierzchnie 2–3 cm; znosi przesuszenie dużo lepiej niż przelanie | równo wilgotno, bez stania w wodzie; podlać, gdy wierzch wyschnie na 2,5–5 cm; **powtarzane więdnięcie daje brązowe końcówki** | **nigdy nie przesuszyć**; zaschnięty torf trudno nawilżyć, ratunek to zanurzenie doniczki w letniej wodzie na ok. 15 min; wylewać wodę z osłonki |
| Zima (X–II) | mniej wody, bez nawozu | mniej wody, bez nawozu | wilgotność bez zmian |
| Temperatura | 16–24 °C, zimą 16–20; nie lubi przeciągów ani kaloryfera | dzień 20–29 °C, **poniżej 15 °C ryzyko uszkodzeń** | **10–18 °C przy kwitnieniu**; przy ≥ 24 °C gubi pąki i liście, ziemia szybko schnie |
| Wilgotność powietrza | 40–60% | ≥ 50%; suche powietrze to najczęstsza przyczyna brązowych końcówek | ≥ 50% |
| Światło | jasno, bez gwałtownych zmian; **źle znosi przestawianie** — gubi liście, a po zmianie miejsca nie ruszać jej przez ok. 4 tygodnie | jasne rozproszone, bez słońca; minimum ok. 800 lx | jasno, chłodno, bez bezpośredniego słońca |
| Światło w liczbach **[do sprawdzenia]** | ok. 1 100–2 150 lx w pomieszczeniu (zalecenia dla innych fikusów) | DLI ok. 0,65 mol/m²/dobę (≈ 10 000 lx·h dziennego światła) | DLI 1,7–2,1 (badania szklarniowe) |

Główne źródła: RHS, UF/IFAS (EP136, EP161, MREC), Missouri Botanical Garden, Clemson
HGIC, SDSU Extension, Murator. Pełna lista na dole. Wartości dla fikusa 'Ginseng'
wyciągnięto z badań nad innymi fikusami. Przelicznik dla światła dziennego to
1 mol/m²/dobę ≈ 15 000 lx·h (1000 lx ≈ 18,5 µmol/m²/s) i nie działa dla lamp.

### Co mówią nasze dane (pomiar, nie zgadywanie)

Zmierzone na czujnikach pokojowych, ważone czasem, z wyłączeniem skoków i znanych
artefaktów. Okno to 1–8.10.2026, ogrzewanie działa od 1.10.

| Pokój | Temperatura: średnio (min–max) | Wilgotność: średnio (min–max) |
|---|---|---|
| Kuchnia (płn.) | 20,8 °C (19,6–22,2) | 59% (48–69) |
| Salon (płn.) | 20,9 °C (18,9–22,3) | 58% (46–69) |
| Sypialnia (płd.) | 22,4 °C (20,8–23,5) | 53% (45–60) |
| Łazienka | 21,4 °C (20,5–22,4) | 60% (50–74) |

**Kuchnia a azalia:**
- Od 17.09 kuchnia była ≤ 18 °C przez **0% czasu**, a powyżej 20 °C przez 79–96%.
- Gotowania przy czujniku nie widać: największy wzrost w godzinę to +0,7 °C.
- W żadnym pokoju nie ma 10–18 °C. Chłodne miejsce dla azalii musiałoby być
  mikroklimatem, np. zimnym parapetem przy zakręconym kaloryferze. Zmierzy go czujnik
  w doniczce.

**Wilgotność spada:**
- Średnia dobowa 1.10 → 7.10: Sypialnia 56 → 50%, Kuchnia 64 → 56%, Salon 61 → 54%.
- Szacunek na mróz, z modelu, a nie z pomiaru: **32–44%**.
- Zimą skrzydłokwiat i azalia będą najpewniej poniżej swoich 50%.

**Światło:**
- Od równonocy jesiennej do wiosennej słońce wschodzi i zachodzi po południowej
  stronie linii wschód–zachód. Okna Kuchni i Salonu nie dostaną bezpośredniego słońca
  **do ok. 20.03**.
- 21.12 dzień ma 8 h, a słońce w południe stoi na 16°.
- Jedynym jasnym miejscem zimą jest Sypialnia od południa, ale tam jest najcieplej
  (22,4 °C).
- W grudniu i styczniu po północnej stronie wszystkie trzy rośliny będą
  najprawdopodobniej poniżej „dobrze", a azalia i fikus blisko swojego minimum lub pod nim.

### Rady już teraz, bez czujników

- **Azalia:**
  - Zdjąć z blatu przy płycie w najchłodniejsze jasne miejsce bez słońca, nie nad
    kaloryferem.
  - Po podlaniu wylać wodę z osłonki.
  - Nigdy nie dopuścić do przesuszenia. Woda z kranu w Katowicach jest miękka
    (ok. 5 °dH) **[do sprawdzenia]**, więc nadaje się do podlewania azalii.
  - Przy 20–21 °C kwitnienie będzie krótsze niż w chłodzie.
- **Fikus:** jeśli stoi po północnej stronie, **przestawić raz, teraz**, a nie
  w grudniu. Najlepiej w najjaśniejsze stałe miejsce z dala od kaloryfera, i więcej
  nie ruszać.
- **Skrzydłokwiat:**
  - Obciąć brązowe końcówki. Nie odrosną, a nowe nie powinny się pojawiać.
  - Nie dopuszczać do więdnięcia między podlewaniami.
  - Sprawdzić, czy w spodzie doniczki nie stoi woda.

---

## Dlaczego nie można po prostu dopisać czujników

Zmierzone na prawdziwym `index.html` z fiksturą `dane.js` i trzema roślinami, opisanymi
tak, jak opisałby je dzisiejszy `fetch.py`.

| Gdzie | Co by się stało |
|---|---|
| `classify()` (`fetch.py:73`) | `humidity` + `%` → `hum`: **gleba jako wilgotność powietrza**. `dimmer`, `bright_value`, `illuminance*` → odrzucone: **światła nie byłoby w ogóle** |
| pamięć kodów w manifeście (`fetch.py:1119-1124`) | pierwsza zła klasyfikacja zostaje na zawsze — późniejsza poprawka `classify()` jej nie rusza |
| `diagnose()` → watchdog | mokra ziemia (75% przy 10 °C na dworze) = „wilgotność powyżej progu pleśni przez 100% doby". **Zgłoszenie przez całą zimę** |
| kafle, tabela, diagnostyka | 5 → 8 kafli, „4/4 OK" → „7/7 OK" albo „4/7 OK · 3 uwaga"; ósmy kolor zawija paletę na kolor Łazienki |
| wykresy temperatury i wilgotności | oś temperatury 23,5–26,5 → 14–28 °C, pokoje spadają do 1/5 wysokości; gleba na wykresie wilgotności powietrza |
| rada o wietrzeniu | średnia mieszkania z roślinami: werdykt zmienił się z „Najlepszy moment na wietrzenie" na „Otwarte okno schłodzi mieszkanie" |
| rzut, rytm doby, strefa komfortu, kalendarz | skale barw rozjechane; rytm doby domyślnie pokazuje „Fikusa" |
| koszt w Tuya | pełne okno 7 dni przy raporcie co 600 s to ok. 51 stron logów na czujnik na przebieg. Przy zalewaniu dochodzi do limitu 300 stron, a przebieg przekracza 20 min i pada **dla wszystkich urządzeń** |

Wniosek: rośliny nie mogą trafić do `data/index.json` ani do `data/RRRR-MM.csv`.

---

## Jak to zbudować

### Osobny tor danych

```
rosliny.json                  konfiguracja (ręczna, jak artefakty.json): czujnik → roślina
data/rosliny/RRRR-MM.csv      surowe odczyty doniczek, ten sam format ts,device_id,code,value
data/rosliny/stan.json        to, co pokazuje zakładka: ostatnie odczyty, dobowe sumy światła,
                              wykryte podlewania, werdykty („podlej", „za ciemno")
data/rosliny/powiadomienia.json  co i kiedy zostało wysłane (bez adresów telefonów!)
```

- **`rosliny.json`** leży obok `fetch.py`, tak jak `artefakty.json`. Ścieżka liczy się
  od pliku, żeby testy w katalogu tymczasowym widziały tę samą listę.
- Wpis wygląda tak (szkic):

  ```json
  {
    "czujnik": "<id z odkryj.yml>",
    "nazwa": "Azalia",
    "gatunek": "azalia",
    "pokoj": "Kuchnia",
    "kody": {"gleba": "humidity", "swiatlo": "dimmer", "temp": "temp_current",
             "wilg": "env_humidity", "bateria": "battery_state"}
  }
  ```

- **Kody wpisane jawnie**, a nie zgadywane przez `classify()`. Po parowaniu przepisuje
  się je z wyniku `odkryj.yml`. Skala przychodzi ze specyfikacji, jak dziś.
- Identyfikatory roślin **nie trafiają** do `TUYA_DEVICE_IDS`. Kolektor bierze je
  z `rosliny.json`, więc `data/index.json`, `dzienne.csv`, `diagnose()` i cała
  dzisiejsza strona nie wiedzą o ich istnieniu.
- Pliki w podkatalogu nie pasują do wzorca `data/[0-9]*.csv`, więc `purge_before`,
  `write_daily`, `recent_rows` i `keep_known` same je pomijają. Mimo to ta izolacja
  musi mieć **własny test**.
- `git add data/` w `zapisz.sh` obejmuje podkatalog, a service worker serwuje `data/`
  najpierw z sieci. Nic więcej nie trzeba dopisywać.

### Kolektor

1. **Pobieranie przyrostowe**, wspólne z etapem 0:
   - od ostatniego zapisanego odczytu minus 2–3 godz. zakładki, ale nigdy dalej niż
     7 dni wstecz, więc nadrabianie po awarii zostaje;
   - `merge()` odrzuca duplikaty po `(ts, device_id, code)`, więc zakładka jest
     bezpieczna;
   - dla roślin **limit stron na przebieg** (np. 5) zamiast globalnych 300 i ostrzeżenie
     w logu, gdy zostanie osiągnięty.
2. **Nowy moduł `rosliny.py`**, czysta biblioteka standardowa, testowany jak `fetch.py`:
   - dobowa suma światła: lx·h, całkowana w czasie, z przycinaniem dziur jak
     w `udzial_powyzej()`;
   - szacunkowe DLI z wyraźnym oznaczeniem „szacunek";
   - wykrywanie podlania (skok gleby w górę) i poruszenia sondy (gwałtowny spadek);
   - uczenie progów (niżej);
   - werdykty z histerezą.
3. **Werdykty liczy Python, a strona je tylko wyświetla.** Dzięki temu nie powstaje
   nowa para bliźniaczych stałych JS/Python (dziś pilnują ich testy `SPIKE` i `FRSI`),
   a karta w aplikacji i powiadomienie nie mogą sobie przeczyć.
4. **Zalewanie komunikatami:** jeśli pomiar z etapu 1 pokaże setki wpisów na godzinę,
   dochodzi `zwin_rosliny()` na wzór `collapse_power()`. Zostają zmiany i co najmniej
   jeden wiersz na godzinę na kod. Działa to tylko przy pobieraniu przyrostowym.
5. **Opcjonalnie** archiwum promieniowania z Open-Meteo (`shortwave_radiation`). Dziś
   kolektor bierze je tylko do prognozy na 36 godz. Stosunek „światło przy roślinie /
   światło na dworze" odróżnia pochmurny tydzień od złego miejsca. Bez tego „przestaw"
   myliłoby się w każdy szary listopadowy tydzień.

### Zakładka „Rośliny"

- **Osobna strona `rosliny.html`** w tym samym zakresie aplikacji (`scope: ./`), a nie
  sekcja wewnątrz `index.html`:
  - w zainstalowanej aplikacji przejście między stronami w zakresie zostaje w jej oknie;
  - nie ładuje 177 KB logiki mieszkania;
  - ma własne testy i własną fiksturę, a 130 testów strony głównej zostaje bez zmian;
  - adres z powiadomienia (`./rosliny.html#azalia`) nie ginie, bo `boot()` w
    `index.html` nadpisuje hash własnym `#zakres=…`.
- **Pasek zakładek** „Mieszkanie | Rośliny" u góry obu stron. To jedyna zmiana widoczna
  na dzisiejszej stronie.
- **Na zakładce:**
  - **Karta każdej rośliny:** gleba na tle pasma rośliny, wzorem toru z „Nocy w
    sypialni". Do tego ostatnie podlanie („3 dni temu"), wczorajsze światło wobec
    potrzeby, temperatura i bateria. Na górze werdykt jednym zdaniem.
  - **Wykres gleby z 14–30 dni** z kreskami podlań. Linia schodkowa, bez wygładzania,
    które rozmazałoby skok podlania.
  - Światło na osobnym panelu, nie na drugiej osi, bo drugie osie zostały z projektu
    świadomie usunięte.
  - Wykres trzymany poza `state.charts`, jak strefa komfortu. Funkcja rysująca
    przechodzi listę wtyczek z `draw()` i świadomie odrzuca te, których nie chce.
  - **Przycisk „Włącz powiadomienia"** z instrukcją dla iPhone'a (patrz niżej).
- **`sw.js`:**
  - `rosliny.html` dochodzi do `SZKIELET`, więc `WERSJA` → `smart-home-v4`;
  - nowe obsługi `push` i `notificationclick`;
  - kliknięcie otwiera tylko adresy z zakresu aplikacji.

### Powiadomienia

**Kanał — rekomendacja i zapasy:**

| Kanał | Za | Przeciw | Rola |
|---|---|---|---|
| **Web Push do aplikacji** | przychodzi *z tej* aplikacji; kliknięcie otwiera zakładkę „Rośliny"; za darmo; treść szyfrowana end-to-end | najwięcej pracy; na iPhonie subskrypcja potrafi po cichu wygasnąć | **główny** |
| ntfy.sh | 10 minut konfiguracji; aplikacje na Androida i iOS | powiadomienie przychodzi z aplikacji ntfy, nie z naszej; ntfy.sh widzi treść; na iPhonie kliknięcie otwiera Safari | zapas, gdyby Web Push zawiódł |
| automatyzacja Smart Life | zero kodu; działa od razu po parowaniu | jeden próg bez histerezy; bez światła z wielu dni i bez uczenia się | **tymczasowo**, do końca etapu 4 |
| zgłoszenie od watchdoga (mail) | już działa | zwłoka do kilkunastu godzin | tylko awarie: martwa subskrypcja, cisza czujnika, bateria |

**Jak wysyłać bez dublowania:**
- Dwa przebiegi kolektora potrafią wystartować naraz, a `zapisz.sh` liczy wtedy
  odczyty jeszcze raz na drzewie zwycięzcy.
- Dlatego `fetch.py` tylko **decyduje** i zapisuje „wysłano" w
  `data/rosliny/powiadomienia.json`, w tym samym commicie co odczyty. Treść ląduje
  w skrzynce poza repozytorium (`$RUNNER_TEMP`).
- **Wysyła osobny krok** w `zbieraj.yml`, który rusza dopiero po udanym `zapisz.sh`.
  Tylko ten krok dostaje sekrety powiadomień.
- Udany push na gałąź działa jak zamek: przegrany przebieg po resecie widzi „wysłano"
  zwycięzcy, więc nic nie idzie dwa razy. Gdy nie uda się żaden push, nic nie jest
  wysłane ani zapisane, więc następny przebieg zrobi to od nowa.
- Pułapka: `git reset --hard` nie kasuje plików nieśledzonych. `zapisz.sh` musi
  czyścić skrzynkę na początku każdej próby, a test powinien to wymusić.

**Sekrety:**
- `VAPID_KLUCZ_PRYWATNY`.
- Subskrypcja każdego telefonu w osobnym sekrecie (`PUSH_ANDROID`, `PUSH_IPHONE`).
  Sekretów GitHuba nie da się odczytać ani częściowo zmienić, więc jedna tablica JSON
  byłaby niewygodna.
- Klucz publiczny VAPID jest jawny z natury. Siedzi w stronie i w nadawcy jako para
  bliźniaczych stałych, pilnowana testem.
- **Subskrypcji nigdy nie wolno trzymać w `data/`**, bo `data/` jest publiczne na Pages.

**Przenoszenie subskrypcji:**
- Strona pokazuje JSON z przyciskiem „Kopiuj". Właściciel wkleja go raz na telefon
  w *Settings → Secrets*.
- Gdy wysyłka dostanie 404/410 (subskrypcja wygasła), watchdog zakłada zgłoszenie
  „Powiadomienia nie dochodzą — włącz ponownie i podmień sekret".

**Nadawca:**
- Ok. 100 linii na samej bibliotece `cryptography`: szyfrowanie RFC 8291 i podpis
  VAPID ES256.
- Prototyp poprawnie szyfruje i podpisuje, co sprawdzono lokalnie z biblioteką
  referencyjną `http_ece`. **Nie był jeszcze puszczany na prawdziwe serwery Google
  i Apple.**
- Alternatywa `pywebpush` 2.5.0 ma trzy zmierzone pułapki:
  - zmienia słownik `claims` w miejscu, więc drugi telefon dostaje zły `aud`;
  - domyślnie wysyła `TTL 0`;
  - odrzuca `sub` z adresem zawierającym ścieżkę.
- `cryptography` wchodzi w osobny plik wymagań kroku wysyłki. Testy kolektora
  zostają na bibliotece standardowej, poza testem szyfrowania.
- Nagłówki: `TTL` 12 godz., `Urgency: normal`, `Topic`/`tag` ASCII (np.
  `podlej-azalia`). Nowe powiadomienie o tym samym podmiocie zastępuje stare, zamiast
  się dokładać.

**Telefony:**

*Android (Chrome):*
1. Otworzyć zainstalowaną aplikację.
2. Zakładka „Rośliny" → „Włącz powiadomienia" → Zezwól.
3. „Kopiuj" → wkleić jako sekret `PUSH_ANDROID`.
4. Actions → próbne powiadomienie.
5. Jeśli przychodzą z opóźnieniem: Ustawienia → Aplikacje → Chrome → Bateria → bez
   ograniczeń.

*iPhone (iOS ≥ 16.4, najlepiej ≥ 18.4):*
1. Aplikacja musi być dodana do ekranu początkowego **z Safari**.
2. Otwarta **z ikony** → „Włącz powiadomienia" → Pozwalaj.
3. „Kopiuj" → sekret `PUSH_IPHONE`.
4. Ograniczenia:
   - po usunięciu i ponownym dodaniu ikony trzeba zrobić subskrypcję od nowa;
   - Safari cofa zgodę, jeśli push nie pokaże powiadomienia, więc obsługa `push`
     musi je pokazać **zawsze**;
   - w UE (DMA) Apple w 2024 r. wycofało się z wyłączenia aplikacji z ekranu
     początkowego, więc w Polsce działa.
5. Zakładka sprawdza przy każdym otwarciu, czy subskrypcja żyje. Jeśli nie, pokazuje
   „Powiadomienia wyłączone — włącz ponownie".

### Reguły powiadomień

**Zasady ogólne:**
- **Cisza 21:00–8:00** czasu polskiego. Co wypadnie w nocy, idzie pierwszym przebiegiem
  po 8:00.
- **Jedno zbiorcze powiadomienie na przebieg** („Podlej: azalia, skrzydłokwiat").
  Najwyżej 2 zwykłe na dobę.
- Stan przewlekły, którego nie da się naprawić od ręki (ciepła kuchnia, ciemna zima),
  dostaje **jedno** powiadomienie. Potem jest już tylko na karcie, dopóki się nie zmieni.
- **Pierwszy tydzień na sucho:** reguły liczą się i widać je na zakładce, ale nic nie
  wychodzi na telefon. Do tego przełącznik w `zbieraj.yml` do wyłączenia wysyłki.

**Uczenie progów:**
- **„Szczyt"** to mediana odczytów 2–6 godz. po wykrytym podlaniu, z trzech ostatnich
  podlań.
- **„Punkt podlewania"** to odczyt tuż przed podlaniem, czyli chwila, w której
  właściciel sam uznał, że już czas. Po trzech podlaniach mediana staje się osobistym
  progiem, przyciętym do granic gatunku.
- Przy schodkach po 3 punkty każda histereza musi mieć **co najmniej 6 punktów**.

| Reguła | Sygnał | Kiedy | Ponowienie | Uwagi |
|---|---|---|---|---|
| **Podlej** | gleba ÷ szczyt (R) | azalia R ≤ 0,75; skrzydłokwiat ≤ 0,60 (X–II: 0,50); fikus ≤ 0,45 (X–II: 0,35); przez ≥ 2 godz. | co 24 godz. (azalia 12), najwyżej 3 razy | gaśnie po wykrytym podlaniu |
| **Pilne** | R | azalia ≤ 0,60 → „zanurz doniczkę na 15 min" | 12 godz. | omija limit dobowy, nie omija ciszy nocnej |
| **Za mokro za długo** | R bez spadku | fikus ≥ 0,85 przez 7 dni (zimą 10); skrzydłokwiat ≥ 0,90 przez 10 (14); azalia ≥ 0,95 przez 7 | raz, potem karta | „wylej wodę z osłonki / podstawki" |
| **Za ciemno — przestaw** | szacunkowe DLI, mediana z 7 dni, tylko dni z pełnym pomiarem | ≥ 5 z 7 dni poniżej progu gatunku, najlepiej względem światła na dworze | 14 dni; **fikus najwyżej raz na sezon**, a po wykrytym przestawieniu 4–6 tygodni ciszy | zimą po północnej stronie raz powiedzieć „lepszego miejsca nie ma" zamiast przypominać |
| **Za dużo słońca** | lx | ≥ 10 000 lx (nasycenie czujnika) przez ≥ 30 min w 2 z 3 dni | 7 dni | po północnej stronie do marca praktycznie niemożliwe |
| **Za ciepło** (azalia) | temperatura przy doniczce, tylko przy słabym świetle | ≥ 24 °C przez 2 godz.; mediana dobowa ≥ 22 °C przez 3 dni → raz | 14 dni | przy słońcu nagrzewa się obudowa, a nie powietrze |
| **Przy kaloryferze** | doniczka − czujnik pokoju | ≥ +3 °C przez 3 godz. | 7 dni | jedyna reguła, która korzysta z czujników pokoi; tylko czyta, niczego nie miesza |
| **Za zimno** | temperatura przy doniczce | skrzydłokwiat ≤ 15 °C, fikus ≤ 13 °C przez 2 godz. | 72 godz. | poranne podsumowanie nocy |
| **Czujnik** | cisza, bateria `low`, nagły spadek gleby (sonda wyjęta) | cisza > 6 godz. za dnia; `low` | 7 dni | zgłoszenie od watchdoga z własną etykietą `rosliny` |

Wszystkie liczby w tabeli to punkt wyjścia z literatury i są **[do sprawdzenia]**.
Po 2–3 cyklach podlewania przykłada się je do prawdziwych danych, tak jak 27.09 do
progów `TREND_MAX` i `CIEPLO_W_DOMU`.

---

## Plan wdrożenia

| Etap | Kto | Co | Kiedy gotowe |
|---|---|---|---|
| **0. Limit Tuya** | Claude | pobieranie przyrostowe dla wszystkich urządzeń; limit stron na urządzenie; bez nieudanej próby API v2 w każdym przebiegu; podpowiedź przy kodzie wyczerpanego limitu. Szacunek: ok. 29 → ok. 10 zapytań na przebieg, także z roślinami | testy odrzucają starą wersję; liczba zapytań zmierzona w logu przebiegu |
| | właściciel | iot.tuya.com → projekt → IoT Core: **ile zostało w tym miesiącu i kiedy limit się odnawia** | liczba w ręku |
| **1. Parowanie i pomiar** | właściciel | sparować trzy czujniki w Smart Life (5 s przycisk), nazwać Fikus / Azalia / Skrzydłokwiat; sprawdzić końcówkę sondy (ostrze czy widełki) i napis na płytce pod klapką (`ZSSF01`?); jeśli Smart Life pozwala, ustawić odstęp próbkowania na 600–1200 s | czujniki widać w Smart Life |
| | Claude | rozszerzyć `--discover`: surowa specyfikacja (`status` i `functions`), bieżące wartości, **liczba wpisów w logach z 24 godz. na punkt danych** — jedno uruchomienie odpowiada na wszystkie pytania | — |
| | właściciel | po dobie: Actions → „Pokaż urządzenia w Tuya" | wiadomo: kody, jednostki, skale, kategoria, czy jest zalewanie |
| | właściciel | jeśli brakuje światła albo wilgotności powietrza: na iot.tuya.com przełączyć **tylko produkt czujnika roślin** na *DP Instruction* i powtórzyć | — |
| | właściciel (opcjonalnie) | tymczasowa automatyzacja w Smart Life „wilgotność gleby < X → powiadomienie", pora: dzień | — |
| **2. Kolektor roślin** | Claude | `rosliny.json`, osobny tor w `data/rosliny/`, `rosliny.py`, testy (każdy odrzuca starą wersję albo jest podpisany jako strażnik) | dane z doniczek lecą do repozytorium; strona główna bez zmian — pilnuje tego test |
| **3. Zakładka „Rośliny"** | Claude | `rosliny.html`, pasek zakładek, karty, wykres, `sw.js`; tryb nauki — bez powiadomień | właściciel widzi rośliny w aplikacji |
| **4. Powiadomienia** | Claude | nadawca Web Push, krok w `zbieraj.yml`, przycisk i obsługa w `sw.js`, przebieg próbny, zgłoszenie o martwej subskrypcji | próbne powiadomienie dochodzi na Androida (i iPhone'a) |
| | właściciel | wygenerowane klucze VAPID do sekretów, subskrypcje z telefonów do sekretów | — |
| | — | tydzień na sucho, potem włączenie | — |
| **5. Strojenie** | razem | po 2–3 cyklach podlewania przyłożyć progi do danych; wyłączyć automatyzację Smart Life | — |

Etap 0 ma sens niezależnie od roślin i dobrze, żeby poszedł pierwszy. Według prognozy
limit kończy się pod koniec października.

---

## Otwarte pytania do właściciela

1. W którym pokoju stoją **fikus** i **skrzydłokwiat**? Jak daleko od okna i od
   kaloryfera? Czy azalia stoi przy płycie?
2. **iPhone** — czyj, jaki iOS? Czy powiadomienia mają iść na oba telefony?
3. Czy doniczka skrzydłokwiatu ma **zbiorniczek na wodę w spodzie**?
4. Kanał: **Web Push w aplikacji** (rekomendacja) czy prostszy **ntfy**?
5. Czy zaczynamy od **etapu 0** (limit Tuya)?

## Niewiadome, które rozstrzygnie pomiar

- Kody, jednostki i skale w chmurze. Czy światło i wilgotność powietrza w ogóle
  przychodzą (*Standard* czy *DP Instruction*).
- Ile wpisów na dobę robi jeden czujnik: raport okresowy, „na zmianę", zalewanie?
  Od tego zależy koszt w Tuya i rozmiar CSV.
- Czy kategoria to `zwjcy`.
- W którą stronę patrzy czujnik światła, przy ilu lx się nasyca i jak często raportuje
  światło.
- Ile wytrzymuje bateria.
- Ile pokazuje gleba w powietrzu, w wodzie i w każdej z trzech doniczek.
- Czy nowe urządzenia same pojawią się w projekcie Tuya (powiązanie „Automatic Link"),
  czy trzeba ponownie połączyć konto.
- Czy Smart Life przyjmuje glebę jako warunek automatyzacji i czy powiadomienie dostaje
  też drugi domownik.
- Rzeczywisty limit i zużycie zapytań Tuya.

---

## Źródła

Czujnik:
- Zigbee2MQTT ZS-301Z — https://www.zigbee2mqtt.io/devices/ZS-301Z.html
- konwerter — https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/tuya.ts
- zgłoszenia Zigbee2MQTT:
  - https://github.com/Koenkk/zigbee2mqtt/issues/27956
  - https://github.com/Koenkk/zigbee2mqtt/issues/28270
  - https://github.com/Koenkk/zigbee2mqtt/issues/29254
- ZHA — https://github.com/zigpy/zha-device-handlers/pull/4602
- kategoria `zwjcy`:
  - https://github.com/home-assistant/core/blob/dev/homeassistant/components/tuya/const.py
  - https://github.com/tuya/tuya-home-assistant/issues/910
- logi tylko dla „oficjalnych" punktów danych — https://github.com/jasonacox/tinytuya (`Cloud.getdevicelog`)
- tryb *DP Instruction* — https://github.com/jasonacox/tinytuya/discussions/284

Tuya:
- limit triala — https://www.tuya.com/vas/commodity/IOT_CORE_V2 (widziane tylko w wynikach
  wyszukiwania); użytkownik w styczniu 2026 potwierdza 26 000 — https://github.com/azerty9971/xtend_tuya/issues/718
- przedłużanie triala — https://github.com/tuya/tuya-home-assistant/blob/main/docs/faq.md

Rośliny:
- RHS — https://www.rhs.org.uk/plants/164300/ficus-microcarpa-moclame/details
- UF/IFAS:
  - https://edis.ifas.ufl.edu/publication/EP136
  - https://edis.ifas.ufl.edu/publication/EP161
  - https://mrec.ifas.ufl.edu/foliage/folnotes/spathiph.htm
- Missouri Botanical Garden (azalia) — https://www.missouribotanicalgarden.org/gardens-gardening/your-garden/help-for-the-home-gardener/advice-tips-resources/gardening-help-faqs/question/524/why-is-my-indoor-azalea-dropping-buds-and-leaves
- Clemson — https://hgic.clemson.edu/factsheet/peace-lily/
- SDSU — https://extension.sdstate.edu/care-peace-lilies
- Murator (azalia, skrzydłokwiat, fikus) — muratordom.pl
- przeliczanie lx → PPFD — https://research.csiro.au/anaccmethods/culture-handling/light-units-and-measurement

Powiadomienia:
- Apple — https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers
- WebKit:
  - https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
  - https://webkit.org/blog/16535/meet-declarative-web-push/
- znikające subskrypcje na iOS — https://bugs.webkit.org/show_bug.cgi?id=273063
- limity Chrome — https://developer.chrome.com/blog/web-push-rate-limits
- ntfy — https://docs.ntfy.sh/publish/
