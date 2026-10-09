/* Service worker: dashboard ma się otwierać natychmiast i pokazywać ostatnie odczyty
   także bez zasięgu — w piwnicy, w windzie, w pociągu.

   Strategie dobrane tak, żeby cache nigdy nie zablokował poprawki:
   - strona (nawigacja): najpierw sieć, cache tylko gdy sieci nie ma. Dzięki temu
     nowy index.html trafia do Ciebie od razu po wypchnięciu na main.
   - data/: najpierw sieć, cache jako zapas. Online widzisz świeże odczyty,
     offline ostatnie znane.
   - biblioteki z CDN i fonty: najpierw cache. Adresy zawierają numer wersji,
     więc treść pod nimi się nie zmienia.

   Od etapu 4 worker obsługuje też powiadomienia roślin (push i kliknięcie) — opis
   przy obsługach na dole pliku.

   Po zmianie tej listy albo strategii podnieś WERSJA — stare cache lecą wtedy
   do kosza przy aktywacji. */
const WERSJA = 'smart-home-v5';
const SZKIELET = ['./', './index.html', './rosliny.html', './ikona.svg', './ikona-192.png', './ikona-512.png', './manifest.json'];
const OBCE = /(^|\.)jsdelivr\.net$|(^|\.)googleapis\.com$|(^|\.)gstatic\.com$/;
// Cel kliknięcia w powiadomienie dla index.html (obejście WebKit 263687, niżej). Osobny
// cache, którego aktywacja nowej wersji nie kasuje: cel zapisany tuż przed aktualizacją
// workera ma dotrwać do startu strony.
const CEL = 'cel-powiadomienia';

