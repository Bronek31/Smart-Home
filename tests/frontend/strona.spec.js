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

  test('historia nie kończy się na progu kroku animacji', () => {
    // floor(rozpiętość / krok) na okrągłej dobie dawał raz 119, raz 120 klatek —
    // zależnie od zaokrąglenia znacznika i szybkości wczytania strony. Zapas musi
    // zostać wyraźnie z dala od progu, inaczej migotanie wraca.
    const w = wiersze(zbuduj({}));
    const czas = (r) => Date.parse(r.split(',')[0]);
    const rozpietosc = Date.now() - Math.min(...w.map(czas));
    const KROK = 60 * 60e3;
    const ulamek = (rozpietosc % KROK) / KROK;
    expect(ulamek, 'rozpiętość historii wypada tuż przy wielokrotności kroku')
      .toBeGreaterThan(0.1);
    expect(ulamek).toBeLessThan(0.9);
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

  test('jedno kliknięcie to jeden przebieg, bez zapętlenia', async ({ page }) => {
    test.setTimeout(90000);
    const bledy = await otworz(page);
    const pozycja = () => page.$eval('#suwak', (s) => +s.value);

    await page.click('#play');
    await expect(page.locator('#play')).toHaveAttribute('aria-pressed', 'true');

    // przez cały przebieg suwak ma iść wyłącznie naprzód — spadek znaczyłby zawinięcie
    let poprzednia = await pozycja(), gra = true;
    for (let i = 0; i < 80 && gra; i++) {
      await page.waitForTimeout(250);
      const v = await pozycja();
      expect(v, 'suwak cofnął się — przebieg się zapętlił').toBeGreaterThanOrEqual(poprzednia);
      poprzednia = v;
      gra = await page.$eval('#play', (b) => b.getAttribute('aria-pressed') === 'true');
    }
    expect(gra, 'przebieg nie skończył się sam').toBe(false);

    // po przebiegu rzut wraca do stanu bieżącego i nic już się nie rusza
    await expect(page.locator('#plan-tytul')).toContainText('aktualny stan');
    expect(await pozycja()).toBe(await page.$eval('#suwak', (s) => +s.max));
    await page.waitForTimeout(700);
    expect(await pozycja()).toBe(await page.$eval('#suwak', (s) => +s.max));
    expect(bledy).toEqual([]);
  });

  test('pauza zatrzymuje tam, gdzie akurat jest', async ({ page }) => {
    const bledy = await otworz(page);
    await page.click('#play');
    await page.waitForTimeout(600);
    await page.click('#play');
    await expect(page.locator('#play')).toHaveAttribute('aria-pressed', 'false');
    const stoi = await page.$eval('#suwak', (s) => s.value);
    await page.waitForTimeout(700);
    expect(await page.$eval('#suwak', (s) => s.value)).toBe(stoi);
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

/* Dwór ma zupełnie inną rozpiętość niż mieszkanie: w fiksturze chodzi 10–26 °C, gdy
   pokoje stoją w paśmie poniżej stopnia. Na wspólnej osi cały ruch w mieszkaniu
   spłaszcza się do kilku pikseli — stąd druga oś po prawej. Wilgotność bezwzględna
   jest wyjątkiem i musi nim zostać, bo tam porównanie z dworem jest sensem wykresu. */
test.describe('osie wykresów', () => {
  const osie = (page, id) => page.evaluate((k) => {
    const ch = state.charts[k];
    return { y2: !!ch.scales.y2, dworNaY2: ch.data.datasets.filter((d) => d.borderDash.length).every((d) => d.yAxisID === 'y2') };
  }, id);

  test('temperatura i wilgotność względna dają dworowi własną oś', async ({ page }) => {
    const bledy = await otworz(page);
    for (const id of ['temp', 'hum']) {
      const o = await osie(page, id);
      expect(o.y2, `${id}: brak prawej osi`).toBe(true);
      expect(o.dworNaY2, `${id}: seria dworu nie trafiła na prawą oś`).toBe(true);
    }
    expect(bledy).toEqual([]);
  });

  test('wilgotność bezwzględna zostaje na jednej osi, bo porównuje z dworem', async ({ page }) => {
    const bledy = await otworz(page);
    const o = await osie(page, 'abs');
    expect(o.y2).toBe(false);
    expect(await page.evaluate(() => state.charts.abs.data.datasets.every((d) => (d.yAxisID || 'y') === 'y'))).toBe(true);
    expect(bledy).toEqual([]);
  });

  test('druga oś naprawdę rozciąga mieszkanie', async ({ page }) => {
    // sedno zmiany: bez niej lewa oś obejmowała cały zakres dworu
    const bledy = await otworz(page);
    const z = await page.evaluate(() => {
      const ch = state.charts.temp;
      return { lewa: ch.scales.y.max - ch.scales.y.min, prawa: ch.scales.y2.max - ch.scales.y2.min };
    });
    expect(z.prawa).toBeGreaterThan(z.lewa * 3);
    expect(bledy).toEqual([]);
  });

  test('prawa oś jest podpisana kolorem serii dworu', async ({ page }) => {
    const bledy = await otworz(page);
    const zgodne = await page.evaluate(() => {
      const ch = state.charts.temp;
      const dwor = state.devices.find((d) => d.ext);
      return ch.options.scales.y2.ticks.color === dwor.color;
    });
    expect(zgodne).toBe(true);
    await expect(page.locator('.trace h2 .osie').first()).toHaveText(/lewa oś: mieszkanie/);
    expect(bledy).toEqual([]);
  });
});

/* Linia pokoi jest wygładzona średnią z trzech odczytów, bo krok czujnika (0,1 °C, 1%)
   po rozdzieleniu osi urósł do kilkudziesięciu pikseli i krzywe zamieniły się w schodki.
   Rusza wyłącznie rysowana linia — dwór, tabela i dymek zostają przy surowych odczytach. */
test.describe('wygładzanie linii', () => {
  const seria = (page, wykres, nazwa) => page.evaluate(([w, n]) => {
    const ds = state.charts[w].data.datasets.find((d) => d.label === n);
    return ds ? ds.data.map((p) => ({ y: p.y, v: p.v })) : null;
  }, [wykres, nazwa]);

  test('pokój dostaje średnią z trzech odczytów, a surowy zostaje przy punkcie', async ({ page }) => {
    const bledy = await otworz(page, { waskaWilgotnosc: true });
    const p = await seria(page, 'temp', 'Salon');
    expect(p.length).toBeGreaterThan(5);
    expect(p.every((x) => x.v != null), 'zgubiony surowy odczyt').toBe(true);
    // środek każdej trójki to średnia sąsiadów i punktu
    for (let i = 1; i < p.length - 1; i++) {
      expect(p[i].y).toBeCloseTo((p[i - 1].v + p[i].v + p[i + 1].v) / 3, 6);
    }
    expect(bledy).toEqual([]);
  });

  test('dwór zostaje surowy', async ({ page }) => {
    const bledy = await otworz(page);
    for (const w of ['temp', 'hum', 'abs']) {
      const p = await seria(page, w, 'Na zewnątrz');
      expect(p, `${w}: brak serii dworu`).not.toBeNull();
      expect(p.every((x) => x.v === undefined), `${w}: dwór został wygładzony`).toBe(true);
    }
    expect(bledy).toEqual([]);
  });

  test('wygładzenie nie odsuwa linii dalej niż o krok czujnika', async ({ page }) => {
    const bledy = await otworz(page, { waskaWilgotnosc: true });
    const p = await seria(page, 'temp', 'Salon');
    const maks = Math.max(...p.map((x) => Math.abs(x.y - x.v)));
    expect(maks, `odsunięcie ${maks.toFixed(3)} °C przekracza krok czujnika`).toBeLessThan(0.1);
    expect(bledy).toEqual([]);
  });

  test('tabela zakresów liczy z surowych odczytów, nie z wygładzonej linii', async ({ page }) => {
    const bledy = await otworz(page, { waskaWilgotnosc: true });
    const zgodne = await page.evaluate(() => {
      const d = state.devices.find((x) => x.id === 'salon');
      const surowe = state.rows.filter((r) => r.id === d.id && r.code === d.temp).map((r) => r.v);
      const wiersz = [...document.querySelectorAll('#summary tbody tr')]
        .find((tr) => tr.children[0].textContent === 'Salon');
      const liczba = (i) => parseFloat(wiersz.children[i].textContent.replace(',', '.'));
      return { min: liczba(1), max: liczba(3),
               oczMin: +Math.min(...surowe).toFixed(1), oczMax: +Math.max(...surowe).toFixed(1) };
    });
    expect(zgodne.min).toBe(zgodne.oczMin);
    expect(zgodne.max).toBe(zgodne.oczMax);
    expect(bledy).toEqual([]);
  });

  test('agregaty dobowe nie są wygładzane drugi raz', async ({ page }) => {
    const bledy = await otworz(page);
    await page.click('.range[data-hours="0"]');
    await page.waitForTimeout(400);
    const p = await seria(page, 'temp', 'Salon');
    expect(p.every((x) => x.v === undefined), 'średnie dobowe zostały wygładzone').toBe(true);
    expect(bledy).toEqual([]);
  });
});

/* Podpis pod wykresem ma wskazywać jedną chwilę. Dwa razy „14.08" pod tym samym
   wykresem nie mówi nic — a dokładnie to wychodziło przy krótkiej historii w widoku
   „całość": krok podziałki liczy się z rozpiętości danych (doba), a format podpisu
   z wybranego zakresu (umowne 24*400 godz., czyli daty). */
test.describe('podziałka osi czasu', () => {
  const podpisy = (page) => page.evaluate(() => state.charts.temp.scales.x.ticks.map((t) => t.label));

  const DATA = /^\d\d\.\d\d$/;

  for (const [zakres, opis] of [['dzis', 'dziś'], ['168', '7 dni'], ['720', '30 dni'], ['0', 'całość']]) {
    test(`${opis}: data pod wykresem wskazuje jedną dobę`, async ({ page }) => {
      // Dwie doby historii — tyle zostało po ucięciu TUYA_SINCE i właśnie przy tak
      // krótkiej historii podpisy się dublowały. Powtórzona godzina na dwóch różnych
      // dobach jest w porządku, bo granice dób znaczy osobno data i jaśniejsza siatka;
      // powtórzona data nie, bo tych podziałek nie da się od siebie odróżnić.
      const bledy = await otworz(page, { dni: 2 });
      await page.click(`.range[data-hours="${zakres}"]`);
      await page.waitForTimeout(400);
      const p = await podpisy(page);
      expect(p.length, 'oś bez żadnego podpisu').toBeGreaterThan(0);
      const daty = p.filter((x) => DATA.test(x));
      expect(daty, `powtórzona data w podpisach: ${p.join(' ')}`).toEqual([...new Set(daty)]);
      expect(bledy).toEqual([]);
    });
  }

  test('data pojawia się tylko o północy albo przy kroku dobowym', async ({ page }) => {
    const bledy = await otworz(page, { dni: 2 });
    for (const zakres of ['dzis', '168', '720', '0']) {
      await page.click(`.range[data-hours="${zakres}"]`);
      await page.waitForTimeout(400);
      const zle = await page.evaluate(() => {
        const t = state.charts.temp.scales.x.ticks;
        const krok = t.length > 1 ? (t[1].value - t[0].value) / 3600e3 : 24;
        return t.filter((x) => /^\d\d\.\d\d$/.test(x.label)
          && new Date(x.value).getHours() !== 0 && krok < 24)
          .map((x) => `${x.label} o ${new Date(x.value).getHours()}:00`);
      });
      expect(zle, `zakres ${zakres}`).toEqual([]);
    }
    expect(bledy).toEqual([]);
  });

  test('przy agregatach dobowych podziałka nie schodzi poniżej doby', async ({ page }) => {
    const bledy = await otworz(page, { dni: 2 });
    await page.click('.range[data-hours="0"]');
    await page.waitForTimeout(400);
    const odstepy = await page.evaluate(() => {
      const t = state.charts.temp.scales.x.ticks.map((x) => x.value);
      return t.slice(1).map((v, i) => (v - t[i]) / 3600e3);
    });
    odstepy.forEach((h) => expect(h).toBeGreaterThanOrEqual(24));
    expect(bledy).toEqual([]);
  });
});

/* Oś pionowa ma ten sam obowiązek co pozioma: jedna kreska, jedna wartość. Wilgotność
   pokazujemy bez miejsc po przecinku, a pokoje stoją w paśmie kilku punktów — Chart.js
   dzielił wtedy oś co pół procenta i sąsiednie podpisy zaokrąglały się do tej samej
   liczby: „51 51 50 50 49 49 48 48 47 47 46". */
test.describe('podziałka osi pionowej', () => {
  for (const [id, nazwa] of [['temp', 'temperatura'], ['hum', 'wilgotność względna'], ['abs', 'wilgotność bezwzględna']]) {
    test(`${nazwa}: żaden podpis nie powtarza się`, async ({ page }) => {
      const bledy = await otworz(page, { waskaWilgotnosc: true });
      const osie = await page.evaluate((k) => {
        const ch = state.charts[k];
        return Object.fromEntries(Object.entries(ch.scales)
          .filter(([n]) => n !== 'x')
          .map(([n, s]) => [n, s.ticks.map((t) => t.label)]));
      }, id);
      for (const [os, podpisy] of Object.entries(osie)) {
        expect(podpisy, `${nazwa}, oś ${os}: ${podpisy.join(' ')}`).toEqual([...new Set(podpisy)]);
      }
      expect(bledy).toEqual([]);
    });
  }
});

/* Łuk doby ma odpowiadać na „która to była pora dnia" bez czytania stempla. */
test.describe('łuk doby', () => {
  test('rysuje łuk z horyzontem, wschodem i zachodem', async ({ page }) => {
    const bledy = await otworz(page);
    const svg = page.locator('#doba');
    await expect(svg).toBeVisible();
    const tresc = await svg.innerHTML();
    expect(tresc).toMatch(/<line/);                       // horyzont
    expect(tresc).toMatch(/<path/);                       // krzywa
    expect(await svg.getAttribute('aria-label')).toMatch(/(Dzień|Noc).*Wschód.*Zachód/s);
    expect(bledy).toEqual([]);
  });

  test('znacznik chodzi po łuku, nad horyzontem za dnia i pod nim w nocy', async ({ page }) => {
    const bledy = await otworz(page);
    // Klatki wybieramy po godzinie zegarowej, nie po ułamku suwaka. Krok animacji
    // wypada tu na godzinę, więc próbkowanie co 1/10 okna trafiało w kółko w te same
    // dwie pory doby i wyglądało, jakby znacznik stał w miejscu.
    const klatki = await page.evaluate(() => {
      const os = state.os, out = [];
      for (let g = 0; g < 24; g += 3) {
        for (let i = 0; i <= os.n; i++) {
          if (new Date(os.od + i * os.krok).getHours() === g) { out.push(i); break; }
        }
      }
      return out;
    });
    expect(klatki.length, 'okno nie pokrywa pełnej doby').toBeGreaterThan(6);
    const HOR = 46;                    // y horyzontu w układzie łuku
    const pozycje = new Set(); const rodzaje = new Set();
    const nad = []; const pod = [];
    for (const i of klatki) {
      await page.$eval('#suwak', (s, k) => { s.value = k; s.dispatchEvent(new Event('input')); }, i);
      const stan = await page.evaluate(() => {
        const c = [...document.querySelectorAll('#doba circle')].pop();
        return { x: +c.getAttribute('cx'), y: +c.getAttribute('cy'), noc: !!document.querySelector('#ksiezyc-maska') };
      });
      pozycje.add(stan.x); rodzaje.add(stan.noc);
      /* Nieostro, bo w samej chwili wschodu i zachodu znacznik leży na kresce — i tak
         ma być, skoro kreska jest właśnie progiem wschodu. Współrzędna zapisuje się
         z jednym miejscem po przecinku, więc „ułamek nad kreską" wychodzi równe 46
         i ostra nierówność wywracała test w te dni, w które próbkowana godzina wypadła
         tuż przy przecięciu. Siłę odzyskujemy na całym przebiegu, niżej. */
      if (stan.noc) { expect(stan.y, 'noc, a znacznik nad horyzontem').toBeGreaterThanOrEqual(HOR); pod.push(stan.y); }
      else { expect(stan.y, 'dzień, a znacznik pod horyzontem').toBeLessThanOrEqual(HOR); nad.push(stan.y); }
    }
    // łuk ma mieć realną wysokość, a nie leżeć płasko na kresce
    expect(Math.min(...nad), 'słońce w ciągu doby nie wzniosło się nad horyzont').toBeLessThan(HOR - 10);
    expect(Math.max(...pod), 'księżyc w ciągu doby nie zszedł pod horyzont').toBeGreaterThan(HOR + 3);
    expect(pozycje.size, 'znacznik stoi w miejscu').toBe(klatki.length);
    expect([...rodzaje].sort()).toEqual([false, true]);   // trafiliśmy i w dzień, i w noc
    expect(bledy).toEqual([]);
  });

  test('działa tak samo przy oknie dobowym', async ({ page }) => {
    const bledy = await otworz(page);
    await page.click('[data-okno="24"]');
    await page.waitForTimeout(300);
    await expect(page.locator('#doba')).toBeVisible();
    expect(await page.locator('#doba').getAttribute('aria-label')).toMatch(/(Dzień|Noc)/);
    expect(bledy).toEqual([]);
  });

  test('wschód wypada przed zachodem i oba są o sensownej porze', async ({ page }) => {
    const bledy = await otworz(page);
    const d = await page.evaluate(() => {
      const x = dobaDane(Date.now(), 50.2649, 19.0238);
      const godz = (ms) => (ms - x.t0) / 3600e3;
      return { w: godz(x.wschod), z: godz(x.zachod), gora: x.gora };
    });
    expect(d.w).toBeGreaterThan(2);
    expect(d.w).toBeLessThan(d.z);
    expect(d.z).toBeLessThan(23);
    expect(d.gora).toBeGreaterThan(10);      // w Katowicach słońce wychodzi wysoko nawet zimą
    expect(bledy).toEqual([]);
  });

  test('wysokość słońca zgadza się z rachunkiem astronomicznym', async ({ page }) => {
    // W południe w przesilenie słońce stoi dokładnie 90° − szerokość ± nachylenie osi
    // (23,44°). To sprawdza cały łańcuch naraz: deklinację, równanie czasu i kąt
    // godzinny. Gdyby którykolwiek człon wzoru się rozjechał, ta tożsamość pęka.
    const bledy = await otworz(page);
    const w = await page.evaluate(() => {
      const LAT = 50.2649, LON = 19.0238;
      const maks = (r, m, d) => Math.max(...Array.from({ length: 288 },
        (_, i) => wysokoscSlonca(Date.UTC(r, m, d) + i * 5 * 60e3, LAT, LON)));
      return { lato: maks(2026, 5, 21), zima: maks(2026, 11, 21), lat: LAT };
    });
    expect(w.lato).toBeCloseTo(90 - w.lat + 23.44, 0);
    expect(w.zima).toBeCloseTo(90 - w.lat - 23.44, 0);
    expect(bledy).toEqual([]);
  });

  test('bez współrzędnych łuk się nie pokazuje, a strona żyje dalej', async ({ page }) => {
    const bledy = await otworz(page, { bezMiejsca: true });
    await expect(page.locator('#doba')).toBeHidden();
    await expect(page.locator('#plan-tytul')).toContainText('aktualny stan');
    await expect(page.locator('#suwak')).toBeVisible();
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
