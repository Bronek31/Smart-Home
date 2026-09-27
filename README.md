# Smart Home

Historia temperatury i wilgotności z czterech czujników Zigbee (Tuya / Smart Life),
zbierana za darmo przez GitHub Actions i pokazywana na stronie GitHub Pages.

Smart Life nie przechowuje historii — ten projekt to nadrabia: raz na godzinę
pobiera logi z chmury Tuya, dopisuje je do plików CSV w repozytorium i rysuje z nich
wykresy. Żadnego serwera, bazy danych ani Raspberry Pi.

**Podgląd:** https://bronek31.github.io/Smart-Home/

---

## Jak to działa

```
czujniki Zigbee → bramka → chmura Tuya → fetch.py (GitHub Actions, co godzinę)
                                            ↓
                          data/*.csv  +  data/dzienne.csv  +  data/index.json
                                            ↓
                                    index.html (GitHub Pages)
```

Tuya udostępnia **7 dni logów wstecz**, więc każdy przebieg pobiera całe to okno
i dokłada tylko to, czego jeszcze nie ma. Pominięty albo nieudany przebieg
niczego nie kosztuje — następny nadrabia zaległości. Dziura w danych powstaje
dopiero wtedy, gdy kolektor milczy dłużej niż tydzień. Właśnie po to jest watchdog.

Czujniki raportują **przy zmianie temperatury o 0,5 °C** albo **raz na godzinę**,
cokolwiek wypadnie pierwsze. Odstępy 60-minutowe to norma, nie awaria.

Poza czujnikami klimatu kolektor zbiera też **włączniki urządzeń** — z klimatyzatora
w salonie bierze wyłącznie to, kiedy chodził. Strona tego dziś nie pokazuje: pasma
pracy służyły wykrywaniu wietrzenia i odeszły razem z nim (27.09.2026). Wiersze
zostają w CSV, gdyby urządzenie wróciło do łask.

---

## Pliki

