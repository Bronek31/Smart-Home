/* Dane testowe zakładki „Rośliny": data/rosliny/stan.json w kształcie, jaki zapisuje
   kolektor (fetch.py → rosliny.stan_rosliny), plus manifest mieszkania tylko z nazwami
   pokoi. Czasy liczone od Date.now(), jak w dane.js.

   Osobny plik, a nie dopisek do dane.js: podstaw() z dane.js podmienia data/** po samej
   nazwie pliku, a data/rosliny/2026-10.csv i data/2026-10.csv mają tę samą. */

const GODZ = 3600e3;
const DOBA = 24 * GODZ;
const SALON = 'bf43cf664d6644420axva3';
const KUCHNIA = 'bf5741c97c96fa85b1d7do';

const iso = (t) => new Date(t).toISOString().replace(/\.\d{3}Z$/, 'Z');
const dzien = (t) => {
  const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

/** Szereg godzinowy z 30 dni, jak szereg_godzinowy() w rosliny.py. */
function szereg(teraz, funkcje) {
  const od = teraz - 30 * DOBA;
  const start = od - (od % GODZ);
  const n = Math.floor((teraz - start) / GODZ) + 1;
  const out = { od: iso(start), krok_min: 60 };
  for (const [klucz, f] of Object.entries(funkcje)) {
    out[klucz] = Array.from({ length: n }, (_, i) => f(start + i * GODZ, teraz));
  }
  return out;
}

/** 30 dób światła: ostatnia (dzisiejsza) niepełna. */
function doby(teraz, lxh) {
  return Array.from({ length: 30 }, (_, i) => {
    const t = teraz - (29 - i) * DOBA;
    const dzis = i === 29;
    return { data: dzien(t), lxh: dzis ? Math.round(lxh / 3) : lxh, pokrycie: dzis ? 0.4 : 1 };
  });
}

function ostatnie(teraz, { gleba, temp = 21.4, wilg = 56, swiatlo = 340, bateria = 'high', temu = 12 * 60e3 }) {
  const ts = iso(teraz - temu);
  return {
    gleba: { v: gleba, ts }, temp: { v: temp, ts }, wilg: { v: wilg, ts },
    swiatlo: { v: swiatlo, ts }, bateria: { v: bateria, ts }, alarm: { v: '0', ts },
  };
}

/**
 * @param {object} [opcje]
 * @param {string} [opcje.blad]        stan.blad (błąd toru w kolektorze)
 * @param {number} [opcje.updatedTemu] ile ms temu kolektor zapisał stan (domyślnie 10 min)
 * @param {boolean} [opcje.pusto]      rosliny: []
 * @param {object} [opcje.zmiany]      {Nazwa: {...pola rośliny}} — nadpisuje wybrane pola
 */
function zbudujStan(opcje = {}) {
  const teraz = Date.now();
  const podlanieSkrz = teraz - 6.5 * GODZ;
  const podlanieFikusa = teraz - 6 * GODZ;
  const rosliny = [
    {
      czujnik: 'bfe5bdf2b91c53dfd1eaiy', nazwa: 'Fikus', gatunek: 'fikus', pokoj: SALON,
      sucho: 10, od: iso(teraz - 30 * GODZ),
      ostatnie: ostatnie(teraz, { gleba: 100 }),
      szereg: szereg(teraz, {
        gleba: (t) => (t < teraz - 30 * GODZ ? null : t < podlanieFikusa ? 17 : 100),
        temp: (t) => (t < teraz - 40 * GODZ ? null : 21.5),
        wilg: (t) => (t < teraz - 40 * GODZ ? null : 55),
        swiatlo: (t) => (t < teraz - 40 * GODZ ? null : 300),
      }),
      swiatlo_dobowe: doby(teraz, 16000), swiatlo_potrzeba_lxh: 20000,
      podlania: [{ ts: iso(podlanieFikusa), przed: 17, szczyt: null, liczy: false, pominiete: true }],
      szczyt: null, punkt_podlewania: null, R: null, prog: 0.35, werdykt: 'nauka',
      uwagi: ['Podlanie pominięte w nauce (rosliny.json) — skala przyjdzie z następnego.'],
      do_zgloszenia: [],
    },
    {
      czujnik: 'bfa2be765aa6176805rhly', nazwa: 'Skrzydłokwiat', gatunek: 'skrzydlokwiat', pokoj: SALON,
      sucho: 11, od: iso(teraz - 45 * DOBA),
      ostatnie: ostatnie(teraz, { gleba: 50, temp: 21.0, wilg: 58 }),
      szereg: szereg(teraz, {
        gleba: (t) => (t < podlanieSkrz ? Math.max(20, 57 - (podlanieSkrz - t) / DOBA * 3) : 50),
        temp: () => 21.2, wilg: () => 57, swiatlo: () => 200,
      }),
      swiatlo_dobowe: doby(teraz, 8000), swiatlo_potrzeba_lxh: 10000,
      podlania: [{ ts: iso(podlanieSkrz), przed: 19.5, szczyt: 57, liczy: true }],
      szczyt: 57, punkt_podlewania: null, R: 0.85, prog: 0.5, werdykt: 'ok', uwagi: [], do_zgloszenia: [],
    },
    {
      czujnik: 'bf262a90fc72e1aef65arq', nazwa: 'Azalia', gatunek: 'azalia', pokoj: KUCHNIA,
      sucho: 9, od: iso(teraz - 45 * DOBA),
      ostatnie: ostatnie(teraz, { gleba: 35, temp: 20.4, wilg: 62, swiatlo: 900 }),
      szereg: szereg(teraz, { gleba: () => 35, temp: () => 20.4, wilg: () => 62, swiatlo: () => 600 }),
      swiatlo_dobowe: doby(teraz, 30000), swiatlo_potrzeba_lxh: 28000,
      podlania: [{ ts: iso(teraz - 4 * DOBA), przed: 30, szczyt: 57, liczy: true }],
      szczyt: 57, punkt_podlewania: null, R: 0.55, prog: 0.75, werdykt: 'pilne', uwagi: [], do_zgloszenia: [],
    },
  ];
  for (const r of rosliny) Object.assign(r, (opcje.zmiany || {})[r.nazwa] || {});
  return {
    updated: iso(teraz - (opcje.updatedTemu ?? 10 * 60e3)),
    blad: opcje.blad ?? null,
    alerty: [],
    rosliny: opcje.pusto ? [] : rosliny,
    urzadzenia: {},
  };
}

const MANIFEST_POKOI = { devices: { [SALON]: { name: 'Salon' }, [KUCHNIA]: { name: 'Kuchnia' } } };

/**
 * Podmienia data/** dla strony roślin: data/rosliny/stan.json i data/index.json (nazwy
 * pokoi). Zwraca obiekt `pliki` — test może podmienić w nim stan w trakcie, jak
 * w testach odświeżania strony mieszkania. Klucz `null` to 404.
 */
async function podstawRosliny(page, opcje = {}, { brakStanu = false } = {}) {
  const pliki = {
    'rosliny/stan.json': brakStanu ? null : zbudujStan(opcje),
    'index.json': MANIFEST_POKOI,
  };
  await page.route('**/data/**', (route) => {
    const sciezka = new URL(route.request().url()).pathname.split('/data/').pop();
    const tresc = pliki[sciezka];
    if (tresc == null) return route.fulfill({ status: 404, body: '' });
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(tresc) });
  });
  return pliki;
}

module.exports = { zbudujStan, podstawRosliny, GODZ, DOBA, iso };
