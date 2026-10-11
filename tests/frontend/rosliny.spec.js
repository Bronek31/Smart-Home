// Powiadomienia na telefonie: subskrypcja Web Push (zakładka Powiadomienia w index.html, grupa „Ten telefon"),
// service worker (sw.js: push, licznik na ikonie, kliknięcie, cache) i przekierowanie dawnej zakładki rosliny.html.
//
// Do 11.10 to wszystko mieszkało w rosliny.html — osobnej stronie roślin z wykresami Chart.js. Rośliny są teraz
// zakładką aplikacji (ich wygląd testuje strona.spec.js), a tu zostało to, co łączy telefon z nadawcą. Nazwa pliku
// zostaje, jak nazwy w pamięci telefonów (rosliny-subskrypcja, IndexedDB rosliny/odebrane).
//
// Świadomie usunięte przy przenosinach (BRIEF5, D15):
// - test „strona mieszkania nie pobiera nic z data/rosliny" (warunek właściciela z 8.10). Zatwierdzony projekt to
//   jedna aplikacja z kropką na zakładce Rośliny i licznikiem na ikonie, więc index.html czyta data/rosliny/stan.json.
//   Warunek zastąpił niezmiennik: na Domu, stronach pokoi i Historii nie ma żadnych wartości z doniczek — pilnuje go
//   strona.spec.js;
// - testy wyglądu starej rosliny.html (karty, pasek gleby, wykresy Chart.js, pasek zakładek „Mieszkanie | Rośliny",
//   strażnik „te same skrypty co index.html") — tej strony już nie ma, jest przekierowanie (testy niżej).
//
// Telefonu w Chromium nie ma, więc Notification, PushManager, schowek i rejestracja workera są atrapami
// (rosliny-dane.js), które zapisują wywołania. Prawdziwe zostają WebCrypto, IndexedDB i Cache API — przez nie
// aplikacja rozmawia z sw.js. Obsługi z sw.js idą dwiema drogami: prawdziwy worker z pushem przez CDP oraz ten sam
// plik w zwykłej stronie z atrapą `self` — kliknięcia w powiadomienie nie da się w Chromium wywołać inaczej.

const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { podstaw } = require('./dane');
const {
  GODZ, DOBA, ANDROID, IPHONE, kluczPubliczny, atrapyPowiadomien, plikPowiadomien, wpis,
  stronaProby, zaladujSw, odebraneWStronie, celWCache,
} = require('./rosliny-dane');

const KORZEN = path.join(__dirname, '..', '..');
const INDEX = fs.readFileSync(path.join(KORZEN, 'index.html'), 'utf8');
const SW = fs.readFileSync(path.join(KORZEN, 'sw.js'), 'utf8');
const ROSLINY_HTML = fs.readFileSync(path.join(KORZEN, 'rosliny.html'), 'utf8');
const STALA_KLUCZA = /const VAPID_PUBLICZNY='([^']*)';/;
const KLUCZ_APLIKACJI = STALA_KLUCZA.exec(INDEX)[1];

/** Wyłapuje każdy błąd strony. 404 nieobowiązkowych plików to nie błąd strony, a przeglądarka loguje je sama. */
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
const stanTelefonu = (page) => page.locator('#pow-telefon');
/** Grupa „Ten telefon" rozstrzygnęła stan (już nie „Sprawdzam…"). */
const czekajNaTelefon = (page) => page.waitForFunction(() => {
  const el = document.getElementById('pow-telefon');
  return el && el.dataset.stan && el.dataset.stan !== 'sprawdzam';
}, null, { timeout: 20000 });

/**
 * Zakładka Powiadomienia z atrapami telefonu i danymi z dane.js.
 * klucz: null → stała VAPID pusta (aplikacja „przed konfiguracją"), napis → podmieniona, undefined → ta z repozytorium.
 */
async function otworzPowiadomienia(page, { klucz, dane = {}, atrapy = {} } = {}) {
  const bledy = pilnujBledow(page);
  await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
  const pliki = await podstaw(page, dane);
  if (klucz !== undefined) {
    await page.route('**/index.html', (r) => r.fulfill({ contentType: 'text/html; charset=utf-8',
      body: INDEX.replace(STALA_KLUCZA, `const VAPID_PUBLICZNY='${klucz || ''}';`) }));
  }
  await atrapyPowiadomien(page, atrapy);
  await page.goto('/index.html#powiadomienia');
  await gotowa(page);
  await czekajNaTelefon(page);
  return { bledy, pliki };
}

const nadmiarPoziomy = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

test.describe('stała VAPID', () => {
  test('w index.html dokładnie raz, w postaci, którą czyta nadawca; w rosliny.html i sw.js wcale (strażnik)', () => {
    /* Strażnik, nie test zachowania: wyslij.py wyciąga klucz z index.html wyrażeniem regularnym i porównuje
       z kluczem wyliczonym z sekretu. Inny zapis (cudzysłów, spacje, drugie przypisanie, przykład w komentarzu)
       i nadawca nie znajdzie klucza albo weźmie zły — a telefony mają subskrypcje założone tym jednym kluczem. */
    const trafienia = [...INDEX.matchAll(/const VAPID_PUBLICZNY='([^']*)';/g)];
    expect(trafienia).toHaveLength(1);
    expect(trafienia[0][1]).toMatch(/^B[A-Za-z0-9_-]{86}$/);
    expect(INDEX.match(/VAPID_PUBLICZNY\s*=/g)).toHaveLength(1);
    expect(ROSLINY_HTML).not.toMatch(/VAPID/);
    expect(SW).not.toMatch(/VAPID_PUBLICZNY/);
  });
});

test.describe('słownictwo', () => {
  test('teksty powiadomień bez form rodzajowych (strażnik)', () => {
    /* Strażnik (D14): dawna rosliny.html mówiła „Jeśli sekret podmieniałeś przed chwilą" — przy przenosinach tekst
       dostał formę bezosobową. Pilnuje, żeby żadna forma „-łeś/-łaś" nie wróciła do aplikacji ani przekierowania. */
    const rodzajowa = /[a-ząćęłńóśźż](?:łeś|łaś|łyście)(?![a-ząćęłńóśźż])|eś\/aś/i;
    expect(INDEX).not.toMatch(rodzajowa);
    expect(ROSLINY_HTML).not.toMatch(rodzajowa);
    expect(INDEX).toContain('Jeśli sekret był podmieniony przed chwilą');
  });
});

