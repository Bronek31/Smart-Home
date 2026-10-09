# Rośliny — przygotowanie

Plan przed wdrożeniem czujników w doniczkach, stan na 8.10.2026. Czujniki są kupione,
w kodzie zmieniło się dotąd tylko pobieranie przyrostowe i rozszerzone `--discover`
(etapy 0 i 1, 8.10); zbierania roślin jeszcze nie ma. Ten plik zbiera to, co wiadomo o czujniku,
o roślinach i o tym, gdzie nowa funkcja zahacza o istniejący kod.

Czynności dla właściciela, krok po kroku, są w osobnym pliku `ROSLINY-INSTRUKCJA.md`.

Oznaczenia:
- **[do sprawdzenia]** — liczba pochodzi z wyszukiwarki albo z cudzych pomiarów.
  Strony źródłowe były w tej sesji zablokowane, więc przed wpisaniem do kodu trzeba
  ją zmierzyć u nas.
- **[zgadnięte]** — punkt wyjścia ułożony pod zalecenia z literatury, a nie liczba
  z literatury.

**Czego chce właściciel:**
- trzy czujniki w trzech doniczkach;
- powiadomienia na telefon, gdy roślinę trzeba **podlać** albo **przestawić**, bo ma
  za mało światła;
- telefony: Android (strona zainstalowana z Chrome jako aplikacja) i iPhone.

**Gdzie stoją rośliny (8.10):**

| Roślina | Pokój | Okno pokoju |
|---|---|---|
| fikus | Salon | północ |
| skrzydłokwiat (do niedawna w Kuchni) | Salon | północ |
| azalia | Kuchnia | północ |

**Warunek właściciela (8.10):** odczyty z doniczek **nie mieszają się** z tym, co strona
pokazuje dziś. Wykresy, kafle, rzut, strefa komfortu i alarmy pleśni zostają wyłącznie
dla pokoi. Rośliny dostają **osobną zakładkę** w aplikacji.

---

## W skrócie

1. **Dziś, bez czujników:**
   - azalia: nie przesuszać, wylewać wodę z osłonki, nie zakręcać dla niej kaloryfera;
   - skrzydłokwiat: sprawdzić, czy w spodzie doniczki nie stoi woda;
   - fikus: nie przestawiać na ślepo — najpierw czujnik zmierzy światło.

   Szczegóły w „Rady już teraz".
2. **Warunek właściciela jest do spełnienia bez kompromisów.** Rośliny mają osobny
   tor danych (własna konfiguracja, pliki w `data/rosliny/`) i osobną stronę
   `rosliny.html`. Na dzisiejszej stronie dochodzi tylko pasek zakładek. Izolacji
   pilnuje test.
3. **Limit Tuya: najpierw pobieranie przyrostowe (etap 0, zrobione 8.10).**
   - Trial to pakiet **0,20 USD na miesiąc**. Nasze zapytania Tuya liczy jako
     zagraniczne, po 3,71 USD za milion, więc pakiet to ok. 54 000 zapytań. Tak wynika
     z panelu, który właściciel sprawdził 8.10.
   - Przy dawnym pobieraniu pełnych 7 dni październik zamknąłby się na ok. **47%**.
   - Czujnik w doniczce przy pełnym oknie kosztowałby więcej niż wszystkie pokoje
     razem, a przy zalewie wyczerpałby pakiet w dwa dni. Po wyczerpaniu staje także
     zbieranie z pokoi.
   - Po etapie 0 przebieg kosztuje ok. 7 zapytań zamiast 29.
4. **Czujnik może być wadliwą wersją.**
   - Model z naklejki to „C3007". Zigbee2MQTT ostrzega przed nim: lawina komunikatów,
     baterie na kilka dni.
   - Nikt nie sprawdził, czy tak samo zachowuje się za bramką Tuya.
   - Trzeba sparować i zmierzyć **od razu, w terminie zwrotu** (14 dni od dostawy przy
     zakupie przez internet).
