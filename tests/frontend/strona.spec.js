// Testy strony w prawdziwej przeglądarce.
//
// Cały index.html to jeden plik bez budowania, więc nie ma czego importować i testować
// w oderwaniu — testujemy to, co widzi użytkownik. Chart.js podstawiamy z node_modules
// zamiast ciągnąć z CDN: testy mają nie zależeć od cudzej dostępności, a przy okazji
// jeden z nich sprawdza właśnie to, co się dzieje, gdy CDN nie odpowiada.

const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const { podstaw } = require('./dane');

// oba pakiety mają zawężone "exports" i nie wypuszczają ani dist, ani package.json,
// więc sięgamy po katalog wprost — to zwykłe pliki w node_modules
const dist = (pakiet, plik) => path.join(__dirname, 'node_modules', pakiet, 'dist', plik);
const CHART = fs.readFileSync(dist('chart.js', 'chart.umd.js'), 'utf8');
const ADAPTER = fs.readFileSync(dist('chartjs-adapter-date-fns', 'chartjs-adapter-date-fns.bundle.js'), 'utf8');

/** Wyłapuje każdy błąd strony — żaden test nie ma prawa przejść przy czerwonej konsoli. */
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

/** Wspólny start: podstawione dane, podpięty Chart, strona gotowa.
 *
 * Czekamy na stempel w nagłówku, a nie na pojawienie się #app. boot() odsłania #app
 * jeszcze przed render(), więc oglądanie samej widoczności łapało stronę w połowie
 * rysowania — i testy potrafiły odczytać wartości sprzed pierwszego renderu. Stempel
 * ustawia się na samym końcu render(), a przy braku danych zmienia się na „brak danych",
 * więc jedno oczekiwanie obsługuje obie ścieżki. */
async function otworz(page, opcje = {}, { hash = '', cdnDziala = true } = {}) {
  const bledy = pilnujBledow(page);
  await podepnijChart(page, { cdnDziala });
  await podstaw(page, opcje);
  await page.goto(`/index.html${hash}`);
  await page.waitForFunction(
    () => !/wczytywanie/.test(document.getElementById('stamp').textContent),
    null, { timeout: 20000 });
  return bledy;
}

const wcisniety = (page, sel) =>
  page.$$eval(sel, (n) => n.filter((x) => x.getAttribute('aria-pressed') === 'true').map((x) => x.textContent));

/* Fikstura też potrafi się zepsuć i wtedy testy kłamią w obie strony. Ten zestaw
   pilnuje jej samej: przy opcji „trend" łatwo dopisać odczyt na istniejący znacznik
   i regresja liczy się wtedy z dwóch wartości naraz, a zbyt żywy rytm dobowy sam
   przebija próg trendu i „spokojny pokój" przestaje być spokojny o niektórych porach.
   Oba te błędy naprawdę przepuściły czerwone CI, zanim tu trafiły. */
test.describe('same dane testowe', () => {
  const { zbuduj } = require('./dane');
  const wiersze = (pliki) => Object.keys(pliki)
    .filter((k) => /^\d{4}-\d\d\.csv$/.test(k))
    .flatMap((k) => pliki[k].trim().split('\n').slice(1));

  for (const [opis, opcje] of [['domyślne', {}], ['z trendem', { trend: { pokoj: 'salon', tempo: 0.8 } }],
    ['z martwym czujnikiem', { martwy: 'kuchnia' }], ['z wietrzeniem', { wietrzenie: true }]]) {
    test(`${opis}: żaden odczyt nie jest zapisany dwa razy`, () => {
      const licznik = new Map();
      for (const r of wiersze(zbuduj(opcje))) {
        const [ts, id, code] = r.split(',');
        const klucz = `${ts}|${id}|${code}`;
        licznik.set(klucz, (licznik.get(klucz) || 0) + 1);
      }
      const podwojne = [...licznik].filter(([, n]) => n > 1).map(([k]) => k);
      expect(podwojne, 'ten sam znacznik zapisany dwa razy').toEqual([]);
    });
  }

  test('sam rytm dobowy nie przebija progu trendu', () => {
    // gdyby przebijał, „kafel milczy przy spokojnym pokoju" zależałby od godziny
    const A = 0.5, PROG = 0.25;
    let maks = 0;
    for (let g = 0; g < 24; g++) {
      const f = (h) => A * Math.sin(((h - 4) / 24) * 2 * Math.PI);
      const x = [0, 1, 2, 3, 4], y = x.map((i) => f(g + i));
      const sx = 2, sy = y.reduce((a, b) => a + b, 0) / 5;
      let gora = 0, dol = 0;
      x.forEach((xi, i) => { gora += (xi - sx) * (y[i] - sy); dol += (xi - sx) ** 2; });
      maks = Math.max(maks, Math.abs(gora / dol));
    }
    expect(maks).toBeLessThan(PROG * 0.7);
  });

  test('każdy plik miesięczny jest posortowany, tak jak zapisuje go kolektor', () => {
    const w = wiersze(zbuduj({}));
    expect(w).toEqual([...w].sort());
  });
});

