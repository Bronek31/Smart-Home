// Syntetyczne data/ dla testów aplikacji (index.html).
//
// Prawdziwe data/ zmienia się co godzinę, więc testy oparte na nim mogłyby sprawdzać tylko to, że „coś się
// narysowało". Tutaj układamy pliki pod konkretne zjawisko — martwy czujnik, spóźnioną zbiórkę, regułę domu
// w data/dom/stan.json, roślinę do podlania — i dopiero wtedy da się sprawdzić, czy strona pokazuje to, co
// powinna. Znaczniki liczymy względem „teraz", żeby wynik nie zależał od godziny uruchomienia.
//
// Kształty plików jak u kolektora (fetch.py, dom.py, rosliny.py) i jak w kontraktach BRIEF5 (2.2–2.4):
//   data/index.json, data/RRRR-MM.csv (miesiąc wg UTC), data/dzienne.csv (doba warszawska), data/pogoda.json,
//   data/dom/stan.json, data/dom/powiadomienia.json, data/rosliny/stan.json, data/rosliny/powiadomienia.json,
//   pokoje.json (katalog główny).
// Router podstawia je PO ŚCIEŻCE: data/rosliny/2026-10.csv to inny plik niż data/2026-10.csv.

const GODZ = 3600e3;
const DOBA = 24 * GODZ;
const iso = (ms) => new Date(Math.round(ms / 1000) * 1000).toISOString().replace(/\.\d+Z$/, 'Z');
const miesiacUtc = (ms) => iso(ms).slice(0, 7);
const FD = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Warsaw', year: 'numeric', month: '2-digit', day: '2-digit' });
const FG = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
/** data lokalna Warszawy „RRRR-MM-DD" — tak kolektor zapisuje doby w dzienne.csv */
const dataWaw = (ms) => FD.format(new Date(ms));
/** czas lokalny bez strefy „RRRR-MM-DDTHH:MM" — tak Open-Meteo podaje `current.time` */
const czasWaw = (ms) => `${dataWaw(ms)}T${FG.format(new Date(ms))}`;

/* Kolejność jak w manifeście kolektora decyduje o kolorach pokoi; id celowo nie są id Tuya, żeby test nie przeszedł
   przypadkiem na prawdziwym pokoje.json. */
const POKOJE = [
  { id: 'salon', nazwa: 'Salon', baza: 21.0, wilg: 52, konf: { slug: 'salon', dop: 'salonu', bier: 'salon', miejsc: 'salonie', okno: 'pln' } },
  { id: 'sypialnia', nazwa: 'Sypialnia', baza: 21.6, wilg: 48, konf: { slug: 'sypialnia', dop: 'sypialni', bier: 'sypialnię', miejsc: 'sypialni', okno: 'pld' } },
  { id: 'kuchnia', nazwa: 'Kuchnia', baza: 20.6, wilg: 56, konf: { slug: 'kuchnia', dop: 'kuchni', bier: 'kuchnię', miejsc: 'kuchni', okno: 'pln', wywiew: true } },
  { id: 'lazienka', nazwa: 'Łazienka', baza: 22.0, wilg: 58, konf: { slug: 'lazienka', dop: 'łazienki', bier: 'łazienkę', miejsc: 'łazience', wywiew: true } },
];
/* Prawdziwe czujniki raportują każdy w innej minucie godziny. */
const PRZESUNIECIE = { salon: 0, sypialnia: 11 * 60e3, kuchnia: 22 * 60e3, lazienka: 33 * 60e3 };
/* Amplituda rytmu dobowego: mała, żeby pokoje nie wychodziły z pola komfortu tylko przez porę doby. */
const AMPLITUDA = 0.4;

const kodyCzujnika = () => ({
  va_temperature: { kind: 'temp', unit: '℃', scale: 1 },
  va_humidity: { kind: 'hum', unit: '%', scale: 0 },
  battery_state: { kind: 'battery', unit: '%', scale: 0 },
});

