// Syntetyczne data/ dla testów strony.
//
// Prawdziwe data/ zmienia się co godzinę, więc testy oparte na nim mogłyby sprawdzać
// tylko to, że „coś się narysowało". Tutaj układamy dane pod konkretne zjawisko —
// rosnący pokój, wietrzenie, martwy czujnik — i dopiero wtedy da się sprawdzić, czy
// strona wyciąga z nich to, co powinna. Znaczniki są liczone względem teraz, żeby
// wynik nie zależał od tego, o której testy poszły.

const GODZ = 3600e3;

/* Amplituda dobowego rytmu w fiksturze. Musi być na tyle mała, żeby sam rytm nie
   przebił progu TREND_MIN (0,25 °C/godz.), bo inaczej „spokojny pokój" bywa uznawany
   za rosnący i test przechodzi albo nie w zależności od godziny, o której poszedł.
   Maksymalne nachylenie sinusa to A·2π/24, więc przy 0,5 °C wychodzi 0,13 °C/godz. —
   dwukrotny zapas. Przy 1,5 °C było 0,38 i CI wywracało się wieczorem, choć lokalnie
   o trzynastej przechodziło. */
const AMPLITUDA = 0.5;

/* Historia nie może mieć równo `dni × 24 h`. Animacja liczy klatki jako
   floor(rozpiętość / krok), a krok przy pięciu dobach wypada na 60 minut — więc
   przy równej dobie rozpiętość ląduje dokładnie na progu i wynik zależy od tego,
   czy znacznik najstarszego wiersza zaokrąglił się w górę, czy w dół, i ile
   milisekund zajęło wczytanie strony. Raz 119 klatek, raz 120, a test „okno
   odtwarzania nie zależy od zakresu wykresów" widział wtedy zmianę, której
   kliknięcia nie spowodowały. Pół kroku zapasu odsuwa nas od progu o 30 minut
   w obie strony. Cała siatka przesuwa się o te 30 minut, co niczemu nie szkodzi:
   nadal jest jeden odczyt na godzinę zegarową, a wiersze trendu stoją względem
   „teraz", więc nie wpadają na wiersze bazowe. */
const ZAPAS = 30 * 60e3;

/* Prawdziwe czujniki raportują każdy w innej minucie godziny i te minuty dryfują.
   20.08 w widoku „dziś" dawało to starty rozjechane o 46 minut, a końce o 53 — czyli
   po dziesiątej części szerokości wykresu z każdej strony. Fikstura stawiała wszystkie
   pokoje na jednej siatce co do sekundy, więc tego zjawiska nie odtwarzała w ogóle
   i żaden test nie mógł go złapać. */
const PRZESUNIECIE = [0, 11 * 60e3, 22 * 60e3, 33 * 60e3];

/* Jak wygląda wietrzenie w fiksturze.

   Dawna wersja zrzucała wilgotność salonu z 46% na 30%, czyli o ok. 3,6 g/m³
   wilgotności bezwzględnej. Zmierzone na pięciu dobach z mieszkania: żaden pokój nigdy
   nie ruszył tej wartości o więcej niż 0,50 g/m³ w dwie godziny, a Salon o więcej niż
   0,33. Fikstura była więc dziewięć razy poza skalą — przechodziła przy progu 0,7,
   przeszłaby przy 2,0 i przy 3,0, czyli sprawdzała wyłącznie, że kod się wykonuje.

   Tutaj pokój zachowuje się tak, jak przy naprawdę otwartym oknie: co godzinę domyka
   ustalony ułamek różnicy temperatury z dworem. To jest dokładnie ten przypadek,
   którego dawny algorytm — patrzący wyłącznie na wilgotność i wyłącznie na
   bezwzględny skok — wykryć nie mógł. */
/* Przy otwartym oknie spada temperatura, a wilgotność BEZWZGLĘDNA zostaje — bo tak
   właśnie wyglądał 19.08: na dworze 12,8 g/m³, w mieszkaniu 12,8–13,9, czyli okno nie
   miało czego wymieniać w tym kanale, a temperatura spadła o 1,9 °C. Gdyby fikstura
   pozwoliła wilgotności bezwzględnej opaść razem z temperaturą, dawny algorytm wykryłby
   epizod przez sam ten spadek i test niczego by nie dowodził. Trzymamy ją więc stałą,
   podnosząc wilgotność względną dokładnie tyle, ile trzeba. */
