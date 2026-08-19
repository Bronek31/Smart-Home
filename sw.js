/* Service worker: dashboard ma się otwierać natychmiast i pokazywać ostatnie odczyty
   także bez zasięgu — w piwnicy, w windzie, w pociągu.

   Strategie dobrane tak, żeby cache nigdy nie zablokował poprawki:
   - strona (nawigacja): najpierw sieć, cache tylko gdy sieci nie ma. Dzięki temu
     nowy index.html trafia do Ciebie od razu po wypchnięciu na main.
   - data/: najpierw sieć, cache jako zapas. Online widzisz świeże odczyty,
     offline ostatnie znane.
   - biblioteki z CDN i fonty: najpierw cache. Adresy zawierają numer wersji,
     więc treść pod nimi się nie zmienia.

   Po zmianie tej listy albo strategii podnieś WERSJA — stare cache lecą wtedy
   do kosza przy aktywacji. */
const WERSJA = 'smart-home-v2';
const SZKIELET = ['./', './index.html', './ikona.svg', './ikona-192.png', './ikona-512.png', './manifest.json'];
const OBCE = /(^|\.)jsdelivr\.net$|(^|\.)googleapis\.com$|(^|\.)gstatic\.com$/;

self.addEventListener('install', e => {
  // addAll przewraca się w całości, gdy padnie jeden plik — stąd pojedynczo
  e.waitUntil(caches.open(WERSJA)
    .then(c => Promise.all(SZKIELET.map(u => c.add(u).catch(() => null))))
    .then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(klucze => Promise.all(klucze.filter(k => k !== WERSJA).map(k => caches.delete(k))))
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
