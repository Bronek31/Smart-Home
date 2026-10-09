// Zakładka „Rośliny" (rosliny.html) w prawdziwej przeglądarce.
//
// Osobna strona w tym samym zakresie aplikacji co index.html — warunek właściciela z 8.10:
// odczyty z doniczek nie mieszają się ze stroną mieszkania. Strona niczego nie liczy:
// werdykty, skalę i serie bierze z data/rosliny/stan.json, który pisze kolektor, więc
// testy sprawdzają, czy pokazuje je wiernie i czy przeżywa braki.

const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { podstaw } = require('./dane');
const { podstawRosliny, GODZ, DOBA, iso } = require('./rosliny-dane');

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
    await expect(karta(page, 'Azalia').locator('.werdykt')).toHaveText('Podlej pilnie');
    // rada przychodzi z Pythona razem z krokiem „wyjmij czujnik", którego strona sama nie znała
    await expect(karta(page, 'Azalia').locator('.opis')).toContainText('Wyjmij czujnik');
    await expect(karta(page, 'Skrzydłokwiat').locator('.werdykt')).toHaveText('Gleba w porządku');
    // próg w tych samych procentach co odczyt obok (50%), a nie w „% skali"
    await expect(karta(page, 'Skrzydłokwiat').locator('.opis')).toHaveText('Podlewaj, gdy gleba spadnie do ok. 34%.');
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
    await expect(karta(page, 'Fikus').locator('.pasmo-opis')).toHaveText('skala jeszcze nieznana');
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
    // pasmo: od progu z Pythona (prog_gleba 34) do poziomu po podlaniu (57)
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

  test('odczyty sprzed wbicia sondy nie trafiają na wykres gleby', async ({ page }) => {
    /* 9.10: przez pierwsze półtorej doby oś sięgała przed wbicie i sonda w powietrzu
       (ok. 10%) rysowała się jak zupełnie sucha ziemia. */
    const { bledy } = await otworzRosliny(page, {}, { hash: '#roslina=Fikus' });
    const przed = await page.evaluate(() => {
      const od = Date.parse(stan.rosliny.find((r) => r.nazwa === 'Fikus').od);
      return wykresy['wykres-gleba'].data.datasets[0].data.filter((p) => p.x < od && p.y != null).length;
    });
    expect(przed).toBe(0);
    expect(bledy).toEqual([]);
  });

  test('przełącznik zostawia fokus na klikniętym przycisku', async ({ page }) => {
    const { bledy } = await otworzRosliny(page);
    await page.focus('#wybor .range[data-roslina="Fikus"]');
    await page.keyboard.press('Enter');
    expect(await page.evaluate(() => document.activeElement?.dataset?.roslina)).toBe('Fikus');
    await expect(page.locator('#wybor .range[aria-pressed="true"]')).toHaveText('Fikus');
    expect(bledy).toEqual([]);
  });

  test('adres z #roslina= obrysowuje kartę tej rośliny', async ({ page }) => {
    const { bledy } = await otworzRosliny(page, {}, { hash: '#roslina=Skrzyd%C5%82okwiat' });
    await expect(karta(page, 'Skrzydłokwiat')).toHaveClass(/wskazana/);
    await expect(page.locator('.karta.wskazana')).toHaveCount(1);
    expect(bledy).toEqual([]);
  });

  test('odczyt sprzed dwóch godzin nie jest jeszcze spóźniony — ten sam próg co nagłówek', async ({ page }) => {
    const teraz = Date.now();
    const ts = iso(teraz - 135 * 60e3);
    const { bledy } = await otworzRosliny(page, { zmiany: { Skrzydłokwiat: { ostatnie: {
      gleba: { v: 50, ts }, temp: { v: 21, ts }, wilg: { v: 58, ts }, bateria: { v: 'high', ts } } } } });
    const dd = karta(page, 'Skrzydłokwiat').locator('.fakty div', { hasText: 'Ostatni odczyt' }).locator('dd');
    await expect(dd).toHaveText('2 godz. temu');
    await expect(dd).not.toHaveClass(/warn-text/);
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

  test('błąd kolektora pojawia się po odświeżeniu, choć czas stanu się nie zmienił', async ({ page }) => {
    /* blad_toru_roslin() zostawia poprzedni stan razem z `updated` i dopisuje tylko błąd —
       dawniej otwarta strona porównywała samo `updated` i baner widać było dopiero po
       przeładowaniu. */
    const { bledy, pliki } = await otworzRosliny(page);
    await expect(page.locator('#baner')).toBeHidden();
    pliki['rosliny/stan.json'] = { ...pliki['rosliny/stan.json'], blad: 'PrzekroczonyCzas: przekroczony limit 300 s' };
    await page.evaluate(() => odswiez());
    await expect(page.locator('#baner')).toContainText('PrzekroczonyCzas');
    expect(bledy).toEqual([]);
  });

  test('odświeżenie z pustą listą roślin mówi to samo co świeże wczytanie', async ({ page }) => {
    const { bledy, pliki } = await otworzRosliny(page);
    pliki['rosliny/stan.json'] = { updated: new Date().toISOString(), blad: 'Fikus: Tuya odmówiła (1010)', alerty: [], rosliny: [], urzadzenia: {} };
    await page.evaluate(() => odswiez());
    await expect(page.locator('#notice h2')).toHaveText('Kolektor nie policzył stanu roślin');
    await expect(page.locator('#app')).toBeHidden();
    expect(bledy).toEqual([]);
  });

  test('bez internetu strona mówi o braku połączenia, a nie o kolektorze', async ({ page }) => {
    const bledy = pilnujBledow(page);
    await podepnijChart(page);
    await page.route('**/data/**', (r) => r.abort('internetdisconnected'));
    await page.goto('/rosliny.html');
    await page.waitForFunction(() => !/wczytywanie/.test(document.getElementById('stamp').textContent), null, { timeout: 20000 });
    await expect(page.locator('#notice h2')).toHaveText('Brak połączenia');
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
    // napisy rysowane na płótnie wykresów — inaczej nie da się sprawdzić komunikatu „brak odczytów"
    await page.addInitScript(() => {
      window.napisy = [];
      const zwykly = CanvasRenderingContext2D.prototype.fillText;
      CanvasRenderingContext2D.prototype.fillText = function (tekst, ...reszta) { window.napisy.push(tekst); return zwykly.call(this, tekst, ...reszta); };
    });
    const { bledy } = await otworzRosliny(page, { zmiany: { Fikus: {
      werdykt: 'czujnik', uwagi: ['Brak jakichkolwiek odczytów.'], ostatnie: {}, podlania: [], swiatlo_dobowe: [],
    } } }, { hash: '#roslina=Fikus' });
    // pusty szereg gleby — wykres ma narysować napis zamiast linii, a nie paść
    await page.evaluate(() => {
      const f = stan.rosliny.find((r) => r.nazwa === 'Fikus');
      f.szereg.gleba = f.szereg.gleba.map(() => null);
      rysujWykresy();
    });
    // pusty szereg to {x, y:null} co godzinę — dawniej wtyczka brała to za dane i nie pisała nic
    expect(await page.evaluate(() => napisy.includes('Brak odczytów gleby w ostatnich 30 dniach'))).toBe(true);
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
    // szkielet z sieci, nie z pamięci HTTP — inaczej nowa wersja mogła zapisać stary index.html
    expect(sw).toMatch(/new Request\(u, \{ cache: 'reload' \}\)/);
  });
});

