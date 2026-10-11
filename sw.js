/* Service worker: aplikacja ma się otwierać natychmiast i pokazywać ostatnie odczyty
   także bez zasięgu — w piwnicy, w windzie, w pociągu.

   Strategie dobrane tak, żeby cache nigdy nie zablokował poprawki:
   - strona (nawigacja): najpierw sieć, cache tylko gdy sieci nie ma. Dzięki temu
     nowy index.html trafia do Ciebie od razu po wypchnięciu na main.
   - data/ i pokoje.json: najpierw sieć, cache jako zapas. Online widzisz świeże odczyty
     i świeży plan pokoi, offline ostatnie znane. Dla data/ zapas także przy odpowiedzi
     z błędem (503/404 z Pages), jeśli plik już kiedyś przyszedł.
   - fonty: najpierw cache. Adresy Google Fonts zawierają wersję kroju, więc treść pod
     nimi się nie zmienia.
   - api.github.com (ustawienia telefonów na zakładce Powiadomienia) i inne obce adresy:
     worker ich nie dotyka. Zapamiętany odczyt zmiennej pokazałby ustawienia sprzed zmiany.

   Worker obsługuje też powiadomienia (push, licznik na ikonie i kliknięcie) — opis przy
   obsługach na dole pliku.

   Po zmianie tej listy albo strategii podnieś WERSJA — stare cache lecą wtedy
   do kosza przy aktywacji. v6: rosliny.html to już tylko przekierowanie do index.html,
   pokoje.json w szkielecie, kliknięcie w powiadomienie przy otwartej aplikacji idzie
   wiadomością do jej routingu. */
const WERSJA = 'smart-home-v6';
const SZKIELET = ['./', './index.html', './rosliny.html', './pokoje.json', './ikona.svg', './ikona-192.png', './ikona-512.png', './manifest.json'];
const OBCE = /(^|\.)googleapis\.com$|(^|\.)gstatic\.com$/;
// Cel kliknięcia w powiadomienie dla zimnego startu (obejście WebKit 263687, niżej). Osobny
// cache, którego aktywacja nowej wersji nie kasuje: cel zapisany tuż przed aktualizacją
// workera ma dotrwać do startu aplikacji.
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

// Odpowiedzi nieprzezroczyste (zasoby z innego originu ładowane bez CORS) mają status 0,
// więc res.ok jest fałszem mimo że treść jest w porządku.
const wartaZapisu = res => res && (res.ok || res.type === 'opaque');

// `zapasPrzyBledzie` (data/): odpowiedź z błędem (503 albo 404 z Pages w trakcie wdrożenia) zastępuje ostatnia dobra
// kopia z cache — dla aplikacji „brak pliku" i „serwer chwilowo nie odpowiada" to różne rzeczy, a pierwsze kasowałoby
// widok. Bez kopii (plik jeszcze nigdy nie przyszedł, np. data/dom/stan.json przed pierwszą zbiórką) idzie oryginalna
// odpowiedź: 404 pliku nieobowiązkowego zostaje 404.
async function siecPotemCache(req, zapasPrzyBledzie) {
  const cache = await caches.open(WERSJA);
  try {
    const res = await fetch(req);
    if (wartaZapisu(res)) cache.put(req, res.clone());
    else if (zapasPrzyBledzie && !res.ok) {
      const zapas = await cache.match(req);
      if (zapas) return zapas;
    }
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
  // pokoje.json zmienia się rzadko, ale gdy się zmieni (nowy pokój, inny slug), stara
  // kopia z cache przypisałaby odczyty złym pokojom — więc jak dane: sieć, potem zapas
  if (url.origin === location.origin && (url.pathname.includes('/data/') || url.pathname.endsWith('/pokoje.json'))) {
    e.respondWith(siecPotemCache(req, url.pathname.includes('/data/')));
    return;
  }
  if (url.origin === location.origin || OBCE.test(url.hostname)) {
    e.respondWith(cachePotemSiec(req));
  }
});

