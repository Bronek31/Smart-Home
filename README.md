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
| `.github/workflows/zbieraj.yml` | harmonogram zbierania, co godzinę o :19 |
| `.github/workflows/watchdog.yml` | raz na dobę sprawdza, czy kolektor żyje i czy czujniki nie wołają o rękę |
| `.github/workflows/odkryj.yml` | na żądanie wypisuje urządzenia w Tuya i ich pola |
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

Pod spodem są dwa przełączniki. Pierwszy wybiera **okno**: cały widoczny zakres albo
ostatnia doba. Drugi wybiera, **co znaczy kolor**:

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

Skala jest domyślnie **wspólna dla wszystkich pokoi**, żeby przełączanie zakładek dało
się czytać jako porównanie — przy osobnych skalach ten sam kolor znaczyłby w każdej
zakładce co innego. Kosztuje to zaskakująco mało: pokoje o szerokim zakresie tracą na
kontraście tyle co nic, płaci tylko ten najbardziej stabilny, i to jest uczciwe.
`skala pokoju` rozciąga paletę na zakres jednego pomieszczenia, gdy chcesz obejrzeć
sam jego rytm.

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

## Koszt

Zero. Publiczne repozytorium ma darmowe minuty Actions i darmowe Pages.
Open-Meteo nie wymaga klucza API (licencja CC BY 4.0 — stąd podpis w stopce). Jedyne ograniczenie to darmowy trial
IoT Core u Tuya, który trzeba co pół roku przedłużać jednym kliknięciem.