/* --- Powiadomienia (etap 4) ---

   Telefonu w Chromium nie ma, więc Notification, PushManager, schowek i service worker
   strony są atrapami (addInitScript), które zapisują wywołania. Prawdziwe zostają
   WebCrypto (klucze), IndexedDB i Cache API — przez nie strona rozmawia z sw.js. Obsługi
   z sw.js idą dwiema drogami: prawdziwy worker z pushem przez CDP oraz ten sam plik
   w zwykłej stronie z atrapą `self` — kliknięcia w powiadomienie nie da się w Chromium
   wywołać inaczej. */

const SW = fs.readFileSync(path.join(KORZEN, 'sw.js'), 'utf8');
const ROSLINY_HTML = fs.readFileSync(path.join(KORZEN, 'rosliny.html'), 'utf8');
const PUSTY_KLUCZ = "const VAPID_PUBLICZNY='';";
const ANDROID = 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36';
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';

/** Klucz publiczny prawdziwej pary P-256 z Node, w postaci stałej w stronie (65 B, base64url). */
function kluczPubliczny() {
  const ecdh = crypto.createECDH('prime256v1');
  ecdh.generateKeys();
  return ecdh.getPublicKey('base64url');
}

/**
 * Atrapy API powiadomień. Subskrypcja atrapy przeżywa przeładowanie (localStorage), jak
 * prawdziwa; stan początkowy wchodzi tylko przy pierwszym wczytaniu karty.
 * @param {object} u
 * @param {string} [u.ua]               navigator.userAgent
 * @param {boolean} [u.standalone]      aplikacja otwarta z ekranu początkowego (iPhone)
 * @param {boolean} [u.bezPush]         bez PushManager (iPhone w Safari)
 * @param {boolean} [u.bezApi]          bez Notification, PushManager i service workera (komputer)
 * @param {string} [u.zgoda]            Notification.permission na start
 * @param {string} [u.odpowiedz]        co odpowie requestPermission()
 * @param {string} [u.subskrypcja]      adres subskrypcji, którą telefon już ma
 * @param {string} [u.kluczSubskrypcji] jej applicationServerKey (base64url); brak — nieznany
 * @param {string} [u.nowa]             adres, który da subscribe()
 * @param {object} [u.zapamietana]      {endpoint, od} skopiowanej kiedyś subskrypcji
 */
async function atrapyPowiadomien(page, u = {}) {
  await page.addInitScript((u) => {
    const log = window.atrapa = { zgody: 0, subskrypcje: [], wypisania: 0, schowek: [] };
    if (!sessionStorage.getItem('atrapa-start')) {
      sessionStorage.setItem('atrapa-start', '1');
      if (u.zapamietana) localStorage.setItem('rosliny-subskrypcja', JSON.stringify(u.zapamietana));
      if (u.subskrypcja) localStorage.setItem('atrapa-subskrypcja', JSON.stringify({ e: u.subskrypcja, k: u.kluczSubskrypcji || null }));
    }
    if (u.ua) {
      Object.defineProperty(navigator, 'userAgent', { get: () => u.ua });
      Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
    }
    if (u.standalone) Object.defineProperty(navigator, 'standalone', { get: () => true });
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async (t) => { log.schowek.push(t); } } });
    if (u.bezApi) {
      delete window.Notification; delete window.PushManager;
      delete Navigator.prototype.serviceWorker;
      return;
    }
    const b64 = (b) => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
    const z64 = (s) => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4)), (c) => c.charCodeAt(0));
    const subskrypcja = ({ e, k }) => ({
      endpoint: e,
      options: { userVisibleOnly: true, applicationServerKey: k ? z64(k).buffer : null },
      toJSON: () => ({ endpoint: e, expirationTime: null, keys: { p256dh: 'BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM', auth: 'tBHItJI5svbpez7KI4CCXg' } }),
      unsubscribe: async () => { log.wypisania++; localStorage.removeItem('atrapa-subskrypcja'); return true; },
    });
    const pushManager = {
      getSubscription: async () => { const s = JSON.parse(localStorage.getItem('atrapa-subskrypcja')); return s ? subskrypcja(s) : null; },
      subscribe: async (o) => {
        const s = { e: u.nowa, k: b64(o.applicationServerKey) };
        log.subskrypcje.push({ userVisibleOnly: o.userVisibleOnly, klucz: s.k });
        localStorage.setItem('atrapa-subskrypcja', JSON.stringify(s));
        return subskrypcja(s);
      },
    };
    const reg = { scope: location.origin + '/', pushManager };
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: {
      getRegistration: async () => reg, register: async () => reg, ready: Promise.resolve(reg), addEventListener() {} } });
    if (u.bezPush) delete window.PushManager;
    else if (!window.PushManager) window.PushManager = function PushManager() {};
    let zgoda = u.zgoda || 'default';
    window.Notification = class Notification {
      static get permission() { return zgoda; }
      static async requestPermission() { log.zgody++; zgoda = u.odpowiedz || 'granted'; return zgoda; }
    };
  }, u);
}

