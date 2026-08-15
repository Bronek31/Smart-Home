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

## Co strona radzi i skąd to wie

Poza wykresami dashboard odpowiada na dwa pytania. **Czy wietrzyć teraz** — przez
porównanie wilgotności bezwzględnej w mieszkaniu i na dworze; jeśli na zewnątrz jest
sucho, otwarte okno osuszy. **O której dziś wietrzyć** — z prognozy godzinowej
Open-Meteo, ta sama różnica policzona na dobę naprzód. Godziny cieplejsze od
mieszkania odpadają: wietrzenie ma osuszyć, nie dogrzać.

Progi (`WIETRZ_ZYSK`, `WIETRZ_CIEPLO`, `SLONCE_MOCNE`) siedzą w `index.html` obok
tych funkcji.

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