5. **Powiadomienia na oba telefony, bez serwera i za darmo.** Nadawcą jest przebieg
   GitHub Actions, który i tak chodzi co godzinę. Doręcza Web Push wprost do
   zainstalowanej aplikacji. Odrzucenie z `TODO.md` („brak serwera") przestało
   obowiązywać.
6. **Progi z Twoich doniczek, nie z książki.**
   - Procent z takiej sondy to indeks względny, inny w każdym egzemplarzu i w każdej
     doniczce.
   - Aplikacja najpierw się uczy: zapisuje odczyt w powietrzu, odczyt zaraz po
     podlaniu i odczyt z chwili, w której sam podlewasz.
   - Realnie pierwsze powiadomienia „podlej" przyjdą za **4–6 tygodni**. Fikus zimą
     pije rzadko.
   - Do tego czasu może pilnować prosta automatyzacja w Smart Life
     **[do sprawdzenia po parowaniu]**.
7. **Brak powiadomienia nie znaczy „wszystko w porządku".**
   - Gdy wygaśnie trial Tuya albo token cron-job.org, powiadomienia ustaną po cichu.
   - Sygnałem życia jest niedzielne podsumowanie: przychodzi zawsze, także gdy nic
     się nie dzieje.
   - Zapasowym sygnałem jest mail „Kolektor stoi" od watchdoga.
8. **Zimą „przestaw" powie niewiele.**
   - Salon i Kuchnia mają okna na północ i do ok. 20 marca nie zobaczą bezpośredniego
     słońca (przy oknach dokładnie na północ).
   - Jedyne jasne miejsce to Sypialnia od południa, a tam jest najcieplej.
9. **Prywatność.** Pliki w `data/` są publiczne na Pages. Z czasów podlewania da się
   wyczytać, kiedy ktoś jest w domu. Z odczytów pokoi (prysznic, farelka) da się to
   już dziś.

---

## Czujnik

Na pudełku:
- **TZ-TR-301Z#AT**, „Zigbee Soil Moisture Sensor Temperature Humidity Luminance
  Detection, 4 in 1 (For tuya App)";
- model **ZS-301Z**, na bocznej naklejce **C3007**;
- 2× AAA (LR03), Zigbee 3.0.

W Zigbee2MQTT ten czujnik to `ZS-301Z` (Arteco), odcisk `TS0601` /
`_TZE284_o9ofysmo` albo `_TZE284_xc3vwx5a`.

| Co mierzy | Punkt danych (Zigbee) | Prawdopodobny kod w chmurze Tuya | Uwagi |
|---|---|---|---|
| wilgotność gleby | 3 | `humidity` (%) | **nazwa myląca** — to gleba, nie powietrze; Home Assistant tak samo traktuje kategorię `zwjcy` |
| temperatura powietrza | 5 | `temp_current` (÷10) | czujnik w szyjce, kilka cm nad ziemią |
| bateria | 14 | `battery_state` (low/middle/high) | **brak procentów**; „low" = 1–25% |
| wilgotność powietrza | 101 | `env_humidity` (%RH) **[do sprawdzenia]** | nad mokrą ziemią będzie wyższa niż w pokoju |
| natężenie światła | 102 | `dimmer` (0–10 000 lx) **[do sprawdzenia]** | otwór na czole głowicy; zakres kończy się na 10 000 lx, a czy czujnik się przy tym nasyca — do sprawdzenia |
| kalibracja gleby | 103 | `adjust_humidity` (±30) | ustawiana w Smart Life; przesuwa odczyt gleby o stałą |
| odstęp próbkowania | 104 | `adjust_sample_time` (30–1200 s) | domyślnie 600 s według zgłoszenia #29254 |

Źródła:
- konwerter Zigbee2MQTT (`zigbee-herdsman-converters`, `src/devices/tuya.ts`);
- zgłoszenia [#27956](https://github.com/Koenkk/zigbee2mqtt/issues/27956) i
  [#29254](https://github.com/Koenkk/zigbee2mqtt/issues/29254).

Kody w chmurze pochodzą z tabeli w #27956, a nie z naszego konta. Rozstrzygnie je
dopiero `odkryj.yml`.

**Z instrukcji (V2.0):**
- Czujnik mierzy co 30 s. Wysyła odczyt, gdy gleba zmieni się o 3%, temperatura
  o 0,3 °C albo wilgotność powietrza o 5%. Seria gleby idzie więc **schodkami po co
  najmniej 3 punkty**.
- Instrukcja nie mówi, kiedy wysyłane jest światło, ani czy jest raport okresowy.
- Krótkie wciśnięcie przycisku wymusza odczyt. Przytrzymanie 5 s włącza parowanie.
- Sondę wbija się na co najmniej 2/3 długości (ok. 5,5 z 8,2 cm), powierzchnią
  pomiarową przy ziemi.
- Kalibracja: „Moisture detection may have some deviations, users calibration can be
  performed on the APP". To jest pole 103 — stałe przesunięcie samej gleby.
  Temperatury i światła się nie kalibruje.

**Wersja z pomiarem żyzności** (EC 0–5000 µS/cm) ma rozwidlony szpic sondy i dodatkowy
punkt danych (112). Etykieta „4 in 1" wskazuje na zwykłą wersję. Rozstrzygnie
`odkryj.yml`.

**Pułapki chmury Tuya:**
- Chmura zwraca logi tylko dla punktów danych z „oficjalnej" specyfikacji produktu
  (tinytuya, `Cloud.getdevicelog`). Punkty 101–104 są niestandardowe, więc w trybie
  *Standard Instruction* mogą nie przyjść wcale.
- Wtedy na iot.tuya.com trzeba przełączyć **wyłącznie produkt czujnika roślin** na
  *DP Instruction*. Zmiana działa po kilku–kilkunastu godzinach.
- **Nie przełączać czujników pokojowych.** Zmieniłyby się ich kody (`va_temperature`
  i reszta), a kolektor zgubiłby serie.

**Zalewanie komunikatami** (C3007, płytka „ZSSF01"):
- Opis Zigbee2MQTT: *„prohibitively high amount of messages … very fast battery drain
  (matter of days) … set values not persisting"*.
- W #29254 to ok. 1 komunikat na sekundę, a ustawiony odstęp wraca do 600 s.
- Zgłoszenia dotyczą Zigbee2MQTT, nie bramki Tuya, więc u nas to niewiadoma.
- Ten sam czujnik obciąża bramkę, przez którą idą czujniki pokojowe. Po parowaniu
  porównamy liczbę ich raportów z dnia przed i po (z CSV, bez zapytań do Tuya).
- **Jeśli się potwierdzi** — tysiące wpisów na godzinę albo bateria `low` w ciągu
  tygodnia — czujniki zwrócić, a nie łatać w kolektorze. Oprogramowanie nie naprawi
  baterii, a pobieranie takich logów zjadłoby limit Tuya.

**Co widzi chmura (8.10, „Pokaż urządzenia w Tuya", przebiegi 37807246328 i 37807716662):**

| Roślina | Identyfikator | Kategoria | Pola w specyfikacji |
|---|---|---|---|
| Fikus | `bfe5bdf2b91c53dfd1eaiy` | `zwjcy` | `humidity` (%, gleba), `temp_current` (℃, 0…1000, scale 1), `temp_unit_convert`, `battery_state` |
| Skrzydłokwiat | `bfa2be765aa6176805rhly` | `zwjcy` | jw. |
| Azalia | `bf262a90fc72e1aef65arq` | `zwjcy` | jw. |

- **Produkt `0ints6wl` („土壤温湿度")**, czyli w Zigbee2MQTT rodzina **ZS-300Z / ZS-304Z**
  (`_TZE284_0ints6wl`), a nie ZS-301Z.
  - Ostrzeżenie o „C3007 / ZSSF01" dotyczy ZS-301Z, więc tu nie musi obowiązywać.
  - Ta rodzina ma te same pola 3, 5, 14, 101 (wilgotność powietrza) i 102 (światło).
  - Do tego ustawienia: 103 próbkowanie gleby 5–3600 s, 104 kalibracja gleby,
    105 wilgotności, 106 światła (±1000 lx) i 107 temperatury (±2 °C), 110 próg suchej
    gleby i 111 alarm „sucho". ZHA zgłaszało, że ten alarm miga co ok. 10 minut.
- Nowe urządzenia pojawiły się w projekcie same, bez ponownego łączenia konta.
- **Tempo wpisów** w godzinie parowania i testów (15:18–16:18 UTC):
  - Fikus 134, Skrzydłokwiat 121, Azalia 111;
  - prawie same `humidity` (gleba): 105–125 na godzinę, czyli co ok. 30 s, choć wartość
    stała;
  - temperatura 6–9 na godzinę.

  Przez logi to ok. 2 strony na czujnik na przebieg, więc pakiet to zniesie. Bateria
  przy raporcie co 30 s — niekoniecznie. Pomiar do powtórzenia po godzinie spokoju przy
  ustawionym próbkowaniu 600 s.
- **Godzina spokoju** (16:15–17:15 UTC, nikt nie dotykał czujników; przebieg 37815058708):
  - Fikus 10, Skrzydłokwiat 8, Azalia 10 wpisów na godzinę, czyli ok. 240 na dobę;
  - gleba 1–3 razy na godzinę, temperatura 1–3, wilgotność powietrza 1–2, światło 1–2,
    bateria 2.

  Raport co 30 s był więc skutkiem parowania i zmian ustawień, a nie pracy czujnika.
  W spokoju zalewania nie ma. Godzinna zakładka w kolektorze roślin to zwykle jedna
  strona, a tydzień historii to ok. 17 stron na czujnik.
- **Zalew przy parowaniu i ustawianiu jednak był** (kolektor 8.10, przebieg 37828561329,
  pomiar „najgęstszej pełnej strony"):
  - ok. 15:57 UTC (17:57 u właściciela, tuż przed wciśnięciem przycisków o 18:03) każdy
    z trzech czujników wysłał 100 wpisów w 131–137 s, w 96–98% samą glebę — jeden wpis
    co ok. 1,4 s, jak w zgłoszeniu Zigbee2MQTT #29254;
  - minął sam; od ok. 16:15 to 8–10 wpisów na godzinę, a wciśnięcie przycisków
    o 17:40 UTC zalewu nie wywołało.
  - „Pokaż urządzenia" o 16:18 liczyło w oknie 15:18–16:18 tylko 134 wpisy. Te same logi
    czytane po 18:00 mają ponad 100 wpisów w 2,5 minuty tego okna. Albo Tuya dopisuje
    logi z opóźnieniem ponad godziny, albo przełączenie na *DP Instruction* (16:45)
    zmieniło to, co logi pokazują wstecz. **[niewyjaśnione]** Dla roślin bez znaczenia
    (zalew to powtórzona ta sama gleba), dla pokoi — patrz zakładka 6 godz.
  - Kolektor to przeżył tak, jak zaprojektowano: dwa przebiegi po 12 zapytań na roślinę
    nadrabiały te 20 minut, trzeci pominął zalaną zakładkę i doszedł do bieżącej
    godziny. **Stan ustalony: jedno zapytanie na roślinę na przebieg** (przebieg 19:01,
    10 zapytań na cały przebieg z pokojami).
  - Wniosek dla baterii: zalew to minuty po parowaniu albo zmianie ustawień, nie stała
    praca. Ustawień czujników nie zmieniać bez potrzeby; baterię obserwować tydzień.
- **Bateria:** Skrzydłokwiat wysłał już `battery_state=high`. Fikus i Azalia jeszcze nic,
  więc aplikacja pokazuje domyślne „low" — to brak pierwszego raportu, nie stan baterii.
- **Brakowało światła i wilgotności powietrza.** W trybie *Standard Instruction* chmura
  pokazywała tylko pola ze standardu kategorii `zwjcy` — dokładnie to, przed czym
  ostrzegał tinytuya. Rozwiązane przełączeniem na *DP Instruction* (niżej).
- Dzisiejsze `classify()` wzięłoby `humidity` za wilgotność powietrza — potwierdzone
  na żywo.

**Po przełączeniu na *DP Instruction*** (8.10 ok. 16:45 UTC; przebieg 37812052768,
zadziałało od razu, bez czekania godzinami):

| Kod w chmurze | Co to jest | Typ, zakres | Odczyt 16:52 UTC (Fikus) |
|---|---|---|---|
| `humidity` | wilgotność gleby | Integer, %, 0…100 | 10 |
| `temp_current` | temperatura powietrza | Integer, ℃, scale 1 | 22,5 °C |
| `env_humidity` | wilgotność powietrza | Integer, %, 0…100 | 51 |
| `illumiance` (sic, z literówką) | światło | Integer, 0…10 000, bez jednostki | 160 |
| `battery_state` | bateria | low / middle / high | high |
| `water_warning` | wbudowany alarm „sucho" | Boolean | True (sonda w powietrzu) |

Ustawienia (`functions`):
- `soil_sampling` 5…1200 s;
- `soil_calibration` ±30;
- `humidity_calibration` ±30%;
- `illumiance_calibration` ±1000 lx;
- `temperature_calibration` ±2,0 °C;
- `soil_warning` 0…80% — próg wbudowanego alarmu „sucho".

Wnioski:
- **Kody do `rosliny.json` są znane.** Dzisiejsze `classify()` dałoby `env_humidity`
  i `humidity` jako dwa razy „hum", a `illumiance` by odrzuciło. Jawne kody w
  konfiguracji to jedyna bezpieczna droga.
- **Baterie są dobre** („high" na wszystkich odczytanych). Wcześniejsze „Niska" było
  domyślną wartością sprzed pierwszego raportu.
- ~~`soil_sampling` nie zmienia tempa wysyłania.~~ Tuż po zmianie na 600 s gleba dalej
  przychodziła co ok. 30 s (110–113 wpisów na godzinę). **Godzina spokoju to obaliła**
  (wyżej): bez dotykania czujnik wysyła 8–10 wpisów na godzinę, glebę 1–3 razy.
  - Kolektor roślin i tak ma krótką zakładkę (godzina, nie 6), przerzedzanie przed
    zapisem do CSV i budżet — na wypadek, gdyby zalew wrócił po dotknięciu czujnika.
- **`water_warning` z progiem `soil_warning`** to gotowy, liczony na samym czujniku
  alarm „sucho". To dobra podstawa tymczasowej automatyzacji w Smart Life
  (warunek „water_warning = alarm"). ZHA zgłaszało, że ten alarm potrafi migać, więc
  kolektor go zapisuje, ale do decyzji nie używa.

**Pierwsze odczyty (8.10, 18:09):** sparowane, wszystkie trzy obok siebie na jednym
stoliku, w zaciemnionym pokoju, po wciśnięciu przycisków.

| | Fikus | Skrzydłokwiat | Azalia | Ocena |
|---|---|---|---|---|
| temperatura | 23,1 °C | 23,5 °C | 23,5 °C | rozrzut 0,4 °C, dokładność ±0,5 |
| wilgotność powietrza | 51% | 49% | 48% | rozrzut 3 pkt, dokładność ±5 |
| gleba w powietrzu („sucho") | **10%** | **11%** | **8%** | punkt zerowy skali R — do `rosliny.json` |
| światło | 62 lx | 0 lx | 0 lx | 62 lx w ciemności do wyjaśnienia (źródło w polu widzenia albo odczyt sprzed zgaszenia) |
| bateria | Niska | Niska | Niska | od razu po włożeniu baterii — najpewniej domyślna wartość, zanim przyszedł pierwszy raport; do obserwacji |

Panel Smart Life nazywa pola „Env Temperature", „Env Humidity", „Soil Humidity"
i „Dimmer" (światło). Pasuje to do kodów z #27956 (`env_humidity`, `dimmer`), co
dopiero potwierdzi `--discover`. Temperatura po wciśnięciu przycisku i trzymaniu
w dłoni jest zawyżona; porównanie z czujnikiem pokojowym — po godzinie spokoju.

**Noc obok siebie (8/9.10, 18:45–05:00 UTC, próbkowanie 1200 s, nikt nie ruszał):**
porównanie z chmury, sprawdzone dwiema metodami i przez sceptyka.

| | Fikus | Skrzydłokwiat | Azalia | Wniosek |
|---|---|---|---|---|
| temperatura − Salon | +0,4 °C | +0,3 °C | +0,4 °C | przy świeżym raporcie ok. +0,2 °C; bez przesunięcia |
| wilgotność powietrza − Salon | −4 | −4 | −2 | ok. −3 ±1 dla wszystkich; bez przesunięcia |
| gleba w powietrzu (mediana) | 10 | 11 | 9 | „sucho": 10 / 11 / **9** (azalia było 8) |
| wybudzenie co | 1239 s | 1160 s | 1218 s | zegary rozjechane o ±3% |
| bateria | high | high | high | |

- **Czujniki raportują tylko zmiany:** temperaturę co ok. 0,4 °C, wilgotność powietrza
  co 3 punkty. Trzymana wartość przy powolnym trendzie jest więc o tyle spóźniona;
  „przesunięcia" z tabeli to w dużej części ten próg. Salon (raport co godzinę) nie
  jest wzorcem lepszym od nich.
- **Gleba ma pojedyncze dołki o 3–4 punkty** (azalia 9 → 5 → 9, skrzydłokwiat
  11 → 8 → 11, każdy na jeden raport). Reguły na telefon muszą je przeczekać
  (projekt reguły „Podlej" już mówi „przez ≥ 2 godz."). Wykrywanie podlań ich nie łapie
  (skok w górę o 10), a nauka by je odrzuciła (mediany).
- **Gleba w powietrzu zależy trochę od temperatury:** azalia 8 przy 23–25 °C po
  południu, 9 nocą przy 22 °C. Różnica 1 punktu to ok. 0,02–0,03 R.
- **Światło przychodzi nocą, ale nie przy każdym wybudzeniu:** przerwy 61–116 min
  (skrzydłokwiat najdłuższe), wilgotność powietrza raz po 2 godz. 1 min. Trzymanie
  wartości podniesione z 2 do 3 godz. Pojedyncze 108 lx na fikusie o 19:27 UTC przy
  zerze u sąsiadów — krótkie, sztuczne światło tylko na jednej głowicy.
- **Skrzydłokwiat gubi najwięcej wybudzeń** (ok. 10 z 33 bez żadnego wiersza; część
  to przerzedzanie, ale też pominięte kody, które były „należne"). Po wbiciu sprawdzić,
  czy nie gorzej — mokra ziemia i ceramika osłabiają zasięg.
- **`water_warning` przychodzi tylko jako zdarzenie** (ostatnie 15:43–15:50), bez
  powtórek. Nie nadaje się na stan — kolektor go zapisuje, decyzje biorą się z gleby.
- **Bramka nie cierpi:** pokoje wysłały tej nocy 11–12 raportów, tyle co przed
  parowaniem (6/7.10: 11–17, 7/8.10: 11–12).
- **Koszt:** 9 zapytań na przebieg plus token, po jednym na roślinę, 8–10 wpisów na
  godzinę na czujnik. Dwa razy w nocy token pobrany 3–4 razy zamiast raz (02:01,
  04:01) — do zbadania przy okazji, to kilka zapytań na dobę.
- Światła w dzień nie porównaliśmy (wschód 04:52 UTC). Pod tą samą lampą 8.10
  o 17:15 UTC: 103 / 122 / 160 lx, czyli ±25%. Ustawienie głowicy w doniczce zmieni
  więcej, więc dziennego testu nie robimy.

**Pierwsze godziny w doniczkach (9.10):**
- Sondy wbite ok. 8:33, `od` = 8:35+02:00. Pierwsze odczyty w ziemi przyszły
  8:35:26–59 (po wciśnięciu przycisków): fikus 17, skrzydłokwiat 19, azalia 16 —
  6–8 punktów nad powietrzem, czyli sucho.
- Podlanie ok. 9:40, wykryte u wszystkich trzech (pierwsze odczyty po nim):
  fikus 17 → **100** o 9:51 (woda przy sondzie, dalej 100 o 11:13), azalia 18 → 66
  → 69 → 59 → 57, skrzydłokwiat 20 → 58 → 56. Wymagało to poprawki: nauka dostawała
  szereg obcięty do startu nauki i pierwsze podlanie tuż po nim nie miało „przed".
- Przy mokrej ziemi wilgotność powietrza przy głowicy skacze z 55–60 do 67–81%.
- Światło przed południem: fikus 377–640 lx, skrzydłokwiat 95–415 lx, azalia
  (kuchnia) 429–1000. Poranne 11 lx fikusa było zaraz po wbiciu — fikus nie jest
  ciemniejszy. Ok. 11:55 oba czujniki w salonie pokazały 0 lx naraz (zasłony?).
  Azalia dwa razy dokładnie 1000 — do obserwacji, czy to nie sufit pomiaru (rano przy
  oknie 2122, więc raczej nie).
- Skrzydłokwiat raportuje w doniczce regularnie, co ok. 19–20 min.
- **Skala po pierwszym podlaniu (9.10, przebieg 14:31 UTC):**
  - skrzydłokwiat: szczyt 57, R 1,02, próg 0,50 (zimowy) = gleba ok. 34%, werdykt „ok";
  - azalia: szczyt 57, R 1,0, próg 0,75 = gleba ok. 45%, werdykt „ok";
  - fikus: podlanie pominięte (`pomin_podlania` — woda stała w osłonce, sonda 100 przez
    5 godz.; po wylaniu ok. 15:30 gleba spada, 95 o 15:42). Skala z następnego podlania,
    ok. 100 ml i wylanie wody z osłonki po 15 min.
  - Światło fikusa po wyjmowaniu doniczki dalej podobne do skrzydłokwiatu (283 vs 370 lx
    o 16:00) — głowica się nie obróciła.

**Światło:**
- Otwór jest na czole głowicy, więc przy pionowej sondzie czujnik patrzy najpewniej
  **w bok** **[do sprawdzenia]**.
- Wynik zależy od tego, w którą stronę obrócona jest głowica, a liście ją zasłaniają.
- Przeliczanie na DLI (fotony na dobę) będzie niepewne ok. 2×. Wiarygodny jest
  **trend w jednym miejscu**.
- Głowicę ustawić czołem do okna i więcej jej nie ruszać.

---

## Rośliny

### Co widać na zdjęciach

| | Fikus 'Ginseng' (*Ficus microcarpa*) | Skrzydłokwiat (*Spathiphyllum*) | Azalia doniczkowa (*Rhododendron simsii*) |
|---|---|---|---|
| Doniczka | czarna ceramika z podstawką, ok. 12–14 cm; na wierzchu mech | biała, z rowkiem nisko na ściance — **możliwe dno z rezerwuarem**, czyli woda w spodzie, której sonda nie widzi | **plastikowa doniczka w osłonce**; woda w osłonce jest dla sondy niewidoczna; na wierzchu kora; pień na paliku |
| Liście | zdrowe, ciemnozielone, przyrosty na czubkach | **brązowe, zaschnięte końcówki** na 4–5 liściach, kilka bladych | zdrowe; kwitnie, nowe przyrosty; u podstawy pnia mały pęd |
| Miejsce | Salon | Salon (zdjęcie zrobione w Kuchni) | Kuchnia, blat |

### Potrzeby

Wszystkie liczby w tej tabeli pochodzą z wyciągów wyszukiwarki i są
**[do sprawdzenia]**.

| | Fikus | Skrzydłokwiat | Azalia |
|---|---|---|---|
| Podlewanie | przesuszyć wierzchnie 2–3 cm; znosi przesuszenie dużo lepiej niż przelanie | równo wilgotno, bez stania w wodzie; podlać, gdy wierzch wyschnie na 2,5–5 cm; **powtarzane więdnięcie daje żółte liście i brązowe brzegi** | **nigdy nie przesuszyć**; zaschnięty torf trudno nawilżyć — ratunkiem jest zanurzenie doniczki; wylewać wodę z osłonki |
| Zima (X–II) | mniej wody, bez nawozu | mniej wody, bez nawozu | podlewanie bez zmian — ziemia stale wilgotna |
| Temperatura | idealnie 18–24 °C, zimą może być chłodniej (16–20); nie lubi przeciągów ani kaloryfera | dzień 20–29 °C; **poniżej ok. 15 °C ryzyko uszkodzeń** | chłodno: 10–20 °C (MBG), polskie źródła 10–15; przyjęte 10–18 °C; przy ≥ 24 °C gubi pąki i liście |
| Wilgotność powietrza | 40–60% | liczby w źródłach brak; suche powietrze to najczęstsze polskie wyjaśnienie brązowych końcówek (obok nieregularnego podlewania i nawozu) | ≥ 50% |
| Światło | jasno, bez gwałtownych zmian; **źle znosi przestawianie** — gubi liście i po zmianie miejsca potrzebuje ok. 4 tygodni spokoju; słońce znosi | jasne rozproszone, bez słońca; minimum ok. 800 lx | jasno, chłodno, bez bezpośredniego słońca |
| Światło w liczbach | ok. 1 100–2 150 lx w pomieszczeniu (zalecenia dla innych fikusów) | DLI ok. 0,65 mol/m²/dobę (≈ 10 000 lx·h dziennego światła) | DLI 1,7–2,1 (badania szklarniowe) |

Źródła: RHS, UF/IFAS (EP136, EP161, MREC), Missouri Botanical Garden, Clemson HGIC,
SDSU Extension, Epic Gardening, Murator. Pełna lista na dole.

Przelicznik dla światła dziennego: 1 mol/m²/dobę ≈ 15 000 lx·h (1000 lx ≈
18,5 µmol/m²/s). Dla lamp nie działa.

### Co mówią nasze dane

Zmierzone na czujnikach pokojowych, ważone czasem, z wyłączeniem skoków i znanych
artefaktów. Okno to 1–8.10.2026, ogrzewanie działa od 1.10.

| Pokój | Temperatura: średnio (min–max) | Wilgotność: średnio (min–max) |
|---|---|---|
| Salon (płn.) — fikus, skrzydłokwiat | 20,9 °C (18,9–22,3) | 58% (46–69) |
| Kuchnia (płn.) — azalia | 20,8 °C (19,6–22,2) | 59% (48–69) |
| Sypialnia (płd.) | 22,4 °C (20,8–23,5) | 53% (45–60) |
| Łazienka | 21,4 °C (20,5–22,4) | 60% (50–74) |

**Ciepło a azalia:**
- Kuchnia ma średnio 20–21 °C, najniżej 19,4 °C. Od 17.09 **ani razu** nie zeszła
  do 18 °C. W drugiej połowie września była powyżej 20 °C przez 81% czasu, a od 1.10
  przez 96%.
- Gotowania przy czujniku nie widać: największy wzrost w godzinę to +0,7 °C.
- W żadnym pokoju nie ma 10–18 °C.
- **Nie zakręcać dla azalii kaloryfera w kuchni.** Schłodzenie kuchni do 17 °C przy tej
  samej ilości pary podnosi wilgotność z 59% do ok. 75%. Próg pleśni przy 0 °C na
  dworze to ok. 58%, więc alarm pleśni na stronie zacząłby krzyczeć.
- Chłodniejsze miejsce przy szybie pokaże czujnik w doniczce, bo mierzy temperaturę
  przy samej roślinie.

**Wilgotność spada:**
- Średnia dobowa 1.10 → 7.10: Salon 61 → 54%, Kuchnia 64 → 56%, Sypialnia 56 → 50%.
- Szacunek na mróz, z modelu, a nie z pomiaru: **32–44%**. Zimą skrzydłokwiat i azalia
  będą najpewniej poniżej swoich 50%.
- **Nie nawilżać mieszkania dla roślin**, bo strona pilnuje progu pleśni. Wystarczy
  trzymać rośliny razem i nie zraszać kwiatów azalii.

**Światło:**
- Od równonocy jesiennej do wiosennej słońce wschodzi i zachodzi po południowej
  stronie linii wschód–zachód. Okna na północ nie dostaną bezpośredniego słońca do
  ok. 20.03.
- 21.12 dzień ma 8 godz., a słońce w południe stoi na 16°.
- Szacunek z literatury, nie z naszych czujników **[do sprawdzenia]**: w grudniu
  i styczniu po północnej stronie wszystkie trzy rośliny będą poniżej „dobrze",
  a azalia i fikus blisko swojego minimum lub pod nim.

### Rady już teraz

- **Azalia (Kuchnia):**
  - Jeśli stoi przy płycie albo czajniku — odsunąć.
  - Po podlaniu wylać wodę z osłonki. Nie lać wody na głowicę czujnika.
  - **Nigdy nie dopuścić do przesuszenia.** Jeśli zaschnie: **wyjąć czujnik**, wyjąć
    plastikową doniczkę z osłonki i zanurzyć ją w letniej wodzie, aż przestaną lecieć
    bąbelki (15–30 min), przytrzymując, bo sucha ziemia pływa, a pień na paliku
    przeważa. Odsączyć, wylać wodę z osłonki, włożyć czujnik w to samo miejsce.
  - Woda z kranu w Katowicach jest miękka (ok. 5 °dH według PSSE)
    **[do sprawdzenia]**, więc nadaje się do podlewania.
  - Usuwać przekwitłe kwiaty. Nie nawozić w czasie kwitnienia. Nie przesadzać do
    wiosny; wtedy do kwaśnej ziemi dla azalii.
  - Mały pęd u podstawy pnia: jeśli to odrost podkładki, wyciąć **[do sprawdzenia]**.
  - Przy 20–21 °C kwitnienie będzie krótsze niż w chłodzie.
- **Skrzydłokwiat (Salon):**
  - Obciąć brązowe końcówki, zostawiając cienki brązowy pasek. Nie odrosną.
  - Zimą przy suchym powietrzu nowe mogą się pojawiać i nie jest to błąd podlewania.
    Ważne, żeby nie dopuszczać do więdnięcia.
  - Sprawdzić, czy w spodzie doniczki nie stoi woda.
- **Fikus (Salon):**
  - Jesienią, przy mniejszym świetle, i po każdym przestawieniu gubi część liści
    przez 2–4 tygodnie. To nie pragnienie: nie podlewać częściej i nie przestawiać
    z powrotem.
  - **Nie przestawiać na ślepo.** Czujnik jest miernikiem światła. Przed wbiciem
    na stałe można nim sprawdzić około południa kilka kandydujących miejsc
    (`ROSLINY-INSTRUKCJA.md`, krok 4). Przestawić raz, do najjaśniejszego, a dopiero
    potem wbić czujnik — nauka zaczyna się w docelowym miejscu.
- **Wszystkie:**
  - Co 2 tygodnie obejrzeć spód liści. Suche, ciepłe powietrze sprzyja przędziorkom
    (azalia, fikus), a na fikusie zdarzają się wciornastki (srebrzyste smugi).
  - Fikusa i skrzydłokwiatu nie nawozić do marca. Nawóz podnosi odczyt sondy, więc
    wiosną trzeba będzie sprawdzić progi.

---

## Dlaczego nie można po prostu dopisać czujników

Sprawdzone na prawdziwym `index.html` z fiksturą `dane.js` i trzema roślinami,
opisanymi tak, jak opisałby je dzisiejszy `fetch.py`. Wartości roślin w fiksturze były
wymyślone, więc pewny jest kierunek i lista dotkniętych miejsc, a nie same liczby.
Wiersz `diagnose()` pochodzi z symulacji w Pythonie.

| Gdzie | Co by się stało |
|---|---|
| `classify()` (`fetch.py:73`) | `humidity` + `%` → `hum`: **gleba jako wilgotność powietrza**. `dimmer`, `bright_value`, `illuminance*` → odrzucone: **światła nie byłoby w ogóle** |
| pamięć kodów w manifeście (`fetch.py:1119-1124`) | pierwsza zła klasyfikacja zostaje na zawsze — późniejsza poprawka `classify()` jej nie rusza |
| `diagnose()` → watchdog | mokra ziemia (75% przy 10 °C na dworze) = „wilgotność powyżej progu pleśni przez 100% doby". **Zgłoszenie przez całą zimę** |
| kafle, tabela, diagnostyka | 5 → 8 kafli, „4/4 OK" → „7/7 OK" albo „4/7 OK · 3 uwaga"; trzecia roślina (siódme urządzenie z palety) dostaje kolor Łazienki |
| wykresy temperatury i wilgotności | pokoje spadają do ok. 1/5 wysokości osi; gleba na wykresie wilgotności powietrza |
| rada o wietrzeniu | średnia mieszkania z roślinami: werdykt zmienił się z „Najlepszy moment na wietrzenie" na „Otwarte okno schłodzi mieszkanie" |
| rzut, rytm doby, strefa komfortu, kalendarz | skale barw rozjechane; rytm doby domyślnie pokazuje „Fikusa" |
| koszt w Tuya | pełne okno 7 dni przy raporcie co 600 s to ok. 51 stron logów na czujnik na przebieg. Przy zalewaniu 3 × 300 stron to ok. 930 zapytań na przebieg: miesięczny pakiet znika w dwie doby, a przebieg (ok. 19 min) ociera się o `timeout-minutes: 20` |

Wniosek: rośliny nie mogą trafić do `data/index.json` ani do `data/RRRR-MM.csv`.

---

## Jak to zbudować

### Etap 0: pobieranie przyrostowe (zrobione 8.10)

**Do 8.10:** 29 zapytań na przebieg.
- Token i lista urządzeń.
- Pełne 7 dni logów dla czterech pokoi: 6–7 stron po 100 wpisów każdy.
- Klimatyzator.
- Najpewniej nieudana próba API v2.

Panel Tuya 8.10 po południu: 6229 zapytań = 0,0231 USD, co do kilku zgodne z 29 ×
liczba przebiegów. Liczy się więc każde zapytanie, także o token i nieudane.

Przebiegów jest ok. 28 na dobę: 24 z cron-job.org i zwykle 4 z zapasowego
harmonogramu GitHuba. Każdy push na `main` z czymś poza `data/` (także samym `.md`)
odpala dodatkowy przebieg.

**Jak działa teraz** (szczegóły w `KONTEKST.md`, sekcja z 8.10):
- Kursor `pobrane_do` w `data/index.json`, zakładka 6 godz., podłoga 7 dni.
  Klimatyzator bez zmian (12 godz., `last_log`).
- Okno czytane odcinkami po jednej stronie:
  - zmieścił się → następny dwa razy dłuższy;
  - nie zmieścił się, a wpisy przyszły rosnąco → przesunięcie po znacznikach czasu;
  - inaczej → o połowę krótszy.
- Kursor nigdy się nie cofa i nie przeskakuje za „najnowszy widziany wpis".
- Budżet 30 zapytań na czujnik na przebieg, z ostrzeżeniem w logu.
- Najpierw API v1, licznik zapytań na końcu logu.
- 20 nowych testów na atrapie Tuya, w obu kolejnościach logów. 14 odrzuca dawne
  pobieranie pełnego okna. Pozostałe 6 dotyczy zagrożeń, których pełne okno nie miało
  (krótkie strony, otwarty start, zakładka po długiej przerwie, zalew w dwie minuty),
  i każdy z nich odrzuca pierwszą wersję pobierania przyrostowego sprzed przeglądu.

**Szacunek** (pakiet ok. 54 000 zapytań na miesiąc):

| Wariant | Zapytań na przebieg | Na miesiąc | Pakietu |
|---|---|---|---|
| do 8.10, pełne okno | 29 | ok. 25 400 | 47% |
| bez roślin | ok. 7 | ok. 6 100 | 11% |
| z roślinami, bez zalewania | ok. 10 | ok. 8 700 | 16% |
| zalew wszystkich trzech roślin (budżet 30 na każdą) | do ok. 97 | do ok. 84 000 | ponad 100% |

Ostatni wiersz to powód, dla którego zalewający czujnik nie może iść przez logi.
Etap 2 da roślinom mniejszy budżet, a przy potwierdzonym zalewie — zapytanie o status
zamiast logów.

### Etap 1: rozpoznanie czujników

`--discover` (workflow „Pokaż urządzenia w Tuya") dostaje:
- surową specyfikację (`status` i `functions`) i bieżące wartości, po jednym zapytaniu
  o specyfikację na urządzenie (do 8.10 były dwa);
- **tempo wpisów z ostatniej godziny**, tylko dla urządzeń spoza manifestu (`data/index.json`),
  najwyżej 3 strony na urządzenie, z przeliczeniem na dobę po znacznikach czasu;
- licznik zapytań w logu;
- przy czujniku roślin ostrzeżenie „NIE dopisuj do `TUYA_DEVICE_IDS`";
- `timeout-minutes: 10` w `odkryj.yml`, dotąd jedynym workflowie bez limitu czasu.

Zrobione 8.10 razem z etapem 0. Integracja Claude'a z GitHubem nie może uruchamiać
workflowów (403), więc `odkryj.yml` rusza też sam po każdej zmianie swojego pliku na
`main`. Koszt: ok. 15–25 zapytań.

**Jeśli potwierdzi się zalewanie**, logi roślin odpadają. Stan bierzemy wtedy jednym
zapytaniem o status dla wszystkich trzech (`/v1.0/devices?device_ids=…`). Może być
za darmo, jeśli lista urządzeń zwraca już `status` **[do sprawdzenia]**. Kosztem jest
jedna próbka na godzinę, bez krzywej światła w ciągu dnia. Ale wcześniej — zwrot
czujników.

### Etap 2: osobny tor danych

**Stan na 8.10 wieczorem: zrobione.**

Odstępstwa od projektu niżej, wymuszone pomiarem:
- **Zakładka roślin 1 godz., nie 6**, i budżet 12 zapytań na czujnik. W godzinie
  parowania gleba przychodziła co ok. 30 s, więc 6 godz. zakładki to było ok. 8 stron
  na przebieg. W spokoju to 8–10 wpisów na godzinę, czyli zakładka mieści się w jednej
  stronie i jest czytana naprawdę (uwaga recenzenta o pomijanej zakładce dotyczyła
  tempa z parowania).
- **Przerzedzanie w kolektorze** (`rosliny.zwin`): zostaje zmiana wartości albo jeden
  wiersz na godzinę na serię. Działa na całym pliku miesięcznym przy każdym przebiegu,
  bo zakładka dokłada wycięte wiersze z powrotem; jest idempotentne.
- **Kursory i skale roślin w `stan.json`**, nie w `index.json`.
- **Nauka zaczyna się godzinę po `od`** (wbicie sondy). Wcześniejsze odczyty, w tym
  testy w wodzie, nie uczą progów — wbicie w wilgotną ziemię wyglądałoby jak podlanie.
  `od` musi mieć godzinę i strefę (`2026-10-09T08:30:00+02:00`): sama data to północ
  UTC, a godzina bez strefy liczy się w strefie maszyny. Godzinę wbicia zaokrąglamy
  w górę.

**Po przeglądzie (8.10 wieczorem):**
- **Błąd toru** zostawia w `stan.json` kursory, skale i ostatnie werdykty (`updated`
  sprzed błędu), dopisuje `blad` i alert dla watchdoga. Kursory zapisują się zaraz po
  dopisaniu odczytów do CSV. Błąd obliczeń jednej rośliny nie zasłania pozostałych.
- **Limit czasu toru: 300 s** (`SIGALRM`, wyjątek spoza `Exception`). Wolność to nie
  wyjątek, a zabite zadanie nie zapisałoby pokoi.
- **Wykrywanie podlań jest liniowe.** `przed` i `szczyt` to mediany 2–6 godz. przed
  skokiem i po nim; szczyt dopiero 6 godz. po podlaniu. Podlanie uczy skali tylko wtedy,
  gdy mediany różnią się o 10 punktów. Przerwa w danych tuż przed podlaniem go nie gubi.
- **Nauka patrzy 60 dni wstecz** (trzy podlania fikusa zimą), więc kolektor czyta pliki
  miesięczne z tego okresu, nie zawsze dwa ostatnie.
- **Martwa strefa ±1 punktu dla gleby** przy przerzedzaniu — drgnięcie 10↔11 to nie
  zmiana.
- **Werdykt „czujnik"**: cisza, brak gleby od 12 godz. przy działającej reszcie, nagły
  spadek gleby do poziomu powietrza po `od` (sonda wyjęta; watchdog dopiero po 2 godz.,
  bo zanurzanie azalii trwa pół godziny). Powolne schnięcie do sucha to dalej „podlej".
- **Do watchdoga** idzie tylko `do_zgloszenia` z każdej rośliny i błędy toru. Pusta
  lista roślin czyści alerty.
- **Pokój wpisany jako „czujnik"** zostaje pokojem, a tor roślin zgłasza błąd.
- **Pierwszy przebieg** bez kursora bierze dobę, a nie 7 dni.
- Doby światła liczone od lokalnej północy; dzisiejszą niepełną widać po `pokrycie`.
- **Jeszcze nie ma histerezy werdyktu.** Przy szumie ±1 koło progu werdykt może skakać.
  Wejdzie z powiadomieniami (etap 4), bo to one muszą być spokojne.

```
rosliny.json                     konfiguracja (ręczna, jak artefakty.json): czujnik → roślina
data/rosliny/RRRR-MM.csv         surowe odczyty doniczek, format ts,device_id,code,value
data/rosliny/stan.json           to, co pokazuje zakładka: szereg godzinowy z 30 dni, dobowe
                                 sumy światła, wykryte podlania, progi, werdykty, kursory
data/rosliny/powiadomienia.json  co i kiedy zostało wysłane (bez adresów telefonów!)
```

**`rosliny.json`** leży obok `fetch.py`, tak jak `artefakty.json`. Ścieżka liczy się
od pliku, żeby testy w katalogu tymczasowym widziały tę samą listę. Szkic wpisu:

```json
{
  "czujnik": "<id z odkryj.yml>",
  "nazwa": "Azalia",
  "gatunek": "azalia",
  "pokoj": "bf5741c97c96fa85b1d7do",
  "kody": {"gleba": "humidity", "swiatlo": "dimmer", "temp": "temp_current",
           "wilg": "env_humidity", "bateria": "battery_state"},
  "sucho": 0
}
```

- **Kody wpisane jawnie**, nie zgadywane przez `classify()`.
- **`pokoj`** to identyfikator czujnika pokojowego, a nie nazwa. Nazwy przychodzą ze
  Smart Life i zmiana nazwy po cichu wyłączyłaby regułę.
- **`sucho`** to odczyt sondy w powietrzu z dnia instalacji.

**Izolacja danych:**
- `merge`, `load_month` i `save_month` dostają parametr katalogu. Dziś mają na sztywno
  `data/` (`fetch.py:318-380`), a ponowne użycie wpisałoby rośliny do plików pokoi.
- Tor pokoi **jawnie pomija** urządzenia z `rosliny.json` i z kategorią `zwjcy`,
  z linią w logu, także przy pustym `TUYA_DEVICE_IDS`. Dziś pusta lista bierze całe
  konto (`fetch.py:1099-1101`), a roślina z `temp_current` przeszłaby filtr
  (`fetch.py:1147`).
- Pliki w podkatalogu nie pasują do wzorca `data/[0-9]*.csv`, więc `purge_before`,
  `write_daily`, `recent_rows` i `keep_known` je pomijają.
- `git add data/` w `zapisz.sh` i service worker (`/data/` najpierw z sieci) obejmują
  podkatalog bez zmian.
- Test izolacji ma obejmować: identyfikator w obu miejscach, pustą listę urządzeń
  i stronę główną z fiksturą roślin — te same liczniki co bez nich.

**Izolacja awarii:**
- Tor roślin działa w tym samym procesie co pokoje, z jednym tokenem. Rusza dopiero
  **po** zapisaniu manifestu pokoi i w całości siedzi w `try/except Exception`.
- Zła składnia ręcznie edytowanego `rosliny.json`, wyjątek w obliczeniach albo odmowa
  Tuya dla doniczki kończy się wpisem `"blad"` w `stan.json` i linią w logu. Kod
  wyjścia `fetch.py` się nie zmienia, więc `zapisz.sh` (`set -e`) dalej zapisuje
  pokoje.
- Pliki roślin zapisujemy przez plik tymczasowy i `os.replace`.
- W drugą stronę: tor roślin nie potrzebuje listy urządzeń, więc jej awaria go nie
  pomija.
- Testy: każdy z trzech przypadków → `main()` zwraca 0, a odczyty pokoi są zapisane.

**Skale i kursory:**
- Skalę czyta nowa funkcja z surowej specyfikacji, tylko dla kodów z `rosliny.json`,
  bez `classify()`. Dzisiejsze `describe_codes` gubi kody, których `classify()` nie
  zna.
- Skalę zapisujemy w `stan.json` i pobieramy ponownie tylko po zmianie kodów. Inaczej
  to +3 zapytania na przebieg.
- Kod z `rosliny.json`, którego brak w specyfikacji, to błąd roślin, a nie cicha dziura.

**Nowy moduł `rosliny.py`.** Czysta biblioteka standardowa, testowany jak `fetch.py`:
- dobowa suma światła w lx·h, całkowana w czasie, z przycinaniem dziur jak
  w `udzial_powyzej()`;
- szereg godzinowy z 30 dni do wykresu, żeby telefon nie ściągał miesięcznych CSV;
- wykrywanie podlania (skok gleby w górę) i poruszenia sondy (gwałtowny spadek);
- uczenie progów (niżej) i werdykty z histerezą.

Pozostałe zasady:
- **Werdykty liczy Python, strona je tylko wyświetla.** Dzięki temu nie powstaje nowa
  para bliźniaczych stałych JS/Python, a karta i powiadomienie mówią to samo.
- **`zwin_rosliny()`** na wzór `collapse_power()` wchodzi od razu. Zostają zmiany
  i jeden wiersz na godzinę na kod. Przy raporcie co 600 s surowe logi to ok. 4 MB
  CSV na miesiąc dla trzech roślin.
- **Watchdog** dostaje krok, który czyta alarmy czujników z `data/rosliny/stan.json`
  i zakłada zgłoszenie z etykietą `rosliny`. Dotyczy to ciszy, baterii `low` i błędu
  toru.
- **Później (v2):** archiwum promieniowania z Open-Meteo, żeby odróżnić pochmurny
  tydzień od złego miejsca. Trafia do `data/rosliny/`, a nie do `fetch_outdoor()`,
  bo stamtąd wpadłoby do `dzienne.csv` i do `index.json`.

### Etap 3: zakładka „Rośliny"

**Stan na 9.10: zrobione** (`rosliny.html`, 30 testów w `tests/frontend/rosliny.spec.js`).
Po przeglądzie (cztery soczewki, każda ze sceptykiem):
- **Werdykt, rady i próg przychodzą z Pythona.** Rada „wyjmij czujnik i zanurz
  doniczkę" dla azalii jest w `GATUNKI`, a `prog_gleba` to próg w procentach czujnika —
  ta sama liczba co odczyt na karcie i dolna krawędź pasma na wykresie.
- **Odświeżanie nie patrzy na samo `updated`:** przy błędzie toru kolektor go nie zmienia,
  więc baner z błędem pokazywał się dopiero po przeładowaniu.
- **Oś gleby od wbicia sondy** (najmniej półtorej doby); odczytów sprzed wbicia nie ma na
  wykresie, doby światła liczą się od dnia wbicia.
- `#roslina=…` wybiera roślinę i obrysowuje jej kartę — tędy wejdzie kliknięcie
  w powiadomienie (etap 4). Nazwy roślin muszą być różne (pilnuje `rosliny.json`).
- Bez internetu i bez zapisanego stanu strona mówi „Brak połączenia", a nie „zajrzyj
  do Actions".
- **Świadomie odłożone:** podbicie wersji service workera (v3 → v4) czyści też zapas
  odczytów, Chart.js i fontów, więc pierwsze uruchomienie bez sieci po aktualizacji nie
  ma danych. Tak było przy każdym podbiciu; rozdzielenie pamięci na szkielet i zapas —
  przy etapie 4, który i tak zmienia `sw.js`.

**Osobna strona `rosliny.html`** w tym samym zakresie aplikacji (`scope: ./`), a nie
sekcja w `index.html`:
- w zainstalowanej aplikacji (Android i iPhone) przejście między stronami z zakresu
  zostaje w jej oknie;
- nie ładuje 177 KB logiki mieszkania;
- ma własne testy i fiksturę, a testy strony głównej zostają bez zmian;
- w `index.html` hash z adresu by zginął, bo `boot()` nadpisuje go `#zakres=…`.

`rosliny.html` jest samodzielny:
- własna funkcja rysująca (wzór: `rysujKomfort()`), ze świadomie skopiowanymi
  wtyczkami;
- Chart.js z tego samego adresu CDN co w `index.html`;
- w `<head>` te same znaczniki manifestu, Apple i viewportu oraz rejestracja `sw.js`;
- pasek zakładek pod `env(safe-area-inset-top)`.

Zasady `state.charts` i listy wtyczek z `draw()` dotyczą tylko `index.html`.

**Zmiany w `index.html` (jedyne dwie):**
1. Pasek zakładek „Mieszkanie | Rośliny".
2. Przy starcie: jeśli w Cache API leży cel z powiadomienia, kasuje go i przechodzi
   na `rosliny.html`. To obejście na iPhone'a, gdzie kliknięcie przy zimnym starcie
   otwiera stronę główną (WebKit 263687).

**Na zakładce:**
- **Karta rośliny:**
  - werdykt jednym zdaniem;
  - gleba na tle pasma rośliny;
  - ostatnie podlanie („3 dni temu");
  - światło wczoraj wobec potrzeby;
  - temperatura, bateria i wiek danych.
- **Wykres gleby z 30 dni** z kreskami podlań. Linia schodkowa, bez wygładzania.
  Światło na osobnym panelu, nie na drugiej osi.
- **„Włącz powiadomienia"** z instrukcją dla iPhone'a.
- Po kliknięciu w powiadomienie zakładka może zastać `stan.json` sprzed minuty
  (Pages wdraża ok. minutę po commicie). Pokazuje wtedy werdykt z powiadomienia
  z dopiskiem „dane w drodze" i pobiera stan ponownie.

**`sw.js`:**
- `rosliny.html` dochodzi do `SZKIELET`, więc `WERSJA` → `smart-home-v4`;
- nowe obsługi `push` i `notificationclick`;
- kliknięcie otwiera tylko adresy z zakresu aplikacji.

**CI:** `strona-bez-budowania` sprawdza oba pliki HTML, a `rosliny.html` dochodzi do
listy wymaganych plików.

### Etap 4: powiadomienia

**Kanał:**

| Kanał | Za | Przeciw | Rola |
|---|---|---|---|
| **Web Push do aplikacji** | przychodzi *z tej* aplikacji; kliknięcie otwiera zakładkę „Rośliny"; za darmo; treść szyfrowana | najwięcej pracy; na iPhonie subskrypcja potrafi po cichu wygasnąć | **główny** |
| ntfy.sh | 10 minut konfiguracji; aplikacje na Androida i iOS | powiadomienie z aplikacji ntfy, nie z naszej; ntfy.sh widzi treść; na iPhonie kliknięcie otwiera Safari | zapas, gdyby Web Push zawiódł |
| automatyzacja Smart Life | zero kodu | jeden próg bez histerezy, bez uczenia; nie wiadomo, czy gleba jest dostępna jako warunek ani czy dostanie je drugi domownik **[do sprawdzenia]** | **tymczasowo**, do etapu 5 |
| zgłoszenie GitHub (mail) | już działa | zwłoka do kilkunastu godzin przez watchdoga | awarie: martwa subskrypcja, cisza czujnika, bateria |

**Jak wysyłać bez dublowania:**
- `fetch.py` zapisuje decyzję w `data/rosliny/powiadomienia.json` z polem
  `przebieg` = `$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT`.
- Po udanym `zapisz.sh` osobny krok w `zbieraj.yml` wysyła **wyłącznie** wpisy z tym
  polem, odczytane z opublikowanego commita (`git show origin/main:…`). Tylko ten krok
  dostaje sekrety powiadomień.
- Wpis jest w opublikowanym commicie albo nie ma go wcale. Dwa przebiegi naraz,
  ponowienie po przegranym wyścigu, ścieżka „nic do zapisania" ani „Re-run" w Actions
  nie mają czego wysłać drugi raz.
- Zasada: **co najwyżej raz**. Nieudanej wysyłki następny przebieg nie ponawia. Reguły
  z ponowieniem nadrobią to same, a nieudana wysyłka zakłada zgłoszenie.

**Awarie wysyłki:**
- 404/410 (subskrypcja wygasła) albo 403 (klucz VAPID nie pasuje): **sam krok wysyłki**
  zakłada albo odświeża zgłoszenie z etykietą `powiadomienia`. `zbieraj.yml` dostaje
  do tego `issues: write`. Watchdog by tego nie zobaczył, bo wynik wysyłki powstaje
  już po commicie.
- 429 i 5xx: dwie ponowne próby w tym samym kroku, potem zgłoszenie.
- Brak sekretów: krok kończy się na zielono z linią „brak subskrypcji". Dzięki temu
  etap 3 da się wdrożyć przed etapem 4.

**Przełącznik `POWIADOMIENIA: na-sucho | wlaczone`** w `zbieraj.yml` trafia do
`fetch.py`, a nie tylko do kroku wysyłki:
- na sucho reguły zapisują `na_sucho` z godziną, a nie „wysłano", więc ponowienia
  i zasada „raz, potem karta" liczą się dopiero od włączenia;
- pierwszy przebieg po włączeniu wysyła jedno zbiorcze powiadomienie o tym, co już
  trwa.

**Sekrety:**
- `VAPID_KLUCZ_PRYWATNY`.
- Subskrypcja każdego telefonu w osobnym sekrecie (`PUSH_ANDROID`, `PUSH_IPHONE`).
  Sekretów GitHuba nie da się odczytać ani zmienić częściowo.
- Klucz publiczny VAPID leży **w jednym miejscu**: w `rosliny.html`. Nadawca wylicza
  go z klucza prywatnego i porównuje ze stroną. Gdy się nie zgadzają, krok kończy się
  na czerwono z komunikatem „klucz w sekrecie nie pasuje do strony". Test w CI
  sprawdza tylko format stałej — to strażnik i tak go podpisujemy.
- Parę kluczy generuje sama strona (WebCrypto), jednym przyciskiem. Prywatny właściciel
  wkleja od razu jako sekret, a publiczny przekazuje do kodu. **Prywatny nigdy nie
  przechodzi przez czat.**
- **Logi Actions są publiczne.** Nadawca nigdy nie wypisuje adresu subskrypcji ani
  treści wyjątków `requests`, bo zawierają URL. Na starcie kroku `::add-mask::` dla
  każdego adresu. Test: przy wyjątku sieciowym z adresem w treści log nie zawiera
  adresu.
- **Subskrypcji nigdy nie trzymać w `data/`**, bo `data/` jest publiczne.

**Nadawca:**
- `pywebpush` w osobnym pliku wymagań kroku wysyłki. Trzy zmierzone pułapki obchodzimy
  jawnie, a każdą pilnuje test:
  - świeży słownik `claims` przy każdym wywołaniu, bo biblioteka zmienia go w miejscu
    i drugi telefon dostałby zły `aud`;
  - `ttl` podany jawnie, bo domyślne 0 Apple odrzuca;
  - `sub` bez ścieżki w adresie.
- Zapas: własna implementacja na samej bibliotece `cryptography` (ok. 100 linii).
  Prototyp przeszedł lokalnie test z biblioteką referencyjną `http_ece`, ale nie był
  puszczany na prawdziwe serwery Google i Apple.
- Nagłówki:
  - `TTL` 12 godz., `Urgency: normal`;
  - `Topic`/`tag` ASCII (np. `podlej-azalia`), więc nowe powiadomienie zastępuje stare.

**Telefony:** kroki w `ROSLINY-INSTRUKCJA.md`.
- **Android:** Chrome, aplikacja już zainstalowana.
- **iPhone:**
  - iOS ≥ 16.4, aplikacja dodana z **Safari** i otwarta z ikony. Na iOS 26
    przełącznik „Otwórz jako aplikację webową" ma być włączony.
  - Safari cofa zgodę, jeśli push nie pokaże powiadomienia, więc obsługa `push`
    pokazuje je **zawsze**.
  - W UE Apple w 2024 r. wycofało się z wyłączenia aplikacji z ekranu początkowego.

**Czy powiadomienia dochodzą:**
1. Adres z `getSubscription()` porównujemy z ostatnio skopiowanym (localStorage).
   Inny albo brak → „włącz ponownie i podmień sekret".
2. Obsługa `push` zapisuje w IndexedDB identyfikator odebranego powiadomienia.
   Zakładka porównuje je z `powiadomienia.json`: wysłane ponad godzinę temu
   i nieodebrane → „Powiadomienia nie dochodzą do tego telefonu".

   Tylko to łapie martwą subskrypcję na iPhonie, którą Apple dalej potwierdza
   kodem 201.

### Reguły powiadomień

**Wersja 1 — trzy reguły, które odpowiadają na „podlej albo przestaw":**

| Reguła | Kiedy | Ponowienie | Treść |
|---|---|---|---|
| **Podlej** | R poniżej progu rośliny przez ≥ 2 godz.; histereza 6 punktów | co 24 godz. (azalia co 12), najwyżej 3 razy; gaśnie po wykrytym podlaniu | azalia poniżej R 0,60: ta sama reguła zmienia treść na instrukcję zanurzenia (najpierw wyjąć czujnik) |
| **Czujnik** | cisza > 12 godz., bateria `low`, sonda wyjęta (nagły spadek gleby) | raz, potem karta | „Fikus: czujnik milczy od…" |
| **Niedzielne podsumowanie** | niedziela, 10:00 | co tydzień, **zawsze** — też jako sygnał, że system żyje | stan trzech roślin, ostatnie podlania, światło tygodnia wobec potrzeby; raz na sezon „przestaw do …" albo „lepszego miejsca nie ma" |

**Zasady ogólne:**
- Cisza 21:00–8:00 czasu polskiego. Po 8:00 reguły liczą się od nowa. Tylko alarm
  czujnika zapisuje zdarzenie nocy i wysyła je rano.
- Jedno zbiorcze powiadomienie na przebieg („Podlej: azalia, skrzydłokwiat"),
  najwyżej 2 zwykłe na dobę.
- Pierwszy tydzień po etapie 4 na sucho.

**Wersja 2 — po zebraniu danych, jeśli będą potrzebne:**
- za mokro za długo („wylej wodę z osłonki / podstawki");
- za ciepło dla azalii: mediana dobowa ≥ 20 °C przez 3 dni → raz, a dziś przez cały
  sezon grzewczy byłoby to stale prawdą, więc w v1 tylko tekst na karcie;
- przy kaloryferze (doniczka − czujnik pokoju ≥ +3 °C przez 3 godz.; czyta pokój, nic
  nie miesza);
- za zimno (skrzydłokwiat ≤ 15 °C, fikus ≤ 13 °C, azalia ≤ 7 °C);
- za dużo słońca: tylko skrzydłokwiat i kwitnąca azalia, odczyt na górnej granicy
  czujnika ≥ 60 min w 2 z 3 dni. **Wiosną**, po zmierzeniu, przy ilu lx czujnik się
  nasyca. Fikus znosi słońce i tej reguły nie dostaje;
- DLI i prognoza „podlej za ok. 2 dni".

**Uczenie progów:**
- To mediany z wykrytych podlań, a nie „cokolwiek uczącego się" ani wykrywanie
  anomalii, które `TODO.md` odrzuca. Działa od trzech zdarzeń.
- **Skala gleby** od „sucho" do „szczytu": R = (odczyt − sucho) ÷ (szczyt − sucho).
  Bez odjęcia „sucho" progi nie przenoszą się między egzemplarzami: sonda, która
  w suchej ziemi pokazuje 50%, a po podlaniu 70%, miałaby przy zupełnie suchej ziemi
  0,71.
  - „Sucho" to odczyt w powietrzu przy instalacji. Później zastępuje go najniższy
    odczyt z 30 dni, jeśli jest niższy.
- **„Szczyt"** to mediana odczytów 2–6 godz. po wykrytym podlaniu, z trzech ostatnich
  podlań.
- **„Punkt podlewania"** to R tuż przed podlaniem, czyli chwila, w której właściciel
  sam uznał, że już czas.
  - Uczy się **tylko** z podlań, przed którymi nie poszło „podlej", czyli w praktyce
    z okresu nauki.
  - Po włączeniu powiadomień próg jest zamrożony i zmienia go tylko strojenie
    (etap 5). Inaczej każde podlanie chwilę po „podlej" spychałoby próg w dół — dla
    azalii w niebezpieczną stronę.
- **Do trzeciego podlania** obowiązuje próg z literatury **[zgadnięte]**, liczony od
  pierwszego wykrytego szczytu. Przed pierwszym szczytem nie ma powiadomień „podlej".

| Roślina | Próg z literatury (R) | Granice osobistego progu |
|---|---|---|
| azalia | 0,75 | 0,60–0,85 |
| skrzydłokwiat | 0,60 (X–II: 0,50) | 0,40–0,70 |
| fikus | 0,45 (X–II: 0,35) | 0,20–0,55 |

Granice nie pozwolą nauce utrwalić nawyku przelewania albo przesuszania.

Przy schodkach po 3 punkty każda histereza musi mieć co najmniej 6 punktów.

---

## Plan wdrożenia

**Etap 0. Limit Tuya** — zrobione 8.10.
- **Właściciel:** sprawdził zużycie na iot.tuya.com.
- **Claude:** pobieranie przyrostowe, budżet zapytań, najpierw API v1, licznik
  zapytań, rozszerzone „Pokaż urządzenia w Tuya", dokumentacja.

**Etap 1. Parowanie i pomiar** — od razu, równolegle z etapem 0, w terminie zwrotu.
- **Właściciel:**
  - sparować i nazwać czujniki;
  - zrobić odczyt w powietrzu i w wodzie;
  - wbić czujniki;
  - przez tydzień patrzeć w Smart Life na baterię.
- **Claude:**
  - porównanie raportów czujników pokojowych przed i po parowaniu (obciążenie
    bramki);
  - po etapie 0 rozszerzone „Pokaż urządzenia w Tuya" i odczyt wyniku.
- **Właściciel, tylko jeśli poproszę:** *DP Instruction* dla produktu czujnika roślin.

**Etap 2. Kolektor roślin** — zrobione 8.10.
- **Claude:** `rosliny.json`, osobny tor, izolacja danych i awarii, `rosliny.py`,
  krok watchdoga (etykieta `rosliny`), testy.
- **Testy:**
  - 7 z 8 testów toru odrzuca wersję bez toru na zachowaniu (rośliny w pokojach,
    brak stanu); ósmy to podpisany strażnik;
  - testy obliczeń dotyczą nowego modułu.
- **Do zrobienia przez właściciela:** napisać godzinę wbicia sond — trafi do pola
  `od` w `rosliny.json`, od niej zaczyna się nauka progów.

**Etap 3. Zakładka „Rośliny"**
- **Claude:** `rosliny.html`, pasek zakładek, karty, wykres, `sw.js`.
- Tryb nauki, bez powiadomień.

**Etap 4. Powiadomienia**
- **Claude:** nadawca, krok w `zbieraj.yml`, przycisk, obsługa w `sw.js`, przebieg
  próbny.
- **Właściciel:** klucz VAPID i subskrypcje do sekretów.
- Potem tydzień na sucho.

**Etap 5. Strojenie** (razem)
- Po 2–3 cyklach podlewania przyłożyć progi do danych.
- Wyłączyć automatyzację Smart Life.

---

## Decyzje właściciela (8.10)

1. **Powiadomienia:** Android i iPhone, w naszej aplikacji (Web Push).
2. **Skrzydłokwiat:** zwykła doniczka z otworami w dnie, na podstawce z nóżkami. Właściciel
   podlewa z góry, więc podlanie będzie widać jako skok.
3. **Wdrożenia:** Claude sam scala na `main`, zbiorczo, po zielonych testach.
4. **Doniczki:** nic nie kupować przed wiosną. Wiosną azalia do kwaśnej ziemi; sprawdzić,
   czy doniczka fikusa ma otwór w dnie.

## Niewiadome, które rozstrzygnie pomiar

- Kody, jednostki, skale i kategoria w chmurze. Czy światło i wilgotność powietrza
  przychodzą (*Standard* czy *DP Instruction*).
- *(Rozstrzygnięte 8.10.)* Ile wpisów na godzinę robi jeden czujnik: w spokoju 8–10,
  gleba 1–3 razy; ok. 120 tylko w godzinie parowania i zmian ustawień. Bateria —
  do obserwacji przez kilka tygodni.
- *(Rozstrzygnięte 8.10.)* Kolejność wpisów w logach Tuya: najpewniej od najnowszego
  (17 zapytań na pokój w pierwszym przebiegu, patrz KONTEKST.md). Algorytm i tak jej
  nie zakłada.
- *(Rozstrzygnięte 9.10.)* Czy czujnik roślin obciąża bramkę tak, że gubi raporty pokoi:
  nie, pokoje raportują jak przed parowaniem.
- W którą stronę patrzy czujnik światła i czy nasyca się przy 10 000 lx.
- Ile pokazuje gleba w każdej z trzech doniczek i zaraz po podlaniu. *(W powietrzu:
  10 / 11 / 9, noc 8/9.10.)*
- Czy nowe urządzenia same pojawią się w projekcie Tuya, czy trzeba ponownie połączyć
  konto.
- Czy Smart Life przyjmuje glebę jako warunek automatyzacji i czy powiadomienie
  dostaje też drugi domownik.
- *(Rozstrzygnięte 8.10.)* Limit: pakiet 0,20 USD, zapytania zagraniczne po 3,71 USD
  za milion, liczy się każde. Workflowów Claude uruchamiać nie może (403), czytać
  przebiegi — tak.

---

## Źródła

**Czujnik:**
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
- logi tylko dla „oficjalnych" punktów danych, tryb *DP Instruction*:
  - https://github.com/jasonacox/tinytuya (`Cloud.getdevicelog`)
  - https://github.com/jasonacox/tinytuya/discussions/284

**Tuya:**
- limit triala — panel iot.tuya.com właściciela, 8.10.2026 (IoT Core → My
  Subscriptions). Wyszukiwarka podawała „26 000 zapytań" — dla tego konta nieprawda
- przedłużanie triala — https://github.com/tuya/tuya-home-assistant/blob/main/docs/faq.md

**Rośliny** (wszystkie przez wyciągi wyszukiwarki, strony zablokowane):
- RHS — https://www.rhs.org.uk/plants/164300/ficus-microcarpa-moclame/details
- UF/IFAS:
  - https://edis.ifas.ufl.edu/publication/EP136
  - https://edis.ifas.ufl.edu/publication/EP161
  - https://mrec.ifas.ufl.edu/foliage/folnotes/spathiph.htm
- Missouri Botanical Garden (azalia) —
  https://www.missouribotanicalgarden.org/gardens-gardening/your-garden/help-for-the-home-gardener/advice-tips-resources/gardening-help-faqs/question/524/why-is-my-indoor-azalea-dropping-buds-and-leaves
- Clemson — https://hgic.clemson.edu/factsheet/peace-lily/
- SDSU — https://extension.sdstate.edu/care-peace-lilies
- Epic Gardening (azalia) — https://www.epicgardening.com/indoor-azalea-care/
- DLI azalii — https://www.researchportal.be/nl/node/8033098
- światło zimą:
  - Sarapata, UŚ — https://rebus.us.edu.pl/bitstream/20.500.12128/13656/1/Sarapata_Evaluation_of_the_solar.pdf
  - https://houseplantjournal.com/?p=213
- lx → PPFD — https://research.csiro.au/anaccmethods/culture-handling/light-units-and-measurement
- Murator (azalia, skrzydłokwiat, fikus) — muratordom.pl
- twardość wody — PSSE Katowice, ocena za 2025 r. (gov.pl; załącznik nieprzypięty)

**Powiadomienia:**
- Apple — https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers
- WebKit:
  - https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
  - https://webkit.org/blog/16535/meet-declarative-web-push/
- znikające subskrypcje i zimny start na iOS:
  - https://bugs.webkit.org/show_bug.cgi?id=273063
  - https://bugs.webkit.org/show_bug.cgi?id=263687
- limity Chrome — https://developer.chrome.com/blog/web-push-rate-limits
- ntfy — https://docs.ntfy.sh/publish/
