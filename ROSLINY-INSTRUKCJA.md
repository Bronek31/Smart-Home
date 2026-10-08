# Rośliny — instrukcja dla właściciela

Co zrobić z czujnikami w doniczkach, krok po kroku. Szczegóły i uzasadnienia są
w `ROSLINY.md`; tu są tylko czynności. Kroki oznaczone **„Claude"** robię ja.
Po każdym etapie wystarczy napisać w czacie, co wyszło.

**Ważne od razu:** do czasu kroku 7 czujniki **nie trafiają** do kolektora
i nie zmieniają niczego na obecnej stronie. Sparowanie ich w Smart Life jest
bezpieczne.

---

## Krok 0. Limit zapytań Tuya (5 minut, najlepiej dziś)

Kolektor zużywa według prognozy ok. 98% miesięcznego limitu wersji próbnej. Trzeba
sprawdzić, ile naprawdę zostało.

1. Zaloguj się na **iot.tuya.com** i otwórz projekt (Cloud → Development → projekt
   Smart Home).
2. Znajdź usługę **IoT Core** i jej zużycie: ile zapytań wykorzystano w tym miesiącu,
   jaki jest limit i kiedy się odnawia.
3. Przejrzyj skrzynkę mailową: Tuya wysyła ostrzeżenia „remaining usage is X%".
4. Napisz mi trzy liczby: **wykorzystane / limit / data odnowienia**.

**Claude:** przerobię kolektor tak, żeby pobierał tylko nowe odczyty. Szacunek to
spadek z ok. 29 do ok. 10 zapytań na przebieg, także z roślinami. To trzeba zrobić
przed dodaniem czujników, ale nie musisz na to czekać z krokami 1–4.

---

## Krok 1. Oględziny przed włożeniem baterii

1. **Końcówka sondy:** ostrze czy widełki (dwa ząbki)? Widełki oznaczają wersję
   z pomiarem żyzności.
2. Zdejmij klapkę baterii (podważ i pociągnij głowicę do góry, jak na rysunku
   w instrukcji). Jeśli na płytce widać napis, np. **„ZSSF01"**, zrób zdjęcie. To
   wersja, przed którą ostrzega Zigbee2MQTT: zjada baterie w kilka dni.
3. Włóż **2 baterie AAA alkaliczne**, plusem zgodnie z oznaczeniem. Akumulatorki
   1,2 V mogą zaniżać wskazanie baterii.

---

## Krok 2. Parowanie w Smart Life

Każdy czujnik osobno, telefon i czujnik blisko bramki Zigbee. Nazwy w aplikacji mogą
się nieco różnić.

