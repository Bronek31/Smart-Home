/* Atrapy i dane testów powiadomień (tests/frontend/rosliny.spec.js): subskrypcja Web Push w zakładce
   Powiadomienia aplikacji (index.html), service worker (sw.js) i przekierowanie rosliny.html.

   Nazwa pliku została z czasów, gdy powiadomienia mieszkały w zakładce „Rośliny" (rosliny.html) — tak jak
   nazwy, których zmienić nie wolno, bo trzymają je telefony: localStorage 'rosliny-subskrypcja' i baza
   IndexedDB 'rosliny'/'odebrane'. Dane mieszkania i roślin (data/**, pokoje.json) podstawia router po ścieżce
   z dane.js — tu są tylko rzeczy telefonu: Notification, PushManager, service worker, schowek. */

const crypto = require('crypto');

const GODZ = 3600e3;
const DOBA = 24 * GODZ;
const iso = (t) => new Date(t).toISOString().replace(/\.\d{3}Z$/, 'Z');

const ANDROID = 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Mobile Safari/537.36';
const IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';

/** Klucz publiczny prawdziwej pary P-256 z Node, w postaci stałej w aplikacji (65 B, base64url). */
function kluczPubliczny() {
  const ecdh = crypto.createECDH('prime256v1');
  ecdh.generateKeys();
  return ecdh.getPublicKey('base64url');
}

/**
 * Atrapy API powiadomień (addInitScript, przed skryptem aplikacji). Subskrypcja atrapy przeżywa
 * przeładowanie (localStorage), jak prawdziwa; stan początkowy wchodzi tylko przy pierwszym wczytaniu karty.
 * Zapis wywołań w window.atrapa.
 * @param {object} u
 * @param {string} [u.ua]               navigator.userAgent
 * @param {boolean} [u.standalone]      aplikacja otwarta z ekranu początkowego (iPhone)
 * @param {boolean} [u.bezPush]         bez PushManager (iPhone w Safari)
 * @param {boolean} [u.bezApi]          bez Notification, PushManager i service workera
 * @param {string} [u.zgoda]            Notification.permission na start
 * @param {string} [u.odpowiedz]        co odpowie requestPermission()
 * @param {string} [u.subskrypcja]      adres subskrypcji, którą telefon już ma
 * @param {string} [u.kluczSubskrypcji] jej applicationServerKey (base64url); brak — nieznany
 * @param {string} [u.nowa]             adres, który da subscribe()
 * @param {object} [u.zapamietana]      {endpoint, od} skopiowanej kiedyś subskrypcji
 */
async function atrapyPowiadomien(page, u = {}) {
  await page.addInitScript((u) => {
    const log = window.atrapa = { zgody: 0, zgodaWKliknieciu: [], subskrypcje: [], wypisania: 0, schowek: [] };
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
    // Prawdziwy kontener zostaje (wiadomości od workera, startMessages) — podmienione tylko to, co dotyczy rejestracji.
    const kontener = navigator.serviceWorker;
    Object.defineProperty(navigator, 'serviceWorker', { configurable: true, value: {
      getRegistration: async () => reg, register: async () => reg, ready: Promise.resolve(reg),
      addEventListener: kontener.addEventListener.bind(kontener), dispatchEvent: kontener.dispatchEvent.bind(kontener),
      startMessages: () => {} } });
    if (u.bezPush) delete window.PushManager;
    else if (!window.PushManager) window.PushManager = function PushManager() {};
    let zgoda = u.zgoda || 'default';
    window.Notification = class Notification {
      static get permission() { return zgoda; }
      // iPhone pyta o zgodę tylko w geście użytkownika: zapisujemy, czy prośba przyszła jeszcze w trakcie
      // obsługi kliknięcia (window.event), czyli przed pierwszym await
      static async requestPermission() {
        log.zgody++;
        log.zgodaWKliknieciu.push(!!(window.event && window.event.type === 'click'));
        zgoda = u.odpowiedz || 'granted';
        return zgoda;
      }
    };
  }, u);
}

/** Plik powiadomień w kształcie kolektora (2.4 BRIEF5) i jeden wpis historii. */
const plikPowiadomien = (historia, tryb = 'wlaczone') =>
  ({ tryb, wlaczone_od: null, historia, stan_regul: {}, telefony: {} });
const wpis = (id, temu, { na_sucho = false, tytul = 'Podlej: azalia', telefony } = {}) => {
  const w = { id, ts: iso(Date.now() - temu), przebieg: '123-1', regula: 'podlej', rosliny: ['Azalia'], tytul,
    tresc: 'Azalia: gleba 41% (podlewaj przy ok. 45%).', tag: 'podlej-azalia', url: '#azalia', na_sucho };
  if (telefony !== undefined) w.telefony = telefony;
  return w;
};

/** Pusta strona w zakresie aplikacji — ma prawdziwe Cache API i IndexedDB tego originu. */
async function stronaProby(page) {
  await page.route('**/proba-sw.html', (r) => r.fulfill({ contentType: 'text/html; charset=utf-8',
    body: '<!doctype html><meta charset="utf-8"><title>sw.js</title>' }));
  await page.goto('/proba-sw.html');
}