test.describe('Ten telefon: subskrypcja Web Push', () => {
  test('pusta stała: para kluczy z przeglądarki w postaci dla nadawcy, a prywatny nigdzie nie zostaje', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 1400 });
    const { bledy } = await otworzPowiadomienia(page, { klucz: null });
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'klucze');
    await expect(page.locator('#pow-klucze-wynik')).toBeHidden();
    await page.getByRole('button', { name: 'Utwórz klucze' }).click();
    await expect(page.locator('#pow-klucze-wynik')).toBeVisible();
    const prywatny = await page.locator('#pow-prywatny').inputValue();
    const publiczny = await page.locator('#pow-publiczny').inputValue();
    expect(prywatny).toMatch(/^[A-Za-z0-9_-]{43}$/);              // 32 B, JWK `d`
    expect(publiczny).toMatch(/^B[A-Za-z0-9_-]{86}$/);            // 65 B, 0x04‖x‖y
    // Niezależnie od WebCrypto: z samego prywatnego (tylko on idzie do sekretu) Node wylicza ten sam publiczny —
    // to samo porównanie robi nadawca ze stałą w aplikacji.
    const ecdh = crypto.createECDH('prime256v1');
    ecdh.setPrivateKey(Buffer.from(prywatny, 'base64url'));
    expect(ecdh.getPublicKey('base64url')).toBe(publiczny);
    await page.locator('button[data-pole="pow-prywatny"]').click();
    await expect(page.locator('button[data-pole="pow-prywatny"]')).toHaveText('Skopiowano');
    expect(await page.evaluate(() => window.atrapa.schowek)).toEqual([prywatny]);
    await expect(stanTelefonu(page)).toContainText('VAPID_KLUCZ_PRYWATNY');
    await expect(stanTelefonu(page)).toContainText('nie wysyłaj go do czatu');
    // druga para po cichu podmieniłaby pierwszą, już wklejoną do sekretu
    await expect(page.getByRole('button', { name: 'Utwórz klucze' })).toBeHidden();
    const pamiec = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }) + document.cookie);
    expect(pamiec).not.toContain(prywatny);
    expect(await nadmiarPoziomy(page)).toBeLessThanOrEqual(0);
    expect(bledy).toEqual([]);
  });

  test('włączenie na Androidzie: zgoda w geście, subskrypcja z kluczem aplikacji, JSON do PUSH_ANDROID, zapamiętany adres', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 1400 });
    const adres = 'https://fcm.googleapis.com/fcm/send/abc123';
    const { bledy } = await otworzPowiadomienia(page, { atrapy: { ua: ANDROID, nowa: adres } });
    await expect(page.locator('#tel-t')).toHaveText('Ten telefon (Android)');
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'wylaczone');
    await page.getByRole('button', { name: 'Włącz powiadomienia' }).click();
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'subskrypcja');
    const log = await page.evaluate(() => window.atrapa);
    expect(log.zgody).toBe(1);
    // iPhone pyta o zgodę tylko w geście: prośba musi wyjść, zanim obsługa kliknięcia na cokolwiek poczeka
    expect(log.zgodaWKliknieciu).toEqual([true]);
    expect(log.subskrypcje).toEqual([{ userVisibleOnly: true, klucz: KLUCZ_APLIKACJI }]);    // klucz ze stałej, bajt w bajt
    const tekst = await page.locator('#pow-subskrypcja').inputValue();
    const json = JSON.parse(tekst);
    expect(json.endpoint).toBe(adres);
    expect(Object.keys(json.keys).sort()).toEqual(['auth', 'p256dh']);
    await expect(stanTelefonu(page)).toContainText('PUSH_ANDROID');
    await expect(stanTelefonu(page)).not.toContainText('PUSH_IPHONE');
    await expect(stanTelefonu(page)).toContainText('Secrets and variables → Actions');
    // samo włączenie to jeszcze nie sekret — zapamiętuje dopiero „Kopiuj"
    expect(await page.evaluate(() => localStorage.getItem('rosliny-subskrypcja'))).toBeNull();
    await expect(page.locator('#pow-telefon button[data-push="kopiuj"]')).toBeFocused();
    await page.locator('#pow-telefon button[data-push="kopiuj"]').click();
    await expect(page.locator('#pow-telefon button[data-push="kopiuj"]')).toHaveText('Skopiowano');
    expect(await page.evaluate(() => window.atrapa.schowek)).toEqual([tekst]);
    const zapamietana = JSON.parse(await page.evaluate(() => localStorage.getItem('rosliny-subskrypcja')));
    expect(zapamietana.endpoint).toBe(adres);
    expect(await nadmiarPoziomy(page)).toBeLessThanOrEqual(0);
    // następne wejście: ta sama subskrypcja co w sekrecie → „włączone", bez ostrzeżeń
    await page.reload();
    await gotowa(page);
    await czekajNaTelefon(page);
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'wlaczone');
    await expect(stanTelefonu(page)).toContainText('Subskrypcja w sekrecie PUSH_ANDROID');
    await expect(page.locator('#pow-dochodza')).toBeHidden();
    // arkusz „Subskrypcja": ta sama subskrypcja do ponownego wklejenia
    await page.getByRole('button', { name: 'Pokaż subskrypcję' }).click();
    await expect(page.locator('#arkusz')).toBeVisible();
    await expect(page.locator('#arkusz-t')).toHaveText('Subskrypcja tego telefonu');
    expect(await page.locator('#pow-subskrypcja-ark').inputValue()).toBe(tekst);
    await page.locator('#arkusz button[data-push="kopiuj"]').click();
    await expect(page.locator('#arkusz button[data-push="kopiuj"]')).toHaveText('Skopiowano');
    // ponowne skopiowanie tej samej subskrypcji nie przesuwa chwili, od której liczy się „czy dochodzą"
    expect(JSON.parse(await page.evaluate(() => localStorage.getItem('rosliny-subskrypcja')))).toEqual(zapamietana);
    await page.click('#arkusz-gotowe');
    await expect(page.locator('#arkusz')).toBeHidden();
    expect(bledy).toEqual([]);
  });

  test('przerysowanie zakładki pokazuje od razu ostatni znany stan, bez „Sprawdzam…"', async ({ page }) => {
    const adres = 'https://fcm.googleapis.com/fcm/send/abc123';
    const { bledy } = await otworzPowiadomienia(page, { atrapy: { ua: ANDROID, zgoda: 'granted', subskrypcja: adres, zapamietana: { endpoint: adres, od: Date.now() - DOBA } } });
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'wlaczone');
    // przełącznik Android | iPhone przerysowuje całą zakładkę synchronicznie
    const zaraz = await page.evaluate(() => { document.querySelector('[data-tel="iphone"]').click(); return document.getElementById('pow-telefon').dataset.stan; });
    expect(zaraz).toBe('wlaczone');
    await expect(page.locator('[data-tel="iphone"]')).toHaveAttribute('aria-pressed', 'true');
    expect(bledy).toEqual([]);
  });

  for (const [opis, subskrypcja, oczekiwany] of [
    ['inna niż skopiowana', 'https://fcm.googleapis.com/fcm/send/nowy', 'https://fcm.googleapis.com/fcm/send/nowy'],
    ['zniknęła', null, 'https://fcm.googleapis.com/fcm/send/nowszy'],
  ]) {
    test(`subskrypcja ${opis} → „włącz ponownie i podmień sekret"`, async ({ page }) => {
      const { bledy } = await otworzPowiadomienia(page, { atrapy: { ua: ANDROID, zgoda: 'granted', subskrypcja,
        nowa: 'https://fcm.googleapis.com/fcm/send/nowszy',
        zapamietana: { endpoint: 'https://fcm.googleapis.com/fcm/send/stary', od: Date.now() - 5 * DOBA } } });
      await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'zmieniona');
      await expect(stanTelefonu(page)).toContainText('Subskrypcja się zmieniła');
      await expect(stanTelefonu(page)).toContainText('Włącz ponownie i podmień sekret PUSH_ANDROID');
      await page.getByRole('button', { name: 'Włącz powiadomienia' }).click();
      await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'subskrypcja');
      expect(JSON.parse(await page.locator('#pow-subskrypcja').inputValue()).endpoint).toBe(oczekiwany);
      expect(bledy).toEqual([]);
    });
  }

  test('subskrypcja ze starym kluczem (po wymianie pary) jest zastępowana nową', async ({ page }) => {
    const stary = kluczPubliczny();
    const adres = 'https://fcm.googleapis.com/fcm/send/stary';
    const { bledy } = await otworzPowiadomienia(page, { atrapy: { ua: ANDROID, subskrypcja: adres, kluczSubskrypcji: stary,
      nowa: 'https://fcm.googleapis.com/fcm/send/nowy', zapamietana: { endpoint: adres, od: Date.now() - DOBA } } });
    // ten sam adres co w sekrecie, ale nadawca podpisuje już innym kluczem — push by nie przeszedł
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'zmieniona');
    await page.getByRole('button', { name: 'Włącz powiadomienia' }).click();
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'subskrypcja');
    const log = await page.evaluate(() => window.atrapa);
    expect(log.wypisania).toBe(1);
    expect(log.subskrypcje).toEqual([{ userVisibleOnly: true, klucz: KLUCZ_APLIKACJI }]);
    expect(JSON.parse(await page.locator('#pow-subskrypcja').inputValue()).endpoint).toBe('https://fcm.googleapis.com/fcm/send/nowy');
    expect(bledy).toEqual([]);
  });

  for (const [opis, atrapy] of [['w Safari (bez PushManager)', { bezPush: true }], ['poza aplikacją z ekranu', {}]]) {
    test(`iPhone ${opis}: instrukcja zamiast przycisku`, async ({ page }) => {
      await page.setViewportSize({ width: 320, height: 1400 });
      const { bledy } = await otworzPowiadomienia(page, { atrapy: { ua: IPHONE, ...atrapy } });
      const tel = stanTelefonu(page);
      await expect(tel).toHaveAttribute('data-stan', 'iphone');
      for (const fraza of ['iOS 16.4', 'Safari', 'Do ekranu początkowego', 'Otwórz jako aplikację webową', 'z ikony', 'Powiadomienia']) {
        await expect(tel).toContainText(fraza);
      }
      await expect(tel.getByRole('button')).toHaveCount(0);
      expect(await nadmiarPoziomy(page)).toBeLessThanOrEqual(0);
      expect(bledy).toEqual([]);
    });
  }

  test('iPhone w aplikacji z ekranu: przycisk i sekret PUSH_IPHONE', async ({ page }) => {
    const { bledy } = await otworzPowiadomienia(page, { atrapy: { ua: IPHONE, standalone: true, nowa: 'https://web.push.apple.com/QAbc' } });
    await expect(page.locator('#tel-t')).toHaveText('Ten telefon (iPhone)');
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'wylaczone');
    await page.getByRole('button', { name: 'Włącz powiadomienia' }).click();
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'subskrypcja');
    await expect(stanTelefonu(page)).toContainText('PUSH_IPHONE');
    await expect(stanTelefonu(page)).not.toContainText('PUSH_ANDROID');
    expect(bledy).toEqual([]);
  });

  test('odmowa zgody, zgoda niedana i brak API nie wywracają zakładki', async ({ page }) => {
    const { bledy } = await otworzPowiadomienia(page, { atrapy: { ua: ANDROID, zgoda: 'denied' } });
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'odmowa');
    // droga w ustawieniach tego telefonu, bez cudzej
    await expect(stanTelefonu(page)).toContainText('Ustawienia → Aplikacje → Smart Home');
    await expect(stanTelefonu(page)).not.toContainText('iPhone:');
    const druga = await page.context().newPage();
    const { bledy: bledy2 } = await otworzPowiadomienia(druga, { atrapy: { ua: ANDROID, odpowiedz: 'default' } });
    await druga.getByRole('button', { name: 'Włącz powiadomienia' }).click();
    await expect(stanTelefonu(druga)).toHaveAttribute('data-stan', 'wylaczone');
    await expect(stanTelefonu(druga)).toContainText('Zgoda nie została udzielona');
    await expect(druga.getByRole('button', { name: 'Włącz powiadomienia' })).toBeEnabled();
    // druga odmowa daje ten sam ekran — przycisk nie może zostać wygaszony na „Włączam…"
    await druga.getByRole('button', { name: 'Włącz powiadomienia' }).click();
    await expect.poll(() => druga.evaluate(() => window.atrapa.zgody)).toBe(2);
    await expect(druga.locator('#pow-telefon button[data-push="wlacz"]')).toHaveText('Włącz powiadomienia');
    await expect(druga.locator('#pow-telefon button[data-push="wlacz"]')).toBeEnabled();
    const trzecia = await page.context().newPage();
    const { bledy: bledy3 } = await otworzPowiadomienia(trzecia, { atrapy: { bezApi: true } });
    await expect(stanTelefonu(trzecia)).toHaveAttribute('data-stan', 'brak-wsparcia');
    // reszta zakładki działa: ustawienia telefonów i lista „Ostatnie"
    await expect(trzecia.locator('[data-ust]')).toHaveCount(8);
    await expect(trzecia.locator('#pw-ostatnie')).toBeVisible();
    expect(bledy).toEqual([]);
    expect(bledy2).toEqual([]);
    expect(bledy3).toEqual([]);
  });

  test('wysłane do tego telefonu ponad godzinę temu i nieodebrane → „nie dochodzą"; zapis odbioru z sw.js je gasi', async ({ page }) => {
    const adres = 'https://web.push.apple.com/QAbc';
    // wpis z pliku domu, wysłany tylko na iPhone'a — liczą się oba pliki powiadomień
    const powDom = plikPowiadomien([wpis('20261011T120112Z-przewietrz', 2 * GODZ, { tytul: 'Przewietrz łazienkę', telefony: ['iphone'] })]);
    const { bledy } = await otworzPowiadomienia(page, {
      dane: { powDom },
      atrapy: { ua: IPHONE, standalone: true, zgoda: 'granted', subskrypcja: adres, zapamietana: { endpoint: adres, od: Date.now() - 3 * DOBA } },
    });
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'wlaczone');
    const ostrzezenie = page.locator('#pow-dochodza');
    await expect(ostrzezenie).toBeVisible();
    await expect(ostrzezenie).toContainText('Powiadomienia nie dochodzą');
    await expect(ostrzezenie).toContainText('Przewietrz łazienkę');
    await expect(ostrzezenie).toContainText('PUSH_IPHONE');
    // odbiór zapisuje ten sam kod co w sw.js — aplikacja musi umieć go przeczytać
    await page.evaluate(([zrodlo]) => new Function('self', 'indexedDB', `${zrodlo}\nreturn zapiszOdebrane;`)(
      { addEventListener() {} }, indexedDB)('20261011T120112Z-przewietrz'), [SW]);
    await page.evaluate(() => SH.odswiezTelefon());
    await expect(ostrzezenie).toBeHidden();
    expect(bledy).toEqual([]);
  });

  test('wpis wysłany tylko na drugi telefon nie liczy się do „nie dochodzą"', async ({ page }) => {
    const adres = 'https://web.push.apple.com/QAbc';
    // telefony.py odłożył go iPhone'owi (cisza nocna) albo iPhone ma tę regułę wyłączoną — nie miał prawa dojść
    const powRosliny = plikPowiadomien([wpis('A', 3 * GODZ, { telefony: ['android'] })]);
    const { bledy } = await otworzPowiadomienia(page, {
      dane: { powRosliny },
      atrapy: { ua: IPHONE, standalone: true, zgoda: 'granted', subskrypcja: adres, zapamietana: { endpoint: adres, od: Date.now() - 3 * DOBA } },
    });
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'wlaczone');
    await page.evaluate(() => SH.odswiezTelefon());
    await expect(page.locator('#pow-dochodza')).toBeHidden();
    expect(bledy).toEqual([]);
  });

  test('„Odnów subskrypcję" przy „nie dochodzą" wymienia martwą subskrypcję na nową', async ({ page }) => {
    const adres = 'https://web.push.apple.com/martwa';
    const { bledy } = await otworzPowiadomienia(page, {
      dane: { powRosliny: plikPowiadomien([wpis('A', 3 * GODZ)]) },
      atrapy: { ua: IPHONE, standalone: true, zgoda: 'granted', subskrypcja: adres, nowa: 'https://web.push.apple.com/zywa',
        zapamietana: { endpoint: adres, od: Date.now() - 3 * DOBA } },
    });
    await page.getByRole('button', { name: 'Odnów subskrypcję' }).click();
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'subskrypcja');
    // ta sama, martwa subskrypcja nic by nie dała — Apple dalej odpowiada 201
    expect(await page.evaluate(() => window.atrapa.wypisania)).toBe(1);
    expect(await page.evaluate(() => window.atrapa.zgodaWKliknieciu)).toEqual([true]);
    expect(JSON.parse(await page.locator('#pow-subskrypcja').inputValue()).endpoint).toBe('https://web.push.apple.com/zywa');
    await expect(page.locator('#pow-dochodza')).toBeHidden();
    expect(bledy).toEqual([]);
  });

  test('nieudane „Odnów": błąd na karcie, a ostrzeżenie zostaje z czynnym przyciskiem', async ({ page }) => {
    const adres = 'https://web.push.apple.com/martwa';
    const { bledy } = await otworzPowiadomienia(page, {
      dane: { powRosliny: plikPowiadomien([wpis('A', 3 * GODZ)]) },
      atrapy: { ua: IPHONE, standalone: true, zgoda: 'granted', subskrypcja: adres, zapamietana: { endpoint: adres, od: Date.now() - 3 * DOBA } },
    });
    // usługa push telefonu odmawia nowej subskrypcji
    await page.evaluate(() => { navigator.serviceWorker.ready.then((r) => { r.pushManager.subscribe = async () => { throw new Error('AbortError: usługa push niedostępna'); }; }); });
    await page.getByRole('button', { name: 'Odnów subskrypcję' }).click();
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'blad');
    await expect(stanTelefonu(page)).toContainText('usługa push niedostępna');
    await expect(page.locator('#pow-dochodza')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Odnów subskrypcję' })).toBeEnabled();
    expect(bledy).toEqual([]);
  });

  test('„nie dochodzą" liczy tylko wysłane do tego telefonu, po skopiowaniu i już rozstrzygnięte', async ({ page }) => {
    const { bledy } = await otworzPowiadomienia(page);
    const wyniki = await page.evaluate(() => {
      const t = Date.now(), H = 3600e3, od = t - 10 * H;
      const w = (id, temu, pola) => Object.assign({ id, ts: new Date(t - temu).toISOString(), na_sucho: false, tytul: id }, pola || {});
      const f = (historia, odebrane, tel = 'iphone') => { const x = SH.nieDotarlo(historia, new Set(odebrane), od, t, tel); return x ? x.id : null; };
      return {
        stareNieodebrane: f([w('A', 2 * H)], []),
        stareOdebrane: f([w('A', 2 * H)], ['A']),
        swiezeCzekaNaGodzine: f([w('A', 30 * 60e3)], []),
        naSucho: f([w('A', 2 * H, { na_sucho: true })], []),
        sprzedSkopiowania: f([w('A', 11 * H)], []),
        noweOdebraneKanalDziala: f([w('A', 3 * H), w('B', 2 * H)], ['B']),
        noweNieodebrane: f([w('A', 3 * H), w('B', 2 * H)], ['A']),
        swiezeNiePrzykrywaStarego: f([w('A', 3 * H), w('B', 10 * 60e3)], []),
        // dwa pliki sklejone: kolejność w tablicy nie jest kolejnością w czasie
        poCzasieNiePoKolejnosci: f([w('B', 2 * H), w('A', 3 * H)], ['A']),
        doDrugiegoTelefonu: f([w('A', 2 * H, { telefony: ['android'] })], []),
        doNikogo: f([w('A', 2 * H, { telefony: [] })], []),
        bezPolaTelefony: f([w('A', 2 * H)], []),
        doTegoTelefonu: f([w('A', 2 * H, { telefony: ['iphone'] })], []),
        komputerTylkoDoObu: f([w('A', 2 * H, { telefony: ['android'] })], [], null),
        komputerDoObu: f([w('A', 2 * H, { telefony: ['android', 'iphone'] })], [], null),
        pusto: f([], []),
      };
    });
    expect(wyniki).toEqual({
      stareNieodebrane: 'A', stareOdebrane: null, swiezeCzekaNaGodzine: null, naSucho: null,
      sprzedSkopiowania: null, noweOdebraneKanalDziala: null, noweNieodebrane: 'B',
      swiezeNiePrzykrywaStarego: 'A', poCzasieNiePoKolejnosci: 'B', doDrugiegoTelefonu: null, doNikogo: null,
      bezPolaTelefony: 'A', doTegoTelefonu: 'A', komputerTylkoDoObu: null, komputerDoObu: 'A', pusto: null,
    });
    expect(bledy).toEqual([]);
  });

  test('bez subskrypcji tego telefonu nie ma „nie dochodzą", choć wysłane nie dotarło', async ({ page }) => {
    const { bledy } = await otworzPowiadomienia(page, { dane: { powRosliny: plikPowiadomien([wpis('A', 2 * GODZ)]) },
      atrapy: { ua: ANDROID, zgoda: 'granted' } });
    await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'wylaczone');
    await expect(page.locator('#pow-dochodza')).toBeHidden();
    expect(bledy).toEqual([]);
  });

  test('grupa stoi na górze zakładki, nad kluczem i ustawieniami; bez rozwijanych sekcji', async ({ page }) => {
    const { bledy } = await otworzPowiadomienia(page, { atrapy: { ua: ANDROID } });
    const kolejnosc = await page.evaluate(() => [...document.getElementById('v-powiadomienia').children].map((e) => e.id || e.tagName.toLowerCase()).slice(0, 3));
    expect(kolejnosc).toEqual(['h1', 'ten-telefon', 'polacz']);
    expect(await page.locator('#v-powiadomienia details').count()).toBe(0);
    // przełączniki ustawień nie biorą przycisków tej grupy za swoje
    await expect(page.locator('[data-ust]')).toHaveCount(8);
    expect(bledy).toEqual([]);
  });

  for (const szer of [390, 360, 320]) {
    test(`${szer} px: subskrypcja, instrukcja iPhone'a i „nie dochodzą" mieszczą się w szerokości`, async ({ page }) => {
      await page.setViewportSize({ width: szer, height: 900 });
      const adres = 'https://web.push.apple.com/' + 'x'.repeat(150);
      const { bledy } = await otworzPowiadomienia(page, { dane: { powRosliny: plikPowiadomien([wpis('A', 3 * GODZ, { tytul: 'Podlej: azalia, skrzydłokwiat, fikus' })]) },
        atrapy: { ua: IPHONE, standalone: true, zgoda: 'granted', subskrypcja: adres, nowa: adres + 'n',
          zapamietana: { endpoint: adres, od: Date.now() - 3 * DOBA } } });
      await expect(page.locator('#pow-dochodza')).toBeVisible();
      expect(await nadmiarPoziomy(page)).toBeLessThanOrEqual(0);
      await page.getByRole('button', { name: 'Odnów subskrypcję' }).click();
      await expect(stanTelefonu(page)).toHaveAttribute('data-stan', 'subskrypcja');
      expect(await nadmiarPoziomy(page)).toBeLessThanOrEqual(0);
      expect(bledy).toEqual([]);
    });
  }
});