/**
 * @param {object} o
 *   dni             ile dób historii odczytów (domyślnie 9: „7 dni" i rytm doby mają pełną treść)
 *   teraz           chwila „teraz" (domyślnie Date.now())
 *   brakManifestu   data/index.json → 404
 *   pusto           manifest bez miesięcy (kolektor jeszcze nic nie zapisał)
 *   bezCzujnikow    manifest bez urządzeń
 *   pustePliki      miesiące są w manifeście, ale CSV mają sam nagłówek
 *   martwy          id pokoju, który milczy od 9 godz.
 *   opoznienieZbiorki  ile godzin temu była ostatnia zbiórka (odczyty kończą się wtedy)
 *   bateria         {pokoj, stan}
 *   wilgotnosc      {pokoj: wartość} — stała wilgotność pokoju przez całą historię
 *   trend           {pokoj: stopnie na dobę} — temperatura rośnie (albo spada) równo, więc kafel ma zmianę w 24 h
 *   nazwaZnacznik   Salon nazywa się w Tuya 'Salon <b>"x"</b>' (i nie ma go w pokoje.json)
 *   pokojeJson      false → brak pliku pokoje.json; tablica id → tylko te pokoje w pliku
 *   pogoda          'pelna' | 'brak' (manifest.weather null) | 'bezPowietrza' (air {}) | 'krotka' (jedna doba)
 *   artefakty       [{czujnik, odGodz, doGodz, wartosc}] — godziny wstecz od teraz; `wartosc` wpisuje do CSV
 *                   absurdalną temperaturę w tym przedziale (to, co artefakt ma ukryć)
 *   zleArtefakty    w manifeście wpisy bez czujnika, ze złą datą i z od ≥ do (kolektor przepisuje ręczny plik)
 *   skok            {pokoj, godzWstecz, o} — jeden odczyt temperatury +o° na 3 min, potem powrót (czujnik w dłoni)
 *   dom             reguły per id pokoju dla data/dom/stan.json (scalane z pustymi), null → brak pliku,
 *                   'zly' → zepsuty JSON; domUpdated — ISO `updated` pliku domu (domyślnie = manifest)
 *   rosliny         null → brak data/rosliny/stan.json, [] → pusta lista; zmianyRoslin {Nazwa: {...pola}}
 *   roslinyGora     pola wierzchu stan.json roślin, np. {blad, updated} — błąd toru zostawia stary `updated`
 *   bezRoslin       nazwy roślin, których nie ma w stan.json (kolektor pominął je po błędzie obliczeń)
 *   stareRosliny    stan.json roślin bez pól z kontraktu 2.3 (sprzed zmiany kolektora)
 *   nazwy           {id: nazwa} — inna nazwa czujnika w Tuya (np. skrót „WC”)
 *   powDom, powRosliny  zawartość plików powiadomień (null → brak pliku)
 */
