# Do rozważenia

Propozycje, nie zobowiązania. Kolejność jest przemyślana: wyżej stoi to, co da się
zrobić na dzisiejszych danych, niżej to, co musi poczekać, aż historia urośnie.

Trzymam je tutaj, a nie w Issues, bo Issues zajmuje watchdog — propozycja funkcji
obok zgłoszenia „Kolektor stoi" tylko przykrywałaby to drugie.

## Ile mamy danych

Stan na 15.08.2026, po trzech dobach zbierania:

| | |
|---|---|
| Historia z mieszkania | **65 godzin**, od 12.08 15:20 |
| Historia z dworu | 224 godziny — Open-Meteo oddaje 7 dni wstecz, więc start był z zapasem |
| Realna rozdzielczość | **~1 godzina.** Mediana odstępu 59–60 min w każdej serii. Raporty przy zmianie o 0,5 °C zdarzają się, ale to mniejszość: Salon 101 odczytów na 65 godz., Łazienka 70 |
| Włącznik klimatyzatora | **3 wiersze**, ostatni 13.08. Cokolwiek na tym opartego pokaże kreski |

To jest powód, dla którego lista jest ułożona tak, a nie inaczej. Trzy doby to trzy
cykle dobowe, wszystkie w jednej fali upałów.

---

## 1. Skutek wietrzenia, nie tylko fakt wietrzenia

Epizody już wykrywamy i rysujemy pasmami. Brakuje domknięcia pętli: **o ile** każde
wietrzenie ścięło wilgotność bezwzględną i **jak długo** efekt się trzymał.

> Wczoraj 6:20 — minus 2,1 g/m³, wróciło po 4 godzinach.

Zero nowych danych, zero nowych zależności. Zamienia detekcję w informację zwrotną:
po tygodniu wiadomo, czy wietrzenia w ogóle coś dają i które pory działają. Nikt tego
nie ma, bo wymaga wykrywania wietrzeń — a to już stoi.

Sensowne, gdy uzbiera się kilkanaście epizodów.

## 2. Model cieplny pokój ↔ dwór

**Wymaga 2–4 tygodni danych, najlepiej obejmujących różną pogodę.**

Jak szczyt na dworze przekłada się na szczyt w pokoju i z jakim opóźnieniem.
Wystarczy zależność w rodzaju „sypialnia dochodzi do 0,7 × amplitudy z dworu, trzy
godziny później", dopasowana osobno na pokój — dwa parametry, żadnego uczenia
maszynowego. Wtedy z prognozy 34 °C wychodzi „sypialnia ok. 29 °C ok. 19:00".

Jeden szczegół blokujący: dla pokoju od południa głównym motorem jest
**nasłonecznienie, nie temperatura powietrza**. `shortwave_radiation` zbieramy tylko
w prognozie, która jest nadpisywana co przebieg — historii z tego nie ma. Open-Meteo
ma jednak osobne **API archiwalne (ERA5)**, darmowe i bez klucza, więc stronę „dwór"
da się dociągnąć wstecz w dowolnym momencie, także sprzed startu projektu. Czekać musi
tylko strona „mieszkanie", więc zwlekanie nic nie kosztuje. *(Do zweryfikowania —
sprawdzone z pamięci, nie na żywym API.)*

---

## Przypomnienie

Do obu pozostałych pozycji wracamy **1 września 2026** — tyle mniej więcej potrzeba,
żeby uzbierało się 2–4 tygodnie danych, najlepiej z jakimś chłodniejszym okresem
w środku. Przypomnienie jest ustawione poza repozytorium, więc jeśli przepadnie,
ta sekcja zostaje jako ślad.

## Świadomie odrzucone

| Pomysł | Dlaczego nie |
|---|---|
| Wykrywanie anomalii, cokolwiek „uczącego się" | Przy trzech dobach to generator fałszywych alarmów. Przy roku i czterech czujnikach nadal nie ma czego się uczyć poza rytmem dobowym, który mapa cieplna pokazuje wprost |
| Wykrywanie obecności domowników | Bez czujnika CO₂, z samej wilgotności, to zgadywanka |
| Rekordy i statystyki („najcieplejsza noc") | Tanie, ale po pierwszym obejrzeniu nikt tam nie zagląda |
| Rozbudowa wokół klimatyzatora | Włącznik ma trzy wiersze. Wrócić, gdy urządzenie znów zacznie chodzić |
| Sterowanie urządzeniami ze strony | Tuya ma API do komend, ale strona jest statyczna i nie ma gdzie schować sekretu. Token w przeglądarce albo `workflow_dispatch` z frontendu to klucz do konta Tuya w publicznym kodzie |
| Powiadomienia push | Brak serwera. Rolę powiadomień pełnią zgłoszenia zakładane przez watchdoga — GitHub wysyła o nich maila |

## Zrobione

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