test.describe('sw.js', () => {
  test('szkielet: przekierowanie rosliny.html i plan pokoi offline, nowa wersja, szkielet z sieci (strażnik)', () => {
    const szkielet = /const SZKIELET = \[([^\]]+)\]/.exec(SW)[1];
    expect(szkielet).toContain("'./rosliny.html'");
    expect(szkielet).toContain("'./pokoje.json'");
    expect(szkielet).toContain("'./index.html'");
    // bez nowej wersji telefony z poprzednim szkieletem nie dociągną nowej aplikacji
    expect(SW).toMatch(/const WERSJA = 'smart-home-v6';/);
    expect(SW).toMatch(/new Request\(u, \{ cache: 'reload' \}\)/);
  });

  test('pobieranie: data/ i pokoje.json najpierw z sieci, potem z zapasu; api.github.com i POST bez workera', async ({ page }) => {
    await stronaProby(page);
    await page.evaluate(zaladujSw, [SW]);
    const o = new URL(page.url()).origin;
    // worker zapisuje do cache bez czekania na zapis — test czeka na wpis, zanim sprawdzi zapas
    const wCache = (u, tresc) => expect.poll(() => page.evaluate((u) => caches.match(u).then((r) => (r ? r.text() : null)), u)).toBe(tresc);
    // plan pokoi zmieniony na serwerze: druga odpowiedź z sieci, nie pierwsza z cache
    expect(await page.evaluate((u) => sw.pobierz(u), `${o}/pokoje.json`)).toBe('sieć 1');
    await wCache(`${o}/pokoje.json`, 'sieć 1');
    expect(await page.evaluate((u) => sw.pobierz(u), `${o}/pokoje.json`)).toBe('sieć 2');
    expect(await page.evaluate((u) => sw.pobierz(u), `${o}/data/dom/stan.json`)).toBe('sieć 3');
    await wCache(`${o}/pokoje.json`, 'sieć 2');
    await wCache(`${o}/data/dom/stan.json`, 'sieć 3');
    // bez zasięgu: ostatnie znane
    await page.evaluate(() => { window.siec.dziala = false; });
    expect(await page.evaluate((u) => sw.pobierz(u), `${o}/pokoje.json`)).toBe('sieć 2');
    expect(await page.evaluate((u) => sw.pobierz(u), `${o}/data/dom/stan.json`)).toBe('sieć 3');
    // ustawienia telefonów: zapamiętany odczyt zmiennej pokazałby ustawienia sprzed zmiany
    await page.evaluate(() => { window.siec.dziala = true; });
    expect(await page.evaluate(() => sw.pobierz('https://api.github.com/repos/Bronek31/Smart-Home/actions/variables/POWIADOMIENIA_ANDROID'))).toBeNull();
    expect(await page.evaluate((u) => sw.pobierz(u, 'POST'), `${o}/data/index.json`)).toBeNull();
    // fonty: z cache po pierwszym razie (adresy z wersją kroju)
    const f = 'https://fonts.gstatic.com/s/familjengrotesk/v8/a.woff2';
    expect(await page.evaluate((u) => sw.pobierz(u), f)).toBe('sieć 4');
    await wCache(f, 'sieć 4');
    expect(await page.evaluate((u) => sw.pobierz(u), f)).toBe('sieć 4');
  });

  test('data/ przy odpowiedzi z błędem (503, 404 z Pages): ostatnia dobra kopia; bez kopii — oryginalny błąd', async ({ page }) => {
    await stronaProby(page);
    await page.evaluate(zaladujSw, [SW]);
    const o = new URL(page.url()).origin;
    const odp = (u) => page.evaluate((u) => sw.odpowiedz(u), u);
    const wCache = (u, tresc) => expect.poll(() => page.evaluate((u) => caches.match(u).then((r) => (r ? r.text() : null)), u)).toBe(tresc);
    expect(await odp(`${o}/data/index.json`)).toEqual({ status: 200, tekst: 'sieć 1' });
    await wCache(`${o}/data/index.json`, 'sieć 1');
    // serwer odpowiada błędem: aplikacja dostaje ostatni dobry manifest, a nie „pliku nie ma” (to kasowałoby widok)
    for (const status of [503, 404]) {
      await page.evaluate((s) => { window.siec.status = s; }, status);
      expect(await odp(`${o}/data/index.json`), String(status)).toEqual({ status: 200, tekst: 'sieć 1' });
    }
    // plik nieobowiązkowy przed pierwszą zbiórką (np. data/dom/stan.json): nie ma kopii, więc 404 zostaje 404
    expect(await odp(`${o}/data/dom/stan.json`)).toEqual({ status: 404, tekst: 'sieć 4' });
    // błędna odpowiedź nie trafia do cache
    expect(await page.evaluate((u) => caches.match(u).then((r) => !!r), `${o}/data/dom/stan.json`)).toBe(false);
    // serwer wrócił: znowu świeże z sieci
    await page.evaluate(() => { window.siec.status = 200; });
    expect(await odp(`${o}/data/index.json`)).toEqual({ status: 200, tekst: 'sieć 5' });
  });

  test('push: zawsze pokazuje powiadomienie, a odbiór zapisuje w IndexedDB', async ({ page }) => {
    await stronaProby(page);
    await page.evaluate(zaladujSw, [SW]);
    const tresc = { title: 'Podlej: azalia', body: 'Azalia: gleba 41%.', tag: 'podlej-azalia', url: '#azalia', id: '20261011T140112Z-podlej' };
    await page.evaluate((t) => sw.push(t), JSON.stringify(tresc));
    await page.evaluate(() => sw.push('zwykły tekst zamiast JSON'));
    await page.evaluate(() => sw.push(null));
    await page.evaluate(() => sw.push('[1,2]'));
    await page.evaluate(() => sw.push(JSON.stringify({ title: 'Bez id' })));
    const pokazane = await page.evaluate(() => log.pokazane);
    expect(pokazane).toEqual([
      ['Podlej: azalia', { body: 'Azalia: gleba 41%.', icon: 'ikona-192.png', tag: 'podlej-azalia', renotify: true,
        data: { url: '#azalia', id: '20261011T140112Z-podlej' } }],
      // powiadomienia są o domu i o roślinach — zepsuta treść dostaje nazwę aplikacji, nie „Rośliny"
      ['Smart Home', { body: 'zwykły tekst zamiast JSON', icon: 'ikona-192.png', data: { url: '', id: null } }],
      ['Smart Home', { body: '', icon: 'ikona-192.png', data: { url: '', id: null } }],
      ['Smart Home', { body: '[1,2]', icon: 'ikona-192.png', data: { url: '', id: null } }],
      ['Bez id', { body: '', icon: 'ikona-192.png', data: { url: '', id: null } }],
    ]);
    expect(await odebraneWStronie(page)).toEqual(['20261011T140112Z-podlej']);
    // bez IndexedDB powiadomienie i tak wychodzi — Safari cofa zgodę za push bez powiadomienia
    await page.evaluate(zaladujSw, [SW, { bezIndexedDB: true }]);
    await page.evaluate((t) => sw.push(t), JSON.stringify(tresc));
    expect(await page.evaluate(() => log.pokazane.map((p) => p[0]))).toEqual(['Podlej: azalia']);
  });

  test('licznik na ikonie: tyle, ile powiadomień w centrum; bez Badging API albo z błędem powiadomienie i tak wychodzi', async ({ page }) => {
    await stronaProby(page);
    await page.evaluate(zaladujSw, [SW]);
    const p = (tag, id) => JSON.stringify({ title: tag, body: '', tag, url: '#dom', id });
    await page.evaluate((t) => sw.push(t), p('podlej-azalia', 'A'));
    await page.evaluate((t) => sw.push(t), p('przewietrz-lazienka', 'B'));
    // ponowienie z tym samym tagiem zastępuje poprzednie — w centrum nadal dwa
    await page.evaluate((t) => sw.push(t), p('podlej-azalia', 'C'));
    expect(await page.evaluate(() => log.licznik)).toEqual([1, 2, 2]);
    for (const licznik of ['brak', 'rzuca']) {
      await page.evaluate(zaladujSw, [SW, { licznik }]);
      await page.evaluate((t) => sw.push(t), p('okno-sypialnia', 'D' + licznik));
      expect(await page.evaluate(() => log.pokazane.map((x) => x[0])), licznik).toEqual(['okno-sypialnia']);
      expect(await page.evaluate(() => log.licznik), licznik).toEqual([]);
    }
    expect((await odebraneWStronie(page)).sort()).toEqual(['A', 'B', 'C', 'Dbrak', 'Drzuca']);
  });

  test('kliknięcie bez otwartego okna: nowe okno na celu z zakresu i cel w Cache API (zimny start iPhone\'a)', async ({ page }) => {
    await stronaProby(page);
    await page.evaluate(zaladujSw, [SW]);
    const Z = 'https://bronek31.github.io/Smart-Home/';
    const cele = await page.evaluate((z) => [
      '#azalia', 'rosliny.html#roslina=Skrzyd%C5%82okwiat', `${z}rosliny.html`, 'https://zly.example/#azalia', '//zly.example/x',
      '../inny/', 'https://bronek31.github.io/Smart-Home-zly/x', 'javascript:alert(1)', '/Smart-Home/../x', '%2e%2e/x',
      'http://bronek31.github.io/Smart-Home/#azalia', null, '',
    ].map((u) => sw.celKlikniecia(u, z)), Z);
    expect(cele).toEqual([`${Z}#azalia`, `${Z}rosliny.html#roslina=Skrzyd%C5%82okwiat`, `${Z}rosliny.html`, Z, Z, Z, Z, Z, Z, Z, Z, Z, Z]);

    const origin = new URL(page.url()).origin;
    await page.evaluate(() => sw.klik({ url: '#azalia', id: 'A' }));
    expect(await page.evaluate(() => log)).toMatchObject({ zamkniete: 1, otwarte: [`${origin}/#azalia`], nawigacje: [], wiadomosci: [] });
    const cel = await celWCache(page);
    expect(cel.cel).toBe('#azalia');
    expect(Math.abs(Date.now() - cel.ts)).toBeLessThan(60e3);
    // obcy adres w data.url → strona startowa, bez celu do przejęcia
    await page.evaluate(() => caches.delete('cel-powiadomienia'));
    await page.evaluate(() => sw.klik({ url: 'https://zly.example/', id: 'B' }));
    expect(await page.evaluate(() => log.otwarte[log.otwarte.length - 1])).toBe(`${origin}/`);
    expect(await celWCache(page)).toBeNull();
  });

  test('kliknięcie przy otwartej aplikacji: wiadomość z celem i fokus, bez navigate, openWindow i zapisu celu', async ({ page }) => {
    await stronaProby(page);
    const origin = new URL(page.url()).origin;
    for (const okno of [`${origin}/index.html#dom`, `${origin}/#rosliny`, `${origin}/`]) {
      await page.evaluate(zaladujSw, [SW, { okna: [{ url: okno }] }]);
      await page.evaluate(() => sw.klik({ url: '#lazienka', id: 'A' }));
      expect(await page.evaluate(() => log), okno).toMatchObject({ fokusy: 1, wiadomosci: [{ typ: 'cel', cel: `${origin}/#lazienka` }], nawigacje: [], otwarte: [] });
      // zapisany cel przerzuciłby następne uruchomienie z ikony do łazienki
      expect(await celWCache(page), okno).toBeNull();
    }
    // stary link z powiadomienia doręczonego przed zmianą: wiadomość z pełnym adresem — aplikacja go tłumaczy
    await page.evaluate(zaladujSw, [SW, { okna: [{ url: `${origin}/index.html` }] }]);
    await page.evaluate(() => sw.klik({ url: 'rosliny.html#roslina=Fikus', id: 'A' }));
    expect(await page.evaluate(() => log.wiadomosci)).toEqual([{ typ: 'cel', cel: `${origin}/rosliny.html#roslina=Fikus` }]);
  });

  test('kliknięcie przy starej stronie w oknie: fokus i pełne przejście; okno obce albo niesterowane — nowe okno', async ({ page }) => {
    await stronaProby(page);
    const origin = new URL(page.url()).origin;
    // dawna rosliny.html otwarta sprzed aktualizacji wiadomości nie rozumie — przejście ładuje aktualną aplikację
    await page.evaluate(zaladujSw, [SW, { okna: [{ url: `${origin}/rosliny.html#roslina=Fikus` }] }]);
    await page.evaluate(() => sw.klik({ url: '#fikus', id: 'A' }));
    expect(await page.evaluate(() => log)).toMatchObject({ fokusy: 1, nawigacje: [`${origin}/#fikus`], wiadomosci: [], otwarte: [] });
    // navigate() się nie udało: fokus już zużył kliknięcie — bez openWindow i bez zapisanego celu
    await page.evaluate(zaladujSw, [SW, { okna: [{ url: `${origin}/rosliny.html`, nawigacjaRzuca: true }] }]);
    await page.evaluate(() => sw.klik({ url: '#fikus', id: 'A' }));
    expect(await page.evaluate(() => log)).toMatchObject({ fokusy: 1, nawigacje: [], otwarte: [] });
    expect(await celWCache(page)).toBeNull();
    // okno, którym ten worker nie steruje — nowe okno z celem
    await page.evaluate(zaladujSw, [SW, { okna: [{ url: `${origin}/index.html`, niesterowane: true }] }]);
    await page.evaluate(() => sw.klik({ url: '#fikus', id: 'A' }));
    expect(await page.evaluate(() => log)).toMatchObject({ nawigacje: [], wiadomosci: [], otwarte: [`${origin}/#fikus`] });
    expect((await celWCache(page)).cel).toBe('#fikus');
    // karta innego projektu z tego samego originu (github.io) — nie nasza, zostaje w spokoju
    await page.evaluate(() => caches.delete('cel-powiadomienia'));
    await page.evaluate(zaladujSw, [SW, { zakres: `${origin}/Smart-Home/`, okna: [{ url: `${origin}/inny-projekt/` }] }]);
    await page.evaluate(() => sw.klik({ url: '#fikus', id: 'A' }));
    expect(await page.evaluate(() => log)).toMatchObject({ fokusy: 0, wiadomosci: [], nawigacje: [], otwarte: [`${origin}/Smart-Home/#fikus`] });
  });

  test('aktywacja v6 kasuje stare cache (v5 z dawną rosliny.html), ale nie cel kliknięcia', async ({ page }) => {
    await stronaProby(page);
    await page.evaluate(zaladujSw, [SW]);
    await page.evaluate(() => Promise.all(['smart-home-v4', 'smart-home-v5', 'smart-home-v6', 'cel-powiadomienia'].map((n) => caches.open(n))));
    await page.evaluate(() => sw.aktywuj());
    expect((await page.evaluate(() => caches.keys())).sort()).toEqual(['cel-powiadomienia', 'smart-home-v6']);
  });
});