const absBez = (temp, rh) => 2.1674 * 6.112 * Math.exp(17.62 * temp / (243.12 + temp)) * rh / (273.15 + temp);
const wilgWzgledna = (absDocelowa, temp) =>
  absDocelowa * (273.15 + temp) / (2.1674 * 6.112 * Math.exp(17.62 * temp / (243.12 + temp)));

const WIETRZ_UDZIAL = 0.35;     // ułamek różnicy z dworem domykany w ciągu godziny
const WIETRZ_GODZIN = 2;
const POWROT_UDZIAL = 0.20;     // po zamknięciu okna pokój wraca do swojego rytmu
const WIETRZ_ROZNICA = [2.5, 7];  // na ile dwór ma być chłodniejszy od pokoju, min i max

/* Upalne popołudnie przy ZAMKNIĘTYCH oknach — epizod, który wykryty być NIE może.

   Odtworzone z 20.08.2026: dwór szedł 19,9 → 29,2 °C, a pokoje przy zamkniętych oknach
   pełzły w górę o niecały stopień przez osiem godzin, bo grzały je ściany i słońce.
   To jest ruch „w stronę dworu" bez żadnej wymiany powietrza — zmierzone λ do 0,18/godz.
   Do tego para z gotowania i prysznica podnosi wilgotność bezwzględną, a na dworze
   w upał jest jej dużo, więc i ten kanał pokazuje zbliżanie. Pierwsza wersja detektora
   narysowała wtedy wietrzenie od 13 do 16 w czterech pokojach naraz. */
const UPAL_UDZIAL = 0.10;      // ułamek różnicy temperatur na godzinę → λ ≈ 0,11, wyraźnie pod progiem 0,20
const UPAL_PARA = 0.45;        // ułamek różnicy wilgotności na godzinę → λ ≈ 0,60, mocno nad progiem
const UPAL_GODZIN = 4;
const UPAL_ROZNICA = [2, 9];   // o ile dwór ma być CIEPLEJSZY od pokoju
/* Zwykły dwór w fiksturze chodzi 10–26 °C, więc nigdy nie jest cieplejszy od pokoju na
   tyle, żeby ściany zdążyły go dogonić — okna upału nie dałoby się w takich danych
   znaleźć. Przy `upalDzien` podnosimy go do 15–33 °C, czyli w falę upałów, w której
   ten projekt wystartował. */
const DWOR_BAZA = { zwykly: 18, upal: 24 };
const DWOR_AMPL = { zwykly: 8, upal: 9 };

/* Czujnik w dłoni — epizod, który wykryty być NIE może.

   Odtworzony z prawdziwego zdarzenia z 19.08.2026: temperatura rośnie o 1,0 °C w ciągu
   dziewięciu minut, wilgotność względna o 5 punktów, po czym wszystko wraca. W
   wilgotności bezwzględnej te dwa umiarkowane skoki mnożą się do 1,8 g/m³ — a powrót
   po takim zaburzeniu idzie w stronę dworu i bez strażnika odbicia wygląda dokładnie
   jak otwarte okno. Dawny algorytm łapał się na to i były to jedyne „wietrzenia",
   jakie kiedykolwiek narysował. */
const REKA = [
  [7 * 60e3, 0.5, 5],
  [9 * 60e3, 1.0, 0],
  [15 * 60e3, 0.5, 0],
  [21 * 60e3, 0.2, 0],
  [27 * 60e3, 0.0, 0],
];