test.describe('start strony', () => {
  test('wczytuje się i wypełnia wszystkie sekcje', async ({ page }) => {
    const bledy = await otworz(page);
    await expect(page.locator('#app')).toBeVisible();
    await expect(page.locator('#notice')).toBeHidden();
    await expect(page.locator('#pens .pen')).toHaveCount(5);          // 4 pokoje + dwór
    await expect(page.locator('#statusbar .statusbox')).toHaveCount(4);
    await expect(page.locator('#summary tbody tr').first()).toBeVisible();
    await expect(page.locator('#health tbody tr')).toHaveCount(4);     // sam dwór nie ma diagnostyki
    await expect(page.locator('#floor svg')).toBeVisible();
    await expect(page.locator('#wx-panel')).toBeVisible();
    expect(bledy).toEqual([]);
  });

  test('bez odczytów pokazuje komunikat zamiast pustych ramek', async ({ page }) => {
    const bledy = await otworz(page, { pusto: true });
    await expect(page.locator('#notice')).toBeVisible();
    await expect(page.locator('#notice')).toContainText('odczyt');
    expect(bledy).toEqual([]);
  });

  test('nazwa czujnika ze znacznikiem HTML nie rozjeżdża strony', async ({ page }) => {
    const bledy = await otworz(page, { nazwaZnacznik: true });
    // ma się pokazać jako tekst, a nie jako pogrubienie
    await expect(page.locator('#pens')).toContainText('Salon <b>"x"</b>');
    expect(await page.locator('#pens b b').count()).toBe(0);
    expect(bledy).toEqual([]);
  });
});

test.describe('zakresy', () => {
  for (const [zakres, opis] of [['dzis', 'dzisiaj'], ['168', 'ostatnie 7 dni'],
    ['720', 'ostatnie 30 dni'], ['0', 'cała historia']]) {
    test(`zakres wykresów „${zakres}" rysuje serie i podpisuje się jako „${opis}"`, async ({ page }) => {
      const bledy = await otworz(page);
      await page.click(`.range[data-hours="${zakres}"]`);
      await page.waitForTimeout(600);
      const serie = await page.evaluate(() => ['temp', 'hum', 'abs'].map((id) => {
        const ch = Chart.getChart(document.getElementById(id));
        return ch ? ch.data.datasets.reduce((a, d) => a + d.data.length, 0) : -1;
      }));
      for (const punkty of serie) expect(punkty).toBeGreaterThan(0);
      expect(bledy).toEqual([]);
    });
  }

  test('zakres tabeli jest niezależny od zakresu wykresów', async ({ page }) => {
    const bledy = await otworz(page);
    await page.click('[data-tab="720"]');
    await page.waitForTimeout(400);
    await expect(page.locator('#summary caption')).toContainText('ostatnie 30 dni');
    expect(await wcisniety(page, '.range[data-hours]')).toEqual(['dziś']);

    await page.click('.range[data-hours="168"]');
    await page.waitForTimeout(600);
    await expect(page.locator('#summary caption')).toContainText('ostatnie 30 dni');
    expect(await wcisniety(page, '[data-tab]')).toEqual(['30 dni']);
    expect(bledy).toEqual([]);
  });

  test('tabela liczy inne skrajne wartości dla innych okresów', async ({ page }) => {
    const bledy = await otworz(page);
    const maxTemp = async () => page.$eval('#summary tbody tr td:nth-child(4)', (td) => td.textContent);
    await page.click('[data-tab="dzis"]');
    await page.waitForTimeout(400);
    const dzis = await maxTemp();
    await page.click('[data-tab="168"]');
    await page.waitForTimeout(400);
    expect(await maxTemp()).not.toBe('–');
    expect(dzis).not.toBe('');
    expect(bledy).toEqual([]);
  });

  test('widok „całość" rysuje z agregatów i nie liczy wietrzeń', async ({ page }) => {
    const bledy = await otworz(page);
    await page.click('[data-tab="0"]');
    await page.waitForTimeout(400);
    await expect(page.locator('#summary caption')).toContainText('dobowe min/śr/max');
    const wietrz = await page.$$eval('#summary tbody tr', (n) =>
      n.map((r) => r.children[r.children.length - 1].textContent));
    expect(new Set(wietrz)).toEqual(new Set(['–']));
    expect(bledy).toEqual([]);
  });
});