function zbuduj(o = {}) {
  const teraz = o.teraz || Date.now();
  const dni = o.dni == null ? 9 : o.dni;
  const koniec = teraz - (o.opoznienieZbiorki || 0) * GODZ;
  const start = teraz - dni * DOBA;
  const wiersze = [];
  const push = (t, id, code, value) => { if (t <= koniec && t >= start) wiersze.push(`${iso(t)},${id},${code},${value}`); };
  const godzinaUtc = (t) => new Date(t).getUTCHours();

  // dwór: co godzinę o pełnej, jak Open-Meteo w kolektorze
  const dworT = (t) => 11 + 4 * Math.sin(((godzinaUtc(t) - 9) / 24) * 2 * Math.PI);
  for (let t = Math.ceil(start / GODZ) * GODZ; t <= koniec; t += GODZ) {
    push(t, 'zewnatrz', 'va_temperature', dworT(t).toFixed(1));
    push(t, 'zewnatrz', 'va_humidity', String(Math.round(75 - 10 * Math.sin(((godzinaUtc(t) - 9) / 24) * 2 * Math.PI))));
  }
  const art = (o.artefakty || []).map((a) => ({ ...a, od: teraz - a.odGodz * GODZ, do: teraz - a.doGodz * GODZ }));
  for (const p of POKOJE) {
    for (let t0 = Math.ceil(start / GODZ) * GODZ; t0 <= koniec; t0 += GODZ) {
      const t = t0 + PRZESUNIECIE[p.id];
      if (o.martwy === p.id && t > teraz - 9 * GODZ) continue;
      const temp = p.baza + AMPLITUDA * Math.sin(((godzinaUtc(t) - 4) / 24) * 2 * Math.PI) + (o.trend && o.trend[p.id] ? o.trend[p.id] * (t - teraz) / DOBA : 0);
      const w = o.wilgotnosc && o.wilgotnosc[p.id] != null ? o.wilgotnosc[p.id] : p.wilg;
      const a = art.find((x) => x.czujnik === p.id && t >= x.od && t <= x.do && x.wartosc != null);
      push(t, p.id, 'va_temperature', (a ? a.wartosc : temp).toFixed(1));
      push(t, p.id, 'va_humidity', String(Math.round(w)));
      push(t, p.id, 'battery_state', o.bateria && o.bateria.pokoj === p.id ? o.bateria.stan : 'middle');
    }
  }
  if (o.skok) {
    const p = POKOJE.find((x) => x.id === o.skok.pokoj);
    const t = Math.floor((teraz - o.skok.godzWstecz * GODZ) / GODZ) * GODZ + PRZESUNIECIE[p.id];
    const temp = p.baza + AMPLITUDA * Math.sin(((godzinaUtc(t) - 4) / 24) * 2 * Math.PI);
    // dłoń na czujniku: kilka minut wyżej i z powrotem, gęściej niż raz na godzinę
    push(t + 3 * 60e3, p.id, 'va_temperature', (temp + o.skok.o).toFixed(1));
    push(t + 9 * 60e3, p.id, 'va_temperature', temp.toFixed(1));
  }
  wiersze.sort();
  const miesiace = [...new Set(wiersze.map((w) => w.slice(0, 7)))].sort();

  const urzadzenia = {
    klima: { name: 'FERSK VIND 2', appliance: true, codes: { switch: { kind: 'power', unit: '', scale: 0 } } },
  };
  for (const p of POKOJE) {
    const nazwa = o.nazwy && o.nazwy[p.id] ? o.nazwy[p.id] : o.nazwaZnacznik && p.id === 'salon' ? 'Salon <b>"x"</b>' : p.nazwa;
    urzadzenia[p.id] = { name: nazwa, codes: kodyCzujnika(), pobrane_do: iso(koniec) };
  }
  urzadzenia.zewnatrz = { name: 'Na zewnątrz', external: true,
    codes: { va_temperature: { kind: 'temp', unit: '°C', scale: 0 }, va_humidity: { kind: 'hum', unit: '%', scale: 0 } } };
  const updated = iso(koniec - 60e3);
  const manifest = {
    updated,
    months: o.pusto ? [] : miesiace.length ? miesiace : [miesiacUtc(teraz)],
    daily: 'dzienne.csv',
    weather: o.pogoda === 'brak' ? null : 'pogoda.json',
    alerty: [],
    artefakty: art.map((a) => ({ czujnik: a.czujnik, od: iso(a.od), do: iso(a.do), powod: 'test' })).concat(o.zleArtefakty ? [
      { czujnik: '', od: iso(teraz - 5 * GODZ), do: iso(teraz) },
      { czujnik: 'salon', od: 'zle', do: iso(teraz) },
      { czujnik: 'salon', od: iso(teraz), do: iso(teraz - 5 * GODZ) },
    ] : []),
    devices: o.bezCzujnikow ? {} : urzadzenia,
  };

  // dzienne.csv: doba warszawska, bez baterii i włączników — jak write_daily w fetch.py
  const kubelki = new Map();
  for (const w of wiersze) {
    const [ts, id, code, value] = w.split(',');
    if (code === 'battery_state') continue;
    const klucz = `${dataWaw(Date.parse(ts))}|${id}|${code}`;
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
    'data/index.json': o.brakManifestu ? null : JSON.stringify(manifest, null, 2),
    'data/dzienne.csv': dzienne.join('\n') + '\n',
    'data/pogoda.json': o.pogoda === 'brak' ? null : JSON.stringify(pogoda(teraz, o.pogoda || 'pelna'), null, 2),
  };
  for (const m of miesiace) {
    pliki[`data/${m}.csv`] = 'ts,device_id,code,value\n' + (o.pustePliki ? '' : wiersze.filter((w) => w.startsWith(m)).join('\n') + '\n');
  }
  if (o.pokojeJson !== false) {
    const konf = {};
    for (const p of POKOJE) {
      if (Array.isArray(o.pokojeJson) && o.pokojeJson.indexOf(p.id) < 0) continue;
      if (o.nazwaZnacznik && p.id === 'salon') continue;
      konf[p.id] = { nazwa: p.nazwa, ...p.konf };
    }
    konf.zewnatrz = { slug: 'zewnatrz', nazwa: 'Na zewnątrz' };
    pliki['pokoje.json'] = JSON.stringify({ opis: 'fikstura', pokoje: konf });
  }
  // data/dom/stan.json (kontrakt 2.2): reguły per pokój, puste, chyba że test poda swoje
  if (o.dom !== null) {
    if (o.dom === 'zly') pliki['data/dom/stan.json'] = '{"updated": ';
    else {
      const pokoje = {};
      for (const p of POKOJE) {
        pokoje[p.id] = { przewietrz: null, okno: null, noc: null, milczy_od: null, bateria: 'middle', ...((o.dom || {})[p.id] || {}) };
      }
      pliki['data/dom/stan.json'] = JSON.stringify({ updated: o.domUpdated || updated, pokoje }, null, 1);
    }
  }
  if (o.rosliny !== null) pliki['data/rosliny/stan.json'] = JSON.stringify(stanRoslin(teraz, o), null, 1);
  if (o.powDom) pliki['data/dom/powiadomienia.json'] = JSON.stringify(o.powDom);
  if (o.powRosliny) pliki['data/rosliny/powiadomienia.json'] = JSON.stringify(o.powRosliny);
  return pliki;
}