const iso = (ms) => new Date(Math.round(ms / 1000) * 1000).toISOString().replace(/\.\d+Z$/, 'Z');
const miesiac = (ms) => { const d = new Date(ms); return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`; };

const POKOJE = [
  { id: 'salon', nazwa: 'Salon', baza: 24.5, wilg: 46 },
  { id: 'sypialnia', nazwa: 'Sypialnia', baza: 25.2, wilg: 44 },
  { id: 'kuchnia', nazwa: 'Kuchnia', baza: 24.0, wilg: 48 },
  { id: 'lazienka', nazwa: 'Łazienka', baza: 25.6, wilg: 52 },
];

const kodyCzujnika = () => ({
  va_temperature: { kind: 'temp', unit: '℃', scale: 1 },
  va_humidity: { kind: 'hum', unit: '%', scale: 0 },
  battery_state: { kind: 'battery', unit: '%', scale: 0 },
});

/**
 * @param {object} opcje
 *   dni            ile dób historii (domyślnie 5)
 *   pusto          zwróć manifest bez miesięcy — stan „jeszcze nic nie zebrano"
 *   trend          {pokoj, tempo} — ostatnie 5 godzin rośnie o tyle °C/godz.
 *   martwy         id pokoju, który milczy od 9 godzin
 *   bateria        {pokoj, stan}
 *   wietrzenie     true — salon przez 2 godz. dąży do temperatury dworu, jak przy otwartym oknie
 *   rekaNaCzujniku true — salon dostaje krótki, nienaturalny skok „czujnik w dłoni” i powrót
 *   zgubionyRaport true — salon nie wysyła jednego raportu, więc jedna godzina zegarowa zostaje pusta
 *   upalDzien      true — salon powoli ogrzewa się ku cieplejszemu dworowi przy ZAMKNIĘTYCH oknach,
 *                  a para z gotowania podciąga jego wilgotność bezwzględną w stronę dworu
 *   nazwaZnacznik  true — jeden pokój dostaje nazwę z „<” i cudzysłowem
 *   pogodaGodzinowa  'sucho' | 'parno' | 'brak'
 *   bezMiejsca     true — pogoda bez współrzędnych, czyli strona nie ma z czego liczyć łuku doby
 *   waskaWilgotnosc  true — wszystkie pokoje w paśmie kilku punktów, jak w prawdziwym mieszkaniu
 *   przesuniete    true — każdy pokój raportuje w innej minucie godziny, jak prawdziwe czujniki
 */
function zbuduj(opcje = {}) {
  const {
    dni = 5, pusto = false, trend = null, martwy = null, bateria = null,
    wietrzenie = false, rekaNaCzujniku = false, upalDzien = false, zgubionyRaport = false,
    nazwaZnacznik = false,
    pogodaGodzinowa = 'sucho', bezMiejsca = false,
    waskaWilgotnosc = false, przesuniete = false,
  } = opcje;
  /* Prawdziwe pokoje stoją w paśmie kilku punktów wilgotności (46–51), a nie ośmiu.
     Przy tak wąskim zakresie Chart.js dzieli oś na kreski co pół procenta i podpisy
     bez miejsc po przecinku zaczynają się powtarzać: „51 51 50 50 49 49…". */
  const POKOJE_TU = waskaWilgotnosc
    ? POKOJE.map((p, i) => ({ ...p, wilg: 46 + i }))
    : POKOJE;

  const teraz = Date.now();
  const start = teraz - dni * 24 * GODZ - ZAPAS;
  const wiersze = [];
  const push = (t, id, code, value) => wiersze.push(`${iso(t)},${id},${code},${value}`);

  // Dwór idzie pierwszy, bo pokój przy otwartym oknie dąży właśnie do niego.
  const dwor = new Map();
  for (let t = start; t <= teraz; t += GODZ) {
    const faza = ((new Date(t).getUTCHours() - 4) / 24) * 2 * Math.PI;
    const temp = (upalDzien ? DWOR_BAZA.upal : DWOR_BAZA.zwykly)
      + (upalDzien ? DWOR_AMPL.upal : DWOR_AMPL.zwykly) * Math.sin(faza);
    const wilg = Math.round(50 - 15 * Math.sin(faza));
    dwor.set(t, temp);
    push(t, 'zewnatrz', 'va_temperature', temp.toFixed(1));
    push(t, 'zewnatrz', 'va_humidity', String(wilg));
  }

  /* Kiedy w fiksturze otworzyć okno — szukamy w danych, a nie liczymy z zegara.
     Gdyby okno stało na sztywnym przesunięciu od „teraz", to przy uruchomieniu testu
     o niewłaściwej porze doby dwór bywałby cieplejszy od pokoju i wietrzenia nie
     wykryłby żaden algorytm; nocny przebieg z harmonogramu wywracałby się losowo.
     Szukamy więc godziny, od której przez cały epizod dwór jest po właściwej stronie
     pokoju o tyle, żeby wymiana powietrza miała co robić — ale nie o tyle, żeby pokój
     zjechał o kilkanaście stopni.

     Z kilku pasujących okien bierzemy to najpóźniejsze w dobie, i to jest sedno tej
     funkcji, a nie sam warunek na różnicę. Wcześniejsza wersja brała pierwsze napotkane,
     czyli takie, na jakie trafiła siatka — a siatka stoi względem „teraz", więc okno
     wędrowało po dobie razem z godziną uruchomienia testu. 29.08 kosztowało to czerwone
     CI: fałszywe wietrzenie w upalny dzień powstawało wyłącznie przy oknach startujących
     o 8, 9 i 10, więc przez tydzień łapały je tylko przebiegi między 8:30 a 11:30 UTC,
     a pozostałe pięć szóstych doby chodziło na zielono po tym samym, zepsutym kodzie.
     Najpóźniejsze okno jest przy okazji najtrudniejsze: im później się zaczyna, tym
     wyżej dwór zdąży podciągnąć pokój i tym więcej ciepła zostaje w nim na wieczorne
     minięcie się krzywych — czyli dokładnie na moment, w którym detektor się mylił. */
  const oknoORoznicy = (baza, godzin, [min, max], cieplejszy) => {
    const pasuje = (t0) => {
      for (let i = 0; i <= godzin; i++) {
        const roznica = cieplejszy ? dwor.get(t0 + i * GODZ) - baza : baza - dwor.get(t0 + i * GODZ);
        if (!(roznica >= min && roznica <= max)) return false;
      }
      return true;
    };
    let wybrane = null;
    for (let t0 = start; t0 <= teraz - 7 * GODZ; t0 += GODZ) {
      // ostra nierówność: przy równej godzinie zostaje ta wcześniejsza data, żeby po
      // epizodzie zostało w zakresie kilka dób na powrót pokoju do własnego rytmu
      if (pasuje(t0) && (wybrane == null || new Date(t0).getUTCHours() > new Date(wybrane).getUTCHours())) {
        wybrane = t0;
      }
    }
    return wybrane;
  };
  const chlodneOkno = (baza, godzin) => oknoORoznicy(baza, godzin, WIETRZ_ROZNICA, false);

  const oknoWietrzenia = wietrzenie ? chlodneOkno(POKOJE_TU[0].baza, WIETRZ_GODZIN) : null;
  const oknoReki = rekaNaCzujniku ? chlodneOkno(POKOJE_TU[0].baza, 1) : null;
  const oknoUpalu = upalDzien ? oknoORoznicy(POKOJE_TU[0].baza, UPAL_GODZIN, UPAL_ROZNICA, true) : null;
  /* Jeden zgubiony raport w środku historii — nie na brzegu, żeby po obu stronach dziury
     był z czego interpolować, i nie w ostatnich godzinach, żeby nie mylić się z martwym
     czujnikiem. 30 godzin wstecz trafia w środek przedostatniej doby. */
  const zgubiony = zgubionyRaport ? start + Math.round((teraz - 30 * GODZ - start) / GODZ) * GODZ : null;

  for (const p of POKOJE_TU) {
    // o ile pokój jest w tej chwili odsunięty od swojego rytmu przez otwarte okno
    let odchylka = 0, absStart = null, upalStan = null;
    const przesun = przesuniete ? PRZESUNIECIE[POKOJE_TU.indexOf(p) % PRZESUNIECIE.length] : 0;
    for (let tSiatka = start; tSiatka <= teraz; tSiatka += GODZ) {
      const t = tSiatka + przesun;
      if (t > teraz) continue;
      const godzina = new Date(t).getUTCHours();
      // dobowy rytm, żeby mapa rytmu i animacja miały co pokazywać
      const rytm = p.baza + AMPLITUDA * Math.sin(((godzina - 4) / 24) * 2 * Math.PI);
      if (oknoWietrzenia != null && p.id === 'salon'
          && t >= oknoWietrzenia && t <= oknoWietrzenia + WIETRZ_GODZIN * GODZ) {
        odchylka += WIETRZ_UDZIAL * (dwor.get(t) - (rytm + odchylka));
      } else if (oknoUpalu != null && p.id === 'salon'
          && t >= oknoUpalu && t <= oknoUpalu + UPAL_GODZIN * GODZ) {
        // Ściany i słońce: ruch w stronę dworu, ale wolniejszy niż wymiana powietrza.
        // Pokój prowadzi tu własny stan zamiast doliczać odchyłkę do rytmu dobowego —
        // inaczej nachylenie sinusa dodawałoby się do relaksacji i zmierzone λ wychodziło
        // wyżej, niż mówi stała.
        if (upalStan == null) upalStan = rytm;
        upalStan += UPAL_UDZIAL * (dwor.get(t) - upalStan);
        odchylka = upalStan - rytm;
      } else if (odchylka !== 0) {
        odchylka *= 1 - POWROT_UDZIAL;
        if (Math.abs(odchylka) < 0.05) odchylka = 0;
      }
      const temp = rytm + odchylka;
      // dopóki okno nie ruszyło pokoju, wilgotność jest dokładnie taka jak dotąd
      let wilg = odchylka === 0 ? p.wilg : wilgWzgledna(absBez(rytm, p.wilg), temp);
      if (oknoUpalu != null && p.id === 'salon'
          && t >= oknoUpalu && t <= oknoUpalu + UPAL_GODZIN * GODZ) {
        // para z gotowania i prysznica goni wilgotność dworu — bez żadnej wymiany powietrza
        if (absStart == null) absStart = absBez(rytm, p.wilg);
        const kroki = Math.round((t - oknoUpalu) / GODZ);
        const cel = absBez(dwor.get(t), 55);
        wilg = wilgWzgledna(absStart + (cel - absStart) * (1 - (1 - UPAL_PARA) ** kroki), temp);
      }
      if (zgubiony != null && p.id === 'salon' && tSiatka === zgubiony) continue;
      if (martwy === p.id && t > teraz - 9 * GODZ) continue;
      // przy zadanym trendzie ostatnie godziny pisze osobna pętla niżej; bez tego
      // powstałyby dwa odczyty na ten sam znacznik i regresja liczyłaby się z obu
      if (trend && trend.pokoj === p.id && t > teraz - 5.5 * GODZ) continue;
      push(t, p.id, 'va_temperature', temp.toFixed(1));
      push(t, p.id, 'va_humidity', String(Math.round(wilg)));
      push(t, p.id, 'battery_state', bateria && bateria.pokoj === p.id ? bateria.stan : 'high');
      // czujnik w dłoni: kilka odczytów gęściej niż co godzinę, w górę i z powrotem
      if (oknoReki != null && p.id === 'salon' && t === oknoReki) {
        for (const [odstep, dt, dw] of REKA) {
          push(t + odstep, p.id, 'va_temperature', (temp + dt).toFixed(1));
          push(t + odstep, p.id, 'va_humidity', String(Math.round(wilg + dw)));
          push(t + odstep, p.id, 'battery_state', 'high');
        }
      }
    }
  }
  if (trend) {
    // sześć odczytów co godzinę tuż przed teraz — z nich liczy się nachylenie
    const p = POKOJE_TU.find((x) => x.id === trend.pokoj);
    for (let i = 5; i >= 0; i--) {
      push(teraz - i * GODZ, trend.pokoj, 'va_temperature', (p.baza + trend.tempo * (5 - i)).toFixed(1));
      push(teraz - i * GODZ, trend.pokoj, 'va_humidity', String(p.wilg));
      push(teraz - i * GODZ, trend.pokoj, 'battery_state', 'high');
    }
  }
  // włącznik: dwie zmiany stanu, tak jak zapisuje je collapse_power
  push(teraz - 30 * GODZ, 'klima', 'switch', '1');
  push(teraz - 28 * GODZ, 'klima', 'switch', '0');

  wiersze.sort();
  const miesiace = [...new Set(wiersze.map((w) => w.slice(0, 7)))].sort();

  const urzadzenia = {};
  for (const p of POKOJE_TU) {
    urzadzenia[p.id] = {
      name: nazwaZnacznik && p.id === 'salon' ? 'Salon <b>"x"</b>' : p.nazwa,
      codes: kodyCzujnika(),
    };
  }
  urzadzenia.zewnatrz = {
    name: 'Na zewnątrz', external: true,
    codes: { va_temperature: { kind: 'temp', unit: '°C', scale: 0 }, va_humidity: { kind: 'hum', unit: '%', scale: 0 } },
  };
  urzadzenia.klima = {
    name: 'FERSK VIND 2', appliance: true,
    codes: { switch: { kind: 'power', unit: '', scale: 0 } },
  };

  const manifest = {
    updated: iso(teraz - 10 * 60000),
    months: pusto ? [] : miesiace,
    daily: 'dzienne.csv',
    weather: 'pogoda.json',
    alerty: [],
    devices: urzadzenia,
  };

  // agregaty dobowe — potrzebne widokowi „całość"
  const kubelki = new Map();
  for (const w of wiersze) {
    const [t, id, code, value] = w.split(',');
    if (code === 'battery_state' || code === 'switch') continue;
    const klucz = `${t.slice(0, 10)}|${id}|${code}`;
    const b = kubelki.get(klucz) || { n: 0, suma: 0, min: Infinity, max: -Infinity };
    const v = parseFloat(value);
    b.n++; b.suma += v; b.min = Math.min(b.min, v); b.max = Math.max(b.max, v);
    kubelki.set(klucz, b);
  }
  const dzienne = ['date,device_id,code,min,avg,max,n'];
  for (const [klucz, b] of [...kubelki].sort()) {
    const [data, id, code] = klucz.split('|');
    dzienne.push(`${data},${id},${code},${b.min},${(b.suma / b.n).toFixed(2)},${b.max},${b.n}`);
  }

  const pliki = {
    'index.json': JSON.stringify(manifest, null, 2),
    'dzienne.csv': dzienne.join('\n') + '\n',
    'pogoda.json': JSON.stringify(pogoda(teraz, pogodaGodzinowa, bezMiejsca), null, 2),
  };
  for (const m of miesiace) {
    pliki[`${m}.csv`] = 'ts,device_id,code,value\n'
      + wiersze.filter((w) => w.startsWith(m)).join('\n') + '\n';
  }
  return pliki;
}

function pogoda(teraz, wariant, bezMiejsca) {
  const snap = {
    updated: iso(teraz),
    current: { time: iso(teraz), temperature_2m: 21.4, relative_humidity_2m: 47, apparent_temperature: 20.3, weather_code: 0, wind_speed_10m: 6.5 },
    daily: {
      time: [0, 1, 2].map((i) => new Date(teraz + i * 24 * GODZ).toISOString().slice(0, 10)),
      weather_code: [0, 3, 61], temperature_2m_max: [28, 30, 22], temperature_2m_min: [15, 17, 13],
      precipitation_probability_max: [0, 20, 80], precipitation_sum: [0, 0, 5],
    },
    air: { european_aqi: 18, pm2_5: 7, pm10: 12 },
  };
  // Katowice — z tego strona liczy wysokość słońca na łuk doby
  if (!bezMiejsca) snap.gdzie = { lat: 50.2649, lon: 19.0238 };
  if (wariant === 'brak') return snap;
  const czas = [], temp = [], rh = [], rad = [];
  const baza = new Date(teraz); baza.setUTCMinutes(0, 0, 0);
  for (let i = 0; i < 30; i++) {
    const t = baza.getTime() + i * GODZ, g = new Date(t).getUTCHours();
    czas.push(iso(t));
    temp.push(wariant === 'parno' ? 26 : +(14 + 6 * Math.max(0, 1 - Math.abs(g - 14) / 8)).toFixed(1));
    rh.push(wariant === 'parno' ? 95 : 40);
    rad.push(Math.round(Math.max(0, 700 * Math.max(0, 1 - Math.abs(g - 12) / 6))));
  }
  snap.hourly = { time: czas, temperature_2m: temp, relative_humidity_2m: rh, shortwave_radiation: rad };
  return snap;
}

/** Podstawia wygenerowane pliki pod żądania data/… — bez ruszania repozytorium. */
async function podstaw(page, opcje) {
  const pliki = zbuduj(opcje);
  await page.route('**/data/**', (route) => {
    const nazwa = new URL(route.request().url()).pathname.split('/').pop();
    const tresc = pliki[nazwa];
    if (tresc === undefined) return route.fulfill({ status: 404, body: '' });
    return route.fulfill({
      status: 200,
      contentType: nazwa.endsWith('.json') ? 'application/json' : 'text/csv',
      body: tresc,
    });
  });
  return pliki;
}

module.exports = { zbuduj, podstaw, POKOJE };