/* sw.js wykonany w stronie z atrapą `self`: registration, clients, navigator (licznik) i fetch zapisują
   wywołania, a Cache API i IndexedDB są prawdziwe. Zwraca też trzy funkcje z pliku. Funkcja leci do
   przeglądarki przez toString — nie może sięgać do niczego spoza siebie.
   okna: [{url, niesterowane, nawigacjaRzuca, doStrony}] — doStrony: wiadomość od workera trafia do
   navigator.serviceWorker tej strony (aplikacja otwarta w tej karcie). */
function zaladujSw([zrodlo, { okna = [], bezIndexedDB = false, zakres = location.origin + '/', licznik = 'tak' } = {}]) {
  const obslugi = {};
  const log = window.log = { pokazane: [], otwarte: [], nawigacje: [], wiadomosci: [], fokusy: 0, zamkniete: 0, licznik: [], siec: [] };
  // Jedno kliknięcie w powiadomienie to jeden „żeton" na focus() albo openWindow() — tak działa Chrome;
  // drugie wywołanie rzuca.
  let zeton = 0;
  const zuzyj = () => { if (zeton-- <= 0) throw new DOMException('Not allowed to open a window.', 'InvalidAccessError'); };
  const okienka = okna.map((o) => ({
    url: o.url,
    niesterowane: !!o.niesterowane,
    focus: async () => { zuzyj(); log.fokusy++; },
    navigate: async (u) => { if (o.niesterowane || o.nawigacjaRzuca) throw new TypeError('okno bez tego workera'); log.nawigacje.push(u); return null; },
    postMessage: (d) => {
      log.wiadomosci.push(JSON.parse(JSON.stringify(d)));
      if (o.doStrony) setTimeout(() => navigator.serviceWorker.dispatchEvent(new MessageEvent('message', { data: d })), 0);
    },
  }));
  // Centrum powiadomień: ten sam tag zastępuje poprzednie, jak w przeglądarce.
  let centrum = [];
  const atrapaNavigator = licznik === 'brak' ? undefined : {
    setAppBadge: async (n) => { if (licznik === 'rzuca') throw new Error('licznik niedostępny'); log.licznik.push(n); },
    clearAppBadge: async () => { log.licznik.push(0); },
  };
  const atrapaSelf = {
    addEventListener: (typ, f) => { obslugi[typ] = f; },
    navigator: atrapaNavigator,
    registration: {
      scope: zakres,
      showNotification: async (t, o) => {
        log.pokazane.push([t, o]);
        centrum = centrum.filter((p) => !o.tag || p.tag !== o.tag).concat([{ title: t, tag: o.tag || '' }]);
      },
      getNotifications: async () => centrum.slice(),
    },
    clients: {
      matchAll: async (opcje = {}) => okienka.filter((o) => opcje.includeUncontrolled || !o.niesterowane),
      openWindow: async (u) => { zuzyj(); log.otwarte.push(u); return null; },
      claim: async () => {},
    },
    skipWaiting: async () => {},
  };
  // Sieć workera: window.siec.dziala = false udaje brak zasięgu, window.siec.status — odpowiedź z błędem (503, 404);
  // każda odpowiedź ma numer, żeby było widać, skąd przyszła.
  window.siec = { dziala: true, n: 0, status: 200 };
  const atrapaFetch = async (req) => {
    log.siec.push(req.url);
    if (!window.siec.dziala) throw new TypeError('Failed to fetch');
    return new Response('sieć ' + (++window.siec.n), { status: window.siec.status });
  };
  const idb = bezIndexedDB ? { open() { throw new Error('IndexedDB wyłączone'); } } : indexedDB;
  const funkcje = new Function('self', 'indexedDB', 'fetch', `${zrodlo}\nreturn { trescPush, celKlikniecia, zapiszOdebrane };`)(atrapaSelf, idb, atrapaFetch);
  const zdarzenie = (pola) => { const czekaj = []; return Object.assign(pola, { waitUntil: (p) => czekaj.push(p), czekaj }); };
  window.sw = {
    ...funkcje,
    async push(tekst) { const e = zdarzenie({ data: tekst == null ? null : { text: () => tekst } }); obslugi.push(e); await Promise.all(e.czekaj); },
    async klik(data) { zeton = 1; const e = zdarzenie({ notification: { data, close: () => { log.zamkniete++; } } }); obslugi.notificationclick(e); await Promise.all(e.czekaj); },
    async aktywuj() { const e = zdarzenie({}); obslugi.activate(e); await Promise.all(e.czekaj); },
    /** zdarzenie fetch: zwraca tekst odpowiedzi workera albo null, gdy worker go nie przejął */
    async pobierz(url, metoda = 'GET') {
      const o = await window.sw.odpowiedz(url, metoda);
      return o ? o.tekst : null;
    },
    /** jak pobierz, ale ze statusem: {status, tekst} albo null */
    async odpowiedz(url, metoda = 'GET') {
      let odp = null;
      obslugi.fetch({ request: new Request(url, { method: metoda }), respondWith: (p) => { odp = p; } });
      if (!odp) return null;
      const r = await odp;
      return { status: r.status, tekst: await r.text() };
    },
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

module.exports = {
  GODZ, DOBA, iso, ANDROID, IPHONE, kluczPubliczny, atrapyPowiadomien, plikPowiadomien, wpis,
  stronaProby, zaladujSw, odebraneWStronie, celWCache,
};
