# Do zrobienia

Plan po przeglądzie z 27.09.2026 — sześć tygodni zbierania, pierwszy chłodny tydzień,
sezon grzewczy za pasem. Trzymam go tutaj, a nie w Issues, bo Issues zajmuje watchdog —
propozycja funkcji obok zgłoszenia „Kolektor stoi" tylko przykrywałaby to drugie.

Ułożone w paczki, które da się wypuścić osobno. Kolejność jest przemyślana: najpierw to,
co psuje zaufanie do strony, potem to, co z niej znika, na końcu to, co dochodzi.

## Stan danych

| | |
|---|---|
| Historia z mieszkania | **44 doby**, od 14.08 |
| Pogoda w historii | od upału (dwór do 33,8 °C, 16.08) po pierwsze chłodne noce (8,6 °C, 24.09) |
| Wykryte wietrzenia | **7 w całej historii**, ostatnie 8.09. Od tamtej pory w żadnym pokoju z oknem temperatura nie spadła o więcej niż 0,7 °C w dwie godziny |
| Wilgotność | średnie dobowe z 50–55% (13.09) do **60–71%** (23–27.09), najwyżej kuchnia i łazienka, przy pokojach stygnących z 22 do 19,5 °C |
| Zapisy kolektora | do 26.08 mediana co **55 min**, od 27.08 co **3,5–4,5 godz.** (bez zmiany w kodzie — patrz A0) |

---

## A0. Zewnętrzny zegar dla kolektora — ręka właściciela, ok. 10 minut

**Przyczyna jest po stronie GitHuba, nie kodu.** Przebiegi nie padają — harmonogram
ich po prostu nie tworzy na czas. Watchdog (cron co 6 godz.) startuje z opóźnieniem
2,5–5,5 godz., więc to dławienie całego harmonogramu repozytorium, nie jednego workflowu.
Odczyty nie przepadają (każdy przebieg bierze z Tuya pełne 7 dni), cierpi tylko „teraz".

Naprawa bez zmiany w repozytorium — `workflow_dispatch` już jest:

1. GitHub → Settings → Developer settings → Fine-grained tokens. Dostęp **tylko do
   Smart-Home**, uprawnienie **Actions: Read and write** i nic więcej (bez dostępu do
   kodu i sekretów). Datę ważności wpisać w kalendarz.
2. cron-job.org (darmowe), co godzinę o :19:
   `POST https://api.github.com/repos/Bronek31/Smart-Home/actions/workflows/zbieraj.yml/dispatches`,
   nagłówki `Authorization: Bearer <token>` i `Accept: application/vnd.github+json`,
   treść `{"ref":"main"}`. Poprawna odpowiedź to `204`.

Harmonogram w `zbieraj.yml` zostaje jako zapas.

**Przy okazji: trial IoT Core wygasł 12.09** (sześć przebiegów z kodem `28841002`),
czyli miesiąc po starcie, a nie pół roku, jak mówi README. Sprawdzić na iot.tuya.com
datę następnego wygaśnięcia i poprawić README.

## A. Zaufanie do tego, co widać — mała paczka, bez ryzyka

