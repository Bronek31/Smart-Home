// Zakładka „Rośliny" (rosliny.html) w prawdziwej przeglądarce.
//
// Osobna strona w tym samym zakresie aplikacji co index.html — warunek właściciela z 8.10:
// odczyty z doniczek nie mieszają się ze stroną mieszkania. Strona niczego nie liczy:
// werdykty, skalę i serie bierze z data/rosliny/stan.json, który pisze kolektor, więc
// testy sprawdzają, czy pokazuje je wiernie i czy przeżywa braki.

const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { podstaw } = require('./dane');
const { podstawRosliny, GODZ, iso } = require('./rosliny-dane');

const KORZEN = path.join(__dirname, '..', '..');
const dist = (pakiet, plik) => path.join(__dirname, 'node_modules', pakiet, 'dist', plik);
const CHART = fs.readFileSync(dist('chart.js', 'chart.umd.js'), 'utf8');
const ADAPTER = fs.readFileSync(dist('chartjs-adapter-date-fns', 'chartjs-adapter-date-fns.bundle.js'), 'utf8');

// Te same pomocniki co w strona.spec.js — skopiowane, bo require() pliku z testami
// zarejestrowałby jego testy drugi raz.
function pilnujBledow(page) {
  const bledy = [];
  page.on('pageerror', (e) => bledy.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error' && !/net::ERR|Failed to load resource/.test(m.text())) {
      bledy.push(`console: ${m.text()}`);
    }
  });
  return bledy;
}

async function podepnijChart(page, { cdnDziala = true } = {}) {
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  if (!cdnDziala) return page.route(/cdn\.jsdelivr\.net/, (r) => r.abort());
  await page.route(/cdn\.jsdelivr\.net\/npm\/chart\.js/, (r) =>
    r.fulfill({ contentType: 'application/javascript', body: CHART }));
  await page.route(/cdn\.jsdelivr\.net\/npm\/chartjs-adapter/, (r) =>
    r.fulfill({ contentType: 'application/javascript', body: ADAPTER }));
}

/** Strona roślin gotowa: stempel w nagłówku przestał mówić „wczytywanie". */
async function otworzRosliny(page, opcje = {}, { hash = '', cdnDziala = true, brakStanu = false } = {}) {
  const bledy = pilnujBledow(page);
  await podepnijChart(page, { cdnDziala });
  const pliki = await podstawRosliny(page, opcje, { brakStanu });
  await page.goto(`/rosliny.html${hash}`);
  await page.waitForFunction(
    () => !/wczytywanie/.test(document.getElementById('stamp').textContent), null, { timeout: 20000 });
  return { bledy, pliki };
}

