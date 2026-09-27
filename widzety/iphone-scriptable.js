// Smart Home — widżet na iPhone'a dla aplikacji Scriptable.
//
// Czyta data/teraz.json, który kolektor zapisuje przy każdym przebiegu: ostatnia
// temperatura i wilgotność w każdym pokoju, próg pleśni i temperatura na dworze.
// Dotknięcie widżetu otwiera stronę. Instrukcja: README, „Widżety na telefon".
//
// Rozmiary: mały i średni. Wilgotność pokoju, który jest ponad progiem pleśni,
// świeci na pomarańczowo; godzina odczytu też, gdy dane są starsze niż trzy godziny.

const DANE = "https://bronek31.github.io/Smart-Home/data/teraz.json";
const STRONA = "https://bronek31.github.io/Smart-Home/";
const KOLOR = {
  tlo: new Color("#0f1419"),
  tekst: new Color("#e4ebf1"),
  szary: new Color("#8496a5"),
  uwaga: new Color("#e8a13c"),
};
const STARE_PO_MIN = 180;

const liczba = (v, miejsc) => (v == null ? "–" : v.toFixed(miejsc).replace(".", ","));
const dwieCyfry = (n) => String(n).padStart(2, "0");

function napis(gdzie, tresc, font, kolor) {
  const t = gdzie.addText(tresc);
  t.font = font;
  t.textColor = kolor;
  t.lineLimit = 1;
  t.minimumScaleFactor = 0.7;
  return t;
}

async function zbuduj() {
  const maly = config.widgetFamily === "small";
  const rozmiar = maly ? 12 : 14;
  const w = new ListWidget();
  w.backgroundColor = KOLOR.tlo;
  w.url = STRONA;
  w.setPadding(12, 14, 12, 14);
  // iOS i tak decyduje sam, kiedy odświeżyć — to tylko prośba o „nie wcześniej niż"
  w.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000);

  let d;
  try {
    const zapytanie = new Request(DANE);
    zapytanie.timeoutInterval = 20;
    d = await zapytanie.loadJSON();
  } catch (blad) {
    napis(w, "Smart Home", Font.boldSystemFont(rozmiar), KOLOR.tekst);
    napis(w, "brak połączenia", Font.systemFont(rozmiar - 2), KOLOR.szary);
    return w;
  }

  const naglowek = w.addStack();
  naglowek.centerAlignContent();
  napis(naglowek, "DOM", Font.boldSystemFont(rozmiar - 3), KOLOR.szary);
  naglowek.addSpacer();
  if (d.dwor) napis(naglowek, `dwór ${liczba(d.dwor.t, 1)}°`, Font.systemFont(rozmiar - 3), KOLOR.szary);
  w.addSpacer(6);

  for (const p of d.pokoje || []) {
    const wiersz = w.addStack();
    wiersz.centerAlignContent();
    napis(wiersz, p.nazwa, Font.mediumSystemFont(rozmiar), KOLOR.tekst);
    wiersz.addSpacer();
    napis(wiersz, `${liczba(p.t, 1)}°`, Font.boldSystemFont(rozmiar), KOLOR.tekst);
    wiersz.addSpacer(maly ? 6 : 10);
    napis(wiersz, `${liczba(p.h, 0)}%`, Font.systemFont(rozmiar), p.plesn ? KOLOR.uwaga : KOLOR.szary);
    w.addSpacer(maly ? 2 : 4);
  }

  w.addSpacer();
  const odczyty = (d.pokoje || []).map((p) => Date.parse(p.odczyt)).filter((t) => !isNaN(t));
  if (odczyty.length) {
    const najnowszy = Math.max(...odczyty);
    const g = new Date(najnowszy);
    const stare = (Date.now() - najnowszy) / 60000 > STARE_PO_MIN;
    const wilgotno = d.pokoje.some((p) => p.plesn);
    napis(w, `odczyt ${dwieCyfry(g.getHours())}:${dwieCyfry(g.getMinutes())}` + (wilgotno ? " · wilgotno" : ""),
      Font.systemFont(rozmiar - 4), stare || wilgotno ? KOLOR.uwaga : KOLOR.szary);
  }
  return w;
}

const widget = await zbuduj();
if (config.runsInWidget) Script.setWidget(widget);
else await widget.presentMedium();
Script.complete();
