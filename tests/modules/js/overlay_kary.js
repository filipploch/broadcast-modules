// Uruchamia PRAWDZIWY kod kar nakladki (time-display.js, penalty-timers-observers.js) w piaskownicy Node.
//   node overlay_kary.js <nakladka> <upływ_głównego_ms> <limit_kary_ms> <start_offset_ms>
// Wypisuje JSON: czy po syncState + tickMain element kary jest widoczny i jaki ma tekst.
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const [overlay, elapsed, limit, offset] = process.argv.slice(2);
const dir = path.resolve(__dirname, '..', '..', '..', 'hub', 'overlays', overlay, 'js');

const containers = {};
const makeEl = () => {
  const el = {
    style: {}, className: '', textContent: '', children: [], parentNode: null,
    setAttribute() {}, classList: { add() {}, remove() {} },
    appendChild(c) { c.parentNode = el; el.children.push(c); },
    removeChild(c) { el.children = el.children.filter(x => x !== c); },
  };
  return el;
};
['home-team-penalty-timer-container', 'away-team-penalty-timer-container'].forEach(id => { containers[id] = makeEl(); });
const sandbox = {
  console: { log() {}, error: console.error, warn() {} },
  document: { getElementById: (id) => containers[id] || null, createElement: makeEl },
  setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {},
};
sandbox.window = sandbox;
vm.createContext(sandbox);
for (const f of ['time-display.js', 'penalty-timers-observers.js']) {
  vm.runInContext(fs.readFileSync(path.join(dir, f), 'utf8'), sandbox, { filename: f });
}
sandbox.window.PenaltyTimers.syncState({
  home: [{ id: 1, team: 'home', player_id: 1, limit_ms: Number(limit), start_offset_ms: Number(offset), adjustment_ms: 0, state: 'paused' }],
  away: [],
});
sandbox.window.PenaltyTimers.tickMain(Number(elapsed));
const shown = containers['home-team-penalty-timer-container'].children;
console.log(JSON.stringify({ visible: shown.length > 0, text: shown.length ? shown[0].textContent : null }));
