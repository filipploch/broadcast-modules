// Reguła minuty zdarzenia (krok B): tabela przypadków tests/modules/js/minuta_przypadki.json wykonana na PRAWDZIWYM kodzie obu nakładek
// (hub/overlays/<nakladka>/js/utils.js i substitution.js) przez pomocnika overlay_time.js (Node, piaskownica vm).
//   node minuta_test.js            -> asercje: kod wyjścia 1, gdy jakikolwiek przypadek się nie zgadza
//   node minuta_test.js --raport   -> tylko raport (kod wyjścia 0): co dziś zgadza się z regułą, a co nie (krok B1, bez zmian w kodzie)
// Dla każdego przypadku sprawdzane są: formatGameTimeDisplay (zdarzenia), nagłówek nakładki zmiany (substitution.js) oraz ta sama wartość w DRUGIEJ nakładce.
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const RAPORT = process.argv.includes('--raport');
const HELPER = path.join(__dirname, 'overlay_time.js');
const PRZYPADKI = JSON.parse(fs.readFileSync(path.join(__dirname, 'minuta_przypadki.json'), 'utf8')).przypadki;
const NAKLADKA = { nalf: 'futsal-nalf', garbarnia: 'garbarnia' };
const DRUGA = { 'futsal-nalf': 'garbarnia', garbarnia: 'futsal-nalf' };

const uruchom = (...args) => JSON.parse(execFileSync(process.execPath, [HELPER, ...args.map(String)], { encoding: 'utf8' }));
const format = (nakladka, t, e, s) => uruchom(nakladka, 'format', t, e, s === undefined ? 'brak' : s);
const zmiana = (nakladka, t, e, s) => {
  const dane = { game_time_ms: t * 1000, period_end_s: e, team_short_name: '', substitutions: [] };
  if (s !== undefined) dane.period_start_s = s;
  return uruchom(nakladka, 'substitution', JSON.stringify(dane)).split(' ZMIANA')[0];
};

// Funkcja z obu utils.js ma mieć identyczną treść (jedna reguła dla obu nakładek)
function tekstFunkcji(nakladka) {
  const zrodlo = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'hub', 'overlays', nakladka, 'js', 'utils.js'), 'utf8');
  const m = zrodlo.match(/function formatGameTimeDisplay[\s\S]*?\n}/);
  return m ? m[0].replace(/\r\n/g, '\n') : null;
}

let zle = 0;
const wiersze = [];
for (const p of PRZYPADKI) {
  const nakladka = NAKLADKA[p.modul];
  const wyn = { zdarzenie: format(nakladka, p.t, p.E, p.S), zmiana: zmiana(nakladka, p.t, p.E, p.S), druga: format(DRUGA[nakladka], p.t, p.E, p.S) };
  const ok = wyn.zdarzenie === p.oczekiwane && wyn.zmiana === p.oczekiwane && wyn.druga === p.oczekiwane;
  if (!ok) zle++;
  wiersze.push({ p, wyn, ok });
}
const identyczne = tekstFunkcji('futsal-nalf') === tekstFunkcji('garbarnia') && tekstFunkcji('futsal-nalf') !== null;

// Zgodność wstecz: bez początku okresu w ładunku (brak, null, NaN, tekst, wartość ujemna) wynik jak przed regułą, bez błędu
const BEZ_S = [
  // [t, E, S (undefined = brak), oczekiwane jak dotąd]
  [0, 2700, undefined, "0'"], [2700, 5400, undefined, "45'"], [2701, 5400, undefined, "46'"], [2705, 2700, undefined, "45+1'"], [1200, 2400, undefined, "20'"],
  [0, 2700, 'null', "0'"], [0, 2700, 'NaN', "0'"], [0, 2700, 'abc', "0'"], [0, 2700, -1, "0'"], [2700, 5400, 'null', "45'"], [2700, 5400, 'abc', "45'"],
];
const legacy = [];
for (const [t, e, s, oczekiwane] of BEZ_S) {
  for (const nakladka of ['futsal-nalf', 'garbarnia']) {
    let wynik, blad = null;
    try { wynik = format(nakladka, t, e, s); } catch (err) { blad = err.message.split('\n')[0]; }
    legacy.push({ opis: `${nakladka} t=${t} E=${e} S=${s}`, oczekiwane, wynik, ok: blad === null && wynik === oczekiwane, blad });
  }
}
// zmiana: ładunek bez period_start_s
for (const nakladka of ['futsal-nalf', 'garbarnia']) {
  const wynik = zmiana(nakladka, 2700, 5400);
  legacy.push({ opis: `${nakladka} nagłówek zmiany bez period_start_s (45:00, E=90:00)`, oczekiwane: "45'", wynik, ok: wynik === "45'", blad: null });
}