/** Zakładka z (opcjonalnie) kluczem VAPID w stałej, plikiem powiadomień i atrapami. */
async function otworzPowiadomienia(page, { klucz = null, powiadomienia, atrapy = {} } = {}) {
  const bledy = pilnujBledow(page);
  await podepnijChart(page);
  const pliki = await podstawRosliny(page);
  if (powiadomienia !== undefined) pliki['rosliny/powiadomienia.json'] = powiadomienia;
  if (klucz) {
    await page.route('**/rosliny.html', (r) => r.fulfill({ contentType: 'text/html; charset=utf-8',
      body: ROSLINY_HTML.replace(PUSTY_KLUCZ, `const VAPID_PUBLICZNY='${klucz}';`) }));
  }
  await atrapyPowiadomien(page, atrapy);
  await page.goto('/rosliny.html');
  await czekajNaTelefon(page);
  return { bledy, pliki };
}
const czekajNaTelefon = (page) => page.waitForFunction(
  () => document.getElementById('pow-telefon')?.dataset.stan, null, { timeout: 20000 });

const plikPowiadomien = (historia, tryb = 'wlaczone') =>
  ({ tryb, wlaczone_od: null, historia, stan_regul: {}, podsumowanie_ostatnie: null });
const wpis = (id, temu, { na_sucho = false, tytul = 'Podlej: azalia' } = {}) => ({
  id, ts: iso(Date.now() - temu), przebieg: '123-1', regula: 'podlej', rosliny: ['Azalia'], tytul,
  tresc: 'Azalia: gleba 41% (podlewaj przy ok. 45%).', tag: 'podlej', url: 'rosliny.html#roslina=Azalia', na_sucho });

const nadmiarPoziomy = (page) => page.evaluate(() =>
  document.documentElement.scrollWidth - document.documentElement.clientWidth);

/** Pusta strona w zakresie aplikacji — ma prawdziwe Cache API i IndexedDB tego originu. */
async function stronaProby(page) {
  await page.route('**/proba-sw.html', (r) => r.fulfill({ contentType: 'text/html; charset=utf-8',
    body: '<!doctype html><meta charset="utf-8"><title>sw.js</title>' }));
  await page.goto('/proba-sw.html');
}

/* sw.js wykonany w stronie z atrapą `self`: registration i clients zapisują wywołania,
   a Cache API i IndexedDB są prawdziwe. Zwraca też trzy funkcje z pliku. Funkcja leci
   do przeglądarki przez toString — nie może sięgać do niczego spoza siebie. */
function zaladujSw([zrodlo, { okna = [], bezIndexedDB = false, zakres = location.origin + '/' } = {}]) {
  const obslugi = {};
  const log = window.log = { pokazane: [], otwarte: [], nawigacje: [], fokusy: 0, zamkniete: 0 };
  const okienka = okna.map((o) => ({
    url: o.url,
    focus: async () => { log.fokusy++; },
    navigate: async (u) => { if (o.niesterowane) throw new TypeError('okno bez tego workera'); log.nawigacje.push(u); return null; },
  }));
  const atrapaSelf = {
    addEventListener: (typ, f) => { obslugi[typ] = f; },
    registration: { scope: zakres, showNotification: async (t, o) => { log.pokazane.push([t, o]); } },
    clients: { matchAll: async () => okienka, openWindow: async (u) => { log.otwarte.push(u); return null; }, claim: async () => {} },
    skipWaiting: async () => {},
  };
  const idb = bezIndexedDB ? { open() { throw new Error('IndexedDB wyłączone'); } } : indexedDB;
  const funkcje = new Function('self', 'indexedDB', `${zrodlo}\nreturn { trescPush, celKlikniecia, zapiszOdebrane };`)(atrapaSelf, idb);
  const zdarzenie = (pola) => { const czekaj = []; return Object.assign(pola, { waitUntil: (p) => czekaj.push(p), czekaj }); };
  window.sw = {
    ...funkcje,
    async push(tekst) { const e = zdarzenie({ data: tekst == null ? null : { text: () => tekst } }); obslugi.push(e); await Promise.all(e.czekaj); },
    async klik(data) { const e = zdarzenie({ notification: { data, close: () => { log.zamkniete++; } } }); obslugi.notificationclick(e); await Promise.all(e.czekaj); },
    async aktywuj() { const e = zdarzenie({}); obslugi.activate(e); await Promise.all(e.czekaj); },
  };
}

const odebraneWStronie = (page) => page.evaluate(() => new Promise((ok, zle) => {
  const z = indexedDB.open('rosliny', 1);
  z.onupgradeneeded = () => z.result.createObjectStore('odebrane', { keyPath: 'id' });
  z.onerror = () => zle(z.error);
  z.onsuccess = () => { const q = z.result.transaction('odebrane').objectStore('odebrane').getAllKeys(); q.onsuccess = () => { z.result.close(); ok(q.result); }; };
}));
const celWCache = (page) => page.evaluate(async () => {
  const r = await caches.match('./cel', { cacheName: 'cel-powiadomienia' });
  return r ? r.json() : null;
});

