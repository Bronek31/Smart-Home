// Widżet na iPhone'a (widzety/iphone-scriptable.js) uruchamiany poza telefonem.
//
// Scriptable nie ma wersji na komputer, więc podstawiamy mu atrapy tych kilku klas,
// których skrypt używa, i patrzymy, co trafiłoby na widżet. Nie sprawdza to wyglądu,
// ale łapie to, co psuje się najczęściej: literówkę w nazwie pola teraz.json po zmianie
// kolektora albo wywrotkę na brakujących danych — a tego na telefonie nikt by nie
// zauważył, bo widżet po prostu przestałby się odświeżać.
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SKRYPT = fs.readFileSync(path.join(__dirname, '..', '..', 'widzety', 'iphone-scriptable.js'), 'utf8');

function uruchom(dane, { rodzina = 'medium', blad = false } = {}) {
  const napisy = [];
  class Stos {
    constructor() { this.elementy = []; }
    addText(t) { const el = { text: t }; napisy.push(el); this.elementy.push(el); return el; }
    addStack() { const s = new Stos(); this.elementy.push(s); return s; }
    addSpacer() {}
    setPadding() {}
    centerAlignContent() {}
  }
  let ustawiony = null;
  const kontekst = {
    Color: class { constructor(hex) { this.hex = hex; } },
    Font: { boldSystemFont: (n) => `b${n}`, systemFont: (n) => `r${n}`, mediumSystemFont: (n) => `m${n}` },
    ListWidget: Stos,
    Request: class {
      constructor(url) { this.url = url; }
      async loadJSON() { if (blad) throw new Error('brak sieci'); return dane; }
    },
    config: { runsInWidget: true, widgetFamily: rodzina },
    Script: { setWidget: (w) => { ustawiony = w; }, complete: () => {} },
    Date, Math, String, isNaN,
  };
  vm.createContext(kontekst);
  return new vm.Script(`(async () => {${SKRYPT}\n})()`).runInContext(kontekst)
    .then(() => ({ napisy, widget: ustawiony }));
}

const PRZYKLAD = {
  updated: '2026-09-27T19:30:00Z',
  pokoje: [
    { nazwa: 'Salon', t: 19.9, h: 66, odczyt: new Date(Date.now() - 20 * 60e3).toISOString(), prog: 75, plesn: false },
    { nazwa: 'Kuchnia', t: 19.9, h: 76, odczyt: new Date(Date.now() - 10 * 60e3).toISOString(), prog: 75, plesn: true },
  ],
  dwor: { nazwa: 'Na zewnątrz', t: 16.2, h: 60 },
  tekst: '…',
};

test.describe('widżet na iPhone\'a', () => {
  test('pokazuje każdy pokój, dwór i godzinę odczytu', async () => {
    const { napisy, widget } = await uruchom(PRZYKLAD);
    const teksty = napisy.map((n) => n.text);
    expect(widget, 'skrypt nie oddał widżetu').not.toBeNull();
    expect(widget.url).toBe('https://bronek31.github.io/Smart-Home/');
    for (const t of ['Salon', 'Kuchnia', '19,9°', '66%', '76%', 'dwór 16,2°']) expect(teksty).toContain(t);
    expect(teksty.some((t) => /^odczyt \d\d:\d\d · wilgotno$/.test(t))).toBe(true);
  });

  test('wilgotność ponad progiem pleśni świeci inaczej niż reszta', async () => {
    const { napisy } = await uruchom(PRZYKLAD);
    const kolor = (t) => napisy.find((n) => n.text === t).textColor.hex;
    expect(kolor('76%')).not.toBe(kolor('66%'));
  });

  test('bez sieci pokazuje komunikat, zamiast się wywrócić', async () => {
    const { napisy, widget } = await uruchom(PRZYKLAD, { blad: true });
    expect(widget).not.toBeNull();
    expect(napisy.map((n) => n.text)).toContain('brak połączenia');
  });

  test('pusty plik nie wywraca widżetu', async () => {
    const { widget } = await uruchom({ updated: '2026-09-27T19:30:00Z', pokoje: [], dwor: null, tekst: '' }, { rodzina: 'small' });
    expect(widget).not.toBeNull();
  });

  // Strażnik zgodności z kolektorem: pola, których skrypt używa, muszą istnieć
  // w tym, co zapisuje write_teraz() w fetch.py.
  test('korzysta tylko z pól, które zapisuje kolektor', async () => {
    const kolektor = fs.readFileSync(path.join(__dirname, '..', '..', 'fetch.py'), 'utf8');
    for (const pole of ['"pokoje"', '"dwor"', '"nazwa"', '"t"', '"h"', '"odczyt"', '"plesn"']) {
      expect(kolektor, `fetch.py nie zapisuje ${pole}`).toContain(pole);
    }
  });
});
