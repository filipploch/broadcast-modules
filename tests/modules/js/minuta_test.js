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
const format = (nakladka, t, e) => uruchom(nakladka, 'format', t, e);
const zmiana = (nakladka, t, e) => uruchom(nakladka, 'substitution', JSON.stringify({ game_time_ms: t * 1000, period_end_s: e, team_short_name: '', substitutions: [] })).split(' ZMIANA')[0];

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
  const wyn = { zdarzenie: format(nakladka, p.t, p.E), zmiana: zmiana(nakladka, p.t, p.E), druga: format(DRUGA[nakladka], p.t, p.E) };
  const ok = wyn.zdarzenie === p.oczekiwane && wyn.zmiana === p.oczekiwane && wyn.druga === p.oczekiwane;
  if (!ok) zle++;
  wiersze.push({ p, wyn, ok });
}
const identyczne = tekstFunkcji('futsal-nalf') === tekstFunkcji('garbarnia') && tekstFunkcji('futsal-nalf') !== null;

if (RAPORT) {
  const pad = (s, n) => String(s).padEnd(n);
  console.log(pad('moduł / okres', 24) + pad('czas', 8) + pad('oczekiwane', 12) + pad('zdarzenie', 12) + pad('zmiana', 12) + pad('2. nakładka', 12) + 'wynik');
  for (const { p, wyn, ok } of wiersze) {
    console.log(pad(`${p.modul} ${p.okres}`, 24) + pad(p.czas, 8) + pad(p.oczekiwane, 12) + pad(wyn.zdarzenie, 12) + pad(wyn.zmiana, 12) + pad(wyn.druga, 12) + (ok ? 'OK' : 'ŹLE') + (p.uwaga ? '   (' + p.uwaga + ')' : ''));
  }
  console.log(`\nPrzypadków: ${wiersze.length}, zgodnych z regułą: ${wiersze.length - zle}, niezgodnych: ${zle}`);
  console.log(`Funkcja formatGameTimeDisplay identyczna w obu utils.js: ${identyczne ? 'TAK' : 'NIE'}`);
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
console.log(niepowodzenia ? `${niepowodzenia} niepowodzeń` : `OK ${wiersze.length} przypadków, funkcja identyczna w obu nakładkach`);
process.exit(niepowodzenia ? 1 : 0);