/* --- powiadomienia ---

   Nadawca (wyslij.py) wysyła JSON {title, body, tag, url, id} z wpisu
   data/dom/powiadomienia.json albo data/rosliny/powiadomienia.json. Kto dostaje co i kiedy
   (ustawienia telefonu, cisza nocna), rozstrzyga kolektor przed wysłaniem — tutaj każdy
   push MUSI skończyć się powiadomieniem, bo Safari cofa zgodę aplikacji, która odebrała
   push i nic nie pokazała. Testy (tests/frontend/rosliny.spec.js) wczytują ten plik
   z atrapą `self` i oprócz obsług wołają wprost trescPush, celKlikniecia i zapiszOdebrane —
   zmiana ich nazw wymaga zmiany testów. */

/** Treść push → [tytuł, opcje showNotification]. Pokazać trzeba ZAWSZE, nawet przy
    zepsutej treści — stąd JSON z zapasem na zwykły tekst i domyślny tytuł. Domyślny tytuł
    to nazwa aplikacji, bo powiadomienia są i o domu, i o roślinach. */
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
  return [napis(d.title) || 'Smart Home', opcje];
}

/** Adres do otwarcia po kliknięciu: data.url rozwiązany względem zakresu aplikacji i tylko
    wtedy, gdy w nim leży. Treść przychodzi z sieci, więc obcy adres (albo `../`, `//host`,
    `javascript:`) nie może się otworzyć w oknie aplikacji — wtedy strona startowa.
    Nowe wpisy mają url '#fikus', '#lazienka', '#rosliny'…; stare 'rosliny.html#roslina=…'
    (doręczone przed zmianą) rozwiązują się tak samo i trafiają do przekierowania. */
function celKlikniecia(adres, zakres) {
  try {
    const u = new URL(String(adres || ''), zakres).href;
    if (u.startsWith(zakres)) return u;
  } catch { /* uszkodzony adres — zakres */ }
  return zakres;
}

/* Identyfikatory odebranych powiadomień w IndexedDB (baza `rosliny`, magazyn `odebrane`).
   Zakładka Powiadomienia porównuje je z plikami powiadomień: wysłane do tego telefonu ponad
   godzinę temu i nieodebrane → „nie dochodzą". Tylko tak widać martwą subskrypcję na
   iPhonie, którą Apple dalej potwierdza kodem 201. Wpisów przybywa najwyżej kilka na dobę,
   po kilkadziesiąt bajtów — bez sprzątania. Nazwy bazy i wersja zostają z czasów zakładki
   Rośliny: zmiana zgubiłaby to, co telefony już zapisały, a aplikacja czyta tę samą bazę. */
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

/* Licznik na ikonie aplikacji: po pokazaniu powiadomienia tyle, ile powiadomień aplikacji
   leży w centrum powiadomień. Otwarta aplikacja ustawia potem własną liczbę (sprawy do
   zrobienia) i zdejmuje licznik, gdy nic nie zostało — iOS sam go nie zdejmuje. Bez Badging
   API w workerze (Android zwykle: licznik rysuje launcher z aktywnych powiadomień) — nic.
   Nigdy osobny push „tylko na licznik": push bez powiadomienia kosztuje zgodę na iPhonie. */
async function ustawLicznik() {
  const n = self.navigator;
  if (!n || !('setAppBadge' in n) || typeof self.registration.getNotifications !== 'function') return;
  const ile = (await self.registration.getNotifications()).length;
  await (ile > 0 ? n.setAppBadge(ile) : n.clearAppBadge());
}

self.addEventListener('push', e => {
  let tekst = '';
  try { tekst = e.data ? e.data.text() : ''; } catch { /* pusta treść — domyślny tytuł */ }
  const [tytul, opcje] = trescPush(tekst);
  // Zapis odbioru i licznik nie mogą zatrzymać pokazania: bez IndexedDB czy Badging API
  // powiadomienie i tak wychodzi.
  e.waitUntil(Promise.all([
    self.registration.showNotification(tytul, opcje).then(() => ustawLicznik().catch(() => null)),
    opcje.data.id ? zapiszOdebrane(opcje.data.id).catch(() => null) : null,
  ]));
});

