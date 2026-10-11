# Rośliny — instrukcja dla właściciela

Co zrobić z czujnikami w doniczkach, krok po kroku. Uzasadnienia są w `ROSLINY.md`,
tu są tylko czynności. Kroki oznaczone **„Claude"** robię ja. Po każdym kroku
wystarczy napisać w czacie, co wyszło.

**Gdzie stoją rośliny:**
- fikus — Salon;
- skrzydłokwiat — Salon;
- azalia — Kuchnia.

**Bezpieczeństwo strony:** sparowanie czujników w Smart Life niczego nie zmienia na
obecnej stronie ani w kolektorze. Czujniki trafią do zbierania dopiero w kroku 8,
osobnym torem.

---

## Krok 1. Limit zapytań Tuya — zrobione 8.10

Panel: pakiet 0,20 USD na miesiąc, w październiku zużyte 0,0231 USD, wersja próbna
przedłużona do 13.03.2027. Kolektor pobiera teraz tylko nowe odczyty, ok. 7 zapytań na
przebieg zamiast 29.

**Na przyszłość:** zużycie widać na iot.tuya.com → IoT Core → My Subscriptions.
Ok. 6.03.2027 trzeba złożyć wniosek o kolejne przedłużenie.

---

## Krok 2. Od razu po rozpakowaniu: baterie i oględziny

Zrób to od razu, bo przy zakupie przez internet na zwrot jest 14 dni od dostawy.
Czujnik ma model „C3007", a ta wersja bywa wadliwa: zjada baterie w kilka dni.

1. Podważ i pociągnij głowicę do góry, żeby zdjąć klapkę baterii.
2. Włóż **2 baterie AAA alkaliczne**, plusem zgodnie z oznaczeniem. Akumulatorki
   1,2 V mogą zaniżać wskazanie baterii.
