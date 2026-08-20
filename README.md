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
w salonie bierze wyłącznie to, kiedy chodził. Bez tego jego osuszanie liczyłoby się
jako wietrzenie, bo w powietrzu wygląda tak samo jak otwarte okno. Które urządzenie
stoi w którym pokoju, mówi `SPRZET_POKOJ` w `index.html`.

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
| `.github/workflows/zbieraj.yml` | harmonogram zbierania, co godzinę o :19 |
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
wykrywania wietrzenia (`WIETRZ`) i filtra chwilowych skoków (`SPIKE`) są tuż obok.
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

## Dwie osie na wykresach

Dwór potrafi w tygodniu przejść 16 → 32 °C, a pokoje stoją wtedy w paśmie 25 → 26.
Na wspólnej osi cały ruch w mieszkaniu spłaszcza się do kilku pikseli i cztery linie
zlewają się w jedną. Dlatego **temperatura** i **wilgotność względna** mają serię
zewnętrzną na osobnej osi po prawej, podpisanej jej kolorem i bez własnej siatki —
żeby było widać, że to druga miarka. Nagłówek każdego z tych wykresów mówi to wprost;
podpis pojawia się tylko wtedy, gdy druga oś naprawdę powstała, czyli gdy jest czujnik
zewnętrzny.

Linie pokoi są **wygładzone średnią z trzech kolejnych odczytów**. Czujniki raportują
z krokiem 0,1 °C i 1%, a po rozdzieleniu osi lewa skala pokazuje niecałe dwa stopnie na
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

### Krawędzie wykresu

Czujniki raportują każdy w innej minucie godziny i te minuty dryfują, więc bez zabiegu
każda linia zaczyna się i kończy tam, gdzie akurat wypadł jej raport. Zmierzone 20.08
w widoku „dziś": starty rozjechane o **46 minut**, końce o **53** — przy oknie 8,5 godziny
to po dziesiątej części szerokości wykresu z każdej strony, a linia urwana w powietrzu
wygląda jak martwy czujnik, nie jak czujnik, który jeszcze się nie odezwał.

Lewą krawędź wyrównuje **kotwica**: do rysowania dokładany jest jeden prawdziwy odczyt
sprzed granicy zakresu, a odcinek do niego przycina oś ustawiona na najwcześniejszy
odczyt z zakresu. Nic nie jest dorysowywane — linia po prostu wchodzi w kadr z lewej.
Do tabeli zakresów ani do wykrywania wietrzeń kotwica nie wchodzi; pilnują tego testy.

Prawej krawędzi tak wyrównać się nie da, bo przyszłych odczytów nie ma. Tam ostatni
odczyt każdego pokoju dostaje **kropkę** — koniec linii jest wtedy znakiem, a nie
urwaniem, i zgadza się z tym, co kafel mówi słowami („ostatni raport 52 min temu”).

Rusza wyłącznie rysowana linia. Kafle, tabela zakresów, rzut mieszkania i wykrywanie
wietrzeń liczą z surowych odczytów, a dymek na wykresie pokazuje ten odczyt, który
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

## Który fragment jaki okres pokazuje

Przełącznik u góry nazywa się **Zakres wykresów** i tyle obejmuje — same wykresy.
Każdy fragment strony, który patrzy na inny okres, mówi o tym wprost albo ma własny
przełącznik; inaczej wybór „dziś" po cichu obcinałby połowę strony do kilku godzin.

| Fragment | Okres | Skąd |
|---|---|---|
| Wykresy | **Zakres wykresów** u góry | to jego zadanie |
| Tabela zakresów | **Zakres tabeli** nad tabelą | własny, bo skrajne wartości ogląda się dla innego okresu niż przebieg |
| Kafle pokoi | teraz, zmiana z 24 h, trend z 4 h | stały |
| Rzut i odtwarzanie | tydzień albo doba | własny przełącznik pod rzutem |
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

**O której dziś będzie najsuchsze powietrze** — z prognozy godzinowej Open-Meteo,
różnica wilgotności policzona na dobę naprzód. Godziny cieplejsze od mieszkania
odpadają: to okno ma osuszyć, nie dogrzać. Ramka mówi wprost, że chodzi o suchość,
bo inaczej przeczyłaby kaflowi obok — w letni wieczór najlepiej otworzyć okno *teraz*,
dla chłodu, a najsuchsze powietrze przychodzi nad ranem.

Progi (`WIETRZ_ZYSK`, `WIETRZ_CIEPLO`, `SLONCE_MOCNE`) siedzą w `index.html` obok
tych funkcji.

### Jak rozpoznajemy, że okno **było** otwarte

To osobna sprawa od rady „czy wietrzyć teraz" i liczy się z samych odczytów.
Przy wymianie powietrza pokój dąży do wartości z dworu wykładniczo:
`d(x)/dt = λ·(x_dwór − x_pokój)`. Wykrywamy więc **λ — ułamek dostępnej różnicy
domykany w ciągu godziny** — a nie bezwzględny skok. Bezwzględny próg nie działa,
bo znaczy co innego w każdą pogodę: dokładnie na tym poległa pierwsza wersja, która
wymagała 0,7 g/m³ wilgotności bezwzględnej w oknie dwóch godzin. Zmierzone na pięciu
dobach: największy ruch dwugodzinny w mieszkaniu to **0,50 g/m³** (w Salonie 0,33),
czyli próg stał wyżej niż fizycznie osiągalne maksimum i przez cały czas zbierania
nie wykrył **ani jednego** wietrzenia.

Wyzwala **wyłącznie temperatura**, i to jest wynik pomiaru. Pierwsza wersja pozwalała
wyzwalać także wilgotności bezwzględnej i 20.08 narysowała wietrzenie od 13 do 16
w czterech pokojach naraz — przy oknach zamkniętych od 8 do 18. Zmierzone na tej dobie:

