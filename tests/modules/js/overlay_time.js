// Uruchamia PRAWDZIWY kod grafik (hub/overlays/<nakladka>/js) w piaskownicy Node i wypisuje wynik jako JSON.
//   node overlay_time.js <nakladka> format <sekundy> <koniec_okresu_s>      -> formatGameTimeDisplay z utils.js
//   node overlay_time.js <nakladka> substitution <json z danymi zmiany>      -> tekst naglowka z showSubstitutionOverlay (substitution.js)
// Zamiast portu wzoru w Pythonie: testy wolaja ten skrypt, wiec zmiana wzoru w grafice od razu zmienia wynik testu.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [overlay, mode, ...args] = process.argv.slice(2);
const dir = path.resolve(__dirname, '..', '..', '..', 'hub', 'overlays', overlay, 'js');

const header = { textContent: '' };
const makeEl = () => {
  const el = { style: {}, className: '', innerHTML: '', offsetWidth: 0, appendChild() {}, remove() {}, classList: { add() {}, remove() {} }, querySelectorAll: () => [] };
  el.cloneNode = () => makeEl();
  el.parentNode = { replaceChild() {} };
  return el;
};
const els = {
  'substitutions-container': makeEl(),
  'substitutions': makeEl(),
  'substitution-header': header,
};
const sandbox = {
  console,
  document: {
    getElementById: (id) => els[id] || null,
    createElement: makeEl,
    querySelectorAll: () => [],
  },
  setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
  requestAnimationFrame: () => 0,
};
sandbox.window = sandbox;
vm.createContext(sandbox);

function load(file) {
  vm.runInContext(fs.readFileSync(path.join(dir, file), 'utf8'), sandbox, { filename: file });
}

load('utils.js');
let out;
if (mode === 'format') {
  out = vm.runInContext(`formatGameTimeDisplay(${Number(args[0])}, ${Number(args[1])})`, sandbox);
} else if (mode === 'substitution') {
  load('substitution.js');
  sandbox.__data = JSON.parse(args[0]);
  vm.runInContext('showSubstitutionOverlay(__data)', sandbox);
  out = header.textContent;
} else {
  console.error('nieznany tryb: ' + mode);
  process.exit(2);
}
process.stdout.write(JSON.stringify(out));
