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
 *   wietrzenie     true — doba temu wilgotność w salonie zjeżdża do poziomu dworu
 *   nazwaZnacznik  true — jeden pokój dostaje nazwę z „<” i cudzysłowem
 *   pogodaGodzinowa  'sucho' | 'parno' | 'brak'
 */
function zbuduj(opcje = {}) {
  const {
    dni = 5, pusto = false, trend = null, martwy = null, bateria = null,
    wietrzenie = false, nazwaZnacznik = false, pogodaGodzinowa = 'sucho',
  } = opcje;

  const teraz = Date.now();
  const start = teraz - dni * 24 * GODZ;
  const wiersze = [];
  const push = (t, id, code, value) => wiersze.push(`${iso(t)},${id},${code},${value}`);

  for (const p of POKOJE) {
    for (let t = start; t <= teraz; t += GODZ) {
      const godzina = new Date(t).getUTCHours();
      // dobowy rytm, żeby mapa rytmu i animacja miały co pokazywać
      const temp = p.baza + AMPLITUDA * Math.sin(((godzina - 4) / 24) * 2 * Math.PI);
      let wilg = p.wilg;
      if (wietrzenie && p.id === 'salon' && t > teraz - 25 * GODZ && t < teraz - 21 * GODZ) wilg = 30;
      if (martwy === p.id && t > teraz - 9 * GODZ) continue;
      // przy zadanym trendzie ostatnie godziny pisze osobna pętla niżej; bez tego
      // powstałyby dwa odczyty na ten sam znacznik i regresja liczyłaby się z obu
      if (trend && trend.pokoj === p.id && t > teraz - 5.5 * GODZ) continue;
      push(t, p.id, 'va_temperature', temp.toFixed(1));
      push(t, p.id, 'va_humidity', String(Math.round(wilg)));
      push(t, p.id, 'battery_state', bateria && bateria.pokoj === p.id ? bateria.stan : 'high');
    }
  }
  if (trend) {
    // sześć odczytów co godzinę tuż przed teraz — z nich liczy się nachylenie
    const p = POKOJE.find((x) => x.id === trend.pokoj);
    for (let i = 5; i >= 0; i--) {
      push(teraz - i * GODZ, trend.pokoj, 'va_temperature', (p.baza + trend.tempo * (5 - i)).toFixed(1));
      push(teraz - i * GODZ, trend.pokoj, 'va_humidity', String(p.wilg));
      push(teraz - i * GODZ, trend.pokoj, 'battery_state', 'high');
    }
  }
  for (let t = start; t <= teraz; t += GODZ) {
    const godzina = new Date(t).getUTCHours();
    push(t, 'zewnatrz', 'va_temperature', (18 + 8 * Math.sin(((godzina - 4) / 24) * 2 * Math.PI)).toFixed(1));
    push(t, 'zewnatrz', 'va_humidity', String(Math.round(50 - 15 * Math.sin(((godzina - 4) / 24) * 2 * Math.PI))));
  }
  // włącznik: dwie zmiany stanu, tak jak zapisuje je collapse_power
  push(teraz - 30 * GODZ, 'klima', 'switch', '1');
  push(teraz - 28 * GODZ, 'klima', 'switch', '0');

  wiersze.sort();
  const miesiace = [...new Set(wiersze.map((w) => w.slice(0, 7)))].sort();

  const urzadzenia = {};
  for (const p of POKOJE) {
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
    'pogoda.json': JSON.stringify(pogoda(teraz, pogodaGodzinowa), null, 2),
  };
  for (const m of miesiace) {
    pliki[`${m}.csv`] = 'ts,device_id,code,value\n'
      + wiersze.filter((w) => w.startsWith(m)).join('\n') + '\n';
  }
  return pliki;
}

function pogoda(teraz, wariant) {
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