test.describe('adres i przełączniki', () => {
  test('deep link ustawia zakres, ukryte czujniki i filtr', async ({ page }) => {
    const bledy = await otworz(page, {}, { hash: '#zakres=7d&bez=salon&filtr=0' });
    expect(await wcisniety(page, '.range[data-hours]')).toEqual(['7 dni']);
    expect(await page.isChecked('#filtr')).toBe(false);
    expect(await wcisniety(page, '#toggles .toggle')).not.toContain('Salon');
    const etykiety = await page.$$eval('#summary tbody tr td:first-child', (n) => n.map((x) => x.textContent));
    expect(etykiety).not.toContain('Salon');
    expect(bledy).toEqual([]);
  });

  test('wyłączenie czujnika zapisuje się w adresie', async ({ page }) => {
    const bledy = await otworz(page);
    await page.click('#toggles .toggle >> nth=0');
    await page.waitForTimeout(400);
    expect(page.url()).toContain('bez=');
    expect(bledy).toEqual([]);
  });

  test('nieznana nazwa w adresie jest pomijana bez wywrotki', async ({ page }) => {
    const bledy = await otworz(page, {}, { hash: '#zakres=7d&bez=nieistniejacy' });
    await expect(page.locator('#toggles .toggle')).toHaveCount(5);
    expect(bledy).toEqual([]);
  });
});

test.describe('rzut mieszkania i odtwarzanie', () => {
  test('suwak cofa rzut w czasie, „teraz" wraca', async ({ page }) => {
    const bledy = await otworz(page);
    await expect(page.locator('#plan-tytul')).toContainText('aktualny stan');
    await page.$eval('#suwak', (s) => { s.value = Math.floor(s.max / 2); s.dispatchEvent(new Event('input')); });
    await page.waitForTimeout(300);
    await expect(page.locator('#plan-tytul')).not.toContainText('aktualny stan');
    await expect(page.locator('#teraz')).toBeVisible();
    await page.click('#teraz');
    await page.waitForTimeout(300);
    await expect(page.locator('#plan-tytul')).toContainText('aktualny stan');
    expect(bledy).toEqual([]);
  });

  test('okno odtwarzania nie zależy od zakresu wykresów', async ({ page }) => {
    const bledy = await otworz(page);
    const klatki = () => page.$eval('#suwak', (s) => s.max);
    const przed = await klatki();
    for (const z of ['dzis', '720', '0']) {
      await page.click(`.range[data-hours="${z}"]`);
      await page.waitForTimeout(600);
      expect(await klatki()).toBe(przed);
    }
    await page.click('[data-okno="24"]');
    await page.waitForTimeout(400);
    expect(await klatki()).not.toBe(przed);
    expect(bledy).toEqual([]);
  });

  test('pętla zawija się, pauza trzyma pozycję, przebieg kończy się sam', async ({ page }) => {
    test.setTimeout(90000);
    const bledy = await otworz(page);
    await page.click('#play');
    await expect(page.locator('#play')).toHaveAttribute('aria-pressed', 'true');
    // zawinięcie: pozycja suwaka musi w którymś momencie spaść
    let poprzednia = -1, zawinelo = false;
    for (let i = 0; i < 60 && !zawinelo; i++) {
      const v = await page.$eval('#suwak', (s) => +s.value);
      if (v < poprzednia) zawinelo = true;
      poprzednia = v;
      await page.waitForTimeout(250);
    }
    expect(zawinelo, 'przebieg powinien wrócić na początek').toBe(true);

    await page.click('#play');
    await expect(page.locator('#play')).toHaveAttribute('aria-pressed', 'false');
    const stoi = await page.$eval('#suwak', (s) => s.value);
    await page.waitForTimeout(700);
    expect(await page.$eval('#suwak', (s) => s.value)).toBe(stoi);

    await page.click('#teraz');
    await page.click('#play');
    await expect(page.locator('#play')).toHaveAttribute('aria-pressed', 'false', { timeout: 60000 });
    await expect(page.locator('#plan-tytul')).toContainText('aktualny stan');
    expect(bledy).toEqual([]);
  });

  test('tryb odchyłki zmienia kolory, nie zmieniając liczb', async ({ page }) => {
    const bledy = await otworz(page);
    const stan = () => page.$$eval('#floor .rm-temp', (n) =>
      n.map((x) => ({ tekst: x.textContent, kolor: x.getAttribute('fill') })));
    const przed = await stan();
    await page.click('[data-tryb="odchylka"]');
    await page.waitForTimeout(400);
    const po = await stan();
    expect(po.map((x) => x.tekst)).toEqual(przed.map((x) => x.tekst));
    expect(po.map((x) => x.kolor)).not.toEqual(przed.map((x) => x.kolor));
    await expect(page.locator('#maplegend')).toContainText('od średniej pokoju');
    expect(bledy).toEqual([]);
  });

  test('rzut podpisuje strony świata', async ({ page }) => {
    await otworz(page);
    const strony = await page.$$eval('#floor .rm-strona', (n) => n.map((x) => x.textContent));
    expect(strony).toEqual(['południe', 'północ']);
  });
});