1. Smart Life → Twoja **bramka Zigbee** („Multi-Mode Gateway") → **Dodaj urządzenie
   podrzędne**.
2. Na czujniku **przytrzymaj przycisk 5 sekund**, aż zacznie migać czerwona dioda.
3. Poczekaj, aż aplikacja znajdzie urządzenie.
4. **Nazwij je dokładnie:** `Fikus`, `Azalia`, `Skrzydłokwiat`. Pokój: Fikus i
   Skrzydłokwiat → **Salon**, Azalia → **Kuchnia**.
   Z tych nazw korzystają powiadomienia.
5. Paruj na **swoim** koncie i w tym samym domu co reszta czujników. Tylko to konto
   jest połączone z projektem Tuya.
6. Powtórz dla dwóch pozostałych.

**Panel czujnika w Smart Life:**
- Sprawdź, czy widać wszystkie cztery wartości: wilgotność gleby, temperaturę,
  wilgotność powietrza i światło (lux).
- Jeśli jest ustawienie odstępu albo czasu próbkowania (np. „sample time",
  „czas raportowania"), ustaw **1200 s**. Kolektor i tak zbiera co godzinę, a rzadsze
  próbkowanie oszczędza baterię.
- **Kalibracji nie ruszaj, zostaw 0.**
  - Instrukcja z pudełka mówi: „Moisture detection may have some deviations, users
    calibration can be performed on the APP". Ten czujnik ma jedno takie ustawienie,
    przesunięcie wilgotności gleby o −30…+30 punktów (pole 103, `adjust_humidity`).
    Temperatury ani światła nie da się tu kalibrować.
  - Przesunięcie dodaje stałą do każdego odczytu, ale nie poprawia skali. Nasze progi
    i tak liczą się względem „szczytu po podlaniu" w danej doniczce, więc stała
    niczego nie zmienia, a zmiana w trakcie zostawia w danych fałszywy skok.
  - Jedyny powód, żeby ją ruszyć: czujnik stoi na **100%** w podlanej ziemi przez
    kilka dni. Wtedy zdecydujemy razem, a ty zapiszesz, kiedy zmieniłeś.

---

## Krok 3. Szybki test każdego czujnika (5 minut, przed wbiciem)

Zapisz liczby, przydadzą się do ustawienia progów.

| Test | Jak | Co zapisać |
|---|---|---|
| sucho | czujnik w powietrzu, krótko naciśnij przycisk (wymusza odczyt), odczekaj minutę | wilgotność gleby (powinna być blisko 0%) |
| mokro | **tylko ostrze** do szklanki wody, do 2/3 długości; **głowica sucha** | wilgotność gleby (powinna skoczyć wysoko); wilgotność powietrza ma się prawie nie zmienić |
| światło | zasłoń palcem mały otwór na czole głowicy, potem odsłoń i skieruj do okna | lux zasłonięty / odsłonięty |

Jeśli któryś czujnik zachowuje się inaczej niż pozostałe, napisz który. Wytrzyj
ostrze do sucha.

---

## Krok 4. Wbicie do doniczek

Zasady wspólne:
- Wbij na **co najmniej 2/3 długości ostrza**, tak żeby płaska część pomiarowa
  przylegała do ziemi.
- Wbij **w połowie drogi między pniem a ścianką**. Ostrze nie może dotykać ścianki
  doniczki.
- **Przez** wierzchnią warstwę (mech, kora) do właściwej ziemi.
- Jeśli ziemia jest bardzo sucha, najpierw podlej, a dopiero potem wbij.
- **Czoło głowicy (otwór światła) zwróć w stronę okna.**
- **Potem nie ruszaj.** Każde przestawienie czujnika albo doniczki zmienia odczyty.
  Jeśli coś przestawisz, napisz mi kiedy.

| Roślina | Gdzie wbić | Na co uważać |
|---|---|---|
| **Fikus** | przez mech, między grubym korzeniem a ścianką | mała doniczka — nie dociskaj do dna |
| **Azalia** | do **plastikowej doniczki**, nie do osłonki; przez korę | po każdym podlaniu wylej wodę, która zebrała się w osłonce — sonda jej nie widzi |
| **Skrzydłokwiat** | z boku, tam gdzie liście najmniej zasłaniają głowicę | sprawdź, czy doniczka ma zbiorniczek w spodzie (napisz mi) |

Po wbiciu krótko naciśnij przycisk i sprawdź w Smart Life, że odczyt gleby się pojawił
(30–60 s).

---

## Krok 5. Napisz mi i poczekaj dobę

Napisz w czacie: „czujniki sparowane", razem z wynikami z kroków 1 i 3.

**Claude:**
- Uruchomię „Pokaż urządzenia w Tuya" (rozszerzone o liczenie wpisów w logach) i
  przeczytam wynik.
- Sprawdzę kody i jednostki, czy przychodzi światło i wilgotność powietrza, a po
  dobie: **ile wpisów robi jeden czujnik**. To pytanie o zalewanie komunikatami
  i o koszt w limicie Tuya.

Ty nic nie musisz robić, chyba że wyjdzie, że brakuje światła albo wilgotności
powietrza. Wtedy krok 6.

---

## Krok 6. Tylko jeśli poproszę: tryb „DP Instruction" w Tuya

Chmura Tuya potrafi ukrywać niestandardowe pola czujnika (światło, wilgotność
powietrza). Naprawia się to przełączeniem trybu instrukcji **tylko dla produktu
czujnika roślin**:

- iot.tuya.com → projekt → **Devices** → przy czujniku roślin opcja zmiany
  „Control Instruction Mode" → **DP Instruction**.
- Może zadziałać dopiero po kilku, kilkunastu godzinach.
- **Nie przełączaj czujników pokojowych** — kolektor zgubiłby ich historię.

Gdy będzie potrzebne, dam dokładniejsze wskazówki do ekranu, który zobaczysz.

---

## Krok 7. Kolektor i zakładka „Rośliny" (Claude)

- Kolektor zbiera doniczki **osobnym torem**, do osobnych plików, bez dotykania
  odczytów pokoi.
- W aplikacji pojawia się zakładka **„Rośliny"** z kartami roślin i wykresem gleby.
- Pierwsze 1–2 tygodnie to **nauka**: aplikacja pokazuje odczyty i uczy się, ile
  pokazuje gleba zaraz po podlaniu i kiedy sam podlewasz.

**Ty w tym czasie:**
- **Podlewaj jak zwykle, wtedy, kiedy sam uznasz.** To z tych chwil biorą się progi.
- Jeśli możesz, zapisuj daty podlewania (np. w notatce). Aplikacja wykrywa podlanie
  sama, ale twoja lista pozwoli sprawdzić, czy wykrywa dobrze.

**Tymczasowe powiadomienie bez kodu (opcjonalnie, od razu po kroku 4):**
1. Smart Life → **Inteligentne / Sceny** → **Automatyzacja** → „+".
2. Warunek: „Gdy stan urządzenia się zmieni" → np. Azalia → wilgotność gleby → „<"
   wartość.
3. Akcja: **Wyślij powiadomienie**.
4. Okres działania: dzień.
5. Wartość progu ustalimy razem po kilku dniach odczytów. Na start możesz dać
   Azalia 40%, Skrzydłokwiat 30%, Fikus 20% — to zgadywanie, nie pomiar.

---

## Krok 8. Powiadomienia w aplikacji

Gdy zakładka będzie działać, dam dokładną listę. W skrócie:

**Android (Chrome, aplikacja już zainstalowana):**
1. Otwórz aplikację → zakładka **Rośliny** → **Włącz powiadomienia** → Zezwól.
2. **Kopiuj** → wklej jako sekret w repozytorium (github.com → Smart-Home → Settings
   → Secrets and variables → Actions → New repository secret; nazwę podam).
3. Jeśli powiadomienia przychodzą z opóźnieniem: Ustawienia telefonu → Aplikacje →
   Chrome → Bateria → **bez ograniczeń**.

**iPhone (iOS 16.4 lub nowszy):**
1. W **Safari** otwórz stronę → Udostępnij → **Do ekranu początkowego**.
2. Otwórz aplikację **z ikony** → Rośliny → **Włącz powiadomienia** → Pozwalaj.
3. **Kopiuj** → drugi sekret.
4. Po usunięciu i ponownym dodaniu ikony trzeba to powtórzyć.

**Klucz do wysyłki** wygenerujesz jednym przyciskiem i wkleisz od razu jako sekret.
**Nigdy nie wklejaj sekretów do czatu.**

Przez pierwszy tydzień powiadomienia lecą „na sucho": widać je na zakładce, ale na
telefon jeszcze nie idą. Potem włączamy wysyłkę, a automatyzację Smart Life można
wyłączyć.

---

## Co możesz zrobić już teraz, bez czujników

- **Azalia:**
  - Kuchnia ma ok. 21 °C dniem i nocą (przez ostatnie 3 tygodnie ani razu nie zeszła
    do 18 °C), a kwitnąca azalia woli 10–18 °C. W ciepłym
    pokoju kwitnie krócej.
  - Najchłodniejsze jasne miejsce bez słońca, z dala od kaloryfera.
  - **Nigdy nie dopuść do przesuszenia.** Jeśli ziemia zaschnie, zanurz plastikową
    doniczkę na ok. 15 minut w letniej wodzie i odsącz.
- **Skrzydłokwiat:**
  - Obetnij brązowe końcówki liści czystymi nożyczkami. Nie odrosną.
  - Nie dopuszczaj do więdnięcia między podlewaniami.
  - Nie zostawiaj wody w podstawce.
- **Fikus:**
  - Zdrowy.
  - **Nie przestawiaj go bez potrzeby** — fikusy gubią liście po zmianie miejsca.
    Jeśli ma zmienić miejsce na jaśniejsze, to raz i na stałe, a nie kilka razy.
  - Kilka opadłych liści po przestawieniu to normalna reakcja.
- **Wszystkie trzy:**
  - Salon i Kuchnia mają okna na północ. Do ok. 20 marca nie zobaczą
    bezpośredniego słońca.
  - Im bliżej okna, tym lepiej, ale nie nad kaloryferem.
  - Zimą bez nawozu i z mniejszą ilością wody (poza azalią).

---

## Dostępy — kto co robi

| Co | Claude | Ty |
|---|---|---|
| kod, commity, wypychanie na gałąź roboczą | ✔ | — |
| uruchamianie workflowów i czytanie ich logów (w tym „Pokaż urządzenia w Tuya") | ✔ (przez aplikację GitHub, jako Bronek31) | — |
| scalanie na `main` (wdrożenie strony i kolektora) | po Twojej zgodzie | albo Ty |
| sekrety repozytorium (Tuya, powiadomienia) | ✘ — ani odczyt, ani zapis | ✔ |
| panel iot.tuya.com (limit, tryb instrukcji) | ✘ — wymaga logowania | ✔ |
| Smart Life (parowanie, automatyzacje) | ✘ | ✔ |

Kluczy Tuya nie trzeba mi dawać bezpośrednio. Workflowy w repozytorium już je mają,
a każde moje zapytanie i tak zjadałoby ten sam limit.
