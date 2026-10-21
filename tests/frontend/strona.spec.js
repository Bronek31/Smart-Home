// Testy aplikacji (index.html): dom, pokoje, rośliny, historia, powiadomienia.
//
// Strona wyświetla to, co policzył kolektor (reguły domu z data/dom/stan.json, werdykty i ocenę światła roślin
// z data/rosliny/stan.json), a sama liczy tylko wyświetlanie: serie wykresów, komfort, zakresy, 30 dni. Testy
// podstawiają pliki z dane.js (po ścieżce), czekają, aż #app dostanie data-dane ≠ „wczytywanie", i sprawdzają
// ekran albo obliczenia przez window.SH. Każdy test pilnuje pustej konsoli.
//
// Uruchamianie: cd tests/frontend && npx playwright test strona.spec.js
const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');
const { podstaw, zbuduj, ROSLINY, GODZ, DOBA, iso, dataWaw } = require('./dane');

const REPO = path.join(__dirname, '..', '..');
const HTML = fs.readFileSync(path.join(REPO, 'index.html'), 'utf8');
const FG = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Warsaw', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const godzinaWaw = (ms) => +FG.format(new Date(ms)).slice(0, 2);

/** Wyłapuje każdy błąd strony. 404 nieobowiązkowych plików (pogoda, dom, rośliny) to nie błąd strony, a przeglądarka
 *  i tak loguje je sama — stąd filtr na komunikaty o zasobach. */
function pilnujBledow(page) {
  const bledy = [];
  page.on('pageerror', (e) => bledy.push(`pageerror: ${e.message}`));
  page.on('console', (m) => {
    if (m.type() === 'error' && !/net::ERR|Failed to load resource/.test(m.text())) bledy.push(`console: ${m.text()}`);
  });
  return bledy;
}
async function gotowa(page) {
  await page.waitForFunction(() => document.getElementById('app').getAttribute('data-dane') !== 'wczytywanie', null, { timeout: 20000 });
}
/** Wspólny start: fonty zablokowane (bez sieci w CI), podstawione dane, strona gotowa. */
async function otworz(page, opcje = {}, { hash = '', sciezka = '/index.html' } = {}) {
  const bledy = pilnujBledow(page);
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  const pliki = await podstaw(page, opcje);
  await page.goto(sciezka + hash);
  await gotowa(page);
  return { bledy, pliki };
}
/** Drugi zestaw plików w tym samym teście: podstawione pliki zbudowane od nowa z innymi opcjami i strona wczytana
 *  od nowa pod `hash` (samo page.goto na inny hash to nawigacja w tym samym dokumencie, bez wczytania danych). */
async function podmien(page, opcje, hash) {
  await page.unroute('**/data/**');
  await page.unroute('**/pokoje.json');
  const pliki = await podstaw(page, opcje);
  await page.goto('/index.html' + hash);
  await page.reload();
  await gotowa(page);
  return pliki;
}
const widok = (page) => page.locator('.widok:not([hidden]), .strona:not(.sasiad)').first();
const tekstStrony = (page) => page.locator('.strona:not(.sasiad)').innerText();
/** Prawdziwy gest palcem w Chromium (CDP), z touch-action — jak na telefonie. Wzór: propozycje3/narzedzia/gest.js. */
async function przesun(page, x0, y0, x1, y1, kroki = 14, czasMs = 260) {
  const c = await page.context().newCDPSession(page);
  await c.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: x0, y: y0 }] });
  for (let i = 1; i <= kroki; i++) {
    const t = i / kroki;
    await c.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x0 + (x1 - x0) * t, y: y0 + (y1 - y0) * t }] });
    await page.waitForTimeout(czasMs / kroki);
  }
  await c.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await c.detach();
}

test.describe('dane testowe', () => {
  const wiersze = (pliki) => Object.keys(pliki).filter((k) => /^data\/\d{4}-\d\d\.csv$/.test(k)).flatMap((k) => pliki[k].trim().split('\n').slice(1));

  test('żaden odczyt nie jest zapisany dwa razy, a pliki miesięczne są posortowane', () => {
    for (const o of [{}, { skok: { pokoj: 'sypialnia', godzWstecz: 5, o: 6 } }, { martwy: 'kuchnia' }]) {
      const w = wiersze(zbuduj(o));
      const klucze = w.map((r) => r.split(',').slice(0, 3).join('|'));
      expect(new Set(klucze).size, JSON.stringify(o)).toBe(klucze.length);
      expect(w).toEqual([...w].sort());
    }
  });

  test('co najmniej 8 dób historii, dzienne.csv z datą warszawską, pliki roślin osobno od pokoi', () => {
    const pliki = zbuduj({});
    const t = wiersze(pliki).map((r) => Date.parse(r.split(',')[0]));
    expect((Math.max(...t) - Math.min(...t)) / DOBA).toBeGreaterThanOrEqual(8);
    const daty = new Set(pliki['data/dzienne.csv'].trim().split('\n').slice(1).map((r) => r.split(',')[0]));
    expect([...daty].sort()).toEqual([...new Set(t.map(dataWaw))].sort());
    expect(pliki['data/rosliny/stan.json']).toBeTruthy();
    expect(Object.keys(pliki).filter((k) => /^data\/rosliny\/\d/.test(k))).toEqual([]);
  });
});