3. Opcjonalnie: jeśli na płytce widać napis (np. „ZSSF01"), zrób zdjęcie.
4. Opcjonalnie: sprawdź końcówkę sondy. Ostrze to zwykła wersja, widełki (dwa ząbki)
   to wersja z pomiarem żyzności.

---

## Krok 3. Parowanie w Smart Life

Każdy czujnik osobno, z telefonem i czujnikiem blisko bramki Zigbee. Nazwy w aplikacji
mogą się nieco różnić.

1. Smart Life → Twoja **bramka Zigbee** („Multi-Mode Gateway") → **Dodaj urządzenie
   podrzędne**.
2. Na czujniku **przytrzymaj przycisk 5 sekund**, aż zacznie migać czerwona dioda.
3. Poczekaj, aż aplikacja znajdzie urządzenie.
4. **Nazwij je dokładnie:** `Fikus` i `Skrzydłokwiat` → pokój **Salon**, `Azalia` →
   pokój **Kuchnia**.
5. Paruj na **swoim** koncie i w tym samym domu co reszta czujników. Tylko to konto
   jest połączone z projektem Tuya.

**W panelu każdego czujnika:**
- Sprawdź, czy widać cztery wartości: wilgotność gleby, temperaturę, wilgotność
  powietrza i światło (lux). Napisz mi, jeśli czegoś brakuje.
- Jeśli jest ustawienie odstępu albo czasu próbkowania („sample time"), ustaw
  **1200 s**. Kolektor i tak zbiera co godzinę, a rzadsze próbkowanie oszczędza
  baterię.
- **Kalibracji nie ruszaj, zostaw 0.** Instrukcja z pudełka wspomina o kalibracji
  w aplikacji, ale chodzi tylko o stałe przesunięcie odczytu gleby. Nasze progi i tak
  liczą się względem odczytów z Twojej doniczki, więc przesunięcie niczego nie
  poprawi, a zmiana w trakcie zostawi w danych fałszywy skok. Ruszymy ją razem tylko
  wtedy, gdy czujnik będzie stał na 100% w podlanej ziemi przez kilka dni.

---

## Krok 4. Test każdego czujnika przed wbiciem (10 minut)

Zapisz liczby — **odczyt „sucho" jest potrzebny do progów podlewania**.

| Test | Jak | Co zapisać |
|---|---|---|
| **sucho** | czujnik czysty i suchy, w powietrzu; krótko naciśnij przycisk (wymusza odczyt) i odczekaj 2 minuty | wilgotność gleby — **zapisz dla każdego czujnika** |
| mokro | **tylko ostrze** do szklanki wody, do 2/3 długości; **głowica ma zostać sucha**; krótkie naciśnięcie, 1 minuta | wilgotność gleby (powinna skoczyć wysoko); wilgotność powietrza ma się prawie nie zmienić |
| światło | zasłoń palcem mały otwór na czole głowicy i naciśnij przycisk; potem odsłoń, skieruj do okna i naciśnij znowu | lux zasłonięty / odsłonięty |

Wytrzyj ostrze do sucha.

**Fikus — jeśli chcesz sprawdzić, czy nie ma lepszego miejsca** (opcjonalnie):
- Fikus źle znosi przestawianie, więc lepiej wybrać miejsce raz, po pomiarze.
- W pochmurny albo pogodny dzień, ale za każdym razem podobny, około południa: postaw
  czujnik pionowo, czołem do okna, w miejscu fikusa i w 1–2 innych jasnych miejscach.
  Na przykład bliżej okna w Salonie albo w Sypialni z dala od kaloryfera.
- W każdym miejscu naciśnij przycisk i odczytaj lux w Smart Life.
- Jeśli inne miejsce jest wyraźnie jaśniejsze (np. 2× więcej lux), przestaw fikusa
  **raz**. Kilka opadłych liści w ciągu 2–4 tygodni to wtedy normalna reakcja.

---

## Krok 5. Wbicie do doniczek

**Zasady wspólne:**
- Wbij na **co najmniej 2/3 długości ostrza** (ok. 5,5 cm), tak żeby płaska część
  pomiarowa przylegała do ziemi.
- **W połowie drogi między pniem a ścianką.** Ostrze nie może dotykać ścianki.
- **Przez** wierzchnią warstwę (mech, kora) do właściwej ziemi.
- Jeśli ziemia jest bardzo sucha, najpierw podlej, potem wbij.
- **Czoło głowicy (otwór światła) zwróć do okna.**
- **Potem nie ruszaj.**
  - Przy podlewaniu lej wodę na ziemię, nie na głowicę.
  - Jeśli wyjmiesz czujnik (np. do zanurzenia azalii), wbij go w to samo miejsce.
  - Jeśli przestawisz doniczkę, napisz mi kiedy.

| Roślina | Gdzie wbić | Na co uważać |
|---|---|---|
| **Fikus** | przez mech, między grubym korzeniem a ścianką | mała doniczka — nie dociskaj do dna |
| **Skrzydłokwiat** | z boku, tam gdzie liście najmniej zasłaniają głowicę | sprawdź, czy doniczka ma zbiorniczek w spodzie, i napisz mi |
| **Azalia** | do **plastikowej doniczki**, nie do osłonki; przez korę do torfu | po każdym podlaniu wylej wodę z osłonki — sonda jej nie widzi |

Po wbiciu krótko naciśnij przycisk i sprawdź w Smart Life, że odczyt gleby się pojawił
(30–60 s).

---

## Krok 6. Napisz mi i obserwuj baterię przez tydzień

**Napisz w czacie:**
- „czujniki sparowane i wbite";
- odczyty z kroku 4 („sucho", „mokro", lux);
- czego brakuje w panelu, jeśli czegoś brakuje.

**Przez pierwszy tydzień raz dziennie zerknij w Smart Life na baterię każdego czujnika.**
Jeśli któraś spadnie do „low" (niski poziom), napisz od razu. To znak wadliwej wersji
i powód do zwrotu w terminie.

**Claude:**
- Porównuję liczbę raportów czujników pokojowych sprzed i po parowaniu. Sprawdzam
  w ten sposób, czy nowe czujniki nie zapychają bramki. Jest to za darmo, z danych
  w repozytorium.
- Rozszerzone „Pokaż urządzenia w Tuya" (ok. 20 zapytań) rusza samo po wdrożeniu
  zmian. Wynik czytam ja.
- Sprawdzam kody, jednostki i to, czy światło i wilgotność powietrza przychodzą.
  Przede wszystkim liczę, **ile wpisów na godzinę robi jeden czujnik**.

---

## Krok 7. Tryb „DP Instruction" w Tuya (na komputerze) — POTRZEBNY

8.10 „Pokaż urządzenia w Tuya" pokazało, że chmura widzi z czujników w doniczkach
tylko glebę, temperaturę i baterię. Światła i wilgotności powietrza nie ma, a bez
światła nie będzie powiadomień „przestaw".

Chmura Tuya ukrywa niestandardowe pola czujnika (światło, wilgotność powietrza),
dopóki produkt jest w trybie „Standard Instruction". Przełącza się go **tylko dla
produktu czujnika roślin**:

1. iot.tuya.com → **Cloud → Development** → projekt **termohigrograf** → zakładka
   **Devices**.
2. **All Devices** → przełącz widok na **View Devices by Product** (urządzenia
   pogrupowane według produktu).
3. Znajdź produkt **土壤温湿度** (identyfikator `0ints6wl`). Są w nim Fikus,
   Skrzydłokwiat i Azalia.
4. Kliknij przy nim **ołówek** („Change Control Instruction Mode") → wybierz
   **DP Instruction** → zapisz.
5. **Nie ruszaj produktu `ZTH02ZTU温湿度传感器` (`9yapgbuv`).** To czujniki pokojowe;
   po przełączeniu zmieniłyby się ich kody i kolektor zgubiłby ich historię.
6. Napisz mi, kiedy to zrobisz. Zmiana działa po kilku–kilkunastu godzinach; potem
   uruchomię odkrywanie jeszcze raz i zobaczę, czy przyszło światło.

Menu może wyglądać trochę inaczej — wtedy wyślij zrzut ekranu zakładki Devices, a
wskażę, gdzie kliknąć. Zmianę da się cofnąć tym samym ołówkiem. Aplikacji Smart Life
to nie dotyczy, to tylko ustawienie dostępu przez API.

---

## Krok 8. Nauka (ok. 2–6 tygodni)

**Claude:** kolektor zaczyna zbierać doniczki osobnym torem, do osobnych plików, bez
dotykania odczytów pokoi. W aplikacji pojawia się zakładka **„Rośliny"** z kartami
roślin i wykresem gleby. Powiadomień jeszcze nie ma.

**Ty w tym czasie:**
- **Podlewaj jak zwykle, wtedy, kiedy sam uznasz.** Z tych chwil biorą się progi.
  Aplikacja wykrywa podlanie sama.
- **Nie ruszaj czujników.**
- Jeśli możesz, zapisuj daty podlewania (np. w notatce). Twoja lista pozwoli
  sprawdzić, czy aplikacja dobrze wykrywa podlania.

Fikus zimą pije rzadko, więc trzy podlania, od których startują progi, mogą zająć
4–6 tygodni.

**Tymczasowe powiadomienie bez kodu (opcjonalnie):**
1. Smart Life → **Inteligentne / Sceny** → **Automatyzacja** → „+".
2. Warunek: „Gdy stan urządzenia się zmieni" → roślina → wilgotność gleby → „<"
   wartość.
3. Akcja: **Wyślij powiadomienie**. Okres działania: dzień.
4. **Wartość** to odczyt gleby z dnia, w którym sam uznasz, że roślinę trzeba podlać.
   Nie zgaduj — poczekaj na pierwsze takie podlanie.

Jeśli Smart Life nie pozwoli wybrać gleby jako warunku albo powiadomienie nie dojdzie
do drugiej osoby w domu, napisz — to jedna z niewiadomych.

---

## Krok 9. Powiadomienia na telefonie — zrobione 9–10.10

Oba telefony są podpięte. Nowa aplikacja (11.10) tego nie zmienia: klucz wysyłki, adres
aplikacji i subskrypcje zostały te same. B albo C powtarzasz tylko na nowym telefonie albo
po usunięciu i ponownym dodaniu ikony — aplikacja sama pokaże wtedy „Subskrypcja się
zmieniła”.

Sekrety dodaje się na stronie github.com, w przeglądarce. Aplikacja GitHub na telefonie
ich nie edytuje; na telefonie otwórz github.com w Chrome/Safari (najlepiej „wersja na
komputer"). Droga do sekretów:
**github.com → Bronek31/Smart-Home → Settings → Secrets and variables → Actions**.
Istniejący sekret: przy nim **Update**; nowy: **New repository secret** (pole *Name*
i pole *Secret*, potem *Add secret*).

**A. Klucz do wysyłki — zrobione 9.10.** Sekret `VAPID_KLUCZ_PRYWATNY`. Przycisk „Utwórz
klucze” pojawia się w aplikacji tylko wtedy, gdy nie ma w niej klucza publicznego, czyli
przy wymianie pary — tę zrobimy razem. **Klucza prywatnego nie wklejaj do czatu.**

**B. Android (Chrome, aplikacja z ekranu początkowego)**
1. Otwórz aplikację **z ikony** → zakładka **Powiadomienia** → grupa **Ten telefon** →
   **Włącz powiadomienia** → **Zezwól**.
2. Pod spodem **Kopiuj** (subskrypcja tego telefonu) → sekret `PUSH_ANDROID` → wklej całość.
3. Żeby powiadomienia nie przychodziły z opóźnieniem: Ustawienia telefonu → Aplikacje →
   Chrome → Bateria → **Bez ograniczeń**.

**C. iPhone (iOS 16.4 lub nowszy)**
1. Aplikacja musi być dodana z **Safari**: Udostępnij → **Do ekranu początkowego**. Na
   iOS 26 zostaw włączone „Otwórz jako aplikację webową".
2. Otwórz ją **z ikony** → **Powiadomienia** → **Ten telefon** → **Włącz powiadomienia** →
   **Pozwalaj**.
3. **Kopiuj** → sekret `PUSH_IPHONE` → wklej całość.
4. Ustawienia → Powiadomienia → Smart Home: włącz baner i ekran blokady.

Kroki z **Kopiuj** zostają na ekranie przez pół godziny od skopiowania — po powrocie z GitHuba
można skopiować jeszcze raz. Gdy powiadomienia już działają, grupy **Ten telefon** nie widać;
wraca sama, kiedy jest coś do zrobienia (subskrypcja się zmieniła, „Powiadomienia nie
dochodzą”, zgoda wyłączona).

**D. Sprawdzenie**
- Napisz w czacie „sekret podmieniony”. Wyślę powiadomienie testowe „Powiadomienia
  działają” na oba telefony — napisz, czy doszło na każdy.
- Sam też możesz je wysłać: github.com → Smart-Home → Actions → **Powiadomienie
  testowe** → Run workflow.

**Co przychodzi** (wysyłka włączona 11.10, na sucho 9–11.10)
- **Dom:** „Przewietrz …” (za wilgotno od 2 godz.), „Przewietrz przed snem” (w nocy grozi
  „za wilgotno”), „Zamknij okno w …?” (po wietrzeniu w pokoju szybko robi się zimno; tylko
  październik–kwiecień), „Czujnik w … milczy” albo słaba bateria w pokoju.
- **Rośliny:** „Podlej: …” (ziemia poniżej progu od 2 godz.; przypomnienie co dobę, azalia
  co 12 godz., najwyżej 3 razy), „Fikus: przestaw bliżej okna” (3 pełne doby za ciemno;
  raz), „Czujnik: …” (cisza, wyjęta sonda, słaba bateria; raz na powód), podsumowanie
  tygodnia w niedzielę o 10:00 — **domyślnie wyłączone**.
- Który telefon co dostaje i kiedy ma ciszę nocną, ustawiasz w aplikacji osobno dla
  każdego (krok 10). Domyślnie wszystko poza podsumowaniem, cisza 21:00–8:00.
- To, co wypadnie w ciszy, przychodzi po jej końcu — o ile nadal jest aktualne.
  „Przewietrz przed snem” i „Zamknij okno?” nie czekają, bo rano nie mają sensu.
- **Brak powiadomień nie znaczy, że wszystko działa.** Podsumowanie tygodnia jest
  wyłączone, więc sygnałem awarii jest mail ze zgłoszeniem „Kolektor stoi” (watchdog co
  6 godz.), na zakładce Dom linia „Ostatnia zbiórka N godz. temu”, a w Powiadomieniach
  lista „Ostatnie” — co i kiedy poszło na który telefon. Podsumowanie możesz włączyć.
- Zakładka sama ostrzeże, gdy subskrypcja się zmieni albo powiadomienia przestaną
  dochodzić; nieudana wysyłka zakłada zgłoszenie z etykietą `powiadomienia`.

---

## Krok 10. Klucz dostępu do ustawień — raz na każdym telefonie

Ustawienia powiadomień (które przychodzą, cisza nocna) leżą w zmiennych repozytorium
`POWIADOMIENIA_ANDROID` i `POWIADOMIENIA_IPHONE`. Zapisuje je sama aplikacja, ale
potrzebuje do tego klucza z jednym uprawnieniem. Bez klucza przełączniki są wygaszone,
a powiadomienia idą według ustawień domyślnych. Wystarczy jeden klucz dla obu telefonów.

**Utwórz klucz** (github.com w przeglądarce, najlepiej na komputerze):
1. Zdjęcie profilu → **Settings** → **Developer settings** → **Personal access tokens** →
   **Fine-grained tokens** → **Generate new token**.
2. *Token name*: np. `Smart Home — ustawienia powiadomień`. *Expiration*: **najdłuższa
   dostępna**. Datę wygaśnięcia od razu wpisz do kalendarza — przed nią trzeba utworzyć
   nowy klucz i wkleić go na obu telefonach (`TODO.md`).
3. *Repository access*: **Only select repositories** → **Smart-Home**.
4. *Permissions* → *Repository permissions* → **Variables: Read and write**. Nic więcej
   nie zaznaczaj (GitHub sam dopisze „Metadata: Read-only” — tak ma być).
5. **Generate token** → skopiuj klucz (zaczyna się od `github_pat_`). GitHub pokazuje go
   tylko raz. **Nie wysyłaj go w czacie.**

**Wklej go na każdym telefonie:** aplikacja → zakładka **Powiadomienia** → pole **Klucz
dostępu** → wklej → **Połącz**. Po chwili przełączniki ożywają, a na dole stoi „Klucz
dostępu · Połączono”.
- **iPhone: wklejaj w aplikacji otwartej z ikony na ekranie początkowym, nie w Safari.**
  Aplikacja z ekranu ma pamięć osobną od Safari — klucza wklejonego w Safari nie zobaczy.
- „Klucz nie działa albo wygasł” — zły albo przeterminowany klucz. „Klucz nie ma
  uprawnienia Variables do Smart-Home” — popraw punkt 3 albo 4. „Brak połączenia” — sieć.
- Skąd wziąć klucz, przypomina też przycisk **Skąd wziąć klucz?** pod polem.

**Potem:**
- Zmiana przełącznika albo godziny działa od następnej zbiórki, najpóźniej za godzinę.
- Przełącznik **Android | iPhone** nad przełącznikami reguł pozwala z jednego telefonu
  zmienić ustawienia drugiego.
- Cisza nocna: **Od** i **Do** muszą się różnić — aplikacja nie przyjmie tej samej godziny,
  bo taka cisza nie trwałaby wcale.
- Klucz zostaje tylko na tym telefonie i ma dostęp wyłącznie do zmiennych repozytorium
  Smart-Home, nie do kodu ani sekretów. **Odłącz** na dole zakładki usuwa go z telefonu.
- Zapisane ustawienia (przełączniki i godziny ciszy) widać w publicznym logu przebiegu
  w Actions. To nie sekret — godziny ciszy i tak da się wyczytać z publicznych plików
  powiadomień — ale wiedz o tym.

---

## Rady już teraz, bez czujników

- **Azalia (Kuchnia):**
  - Jeśli stoi przy płycie albo czajniku — odsuń.
  - **Nigdy nie dopuść do przesuszenia.** Po podlaniu wylewaj wodę z osłonki.
  - Jeśli ziemia zaschnie: **wyjmij czujnik**, wyjmij plastikową doniczkę z osłonki
    i zanurz ją w letniej wodzie, aż przestaną lecieć bąbelki (15–30 min). Przytrzymaj,
    bo sucha ziemia pływa, a pień na paliku przeważa. Odsącz, wylej wodę z osłonki,
    wbij czujnik w to samo miejsce.
  - Kuchnia ma ok. 21 °C dniem i nocą (od 17.09 ani razu nie zeszła do 18 °C),
    a kwitnąca azalia woli 10–18 °C, więc w cieple kwitnie krócej.
  - **Nie zakręcaj dla niej kaloryfera.** Chłodniejsza kuchnia to wyższa wilgotność
    i alarm pleśni na stronie.
  - Usuwaj przekwitłe kwiaty. Nie nawoź w czasie kwitnienia. Nie przesadzaj do
    wiosny.
- **Skrzydłokwiat (Salon):**
  - Obetnij brązowe końcówki liści czystymi nożyczkami, zostawiając cienki brązowy
    pasek. Nie odrosną.
  - Zimą przy suchym powietrzu mogą pojawiać się nowe — to nie błąd podlewania.
  - Nie dopuszczaj do więdnięcia między podlewaniami.
  - Nie zostawiaj wody w podstawce ani w spodzie doniczki.
- **Fikus (Salon):**
  - Zdrowy.
  - Jesienią i po każdym przestawieniu gubi część liści przez 2–4 tygodnie. To nie
    pragnienie: nie podlewaj częściej i nie przestawiaj z powrotem.
  - Przesusz wierzchnie 2–3 cm między podlewaniami.
- **Wszystkie:**
  - Salon i Kuchnia mają okna na północ i do ok. 20 marca nie zobaczą bezpośredniego
    słońca. Im bliżej okna, tym lepiej, ale nie nad kaloryferem.
  - **Nie nawilżaj mieszkania dla roślin** — strona pilnuje progu pleśni. Wystarczy
    trzymać rośliny razem.
  - Co 2 tygodnie obejrzyj spód liści. W suchym, ciepłym powietrzu łatwo o przędziorki
    (azalia, fikus).
  - Do marca bez nawozu; azalia — bez nawozu do końca kwitnienia.

---

## Dostępy — kto co robi

| Co | Claude | Ty |
|---|---|---|
| kod, commity, wypychanie na gałąź roboczą | ✔ | — |
| odczyt przebiegów i logów workflowów | ✔ (sprawdzone, jako Bronek31 przez aplikację GitHub) | — |
| uruchamianie workflowów („Pokaż urządzenia w Tuya", próbne powiadomienie) | ✘ — GitHub odmawia (403). Obejście: „Pokaż urządzenia w Tuya" rusza samo po każdej zmianie swojego pliku na `main` | ręcznie: Actions → workflow → Run workflow |
| scalanie na `main`, czyli wdrożenie strony i kolektora | po Twojej zgodzie | albo Ty |
| sekrety repozytorium (Tuya, powiadomienia) | ✘ — ani odczyt, ani zapis | ✔ |
| klucz dostępu do ustawień (krok 10) i same ustawienia telefonów | ✘ — klucza nie mam i mieć nie powinienem | ✔ w aplikacji, zakładka Powiadomienia |
| panel iot.tuya.com (limit, tryb instrukcji) | ✘ — wymaga logowania | ✔ |
| Smart Life (parowanie, automatyzacje, bateria) | ✘ | ✔ |

**Kluczy Tuya nie trzeba mi dawać.** Workflowy w repozytorium już je mają, a każde moje
zapytanie i tak zjadałoby ten sam limit. **Haseł do Tuya, Smart Life ani GitHuba nie
wysyłaj w czacie.**