1. **Status czujników liczony od ostatniej zbiórki, nie od „teraz".** Przy opóźnionym
   kolektorze kafle mówią „0/4 OK · 4 uwaga", a tabela łączności świeci na pomarańczowo
   „5 godz. temu" — tuż obok zdarzenia „to nie wina czujników". Strona przeczy sama
   sobie. Wiek raportu czujnika trzeba mierzyć do `updated` z `index.json`; opóźnienie
   kolektora zgłasza jedno miejsce (kafel „ostatnia zbiórka" i zdarzenie).
2. **Skala barw rzutu bez prysznica.** 27.09 rano łazienka doszła do 26,9 °C i skala
   rozjechała się do 19,2–27,0 °C, a pokoje stoją w 19,9–21,0 — cztery pokoje w jednym
   odcieniu. Skala bierze surowe odczyty, choć filtr skoków ukrywa ten sam prysznic na
   wykresie i w tabeli. Skoro odtwarzanie jest schowane, prościej i czytelniej: **stała
   skala komfortu** (np. 17–25 °C), w której niebieski znaczy „chłodno", a pomarańcz
   „ciepło" niezależnie od tygodnia.
3. **Rada wietrzenia przestaje być letnia.** „Słońce stoi wtedy od południa, więc zacznij
   od salonu i kuchni, a sypialnię otwieraj krótko" pokazuje się dziś przy 13–21 °C,
   a jesienią słońce od południa to zysk. `stronaStartowa()` patrzy wyłącznie na
   nasłonecznienie — ma się odzywać tylko wtedy, gdy na dworze jest ciepło.
4. **Actions: ostrzeżenie o Node 20** przy `checkout@v4`, `setup-python@v5`,
   `setup-node@v4`. Dziś działa na wymuszonym Node 24; podbić wersje, zanim przestanie.

## B. Wykrywanie wietrzenia znika — średnia paczka

Decyzja z 27.09: **do odpuszczenia.** Przy raportach co godzinę i czujnikach
z krokiem 0,1 °C nie da się go dostroić tak, żeby było dobrze — latem wymagało trzech
przeróbek, a jesienią milczy od 8.09. `KONTEKST.md` nazywał to wprost „świadomym sufitem".

1. **Usunąć, nie wyłączyć** (odwrotnie niż odtwarzanie, które ma wrócić): `WIETRZ`,
   `kanalyPokoju`, `wietrzenia`, `policzWietrzenia`, wtyczkę `pasma`, licznik i legendę
   przy wykresach, kolumnę „wietrzenia" w tabeli zakresów, opis o „błękitnych wstążkach"
   pod wilgotnością bezwzględną. Z nimi ok. 12 testów i fikstury `wietrzenie`
   i `rekaNaCzujniku` w `tests/frontend/dane.js`. Kod zostaje w historii gita.
2. **Razem z nimi pasma klimatyzatora** (`SPRZET_POKOJ`, `okresyPracy`): trzy wiersze,
   ostatni 13.08. Zbieranie włącznika można zostawić — nic nie kosztuje.
3. **Zostaje rada „czy wietrzyć teraz" i „Najsuchsze powietrze"** — liczone z prognozy
   i bieżących odczytów, nie z wykrywania. Przy 70% w kuchni i łazience to najbardziej
   użyteczna rzecz na stronie.
4. **Tabela „Łączność z bramką" pod rozwijanym „Diagnostyka"**, domyślnie zwiniętym.
   To narzędzie do szukania usterek, a o usterkach i tak mówią watchdog i zdarzenia.

## C. Wilgotność na sezon grzewczy — średnia paczka

1. **Ryzyko pleśni zamiast stałych 65%** (`HUM_ALERT` w `fetch.py` i `index.html`).
   Pleśń rozstrzyga się w najzimniejszym rogu ściany zewnętrznej, a jego temperatura
   zależy od dworu. Metoda z PN-EN ISO 13788 (czynnik temperaturowy fRsi = 0,7,
   wilgotność na powierzchni powyżej 80%), dla pokoju o 20 °C:

   | Na dworze | 11 °C | 5 °C | 0 °C | −5 °C | −10 °C |
   |---|---|---|---|---|---|
   | Wilgotność, od której grozi pleśń | 68% | 60% | 55% | 50% | 45% |

   We wrześniu 65% przypadkiem się zgadza; w styczniu alarm milczałby przy 55%, gdy rogi
   już pleśnieją. Wszystkie dane już są. fRsi to liczba z normy, nie z pomiaru —
   **zmierzyć ją**: jeden czujnik na dobę w najzimniejszym rogu ściany zewnętrznej.
2. **Wykres wilgotności względnej bez dworu.** Dwór (30–100%) rozciąga oś i ściska
   pokoje w paśmie 55–78. Projekt sam ustalił, że porównywanie wilgotności względnej
   z dworem jest fizycznie mylące — porównanie z dworem zostaje na wilgotności
   bezwzględnej, gdzie ma sens. Na zwolnione miejsce: linia progu pleśni z C1.

## D. Telefon — średnia paczka

1. **Kolejność sekcji.** Pierwszy ekran to cztery wiersze diagnostyki (ok. 270 px), zanim
   pojawi się pierwsza temperatura, a pogoda z radą wietrzenia leży na samym dole
   strony długiej na ok. 4900 px. Propozycja: status w jednej linii, kafle, zaraz pod
   nimi pogoda i rada, potem wykresy; tabele i rzut niżej. Kafel dworu na całą
   szerokość zamiast samotnej komórki obok pustej.
2. **Tabele przewijają się w bok bez żadnej wskazówki** — połowa kolumn jest poza
   ekranem. Na wąskim ekranie „min–max" w jednej kolumnie; po B1 znika też kolumna
   wietrzeń.

## Odłożone

| Pomysł | Dlaczego nie teraz |
|---|---|
| Model cieplny pokój ↔ dwór | Odpowiada na letnie pytanie („sypialnia 29 °C o 19:00"), a z kaloryferami pasywny model przestaje pasować. Dane z sierpnia i września zostają w gicie, stronę „dwór" da się dociągnąć z archiwum Open-Meteo kiedykolwiek. **Wrócić w maju 2027** |
| Skutek wietrzenia | Odpada razem z wykrywaniem (B) |
| Plik z godzinami otwarcia okien | Przez sześć tygodni nie powstał ani jeden wpis — ręczny plik nie pasuje do nawyków. Odpada razem z wykrywaniem |

## Świadomie odrzucone

| Pomysł | Dlaczego nie |
|---|---|
| Wykrywanie anomalii, cokolwiek „uczącego się" | Przy trzech dobach to generator fałszywych alarmów. Przy roku i czterech czujnikach nadal nie ma czego się uczyć poza rytmem dobowym, który mapa cieplna pokazuje wprost |
| Wykrywanie obecności domowników | Bez czujnika CO₂, z samej wilgotności, to zgadywanka |
| Rekordy i statystyki („najcieplejsza noc") | Tanie, ale po pierwszym obejrzeniu nikt tam nie zagląda |
| Rozbudowa wokół klimatyzatora | Włącznik ma trzy wiersze. Wrócić, gdy urządzenie znów zacznie chodzić |
| Sterowanie urządzeniami ze strony | Tuya ma API do komend, ale strona jest statyczna i nie ma gdzie schować sekretu. Token w przeglądarce albo `workflow_dispatch` z frontendu to klucz do konta Tuya w publicznym kodzie |
| Wykrywanie wietrzenia i wszystko, co na nim stoi | Patrz B. Przy raportach co godzinę nie da się go dostroić; 7 epizodów w 44 dobach, zero od 8.09 |
| Powiadomienia push | Brak serwera. Rolę powiadomień pełnią zgłoszenia zakładane przez watchdoga — GitHub wysyła o nich maila |

## Zrobione

- **Odtwarzanie historii na rzucie schowane** (27.09) — przełącznikiem `ODTWARZANIE`,
  nie usunięte: kod zostaje pod testami, które włączają go flagą, więc powrót to jedna linia.
- **Odtwarzanie historii na rzucie mieszkania** — suwak i przycisk pod planem,
  pionowa kreska „jesteś tutaj" na wykresach. Pokazuje, jak ciepło wędruje przez
  mieszkanie: słońce wchodzi w sypialnię od południa, salon i kuchnia od północy idą
  z opóźnieniem. Tego cztery nałożone linie nie pokazują.
- **Widoczna skala kolorów** — stała 19–28 °C była o rząd wielkości za szeroka na dobę
  (mieszkanie mieści się w 0,9 °C), a przejście błękit → pomarańcz prowadziło przez
  zieleń, więc wszystko lądowało w zielonym środku. Skala dobiera się teraz do okna,
  paleta nie ma martwego miejsca, a rozstaw barw między pokojami wzrósł z 46 na 170.
- **Tryb odchyłki, pasek kontekstu i okno domyślnie na cały zakres** — trzecie podejście
  do czytelności animacji, tym razem po zmierzeniu, co w danych w ogóle jest.
  Przez dobę pokój rusza się o 0,2–0,4 °C, a pokoje różnią się o 0,67 °C, więc obraz
  był w 2/3 statyczny. Odjęcie średniej pokoju podniosło ruch barwy Salonu z 29 na 133.
- **Ekstrapolacja trendu** — regresja z ostatnich czterech godzin w kaflu pokoju,
  z godziną przekroczenia progu komfortu zamiast samego tempa. Milczy poniżej
  0,25 °C/godz., bo tyle wynosi próg odróżnialności od szumu przy raportach co godzinę.
- **Testy** — 51 testów kolektora (biblioteka standardowa) i 35 testów strony
  w przeglądarce, wpięte w GitHub Actions: przy każdej zmianie kodu i raz na dobę na
  żywych danych. Szczegóły w README.
- **Rytm doby** — mapa cieplna godzina × doba z przełącznikiem pokoju. Przy trzech
  dobach to trzy wiersze, ale rośnie sama i nie wymaga już żadnej pracy. Skala wspólna
  dla wszystkich pokoi, żeby przełączanie zakładek dało się czytać jako porównanie;
  trzy pokoje na cztery nic na tym nie tracą (kontrast 217 → 193–199), płaci wyłącznie
  najstabilniejsza Łazienka (217 → 74) i ma do tego prawo.
