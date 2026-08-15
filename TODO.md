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

## 1. Ekstrapolacja trendu na 2–4 godziny

Regresja liniowa z ostatnich 2–3 godzin, wynik w kaflu pokoju:

> Sypialnia +0,5 °C/godz. — przy tym tempie 28 °C ok. 17:00.

Nie potrzebuje historii, bo liczy się z odczytów, które właśnie przyszły. Uczciwe od
pierwszego dnia. W upale najbardziej praktyczna rzecz, jaką ten dashboard może
powiedzieć, bo mówi, kiedy zamknąć rolety, zanim zrobi się gorąco.

Do przemyślenia: przy stabilnej temperaturze prognoza jest bez treści — lepiej ją
wtedy chować, niż pisać „za 4 godziny bez zmian".

## 2. Mapa cieplna godzina × doba

Wiersze to dni, kolumny godziny, kolor to temperatura. Standardowa odpowiedź na
pytanie „kiedy w tym pokoju jest gorąco" — ma ją Grafana, Home Assistant i każdy
dashboard energetyczny, i nie jest to przypadek: rytm dobowy widać na niej
natychmiast, a wykres liniowy przy dwóch tygodniach zamienia się w kłębek.

Zaleta: **degraduje się łagodnie.** Dziś to trzy wiersze, za miesiąc trzydzieści,
i przez cały ten czas jest czytelna. Liczona wprost z miesięcznych CSV, jedna seria
na pokój, przełącznik temperatura/wilgotność.

## 3. Skutek wietrzenia, nie tylko fakt wietrzenia

Epizody już wykrywamy i rysujemy pasmami. Brakuje domknięcia pętli: **o ile** każde
wietrzenie ścięło wilgotność bezwzględną i **jak długo** efekt się trzymał.

> Wczoraj 6:20 — minus 2,1 g/m³, wróciło po 4 godzinach.

Zero nowych danych, zero nowych zależności. Zamienia detekcję w informację zwrotną:
po tygodniu wiadomo, czy wietrzenia w ogóle coś dają i które pory działają. Nikt tego
nie ma, bo wymaga wykrywania wietrzeń — a to już stoi.

Sensowne, gdy uzbiera się kilkanaście epizodów.

## 4. Model cieplny pokój ↔ dwór

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

## Gdyby animacja nadal była za mało czytelna

Zapasowy pomysł, którego nie wdrożyłem, bo obecna wersja wystarcza: kolorować pokoje
**odchyleniem od średniej mieszkania**, a nie temperaturą bezwzględną. Znika wtedy
wspólny dryf dobowy, który dotyczy wszystkich pokoi naraz, i zostaje sama struktura
przestrzenna — który pokój prowadzi, a który się opóźnia. Kosztem tego, że kolor
przestaje odpowiadać odczytowi, więc musiałby być przełącznikiem, nie zamiennikiem.