// data doby jak w swiatlo_dobowe (czas lokalny) — przeglądarka i Node mają tę samą strefę
const dzien = (t) => { const d = new Date(t); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
const karta = (page, nazwa) => page.locator(`.karta[data-roslina="${nazwa}"]`);

test.describe('zakładka roślin', () => {
  test('pokazuje karty trzech roślin z werdyktem kolektora', async ({ page }) => {
    const { bledy } = await otworzRosliny(page);
    await expect(page.locator('#app')).toBeVisible();
    await expect(page.locator('#notice')).toBeHidden();
    await expect(page.locator('.karta')).toHaveCount(3);
    await expect(karta(page, 'Azalia')).toHaveAttribute('data-werdykt', 'pilne');
    await expect(karta(page, 'Azalia').locator('.werdykt')).toHaveText('Podlej pilnie — najlepiej zanurz doniczkę');
    await expect(karta(page, 'Skrzydłokwiat').locator('.werdykt')).toHaveText('Gleba w porządku');
    await expect(karta(page, 'Skrzydłokwiat').locator('.opis')).toHaveText('Gleba na 85% skali, podlewanie przy 50%.');
    await expect(karta(page, 'Fikus').locator('.werdykt')).toHaveText('Uczę się');
    await expect(karta(page, 'Fikus').locator('.opis')).toContainText('pominięte w nauce');
    // nazwa pokoju z manifestu mieszkania, tylko jako podpis
    await expect(karta(page, 'Azalia').locator('h2 small')).toHaveText('kuchnia');
    await expect(karta(page, 'Fikus').locator('h2 small')).toHaveText('salon');
    await expect(page.locator('#stamp')).toContainText('stan z');
    await expect(page.locator('#stamp')).not.toHaveClass(/warn-text/);
    expect(bledy).toEqual([]);
  });

  test('pasek gleby stawia znacznik na skali rośliny, a bez skali mówi, czego czeka', async ({ page }) => {
    const { bledy } = await otworzRosliny(page);
    const pozycja = (nazwa, sel) => karta(page, nazwa).locator(sel).evaluate((n) => parseFloat(n.style.left));
    expect(await pozycja('Skrzydłokwiat', '.pasmo-teraz')).toBeCloseTo(85, 5);
    expect(await pozycja('Skrzydłokwiat', '.pasmo-dobrze')).toBeCloseTo(50, 5);
    expect(await pozycja('Azalia', '.pasmo-teraz')).toBeCloseTo(55, 5);
    await expect(karta(page, 'Fikus').locator('.pasmo-teraz')).toHaveCount(0);
    await expect(karta(page, 'Fikus').locator('.pasmo-opis')).toHaveText('skala po pierwszym podlaniu');
    // wartość gleby jak w stan.json, bez zaokrągleń po drodze
    await expect(karta(page, 'Azalia').locator('.gleba .t')).toHaveText('35%');
    expect(bledy).toEqual([]);
  });

  test('karta mówi, kiedy było podlanie i ile światła było wczoraj', async ({ page }) => {
    const { bledy } = await otworzRosliny(page);
    const fakt = (nazwa, tytul) => karta(page, nazwa).locator('.fakty div', { hasText: tytul }).locator('dd');
    await expect(fakt('Fikus', 'Ostatnie podlanie')).toHaveText('6 godz. temu (pominięte w nauce)');
    await expect(fakt('Azalia', 'Ostatnie podlanie')).toHaveText('4 dni temu');
    await expect(fakt('Skrzydłokwiat', 'Światło wczoraj')).toHaveText('8000 lx·h · 80% potrzeby');
    await expect(fakt('Skrzydłokwiat', 'Powietrze')).toHaveText('21,0 °C · 58%');
    await expect(fakt('Skrzydłokwiat', 'Bateria')).toHaveText('dobra');
    await expect(fakt('Skrzydłokwiat', 'Ostatni odczyt')).toHaveText('12 min temu');
    expect(bledy).toEqual([]);
  });

  test('na start wykres pokazuje roślinę, która najbardziej potrzebuje uwagi', async ({ page }) => {
    const { bledy } = await otworzRosliny(page);
    expect(await page.evaluate(() => wybrana)).toBe('Azalia');
    await expect(page.locator('#wybor .range[aria-pressed="true"]')).toHaveText('Azalia');
    const gleba = await page.evaluate(() => {
      const ch = wykresy['wykres-gleba'];
      return { punkty: ch.data.datasets[0].data.length, schodki: ch.data.datasets[0].stepped,
        oczekiwane: stan.rosliny.find((r) => r.nazwa === 'Azalia').szereg.gleba.length };
    });
    expect(gleba.punkty).toBe(gleba.oczekiwane);
    expect(gleba.schodki).toBe(true);      // odczyt trzymany do następnego, bez wygładzania
    expect(bledy).toEqual([]);
  });

  test('przełącznik zmienia wykresy i zapisuje roślinę w adresie', async ({ page }) => {
    const { bledy } = await otworzRosliny(page);
    await page.click('#wybor .range[data-roslina="Skrzydłokwiat"]');
    await expect(page.locator('#wybor .range[aria-pressed="true"]')).toHaveText('Skrzydłokwiat');
    expect(decodeURIComponent(new URL(page.url()).hash)).toBe('#roslina=Skrzydłokwiat');
    const opcje = await page.evaluate(() => {
      const ch = wykresy['wykres-gleba'];
      return { pasmo: ch.options.plugins.pasmo, podlania: ch.options.plugins.podlania.lista.length };
    });
    // pasmo: od progu (11 + 0,5 × (57 − 11) = 34) do poziomu po podlaniu (57)
    expect(opcje.pasmo).toEqual({ dol: 34, gora: 57 });
    expect(opcje.podlania).toBe(1);
    expect(bledy).toEqual([]);
  });

  test('adres z #roslina= otwiera od razu wykres tej rośliny', async ({ page }) => {
    // tędy wejdzie kliknięcie w powiadomienie (etap 4)
    const { bledy } = await otworzRosliny(page, {}, { hash: '#roslina=Fikus' });
    expect(await page.evaluate(() => wybrana)).toBe('Fikus');
    const pasmo = await page.evaluate(() => wykresy['wykres-gleba'].options.plugins.pasmo);
    expect(pasmo).toEqual({ dol: null, gora: null });     // fikus bez skali — bez pasma
    expect(bledy).toEqual([]);
  });

  test('uszkodzony adres nie wywraca strony', async ({ page }) => {
    const { bledy } = await otworzRosliny(page, {}, { hash: '#roslina=%E0%A4' });
    await expect(page.locator('.karta')).toHaveCount(3);
    expect(await page.evaluate(() => wybrana)).toBe('Azalia');
    expect(bledy).toEqual([]);
  });

  test('wykres światła ma słupek na każdą dobę i linię potrzeby rośliny', async ({ page }) => {
    const { bledy } = await otworzRosliny(page, {}, { hash: '#roslina=Skrzydłokwiat' });
    const swiatlo = await page.evaluate(() => {
      const ch = wykresy['wykres-swiatlo'];
      return { slupki: ch.data.labels.length, potrzeba: ch.options.plugins.potrzeba.wartosc,
        barwy: new Set(ch.data.datasets[0].backgroundColor).size };
    });
    expect(swiatlo.slupki).toBe(30);
    expect(swiatlo.potrzeba).toBe(10000);
    expect(swiatlo.barwy).toBe(2);         // dzisiejsza, niepełna doba jest bledsza
    expect(bledy).toEqual([]);
  });

  test('wykres gleby zaczyna się od wbicia sondy, a nie od pustego miesiąca', async ({ page }) => {
    /* 9.10: pierwszy dzień w doniczkach na osi 30 dni był kreską przy prawej krawędzi,
       a odczyty sprzed wbicia (sonda w powietrzu) wyglądały jak gleba. */
    const { bledy } = await otworzRosliny(page, {}, { hash: '#roslina=Fikus' });
    const os = await page.evaluate(() => {
      const ch = wykresy['wykres-gleba'];
      return { min: ch.options.scales.x.min, max: ch.options.scales.x.max };
    });
    expect((os.max - os.min) / GODZ).toBeCloseTo(36, 5);        // od 30 godz. w ziemi → najmniej półtorej doby
    await page.click('#wybor .range[data-roslina="Skrzydłokwiat"]');
    const dlugo = await page.evaluate(() => {
      const ch = wykresy['wykres-gleba'];
      return ch.options.scales.x.min === Date.parse(stan.rosliny.find((r) => r.nazwa === 'Skrzydłokwiat').szereg.od);
    });
    expect(dlugo).toBe(true);                                    // sonda od 45 dni — całe 30 dni
    expect(bledy).toEqual([]);
  });

  test('światło sprzed wbicia sondy się nie liczy, a niepełna doba nie straszy procentem', async ({ page }) => {
    const teraz = Date.now();
    const { bledy } = await otworzRosliny(page, { zmiany: {
      Fikus: { od: iso(teraz - 60e3) },
      Skrzydłokwiat: { swiatlo_dobowe: [
        { data: dzien(teraz - 2 * 24 * GODZ), lxh: 9000, pokrycie: 1 },
        { data: dzien(teraz - 24 * GODZ), lxh: 2500, pokrycie: 0.5 },
        { data: dzien(teraz), lxh: 300, pokrycie: 0.2 }] },
    } }, { hash: '#roslina=Fikus' });
    const fakt = (nazwa) => karta(page, nazwa).locator('.fakty div', { hasText: 'Światło wczoraj' }).locator('dd');
    await expect(fakt('Fikus')).toHaveText('jeszcze bez pełnej doby');
    expect(await page.evaluate(() => wykresy['wykres-swiatlo'].data.labels.length)).toBe(1);   // tylko dziś
    await expect(fakt('Skrzydłokwiat')).toHaveText('2500 lx·h (niepełny pomiar)');
    expect(bledy).toEqual([]);
  });

  test('odświeżenie podmienia karty, gdy kolektor zapisał nowy stan', async ({ page }) => {
    const { bledy, pliki } = await otworzRosliny(page);
    const nowy = JSON.parse(JSON.stringify(pliki['rosliny/stan.json']));
    nowy.updated = new Date(Date.now() - 60e3).toISOString();
    Object.assign(nowy.rosliny.find((r) => r.nazwa === 'Azalia'), { werdykt: 'ok', R: 0.95 });
    pliki['rosliny/stan.json'] = nowy;
    await page.evaluate(() => odswiez());
    await expect(karta(page, 'Azalia')).toHaveAttribute('data-werdykt', 'ok');
    await expect(karta(page, 'Azalia').locator('.werdykt')).toHaveText('Gleba w porządku');
    expect(bledy).toEqual([]);
  });
});

test.describe('zakładka roślin — odporność', () => {
  test('błąd kolektora widać na banerze, a karty zostają', async ({ page }) => {
    const { bledy } = await otworzRosliny(page, { blad: 'Fikus: Tuya odmówiła (1010)' });
    await expect(page.locator('#baner')).toBeVisible();
    await expect(page.locator('#baner')).toContainText('Tuya odmówiła (1010)');
    await expect(page.locator('.karta')).toHaveCount(3);
    expect(bledy).toEqual([]);
  });

  test('stary stan zmienia kolor stempla w nagłówku', async ({ page }) => {
    const { bledy } = await otworzRosliny(page, { updatedTemu: 5 * GODZ });
    await expect(page.locator('#stamp')).toHaveClass(/warn-text/);
    expect(bledy).toEqual([]);
  });

  test('bez stan.json strona mówi, że nie ma jeszcze danych z doniczek', async ({ page }) => {
    const { bledy } = await otworzRosliny(page, {}, { brakStanu: true });
    await expect(page.locator('#notice')).toBeVisible();
    await expect(page.locator('#notice h2')).toHaveText('Nie ma jeszcze danych z doniczek');
    await expect(page.locator('#app')).toBeHidden();
    await expect(page.locator('#stamp')).toHaveText('brak danych');
    expect(bledy).toEqual([]);
  });

  test('pusta lista roślin to komunikat, a nie pusta strona', async ({ page }) => {
    const { bledy } = await otworzRosliny(page, { pusto: true });
    await expect(page.locator('#notice h2')).toHaveText('Brak roślin w konfiguracji');
    expect(bledy).toEqual([]);
  });

  test('bez biblioteki wykresów karty działają, a wykresy mówią dlaczego ich nie ma', async ({ page }) => {
    const { bledy } = await otworzRosliny(page, {}, { cdnDziala: false });
    await expect(page.locator('.karta')).toHaveCount(3);
    await expect(page.locator('.plot-blad')).toHaveCount(2);
    await expect(page.locator('.plot-blad').first()).toContainText('biblioteki wykresów');
    expect(bledy).toEqual([]);
  });

  test('czujnik bez żadnych odczytów nie wywraca strony', async ({ page }) => {
    const { bledy } = await otworzRosliny(page, { zmiany: { Fikus: {
      werdykt: 'czujnik', uwagi: ['Brak jakichkolwiek odczytów.'], ostatnie: {}, podlania: [], swiatlo_dobowe: [],
    } } }, { hash: '#roslina=Fikus' });
    // pusty szereg gleby — wykres ma narysować napis zamiast linii, a nie paść
    await page.evaluate(() => {
      const f = stan.rosliny.find((r) => r.nazwa === 'Fikus');
      f.szereg.gleba = f.szereg.gleba.map(() => null);
      rysujWykresy();
    });
    await expect(karta(page, 'Fikus').locator('.werdykt')).toHaveText('Sprawdź czujnik');
    await expect(karta(page, 'Fikus').locator('.fakty div', { hasText: 'Ostatni odczyt' }).locator('dd')).toHaveText('brak odczytów');
    await expect(karta(page, 'Fikus').locator('.fakty div', { hasText: 'Ostatnie podlanie' }).locator('dd')).toHaveText('nie wykryto');
    expect(bledy).toEqual([]);
  });

  for (const szerokosc of [390, 320]) {
    test(`na telefonie (${szerokosc} px) nic nie wystaje w poziomie`, async ({ page }) => {
      await page.setViewportSize({ width: szerokosc, height: 1400 });
      const { bledy } = await otworzRosliny(page);
      const nadmiar = await page.evaluate(() =>
        document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(nadmiar).toBeLessThanOrEqual(0);
      expect(bledy).toEqual([]);
    });
  }
});

test.describe('pasek zakładek', () => {
  /* Warunek właściciela z 8.10: strona mieszkania dostaje tylko przejście do roślin.
     Żaden odczyt z doniczek nie może tam trafić — nawet zapytaniem w tle. */
  test('strona mieszkania ma pasek zakładek i nie pobiera nic z data/rosliny', async ({ page }) => {
    const bledy = pilnujBledow(page);
    const zapytania = [];
    page.on('request', (r) => zapytania.push(new URL(r.url()).pathname));
    await podepnijChart(page);
    await podstaw(page);
    await page.goto('/index.html');
    await page.waitForFunction(() => !/wczytywanie/.test(document.getElementById('stamp').textContent), null, { timeout: 20000 });
    const linki = await page.$$eval('nav.zakladki a', (a) => a.map((x) => [x.textContent, x.getAttribute('href'), x.getAttribute('aria-current')]));
    expect(linki).toEqual([['Mieszkanie', './', 'page'], ['Rośliny', 'rosliny.html', null]]);
    expect(zapytania.filter((p) => p.includes('/data/rosliny'))).toEqual([]);
    expect(bledy).toEqual([]);
  });

  test('z zakładki roślin wraca się na stronę mieszkania', async ({ page }) => {
    const { bledy } = await otworzRosliny(page);
    const linki = await page.$$eval('nav.zakladki a', (a) => a.map((x) => [x.textContent, x.getAttribute('href'), x.getAttribute('aria-current')]));
    expect(linki).toEqual([['Mieszkanie', './', null], ['Rośliny', 'rosliny.html', 'page']]);
    expect(bledy).toEqual([]);
  });
});

test.describe('zakładka roślin — pliki', () => {
  /* Strażnik, nie test: iPhona w Chromium nie da się udać. rosliny.html musi mieć te same
     znaczniki co index.html, inaczej w zainstalowanej aplikacji nagłówek wejdzie pod
     zegar albo strona otworzy się poza oknem aplikacji. */
  test('rosliny.html ma znaczniki aplikacji i bibliotekę z tego samego adresu (strażnik)', async () => {
    const rosliny = fs.readFileSync(path.join(KORZEN, 'rosliny.html'), 'utf8');
    const index = fs.readFileSync(path.join(KORZEN, 'index.html'), 'utf8');
    expect(rosliny).toMatch(/name="apple-mobile-web-app-status-bar-style" content="black-translucent"/);
    expect(rosliny).toMatch(/name="viewport" content="[^"]*viewport-fit=cover/);
    expect(rosliny).toMatch(/\.sheet\{padding-top:max\(var\(--gap\),env\(safe-area-inset-top\)\)/);
    expect(rosliny).toMatch(/<link rel="manifest" href="manifest.json">/);
    expect(rosliny).toMatch(/navigator\.serviceWorker\.register\('sw\.js'\)/);
    const skrypty = (html) => [...html.matchAll(/<script src="([^"]+)"/g)].map((m) => m[1]);
    expect(skrypty(rosliny)).toEqual(skrypty(index));
  });

  test('service worker trzyma rosliny.html w szkielecie i ma nową wersję', async () => {
    const sw = fs.readFileSync(path.join(KORZEN, 'sw.js'), 'utf8');
    const szkielet = /const SZKIELET = \[([^\]]+)\]/.exec(sw)[1];
    expect(szkielet).toContain("'./rosliny.html'");
    // bez nowej wersji telefony z poprzednim szkieletem nie dociągną nowej strony
    expect(sw).not.toMatch(/WERSJA = 'smart-home-v3'/);
  });
});