test.describe('start', () => {
  test('Dom: cztery pokoje, dwór, wykres i cztery zakładki', async ({ page }) => {
    const { bledy } = await otworz(page);
    await expect(page.locator('#app')).toHaveAttribute('data-dane', 'gotowe');
    await expect(page.locator('#v-dom .siatka-p .pokoj')).toHaveCount(4);
    await expect(page.locator('#v-dom .dwor')).toBeVisible();
    await expect(page.locator('#v-dom [data-wykres="dom"] svg')).toBeVisible();
    await expect(page.locator('#zakladki .zakladka')).toHaveCount(4);
    await expect(page.locator('#zakladki [data-tab="dom"]')).toHaveAttribute('aria-current', 'page');
    // pokoje w kolejności manifestu, kolory z palety w tej kolejności, dwór spoza palety
    const kolory = await page.evaluate(() => SH.dane.pokoje.map((p) => p.kolor));
    expect(kolory.slice(0, 4)).toEqual(['#e8a13c', '#5fb8e0', '#5fce9e', '#e2708f']);
    expect(kolory.slice(0, 4)).not.toContain(kolory[4]);
    expect(bledy).toEqual([]);
  });

  for (const [opis, opcje, tekst] of [
    ['brak manifestu', { brakManifestu: true }, 'Nie ma jeszcze żadnych odczytów'],
    ['manifest bez miesięcy', { pusto: true }, 'Czujniki są, odczytów jeszcze nie ma'],
    ['manifest bez czujników', { bezCzujnikow: true }, 'Kolektor nie znalazł czujników'],
    ['puste pliki odczytów', { pustePliki: true }, 'Pliki z danymi są puste'],
  ]) {
    test(`${opis}: komunikat zamiast pustych ramek, Rośliny działają dalej`, async ({ page }) => {
      const { bledy } = await otworz(page, opcje);
      await expect(page.locator('#app')).toHaveAttribute('data-dane', 'blad');
      await expect(page.locator('#v-dom [data-blad]')).toContainText(tekst);
      await page.click('[data-tab="historia"]');
      await expect(page.locator('#v-historia [data-blad]')).toContainText(tekst);
      await page.click('[data-tab="rosliny"]');
      await expect(page.locator('#v-rosliny .rk')).toHaveCount(3);
      expect(bledy).toEqual([]);
    });
  }

  test('nazwa czujnika ze znacznikiem HTML jest tekstem', async ({ page }) => {
    const { bledy } = await otworz(page, { nazwaZnacznik: true });
    await expect(page.locator('#v-dom .siatka-p')).toContainText('Salon <b>"x"</b>');
    expect(await page.locator('.pokoj-n b').count()).toBe(0);
    expect(bledy).toEqual([]);
  });

  test('bez pokoje.json: slug z nazwy, odmiana = nazwa małą literą', async ({ page }) => {
    const { bledy } = await otworz(page, { pokojeJson: false, dom: { lazienka: { przewietrz: { od: iso(Date.now() - 3 * GODZ), wilg: 72, granica: 63.2 } } } });
    const slugi = await page.evaluate(() => SH.dane.pokoje.map((p) => p.slug));
    expect(slugi).toEqual(['salon', 'sypialnia', 'kuchnia', 'lazienka', 'zewnatrz']);
    await expect(page.locator('#v-dom .podsum-s')).toHaveText(/Przewietrz łazienka/);
    expect(bledy).toEqual([]);
  });

  test('bez pogody: karta dworu z samym odczytem, strona dworu bez prognozy', async ({ page }) => {
    const { bledy } = await otworz(page, { pogoda: 'brak' });
    await expect(page.locator('#v-dom .dwor')).toContainText('Wilgotność');
    expect(await page.locator('#v-dom .dni3').count()).toBe(0);
    await page.click('#v-dom .dwor');
    await expect(page).toHaveURL(/#zewnatrz$/);
    const t = await tekstStrony(page);
    expect(t).not.toMatch(/undefined|NaN|3 dni|Powietrze/);
    expect(bledy).toEqual([]);
  });

  test('strona dworu podaje źródło pogody (Open-Meteo, CC BY 4.0), a bez pogody nie podaje', async ({ page }) => {
    const { bledy } = await otworz(page, {}, { hash: '#zewnatrz' });
    const zrodlo = page.locator('.strona:not(.sasiad) .zrodlo');
    await expect(zrodlo).toContainText('Open-Meteo');
    await expect(zrodlo).toContainText('CC BY 4.0');
    expect(await zrodlo.locator('a').getAttribute('href')).toBe('https://open-meteo.com/');
    await podmien(page, { pogoda: 'brak' }, '#zewnatrz');
    expect(await page.locator('.strona:not(.sasiad) .zrodlo').count()).toBe(0);
    expect(bledy).toEqual([]);
  });

  test('zmiana „od wczoraj” równa 0,0° nie ma strzałki, a 1,2° ma', async ({ page }) => {
    // domyślna fikstura: doba sinusoidy powtarza się, więc temperatura sprzed 24 godz. jest taka sama
    const { bledy } = await otworz(page, {}, { hash: '#kuchnia' });
    const z = page.locator('.strona:not(.sasiad) .boh-z');
    await expect(z).toContainText('0,0°');
    expect(await z.locator('svg, .ik').count()).toBe(0);
    await podmien(page, { trend: { kuchnia: -1.2 } }, '#kuchnia');
    await expect(page.locator('.strona:not(.sasiad) .boh-z')).toContainText('1,2°');
    expect(await page.locator('.strona:not(.sasiad) .boh-z').locator('svg, .ik').count()).toBeGreaterThan(0);
    expect(bledy).toEqual([]);
  });

  for (const p of ['bezPowietrza', 'krotka']) {
    test(`pogoda „${p}" (powietrze {} po błędzie AQI, prognoza na jedną dobę) nie wywraca dworu ani Domu`, async ({ page }) => {
      const { bledy } = await otworz(page, { pogoda: p }, { hash: '#zewnatrz' });
      const t = await tekstStrony(page);
      expect(t).not.toMatch(/undefined|NaN/);
      if (p === 'bezPowietrza') expect(t).not.toContain('Powietrze');
      else expect(await page.locator('.strona:not(.sasiad) .prog-dzien').count()).toBe(1);
      await page.click('[data-tab="dom"]');
      expect(await page.locator('#v-dom').innerText()).not.toMatch(/undefined|NaN/);
      expect(bledy).toEqual([]);
    });
  }

  test('bez odczytu sprzed doby: bez strzałki zmiany, bez „–°"', async ({ page }) => {
    const { bledy } = await otworz(page, { dni: 0.5 }, { hash: '#kuchnia' });
    expect(await page.evaluate(() => SH.dane.pokoje.every((p) => p.temp_24h_temu == null))).toBe(true);
    expect(await tekstStrony(page)).not.toContain('od wczoraj');
    await page.click('[data-tab="dom"]');
    const dom = await page.locator('#v-dom').innerText();
    expect(dom).not.toMatch(/–°|24\sh|NaN|undefined/);
    // 30 dni i 7 dni bez treści też nie wywracają Historii
    await page.click('[data-tab="historia"]');
    expect(await page.locator('#v-historia').innerText()).not.toMatch(/NaN|undefined/);
    expect(bledy).toEqual([]);
  });
});

test.describe('adresy (D7)', () => {
  test('każda zakładka ma swój hash, nieznany hash prowadzi na Dom', async ({ page }) => {
    const { bledy } = await otworz(page, {}, { hash: '#xyz' });
    await expect(page).toHaveURL(/#dom$/);
    for (const z of ['rosliny', 'historia', 'powiadomienia', 'dom']) {
      await page.click(`[data-tab="${z}"]`);
      await expect(page).toHaveURL(new RegExp(`#${z}$`));
      await expect(page.locator(`[data-tab="${z}"]`)).toHaveAttribute('aria-current', 'page');
    }
    expect(bledy).toEqual([]);
  });

  test('pokój, dwór i roślina po slugu, z licznikiem w nagłówku', async ({ page }) => {
    const { bledy } = await otworz(page, {}, { hash: '#kuchnia' });
    await expect(page.locator('.strona:not(.sasiad) h1')).toHaveText('Kuchnia');
    await expect(page.locator('#licznik')).toHaveText('3/4');
    await page.goto('/index.html#zewnatrz');
    await gotowa(page);
    await expect(page.locator('.strona:not(.sasiad) h1')).toHaveText('Na zewnątrz');
    await expect(page.locator('#strzalki')).toBeHidden();
    await page.goto('/index.html#skrzydlokwiat');
    await gotowa(page);
    await expect(page.locator('.strona:not(.sasiad) h1')).toHaveText('Skrzydłokwiat');
    await expect(page.locator('#licznik')).toHaveText('2/3');
    expect(bledy).toEqual([]);
  });

  test('stary link #roslina=<nazwa> otwiera roślinę, a „wstecz" wraca do listy', async ({ page }) => {
    const { bledy } = await otworz(page, {}, { hash: '#roslina=' + encodeURIComponent('Skrzydłokwiat') });
    await expect(page).toHaveURL(/#skrzydlokwiat$/);
    await page.goBack();
    await expect(page).toHaveURL(/#rosliny$/);
    await expect(page.locator('#v-rosliny')).toBeVisible();
    await page.goto('/index.html#roslina=Nieznana');
    await gotowa(page);
    await expect(page).toHaveURL(/#rosliny$/);
    expect(bledy).toEqual([]);
  });

  test('index.html podany pod adresem rosliny.html (zapas service workera) wraca na ./#slug', async ({ page }) => {
    await page.route('**/rosliny.html', (r) => r.fulfill({ contentType: 'text/html', body: HTML }));
    const { bledy } = await otworz(page, {}, { sciezka: '/rosliny.html', hash: '#roslina=Fikus' });
    await expect(page).toHaveURL(/127\.0\.0\.1:\d+\/#fikus$/);
    await page.goBack();
    await expect(page).toHaveURL(/\/#rosliny$/);
    // sam rosliny.html (stara zakładka, bez hasha) to Rośliny
    await page.goto('/rosliny.html');
    await gotowa(page);
    await expect(page).toHaveURL(/127\.0\.0\.1:\d+\/#rosliny$/);
    expect(bledy).toEqual([]);
  });

  test('slug rośliny jak _slug w rosliny.py, z dopiskiem -2 przy kolizji z zakładką albo pokojem', async ({ page }) => {
    const nazwy = ['Skrzydłokwiat', 'Łazienka', 'Żółta Róża 2', 'Fikus  „Mały”', 'ąćęłńóśźż'];
    const py = JSON.parse(execFileSync('python3', ['-c',
      'import sys, json; sys.path.insert(0, "."); import rosliny; print(json.dumps([rosliny._slug(x) for x in json.loads(sys.argv[1])]))',
      JSON.stringify(nazwy)], { cwd: REPO }).toString());
    const zm = { Fikus: { nazwa: 'Kuchnia' }, 'Skrzydłokwiat': { nazwa: 'Dom' } };
    const { bledy } = await otworz(page, { zmianyRoslin: zm });
    expect(await page.evaluate((n) => n.map(SH.slug), nazwy)).toEqual(py);
    expect(await page.evaluate(() => SH.dane.rosliny.map((r) => r.slug))).toEqual(['kuchnia-2', 'dom-2', 'azalia']);
    await page.goto('/index.html#kuchnia-2');
    await gotowa(page);
    await expect(page.locator('.strona:not(.sasiad) h1')).toHaveText('Kuchnia');
    await expect(page.locator('#wstecz')).toContainText('Rośliny');
    expect(bledy).toEqual([]);
  });

  test('wstecz ze szczegółu wraca na zakładkę i oddaje fokus kaflowi', async ({ page }) => {
    const { bledy } = await otworz(page);
    await page.click('[data-idz="kuchnia"]');
    await expect(page).toHaveURL(/#kuchnia$/);
    await page.click('#wstecz');
    await expect(page).toHaveURL(/#dom$/);
    await expect(page.locator('[data-idz="kuchnia"]')).toBeFocused();
    // systemowe „wstecz" też
    await page.click('[data-tab="rosliny"]');
    await page.click('[data-idz="azalia"]');
    await page.goBack();
    await expect(page).toHaveURL(/#rosliny$/);
    expect(bledy).toEqual([]);
  });
});

test.describe('przesuwanie palcem', () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test('między pokojami: w lewo następny, w prawo poprzedni, na końcu opór', async ({ page }) => {
    const { bledy } = await otworz(page, {}, { hash: '#kuchnia' });
    await page.waitForTimeout(600);
    await przesun(page, 320, 200, 60, 205);
    await expect(page).toHaveURL(/#lazienka$/);
    await expect(page.locator('#licznik')).toHaveText('4/4');
    await page.waitForTimeout(400);
    await przesun(page, 320, 200, 60, 205);   // ostatni pokój: opór i powrót
    await page.waitForTimeout(500);
    await expect(page).toHaveURL(/#lazienka$/);
    await przesun(page, 60, 200, 320, 205);
    await expect(page).toHaveURL(/#kuchnia$/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
    expect(bledy).toEqual([]);
  });

  test('między roślinami, a pion przewija stronę zamiast przełączać', async ({ page }) => {
    const { bledy } = await otworz(page, {}, { hash: '#fikus' });
    await page.waitForTimeout(600);
    await przesun(page, 200, 500, 204, 250);
    await page.waitForTimeout(300);
    await expect(page).toHaveURL(/#fikus$/);
    await page.evaluate(() => window.scrollTo(0, 0));
    await przesun(page, 320, 150, 60, 152);
    await expect(page).toHaveURL(/#skrzydlokwiat$/);
    await expect(page.locator('#licznik')).toHaveText('2/3');
    expect(bledy).toEqual([]);
  });
});

test.describe('30 dni i 7 dni', () => {
  test('30 kolejnych dat warszawskich kończących się dziś, doby bez danych jako null', async ({ page }) => {
    const { bledy } = await otworz(page);
    const d = await page.evaluate(() => SH.dane.dobowe_30_dni.salon);
    const dzis = dataWaw(Date.now());
    expect(d.dni).toHaveLength(30);
    expect(d.dni[29]).toBe(dzis);
    for (let i = 1; i < 30; i++) {
      const a = Date.parse(d.dni[i - 1] + 'T12:00:00Z'), b = Date.parse(d.dni[i] + 'T12:00:00Z');
      expect(b - a, `${d.dni[i - 1]} → ${d.dni[i]}`).toBe(DOBA);
    }
    // fikstura ma 9 dób: starsze daty są puste, a nie przesunięte
    expect(d.temp.slice(0, 20).every((x) => x === null)).toBe(true);
    expect(d.temp[29]).not.toBeNull();
    // przez zmianę czasu 25.10 (doba 25-godzinna) daty dalej idą po kolei
    const przezZmiane = await page.evaluate(() => SH.zbudujDane(SH.surowe, Date.parse('2026-10-26T10:00:00Z')).dobowe_30_dni.salon.dni);
    expect(przezZmiane.slice(-3)).toEqual(['2026-10-24', '2026-10-25', '2026-10-26']);
    expect(new Set(przezZmiane).size).toBe(30);
    await page.click('[data-tab="historia"]');
    await expect(page.locator('.m30-xos .dzis')).toHaveText('dziś');
    expect(bledy).toEqual([]);
  });

  test('„7 dni": min i maks. z dób, średnia ważona liczbą odczytów', async ({ page }) => {
    const { bledy, pliki } = await otworz(page);
    const z = await page.evaluate(() => SH.dane.zakresy_7_dni.kuchnia);
    const dni = await page.evaluate(() => SH.dane.dobowe_30_dni.kuchnia.dni.slice(-7));
    const w = pliki['data/dzienne.csv'].trim().split('\n').slice(1).map((r) => r.split(','))
      .filter((r) => r[1] === 'kuchnia' && r[2] === 'va_temperature' && dni.indexOf(r[0]) >= 0);
    const n = w.reduce((a, r) => a + +r[6], 0);
    expect(z.t).toEqual([Math.min(...w.map((r) => +r[3])), Math.max(...w.map((r) => +r[5]))]);
    expect(z.t_sr).toBeCloseTo(w.reduce((a, r) => a + r[4] * r[6], 0) / n, 6);
    expect(bledy).toEqual([]);
  });
});

test.describe('na Domu, pokojach i Historii nie ma wartości z doniczek (D15)', () => {
  // strażnik: dawna strona mieszkania też ich nie miała — pilnuje, żeby nowa aplikacja tego nie zmieniła
  test('ani nazw roślin, ani gleby, ani światła (strażnik)', async ({ page }) => {
    const { bledy } = await otworz(page, { zmianyRoslin: { Azalia: { werdykt: 'podlej' } } });
    const zakazane = /Fikus|Skrzydłokwiat|Azalia|[Gg]leb|doniczk|lx/;
    expect(await page.locator('#v-dom').innerText()).not.toMatch(zakazane);
    for (const h of ['#salon', '#kuchnia']) {
      await page.goto('/index.html' + h);
      await gotowa(page);
      expect(await tekstStrony(page), h).not.toMatch(zakazane);
    }
    await page.click('[data-tab="historia"]');
    expect(await page.locator('#v-historia').innerText()).not.toMatch(zakazane);
    // wolno: kropka na zakładce Rośliny (azalia do podlania)
    await expect(page.locator('[data-tab="rosliny"] .z-kropka')).toHaveCount(1);
    expect(bledy).toEqual([]);
  });
});

test.describe('reguły domu z data/dom/stan.json (D1)', () => {
  test('„przewietrz": podsumowanie Domu, kafel i strona pokoju mówią to, co kolektor', async ({ page }) => {
    const od = iso(Date.now() - 3 * GODZ - 5 * 60e3);
    const { bledy } = await otworz(page, { dom: { kuchnia: { przewietrz: { od, wilg: 71, granica: 63.2 } } } });
    await expect(page.locator('#v-dom .podsum-s')).toHaveText(/Przewietrz kuchnię/);
    await expect(page.locator('#v-dom .podsum-l')).toContainText('za wilgotno od 63%');
    await expect(page.locator('[data-idz="kuchnia"].pokoj .pokoj-uw')).toContainText('od 3');
    await page.click('#v-dom .podsum');
    await expect(page).toHaveURL(/#kuchnia$/);
    const s = page.locator('.strona:not(.sasiad) .status').first();
    await expect(s).toContainText('Przewietrz kuchnię');
    await expect(s).toContainText('za wilgotno od 63%');
    await expect(s).toContainText('Na przestrzał');
    // pokój do przewietrzenia otwiera się na wilgotności
    await expect(page.locator('.strona:not(.sasiad) [data-seg="wyk.miara"][data-w="wilg"]')).toHaveAttribute('aria-pressed', 'true');
    expect(bledy).toEqual([]);
  });

  test('granica przy „przewietrz" jak w powiadomieniu: 62% przy granicy 61,6 → „61,6%", nigdy „62% … granica 62%"', async ({ page }) => {
    // dom._linia_przewietrz: granica zaokrąglona do wilgotności dostaje miejsce po przecinku. Kontrola na końcu:
    // 62% przy 61,4 to dwie różne liczby po zaokrągleniu (62 i 61), więc bez przecinka.
    const od = iso(Date.now() - 2 * GODZ);
    const { bledy } = await otworz(page, { wilgotnosc: { lazienka: 62 }, dom: { lazienka: { przewietrz: { od, wilg: 62, granica: 61.6 } } } });
    const sprzeczne = /(granica|za wilgotno od)\s62%/;
    await expect(page.locator('#v-dom .podsum-l')).toContainText(/62% od 2\sgodz\. · za wilgotno od 61,6%/);
    expect(await page.locator('#v-dom').innerText()).not.toMatch(sprzeczne);
    await page.goto('/index.html#lazienka');
    await gotowa(page);
    const s = page.locator('.strona:not(.sasiad)');
    await expect(s.locator('.status').first()).toContainText(/Wilgotność 62% od 2\sgodz\., za wilgotno od 61,6%\./);
    await expect(s.locator('.wart-op')).toContainText('za wilgotno — 62%, granica 61,6%');
    await expect(s.locator('.tor-et .gr')).toHaveText('61,6%');
    // legenda wykresu doby (pokój do przewietrzenia otwiera się na wilgotności)
    await expect(s.locator('.wyk-karta .leg')).toContainText('za wilgotno od 61,6%');
    expect(await tekstStrony(page)).not.toMatch(sprzeczne);
    await podmien(page, { wilgotnosc: { lazienka: 62 }, dom: { lazienka: { przewietrz: { od, wilg: 62, granica: 61.4 } } } }, '#dom');
    await expect(page.locator('#v-dom .podsum-l')).toContainText(/62% od 2\sgodz\. · za wilgotno od 61%$/);
    await page.goto('/index.html#lazienka');
    await gotowa(page);
    await expect(page.locator('.strona:not(.sasiad) .status').first()).toContainText(/za wilgotno od 61%\./);
    await expect(page.locator('.strona:not(.sasiad) .wart-op')).toContainText('granica 61%');
    expect(bledy).toEqual([]);
  });

  test('połówki i granica „przewietrz" tak samo jak w treściach dom.py (strażnik)', async ({ page }) => {
    // karta i powiadomienie liczą z tych samych liczb ze stan.json; reguła zaokrąglania i przecinka musi być wspólna
    const liczby = [62.5, 61.5, 60.5, 0.5, 63.45, 64.55];
    const pary = [[62, 61.6], [62, 61.4], [63, 62.5], [64, 63.5], [70, 63.2], [61, 60.5]];
    const py = JSON.parse(execFileSync('python3', ['-c', [
      'import sys, json; sys.path.insert(0, "."); import dom',
      'l, p = json.loads(sys.argv[1]), json.loads(sys.argv[2])',
      'g = [dom._linia_przewietrz({"nazwa": "X"}, {"od": "2026-10-11T10:00:00Z", "wilg": w, "granica": gr}, 1760180400000).split("powyżej ")[1].rstrip("%.") for w, gr in p]',
      'print(json.dumps([[dom._pl(x, 0) for x in l], g]))'].join('\n'), JSON.stringify(liczby), JSON.stringify(pary)], { cwd: REPO }).toString());
    const { bledy } = await otworz(page);
    const js = await page.evaluate(([l, p]) => [l.map((x) => SH.liczba(x, 0)), p.map(([w, gr]) => SH.tekstGranicy(gr, [w]))], [liczby, pary]);
    expect(js).toEqual(py);
    expect(bledy).toEqual([]);
  });

  test('skrót w nazwie pokoju zostaje wielkimi literami: „Przewietrz WC", jak w powiadomieniu (dom._mala)', async ({ page }) => {
    // pokój spoza pokoje.json: odmiany z nazwy czujnika, małą literą tylko wtedy, gdy druga litera jest mała
    const { bledy } = await otworz(page, { nazwy: { lazienka: 'WC' }, pokojeJson: ['salon', 'sypialnia', 'kuchnia'],
      dom: { lazienka: { przewietrz: { od: iso(Date.now() - 3 * GODZ), wilg: 72, granica: 63.2 } } } });
    await expect(page.locator('#v-dom .podsum-s')).toHaveText(/Przewietrz WC$/);
    await page.goto('/index.html#wc');
    await gotowa(page);
    await expect(page.locator('.strona:not(.sasiad) .status').first()).toContainText('Przewietrz WC');
    expect(bledy).toEqual([]);
  });

  test('strona nie liczy reguł drugi raz: wilgotno od tygodnia, ale kolektor mówi „nic" → nic', async ({ page }) => {
    // prototyp liczył „przewietrz" z serii w przeglądarce i przy 88% od tygodnia by go pokazał
    const { bledy } = await otworz(page, { wilgotnosc: { kuchnia: 88 } });
    await expect(page.locator('#v-dom .podsum-s')).toHaveText(/Wszystko w normie/);
    await page.goto('/index.html#kuchnia');
    await gotowa(page);
    expect(await page.locator('.strona:not(.sasiad) .status').count()).toBe(0);
    // ekran i tak pokazuje wilgotność ponad granicą — to wyświetlanie, nie reguła
    await expect(page.locator('.strona:not(.sasiad) .wart-op')).toContainText('za wilgotno —');
    expect(bledy).toEqual([]);
  });

  test('„zamknij okno?" ma pierwszeństwo przed „przewietrz"', async ({ page }) => {
    const od = Date.now() - 2 * GODZ;
    const { bledy } = await otworz(page, { dom: {
      sypialnia: { okno: { od: iso(od), przed: 21.2, teraz: 18.4, spadek: 2.8 } },
      kuchnia: { przewietrz: { od: iso(Date.now() - 4 * GODZ), wilg: 71, granica: 63 } },
    } });
    await expect(page.locator('#v-dom .podsum-s')).toHaveText(/Zamknij okno w sypialni\?/);
    await expect(page.locator('#v-dom .podsum-l')).toContainText('spadło 2,8°');
    await page.goto('/index.html#sypialnia');
    await gotowa(page);
    await expect(page.locator('.strona:not(.sasiad) .status.info')).toContainText('Okno otwarte?');
    expect(bledy).toEqual([]);
  });

  test('linia nocna tylko dla bieżącej albo nadchodzącej nocy', async ({ page }) => {
    const teraz = Date.now(), h = godzinaWaw(teraz);
    const noc = h >= 22 || h < 7 ? dataWaw(teraz - 12 * GODZ) : dataWaw(teraz);
    const wpis = { noc, t_min: 4, granica: 60.4, zwykle: 60.9, ostrz: true };
    const { bledy } = await otworz(page, { dom: { lazienka: { noc: wpis }, kuchnia: { noc: { ...wpis, noc: dataWaw(teraz - 3 * DOBA) } } } }, { hash: '#lazienka' });
    const linia = page.locator('.strona:not(.sasiad) [data-noc]');
    await expect(linia).toContainText(h < 7 ? 'Tej nocy' : 'Dziś w');
    await expect(linia).toContainText('za wilgotno od ok.');
    await expect(linia).toHaveClass(/warn-t/);
    await page.goto('/index.html#kuchnia');
    await gotowa(page);
    expect(await page.locator('.strona:not(.sasiad) [data-noc]').count()).toBe(0);
    expect(bledy).toEqual([]);
  });

  for (const [opis, opcje] of [['brak pliku', { dom: null }], ['zepsuty JSON', { dom: 'zly' }],
    ['plik starszy od zbiórki o 5 godz.', { dom: { kuchnia: { przewietrz: { od: iso(Date.now() - 9 * GODZ), wilg: 71, granica: 63 } } }, domUpdated: iso(Date.now() - 5 * GODZ) }]]) {
    test(`${opis}: brak reguł, bez błędu`, async ({ page }) => {
      const { bledy } = await otworz(page, opcje);
      await expect(page.locator('#v-dom .podsum-s')).toHaveText(/Wszystko w normie/);
      expect(bledy).toEqual([]);
    });
  }
});

test.describe('czujnik milczy i spóźniona zbiórka (D5)', () => {
  test('spóźniony kolektor: czujniki nie „milczą", a Dom mówi jedną linią o zbiórce', async ({ page }) => {
    const { bledy } = await otworz(page, { opoznienieZbiorki: 5 });
    await expect(page.locator('#v-dom .podsum-s')).toHaveText(/Wszystko w normie/);
    await expect(page.locator('#v-dom [data-spoznienie]')).toContainText('Ostatnia zbiórka 5');
    expect(await page.locator('.pokoj.stary').count()).toBe(0);
    await page.click('[data-tab="historia"]');
    await expect(page.locator('[data-nadaja]')).toHaveText('4 z 4 nadają');
    expect(bledy).toEqual([]);
  });

  test('martwy czujnik przy świeżej zbiórce: „Czujnik w kuchni milczy" i 3 z 4', async ({ page }) => {
    const { bledy } = await otworz(page, { martwy: 'kuchnia' });
    await expect(page.locator('#v-dom .podsum-s')).toHaveText(/Czujnik w kuchni milczy/);
    await expect(page.locator('[data-idz="kuchnia"].pokoj')).toHaveClass(/stary/);
    await expect(page.locator('[data-idz="kuchnia"].pokoj .pokoj-stary')).toContainText('brak odczytu od');
    expect(await page.locator('#v-dom [data-spoznienie]').count()).toBe(0);
    await page.click('[data-tab="historia"]');
    await expect(page.locator('[data-nadaja]')).toHaveText('3 z 4 nadają');
    expect(bledy).toEqual([]);
  });

  test('słaba bateria w opisie baterii', async ({ page }) => {
    const { bledy } = await otworz(page, { bateria: { pokoj: 'kuchnia', stan: 'low' } }, { hash: '#historia' });
    await expect(page.locator('#v-historia')).toContainText('Kuchnia słaba, reszta średnie');
    expect(bledy).toEqual([]);
  });
});

test.describe('obliczenia wyświetlania', () => {
  test('granica „za wilgotno" liczy się tak samo jak w kolektorze', async ({ page }) => {
    // te same liczby co test_prog_plesni_z_normy w tests/test_fetch.py
    const { bledy } = await otworz(page);
    const w = await page.evaluate(() => [11, 5, 0, -5, -10].map((d) => SH.granica(20, d)).concat([SH.granica(24, 30), SH.granica(null, 0), SH.stale.HUM_ALERT]));
    [67.6, 60.3, 54.7, 49.6, 44.9].forEach((v, i) => expect(w[i]).toBeCloseTo(v, 1));
    expect(w[5]).toBe(80);
    expect(w[6]).toBeNull();
    expect(w[7]).toBe(65);
    expect(bledy).toEqual([]);
  });

  test('filtr skoków: farelka zostaje, dłoń na czujniku znika', async ({ page }) => {
    const { bledy } = await otworz(page);
    const w = await page.evaluate(() => {
      // prawdziwe odczyty łazienki z 27.09.2026, minuty od 7:15
      const min = [0, 39, 41, 43, 45, 47, 49.2, 51.8, 55.2, 60, 64.3, 69, 73.8, 75.8, 77.8, 80.4, 84.1, 89.7, 98.2, 113.1, 129.1, 148.1, 185.6, 245.3];
      const v = [20.0, 20.5, 21.7, 22.7, 23.4, 23.9, 24.4, 24.9, 25.4, 25.9, 26.4, 26.9, 26.4, 25.7, 25.2, 24.7, 24.2, 23.7, 23.2, 22.7, 22.2, 21.7, 21.2, 20.9];
      const farelka = SH.despike(min.map((m, i) => ({ x: m * 60e3, y: v[i] })), 'temp').cut;
      const dlon = SH.despike([0, 60, 63, 69, 120].map((m, i) => ({ x: m * 60e3, y: [21, 21, 23.5, 21, 21][i] })), 'temp');
      return { farelka, dlon: dlon.cut, zostalo: dlon.pts.map((p) => p.y) };
    });
    expect(w.farelka).toBe(0);
    expect(w.dlon).toBe(1);
    expect(w.zostalo).toEqual([21, 21, 21, 21]);
    expect(bledy).toEqual([]);
  });

  test('seria godzinowa: (b − 1 godz., b], pusta godzina null, po filtrze skoków i bez artefaktów', async ({ page }) => {
    const { bledy } = await otworz(page, {
      skok: { pokoj: 'sypialnia', godzWstecz: 5, o: 6 },
      artefakty: [{ czujnik: 'salon', odGodz: 30, doGodz: 27, wartosc: 35 }],
      martwy: 'kuchnia',
    });
    const w = await page.evaluate(() => {
      const H = 36e5, s = SH.seriaGodzinowa([{ x: 10 * H, y: 20 }, { x: 10 * H + 1000, y: 22 }, { x: 11 * H - 1000, y: 24 }], 9 * H, 12 * H);
      const p = (id) => SH.dane.pokoje.find((x) => x.id === id);
      return { s, syp: Math.max(...p('sypialnia').seria.temp.filter((v) => v != null)), salon: Math.max(...p('salon').seria.temp.filter((v) => v != null)),
        kuchnia: p('kuchnia').seria.temp.slice(-8), dlugosc: p('salon').seria.temp.length };
    });
    expect(w.s).toEqual([null, 20, 23, null]);
    expect(w.dlugosc).toBe(169);
    expect(w.syp, 'skok dłoni nie wchodzi do średniej godziny').toBeLessThan(22.3);
    expect(w.salon, 'artefakt nie wchodzi do serii').toBeLessThan(30);
    expect(w.kuchnia.slice(-7).every((v) => v === null), 'cisza czujnika to dziura, a nie przeciągnięta wartość').toBe(true);
    expect(bledy).toEqual([]);
  });

  test('artefakt na ostatnich odczytach: kafel pokazuje odczyt (czujnik raportował), wykres i zakresy go nie mają; złe wpisy pominięte', async ({ page }) => {
    const { bledy } = await otworz(page, { artefakty: [{ czujnik: 'salon', odGodz: 3, doGodz: -1, wartosc: 35 }], zleArtefakty: true });
    const w = await page.evaluate(() => { const p = SH.dane.pokoje.find((x) => x.id === 'salon'); return { temp: p.temp, seria: p.seria.temp.slice(-2), milczy: SH.milczy('salon') }; });
    expect(w.temp).toBe(35);
    expect(w.seria, 'godziny pod artefaktem są puste').toEqual([null, null]);
    expect(w.milczy, 'ukryty odczyt to nie cisza czujnika').toBe(false);
    expect(bledy).toEqual([]);
  });

  test('komfort dziś zgadza się z niezależnym przeliczeniem', async ({ page }) => {
    const { bledy, pliki } = await otworz(page, { wilgotnosc: { kuchnia: 64 } });
    const k = await page.evaluate(() => SH.dane.komfort_dzis);
    const teraz = Date.now(), dzis = dataWaw(teraz);
    let polnoc = null;
    for (let off = -3; off <= 3 && polnoc == null; off++) {
      const a = dzis.split('-').map(Number), t = Date.UTC(a[0], a[1] - 1, a[2]) + off * GODZ;
      if (dataWaw(t) === dzis && godzinaWaw(t) === 0 && new Date(t).getUTCMinutes() === 0) polnoc = t;
    }
    const wiersze = Object.keys(pliki).filter((x) => /^data\/\d{4}-\d\d\.csv$/.test(x)).flatMap((x) => pliki[x].trim().split('\n').slice(1)).map((r) => r.split(','));
    for (const id of ['salon', 'sypialnia', 'kuchnia', 'lazienka']) {
      const kub = {};
      for (const [ts, dev, code, v] of wiersze) {
        const t = Date.parse(ts);
        if (dev !== id || t < polnoc || t > teraz || code === 'battery_state') continue;
        const b = Math.floor(t / GODZ), q = kub[b] || (kub[b] = { T: [], H: [] });
        (code === 'va_temperature' ? q.T : q.H).push(+v);
      }
      const pkt = Object.values(kub).filter((q) => q.T.length && q.H.length).map((q) => [q.T.reduce((a, b) => a + b) / q.T.length, q.H.reduce((a, b) => a + b) / q.H.length]);
      const wpis = k.find((x) => x.id === id);
      if (!pkt.length) { expect(wpis, id).toBeUndefined(); continue; }
      const w = pkt.filter(([t, h]) => t >= 20 && t <= 24 && h >= 40 && h <= 60).length;
      expect(wpis.proc, id).toBe(Math.round(100 * w / pkt.length));
    }
    if (k.find((x) => x.id === 'kuchnia')) expect(k.find((x) => x.id === 'kuchnia').glownie).toBe('wilgotno');
    await page.goto('/index.html#kuchnia');
    await gotowa(page);
    if (k.find((x) => x.id === 'kuchnia')) await expect(page.locator('.strona:not(.sasiad)')).toContainText('wilgotność ponad 60%');
    expect(bledy).toEqual([]);
  });
});

test.describe('rośliny', () => {
  test('stałe gatunku i nazwa pełna ze stan.json, nie ze stałych w kodzie', async ({ page }) => {
    const { bledy } = await otworz(page, {}, { hash: '#fikus' });
    const t = await tekstStrony(page);
    expect(t).toMatch(/lubi 17–23\s°C/);
    expect(t).toContain("Fikus 'Ginseng' (Ficus microcarpa) · Salon");
    expect(bledy).toEqual([]);
  });

  test('ocena światła z swiatlo_ocena: „za ciemno" przy dobach, które próg 0,9 uznałby za niepełne', async ({ page }) => {
    // stara ocen() liczyła sama, z progiem pełnej doby 0,9: przy pokryciu 0,85 powiedziałaby „0 z 3 dób pomiaru"
    const teraz = Date.now();
    const doby = Array.from({ length: 30 }, (_, i) => ({ data: dataWaw(teraz - (29 - i) * DOBA), lxh: i === 29 ? 900 : 4400, pokrycie: i === 29 ? 0.4 : 0.85, szczyt_lx: 1033 }));
    const { bledy } = await otworz(page, { zmianyRoslin: { Fikus: { swiatlo_dobowe: doby, swiatlo_pelne_doby: 5,
      swiatlo_ocena: { kierunek: 'jasniej', u: 0.22, doby: doby.slice(-4, -1).map((d) => d.data), szczyt_lx: 1033 } } } }, { hash: '#fikus' });
    const s = page.locator('.strona:not(.sasiad)');
    await expect(s.locator('.powody')).toContainText('Za ciemno — przestaw bliżej okna');
    await expect(s.locator('.status')).toContainText('Przestaw bliżej okna.');
    await expect(s.locator('.status')).toContainText('Ostatnie 3 doby: średnio 22% potrzebnego światła. Fikus gubi liście po każdej przeprowadzce');
    // podpis doby: ten sam próg pełnej doby co rosliny.py (0,8)
    // (pierwszy wiersz to doba wbicia czujnika — „od 8:35", a nie pełna)
    await expect(s.locator('.sw-n').nth(1)).toContainText('pełna doba');
    await page.click('[data-tab="rosliny"]');
    await expect(page.locator('#v-rosliny .podtytul')).toContainText('Fikus: za ciemno');
    await expect(page.locator('[data-tab="rosliny"] .z-kropka')).toHaveCount(1);
    expect(bledy).toEqual([]);
  });

  test('„przestaw": procent z swiatlo_ocena.proc, tej samej liczby co w powiadomieniu; bez pola — z u', async ({ page }) => {
    // u = 0,285: w przeglądarce 0,285 · 100 = 28,499…, więc Math.round daje 28, a treść powiadomienia (rosliny.py,
    // połówka w górę z zapisu dziesiętnego) — 29. Kolektor podaje gotowy `proc` i to on trafia na kartę.
    const proc = +execFileSync('python3', ['-c', 'import sys; sys.path.insert(0, "."); import rosliny; print(rosliny._proc_swiatla(0.285))'], { cwd: REPO }).toString();
    expect(proc).toBe(29);
    const teraz = Date.now();
    const doby = Array.from({ length: 30 }, (_, i) => ({ data: dataWaw(teraz - (29 - i) * DOBA), lxh: 3700, pokrycie: i === 29 ? 0.4 : 1, szczyt_lx: 900 }));
    const ocena = (u, p) => ({ kierunek: 'jasniej', u, ...(p == null ? {} : { proc: p }), doby: doby.slice(-4, -1).map((d) => d.data), szczyt_lx: 900 });
    const { bledy } = await otworz(page, { zmianyRoslin: {
      Fikus: { swiatlo_dobowe: doby, swiatlo_pelne_doby: 5, swiatlo_ocena: ocena(0.285, proc) },
      Azalia: { swiatlo_dobowe: doby, swiatlo_pelne_doby: 5, swiatlo_ocena: ocena(0.226) },
    } }, { hash: '#fikus' });
    await expect(page.locator('.strona:not(.sasiad) .status')).toContainText('Ostatnie 3 doby: średnio 29% potrzebnego światła.');
    await page.goto('/index.html#azalia');
    await gotowa(page);
    await expect(page.locator('.strona:not(.sasiad) .status')).toContainText('Ostatnie 3 doby: średnio 23% potrzebnego światła.');
    expect(bledy).toEqual([]);
  });

  test('bez oceny światła: „Światło: N z 3 dób pomiaru" z liczby pełnych dób kolektora', async ({ page }) => {
    const { bledy } = await otworz(page, { zmianyRoslin: { Azalia: { swiatlo_ocena: null, swiatlo_pelne_doby: 2 } } }, { hash: '#azalia' });
    await expect(page.locator('.strona:not(.sasiad) .powody')).toContainText('Światło: 2 z 3 dób pomiaru');
    expect(bledy).toEqual([]);
  });

  test('próg pełnej doby w podpisie to ten sam co w rosliny.py (strażnik)', async ({ page }) => {
    const py = /^POKRYCIE_PELNEJ_DOBY\s*=\s*([\d.]+)/m.exec(fs.readFileSync(path.join(REPO, 'rosliny.py'), 'utf8'));
    expect(py, 'brak POKRYCIE_PELNEJ_DOBY w rosliny.py').not.toBeNull();
    const { bledy } = await otworz(page);
    expect(await page.evaluate(() => SH.stale.POKRYCIE_PELNEJ_DOBY)).toBe(+py[1]);
    expect(bledy).toEqual([]);
  });

  test('stan.json sprzed nowych pól: roślina bez pasma „lubi", ale bez błędu', async ({ page }) => {
    const { bledy } = await otworz(page, { stareRosliny: true }, { hash: '#azalia' });
    const t = await tekstStrony(page);
    expect(t).not.toMatch(/lubi|undefined|NaN/);
    expect(t).toContain('Azalia · Kuchnia');
    expect(bledy).toEqual([]);
  });

  test('błąd toru roślin: stan sprzed 30 godz. nie udaje dzisiejszego — linia z błędem, werdykty przygaszone', async ({ page }) => {
    // fetch.blad_toru_roslin zostawia poprzedni stan.json z jego `updated` i dopisuje `blad`
    const teraz = Date.now();
    const { bledy } = await otworz(page, { teraz, roslinyGora: { blad: 'Tuya: permission deny (1106)', updated: iso(teraz - 30 * GODZ) } }, { hash: '#rosliny' });
    const linia = page.locator('#v-rosliny [data-blad-roslin]');
    await expect(linia).toHaveText(/^Kolektor zgłosił błąd przy roślinach: Tuya: permission deny \(1106\) · stan sprzed 30\sgodz\.$/);
    const t = await page.locator('#v-rosliny').innerText();
    expect(t).not.toMatch(/w dobrej formie/);
    await expect(page.locator('#v-rosliny .rk.stare')).toHaveCount(3);
    expect(await page.locator('#v-rosliny .rk').first().getAttribute('aria-label')).toContain('stan sprzed 30');
    // szczegół: ta sama linia pod tytułem, werdykt przygaszony
    await page.click('[data-idz="azalia"]');
    const s = page.locator('.strona:not(.sasiad)');
    await expect(s.locator('h1 + [data-blad-roslin]')).toContainText('Kolektor zgłosił błąd przy roślinach: Tuya: permission deny (1106)');
    await expect(s.locator('.rd-poziom')).toHaveClass(/rd-stare/);
    expect(bledy).toEqual([]);
  });

  test('stary stan bez błędu: „Kolektor nie odświeżył roślin"; świeży stan bez błędu: bez linii', async ({ page }) => {
    const teraz = Date.now();
    const { bledy } = await otworz(page, { teraz, roslinyGora: { updated: iso(teraz - 5 * GODZ) } }, { hash: '#rosliny' });
    await expect(page.locator('#v-rosliny [data-blad-roslin]')).toHaveText(/^Kolektor nie odświeżył roślin · stan sprzed 5\sgodz\.$/);
    expect(await page.locator('#v-rosliny').innerText()).not.toMatch(/w dobrej formie/);
    await page.goto('/index.html#fikus');
    await gotowa(page);
    await expect(page.locator('.strona:not(.sasiad) [data-blad-roslin]')).toHaveCount(1);
    // ten sam stan 2 godz. za zbiórką to jeszcze nie „stary”
    await podmien(page, { teraz, roslinyGora: { updated: iso(teraz - 2 * GODZ) } }, '#rosliny');
    await expect(page.locator('#v-rosliny .podtytul')).toHaveText('Wszystkie trzy w dobrej formie');
    await expect(page.locator('#v-rosliny [data-blad-roslin]')).toHaveCount(0);
    expect(bledy).toEqual([]);
  });

  test('błąd jednej rośliny: zniknęła z listy, więc nie ma „Obie w dobrej formie", jest linia z błędem i chwilą danych', async ({ page }) => {
    const { bledy } = await otworz(page, { bezRoslin: ['Fikus'], roslinyGora: { blad: 'Fikus: błąd obliczeń — ValueError: x' } }, { hash: '#rosliny' });
    await expect(page.locator('#v-rosliny .rk')).toHaveCount(2);
    await expect(page.locator('#v-rosliny [data-blad-roslin]')).toHaveText(/^Kolektor zgłosił błąd przy roślinach: Fikus: błąd obliczeń — ValueError: x · dane z (dziś|wczoraj), \d+:\d\d$/);
    expect(await page.locator('#v-rosliny').innerText()).not.toMatch(/w dobrej formie/);
    // świeży stan: werdykty nie są przygaszone
    await expect(page.locator('#v-rosliny .rk.stare')).toHaveCount(0);
    expect(bledy).toEqual([]);
  });

  test('pusta lista z błędem: „Kolektor nie policzył stanu roślin" z treścią błędu, a nie rada o rosliny.json', async ({ page }) => {
    const { bledy } = await otworz(page, { rosliny: [], roslinyGora: { blad: 'rosliny.json: zły czujnik' } }, { hash: '#rosliny' });
    const b = page.locator('#v-rosliny [data-blad]');
    await expect(b).toContainText('Kolektor nie policzył stanu roślin');
    await expect(b).toContainText('rosliny.json: zły czujnik');
    await expect(b).not.toContainText('Dopisz je');
    expect(bledy).toEqual([]);
  });

  for (const [opis, opcje, tekst] of [['brak pliku', { rosliny: null }, 'Nie ma jeszcze danych z doniczek'],
    ['pusta lista', { rosliny: [] }, 'Brak roślin w konfiguracji']]) {
    test(`${opis}: komunikat na zakładce Rośliny, Dom działa`, async ({ page }) => {
      const { bledy } = await otworz(page, opcje, { hash: '#rosliny' });
      await expect(page.locator('#v-rosliny [data-blad]')).toContainText(tekst);
      await page.click('[data-tab="dom"]');
      await expect(page.locator('#v-dom .pokoj')).toHaveCount(4);
      expect(bledy).toEqual([]);
    });
  }
});

test.describe('powiadomienia: ustawienia telefonów przez API GitHuba (D11)', () => {
  const ZM = '/repos/Bronek31/Smart-Home/actions/variables';
  /** Atrapa api.github.com: `odp(metoda, sciezka)` zwraca {status, body} albo 'siec'. */
  async function atrapa(page, odp) {
    const zapytania = [];
    await page.route('https://api.github.com/**', async (route) => {
      const r = route.request(), u = new URL(r.url());
      if (r.method() === 'OPTIONS') return route.fulfill({ status: 204, headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' } });
      zapytania.push({ metoda: r.method(), sciezka: u.pathname, naglowki: r.headers(), cialo: r.postData() });
      const w = odp(r.method(), u.pathname);
      if (w === 'siec') return route.abort('internetdisconnected');
      return route.fulfill({ status: w.status, headers: { 'access-control-allow-origin': '*' }, contentType: 'application/json', body: w.body ? JSON.stringify(w.body) : '' });
    });
    return zapytania;
  }
  async function polacz(page, klucz = 'github_pat_test') {
    await page.fill('#klucz', klucz);
    await page.click('#polacz .przycisk');
  }

  test('bez klucza przełączniki są wygaszone, a zakładka nie pyta GitHuba', async ({ page }) => {
    const zap = await atrapa(page, () => ({ status: 500 }));
    const { bledy } = await otworz(page, {}, { hash: '#powiadomienia' });
    await expect(page.locator('#polacz')).toBeVisible();
    const sw = page.locator('[data-ust]');
    expect(await sw.count()).toBe(8);
    for (let i = 0; i < 8; i++) await expect(sw.nth(i)).toBeDisabled();
    await expect(page.locator('[data-godz="od"]')).toBeDisabled();
    expect(zap).toEqual([]);
    expect(bledy).toEqual([]);
  });

  test('Połącz: GET obu zmiennych (200 → zapisane, 404 → domyślne), klucz zapisany dopiero po sukcesie', async ({ page }) => {
    const android = { przewietrz: false, okno: true, czujniki: true, podlej: true, przestaw: false, czujnik: true, podsumowanie: true, cisza: true, od: 22, do: 7 };
    const zap = await atrapa(page, (m, s) => (s === `${ZM}/POWIADOMIENIA_ANDROID` ? { status: 200, body: { name: 'POWIADOMIENIA_ANDROID', value: JSON.stringify(android) } } : { status: 404, body: { message: 'Not Found' } }));
    const { bledy } = await otworz(page, {}, { hash: '#powiadomienia' });
    await polacz(page);
    await expect(page.locator('#polacz')).toHaveCount(0);
    await expect(page.locator('[data-ust="przewietrz"]')).toHaveAttribute('aria-checked', 'false');
    await expect(page.locator('[data-ust="podsumowanie"]')).toHaveAttribute('aria-checked', 'true');
    await expect(page.locator('.godz-w').first()).toContainText('22:00');
    await expect(page.locator('[data-ust="przewietrz"]')).toBeEnabled();
    await page.click('[data-tel="iphone"]');
    await expect(page.locator('[data-ust="przewietrz"]')).toHaveAttribute('aria-checked', 'true');
    await expect(page.locator('[data-ust="podsumowanie"]')).toHaveAttribute('aria-checked', 'false');
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem('sh.klucz')))).toBe('github_pat_test');
    const get = zap.filter((z) => z.metoda === 'GET');
    expect(get.map((z) => z.sciezka).sort()).toEqual([`${ZM}/POWIADOMIENIA_ANDROID`, `${ZM}/POWIADOMIENIA_IPHONE`]);
    for (const z of get) {
      expect(z.naglowki.authorization).toBe('Bearer github_pat_test');
      expect(z.naglowki.accept).toBe('application/vnd.github+json');
      expect(z.naglowki['x-github-api-version']).toBe('2022-11-28');
    }
    expect(bledy).toEqual([]);
  });

  for (const [status, tekst] of [[401, 'Klucz nie działa albo wygasł'], [403, 'Klucz nie ma uprawnienia Variables do Smart-Home'], ['siec', 'Brak połączenia']]) {
    test(`Połącz przy ${status}: komunikat, klucz nie zostaje w pamięci`, async ({ page }) => {
      await atrapa(page, () => (status === 'siec' ? 'siec' : { status, body: { message: 'x' } }));
      const { bledy } = await otworz(page, {}, { hash: '#powiadomienia' });
      await polacz(page);
      await expect(page.locator('#klucz-blad')).toHaveText(tekst);
      await expect(page.locator('#klucz')).toHaveAttribute('aria-invalid', 'true');
      expect(await page.evaluate(() => localStorage.getItem('sh.klucz'))).toBeNull();
      await expect(page.locator('[data-ust="okno"]')).toBeDisabled();
      expect(bledy).toEqual([]);
    });
  }

  test('zmiana przełącznika: od razu w UI, PATCH z JSON-em w kolejności DOMYSLNE (204)', async ({ page }) => {
    const zap = await atrapa(page, (m) => (m === 'GET' ? { status: 404 } : { status: 204 }));
    const { bledy } = await otworz(page, {}, { hash: '#powiadomienia' });
    await polacz(page);
    await page.click('[data-ust="okno"]');
    await expect(page.locator('[data-ust="okno"]')).toHaveAttribute('aria-checked', 'false');
    await expect(page.locator('#toast')).toContainText('Zapisano · Android');
    const p = zap.find((z) => z.metoda === 'PATCH');
    expect(p.sciezka).toBe(`${ZM}/POWIADOMIENIA_ANDROID`);
    const cialo = JSON.parse(p.cialo);
    expect(cialo.name).toBe('POWIADOMIENIA_ANDROID');
    expect(cialo.value).toBe('{"przewietrz":true,"okno":false,"czujniki":true,"podlej":true,"przestaw":true,"czujnik":true,"podsumowanie":false,"cisza":true,"od":21,"do":8}');
    // godzina ciszy
    await page.selectOption('[data-godz="od"]', '23');
    await expect(page.locator('.godz-w').first()).toContainText('23:00');
    await expect.poll(() => zap.filter((z) => z.metoda === 'PATCH').length).toBe(2);
    expect(JSON.parse(JSON.parse(zap.filter((z) => z.metoda === 'PATCH')[1].cialo).value).od).toBe(23);
    expect(bledy).toEqual([]);
  });

  test('cisza nocna Od = Do: wybór cofnięty z komunikatem, bez zapisu do GitHuba', async ({ page }) => {
    // telefony.w_ciszy uznaje od == do za brak ciszy: ekran mówiłby „Włączona”, a powiadomienia przychodziłyby w nocy
    const zap = await atrapa(page, (m) => (m === 'GET' ? { status: 404 } : { status: 204 }));
    const { bledy } = await otworz(page, {}, { hash: '#powiadomienia' });
    await polacz(page);
    // selectOption na wygaszonym polu sprzed połączenia trafiłby w element, który za chwilę zniknie
    await expect(page.locator('[data-godz="od"]')).toBeEnabled();
    await page.selectOption('[data-godz="od"]', '8');   // „Do” domyślnie 8:00
    await expect(page.locator('#toast')).toContainText('Od i Do muszą się różnić');
    await expect(page.locator('[data-godz="od"]')).toHaveValue('21');
    await expect(page.locator('.godz-w').first()).toContainText('21:00');
    await page.selectOption('[data-godz="do"]', '21');
    await expect(page.locator('[data-godz="do"]')).toHaveValue('8');
    await page.waitForTimeout(300);
    expect(zap.filter((z) => z.metoda !== 'GET')).toEqual([]);
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem('sh.ustawienia') || 'null'))).not.toMatchObject({ android: { od: 8 } });
    // inna godzina zapisuje się jak zwykle
    await page.selectOption('[data-godz="od"]', '22');
    await expect.poll(() => zap.filter((z) => z.metoda === 'PATCH').length).toBe(1);
    expect(JSON.parse(JSON.parse(zap.find((z) => z.metoda === 'PATCH').cialo).value)).toMatchObject({ od: 22, do: 8 });
    expect(bledy).toEqual([]);
  });

  test('zmiennej jeszcze nie ma: PATCH 404 → POST (201)', async ({ page }) => {
    const zap = await atrapa(page, (m) => (m === 'GET' ? { status: 404 } : m === 'PATCH' ? { status: 404 } : { status: 201 }));
    const { bledy } = await otworz(page, {}, { hash: '#powiadomienia' });
    await polacz(page);
    await page.click('[data-tel="iphone"]');
    await page.click('[data-ust="podsumowanie"]');
    await expect(page.locator('#toast')).toContainText('Zapisano · iPhone');
    const post = zap.find((z) => z.metoda === 'POST');
    expect(post.sciezka).toBe(ZM);
    expect(JSON.parse(post.cialo).name).toBe('POWIADOMIENIA_IPHONE');
    expect(JSON.parse(JSON.parse(post.cialo).value).podsumowanie).toBe(true);
    expect(bledy).toEqual([]);
  });

  test('błąd zapisu cofa przełącznik i mówi, co się stało; 401 wraca do „Połącz"', async ({ page }) => {
    let patch = 500;
    await atrapa(page, (m) => (m === 'GET' ? { status: 404 } : { status: patch }));
    const { bledy } = await otworz(page, {}, { hash: '#powiadomienia' });
    await polacz(page);
    await page.click('[data-ust="czujniki"]');
    await expect(page.locator('#toast')).toContainText('GitHub odpowiedział błędem (500)');
    await expect(page.locator('[data-ust="czujniki"]')).toHaveAttribute('aria-checked', 'true');
    patch = 401;
    await page.click('[data-ust="czujniki"]');
    await expect(page.locator('#klucz-blad')).toHaveText('Klucz nie działa albo wygasł');
    expect(await page.evaluate(() => localStorage.getItem('sh.klucz'))).toBeNull();
    expect(bledy).toEqual([]);
  });

  test('Odłącz usuwa klucz z telefonu', async ({ page }) => {
    await atrapa(page, () => ({ status: 404 }));
    const { bledy } = await otworz(page, {}, { hash: '#powiadomienia' });
    await polacz(page);
    await page.click('[data-akcja="odlacz"]');
    await page.click('[data-akcja="odlacz-tak"]');
    await expect(page.locator('#polacz')).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem('sh.klucz'))).toBeNull();
    await expect(page.locator('[data-ust="okno"]')).toBeDisabled();
    expect(bledy).toEqual([]);
  });

  test('„Ostatnie": z obu plików, tylko wysłane do telefonu, najnowsze na górze; bez dopisku o próbie przy „wlaczone"', async ({ page }) => {
    const t = (h) => iso(Date.now() - h * GODZ);
    const powDom = { tryb: 'wlaczone', wlaczone_od: t(48), historia: [
      { ts: t(2), regula: 'przewietrz', pokoje: ['Kuchnia'], tytul: 'Przewietrz kuchnię', tresc: '…', na_sucho: false, telefony: ['iphone'] },
      { ts: t(1), regula: 'okno', pokoje: ['Sypialnia'], tytul: 'Zamknij okno w sypialni?', tresc: '…', na_sucho: false, telefony: [] },
    ], stan_regul: {}, telefony: {} };
    const powRosliny = { tryb: 'wlaczone', wlaczone_od: t(48), historia: [
      { ts: t(5), regula: 'podlej', rosliny: ['Azalia'], tytul: 'Azalia: podlej dziś', tresc: '…', na_sucho: false },
      { ts: t(3), regula: 'podlej', rosliny: ['Fikus'], tytul: 'Fikus: próba', tresc: '…', na_sucho: true, telefony: ['android'] },
    ], stan_regul: {} };
    const { bledy } = await otworz(page, { powDom, powRosliny }, { hash: '#powiadomienia' });
    const w = page.locator('#pw-ostatnie .wiersz');
    await expect(w).toHaveCount(2);
    await expect(w.nth(0)).toContainText('Przewietrz kuchnię');
    await expect(w.nth(0)).toContainText('iPhone');
    await expect(w.nth(1)).toContainText('Azalia: podlej dziś');
    await expect(w.nth(1)).toContainText('Android i iPhone');
    expect(await page.locator('#v-powiadomienia').innerText()).not.toContain('w próbie');
    expect(bledy).toEqual([]);
  });

  test('tryb próby w pliku powiadomień: dopisek pod grupą', async ({ page }) => {
    const { bledy } = await otworz(page, { powRosliny: { tryb: 'na-sucho', historia: [] } }, { hash: '#powiadomienia' });
    await expect(page.locator('#v-powiadomienia')).toContainText('Powiadomienia o roślinach są w próbie i jeszcze nie przychodzą.');
    await expect(page.locator('#pw-ostatnie')).toContainText('Jeszcze nic nie wysłano');
    expect(bledy).toEqual([]);
  });
});

test.describe('licznik na ikonie (D10)', () => {
  async function atrapaLicznika(page, zgoda) {
    await page.addInitScript((z) => {
      window.__licznik = [];
      navigator.setAppBadge = (n) => { window.__licznik.push(n); return Promise.resolve(); };
      navigator.clearAppBadge = () => { window.__licznik.push(0); return Promise.resolve(); };
      Object.defineProperty(Notification, 'permission', { configurable: true, get: () => z });
    }, zgoda);
  }

  test('liczba spraw: pokoje z regułą albo ciszą i rośliny do podlania', async ({ page }) => {
    await atrapaLicznika(page, 'granted');
    const { bledy } = await otworz(page, { martwy: 'salon', dom: { kuchnia: { przewietrz: { od: iso(Date.now() - 3 * GODZ), wilg: 71, granica: 63 } } },
      zmianyRoslin: { Azalia: { werdykt: 'podlej' } } });
    await expect.poll(() => page.evaluate(() => window.__licznik[window.__licznik.length - 1])).toBe(3);
    expect(bledy).toEqual([]);
  });

  test('nic do zrobienia: licznik zdjęty; bez zgody na powiadomienia: nietknięty', async ({ page }) => {
    await atrapaLicznika(page, 'granted');
    const { bledy } = await otworz(page);
    await expect.poll(() => page.evaluate(() => window.__licznik.length)).toBeGreaterThan(0);
    expect(await page.evaluate(() => window.__licznik.every((n) => n === 0))).toBe(true);
    expect(bledy).toEqual([]);
  });

  test('bez zgody na powiadomienia licznik nie jest ustawiany', async ({ page }) => {
    await atrapaLicznika(page, 'default');
    const { bledy } = await otworz(page, { zmianyRoslin: { Azalia: { werdykt: 'pilne' } } });
    await page.evaluate(() => document.dispatchEvent(new Event('visibilitychange')));
    await page.waitForTimeout(200);
    expect(await page.evaluate(() => window.__licznik)).toEqual([]);
    expect(bledy).toEqual([]);
  });
});

test.describe('wejście z powiadomienia', () => {
  async function zostawCel(page, cel, ts) {
    await page.evaluate(async ({ cel, ts }) => {
      const c = await caches.open('cel-powiadomienia');
      await c.put('./cel', new Response(JSON.stringify({ cel, ts }), { headers: { 'Content-Type': 'application/json' } }));
    }, { cel, ts });
  }
  for (const [cel, oczekiwany] of [['rosliny.html#roslina=Azalia', '#azalia'], ['./#kuchnia', '#kuchnia'], ['rosliny.html', '#rosliny']]) {
    test(`zimny start z celem „${cel}" w Cache API → ${oczekiwany}, cel skasowany`, async ({ page }) => {
      const { bledy } = await otworz(page);
      await zostawCel(page, cel, Date.now());
      await page.goto('/index.html');
      await gotowa(page);
      await expect(page).toHaveURL(new RegExp(oczekiwany + '$'));
      expect(await page.evaluate(() => caches.has('cel-powiadomienia'))).toBe(false);
      if (oczekiwany !== '#rosliny') {
        await page.goBack();
        await expect(page).toHaveURL(new RegExp(oczekiwany === '#azalia' ? '#rosliny$' : '#dom$'));
      }
      expect(bledy).toEqual([]);
    });
  }

  test('stary cel (sprzed 10 min) nie przenosi, ale jest kasowany; adres ze szczegółem wygrywa', async ({ page }) => {
    const { bledy } = await otworz(page);
    await zostawCel(page, '#kuchnia', Date.now() - 10 * 60e3);
    await page.goto('/index.html');
    await gotowa(page);
    await page.waitForTimeout(300);
    await expect(page).toHaveURL(/#dom$/);
    expect(await page.evaluate(() => caches.has('cel-powiadomienia'))).toBe(false);
    await zostawCel(page, '#kuchnia', Date.now());
    await page.goto('/index.html#fikus');
    await gotowa(page);
    await page.waitForTimeout(300);
    await expect(page).toHaveURL(/#fikus$/);
    expect(bledy).toEqual([]);
  });

  test('cel kliknięcia od service workera przy otwartej aplikacji (postMessage) i obce adresy odrzucone', async ({ page }) => {
    const { bledy } = await otworz(page);
    const w = await page.evaluate(() => [SH.hashZCelu('rosliny.html#roslina=Fikus'), SH.hashZCelu('index.html#azalia'), SH.hashZCelu(location.origin + '/#salon'),
      SH.hashZCelu('https://example.com/#salon'), SH.hashZCelu('javascript:alert(1)'), SH.hashZCelu('#a b')]);
    expect(w).toEqual(['#roslina=Fikus', '#azalia', '#salon', null, null, null]);
    await page.evaluate(() => navigator.serviceWorker.dispatchEvent(new MessageEvent('message', { data: { typ: 'cel', cel: './#sypialnia' } })));
    await expect(page).toHaveURL(/#sypialnia$/);
    await page.goBack();
    await expect(page).toHaveURL(/#dom$/);
    expect(bledy).toEqual([]);
  });
});

test.describe('odświeżanie', () => {
  test('po powrocie do karty dociąga nowy odczyt i zostaje na tym samym widoku', async ({ page }) => {
    const { bledy, pliki } = await otworz(page, {}, { hash: '#kuchnia' });
    await expect(page.locator('.strona:not(.sasiad) .boh-t')).not.toContainText('30,0');
    const t = iso(Date.now());
    const m = JSON.parse(pliki['data/index.json']);
    m.updated = t;
    pliki['data/index.json'] = JSON.stringify(m);
    pliki[`data/${t.slice(0, 7)}.csv`] += `${t},kuchnia,va_temperature,30.0\n`;
    await page.evaluate(() => { SH.ustawOstatnieOdswiezenie(0); document.dispatchEvent(new Event('visibilitychange')); });
    await expect(page.locator('.strona:not(.sasiad) .boh-t')).toContainText('30,0');
    await expect(page).toHaveURL(/#kuchnia$/);
    expect(bledy).toEqual([]);
  });

  test('bez nowej zbiórki dane się nie przebudowują', async ({ page }) => {
    const { bledy } = await otworz(page);
    const ta = await page.evaluate(async () => { const przed = SH.dane; const nowe = await SH.odswiezDane(); return { nowe, ta: SH.dane === przed }; });
    expect(ta).toEqual({ nowe: false, ta: true });
    expect(bledy).toEqual([]);
  });

  for (const [opis, odp] of [['503', { status: 503, body: 'Service Unavailable' }], ['404 (Pages w trakcie wdrożenia)', null],
    ['portal Wi-Fi: HTML ze statusem 200', { status: 200, contentType: 'text/html', body: '<html><body>Zaloguj się do Wi-Fi</body></html>' }]]) {
    test(`manifest przy odświeżaniu: ${opis} → nic nie zmienia się na ekranie`, async ({ page }) => {
      const { bledy, pliki } = await otworz(page, { dom: { lazienka: { przewietrz: { od: iso(Date.now() - 2 * GODZ), wilg: 72, granica: 63 } } } }, { hash: '#lazienka' });
      const przed = await tekstStrony(page);
      pliki['data/index.json'] = odp;
      expect(await page.evaluate(() => SH.odswiezDane())).toBe(false);
      await expect(page).toHaveURL(/#lazienka$/);
      expect(await page.locator('[data-blad]').count()).toBe(0);
      expect(await tekstStrony(page)).toBe(przed);
      expect(bledy).toEqual([]);
    });
  }

  test('nowa zbiórka, ale miesiąc CSV odpowiada 503: widok zostaje, a następne odświeżenie dociąga dane', async ({ page }) => {
    const { bledy, pliki } = await otworz(page, {}, { hash: '#kuchnia' });
    const t = iso(Date.now()), mies = `data/${t.slice(0, 7)}.csv`, csv = pliki[mies];
    const m = JSON.parse(pliki['data/index.json']);
    m.updated = t;
    pliki['data/index.json'] = JSON.stringify(m);
    pliki[mies] = { status: 503, body: 'Service Unavailable' };
    expect(await page.evaluate(() => SH.odswiezDane())).toBe(false);
    await expect(page.locator('.strona:not(.sasiad) h1')).toHaveText('Kuchnia');
    expect(await page.locator('[data-blad]').count()).toBe(0);
    await page.click('[data-tab="dom"]');
    await expect(page.locator('#v-dom .pokoj')).toHaveCount(4);
    // serwer znowu działa: ten sam manifest, ale poprzednia próba się nie udała, więc dane przychodzą
    pliki[mies] = csv + `${t},kuchnia,va_temperature,30.0\n`;
    expect(await page.evaluate(() => SH.odswiezDane())).toBe(true);
    await expect(page.locator('[data-idz="kuchnia"] .pokoj-t')).toContainText('30,0');
    expect(bledy).toEqual([]);
  });

  test('pierwsze wczytanie z miesiącami 503: komunikat jak dotąd, a odświeżenie z tą samą zbiórką próbuje znowu', async ({ page }) => {
    const bledy = pilnujBledow(page);
    await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
    const pliki = await podstaw(page, {});
    const miesiace = Object.keys(pliki).filter((k) => /^data\/\d{4}-\d\d\.csv$/.test(k)), csv = {};
    for (const k of miesiace) { csv[k] = pliki[k]; pliki[k] = { status: 503, body: '' }; }
    await page.goto('/index.html#dom');
    await gotowa(page);
    await expect(page.locator('#v-dom [data-blad]')).toContainText('Pliki z danymi są puste');
    // nieudany miesiąc nie został zapamiętany jako pusty: serwer działa, manifest ten sam, a dane przychodzą
    Object.assign(pliki, csv);
    expect(await page.evaluate(() => SH.odswiezDane())).toBe(true);
    await expect(page.locator('#v-dom .pokoj')).toHaveCount(4);
    expect(bledy).toEqual([]);
  });

  test('plik nieobowiązkowy z błędem przy odświeżaniu: zostaje poprzednia wersja (reguły domu nie znikają)', async ({ page }) => {
    const { bledy, pliki } = await otworz(page, { dom: { kuchnia: { przewietrz: { od: iso(Date.now() - 3 * GODZ), wilg: 71, granica: 63.2 } } } });
    await expect(page.locator('#v-dom .podsum-s')).toHaveText(/Przewietrz kuchnię/);
    const m = JSON.parse(pliki['data/index.json']);
    m.updated = iso(Date.now());
    pliki['data/index.json'] = JSON.stringify(m);
    pliki['data/dom/stan.json'] = { status: 503, body: '' };
    expect(await page.evaluate(() => SH.odswiezDane())).toBe(true);
    await expect(page.locator('#v-dom .podsum-s')).toHaveText(/Przewietrz kuchnię/);
    expect(bledy).toEqual([]);
  });

  test('karta widoczna godzinami bez nowej zbiórki: co 10 min przerysowanie z zegarem („Ostatnia zbiórka 4 godz. temu")', async ({ page }) => {
    const teraz = Date.now();
    await page.clock.install({ time: teraz });
    const { bledy } = await otworz(page, { teraz });
    await expect(page.locator('#v-dom [data-spoznienie]')).toHaveCount(0);
    await page.clock.runFor(4 * GODZ);
    await expect(page.locator('#v-dom [data-spoznienie]')).toContainText(/Ostatnia zbiórka 4\sgodz\. temu/);
    expect(bledy).toEqual([]);
  });

  test('krótki powrót do karty przerysowuje widok bez pobierania („N min temu" idzie z zegarem)', async ({ page }) => {
    const teraz = Date.now();
    await page.clock.install({ time: teraz });
    const { bledy } = await otworz(page, { teraz }, { hash: '#kuchnia' });
    const pod = page.locator('.strona:not(.sasiad) .podtytul');
    await expect(pod).not.toContainText(/[45]\sgodz\. temu/);
    // karta w tle przez 4 godz. (interwał nic wtedy nie robi), a sprawdzenie manifestu było przed chwilą
    await page.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange')); });
    await page.clock.runFor(4 * GODZ);
    let zapytania = 0;
    page.on('request', (r) => { if (r.url().endsWith('/data/index.json')) zapytania++; });
    await page.evaluate(() => {
      SH.ustawOstatnieOdswiezenie(Date.now());
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await expect(pod).toContainText(/[45]\sgodz\. temu/);
    expect(zapytania).toBe(0);
    expect(bledy).toEqual([]);
  });

  test('krótki powrót do karty nie odpytuje serwera', async ({ page }) => {
    const { bledy } = await otworz(page);
    let zapytania = 0;
    page.on('request', (r) => { if (r.url().endsWith('/data/index.json')) zapytania++; });
    await page.evaluate(() => { SH.ustawOstatnieOdswiezenie(Date.now()); document.dispatchEvent(new Event('visibilitychange')); });
    await page.waitForTimeout(300);
    expect(zapytania).toBe(0);
    expect(bledy).toEqual([]);
  });
});

test.describe('układ na telefonie', () => {
  for (const szer of [390, 360, 320]) {
    test(`${szer} px: nic nie wystaje w poziomie na żadnej zakładce ani szczególe`, async ({ page }) => {
      await page.setViewportSize({ width: szer, height: 900 });
      const { bledy } = await otworz(page, { dom: { kuchnia: { przewietrz: { od: iso(Date.now() - 3 * GODZ), wilg: 71, granica: 63 } } } });
      for (const h of ['#dom', '#kuchnia', '#zewnatrz', '#rosliny', '#azalia', '#historia', '#powiadomienia']) {
        await page.goto('/index.html' + h);
        await gotowa(page);
        await page.waitForTimeout(150);
        const nadmiar = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
        expect(nadmiar, h).toBeLessThanOrEqual(0);
      }
      expect(bledy).toEqual([]);
    });
  }

  test('320 px: dolny wiersz kafla pokoju nie jest ucięty; 390 i 360 px mają podpis „24 h" jak w prototypie', async ({ page }) => {
    const { bledy } = await otworz(page, { trend: { salon: -0.2, sypialnia: 0.4, kuchnia: -1.2, lazienka: 0.6 } });
    for (const szer of [390, 360, 320]) {
      await page.setViewportSize({ width: szer, height: 900 });
      await page.waitForTimeout(100);
      const w = await page.evaluate(() => Array.prototype.map.call(document.querySelectorAll('#v-dom .pokoj-d'), (d) => ({
        nadmiar: d.scrollWidth - d.clientWidth, h24: !!Array.prototype.find.call(d.querySelectorAll('.zm-h'), (z) => z.getClientRects().length) })));
      expect(w.length, `${szer}`).toBe(4);
      for (const k of w) {
        expect(k.nadmiar, `${szer} px`).toBeLessThanOrEqual(0);
        expect(k.h24, `${szer} px: „24 h"`).toBe(szer >= 360);
      }
    }
    expect(bledy).toEqual([]);
  });

  test('bez zagnieżdżonych <svg> (WebKit rozdmuchuje je do rozmiaru rodzica)', async ({ page }) => {
    const { bledy } = await otworz(page);
    for (const h of ['#dom', '#kuchnia', '#azalia', '#historia']) {
      await page.goto('/index.html' + h);
      await gotowa(page);
      expect(await page.evaluate(() => document.querySelectorAll('svg svg').length), h).toBe(0);
    }
    expect(bledy).toEqual([]);
  });
});

test.describe('pliki towarzyszące', () => {
  /* Strażnik, nie test: iPhone'a w Chromium nie da się udać. Aplikacja z ekranu ma przezroczysty pasek stanu
     i bez tych trzech rzeczy nagłówek wchodzi pod zegar albo treść przewija się nad nim. */
  test('na iPhonie nagłówek zakrywa pas pod paskiem stanu (strażnik)', () => {
    expect(HTML).toMatch(/name="apple-mobile-web-app-status-bar-style" content="black-translucent"/);
    expect(HTML).toMatch(/name="viewport" content="[^"]*viewport-fit=cover/);
    expect(HTML).toMatch(/\.nav\{[^}]*position:sticky;top:0;[^}]*padding-top:env\(safe-area-inset-top,0px\);background:var\(--bg\)\}/);
  });

  test('pełny nagłówek PWA, bez modułów ES i bez Chart.js (strażnik)', () => {
    for (const w of [/<link rel="manifest" href="manifest.json">/, /<meta name="theme-color" content="#0f1419">/, /<link rel="apple-touch-icon" href="ikona-192.png">/,
      /<meta name="apple-mobile-web-app-capable" content="yes">/]) expect(HTML).toMatch(w);
    expect(HTML).not.toMatch(/<script[^>]+type=["']module["']/);
    expect(HTML).not.toMatch(/chart\.js|<script[^>]+src=/i);
    expect(HTML).not.toMatch(/pleśń|pleśni|pleśnią/i);
  });

  test.describe('z włączonym service workerem', () => {
    test.use({ serviceWorkers: 'allow' });
    test('rejestruje się i nie psuje strony na prawdziwych danych', async ({ page }) => {
      const bledy = pilnujBledow(page);
      await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
      await page.goto('/index.html');
      await gotowa(page);
      const gotowy = await page.evaluate(() => navigator.serviceWorker.ready.then((r) => !!r.active).catch(() => false));
      expect(gotowy, 'service worker powinien się zarejestrować').toBe(true);
      expect(bledy).toEqual([]);
    });
  });

  test('manifest PWA i service worker są na miejscu', async ({ request }) => {
    const m = await (await request.get('/manifest.json')).json();
    expect(m.start_url).toBe('./');
    expect(m.scope).toBe('./');
    for (const ikona of m.icons) expect((await request.get(`/${ikona.src}`)).status(), ikona.src).toBe(200);
    expect(await (await request.get('/sw.js')).text()).toContain('addEventListener');
  });
});

test.describe('czytelność wykresów (21.10)', () => {
  test('rytm doby: godzina bez odczytu w środku serii to ramka „brak odczytu”, a nie dziura; koniec serii bez ramek', async ({ page }) => {
    // Łazienka 20/21.10: wszystkie czujniki milczały ok. 3 godz., a mapa miała w tym miejscu po prostu nic
    const { bledy } = await otworz(page, { luka: { pokoj: 'kuchnia', odGodz: 30, doGodz: 27 } }, { hash: '#kuchnia' });
    const brak = page.locator('.strona:not(.sasiad) [data-rytm] rect.r-brak');
    expect(await brak.count()).toBeGreaterThanOrEqual(2);
    await brak.first().scrollIntoViewIfNeeded();
    const b = await brak.first().boundingBox();
    await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
    await expect(page.locator('.strona:not(.sasiad) .rytm-nagl')).toContainText('brak odczytu');
    // martwy czujnik od 9 godz.: to nie luka w środku, tylko koniec serii — „Czujnik milczy” mówi o tym osobno
    await podmien(page, { martwy: 'kuchnia' }, '#kuchnia');
    await expect(page.locator('.strona:not(.sasiad) [data-rytm] svg')).toBeVisible();
    expect(await page.locator('.strona:not(.sasiad) [data-rytm] rect.r-brak').count()).toBe(0);
    expect(bledy).toEqual([]);
  });

  test('gleba: podpisy osi czasu nie wchodzą na siebie przy 12 dobach na 360 px', async ({ page }) => {
    // Azalia 21.10: 24 podpisy („10.10”, „12:00”…) zlepione w jeden pasek pod wykresem
    await page.setViewportSize({ width: 360, height: 800 });
    const { bledy } = await otworz(page, { zmianyRoslin: { Azalia: { od: iso(Date.now() - 12 * DOBA) } } }, { hash: '#azalia' });
    const et = page.locator('.strona:not(.sasiad) [data-gleba] svg text.w-os');
    await expect(et.first()).toBeVisible();
    const pudla = [];
    for (const e of await et.all()) {
      const t = (await e.textContent()).trim();
      if (/^\d+\.\d\d$/.test(t) || /:00$/.test(t)) pudla.push(await e.boundingBox());
    }
    expect(pudla.length).toBeGreaterThanOrEqual(3);
    pudla.sort((a, b) => a.x - b.x);
    for (let i = 1; i < pudla.length; i++) expect(pudla[i].x, `podpis ${i}`).toBeGreaterThanOrEqual(pudla[i - 1].x + pudla[i - 1].width);
    expect(bledy).toEqual([]);
  });

  test('30 dni: podpisy z prawej przy krawędziach pola komfortu, nie przy osi', async ({ page }) => {
    // salon chłodnieje w przeszłość o 0,3° na dobę: 9 dób temu ok. 18 °C, więc oś schodzi poniżej pola komfortu
    const { bledy } = await otworz(page, { trend: { salon: 0.3 } }, { hash: '#historia' });
    const et = await page.locator('.m30-w').first().locator('text.m30-os').allTextContents();
    // dolny podpis to krawędź pola (20°), a nie dół osi — dawna wersja pisała tu „18°” i pole kończyło się bez liczby
    expect(et).toHaveLength(2);
    expect(et[0]).toBe('20°');
    expect(bledy).toEqual([]);
  });

  test('roślina za ciepło przez 3 doby: ile było i co zrobić; w zakresie — bez rady', async ({ page }) => {
    // Azalia w kuchni 18–21.10: stale 19–22 °C, a lubi do 18 — ekran mówił tylko „Trochę za ciepło”
    const { bledy } = await otworz(page, { zmianyRoslin: { Azalia: { temp_zakres: [10, 18] } } }, { hash: '#azalia' });
    await expect(page.locator('.strona:not(.sasiad) .powody')).toContainText('Od 3 dób ok. 20,5 °C, a lubi do 18 °C. Postaw w chłodniejszym miejscu');
    await podmien(page, {}, '#azalia');
    await expect(page.locator('.strona:not(.sasiad) .powody')).toBeVisible();
    await expect(page.locator('.strona:not(.sasiad) .powody')).not.toContainText('Od 3 dób');
    expect(bledy).toEqual([]);
  });
});