test.describe('rytm doby', () => {
  test('rysuje mapę, przełącza pokoje i trzyma wspólną skalę', async ({ page }) => {
    const bledy = await otworz(page);
    await expect(page.locator('#rytm')).toBeVisible();
    expect(await page.locator('#mapa .cell').count()).toBeGreaterThan(24);

    const skala = () => page.$eval('#rytm-skala', (e) => e.textContent.match(/[\d,]+°/g).slice(0, 2).join('-'));
    const wspolna = await skala();
    const pokoje = await page.$$eval('#rytm-wybor [data-rytm]', (n) => n.map((x) => x.textContent));
    for (const p of pokoje) {
      await page.click(`#rytm-wybor button:text-is("${p}")`);
      await page.waitForTimeout(200);
      expect(await skala(), `skala wspólna ma być ta sama dla ${p}`).toBe(wspolna);
    }
    await page.click('[data-rskala="pokoj"]');
    await page.waitForTimeout(300);
    expect(await skala()).not.toBe(wspolna);
    expect(bledy).toEqual([]);
  });

  test('mapa nie zależy od zakresu wykresów', async ({ page }) => {
    const bledy = await otworz(page);
    const naglowek = () => page.textContent('#rytm-info');
    const przed = await naglowek();
    for (const z of ['dzis', '0']) {
      await page.click(`.range[data-hours="${z}"]`);
      await page.waitForTimeout(600);
      expect(await naglowek()).toBe(przed);
    }
    expect(bledy).toEqual([]);
  });

  test('komórka niesie godzinę i odczyt w podpowiedzi', async ({ page }) => {
    await otworz(page);
    const tytul = await page.getAttribute('#mapa .cell[title]', 'title');
    expect(tytul).toMatch(/\d{2}\.\d{2} \d{2}:00 · [\d,]+ °C/);
  });
});