| kanał | przy oknach ZAMKNIĘTYCH | przy oknach OTWARTYCH |
|---|---|---|
| wilgotność bezwzględna | λ **do 2,45/godz.** — parę produkuje kuchnia, prysznic i domownicy, a na dworze w upał jest jej dużo | milczy: różnica z dworem spada poniżej progu, kanał nie ma czego mierzyć |
| temperatura | λ **do 0,18/godz.** — tyle dowożą ściany i słońce | pewne kroki od 0,25/godz. w górę |

Wilgotność myli się więc w obie strony naraz: kłamie, gdy okna są zamknięte, i milczy,
gdy są otwarte. Temperatura myli się przewidywalnie i da się to odciąć progiem. Kanał
wilgotności zostaje wyłącznie jako strażnik odbicia — tam jego czułość na parę
z gotowania jest zaletą, bo garnek ma być odsiany razem z ręką na czujniku.

Trzy zabezpieczenia, wszystkie w stałej `WIETRZ` w `index.html`:

| | |
|---|---|
| `luka` | poniżej takiej różnicy z dworem kanał milczy — „w stronę dworu" przestaje cokolwiek znaczyć, a dzielenie małego ruchu przez małą różnicę produkuje wielkie λ z samego szumu |
| `ruch` | ruch mniejszy niż dwa kroki kwantyzacji czujnika (0,1 °C i 1%) to szum, choćby ułamek wychodził duży |
| `odbicie` | **strażnik odbicia**: gdy pokój przed chwilą *oddalił się* od dworu szybciej, niż potrafi sam z siebie, to powrót po takim zaburzeniu nie jest wymianą powietrza. Bez tego czujnik wzięty do ręki wygląda dokładnie jak otwarte okno — i właśnie tak wyglądał 19.08.2026 |

Pasma rysują się nad **temperaturą i wilgotnością bezwzględną** — czyli nad tymi
dwoma wykresami, z których wykrywanie korzysta. Wilgotność względna ich nie dostaje
celowo: skacze od samej temperatury, więc pasmo nad nią obiecywałoby związek, którego
tam nie ma.

Czego to nadal nie wykryje: wietrzenia słabszego niż **20% różnicy temperatur na
godzinę**, ani żadnego, gdy na dworze jest niemal tyle samo stopni co w mieszkaniu.
Przy raportach co godzinę takiego epizodu nie da się odróżnić od ścian i słońca, więc
próg jest tam, gdzie jest, świadomie — sprawdzone przeciwko dwóm dobom, o których
wiadomo, kiedy okna były otwarte, a kiedy zamknięte.

Kafel pokoju dopisuje też, **dokąd temperatura zmierza**: regresja liniowa z ostatnich
czterech godzin wyciągnięta naprzód. Gdy z przedłużenia wychodzi przekroczenie progu
komfortu, pokazuje godzinę (`↗ 28° ok. 17:00`) zamiast samego tempa — to ta informacja,
po którą się sięga. Poniżej `TREND_MIN` kafel milczy, bo nachylenia mniejszego niż
0,25 °C/godz. nie da się przy godzinnych raportach odróżnić od szumu czujnika.

---

## Gdy coś nie działa

| Objaw | Co z tym |
|---|---|
| Strona: „Nie ma jeszcze żadnych odczytów" | Kolektor nie zrobił jeszcze udanego przebiegu. Zakładka Actions |
| Zamiast wykresów: „Nie udało się wczytać biblioteki wykresów" | Sieć blokuje `cdn.jsdelivr.net` albo CDN ma awarię. Kafle, tabele i rzut działają dalej; wykresy wrócą same |
| „Zbieranie odczytów" na czerwono z „Push odrzucony" | Dwa przebiegi kolektora weszły sobie w drogę. `zapisz.sh` liczy wtedy odczyty jeszcze raz na drzewie zwycięzcy i próbuje trzy razy; czerwień znaczy, że nie udało się ani razu. Odczyty nie giną — następny przebieg i tak bierze okno 7 dni |
| Zgłoszenie „brak nowej pogody od… , Open-Meteo nie odpowiada" | Dwór milczy dłużej niż zwykle. Czujniki i wykresy mieszkania działają dalej; rada o wietrzeniu i łuk doby czekają na świeżą prognozę |
| Na stronie zniknął dwór, choć czujniki działają | Przebieg nie dostał odpowiedzi z Open-Meteo. Historia leży dalej w CSV, a `keep_known` w `fetch.py` trzyma urządzenie w manifeście, dopóki ma odczyty — linia wróci przy najbliższym udanym przebiegu. Jeśli mimo to zniknęła, w logu przebiegu szukaj „Pogoda: pominięta" |
| Pulpit: „Kolektor nie zapisał nic od…" | Problem po stronie Actions albo Tuya, nie czujników |
| Błąd `28841002` w logu | Wygasł trial IoT Core. Wniosek o przedłużenie na iot.tuya.com, 1-2 dni robocze |
| Błąd `1004` | Access Secret przepisany z ucięciem znaku |
| Błąd `1114` albo `2007` | Zły region w `TUYA_REGION` |
| Pusta lista przy `--discover` | Konto Smart Life podpięte do innego data center |
| Bateria: `niski` | Wymień ogniwo. Słabnąca bateria gubi raporty, zanim czujnik zniknie zupełnie |
| Zgłoszenie „Czujniki wymagają uwagi" | Watchdog wyłapał słabą baterię, milczący czujnik albo wilgotność trzymającą się za wysoko od doby. Treść odświeża się co kilka godzin, zgłoszenie zamknie się samo |
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
IoT Core u Tuya, który trzeba co pół roku przedłużać jednym kliknięciem.