// Panel (ui-jinja.js): domyślna minuta w edytorze zmiany jako liczba minut; ta sama reguła (czas doliczony = E/60 + k, np. 45+1' = 46)
const vm = require('vm');
function funkcjaPanelu() {
  const zrodlo = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'modules', 'static', 'js', 'pages', 'ui-jinja.js'), 'utf8');
  const m = zrodlo.match(/function substDefaultMinute[\s\S]*?\n}/);
  if (!m) return null;
  const ctx = vm.createContext({});
  vm.runInContext(m[0], ctx);
  return ctx.substDefaultMinute;
}
const panel = funkcjaPanelu();
const minutaLiczbowa = (tekst) => tekst.replace("'", '').split('+').reduce((a, b) => a + Number(b), 0);
const panelWiersze = panel ? PRZYPADKI.map((p) => ({ p, wynik: panel(p.t, p.S), oczekiwane: minutaLiczbowa(p.oczekiwane) })) : [];
const panelBez = panel ? [panel(0, undefined), panel(2700, null), panel(2700, 'abc'), panel(0, -1), panel(2701, undefined)] : [];
const panelZle = panelWiersze.filter((w) => w.wynik !== w.oczekiwane);
const panelBezOk = panel && JSON.stringify(panelBez) === JSON.stringify([0, 45, 45, 0, 46]);

if (RAPORT) {
  const pad = (s, n) => String(s).padEnd(n);
  console.log(pad('moduł / okres', 24) + pad('czas', 8) + pad('oczekiwane', 12) + pad('zdarzenie', 12) + pad('zmiana', 12) + pad('2. nakładka', 12) + 'wynik');
  for (const { p, wyn, ok } of wiersze) {
    console.log(pad(`${p.modul} ${p.okres}`, 24) + pad(p.czas, 8) + pad(p.oczekiwane, 12) + pad(wyn.zdarzenie, 12) + pad(wyn.zmiana, 12) + pad(wyn.druga, 12) + (ok ? 'OK' : 'ŹLE') + (p.uwaga ? '   (' + p.uwaga + ')' : ''));
  }
  console.log(`\nPrzypadków: ${wiersze.length}, zgodnych z regułą: ${wiersze.length - zle}, niezgodnych: ${zle}`);
  console.log(`Funkcja formatGameTimeDisplay identyczna w obu utils.js: ${identyczne ? 'TAK' : 'NIE'}`);
  console.log(`Zgodność wstecz (bez początku okresu): ${legacy.filter((l) => l.ok).length}/${legacy.length} jak dotąd`);
  console.log(`Panel (domyślna minuta w edytorze zmiany): ${panel ? `${panelWiersze.length - panelZle.length}/${panelWiersze.length} zgodnych z regułą, bez S jak dotąd: ${panelBezOk ? 'TAK' : 'NIE'}` : 'brak funkcji substDefaultMinute'}`);
  process.exit(0);
}

let niepowodzenia = 0;
for (const { p, wyn, ok } of wiersze) {
  if (!ok) {
    niepowodzenia++;
    console.log(`FAIL ${p.modul} ${p.okres} ${p.czas}: oczekiwane ${p.oczekiwane}, zdarzenie ${wyn.zdarzenie}, zmiana ${wyn.zmiana}, druga nakładka ${wyn.druga}`);
  }
}
if (!identyczne) { niepowodzenia++; console.log('FAIL funkcja formatGameTimeDisplay różni się między nakładkami'); }
for (const l of legacy) {
  if (!l.ok) { niepowodzenia++; console.log(`FAIL (bez S) ${l.opis}: oczekiwane ${l.oczekiwane}, jest ${l.wynik}${l.blad ? ' błąd: ' + l.blad : ''}`); }
}
if (!panel) { niepowodzenia++; console.log('FAIL brak funkcji substDefaultMinute w ui-jinja.js'); }
for (const w of panelZle) { niepowodzenia++; console.log(`FAIL panel ${w.p.modul} ${w.p.okres} ${w.p.czas}: oczekiwane ${w.oczekiwane}, jest ${w.wynik}`); }
if (panel && !panelBezOk) { niepowodzenia++; console.log(`FAIL panel bez S nie działa jak dotąd: ${JSON.stringify(panelBez)}`); }
console.log(niepowodzenia ? `${niepowodzenia} niepowodzeń` : `OK ${wiersze.length} przypadków (zdarzenie, zmiana, druga nakładka), ${legacy.length} bez S jak dotąd, panel ${panelWiersze.length}, funkcja identyczna w obu nakładkach`);
process.exit(niepowodzenia ? 1 : 0);