/* Cel zapisany w Cache API dla zimnego startu. iPhone przy zimnym starcie aplikacji otwiera
   po kliknięciu start_url zamiast adresu z openWindow (WebKit 263687), więc index.html
   na starcie zagląda tutaj i przechodzi do celu. Zapis względny wobec zakresu ('#azalia',
   u starego workera 'rosliny.html#roslina=…' — aplikacja przyjmuje oba) i z czasem:
   aplikacja bierze tylko świeży i kasuje go zawsze, żeby następne uruchomienie z ikony
   otworzyło Dom. Klucz './cel' rozwiązuje się tu względem sw.js, a w index.html względem
   strony — oba pliki leżą w tym samym katalogu. */
async function zapiszCel(cel) {
  const zakres = self.registration.scope;
  const wzgledny = cel.slice(zakres.length);
  if (!wzgledny) return;
  const c = await caches.open(CEL);
  await c.put('./cel', new Response(JSON.stringify({ cel: wzgledny, ts: Date.now() }),
    { headers: { 'Content-Type': 'application/json' } }));
}

/** Okno z samą aplikacją (index.html pod zakresem, z dowolnym hashem) — ona przejdzie do celu
    we własnym routingu. Inne okno w zakresie to stara strona sprzed aktualizacji (np. dawna
    rosliny.html otwarta od wczoraj), która wiadomości nie rozumie. */
function oknoAplikacji(adres, zakres) {
  const bez = String(adres).split('#')[0].split('?')[0];
  return bez === zakres || bez === zakres + 'index.html';
}

async function otworzCel(cel) {
  // Tylko okna, którymi ten worker steruje. Okno spoza kontroli (albo karta innego
  // projektu na github.io) nie jest nasze: nowe okno.
  const okna = (await self.clients.matchAll({ type: 'window' })).filter(o => o.url.startsWith(self.registration.scope));
  const zakres = self.registration.scope;
  const aplikacja = okna.find(o => oknoAplikacji(o.url, zakres));
  if (aplikacja) {
    // Przy otwartej aplikacji cel idzie wiadomością: aplikacja przechodzi do niego jak po
    // stuknięciu (szczegół z rodzicem pod spodem). navigate() na sam hash dawał w aplikacji
    // jednej strony tylko popstate — przejście „wstecz" i bez rodzica w historii, a na
    // iPhonie navigate() nie jest sprawdzone. Wiadomość przed focus(): gdyby fokus odmówił,
    // aplikacja i tak jest już na celu. Bez openWindow: Chrome daje na jedno kliknięcie
    // jeden focus() albo jedno openWindow() (przegląd 9.10).
    try { aplikacja.postMessage({ typ: 'cel', cel }); } catch { /* okno zamknięte w międzyczasie */ }
    try { await aplikacja.focus(); } catch { /* fokus już jest */ }
    return;
  }
  if (okna.length) {
    // Stara strona w oknie: pełne przejście do celu ładuje aktualną aplikację.
    try { await okna[0].focus(); await okna[0].navigate(cel); } catch { /* fokus już jest */ }
    return;
  }
  // Cel tylko przed openWindow, czyli przy zimnym starcie — tam działa obejście. Przy
  // otwartym oknie zapisany cel mógłby zostać i przerzucić do niego następne uruchomienie
  // z ikony. Zapis przed otwarciem, bo strona otwarta przez openWindow może ruszyć od razu.
  try { await zapiszCel(cel); } catch { /* bez Cache API — zostaje samo openWindow */ }
  await self.clients.openWindow(cel);
}

self.addEventListener('notificationclick', e => {
  e.notification.close();
  const dane = e.notification.data || {};
  e.waitUntil(otworzCel(celKlikniecia(dane.url, self.registration.scope)));
});
