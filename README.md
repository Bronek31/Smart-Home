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
| `TODO.md` | pomysły na później i te świadomie odrzucone, wraz z powodami |
| `tests/` | testy kolektora i strony; nie trafiają na Pages, bo Pages serwuje tylko katalog główny |
| `.githooks/pre-push` | nie przepuszcza pusha, dopóki testy nie przejdą |
| `.github/workflows/zbieraj.yml` | harmonogram zbierania, co godzinę o :19 |
| `.github/workflows/watchdog.yml` | raz na dobę sprawdza, czy kolektor żyje i czy czujniki nie wołają o rękę |
| `.github/workflows/odkryj.yml` | na żądanie wypisuje urządzenia w Tuya i ich pola |
| `.github/workflows/testy.yml` | testy przy każdej zmianie kodu i raz na dobę na żywych danych |
| `manifest.json`, `sw.js`, `ikona*` | instalacja na ekranie głównym telefonu i tryb offline |
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
| `OUTDOOR_LAT` / `OUTDOOR_LON` | Katowice | pogoda i smog z Open-Meteo. Puste = wyłączone |
| `TZ_LOCAL` | `Europe/Warsaw` | według tej strefy tną się doby w agregatach |

Proporcje pokoi na rzucie mieszkania siedzą w stałej `PLAN` w `index.html` —
to `x, y, w, h` w siatce 400×500. Progi alarmów (`HEARTBEAT`, `STALE_WARN`)
i filtra chwilowych skoków (`SPIKE`) są tuż obok.

Tam też stoi **orientacja mieszkania**: pole `okno` mówi, na którą stronę świata
patrzy pokój (`pld` albo `pln`, opisane w `STRONY`). Sypialnia wychodzi na południe,
salon i kuchnia na północ — na rzucie góra to więc południe. To nie jest ozdoba:
z tego bierze się rada, żeby w upalne, słoneczne godziny zaczynać wietrzenie od
strony północnej, bo okno od południa wpuszcza wtedy ciepło, którego prognoza
temperatury nie pokazuje. Obok są `dop` i `bier` — nazwy pokoi w dopełniaczu
i bierniku, bo podpowiedzi wklejają je wprost w zdanie.

Pod rzutem siedzi **odtwarzanie historii**: suwak przewija mieszkanie w czasie, a
przycisk puszcza je w pętli. Przebieg powtarza się trzy razy, z krótkim przystankiem
na końcu każdego okrążenia, i wraca do stanu bieżącego; pauza zatrzymuje go wcześniej,
tam gdzie akurat jest. Jeden przebieg to za mało, żeby cokolwiek wyłapać, a pętla bez
końca miele w tle bez powodu — stąd `PETLE_MAX` i `PAUZA_KONCA`. Odtwarzanie zatrzymuje
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

Poza wykresami dashboard odpowiada na dwa pytania. **Czy wietrzyć teraz** — przez
porównanie wilgotności bezwzględnej w mieszkaniu i na dworze; jeśli na zewnątrz jest
sucho, otwarte okno osuszy. **O której dziś wietrzyć** — z prognozy godzinowej
Open-Meteo, ta sama różnica policzona na dobę naprzód. Godziny cieplejsze od
mieszkania odpadają: wietrzenie ma osuszyć, nie dogrzać.

Progi (`WIETRZ_ZYSK`, `WIETRZ_CIEPLO`, `SLONCE_MOCNE`) siedzą w `index.html` obok
tych funkcji.

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
| Pulpit: „Kolektor nie zapisał nic od…" | Problem po stronie Actions albo Tuya, nie czujników |
| Błąd `28841002` w logu | Wygasł trial IoT Core. Wniosek o przedłużenie na iot.tuya.com, 1-2 dni robocze |
| Błąd `1004` | Access Secret przepisany z ucięciem znaku |
| Błąd `1114` albo `2007` | Zły region w `TUYA_REGION` |
| Pusta lista przy `--discover` | Konto Smart Life podpięte do innego data center |
| Bateria: `niski` | Wymień ogniwo. Słabnąca bateria gubi raporty, zanim czujnik zniknie zupełnie |
| Zgłoszenie „Czujniki wymagają uwagi" | Watchdog wyłapał słabą baterię, milczący czujnik albo wilgotność trzymającą się za wysoko od doby. Treść odświeża się co dobę, zgłoszenie zamknie się samo |
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