function pogoda(teraz, wariant) {
  const dni = wariant === 'krotka' ? 1 : 3;
  const snap = {
    updated: iso(teraz),
    current: { time: czasWaw(teraz), interval: 900, temperature_2m: 12.4, relative_humidity_2m: 71, apparent_temperature: 10.6, weather_code: 3, wind_speed_10m: 9.2 },
    daily: {
      time: [0, 1, 2].slice(0, dni).map((i) => dataWaw(teraz + i * DOBA)),
      weather_code: [3, 61, 0].slice(0, dni), temperature_2m_max: [15.2, 13.1, 14.0].slice(0, dni), temperature_2m_min: [8.1, 7.2, 6.4].slice(0, dni),
      precipitation_probability_max: [10, 70, 0].slice(0, dni), precipitation_sum: [0, 3.2, 0].slice(0, dni),
    },
    air: wariant === 'bezPowietrza' ? {} : { time: czasWaw(teraz), interval: 3600, european_aqi: 33, pm2_5: 11.4, pm10: 16.6 },
    gdzie: { lat: 50.26, lon: 19.02 },
  };
  const czas = [], temp = [], rh = [], rad = [];
  const baza = Math.floor(teraz / GODZ) * GODZ - GODZ;
  for (let i = 0; i < 37; i++) {
    const t = baza + i * GODZ;
    czas.push(iso(t)); temp.push(+(11 + 4 * Math.sin(((new Date(t).getUTCHours() - 9) / 24) * 2 * Math.PI)).toFixed(1));
    rh.push(75); rad.push(0);
  }
  snap.hourly = { time: czas, temperature_2m: temp, relative_humidity_2m: rh, shortwave_radiation: rad };
  return snap;
}

/* data/rosliny/stan.json z polami kontraktu 2.3. Zakresy gatunków celowo INNE niż w prototypie (fikus 17–23 °C
   zamiast 16–24): test widzi wtedy, że strona bierze je z pliku, a nie ze stałych w kodzie. */