test.describe('podpowiedzi i diagnostyka', () => {
  test('kafel milczy przy spokojnym pokoju', async ({ page }) => {
    await otworz(page);
    await expect(page.locator('#pens')).not.toContainText('°/godz.');
  });

  test('kafel ostrzega, gdy pokój wyraźnie się nagrzewa', async ({ page }) => {
    const bledy = await otworz(page, { trend: { pokoj: 'salon', tempo: 0.8 } });
    await expect(page.locator('#pens')).toContainText(/↗/);
    expect(bledy).toEqual([]);
  });

  test('okno wietrzenia wychodzi z prognozy godzinowej', async ({ page }) => {
    const bledy = await otworz(page, { pogodaGodzinowa: 'sucho' });
    await expect(page.locator('.wx-okno')).toContainText(/wietrzyć|Sucho/);
    expect(bledy).toEqual([]);
  });

  test('przy parnej prognozie mówi wprost, że nie ma okna', async ({ page }) => {
    const bledy = await otworz(page, { pogodaGodzinowa: 'parno' });
    await expect(page.locator('.wx-okno')).toContainText('Brak dobrego okna');
    expect(bledy).toEqual([]);
  });

  test('stara pogoda bez prognozy godzinowej nie wywraca strony', async ({ page }) => {
    const bledy = await otworz(page, { pogodaGodzinowa: 'brak' });
    await expect(page.locator('.wx-tip')).toBeVisible();
    expect(await page.locator('.wx-okno').count()).toBe(0);
    expect(bledy).toEqual([]);
  });

  test('milczący czujnik trafia do zdarzeń i diagnostyki', async ({ page }) => {
    const bledy = await otworz(page, { martwy: 'kuchnia' });
    await expect(page.locator('#events')).toContainText('Kuchnia');
    await expect(page.locator('#health')).toContainText('Kuchnia');
    expect(bledy).toEqual([]);
  });

  test('słaba bateria trafia do zdarzeń', async ({ page }) => {
    const bledy = await otworz(page, { bateria: { pokoj: 'sypialnia', stan: 'low' } });
    await expect(page.locator('#events')).toContainText('bateria');
    expect(bledy).toEqual([]);
  });

  test('wietrzenie jest wykryte i policzone w tabeli', async ({ page }) => {
    const bledy = await otworz(page, { wietrzenie: true });
    await page.click('[data-tab="168"]');
    await page.waitForTimeout(500);
    const liczby = await page.$$eval('#summary tbody tr', (n) =>
      n.map((r) => r.children[r.children.length - 1].textContent).filter((x) => x !== '–').map(Number));
    expect(Math.max(...liczby)).toBeGreaterThan(0);
    expect(bledy).toEqual([]);
  });
});

test.describe('odporność', () => {
  test('brak Chart.js nie zabiera tabel ani nagłówka', async ({ page }) => {
    const bledy = await otworz(page, {}, { cdnDziala: false });
    await expect(page.locator('.plot-blad').first()).toBeVisible();
    await expect(page.locator('#summary tbody tr').first()).toBeVisible();
    await expect(page.locator('#health tbody tr')).toHaveCount(4);
    await expect(page.locator('#stamp')).toContainText('ostatni zapis');
    await expect(page.locator('#rytm')).toBeVisible();          // mapa rytmu nie potrzebuje Chart.js
    expect(bledy).toEqual([]);
  });

  test('suwak działa też bez wykresów', async ({ page }) => {
    const bledy = await otworz(page, {}, { cdnDziala: false });
    await page.$eval('#suwak', (s) => { s.value = 5; s.dispatchEvent(new Event('input')); });
    await page.waitForTimeout(300);
    await expect(page.locator('#plan-tytul')).not.toContainText('aktualny stan');
    expect(bledy).toEqual([]);
  });

  test('na telefonie nic nie wystaje w poziomie', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1400 });
    const bledy = await otworz(page);
    const nadmiar = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(nadmiar).toBeLessThanOrEqual(0);
    expect(bledy).toEqual([]);
  });

  test('wąska szyba 320 px też się mieści', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 1400 });
    await otworz(page);
    const nadmiar = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(nadmiar).toBeLessThanOrEqual(0);
  });
});

test.describe('pliki towarzyszące', () => {
  // jedyny test, w którym worker ma działać — reszta go blokuje, bo omijałby podstawione dane
  test.describe('z włączonym service workerem', () => {
    test.use({ serviceWorkers: 'allow' });
    test('rejestruje się i nie psuje strony na prawdziwych danych', async ({ page }) => {
      const bledy = pilnujBledow(page);
      await podepnijChart(page);
      await page.goto('/index.html');
      await page.waitForFunction(() =>
        !document.getElementById('app').hidden || !document.getElementById('notice').hidden,
        null, { timeout: 15000 });
      const gotowy = await page.evaluate(() =>
        navigator.serviceWorker.ready.then((r) => !!r.active).catch(() => false));
      expect(gotowy, 'service worker powinien się zarejestrować').toBe(true);
      expect(bledy).toEqual([]);
    });
  });

  test('manifest PWA i service worker są poprawne', async ({ page, request }) => {
    const m = await (await request.get('/manifest.json')).json();
    expect(m.start_url).toBe('./');
    expect(m.icons.length).toBeGreaterThan(0);
    for (const ikona of m.icons) {
      const r = await request.get(`/${ikona.src}`);
      expect(r.status(), `brak pliku ${ikona.src}`).toBe(200);
    }
    const sw = await (await request.get('/sw.js')).text();
    expect(sw).toContain('addEventListener');
  });
});
