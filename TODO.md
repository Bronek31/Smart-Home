# Do zrobienia

Stan po wdrożeniu nowej aplikacji, 11.10.2026. Trzymam to tutaj, a nie w Issues, bo Issues
zajmuje watchdog — propozycja funkcji obok zgłoszenia „Kolektor stoi" tylko przykrywałaby
to drugie.

## Po stronie właściciela

Zrobione 27.09: zewnętrzny zegar kolektora (cron-job.org, co godzinę) i sprawdzona
data wygaśnięcia triala Tuya. Zostają trzy rzeczy cykliczne, wszystkie w kalendarzu
właściciela:

- **token GitHuba dla cron-job.org** ma datę ważności — przed nią wygenerować nowy
  i podmienić nagłówek `Authorization` (README, „Kolektor co godzinę");
- **klucz dostępu do ustawień powiadomień** (fine-grained, tylko Variables, od 11.10) —
  co roku, przed datą wygaśnięcia wybraną przy tworzeniu, wygenerować nowy
  (`ROSLINY-INSTRUKCJA.md`, krok 10) i wkleić **na obu telefonach**: Powiadomienia →
  Połącz. Datę zapisać w kalendarzu od razu przy tworzeniu;
- **trial IoT Core u Tuya** — przedłużony do 13.03.2027 (panel 8.10); wniosek
  o kolejne przedłużenie z tygodniem zapasu, czyli ok. 6.03.2027.

Gdyby któreś przepadło: pierwsze objawi się powrotem do odczytów co 3–5 godz.,
drugie komunikatem „Klucz nie działa albo wygasł” przy zmianie ustawienia w aplikacji
(powiadomienia dochodzą dalej według ostatnich zapisanych ustawień — kolektor czyta
zmienne w Actions, bez tego klucza), trzecie zgłoszeniem „Kolektor stoi" z kodem
`28841002`.

## W przygotowaniu

**Token Tuya pobierany kilka razy w przebiegu** (9.10) — zwykle 1, ale o 02:01 i 04:01
UTC 3 i 4 razy („w tym o token" w podsumowaniu przebiegu); 8.10 o 17:01 pewnie to samo.
Kilka zapytań na dobę z pakietu — znaleźć, która ścieżka w `Tuya.get()` /
`_refresh_token()` odnawia token bez potrzeby, z testem odrzucającym starą wersję.

## Do sprawdzenia

| Kiedy | Co | Dlaczego |
|---|---|---|
| **ok. 11.11.2026** | trafność „Przewietrz przed snem”: z `data/dom/powiadomienia.json` (wpisy `przed-snem`) i historii gita `data/dom/stan.json` (pole `noc` z przebiegu wysyłki) porównać ostrzeżenia z nocnymi odczytami 23–7 — czy wilgotność przekroczyła granicę ze swojej chwili | pomiar z 11.10 na 14 dobach (prognoza przybliżona zapisanymi godzinami dworu): wpis w 8 wieczorów na 14, a z 18 ostrzeżeń pokój-noc tylko 3 skończyły się przekroczeniem. Zapas 2 pkt zostawiony świadomie: mniejszy gubi prawdziwe noce (przy 1 pkt jedną z 3, przy 0 — dwie). Do decyzji: zostawić, zmniejszyć zapas albo wyłączyć regułę |
| listopad | „Zamknij okno” na danych z kaloryferami: wszystkie epizody z `data/dom/powiadomienia.json` (`okno`) z godzinami, każdy potwierdzić u właściciela | na 14 dobach i całej historii nie ma ani jednego potwierdzonego trafienia — reguła jest ostrożna, ale jej czułości nie znamy. Przy przebiegach co godzinę krótkie wietrzenie (Salon 6.10, ok. 45 min) nie trafia w żaden przebieg |
| wiosna 2027, gdy staną kaloryfery | koniec sezonu grzewczego w `dom.py` (`SEZON_GRZEWCZY`, dziś do kwietnia) | kwiecień to założenie, nie pomiar. Poza sezonem „zamknij okno” milczy, bo latem okno otwiera się po to, żeby schłodzić (Kuchnia 23.08: 6 godz. fałszywego alarmu bez bramki) |

`TREND_MAX` i `CIEPLO_W_DOMU`, które stały tu do sprawdzenia w listopadzie, odeszły
11.10 razem z dawną stroną — nowa aplikacja nie ma ani kafla trendu, ani rady „schłodzi /
osuszy”.

## Odłożone

| Pomysł | Dlaczego nie teraz |
|---|---|
| Model cieplny pokój ↔ dwór | Odpowiada na letnie pytanie („sypialnia 29 °C o 19:00"), a z kaloryferami pasywny model przestaje pasować. Dane z sierpnia i września zostają w gicie, stronę „dwór" da się dociągnąć z archiwum Open-Meteo kiedykolwiek. **Wrócić w maju 2027** |
| Odtwarzanie historii na rzucie | Odeszło 11.10 razem z dawną stroną (rzutu nie ma w nowej aplikacji). Kod jest w historii gita: `git show 6b5c01b:index.html` |
| „Za dużo słońca” dla roślin | Czujnik mierzy 0–10 000 lx, progi z literatury są nieosiągalne. Gałąź „przestaw dalej od okna” jest w kodzie, ale uśpiona (`swiatlo_za_duzo_lx: null`). **Wiosną**, po zmierzeniu, przy ilu lx czujnik się nasyca (`ROSLINY.md`) |

## Świadomie odrzucone

| Pomysł | Dlaczego nie |
|---|---|
| Wykrywanie anomalii, cokolwiek „uczącego się" | Przy trzech dobach to generator fałszywych alarmów. Przy roku i czterech czujnikach nadal nie ma czego się uczyć poza rytmem dobowym, który mapa cieplna pokazuje wprost |
| Wykrywanie obecności domowników | Bez czujnika CO₂, z samej wilgotności, to zgadywanka |
| Rekordy i statystyki („najcieplejsza noc") | Tanie, ale po pierwszym obejrzeniu nikt tam nie zagląda |
| Rozbudowa wokół klimatyzatora | Włącznik ma trzy wiersze, a pasma jego pracy odeszły razem z wykrywaniem wietrzenia. Wrócić, gdy urządzenie znów zacznie chodzić |
| Sterowanie urządzeniami ze strony | Tuya ma API do komend, ale strona jest statyczna i nie ma gdzie schować sekretu. Token w przeglądarce albo `workflow_dispatch` z frontendu to klucz do konta Tuya w publicznym kodzie |
| Wykrywanie wietrzenia i wszystko, co na nim stoi | Usunięte 27.09. Przy raportach co godzinę nie da się go dostroić; 7 epizodów w 44 dobach, zero od 8.09. Z nim odpadły „skutek wietrzenia" i plik z godzinami otwarcia okien |
| Pomiar fRsi czujnikiem w narożniku ściany | Właściciel nie przestawia czujników (27.09). Próg pleśni zostaje na wartości z normy, 0,70 |

## Zrobione

- **Jedna aplikacja** (11.10) — `index.html` z zakładkami Dom · Rośliny · Historia ·
  Powiadomienia zamiast dawnej strony mieszkania i osobnej `rosliny.html` (została jako
  przekierowanie starych adresów). Reguły domu w `dom.py` (przewietrz, przed snem, zamknij
  okno, czujniki w pokojach) z powiadomieniami, ustawienia i cisza nocna osobno dla każdego
  telefonu, zapisywane z aplikacji. Szczegóły w `KONTEKST.md`, sekcja z 11.10.
- **Czujniki w doniczkach i powiadomienia na telefon** (8–11.10) — tor danych roślin,
  zakładka, Web Push na Androida i iPhone'a; wysyłka włączona 11.10. Powiadomienia push
  stały wcześniej w „świadomie odrzuconych” z powodem „brak serwera” — odpadł: nadawcą jest
  przebieg GitHub Actions, a doręcza Web Push. Plan i pomiary w `ROSLINY.md`.
- **Strona sama dociąga świeże dane** (27.09) — przy powrocie do karty i co 10 minut;
  zainstalowana na telefonie nie ma przycisku odświeżania.
- **Znane artefakty** (27.09) — `artefakty.json`; ukryte odczyty mostkowane kropkami.
- **Rzut w trybie „wilgotność a pleśń", kalendarz całej historii** (27.09). Widżety na
  telefon zrobione i wycofane tego samego dnia — strona zainstalowana jako aplikacja
  wystarcza; na iPhonie poprawione miejsce pod paskiem stanu.
- **Strefa komfortu i noce w sypialni** (27.09) — wykres temperatura × wilgotność
  z polem 20–24 °C / 40–60% i procentem czasu w polu dla każdego pokoju; ostatnie 14 nocy
  w sypialni na tle strefy optymalnej do snu 16–19 °C. We wrześniu żadna noc nie zeszła poniżej
  20 °C.
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