const ROSLINY = [
  { nazwa: 'Fikus', gatunek: 'fikus', pokoj: 'salon', gleba: 64, prog_gleba: 30, szczyt: 80, R: 0.68, werdykt: 'ok',
    nazwa_pelna: "Fikus 'Ginseng' (Ficus microcarpa)", temp_zakres: [17, 23], wilg_zakres: [40, 70], potrzeba: 20000 },
  { nazwa: 'Skrzydłokwiat', gatunek: 'skrzydlokwiat', pokoj: 'salon', gleba: 58, prog_gleba: 34, szczyt: 57, R: 1.0, werdykt: 'ok',
    nazwa_pelna: 'Skrzydłokwiat (Spathiphyllum)', temp_zakres: [18, 27], wilg_zakres: [50, 80], potrzeba: 10000 },
  { nazwa: 'Azalia', gatunek: 'azalia', pokoj: 'kuchnia', gleba: 52, prog_gleba: 45, szczyt: 60, R: 0.5, werdykt: 'ok',
    nazwa_pelna: 'Azalia doniczkowa (Rhododendron simsii), forma drzewka', temp_zakres: [10, 21], wilg_zakres: [50, 80], potrzeba: 28000 },
];
function stanRoslin(teraz, o) {
  if (Array.isArray(o.rosliny) && !o.rosliny.length) return { updated: iso(teraz), blad: null, alerty: [], rosliny: [], urzadzenia: {}, ...(o.roslinyGora || {}) };
  const od = teraz - 6 * DOBA;
  const s0 = Math.floor(teraz / GODZ) * GODZ - 30 * DOBA;
  const n = 30 * 24 + 1;
  const rosliny = ROSLINY.map((r, k) => {
    const zm = (o.zmianyRoslin || {})[r.nazwa] || {};
    const gleba = [], temp = [], wilg = [], swiatlo = [];
    for (let i = 0; i < n; i++) {
      const t = s0 + i * GODZ;
      const przed = t < od;
      // ziemia schnie po 1 pkt na 4 godz. od wbicia — prognoza podlewania ma z czego liczyć
      gleba.push(przed ? null : +(r.gleba + (teraz - t) / (4 * GODZ)).toFixed(0));
      temp.push(przed ? null : 20.5); wilg.push(przed ? null : 55); swiatlo.push(przed ? null : 300);
    }
    const doby = [];
    for (let i = 29; i >= 0; i--) {
      const data = dataWaw(teraz - i * DOBA), pokrycie = i === 0 ? 0.6 : teraz - i * DOBA < od ? 0 : 1;
      doby.push({ data, lxh: pokrycie ? Math.round(r.potrzeba * 0.7) : 0, pokrycie, szczyt_lx: pokrycie ? 900 : null });
    }
    const pelne = doby.filter((d) => d.pokrycie >= 0.8 && d.data > dataWaw(od) && d.data !== dataWaw(teraz));
    const wpis = {
      czujnik: 'czujnik-' + k, nazwa: r.nazwa, gatunek: r.gatunek, pokoj: r.pokoj, sucho: 10, od: iso(od),
      ostatnie: { gleba: { v: r.gleba, ts: iso(teraz - 20 * 60e3) }, temp: { v: 20.5, ts: iso(teraz - 20 * 60e3) }, wilg: { v: 55, ts: iso(teraz - 20 * 60e3) },
        swiatlo: { v: 300, ts: iso(teraz - 20 * 60e3) }, bateria: { v: 'high' }, alarm: { v: '0' } },
      szereg: { od: iso(s0), krok_min: 60, gleba, temp, wilg, swiatlo },
      swiatlo_dobowe: doby, swiatlo_potrzeba_lxh: r.potrzeba,
      podlania: [{ ts: iso(od + 2 * GODZ), przed: 20, szczyt: 80, liczy: true }],
      szczyt: r.szczyt, punkt_podlewania: null, R: r.R, prog: 0.35, werdykt: r.werdykt, uwagi: [], do_zgloszenia: [], prog_gleba: r.prog_gleba,
    };
    if (!o.stareRosliny) {
      Object.assign(wpis, {
        nazwa_pelna: r.nazwa_pelna, temp_zakres: r.temp_zakres, wilg_zakres: r.wilg_zakres, swiatlo_za_duzo_lx: null,
        swiatlo_pelne_doby: pelne.length, swiatlo_wczoraj_lxh: pelne.length ? pelne[pelne.length - 1].lxh : null,
        swiatlo_szczyt_lx_wczoraj: pelne.length ? 900 : null,
        swiatlo_ocena: pelne.length >= 3 ? { kierunek: 'ok', u: 0.7, doby: pelne.slice(-3).map((d) => d.data), szczyt_lx: 900 } : null,
      });
    }
    return Object.assign(wpis, zm);
  }).filter((r) => (o.bezRoslin || []).indexOf(r.nazwa) < 0);
  return { updated: iso(teraz - 60e3), blad: null, alerty: [], rosliny, urzadzenia: {}, ...(o.roslinyGora || {}) };
}

/** Podstawia pliki pod żądania po ścieżce (data/** i pokoje.json). Zwraca obiekt `pliki` — test może podmienić
 *  w nim plik w trakcie (odświeżanie). Wartość null albo brak klucza → 404; obiekt {status, body, contentType} →
 *  dokładnie taka odpowiedź (503 z Pages, portal Wi-Fi oddający HTML ze statusem 200). */
async function podstaw(page, opcje = {}) {
  const pliki = zbuduj(opcje);
  const odpowiedz = (route) => {
    const sciezka = new URL(route.request().url()).pathname.replace(/^\//, '');
    const tresc = pliki[sciezka];
    if (tresc == null) return route.fulfill({ status: 404, body: '' });
    if (typeof tresc === 'object') return route.fulfill({ status: tresc.status, contentType: tresc.contentType || 'text/plain', body: tresc.body || '' });
    return route.fulfill({ status: 200, contentType: sciezka.endsWith('.json') ? 'application/json' : 'text/csv', body: tresc });
  };
  await page.route('**/data/**', odpowiedz);
  await page.route('**/pokoje.json', odpowiedz);
  return pliki;
}

module.exports = { zbuduj, podstaw, POKOJE, ROSLINY, GODZ, DOBA, iso, dataWaw, czasWaw };
