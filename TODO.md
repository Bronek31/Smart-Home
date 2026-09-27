# Do zrobienia

Stan po przeglądzie z 27.09.2026. Trzymam to tutaj, a nie w Issues, bo Issues zajmuje
watchdog — propozycja funkcji obok zgłoszenia „Kolektor stoi" tylko przykrywałaby to drugie.

## Po stronie właściciela

Rzeczy, których nie da się zrobić z repozytorium.

1. **Zewnętrzny zegar dla kolektora.** GitHub od 27.08 odpala harmonogram co 3–5 godz.
   zamiast co godzinę. Przebiegi są zielone i odczyty nie giną (każdy bierze 7 dni
   wstecz), ale strona jest nieświeża, a watchdog potrafi zgłosić fałszywe „Kolektor
   stoi" (tak było 27 i 28.08). Instrukcja krok po kroku: README, „Kolektor co godzinę".
2. **Data wygaśnięcia triala Tuya.** Pierwszy wygasł po miesiącu (12.09), nie po pół
   roku. Sprawdzić na iot.tuya.com, do kiedy działa przedłużenie, i wpisać w kalendarz
   z tygodniem zapasu — zatwierdzenie wniosku trwa 1–2 dni robocze.
3. **(Opcjonalnie) zmierzyć fRsi.** Próg pleśni stoi na liczbie z normy (0,70). Jeden
   czujnik przez dobę w najzimniejszym narożniku ściany zewnętrznej, najlepiej w mroźny
   dzień: `fRsi = (θnarożnik − θdwór) / (θpokój − θdwór)`. Wynik wpisać w `FRSI`
   w `fetch.py` i `index.html` (test pilnuje, żeby się zgadzały).

## Do sprawdzenia po kilku tygodniach grzania

Kaloryfery ruszają 1.10, a farelka w łazience będzie chodzić codziennie. Dwa progi
dobrane są na danych bez ogrzewania — w listopadzie przyłożyć je do nowych danych:

| Próg | Dziś | Co sprawdzić |
|---|---|---|
| `TREND_MAX` (0,7 °C/godz.) | naturalny dryf ≤ 0,5, impulsy ≥ 0,86 | czy poranny rozruch kaloryferów nie przekracza progu — jeśli tak, kafel będzie przy nim milczał |
| `CIEPLO_W_DOMU` (24 °C) | lato 24–26, jesień 19–22 | czy któryś pokój z kaloryferem nie dobija do 24 — wtedy rada wróci do letniej |

## Odłożone

| Pomysł | Dlaczego nie teraz |
|---|---|
| Model cieplny pokój ↔ dwór | Odpowiada na letnie pytanie („sypialnia 29 °C o 19:00"), a z kaloryferami pasywny model przestaje pasować. Dane z sierpnia i września zostają w gicie, stronę „dwór" da się dociągnąć z archiwum Open-Meteo kiedykolwiek. **Wrócić w maju 2027** |
| Odtwarzanie historii na rzucie | Schowane przełącznikiem `ODTWARZANIE`, kod chodzi pod testami. Powrót to zmiana jednej linii |

## Świadomie odrzucone

| Pomysł | Dlaczego nie |
|---|---|
| Wykrywanie anomalii, cokolwiek „uczącego się" | Przy trzech dobach to generator fałszywych alarmów. Przy roku i czterech czujnikach nadal nie ma czego się uczyć poza rytmem dobowym, który mapa cieplna pokazuje wprost |
| Wykrywanie obecności domowników | Bez czujnika CO₂, z samej wilgotności, to zgadywanka |
| Rekordy i statystyki („najcieplejsza noc") | Tanie, ale po pierwszym obejrzeniu nikt tam nie zagląda |
| Rozbudowa wokół klimatyzatora | Włącznik ma trzy wiersze, a pasma jego pracy odeszły razem z wykrywaniem wietrzenia. Wrócić, gdy urządzenie znów zacznie chodzić |
| Sterowanie urządzeniami ze strony | Tuya ma API do komend, ale strona jest statyczna i nie ma gdzie schować sekretu. Token w przeglądarce albo `workflow_dispatch` z frontendu to klucz do konta Tuya w publicznym kodzie |
| Wykrywanie wietrzenia i wszystko, co na nim stoi | Usunięte 27.09. Przy raportach co godzinę nie da się go dostroić; 7 epizodów w 44 dobach, zero od 8.09. Z nim odpadły „skutek wietrzenia" i plik z godzinami otwarcia okien |
| Powiadomienia push | Brak serwera. Rolę powiadomień pełnią zgłoszenia zakładane przez watchdoga — GitHub wysyła o nich maila |

## Zrobione

- **Przegląd z 27.09** — szczegóły i pomiary w `KONTEKST.md`:
  - wykrywanie wietrzenia i pasma klimatyzatora usunięte;
  - farelka przestała być „chwilowym skokiem" (filtr startuje ze spokojnego poziomu),
    kafel trendu milczy przy impulsach, skala rzutu z percentyli godzinowych średnich;
  - status czujników liczony do chwili ostatniej zbiórki, nie do „teraz";
  - rady wietrzenia na sezon grzewczy („krótko i szeroko"), rada o słońcu tylko latem;
  - próg pleśni zależny od pogody (PN-EN ISO 13788) w kolektorze i na stronie,
    wykres wilgotności względnej bez dworu, z linią progu;
  - telefon: pogoda i rada pod kaflami, tabela bez przewijania, diagnostyka zwijana;
  - akcje GitHuba na wersjach z Node 24.
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