self.addEventListener('install', e => {
  // addAll przewraca się w całości, gdy padnie jeden plik — stąd pojedynczo. cache:'reload'
  // omija pamięć HTTP przeglądarki (Pages daje max-age 10 min): inaczej nowa wersja mogła
  // zapisać w szkielecie starą stronę, np. index.html sprzed paska zakładek.
  e.waitUntil(caches.open(WERSJA)
    .then(c => Promise.all(SZKIELET.map(u => c.add(new Request(u, { cache: 'reload' })).catch(() => null))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(klucze => Promise.all(klucze.filter(k => k !== WERSJA && k !== CEL).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Odpowiedzi nieprzezroczyste (skrypty z CDN ładowane bez CORS) mają status 0,
// więc res.ok jest fałszem mimo że treść jest w porządku.
const wartaZapisu = res => res && (res.ok || res.type === 'opaque');

async function siecPotemCache(req) {
  const cache = await caches.open(WERSJA);
  try {
    const res = await fetch(req);
    if (wartaZapisu(res)) cache.put(req, res.clone());
    return res;
  } catch (blad) {
    const zapas = await cache.match(req);
    if (zapas) return zapas;
    throw blad;
  }
}

async function cachePotemSiec(req) {
  const cache = await caches.open(WERSJA);
  const trafienie = await cache.match(req);
  if (trafienie) return trafienie;
  const res = await fetch(req);
  if (wartaZapisu(res)) cache.put(req, res.clone());
  return res;
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);

  if (req.mode === 'navigate') {
    e.respondWith(siecPotemCache(req).catch(() => caches.match('./index.html')));
    return;
  }
  if (url.origin === location.origin && url.pathname.includes('/data/')) {
    e.respondWith(siecPotemCache(req));
    return;
  }
  if (url.origin === location.origin || OBCE.test(url.hostname)) {
    e.respondWith(cachePotemSiec(req));
  }
});

/* --- powiadomienia (etap 4, ROSLINY.md) ---

   Nadawca (wyslij.py) wysyła JSON {title, body, tag, url, id} z wpisu
   data/rosliny/powiadomienia.json. Testy (tests/frontend/rosliny.spec.js) wczytują ten
   plik z atrapą `self` i oprócz obsług wołają wprost trescPush, celKlikniecia
   i zapiszOdebrane — zmiana ich nazw wymaga zmiany testów. */

/** Treść push → [tytuł, opcje showNotification]. Pokazać trzeba ZAWSZE, nawet przy
    zepsutej treści: Safari cofa zgodę aplikacji, która odebrała push i nic nie pokazała.
    Stąd JSON z zapasem na zwykły tekst i domyślny tytuł. */
function trescPush(tekst) {
  let d = null;
  try { d = JSON.parse(tekst); } catch { /* zwykły tekst — niżej */ }
  if (!d || typeof d !== 'object' || Array.isArray(d)) d = { body: String(tekst || '') };
  const napis = v => (typeof v === 'string' ? v : '');
  const opcje = {
    body: napis(d.body),
    // Ikona aplikacji. Bez `badge`: ikona-192.png jest nieprzezroczysta, a Android rysuje
    // znaczek z samej przezroczystości — wyszedłby biały kwadrat zamiast domyślnego.
    icon: 'ikona-192.png',
    data: { url: napis(d.url), id: napis(d.id) || null },
  };
  // Ten sam tag zastępuje poprzednie powiadomienie (np. ponowienie „podlej" po 12 godz.),
  // a renotify każe mimo to zadzwonić — ponowienie, które przychodzi po cichu, nie przypomina.
  if (napis(d.tag)) { opcje.tag = d.tag; opcje.renotify = true; }
  return [napis(d.title) || 'Rośliny', opcje];
}

/** Adres do otwarcia po kliknięciu: data.url rozwiązany względem zakresu aplikacji i tylko
    wtedy, gdy w nim leży. Treść przychodzi z sieci, więc obcy adres (albo `../`, `//host`,
    `javascript:`) nie może się otworzyć w oknie aplikacji — wtedy strona startowa. */
function celKlikniecia(adres, zakres) {
  try {
    const u = new URL(String(adres || ''), zakres).href;
    if (u.startsWith(zakres)) return u;
  } catch { /* uszkodzony adres — zakres */ }
  return zakres;
}

/* Identyfikatory odebranych powiadomień w IndexedDB (baza `rosliny`, magazyn `odebrane`).
   Zakładka porównuje je z powiadomienia.json: wysłane ponad godzinę temu i nieodebrane →
   „nie dochodzą". Tylko tak widać martwą subskrypcję na iPhonie, którą Apple dalej
   potwierdza kodem 201. Wpisów przybywa najwyżej kilka na dobę, po kilkadziesiąt bajtów —
   bez sprzątania. Ta sama baza i wersja co w rosliny.html: kto pierwszy, ten ją zakłada. */
function zapiszOdebrane(id) {
  return new Promise((ok, zle) => {
    const zad = indexedDB.open('rosliny', 1);
    zad.onupgradeneeded = () => zad.result.createObjectStore('odebrane', { keyPath: 'id' });
    zad.onerror = () => zle(zad.error);
    zad.onsuccess = () => {
      const db = zad.result;
      const tx = db.transaction('odebrane', 'readwrite');
      tx.objectStore('odebrane').put({ id, ts: Date.now() });
      tx.oncomplete = () => { db.close(); ok(); };
      tx.onerror = tx.onabort = () => { db.close(); zle(tx.error); };
    };
  });
}

self.addEventListener('push', e => {
  let tekst = '';
  try { tekst = e.data ? e.data.text() : ''; } catch { /* pusta treść — domyślny tytuł */ }
  const [tytul, opcje] = trescPush(tekst);
  // Zapis odbioru nie może zatrzymać pokazania: bez IndexedDB powiadomienie i tak wychodzi.
  e.waitUntil(Promise.all([
    self.registration.showNotification(tytul, opcje),
    opcje.data.id ? zapiszOdebrane(opcje.data.id).catch(() => null) : null,
  ]));
});

/* Cel zapisany w Cache API dla index.html. iPhone przy zimnym starcie aplikacji otwiera
   po kliknięciu start_url zamiast adresu z openWindow (WebKit 263687), więc index.html
   na starcie zagląda tutaj i przechodzi do celu. Zapis względny wobec zakresu
   ('rosliny.html#roslina=…') i z czasem — index.html bierze tylko świeży, a rosliny.html
   kasuje go po wejściu, żeby następne uruchomienie z ikony nie skakało do roślin.
   Klucz './cel' rozwiązuje się tu względem sw.js, a w index.html względem strony — oba
   pliki leżą w tym samym katalogu. */
async function zapiszCel(cel) {
  const zakres = self.registration.scope;
  const wzgledny = cel.slice(zakres.length);
  if (!wzgledny) return;
  const c = await caches.open(CEL);
  await c.put('./cel', new Response(JSON.stringify({ cel: wzgledny, ts: Date.now() }),
    { headers: { 'Content-Type': 'application/json' } }));
}

async function otworzCel(cel) {
  // includeUncontrolled widzi wszystkie karty z tego originu, także innych projektów
  // na github.io — przejmujemy tylko okno naszej aplikacji
  const okna = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  const zakres = self.registration.scope;
  const okno = okna.find(o => o.url.startsWith(zakres));
  if (okno) {
    try {
      await okno.focus();
      // navigate() działa tylko w oknie, którym ten worker steruje; w innym rzuca —
      // wtedy nowe okno, żeby kliknięcie nie skończyło się na samym fokusie
      await okno.navigate(cel);
      return;
    } catch { /* niżej openWindow */ }
  }
  // Cel tylko przed openWindow, czyli przy zimnym starcie — tam działa obejście. Przy
  // otwartym oknie navigate() wystarcza, a zapisany cel mógłby zostać (nawigacja w obrębie
  // tej samej strony nie przeładowuje rosliny.html, więc ta go nie skasuje) i przerzucić
  // do roślin kliknięcie w zakładkę „Mieszkanie". Zapis przed otwarciem, bo strona
  // otwarta przez openWindow może ruszyć od razu.
  try { await zapiszCel(cel); } catch { /* bez Cache API — zostaje samo openWindow */ }
  await self.clients.openWindow(cel);
}

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const dane = e.notification.data || {};
  e.waitUntil(otworzCel(celKlikniecia(dane.url, self.registration.scope)));
});