test.describe('kliknięcie w powiadomienie a aplikacja', () => {
  test('otwarta aplikacja: sw.js przysyła cel, aplikacja przechodzi do niego z rodzicem pod spodem', async ({ page }) => {
    const bledy = pilnujBledow(page);
    await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
    await podstaw(page);
    await page.goto('/index.html#historia');
    await gotowa(page);
    await page.evaluate(zaladujSw, [SW, { okna: [{ url: await page.evaluate(() => location.href), doStrony: true }] }]);
    await page.evaluate(() => sw.klik({ url: '#azalia', id: 'A' }));
    await expect(page).toHaveURL(/\/index\.html#azalia$/);
    await expect(page.locator('.strona:not(.sasiad)')).toHaveAttribute('data-slug', 'azalia');
    await page.goBack();
    await expect(page).toHaveURL(/#rosliny$/);
    // stary adres z powiadomienia doręczonego przed zmianą
    await page.evaluate(() => sw.klik({ url: 'rosliny.html#roslina=Skrzyd%C5%82okwiat', id: 'B' }));
    await expect(page).toHaveURL(/#skrzydlokwiat$/);
    await page.evaluate(() => sw.klik({ url: '#lazienka', id: 'C' }));
    await expect(page).toHaveURL(/#lazienka$/);
    await page.goBack();
    await expect(page).toHaveURL(/#dom$/);
    expect(await celWCache(page)).toBeNull();
    expect(bledy).toEqual([]);
  });

  for (const [opis, url, oczekiwany, rodzic] of [
    ['nowy adres', '#skrzydlokwiat', '#skrzydlokwiat', '#rosliny'],
    ['stary adres', 'rosliny.html#roslina=Skrzyd%C5%82okwiat', '#skrzydlokwiat', '#rosliny'],
    ['pokój', '#kuchnia', '#kuchnia', '#dom'],
  ]) {
    test(`zimny start (${opis}): cel zapisany przez sw.js prowadzi do ${oczekiwany} i jest kasowany`, async ({ page }) => {
      const bledy = pilnujBledow(page);
      await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
      await podstaw(page);
      await stronaProby(page);
      await page.evaluate(zaladujSw, [SW]);
      await page.evaluate((u) => sw.klik({ url: u, id: 'A' }), url);
      // iPhone otwiera start_url zamiast celu z openWindow (WebKit 263687)
      await page.goto('/index.html');
      await gotowa(page);
      await expect(page).toHaveURL(new RegExp(oczekiwany + '$'));
      expect(await celWCache(page)).toBeNull();
      await page.goBack();
      await expect(page).toHaveURL(new RegExp(rodzic + '$'));
      // następne uruchomienie z ikony zostaje na Domu
      await page.goto('/index.html');
      await gotowa(page);
      await page.waitForTimeout(300);
      await expect(page).toHaveURL(/\/index\.html#dom$/);
      expect(bledy).toEqual([]);
    });
  }

  test('cel zapisany chwilę po starcie aplikacji też działa (druga próba)', async ({ page }) => {
    const bledy = pilnujBledow(page);
    await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
    await podstaw(page);
    await page.goto('/index.html');
    await gotowa(page);
    await page.evaluate(() => caches.open('cel-powiadomienia').then((c) => c.put('./cel',
      new Response(JSON.stringify({ cel: '#fikus', ts: Date.now() })))));
    await expect(page).toHaveURL(/#fikus$/, { timeout: 6000 });
    expect(bledy).toEqual([]);
  });

  for (const [opis, cel, temu] of [
    ['obcy adres', 'https://zly.example/#azalia', 0],
    ['adres względny do obcego hosta', '//zly.example/rosliny.html', 0],
    ['dawny adres zakresu wykresu', 'index.html#zakres=7', 0],
    ['nazwa tylko udająca przekierowanie', 'rosliny.html.zly.example', 0],
    ['cel sprzed kwadransa', '#azalia', 15 * 60e3],
  ]) {
    test(`aplikacja nie idzie za celem (${opis}), ale go kasuje`, async ({ page }) => {
      const bledy = pilnujBledow(page);
      await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
      await podstaw(page);
      await stronaProby(page);
      await page.evaluate(([c, t]) => caches.open('cel-powiadomienia').then((k) => k.put('./cel',
        new Response(JSON.stringify({ cel: c, ts: Date.now() - t })))), [cel, temu]);
      await page.goto('/index.html');
      await gotowa(page);
      await expect.poll(() => celWCache(page)).toBeNull();
      await page.waitForTimeout(300);
      await expect(page).toHaveURL(/\/index\.html#dom$/);
      expect(bledy).toEqual([]);
    });
  }

  test.describe('z prawdziwym service workerem', () => {
    // Jedyny (obok strona.spec.js) test z działającym workerem: tylko tak push przechodzi przez prawdziwą obsługę,
    // showNotification i IndexedDB workera. Dane idą wtedy z repozytorium — worker sam pobiera data/.
    test.use({ serviceWorkers: 'allow' });

    test('push przez CDP: worker pokazuje powiadomienie i zapisuje odbiór, który czyta aplikacja', async ({ page, context, baseURL }) => {
      const bledy = pilnujBledow(page);
      await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
      await context.grantPermissions(['notifications']);
      const cdp = await context.newCDPSession(page);
      const rejestracje = [];
      cdp.on('ServiceWorker.workerRegistrationUpdated', (e) => rejestracje.push(...e.registrations));
      await cdp.send('ServiceWorker.enable');
      await page.goto('/index.html#powiadomienia');
      await gotowa(page);
      await page.evaluate(() => navigator.serviceWorker.ready.then(() => null));
      await expect.poll(() => rejestracje.some((r) => !r.isDeleted)).toBe(true);
      const { registrationId } = rejestracje.find((r) => !r.isDeleted);
      const tresc = { title: 'Przewietrz łazienkę', body: 'Łazienka: 71% od 2 godz., za wilgotno powyżej 63%.', tag: 'przewietrz-lazienka', url: '#lazienka', id: '20261011T140112Z-przewietrz' };
      await cdp.send('ServiceWorker.deliverPushMessage', { origin: `${baseURL}/`, registrationId, data: JSON.stringify(tresc) });
      // odbiór zapisuje obsługa push workera, a czyta go funkcja aplikacji — w każdym Chromium
      await expect.poll(() => page.evaluate(() => SH.odebraneId().then((s) => [...s]))).toEqual(['20261011T140112Z-przewietrz']);
      // Samo powiadomienie widać tylko w pełnym Chromium. Headless shell (domyślny w CI przy Playwright 1.49) mimo
      // grantPermissions zostaje przy zgodzie 'denied' i niczego nie pokazuje — zmierzone 9.10 na obu binarkach.
      // Treść powiadomienia pilnuje wtedy test „push" z atrapą `self`.
      if (await page.evaluate(() => Notification.permission) === 'granted') {
        await expect.poll(() => page.evaluate(async () => (await (await navigator.serviceWorker.ready).getNotifications())
          .map((n) => ({ tytul: n.title, tresc: n.body, tag: n.tag, dane: n.data })))).toEqual([
          { tytul: tresc.title, tresc: tresc.body, tag: tresc.tag, dane: { url: '#lazienka', id: tresc.id } }]);
      } else {
        test.info().annotations.push({ type: 'bez pokazania', description: 'ta binarka Chromium nie pokazuje powiadomień — sprawdzony tylko zapis odbioru' });
      }
      expect(bledy).toEqual([]);
    });

    test('bez sieci stary link z powiadomienia i tak otwiera roślinę: przekierowanie, aplikacja i dane z cache workera', async ({ page, context }) => {
      const bledy = pilnujBledow(page);
      await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
      await page.goto('/index.html');
      await gotowa(page);
      await page.evaluate(() => navigator.serviceWorker.ready.then(() => null));
      // dopiero strona pod kontrolą workera pobiera data/ przez niego (i zostawia zapas)
      await page.reload();
      await gotowa(page);
      await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
      await expect.poll(() => page.evaluate(async () => {
        const c = await caches.open('smart-home-v6');
        const k = (await c.keys()).map((r) => new URL(r.url).pathname.replace(/\d{4}-\d\d\.csv$/, 'MIESIĄC.csv'));
        return ['/rosliny.html', '/pokoje.json', '/data/index.json', '/data/MIESIĄC.csv', '/data/rosliny/stan.json'].filter((x) => k.indexOf(x) < 0);
      })).toEqual([]);
      await context.setOffline(true);
      await page.goto('/rosliny.html#roslina=Azalia', { waitUntil: 'commit' });
      await page.waitForURL(/\/#azalia$/);
      await gotowa(page);
      await expect(page.locator('#app')).toHaveAttribute('data-dane', 'gotowe');
      await expect(page.locator('.strona:not(.sasiad)')).toHaveAttribute('data-slug', 'azalia');
      await context.setOffline(false);
      expect(bledy).toEqual([]);
    });
  });
});

test.describe('rosliny.html: przekierowanie starych adresów', () => {
  for (const [opis, adres, oczekiwany, slug] of [
    ['stary link rośliny z powiadomienia', '/rosliny.html#roslina=Azalia', '#azalia', 'azalia'],
    ['nazwa z polskimi znakami', '/rosliny.html#roslina=Skrzyd%C5%82okwiat', '#skrzydlokwiat', 'skrzydlokwiat'],
    ['nowy adres pod starą ścieżką', '/rosliny.html#kuchnia', '#kuchnia', 'kuchnia'],
  ]) {
    test(`${opis}: ${adres} → ./${oczekiwany}, „wstecz" do rodzica`, async ({ page }) => {
      const bledy = pilnujBledow(page);
      await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
      await podstaw(page);
      // stub przekierowuje już w <head>, więc czekamy tylko na jego odpowiedź, a potem na adres aplikacji
      await page.goto(adres, { waitUntil: 'commit' });
      await page.waitForURL(new RegExp('/' + oczekiwany + '$'));
      await gotowa(page);
      expect(new URL(page.url()).pathname).toBe('/');
      await expect(page.locator('.strona:not(.sasiad)')).toHaveAttribute('data-slug', slug);
      await page.goBack();
      await expect(page).toHaveURL(new RegExp(slug === 'kuchnia' ? '#dom$' : '#rosliny$'));
      expect(bledy).toEqual([]);
    });
  }

  for (const [adres, oczekiwany] of [['/rosliny.html', '#rosliny'], ['/rosliny.html#roslina=Nieznana', '#rosliny'], ['/rosliny.html?x=1', '#rosliny']]) {
    test(`${adres} → lista roślin`, async ({ page }) => {
      const bledy = pilnujBledow(page);
      await page.route(/fonts\.(googleapis|gstatic)\.com/, (r) => r.abort());
      await podstaw(page);
      await page.goto(adres, { waitUntil: 'commit' });
      await page.waitForURL(/\/#/);
      await gotowa(page);
      await expect(page).toHaveURL(new RegExp('/' + oczekiwany + '$'));
      await expect(page.locator('#v-rosliny')).toBeVisible();
      expect(bledy).toEqual([]);
    });
  }

  test.describe('bez JavaScriptu', () => {
    test.use({ javaScriptEnabled: false });
    test('meta refresh z <noscript> prowadzi do listy roślin', async ({ page }) => {
      await page.goto('/rosliny.html#roslina=Azalia', { waitUntil: 'commit' });
      await page.waitForURL(/\/#rosliny$/);
    });
  });

  test('przekierowanie bez skryptów zewnętrznych, bez klucza i bez mapowania nazw (strażnik)', () => {
    /* Strażnik: stub ma być mały i głupi. Tłumaczenie nazwy rośliny na adres jest tylko w index.html — drugie
       miejsce rozjechałoby się przy pierwszej nowej roślinie. Meta refresh wyłącznie w <noscript>: przy działającym
       JS zwykły meta refresh to druga nawigacja, która w WebKit może przegonić location.replace i zgubić hash
       (w Chromium nie przegania — zmierzone 11.10, 45 prób; WebKit nie był do sprawdzenia). */
    expect(ROSLINY_HTML).not.toMatch(/<script[^>]+src=/i);
    const kod = ROSLINY_HTML.replace(/<!--[\s\S]*?-->/g, '');   // komentarz opisuje stare adresy — liczy się kod
    expect(kod).not.toMatch(/VAPID|chart\.js|roslina=|slug/i);
    expect(ROSLINY_HTML).toContain("location.replace('./' + (location.hash || '#rosliny'))");
    expect(ROSLINY_HTML).toMatch(/<noscript><meta http-equiv="refresh" content="0;url=\.\/#rosliny"><\/noscript>/);
    expect(ROSLINY_HTML.replace(/<noscript>[\s\S]*?<\/noscript>/g, '')).not.toMatch(/http-equiv="refresh"/);
  });
});

test.describe('manifest', () => {
  test('opis obejmuje dom i rośliny; start_url, scope, nazwy i ikony bez zmian (strażnik)', () => {
    /* Strażnik: iOS kasuje subskrypcję przy ponownym dodaniu ikony, a zmiana start_url, scope, nazwy albo ikon
       wymaga właśnie tego. Wolno zmienić tylko opis. */
    const m = JSON.parse(fs.readFileSync(path.join(KORZEN, 'manifest.json'), 'utf8'));
    expect(m.description).toMatch(/[Dd]om/);
    expect(m.description).toMatch(/rośliny/);
    expect({ name: m.name, short_name: m.short_name, start_url: m.start_url, scope: m.scope, display: m.display, icons: m.icons }).toEqual({
      name: 'Smart Home', short_name: 'Smart Home', start_url: './', scope: './', display: 'standalone',
      icons: [
        { src: 'ikona-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
        { src: 'ikona-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
        { src: 'ikona-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        { src: 'ikona.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' },
      ],
    });
  });
});