| Plik | Do czego |
|---|---|
| `fetch.py` | kolektor: pobiera logi z Tuya, pogodę i smog z Open-Meteo, przelicza agregaty |
| `index.html` | cała strona — wykresy, rzut mieszkania, diagnostyka. Bez budowania |
| `zapisz.sh` | pobiera odczyty i zapisuje je na gałąź, przeżywając wyścig dwóch przebiegów |
| `TODO.md` | pomysły na później i te świadomie odrzucone, wraz z powodami |
| `KONTEKST.md` | notatka przekazania: dlaczego jest tak, jak jest, i na co uważać przy dalszej pracy |
| `tests/` | testy kolektora i strony; nie trafiają na Pages, bo Pages serwuje tylko katalog główny |
| `.githooks/pre-push` | nie przepuszcza pusha, dopóki testy nie przejdą |
| `.github/workflows/zbieraj.yml` | zbieranie; zapasowy harmonogram co godzinę o :19, właściwym zegarem jest zewnętrzny cron co godzinę (patrz „Kolektor co godzinę") |
| `.github/workflows/watchdog.yml` | co 6 godzin sprawdza, czy kolektor żyje i czy czujniki nie wołają o rękę |
| `.github/workflows/odkryj.yml` | na żądanie wypisuje urządzenia w Tuya i ich pola |
| `.github/workflows/testy.yml` | testy przy każdej zmianie kodu i raz na dobę na żywych danych |
| `manifest.json`, `sw.js`, `ikona*` | instalacja na ekranie głównym telefonu i tryb offline |
| `.nojekyll` | pusty plik, który mówi Pages: serwuj repozytorium jak jest, bez Jekylla |
| `data/RRRR-MM.csv` | surowe odczyty: `ts,device_id,code,value` |
| `data/dzienne.csv` | dobowe min/średnia/max — z tego rysuje się widok „całość" |
| `data/pogoda.json` | migawka: teraz, prognoza na 3 dni i godzinowa na dobę, jakość powietrza. Nadpisywana co przebieg |
| `data/index.json` | lista urządzeń, miesięcy, czas ostatniej zbiórki i diagnostyka dla watchdoga |

---

## Uruchomienie od zera

1. **Projekt w chmurze Tuya.** Na [iot.tuya.com](https://iot.tuya.com) załóż projekt
   (Smart Home, data center **Central Europe**), podepnij konto Smart Life przez
   kod QR i sprawdź, czy w zakładce *Devices* widać czujniki. W *Service API*
   musi być **IoT Core** — to z niego biorą się logi.
2. **Sekrety repozytorium.** *Settings → Secrets and variables → Actions*:
   `TUYA_CLIENT_ID` i `TUYA_CLIENT_SECRET` z zakładki *Overview → Authorization Key*.
3. **Identyfikatory czujników.** `python fetch.py --discover` wypisze listę.
   Wklej je do `TUYA_DEVICE_IDS` w `zbieraj.yml`.
4. **GitHub Pages.** *Settings → Pages → Source: Deploy from a branch → main / (root)*.
5. **Pierwszy przebieg.** *Actions → Zbieranie odczytów → Run workflow*.
   Po minucie w `data/` pojawią się pliki, a strona zacznie coś pokazywać.

Repozytorium musi być **publiczne** — przy prywatnym Pages wymaga płatnego planu.

---

## Ustawienia

Wszystkie w sekcji `env` w `.github/workflows/zbieraj.yml`:

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `TUYA_REGION` | `eu` | data center projektu Tuya |
| `TUYA_DEVICE_IDS` | — | identyfikatory czujników po przecinku |
| `TUYA_SINCE` | puste | granica: starsze odczyty są kasowane i nie wracają |
| `OUTDOOR_LAT` / `OUTDOOR_LON` | Katowice | pogoda i smog z Open-Meteo, a także wschód i zachód na łuku doby. Puste = wyłączone |
| `TZ_LOCAL` | `Europe/Warsaw` | według tej strefy tną się doby w agregatach i przelicza się prognozę godzinową. Musi być nazwą strefy, nie przesunięciem: prognoza sięga 36 godz. naprzód, więc dwa razy w roku przechodzi przez zmianę czasu |

Proporcje pokoi na rzucie mieszkania siedzą w stałej `PLAN` w `index.html` —
to `x, y, w, h` w siatce 400×500. Progi alarmów (`HEARTBEAT`, `STALE_WARN`),
progu pleśni (`FRSI`, `WILG_POWIERZCHNI`) i filtra chwilowych skoków (`SPIKE`) są tuż obok.
Próg pleśni też ma bliźniaka w `fetch.py` i też pilnuje go test zgodności.
`SPIKE` ma bliźniaka po stronie kolektora (`SPIKE_JUMP`, `SPIKE_RISE`, `SPIKE_MAX`
w `fetch.py`) i obie kopie muszą się zgadzać — inaczej agregaty dobowe pokazują co
innego niż wykres. Pilnuje tego osobny test.

Tam też stoi **orientacja mieszkania**: pole `okno` mówi, na którą stronę świata
patrzy pokój (`pld` albo `pln`, opisane w `STRONY`). Sypialnia wychodzi na południe,
salon i kuchnia na północ — na rzucie góra to więc południe. To nie jest ozdoba:
z tego bierze się rada, żeby w upalne, słoneczne godziny zaczynać wietrzenie od
strony północnej, bo okno od południa wpuszcza wtedy ciepło, którego prognoza
temperatury nie pokazuje. Obok są `dop` i `bier` — nazwy pokoi w dopełniaczu
i bierniku, bo podpowiedzi wklejają je wprost w zdanie.

> **Odtwarzanie historii i łuk doby są od 27.09.2026 schowane** (`ODTWARZANIE` w `index.html`).
> Kod zostaje i chodzi pod testami, które włączają go flagą `window.odtwarzanieWlaczone`;
> przywrócenie to zmiana jednej linii. Rzut pokazuje stan bieżący, a jego skala barw
> liczy się dalej z tygodniowego okna. Opis poniżej dotyczy wersji włączonej.

Nad suwakiem odtwarzania biegnie **łuk doby** — rzeczywista droga słońca nad
horyzontem tego dnia, na który patrzy klatka. Znacznik siedzi na krzywej: nad kreską
słońce, pod kreską księżyc, a przy końcach podpisane godziny wschodu i zachodu. Sam
stempel z datą wymaga przeliczenia w głowie, a zmierzch w sierpniu i w grudniu wypada
o zupełnie innej porze — łuk odpowiada na „która to była pora dnia" jednym spojrzeniem.
Krzywa jest liczona, nie brana z prognozy: dobowa prognoza Open-Meteo sięga trzech dni
w przód, a odtwarzanie chodzi tydzień wstecz, więc i tak trzeba by ją uzupełniać.
Wzór NOAA daje dokładność rzędu minuty — sprawdzone testem przez tożsamość
„wysokość w południe w przesilenie = 90° − szerokość ± 23,44°". Potrzebne są tylko
współrzędne; kolektor zapisuje je w `data/pogoda.json` jako `gdzie`, a bez nich łuk
po prostu się nie pokazuje. Rysowana kreska to nie zero, lecz próg wschodu (−0,833°,
czyli moment, gdy zza horyzontu wychodzi górna krawędź tarczy) — dzięki temu „słońce
nad kreską" i „jest dzień" znaczą dokładnie to samo.

Pod rzutem siedzi **odtwarzanie historii**: suwak przewija mieszkanie w czasie, a
przycisk puszcza jeden przebieg. Po dojściu do końca rzut wraca do stanu bieżącego
i przycisk sam przełącza się na trójkąt — kolejny przebieg wymaga kolejnego kliknięcia.
Pauza w trakcie zatrzymuje tam, gdzie akurat jest. Odtwarzanie zatrzymuje
się też samo, gdy karta przestaje być widoczna. Pokazuje to, czego cztery nałożone linie nie
pokazują — którędy ciepło wędruje przez mieszkanie. Pasek pod suwakiem to średnia
mieszkania przez całe okno ze znacznikiem bieżącej klatki; wykresy są półtora tysiąca
pikseli wyżej, więc bez niego nie wiadomo, czy ogląda się szczyt dnia, czy noc.
Klatki idą stałym krokiem dobranym do okna (`KLATKI_CEL`, `KROKI_MIN`, `KLATKA_MS`),
a wartości między odczytami są interpolowane, bo czujniki raportują raz na godzinę
i bez tego byłby to pokaz slajdów.

Pod spodem są dwa przełączniki. Pierwszy wybiera **okno**: ostatni tydzień albo ostatnia doba —
niezależnie od zakresu wykresów. Drugi wybiera, **co znaczy kolor**:

| Tryb | Kolor mówi | Kiedy przydatny |
|---|---|---|
| `temperatura` | ile stopni, wspólna skala dla całego mieszkania | gdy chcesz porównać pokoje między sobą |
| `odchyłka pokoju` | o ile pokój odbiega od własnej średniej w oknie | gdy chcesz zobaczyć sam ruch |

Drugi tryb istnieje, bo przez dobę różnice między pokojami są ponad dwa razy większe
niż ruch któregokolwiek z nich — na wspólnej skali widać wtedy tylko stały ranking
„łazienka najcieplejsza", a on się nie zmienia. Po odjęciu średniej pokoju zostaje
sama dynamika i widać, że sypialnia od południa nagrzewa się 2 godziny po dworze,
a pokoje od północy dopiero po 4–5. Liczba w pokoju pozostaje bezwzględna, więc
w tym trybie kolor i cyfra mówią o dwóch różnych rzeczach — stąd osobny przycisk,
a nie zamiennik.

**Skala kolorów rzutu dobiera się do danych w oknie**, a nie stoi na stałych 19–28 °C:
spokojna doba mieści się w jednym stopniu i na stałej skali wszystkie pokoje wyglądały
identycznie. Końce skali są podpisane w legendzie pod rzutem, więc widać, co znaczy
dany odcień. `SKALA_ROZPIETOSC` pilnuje, żeby przy bardzo równej dobie nie rozdmuchać
szumu czujnika, a `RAMPA` to sama paleta.

**Rytm doby** to mapa cieplna godzina × doba dla wybranego pokoju: wiersz to doba,
kolumna godzina. Wykres liniowy przy kilku tygodniach zamienia się w kłębek, a mapa
rośnie o jeden wiersz dziennie i zostaje czytelna. Doba i godzina liczone po zegarze
lokalnym, bo rytm mieszkania chodzi za mieszkańcami, nie za południkiem zerowym.

Mapa obejmuje ostatnie 30 dób, niezależnie od zakresu wykresów.
Skala jest domyślnie **wspólna dla wszystkich pokoi**, żeby przełączanie zakładek dało
się czytać jako porównanie — przy osobnych skalach ten sam kolor znaczyłby w każdej
zakładce co innego. Kosztuje to zaskakująco mało: pokoje o szerokim zakresie tracą na
kontraście tyle co nic, płaci tylko ten najbardziej stabilny, i to jest uczciwe.
`skala pokoju` rozciąga paletę na zakres jednego pomieszczenia, gdy chcesz obejrzeć
sam jego rytm.

## Skale: gdzie dwór, a gdzie pokoje

Dwór potrafi w tygodniu przejść 14 → 34 °C, a pokoje stoją wtedy w paśmie 22,8 → 26,7.
Na wspólnej osi cały ruch w mieszkaniu spłaszcza się do kilku pikseli i cztery linie
zlewają się w jedną. Rozwiązania są trzy i każdy z wykresów dostał inne — bo każdy
odpowiada na inne pytanie.

**Temperatura: dwa panele ze wspólną osią czasu.** Górny to same pokoje na własnej
skali, dolny to pasek „mieszkanie kontra dwór”. Podwójna oś, którą ten wykres miał do
21.08, jest w wizualizacji danych techniką odradzaną i nie jest to kwestia gustu:
**punkt przecięcia dwóch linii na dwóch skalach nie znaczy nic**, bo zależy wyłącznie
od tego, jak dobrano zakresy — można nimi „pokazać” dowolną korelację. Grafana ostrzega
przed drugą osią w dokumentacji, Datadog ją odradza, Home Assistant w ogóle jej nie
oferuje. Rozwiązaniem, po które sięgają narzędzia monitoringu, są osobne panele nad sobą.

W pasku obie krzywe — dwór i **średnia mieszkania** — siedzą na jednej skali, więc
odległość między nimi to dosłownie różnica w stopniach. Pole między nimi jest zabarwione:
**błękit, gdy na dworze chłodniej** (jest po co otwierać), **czerwień, gdy cieplej**
(zamykaj). Moment przecięcia to chwila, w której warto ruszyć okna. Podziałkę czasu
niesie wyłącznie dolny panel: stykają się krawędziami i czytają jak jedna całość.
Bez czujnika zewnętrznego pasek się chowa, a podpisy godzin wracają na górę.

**Wilgotność względna i bezwzględna: jedna wspólna oś.** Bez drugiej osi i bez osobnego
panelu — i to jest wynik pomiaru, nie oszczędności. Decyduje jedna liczba: **ile wysokości
zajęłyby pokoje, gdyby dzieliły oś z dworem**.

| wykres | zakres dworu | zakres pokoi | pokoje na wspólnej osi |
|---|---|---|---|
| temperatura | 14,0–33,8 °C | 22,8–26,7 °C | **20%** — nie do przyjęcia, stąd dwa panele |
| wilgotność względna | 18–87% | 46–80% | **49%** — czytelne |
| wilgotność bezwzględna | 6,1–16,2 g/m³ | 10,6–16,9 g/m³ | **58%** — czytelne |

Wilgotność względna nie dostaje też paska zestawienia, i to z drugiego powodu:
**porównywanie jej z dworem jest fizycznie mylące**, bo skacze od samej temperatury.
Pasek obiecywałby odpowiedź na pytanie, na które ten wykres nie odpowiada — od tego jest
wilgotność bezwzględna.

Przy wilgotności bezwzględnej wspólna oś to nie tylko dopuszczalny kompromis, ale sens
wykresu: przy wietrzeniu linia mieszkania zbliża się do linii dworu, a na dwóch skalach
ta odległość przestałaby cokolwiek znaczyć.

Po tych zmianach **na całej stronie nie ma ani jednej podwójnej osi**, a maszyneria, która
ją rysowała, została z `draw()` usunięta, nie wyłączona. Wszędzie, gdzie dwór dzieli wykres
z pokojami, jest kreskowaną linią; własnego pasma nie ma już gdzie rysować.

Linie pokoi są **wygładzone średnią z trzech kolejnych odczytów**. Czujniki raportują
z krokiem 0,1 °C i 1%, a odkąd pokoje mają wykres dla siebie, skala pokazuje niecałe cztery stopnie na
całą wysokość — jedna dziesiąta urosła do kilkudziesięciu pikseli i krzywe zamieniły się
w schodki, które są rozdzielczością sprzętu, a nie zjawiskiem w mieszkaniu. Zmierzone na
tygodniu prawdziwych danych: średnia odsuwa linię najwyżej o **0,067 °C**, czyli mniej
niż krok, o który czujnik i tak zaokrągla — wygładzona linia jest bliżej prawdy niż
surowe schodki, bo kwantyzacja się uśrednia.

Uśredniany jest **wyłącznie punkt, który ma sąsiadów po obu stronach**. Pierwszy, ostatni
i każdy przy dłuższej przerwie w raportach zostaje surowy, bo średnia z dwóch odczytów
zamiast trzech ma inne ograniczenie: przesuwa punkt o połowę kroku do sąsiada, czyli przy
skoku 0,2 °C odsuwa linię o 0,1 — półtora raza dalej niż wnętrze serii. Na prawdziwych
danych brzegiem jest ostatni odczyt, czyli „teraz", i akurat przy wietrzeniu potrafi
lecieć 0,5 °C w kwadrans.

### Przybliżanie osi czasu

Dwa panele załatwiły dwór kontra pokoje, ale nie załatwiły telefonu. Przy „7 dniach"
na szybie 390 px pole wykresu ma 356 pikseli szerokości, a **96% odczytów mieści się
w paśmie 2,3 °C, gdy oś musi objąć 4,9 °C** — bo dwa nurki wietrzenia z 19 i 20.08
sięgają 22,5 °C. Każdy z tych nurków ma na ekranie dwa piksele szerokości i we dwa
zabierają dolną połowę panelu. Codzienna różnica między pokojami, czyli 0,3–0,5 °C,
dostaje przez to jakieś dwadzieścia pikseli.

Statyczna skala tego nie naprawia — sprawdzone na tych samych danych i **odrzucone**:

| pomysł | zysk | dlaczego odpadł |
|---|---|---|
| wyższy panel (238 → 300 px) | 1,3× | puste pole rośnie razem z panelem |
| oś ucięta do 24,0° | 1,6× | nurki wychodziły poza wykres |
| oś łamana (ogon ściśnięty przy krawędzi) | 1,4× | dużo maszynerii jak na tyle |

Weszło **przybliżanie gestem**, bo Chart.js liczy oś pionową wyłącznie z punktów
mieszczących się w oknie czasu — więc zwężenie okna samo z siebie rozciąga skalę pionową,
i to o rząd wielkości mocniej niż cokolwiek statycznego. Zmierzone na tych samych siedmiu
dniach:

| okno | rozpiętość pokoi | gęstość skali | zysk |
|---|---|---|---|
| 7 dni — widok domyślny | 4,4 °C | 63 px/°C | 1,0× |
| doba z wietrzeniem (20.08) | 4,2 °C | 66 px/°C | 1,0× |
| doba 21.08 | 2,0 °C | 143 px/°C | **2,3×** |
| doba 17.08 | 1,1 °C | 258 px/°C | **4,1×** |
| 6 godzin 17.08 | 1,0 °C | 290 px/°C | **4,6×** |

Doba z wietrzeniem nie zyskuje nic i tak ma być: tam nurek jest w oknie i to on
wyznacza skalę — a jest tym, na co się patrzy. Domyślny widok zostaje **dokładnie taki,
jaki był**; przybliżenie jest czymś, po co się sięga, a nie czymś, co się dzieje samo.

Podział gestów tak dobrany, żeby strona nie straciła niczego, co już umiała:

| gest | co robi |
|---|---|
| dwa palce | przybliża i oddala oś czasu |
| jeden palec w poziomie | przesuwa okno w lewo i w prawo |
| jeden palec w pionie | przewija stronę, tak jak dotąd |
| dotknięcie | pokazuje odczyt w dymku |
| kółko / przeciąganie / dwuklik | to samo myszą |

Pion zostaje przeglądarce dzięki `touch-action: pan-y` na polu wykresu — poziom i
wielodotyk dostaje wykres, pion obsługuje przeglądarka i przewijanie strony działa
jak przedtem. Dymek przeniósł się z „każdego ruchu w poziomie" na „dotknięcie", bo
poziom jest teraz zajęty przez przesuwanie; wtyczka `dotyk` ukrywa przed Chart.js
wszystkie zdarzenia dotyku, a przy dotknięciu podaje mu jedno sztuczne `mousemove`.

Przybliżenie jest **wspólne dla wszystkich czterech płócien** i trzyma się w czasie
bezwzględnym, żeby panele stały równo co do piksela. Nie schodzi poniżej pół godziny
ani nie wyjeżdża poza dane, a zmiana zakresu u góry je kasuje — inne dane to inne okno.
Przycisk **⤢ cały zakres** pokazuje się dopiero wtedy, gdy jest z czego wracać.

Przy okazji doszło domknięcie osi pionowej o **wartości interpolowane na krawędziach
okna**. Chart.js liczy zakres z samych punktów w oknie, więc linia wchodząca w kadr
z boku potrafiła uciec poza pole — jej odcinek zaczyna się poza oknem i na krawędzi ma
wartość, której w rachunku nie było. Dotyczy to również kotwicy sprzed początku zakresu,
więc działa i bez przybliżania.

### Krawędzie wykresu

Czujniki raportują każdy w innej minucie godziny i te minuty dryfują, więc bez zabiegu
każda linia zaczyna się i kończy tam, gdzie akurat wypadł jej raport. Zmierzone 20.08
w widoku „dziś": starty rozjechane o **46 minut**, końce o **53** — przy oknie 8,5 godziny
to po dziesiątej części szerokości wykresu z każdej strony, a linia urwana w powietrzu
wygląda jak martwy czujnik, nie jak czujnik, który jeszcze się nie odezwał.

Lewą krawędź wyrównuje **kotwica**: do rysowania dokładany jest jeden prawdziwy odczyt
sprzed granicy zakresu, a odcinek do niego przycina oś ustawiona na najwcześniejszy
odczyt z zakresu. Nic nie jest dorysowywane — linia po prostu wchodzi w kadr z lewej.
Do tabeli zakresów kotwica nie wchodzi; pilnuje tego test.

Prawej krawędzi tak wyrównać się nie da, bo przyszłych odczytów nie ma. Tam ostatni
odczyt każdego pokoju dostaje **kropkę** — koniec linii jest wtedy znakiem, a nie
urwaniem, i zgadza się z tym, co kafel mówi słowami („ostatni raport 52 min temu”).

Rusza wyłącznie rysowana linia. Kafle, tabela zakresów i rzut mieszkania
liczą z surowych odczytów, a dymek na wykresie pokazuje ten odczyt, który
naprawdę przyszedł z czujnika. Dwór zostaje surowy: z Open-Meteo przychodzi już gładki,
a uśrednienie jego stromej krzywej odsuwało linię o 1,17 °C. Agregaty dobowe w widoku
„całość" też nie są wygładzane — to już są średnie.

Na własnej osi **dwór nie jest linią, tylko pasmem w tle**, w stalowym kolorze spoza
palety pokoi. Brał wcześniej piąty odcień z tej palety, bo jest piątym urządzeniem na
liście — i przez to wyglądał na piąty pokój, choć jest tłem, na którym tamte cztery się
dzieją. Jako równorzędna kreska zapraszał też do odczytu „na dworze było tyle co
w sypialni", a to nieprawda: obie linie leżą na innych miarkach. Z pasma widać dalej to,
o co chodzi — że fala upału na dworze podnosi pokoje kilka godzin później — a nie widać
porównania, którego robić nie wolno. Ten sam kolor niesie kafel i legenda, żeby wszędzie
mówiły to samo: dwór to odniesienie, nie pomieszczenie.

**Wilgotność bezwzględna zostaje na jednej osi i tak ma być.** Tam cały sens wykresu
polega na tym, że przy wietrzeniu linia mieszkania zbliża się do linii dworu — na dwóch
skalach ta odległość przestałaby cokolwiek znaczyć. Testy pilnują obu tych decyzji.

### Dziury w rytmie doby

Raporty przychodzą co ok. 59 minut i ta minuta dryfuje, więc co jakiś czas jedna godzina
zegarowa zostaje bez odczytu, a następna dostaje dwa. W mapie robiła się wtedy czarna
kratka w środku doby — a mapa istnieje po to, żeby pokazywać **powtarzalny rytm**, więc
dziura rozbija dokładnie to, po co się ją ogląda.

Taka kratka jest **odtwarzana liniowo z sąsiednich odczytów**: temperatura jest wielkością
ciągłą, a pomiary mamy po obu stronach. To jedyny odtwarzany kawałek danych w projekcie,
więc dostaje kreskowaną ramkę, dopisek w dymku i własną pozycję w legendzie — ma nie
udawać pomiaru. Gdy przerwa przekracza `MISS_GAP` (2,5 godz.), czyli czujnik naprawdę
milczał, pole **zostaje czarne**: nie ma z czego odtwarzać i nie wolno tego zamalowywać.
Pilnuje tego osobny test.

## Który fragment jaki okres pokazuje

Przełącznik u góry nazywa się **Zakres wykresów** i tyle obejmuje — same wykresy.
Każdy fragment strony, który patrzy na inny okres, mówi o tym wprost albo ma własny
przełącznik; inaczej wybór „dziś" po cichu obcinałby połowę strony do kilku godzin.

| Fragment | Okres | Skąd |
|---|---|---|
| Wykresy | **Zakres wykresów** u góry | to jego zadanie |
| Tabela zakresów | **Zakres tabeli** nad tabelą | własny, bo skrajne wartości ogląda się dla innego okresu niż przebieg |
| Kafle pokoi | teraz, zmiana z 24 h, trend z 4 h | stały |
| Rzut (skala barw) | ostatni tydzień | stały, dopóki odtwarzanie jest schowane |
| Rytm doby | ostatnie 30 dób | stały, liczba dób w nagłówku |
| Łączność z bramką | 24 h | stały, napisany w podpisie tabeli |
| Ostatnie zdarzenia | 24 h | stały |
| Pogoda i wietrzenie | teraz plus doba prognozy | stały |

## Co strona radzi i skąd to wie

Poza wykresami dashboard odpowiada na dwa pytania.

**Czy wietrzyć teraz** — z dwóch różnic naraz: temperatury i wilgotności bezwzględnej
między mieszkaniem a dworem. Otwarte okno robi obie rzeczy, a która z nich się liczy,
zależy od pory roku: zimą i w suchy dzień pracuje wilgotność, w letni wieczór wyłącznie
temperatura. Werdykt nazywa ten skutek, który naprawdę wystąpi — „schłodzi", „osuszy",
„osuszy, ale dogrzeje" — zamiast wypowiadać się o jednej osi i milczeć o drugiej.

Chłód z dworu jest zaletą tylko w ciepłym mieszkaniu (`CIEPLO_W_DOMU`, 24 °C). Poniżej —
jesienią i w sezonie grzewczym — to samo okno wychładza ściany, za które się płaci,
więc werdykt brzmi „Przewietrz krótko i szeroko": okno na oścież przez 5–10 minut
wymienia powietrze, zanim ściany zdążą wystygnąć, a uchylone na godziny wychładza
i prawie nie osusza. Z tego samego powodu rada „sypialnię od południa otwieraj krótko,
bo słońce" pojawia się tylko w ciepłym mieszkaniu — w chłodnym to słońce jest darmowym
ciepłem.

**O której dziś będzie najsuchsze powietrze** — z prognozy godzinowej Open-Meteo,
różnica wilgotności policzona na dobę naprzód. Godziny cieplejsze od mieszkania
odpadają: to okno ma osuszyć, nie dogrzać. Ramka mówi wprost, że chodzi o suchość,
bo inaczej przeczyłaby kaflowi obok — w letni wieczór najlepiej otworzyć okno *teraz*,
dla chłodu, a najsuchsze powietrze przychodzi nad ranem.

Progi (`WIETRZ_ZYSK`, `WIETRZ_CIEPLO`, `SLONCE_MOCNE`) siedzą w `index.html` obok
tych funkcji.

### Strefa komfortu i noce w sypialni

**Strefa komfortu** to wykres temperatura × wilgotność: punkt to godzina w jednym pokoju
(w widoku „całość" — doba), a zielone pole to 20–24 °C i 40–60% (`STREFA`). Pod wykresem
każdy pokój ma jedną liczbę — jaką część czasu spędził w polu — i dopisek, w którą stronę
uciekał najczęściej. Zakres ten sam co wykresów. Punkt to średnia godzinowa, bo przy
zmianie czujnik raportuje co dwie minuty i surowe odczyty przeważyłyby impulsy.

**Noce w sypialni** — ostatnie 14 nocy, 23:00–7:00: średnia (kropka), rozpiętość od
najchłodniejszej do najcieplejszej godziny (pasek) i średnia wilgotność, na tle
**strefy optymalnej do snu**, 16–19 °C (`SEN`) — tyle zalecają NHS, brytyjska Sleep
Charity (16–18) i amerykańska Sleep Foundation (15,6–19,4). To zalecenie dla snu,
nie komfort dzienny w mieszkaniu. Noc z mniej niż sześcioma godzinami
odczytów jest pomijana, noc, która jeszcze trwa — też. Obie sekcje liczą liczby bez
Chart.js, więc przy awarii CDN znika tylko sam wykres komfortu.

### Rzut w trybie „wilgotność a pleśń" i kalendarz historii

Pod rzutem jest przełącznik **temperatura / wilgotność a pleśń**. W drugim trybie duża
liczba w pokoju to wilgotność, pod nią próg pleśni przy obecnej pogodzie, a kolor
mówi o zapasie do progu: zielony od 15 punktów w dół (`PLESN_ZAPAS`), czerwony na
progu i ponad nim. Sama wilgotność tego nie mówi, bo próg zależy od temperatury
pokoju i dworu.

**Cała historia** to kalendarz jak na GitHubie: kratka na dobę, kolumna na tydzień
od poniedziałku, z agregatów dobowych — więc sięga do początku zbierania. Domyślnie
**wszystkie** pokoje i dwór jako bloki jeden pod drugim, w tych samych kolumnach
tygodni, więc ta sama doba stoi w jednej pionowej linii; pokoje dzielą skalę, dwór ma
własną. Do wyboru też mieszkanie (średnia pokoi) i każde miejsce osobno, temperatura
albo wilgotność; przy wilgotności skala jest odwrócona, niebieski znaczy mokro.

### Próg pleśni

Alarm o wilgoci (kafel zdarzeń i zgłoszenie watchdoga) nie ma stałego progu. Pleśń
nie rośnie w powietrzu pokoju, tylko na najzimniejszym kawałku ściany zewnętrznej —
w narożniku, za szafą, przy nadprożu — a ten jest tym zimniejszy, im zimniej na
dworze. Rachunek z PN-EN ISO 13788: temperatura powierzchni
`θsi = θe + fRsi·(θi − θe)`, a kłopot zaczyna się, gdy wilgotność przy niej trwale
przekracza 80%. Z tego wychodzi wilgotność powietrza w pokoju, od której robi się
niebezpiecznie — dla pokoju o 20 °C:

| Na dworze | 15 °C | 11 °C | 5 °C | 0 °C | −5 °C | −10 °C |
|---|---|---|---|---|---|---|
| Próg w pokoju | 73% | 68% | 60% | 55% | 50% | 45% |

Dawny stały próg 65% był więc trafny przypadkiem we wrześniu, a w styczniu milczałby
przy 55%, gdy narożniki już pleśnieją. Alarm odzywa się, gdy pokój przez ponad ćwierć
doby stoi powyżej progu ze swojej chwili; każdy odczyt porównywany jest z temperaturą
pokoju i dworu z tej samej chwili. Na wykresie wilgotności względnej próg rysuje się
kreskowaną linią dla średniej temperatury mieszkania — w miejscu dawnej linii dworu,
która chodziła 30–100% i ściskała pokoje w pasek.

`FRSI = 0,70` to liczba z normy, nie z pomiaru. Da się ją zmierzyć: jeden czujnik na
dobę w najzimniejszym narożniku ściany zewnętrznej, drugi w środku pokoju, i odczyt
z dworu — `fRsi = (θnarożnik − θdwór) / (θpokój − θdwór)`. Na razie tego nie robimy:
czujniki zostają na swoich miejscach, więc obowiązuje wartość z normy.

### Wykrywanie wietrzenia — usunięte

Do 27.09.2026 strona rysowała pasma „wykrytego wietrzenia". Przy raportach co godzinę
i czujnikach z krokiem 0,1 °C nie dało się go dostroić: latem wymagało trzech przeróbek,
przez 44 doby znalazło 7 epizodów, a od 8.09 nie znalazło żadnego. Kod jest w historii
gita (usunął go commit `06f4a52`; ostatnia wersja z detektorem to jego rodzic), opis tego, jak działało
i dlaczego tak, w `KONTEKST.md`.

Kafel pokoju dopisuje też, **dokąd temperatura zmierza**: regresja liniowa z ostatnich
czterech godzin wyciągnięta naprzód. Gdy z przedłużenia wychodzi przekroczenie progu
komfortu, pokazuje godzinę (`↗ 28° ok. 17:00`) zamiast samego tempa — to ta informacja,
po którą się sięga. Poniżej `TREND_MIN` kafel milczy, bo nachylenia mniejszego niż
0,25 °C/godz. nie da się przy godzinnych raportach odróżnić od szumu czujnika.
Powyżej `TREND_MAX` (0,7 °C/godz.) też milczy: tak szybko pokój sam z siebie nie jedzie
(ściany i słońce to najwyżej 0,5), to impuls — farelka, prysznic, otwarte okno —
i przedłużony linią prostą obiecywałby „28° za godzinę" w łazience, która za godzinę
wróci do 21 °C.

### Farelka w łazience

Farelka to prawdziwe grzanie, nie usterka czujnika, więc strona ją pokazuje. Filtr
chwilowych skoków odsiewa wyłącznie nagłe wyskoki **ze spokojnego poziomu** (czujnik
w dłoni); do 27.09 wycinał też środek grzania farelką i zostawiał na wykresie garb
o złej godzinie. Skala barw rzutu bierze percentyle godzinowych średnich, więc pół
godziny farelki jej nie rozciąga, a kafel trendu przy takim impulsie milczy.

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

**Limit zapytań Tuya.** Każdy przebieg pobiera pełne 7 dni logów, czyli ok. 30 zapytań
(ok. 24 strony logów po 100 wpisów dla czterech czujników, plus token i specyfikacje).
Co godzinę to ok. 750 zapytań na dobę, do tego przebiegi z zapasowego harmonogramu
GitHuba. Trial IoT Core ma miesięczny limit zapytań — jego wykorzystanie widać na
iot.tuya.com w projekcie, przy usłudze IoT Core.

## Na ekranie telefonu

Strona instaluje się jak aplikacja — własna ikona, pełny ekran, bez paska przeglądarki:

- **Android (Chrome):** menu ⋮ → **Zainstaluj aplikację** (albo „Dodaj do ekranu głównego").
- **iPhone (Safari):** przycisk udostępniania (kwadrat ze strzałką) → **Do ekranu
  początkowego** → „Dodaj". Musi to być Safari — inne przeglądarki na iPhonie tej opcji
  nie mają albo dodają zwykłą zakładkę.

Na iPhonie pasek stanu jest przezroczysty, więc strona zostawia pod nim miejsce
(`viewport-fit=cover` i `env(safe-area-inset-*)`); bez tego nagłówek wchodził pod zegar.
Widżety na ekran główny (Scriptable, KWGT) były gotowe 27.09 i zostały wycofane tego
samego dnia — zainstalowana strona wystarcza.

## Gdy coś nie działa

| Objaw | Co z tym |
|---|---|
| Strona: „Nie ma jeszcze żadnych odczytów" | Kolektor nie zrobił jeszcze udanego przebiegu. Zakładka Actions |
| Zamiast wykresów: „Nie udało się wczytać biblioteki wykresów" | Sieć blokuje `cdn.jsdelivr.net` albo CDN ma awarię. Kafle, tabele i rzut działają dalej; wykresy wrócą same |
| „Zbieranie odczytów" na czerwono z „Push odrzucony" | Dwa przebiegi kolektora weszły sobie w drogę. `zapisz.sh` liczy wtedy odczyty jeszcze raz na drzewie zwycięzcy i próbuje trzy razy; czerwień znaczy, że nie udało się ani razu. Odczyty nie giną — następny przebieg i tak bierze okno 7 dni |
| Zgłoszenie „brak nowej pogody od… , Open-Meteo nie odpowiada" | Dwór milczy dłużej niż zwykle. Czujniki i wykresy mieszkania działają dalej; rada o wietrzeniu i łuk doby czekają na świeżą prognozę |
| Na stronie zniknął dwór, choć czujniki działają | Przebieg nie dostał odpowiedzi z Open-Meteo. Historia leży dalej w CSV, a `keep_known` w `fetch.py` trzyma urządzenie w manifeście, dopóki ma odczyty — linia wróci przy najbliższym udanym przebiegu. Jeśli mimo to zniknęła, w logu przebiegu szukaj „Pogoda: pominięta" |
| Pulpit: „Kolektor nie zapisał nic od…" | Problem po stronie Actions albo Tuya, nie czujników. Czujniki oceniane są do chwili ostatniej zbiórki, więc przy spóźnionym kolektorze nie świecą się na pomarańczowo |
| Dane przychodzą co 3–5 godz. zamiast co godzinę, przebiegi zielone | GitHub opóźnia harmonogram (od końca sierpnia 2026 to norma). Odczyty nie giną — każdy przebieg bierze 7 dni wstecz — ale strona jest nieświeża, a watchdog potrafi zgłosić fałszywe „Kolektor stoi". Lekarstwo: zewnętrzny zegar, patrz „Kolektor co godzinę" |
| Błąd `28841002` w logu | Wygasł trial IoT Core. Wniosek o przedłużenie na iot.tuya.com, 1-2 dni robocze. Pierwszy trial wygasł **po miesiącu** (12.09.2026) — datę kolejnego sprawdzać na iot.tuya.com |
| Błąd `1004` | Access Secret przepisany z ucięciem znaku |
| Błąd `1114` albo `2007` | Zły region w `TUYA_REGION` |
| Pusta lista przy `--discover` | Konto Smart Life podpięte do innego data center |
| Bateria: `niski` | Wymień ogniwo. Słabnąca bateria gubi raporty, zanim czujnik zniknie zupełnie |
| Zgłoszenie „Czujniki wymagają uwagi" | Watchdog wyłapał słabą baterię, milczący czujnik albo wilgotność powyżej progu pleśni przez ponad ćwierć doby. Treść odświeża się co kilka godzin, zgłoszenie zamknie się samo |
| Przebiegi w ogóle nie ruszają | GitHub wyłącza harmonogramy po 60 dniach bezczynności. Jedno ręczne uruchomienie je wskrzesza |

---

## Testy

```bash
python -m unittest discover -s tests -v        # kolektor, sama biblioteka standardowa
cd tests/frontend && npm ci && npx playwright test
```

Dwie warstwy, bo są dwa różne rodzaje ryzyka.

**Kolektor** ma testy jednostkowe czystych funkcji — rozpoznawanie pól Tuya, filtr
wyskoków, przeliczanie stref w prognozie, progi diagnostyki — plus zestaw sprawdzający
**prawdziwe `data/`**: czy pliki miesięczne są posortowane i bez duplikatów, czy każde
urządzenie z odczytów jest w manifeście, czy włącznik ma wyłącznie zmiany stanu i czy
`dzienne.csv` da się odtworzyć z surowych odczytów co do bajtu. Ta druga grupa nie
zależy od żadnej zmiany w kodzie, więc chodzi też raz na dobę z harmonogramu.

**Strona** jest testowana w prawdziwej przeglądarce, bo `index.html` to jeden plik bez
budowania — nie ma czego importować w oderwaniu od DOM-u. Dane są podstawiane
(`tests/frontend/dane.js`) i układane pod konkretne zjawisko: pokój, który się nagrzewa,
czujnik, który zamilkł, parna prognoza bez okna na wietrzenie, nazwa urządzenia ze
znacznikiem HTML. Każdy test wywraca się też na dowolnym błędzie w konsoli.

Fikstury muszą trzymać się skali prawdziwych danych, bo inaczej test przestaje
cokolwiek sprawdzać. Wietrzenie w `dane.js` to pokój dążący do temperatury dworu,
a nie zjazd wilgotności o 16 punktów, jak było wcześniej — tamto było dziewięć razy
poza tym, co pokój w ogóle potrafi, więc przechodziło przy każdym progu. Okna epizodów
fikstura **wybiera z własnych danych** (szuka godzin, w których na dworze jest
odpowiednio chłodniej), a nie odlicza od „teraz": inaczej wynik zależałby od pory doby,
o której testy poszły, i nocny przebieg z harmonogramu wywracałby się losowo.

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
odczytów — a wtedy dashboard przestanie się aktualizować.

### Dwie rzeczy warte zapamiętania przy pisaniu kolejnych testów

- **Fikstura też potrafi kłamać.** Dwa razy przepuściła czerwone CI: raz dopisując
  odczyt na istniejący znacznik (regresja liczyła się z dwóch wartości naraz), raz
  rytmem dobowym tak żywym, że sam przebijał próg trendu i „spokojny pokój" przestawał
  być spokojny o niektórych porach doby. Osobny zestaw `same dane testowe` pilnuje
  teraz samej fikstury.
- **Service worker musi być zablokowany** (`serviceWorkers: 'block'`). Inaczej
  przechwytuje `fetch` strony i idzie prosto do sieci, omijając podstawione dane —
  manifest przychodzi z fikstury, CSV prawdziwy z repozytorium i pokoje wyglądają na
  martwe. Sam worker ma jeden własny test, który go włącza.
- **Czekaj na stempel w nagłówku, nie na `#app`.** `boot()` odsłania stronę przed
  `render()`, więc oglądanie samej widoczności łapie ją w połowie rysowania.

---

## Koszt

Zero. Publiczne repozytorium ma darmowe minuty Actions i darmowe Pages.
Open-Meteo nie wymaga klucza API (licencja CC BY 4.0 — stąd podpis w stopce). Jedyne ograniczenie to darmowy trial
IoT Core u Tuya, który trzeba przedłużać wnioskiem na iot.tuya.com — pierwszy
wygasł po miesiącu, a zatwierdzenie trwa 1–2 dni robocze. Zewnętrzny zegar
(cron-job.org) też jest darmowy.