test.describe('powiadomienia', () => {
  test('stała VAPID_PUBLICZNY ma postać, którą czyta nadawca (strażnik)', async () => {
    /* Strażnik, nie test zachowania: wyslij.py wyciąga klucz z rosliny.html wyrażeniem
       regularnym i porównuje z kluczem wyliczonym z sekretu. Inny zapis (cudzysłów,
       spacje, drugie przypisanie) i nadawca nie znajdzie klucza albo weźmie zły. */
    const trafienia = [...ROSLINY_HTML.matchAll(/const VAPID_PUBLICZNY='([^']*)';/g)];
    expect(trafienia).toHaveLength(1);
    expect(trafienia[0][1]).toMatch(/^(|B[A-Za-z0-9_-]{86})$/);
    expect(ROSLINY_HTML.match(/VAPID_PUBLICZNY\s*=/g)).toHaveLength(1);
  });

  test('klucze: para z przeglądarki w postaci dla nadawcy, a prywatny nigdzie nie zostaje', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 1400 });
    const { bledy } = await otworzPowiadomienia(page);
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'klucze');
    await expect(page.locator('#pow-klucze-wynik')).toBeHidden();
    await page.locator('#pow-klucze summary').click();
    await page.getByRole('button', { name: 'Utwórz klucze' }).click();
    await expect(page.locator('#pow-klucze-wynik')).toBeVisible();
    const prywatny = await page.locator('#pow-prywatny').inputValue();
    const publiczny = await page.locator('#pow-publiczny').inputValue();
    expect(prywatny).toMatch(/^[A-Za-z0-9_-]{43}$/);              // 32 B, JWK `d`
    expect(publiczny).toMatch(/^B[A-Za-z0-9_-]{86}$/);            // 65 B, 0x04‖x‖y
    // Niezależnie od WebCrypto: z samego prywatnego (tylko on idzie do sekretu) Node
    // wylicza ten sam publiczny — to samo porównanie robi nadawca ze stałą w stronie.
    const ecdh = crypto.createECDH('prime256v1');
    ecdh.setPrivateKey(Buffer.from(prywatny, 'base64url'));
    expect(ecdh.getPublicKey('base64url')).toBe(publiczny);
    // ...i para wraca do WebCrypto: podpis prywatnym sprawdza się publicznym
    const surowy = Buffer.from(publiczny, 'base64url');
    const zgodne = await page.evaluate(async ([jwk, raw]) => {
      const alg = { name: 'ECDSA', namedCurve: 'P-256' }, podpisAlg = { name: 'ECDSA', hash: 'SHA-256' };
      const kPryw = await crypto.subtle.importKey('jwk', jwk, alg, false, ['sign']);
      const kPubl = await crypto.subtle.importKey('raw', new Uint8Array(raw), alg, false, ['verify']);
      const dane = new TextEncoder().encode('Podlej: azalia');
      return crypto.subtle.verify(podpisAlg, kPubl, await crypto.subtle.sign(podpisAlg, kPryw, dane), dane);
    }, [{ kty: 'EC', crv: 'P-256', d: prywatny, x: surowy.subarray(1, 33).toString('base64url'),
      y: surowy.subarray(33).toString('base64url') }, [...surowy]]);
    expect(zgodne).toBe(true);
    await page.locator('button[data-pole="pow-prywatny"]').click();
    await expect(page.locator('button[data-pole="pow-prywatny"]')).toHaveText('Skopiowano');
    expect(await page.evaluate(() => window.atrapa.schowek)).toEqual([prywatny]);
    await expect(page.locator('#pow-telefon')).toContainText('VAPID_KLUCZ_PRYWATNY');
    await expect(page.locator('#pow-telefon')).toContainText('nie wysyłaj go do czatu');
    // druga para po cichu podmieniłaby pierwszą, już wklejoną do sekretu
    await expect(page.getByRole('button', { name: 'Utwórz klucze' })).toBeHidden();
    const pamiec = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }) + document.cookie);
    expect(pamiec).not.toContain(prywatny);
    expect(await nadmiarPoziomy(page)).toBeLessThanOrEqual(0);
    expect(bledy).toEqual([]);
  });

  test('włączenie na Androidzie: zgoda, subskrypcja z kluczem ze strony, JSON do PUSH_ANDROID i zapamiętany adres', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 1400 });
    const klucz = kluczPubliczny();
    const adres = 'https://fcm.googleapis.com/fcm/send/abc123';
    const { bledy } = await otworzPowiadomienia(page, { klucz, atrapy: { ua: ANDROID, nowa: adres } });
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'wylaczone');
    await page.getByRole('button', { name: 'Włącz powiadomienia na tym telefonie' }).click();
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'subskrypcja');
    const log = await page.evaluate(() => window.atrapa);
    expect(log.zgody).toBe(1);
    expect(log.subskrypcje).toEqual([{ userVisibleOnly: true, klucz }]);    // klucz ze stałej, bajt w bajt
    const tekst = await page.locator('#pow-subskrypcja').inputValue();
    const json = JSON.parse(tekst);
    expect(json.endpoint).toBe(adres);
    expect(Object.keys(json.keys).sort()).toEqual(['auth', 'p256dh']);
    await expect(page.locator('#pow-telefon')).toContainText('PUSH_ANDROID');
    await expect(page.locator('#pow-telefon')).not.toContainText('PUSH_IPHONE');
    // samo włączenie to jeszcze nie sekret — zapamiętuje dopiero „Kopiuj"
    expect(await page.evaluate(() => localStorage.getItem('rosliny-subskrypcja'))).toBeNull();
    await page.locator('#pow-telefon button[data-akcja="kopiuj"]').click();
    await expect(page.locator('#pow-telefon button[data-akcja="kopiuj"]')).toHaveText('Skopiowano');
    expect(await page.evaluate(() => window.atrapa.schowek)).toEqual([tekst]);
    const zapamietana = JSON.parse(await page.evaluate(() => localStorage.getItem('rosliny-subskrypcja')));
    expect(zapamietana.endpoint).toBe(adres);
    expect(await nadmiarPoziomy(page)).toBeLessThanOrEqual(0);
    // następne wejście: ta sama subskrypcja co w sekrecie → „włączone", bez ostrzeżeń
    await page.reload();
    await czekajNaTelefon(page);
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'wlaczone');
    await expect(page.locator('#pow-dochodza')).toBeHidden();
    expect(bledy).toEqual([]);
  });

  for (const [opis, subskrypcja, oczekiwany] of [
    ['inna niż skopiowana', 'https://fcm.googleapis.com/fcm/send/nowy', 'https://fcm.googleapis.com/fcm/send/nowy'],
    ['zniknęła', null, 'https://fcm.googleapis.com/fcm/send/nowszy'],
  ]) {
    test(`subskrypcja ${opis} → „włącz ponownie i podmień sekret"`, async ({ page }) => {
      const { bledy } = await otworzPowiadomienia(page, { klucz: kluczPubliczny(), atrapy: { ua: ANDROID, zgoda: 'granted', subskrypcja,
        nowa: 'https://fcm.googleapis.com/fcm/send/nowszy',
        zapamietana: { endpoint: 'https://fcm.googleapis.com/fcm/send/stary', od: Date.now() - 5 * DOBA } } });
      await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'zmieniona');
      await expect(page.locator('#pow-telefon')).toContainText('Subskrypcja się zmieniła — włącz ponownie i podmień sekret PUSH_ANDROID');
      await page.getByRole('button', { name: 'Włącz powiadomienia na tym telefonie' }).click();
      await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'subskrypcja');
      expect(JSON.parse(await page.locator('#pow-subskrypcja').inputValue()).endpoint).toBe(oczekiwany);
      expect(bledy).toEqual([]);
    });
  }

  test('subskrypcja ze starym kluczem (po wymianie pary) jest zastępowana nową', async ({ page }) => {
    const klucz = kluczPubliczny(), stary = kluczPubliczny();
    const adres = 'https://fcm.googleapis.com/fcm/send/stary';
    const { bledy } = await otworzPowiadomienia(page, { klucz, atrapy: { ua: ANDROID, subskrypcja: adres, kluczSubskrypcji: stary,
      nowa: 'https://fcm.googleapis.com/fcm/send/nowy', zapamietana: { endpoint: adres, od: Date.now() - DOBA } } });
    // ten sam adres co w sekrecie, ale nadawca podpisuje już nowym kluczem — push by nie przeszedł
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'zmieniona');
    await page.getByRole('button', { name: 'Włącz powiadomienia na tym telefonie' }).click();
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'subskrypcja');
    const log = await page.evaluate(() => window.atrapa);
    expect(log.wypisania).toBe(1);
    expect(log.subskrypcje).toEqual([{ userVisibleOnly: true, klucz }]);
    expect(JSON.parse(await page.locator('#pow-subskrypcja').inputValue()).endpoint).toBe('https://fcm.googleapis.com/fcm/send/nowy');
    expect(bledy).toEqual([]);
  });

  for (const [opis, atrapy] of [['w Safari (bez PushManager)', { bezPush: true }], ['poza aplikacją z ekranu', {}]]) {
    test(`iPhone ${opis}: instrukcja zamiast przycisku`, async ({ page }) => {
      const { bledy } = await otworzPowiadomienia(page, { klucz: kluczPubliczny(), atrapy: { ua: IPHONE, ...atrapy } });
      const tel = page.locator('#pow-telefon');
      await expect(tel).toHaveAttribute('data-stan', 'iphone');
      for (const fraza of ['iOS 16.4', 'Safari', 'Do ekranu początkowego', 'Otwórz jako aplikację webową', 'z ikony']) {
        await expect(tel).toContainText(fraza);
      }
      await expect(tel.getByRole('button')).toHaveCount(0);
      expect(bledy).toEqual([]);
    });
  }

  test('iPhone w aplikacji z ekranu: przycisk i sekret PUSH_IPHONE', async ({ page }) => {
    const { bledy } = await otworzPowiadomienia(page, { klucz: kluczPubliczny(),
      atrapy: { ua: IPHONE, standalone: true, nowa: 'https://web.push.apple.com/QAbc' } });
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'wylaczone');
    await page.getByRole('button', { name: 'Włącz powiadomienia na tym telefonie' }).click();
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'subskrypcja');
    await expect(page.locator('#pow-telefon')).toContainText('PUSH_IPHONE');
    await expect(page.locator('#pow-telefon')).not.toContainText('PUSH_ANDROID');
    expect(bledy).toEqual([]);
  });

  test('odmowa zgody i brak API nie wywracają strony', async ({ page }) => {
    const { bledy } = await otworzPowiadomienia(page, { klucz: kluczPubliczny(), atrapy: { ua: ANDROID, zgoda: 'denied' } });
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'odmowa');
    await expect(page.locator('#pow-telefon')).toContainText('Ustawienia');
    const druga = await page.context().newPage();
    const { bledy: bledy2 } = await otworzPowiadomienia(druga, { klucz: kluczPubliczny(), atrapy: { bezApi: true } });
    await expect(druga.locator('#pow-telefon')).toHaveAttribute('data-stan', 'brak-wsparcia');
    await expect(druga.locator('.karta')).toHaveCount(3);
    expect(bledy).toEqual([]);
    expect(bledy2).toEqual([]);
  });

  test('wysłane ponad godzinę temu i nieodebrane → „nie dochodzą"; zapis odbioru z sw.js je gasi', async ({ page }) => {
    const adres = 'https://web.push.apple.com/QAbc';
    const { bledy } = await otworzPowiadomienia(page, {
      klucz: kluczPubliczny(),
      powiadomienia: plikPowiadomien([wpis('20261009T120112Z-podlej', 2 * GODZ)]),
      atrapy: { ua: IPHONE, standalone: true, zgoda: 'granted', subskrypcja: adres, zapamietana: { endpoint: adres, od: Date.now() - 3 * DOBA } },
    });
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'wlaczone');
    const ostrzezenie = page.locator('#pow-dochodza');
    await expect(ostrzezenie).toBeVisible();
    await expect(ostrzezenie).toContainText('Powiadomienia nie dochodzą do tego telefonu');
    await expect(ostrzezenie).toContainText('Podlej: azalia');
    await expect(ostrzezenie).toContainText('PUSH_IPHONE');
    // odbiór zapisuje ten sam kod co w sw.js — strona musi umieć go przeczytać
    await page.evaluate(([zrodlo]) => new Function('self', 'indexedDB', `${zrodlo}\nreturn zapiszOdebrane;`)(
      { addEventListener() {} }, indexedDB)('20261009T120112Z-podlej'), [SW]);
    await page.evaluate(() => odswiezPowiadomienia());
    await expect(ostrzezenie).toBeHidden();
    expect(bledy).toEqual([]);
  });

  test('„Odnów subskrypcję" przy „nie dochodzą" wymienia martwą subskrypcję na nową', async ({ page }) => {
    const adres = 'https://web.push.apple.com/martwa';
    const { bledy } = await otworzPowiadomienia(page, {
      klucz: kluczPubliczny(),
      powiadomienia: plikPowiadomien([wpis('A', 3 * GODZ)]),
      atrapy: { ua: IPHONE, standalone: true, zgoda: 'granted', subskrypcja: adres, nowa: 'https://web.push.apple.com/zywa',
        zapamietana: { endpoint: adres, od: Date.now() - 3 * DOBA } },
    });
    await page.getByRole('button', { name: 'Odnów subskrypcję' }).click();
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'subskrypcja');
    // ta sama, martwa subskrypcja nic by nie dała — Apple dalej odpowiada 201
    expect(await page.evaluate(() => window.atrapa.wypisania)).toBe(1);
    expect(JSON.parse(await page.locator('#pow-subskrypcja').inputValue()).endpoint).toBe('https://web.push.apple.com/zywa');
    await expect(page.locator('#pow-dochodza')).toBeHidden();
    expect(bledy).toEqual([]);
  });

  test('„nie dochodzą" liczy tylko wysłane po skopiowaniu i już rozstrzygnięte', async ({ page }) => {
    const { bledy } = await otworzPowiadomienia(page);
    const wyniki = await page.evaluate(() => {
      const t = Date.now(), H = 3600e3, od = t - 10 * H;
      const w = (id, temu, naSucho = false) => ({ id, ts: new Date(t - temu).toISOString(), na_sucho: naSucho, tytul: id });
      const f = (historia, odebrane) => nieDotarlo(historia, new Set(odebrane), od, t)?.id ?? null;
      return {
        stareNieodebrane: f([w('A', 2 * H)], []),
        stareOdebrane: f([w('A', 2 * H)], ['A']),
        swiezeCzekaNaGodzine: f([w('A', 30 * 60e3)], []),
        naSucho: f([w('A', 2 * H, true)], []),
        sprzedSkopiowania: f([w('A', 11 * H)], []),
        noweOdebraneKanalDziala: f([w('A', 3 * H), w('B', 2 * H)], ['B']),
        noweNieodebrane: f([w('A', 3 * H), w('B', 2 * H)], ['A']),
        swiezeNiePrzykrywaStarego: f([w('A', 3 * H), w('B', 10 * 60e3)], []),
        pusto: f([], []),
      };
    });
    expect(wyniki).toEqual({
      stareNieodebrane: 'A', stareOdebrane: null, swiezeCzekaNaGodzine: null, naSucho: null,
      sprzedSkopiowania: null, noweOdebraneKanalDziala: null, noweNieodebrane: 'B',
      swiezeNiePrzykrywaStarego: 'A', pusto: null,
    });
    expect(bledy).toEqual([]);
  });

  test('bez subskrypcji tego telefonu nie ma „nie dochodzą", choć wysłane nie dotarło', async ({ page }) => {
    const { bledy } = await otworzPowiadomienia(page, { klucz: kluczPubliczny(),
      powiadomienia: plikPowiadomien([wpis('A', 2 * GODZ)]), atrapy: { ua: ANDROID, zgoda: 'granted' } });
    await expect(page.locator('#pow-telefon')).toHaveAttribute('data-stan', 'wylaczone');
    await expect(page.locator('#pow-dochodza')).toBeHidden();
    expect(bledy).toEqual([]);
  });

  test('decyzje z powiadomienia.json widać na zakładce — w trybie na sucho z dopiskiem', async ({ page }) => {
    const wpisy = Array.from({ length: 7 }, (_, i) => wpis(`W${i}`, (7 - i) * GODZ, { na_sucho: true, tytul: `Podlej ${i}` }));
    const { bledy } = await otworzPowiadomienia(page, { powiadomienia: plikPowiadomien(wpisy, 'na-sucho') });
    const lista = page.locator('#pow-historia');
    await expect(lista).toBeVisible();
    await expect(lista).toContainText('na sucho — reguły już działają');
    await expect(lista.locator('li')).toHaveCount(5);
    expect(await lista.locator('li').evaluateAll((li) => li.map((x) => x.dataset.id))).toEqual(['W6', 'W5', 'W4', 'W3', 'W2']);
    await expect(lista.locator('.znacznik')).toHaveCount(5);
    await expect(lista.locator('li').first()).toContainText('Azalia: gleba 41%');
    expect(bledy).toEqual([]);
  });

  test('bez pliku powiadomień sekcja mówi, że kolektor jeszcze nic nie zdecydował', async ({ page }) => {
    const { bledy } = await otworzPowiadomienia(page);
    await expect(page.locator('#pow-historia')).toContainText('Kolektor nie zapisał jeszcze żadnej decyzji');
    expect(bledy).toEqual([]);
  });

  test('sw.js push: zawsze pokazuje powiadomienie, a odbiór zapisuje w IndexedDB', async ({ page }) => {
    await stronaProby(page);
    await page.evaluate(zaladujSw, [SW]);
    const tresc = { title: 'Podlej: azalia', body: 'Azalia: gleba 41%.', tag: 'podlej', url: 'rosliny.html#roslina=Azalia', id: '20261009T140112Z-podlej' };
    await page.evaluate((t) => sw.push(t), JSON.stringify(tresc));
    await page.evaluate(() => sw.push('zwykły tekst zamiast JSON'));
    await page.evaluate(() => sw.push(null));
    await page.evaluate(() => sw.push('[1,2]'));
    await page.evaluate(() => sw.push(JSON.stringify({ title: 'Bez id' })));
    const pokazane = await page.evaluate(() => log.pokazane);
    expect(pokazane).toEqual([
      ['Podlej: azalia', { body: 'Azalia: gleba 41%.', icon: 'ikona-192.png', tag: 'podlej', renotify: true,
        data: { url: 'rosliny.html#roslina=Azalia', id: '20261009T140112Z-podlej' } }],
      ['Rośliny', { body: 'zwykły tekst zamiast JSON', icon: 'ikona-192.png', data: { url: '', id: null } }],
      ['Rośliny', { body: '', icon: 'ikona-192.png', data: { url: '', id: null } }],
      ['Rośliny', { body: '[1,2]', icon: 'ikona-192.png', data: { url: '', id: null } }],
      ['Bez id', { body: '', icon: 'ikona-192.png', data: { url: '', id: null } }],
    ]);
    expect(await odebraneWStronie(page)).toEqual(['20261009T140112Z-podlej']);
    // bez IndexedDB powiadomienie i tak wychodzi — Safari cofa zgodę za push bez powiadomienia
    await page.evaluate(zaladujSw, [SW, { bezIndexedDB: true }]);
    await page.evaluate((t) => sw.push(t), JSON.stringify(tresc));
    expect(await page.evaluate(() => log.pokazane.map((p) => p[0]))).toEqual(['Podlej: azalia']);
  });

  test('sw.js kliknięcie: otwiera tylko adresy z zakresu aplikacji', async ({ page }) => {
    await stronaProby(page);
    await page.evaluate(zaladujSw, [SW]);
    const Z = 'https://bronek31.github.io/Smart-Home/';
    const cele = await page.evaluate((z) => [
      'rosliny.html#roslina=Skrzyd%C5%82okwiat', `${z}rosliny.html`, 'https://zly.example/rosliny.html', '//zly.example/x',
      '../inny/', 'https://bronek31.github.io/Smart-Home-zly/x', 'javascript:alert(1)', '/Smart-Home/../x', '%2e%2e/x',
      'http://bronek31.github.io/Smart-Home/rosliny.html', null, '',
    ].map((u) => sw.celKlikniecia(u, z)), Z);
    expect(cele).toEqual([`${Z}rosliny.html#roslina=Skrzyd%C5%82okwiat`, `${Z}rosliny.html`, Z, Z, Z, Z, Z, Z, Z, Z, Z, Z]);

    const origin = new URL(page.url()).origin;
    // bez otwartego okna: nowe okno na celu i cel w Cache API dla index.html (zimny start iPhone'a)
    await page.evaluate(() => sw.klik({ url: 'rosliny.html#roslina=Azalia', id: 'A' }));
    expect(await page.evaluate(() => log)).toMatchObject({ zamkniete: 1, otwarte: [`${origin}/rosliny.html#roslina=Azalia`], nawigacje: [] });
    const cel = await celWCache(page);
    expect(cel.cel).toBe('rosliny.html#roslina=Azalia');
    expect(Math.abs(Date.now() - cel.ts)).toBeLessThan(60e3);
    // obcy adres w data.url → strona startowa, bez celu do przekierowania
    await page.evaluate(() => caches.delete('cel-powiadomienia'));
    await page.evaluate(() => sw.klik({ url: 'https://zly.example/', id: 'B' }));
    expect(await page.evaluate(() => log.otwarte.at(-1))).toBe(`${origin}/`);
    expect(await celWCache(page)).toBeNull();
  });

  test('sw.js kliknięcie przy otwartym oknie: fokus i przejście, bez zapisu celu', async ({ page }) => {
    await stronaProby(page);
    const origin = new URL(page.url()).origin;
    await page.evaluate(zaladujSw, [SW, { okna: [{ url: `${origin}/index.html` }] }]);
    await page.evaluate(() => sw.klik({ url: 'rosliny.html#roslina=Fikus', id: 'A' }));
    expect(await page.evaluate(() => log)).toMatchObject({ fokusy: 1, nawigacje: [`${origin}/rosliny.html#roslina=Fikus`], otwarte: [] });
    // zapisany cel przerzuciłby do roślin następne kliknięcie w zakładkę „Mieszkanie"
    expect(await celWCache(page)).toBeNull();
    // okno, którym ten worker nie steruje, odrzuca navigate() — wtedy nowe okno z celem
    await page.evaluate(zaladujSw, [SW, { okna: [{ url: `${origin}/index.html`, niesterowane: true }] }]);
    await page.evaluate(() => sw.klik({ url: 'rosliny.html#roslina=Fikus', id: 'A' }));
    expect(await page.evaluate(() => log)).toMatchObject({ nawigacje: [], otwarte: [`${origin}/rosliny.html#roslina=Fikus`] });
    expect((await celWCache(page)).cel).toBe('rosliny.html#roslina=Fikus');
    // karta innego projektu z tego samego originu (github.io) — nie nasza, zostaje w spokoju
    await page.evaluate(zaladujSw, [SW, { zakres: `${origin}/Smart-Home/`, okna: [{ url: `${origin}/inny-projekt/` }] }]);
    await page.evaluate(() => sw.klik({ url: 'rosliny.html#roslina=Fikus', id: 'A' }));
    expect(await page.evaluate(() => log)).toMatchObject({ fokusy: 0, nawigacje: [], otwarte: [`${origin}/Smart-Home/rosliny.html#roslina=Fikus`] });
  });

  test('sw.js aktywacja: nowa wersja kasuje stare cache, ale nie cel kliknięcia', async ({ page }) => {
    // pierwsza linia to strażnik (v4 → v5 przy nowych obsługach); reszta to zachowanie
    expect(SW).toMatch(/const WERSJA = 'smart-home-v5';/);
    await stronaProby(page);
    await page.evaluate(zaladujSw, [SW]);
    await page.evaluate(() => Promise.all(['smart-home-v4', 'smart-home-v5', 'cel-powiadomienia'].map((n) => caches.open(n))));
    await page.evaluate(() => sw.aktywuj());
    expect((await page.evaluate(() => caches.keys())).sort()).toEqual(['cel-powiadomienia', 'smart-home-v5']);
  });

  test('zimny start z powiadomienia: index.html przechodzi do celu z sw.js i go kasuje', async ({ page }) => {
    const bledy = pilnujBledow(page);
    await podepnijChart(page);
    await podstawRosliny(page);
    await stronaProby(page);
    await page.evaluate(zaladujSw, [SW]);
    await page.evaluate(() => sw.klik({ url: 'rosliny.html#roslina=Skrzyd%C5%82okwiat', id: 'A' }));
    await page.goto('/index.html');
    await page.waitForURL(/\/rosliny\.html#roslina=Skrzyd%C5%82okwiat$/);
    await page.waitForFunction(() => !/wczytywanie/.test(document.getElementById('stamp').textContent), null, { timeout: 20000 });
    await expect(karta(page, 'Skrzydłokwiat')).toHaveClass(/wskazana/);
    expect(await celWCache(page)).toBeNull();
    // następne uruchomienie z ikony zostaje na mieszkaniu
    await page.goto('/index.html');
    await page.waitForLoadState('load');
    await page.waitForTimeout(300);
    expect(new URL(page.url()).pathname).toBe('/index.html');
    expect(bledy).toEqual([]);
  });

  test('wejście na zakładkę roślin kasuje cel kliknięcia, więc mieszkanie potem nie skacze', async ({ page }) => {
    // Android otwiera rosliny.html wprost z openWindow — cel zapisany przez sw.js zostałby
    // i najbliższe wejście na mieszkanie w ciągu kilku minut przerzuciłoby z powrotem tutaj.
    await stronaProby(page);
    await page.evaluate(() => caches.open('cel-powiadomienia').then((c) => c.put('./cel',
      new Response(JSON.stringify({ cel: 'rosliny.html#roslina=Azalia', ts: Date.now() })))));
    const { bledy } = await otworzRosliny(page, {}, { hash: '#roslina=Azalia' });
    await expect.poll(() => celWCache(page)).toBeNull();
    await page.goto('/index.html');
    await page.waitForLoadState('load');
    await page.waitForTimeout(300);
    expect(new URL(page.url()).pathname).toBe('/index.html');
    expect(bledy).toEqual([]);
  });

  test('cel zapisany chwilę po starcie index.html też działa (druga próba)', async ({ page }) => {
    const bledy = pilnujBledow(page);
    await podepnijChart(page);
    await podstawRosliny(page);
    await page.goto('/index.html');
    await page.waitForLoadState('load');
    await page.evaluate(() => caches.open('cel-powiadomienia').then((c) => c.put('./cel',
      new Response(JSON.stringify({ cel: 'rosliny.html#roslina=Fikus', ts: Date.now() })))));
    await page.waitForURL(/\/rosliny\.html#roslina=Fikus$/, { timeout: 6000 });
    expect(bledy).toEqual([]);
  });

  for (const [opis, cel, temu] of [
    ['obcy adres', 'https://zly.example/rosliny.html', 0],
    ['adres względny do obcego hosta', '//zly.example/rosliny.html', 0],
    ['inna strona aplikacji', 'index.html#zakres=7', 0],
    ['nazwa tylko udająca zakładkę', 'rosliny.html.zly.example', 0],
    ['cel sprzed kwadransa', 'rosliny.html#roslina=Azalia', 15 * 60e3],
  ]) {
    test(`index.html nie idzie za celem (${opis}), ale go kasuje`, async ({ page }) => {
      const bledy = pilnujBledow(page);
      await podepnijChart(page);
      await podstawRosliny(page);
      await stronaProby(page);
      await page.evaluate(([c, t]) => caches.open('cel-powiadomienia').then((k) => k.put('./cel',
        new Response(JSON.stringify({ cel: c, ts: Date.now() - t })))), [cel, temu]);
      await page.goto('/index.html');
      await expect.poll(() => celWCache(page)).toBeNull();
      await page.waitForTimeout(300);
      expect(new URL(page.url()).pathname).toBe('/index.html');
      expect(bledy).toEqual([]);
    });
  }

  test.describe('z prawdziwym service workerem', () => {
    // Drugi (po strona.spec.js) test z działającym workerem: tylko tak push przechodzi przez
    // prawdziwą obsługę, showNotification i IndexedDB workera. Dane idą wtedy z repozytorium.
    test.use({ serviceWorkers: 'allow' });

    test('push przez CDP: worker pokazuje powiadomienie i zapisuje odbiór, który czyta zakładka', async ({ page, context, baseURL }) => {
      const bledy = pilnujBledow(page);
      await podepnijChart(page);
      await context.grantPermissions(['notifications']);
      const cdp = await context.newCDPSession(page);
      const rejestracje = [];
      cdp.on('ServiceWorker.workerRegistrationUpdated', (e) => rejestracje.push(...e.registrations));
      await cdp.send('ServiceWorker.enable');
      await page.goto('/rosliny.html');
      await page.evaluate(() => navigator.serviceWorker.ready.then(() => null));
      await expect.poll(() => rejestracje.some((r) => !r.isDeleted)).toBe(true);
      const { registrationId } = rejestracje.find((r) => !r.isDeleted);
      const tresc = { title: 'Podlej: azalia', body: 'Azalia: gleba 41%.', tag: 'podlej', url: 'rosliny.html#roslina=Azalia', id: '20261009T140112Z-podlej' };
      await cdp.send('ServiceWorker.deliverPushMessage', { origin: `${baseURL}/`, registrationId, data: JSON.stringify(tresc) });
      // odbiór zapisuje obsługa push workera, a czyta go funkcja zakładki — w każdym Chromium
      await expect.poll(() => page.evaluate(() => odebraneId().then((s) => [...s]))).toEqual(['20261009T140112Z-podlej']);
      // Samo powiadomienie widać tylko w pełnym Chromium. Headless shell (domyślny w CI przy
      // Playwright 1.49) mimo grantPermissions zostaje przy zgodzie 'denied' i niczego nie
      // pokazuje — zmierzone 9.10 na obu binarkach. Treść powiadomienia pilnuje wtedy test
      // „sw.js push" z atrapą `self`.
      if (await page.evaluate(() => Notification.permission) === 'granted') {
        await expect.poll(() => page.evaluate(async () => (await (await navigator.serviceWorker.ready).getNotifications())
          .map((n) => ({ tytul: n.title, tresc: n.body, tag: n.tag, dane: n.data })))).toEqual([
          { tytul: 'Podlej: azalia', tresc: 'Azalia: gleba 41%.', tag: 'podlej', dane: { url: 'rosliny.html#roslina=Azalia', id: '20261009T140112Z-podlej' } }]);
      } else {
        test.info().annotations.push({ type: 'bez pokazania', description: 'ta binarka Chromium nie pokazuje powiadomień — sprawdzony tylko zapis odbioru' });
      }
      expect(bledy).toEqual([]);
    });
  });
});
