// W7e-2b: PRAWDZIWY kod modules/static/js/pages/game-setup.js (panel „Dodaj spoza kadry”) w Node, z atrapą dokumentu, fetch i confirm.
// Uruchomienie: node spoza_kadry_ui_test.js   (kod wyjścia 0 = wszystko przeszło)
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const src = fs.readFileSync(path.resolve(__dirname, '..', '..', '..', 'modules', 'static', 'js', 'pages', 'game-setup.js'), 'utf8');
const PRELUDE = `let _contentType='home-squad', _assigned=[], _available=[], _starters=[], _substitutes=[], _isGarbarnia=false, _MAX_STARTERS=11;
function _reloadModal(){} `;

function makeEnv(garbarnia, odpowiedzi) {
  const els = {};
  const el = (id) => (els[id] = els[id] || { id, style: {}, innerHTML: '', textContent: '', value: '', checked: false, addEventListener() {}, classList: { add() {}, remove() {} } });
  const pytania = [];
  const posty = [];
  const ctx = {
    document: {
      getElementById: (id) => el(id),
      querySelector: (sel) => (sel.includes('value="free"') ? el('mode-free') : el('mode-all')),
    },
    fetch: (url, opts) => {
      if (opts && opts.method === 'POST') { posty.push({ url, body: JSON.parse(opts.body) }); }
      return Promise.resolve({ json: () => Promise.resolve(opts && opts.method === 'POST' ? { ok: true } : { players: odpowiedzi }) });
    },
    confirm: (t) => { pytania.push(t); return ctx.__tak; },
    alert: () => {},
    io: () => ({ on() {}, emit() {}, connected: true }),
    setTimeout, clearTimeout, encodeURIComponent, URLSearchParams, window: { location: { search: '' } }, history: { replaceState() {} },
    __tak: true,
  };
  vm.createContext(ctx);
  vm.runInContext(PRELUDE.replace("_isGarbarnia=false", `_isGarbarnia=${garbarnia}`) + src + '\nthis.__f = { loadOutsidePlayers, renderOutsideList, addOutsidePlayer, set: (a, s) => { _outsideList = a; _assigned = []; _substitutes = []; }, state: () => ({ assigned: _assigned, substitutes: _substitutes }) };', ctx);
  return { ctx, els, el, pytania, posty };
}

const LISTA = [
  { player_id: 1, label: 'Adamski Adam', last_name: 'Adamski', first_name: 'Adam', number: 10, team_name: 'Alfa', tag: '', w_drugiej_druzynie: false },
  { player_id: 2, label: 'Bielecki Bartek', last_name: 'Bielecki', first_name: 'Bartek', number: null, team_name: 'Beta', tag: 'inna drużyna', w_drugiej_druzynie: false },
  { player_id: 3, label: 'Cichy <b>', last_name: 'Cichy', first_name: 'C', number: 5, team_name: 'Beta', tag: 'inny klub', w_drugiej_druzynie: true },
  { player_id: 4, label: 'Wolny Wojtek', last_name: 'Wolny', first_name: 'Wojtek', number: 7, team_name: null, tag: '', w_drugiej_druzynie: false },
];

const eq = (a, b) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b));   // obiekty z piaskownicy vm mają inne prototypy
const wyniki = [];
const ok = (nazwa, fn) => { fn(); wyniki.push(nazwa); };

ok('lista pokazuje drużynę, numer, napis i „w drugiej drużynie meczu”; tekst jest zabezpieczony przed HTML', () => {
  const e = makeEnv(false, LISTA);
  e.ctx.__f.set(LISTA);
  e.ctx.__f.renderOutsideList();
  const html = e.el('outside-list').innerHTML;
  assert.ok(html.includes('Adamski Adam') && html.includes('Alfa') && html.includes('#10'));
  assert.ok(html.includes('inna drużyna') && html.includes('inny klub'));
  assert.ok(html.includes('w drugiej drużynie meczu') && html.includes('opacity:.55'));
  assert.ok(html.includes('bez drużyny'));
  assert.ok(!html.includes('<b>') && html.includes('&lt;b&gt;'));
  assert.ok(!/null|undefined/.test(html), 'na liście nie może być null ani undefined');
});

ok('własna drużyna i zawodnik bez drużyny: dodanie bez pytania, zapis składu wysłany z zawodnikiem', () => {
  const e = makeEnv(false, LISTA);
  e.ctx.__f.set(LISTA);
  e.ctx.__f.addOutsidePlayer(0);
  e.ctx.__f.addOutsidePlayer(3);
  eq(e.pytania, []);
  eq(e.posty.map((p) => p.body.assigned.map((a) => a.player_id)), [[1], [1, 4]]);
  assert.ok(e.posty.every((p) => p.url === '/api/assign/home-squad/save'));
  eq(e.ctx.__f.state().assigned.map((a) => a.player_id), [1, 4]);
});

ok('inna drużyna / inny klub: pytanie z nazwą drużyny; odmowa nic nie zmienia', () => {
  const e = makeEnv(false, LISTA);
  e.ctx.__f.set(LISTA);
  e.ctx.__tak = false;
  e.ctx.__f.addOutsidePlayer(1);
  assert.strictEqual(e.pytania.length, 1);
  assert.ok(e.pytania[0].includes('innej drużyny') && e.pytania[0].includes('(Beta)'));
  assert.strictEqual(e.posty.length, 0);
  eq(e.ctx.__f.state().assigned, []);
  e.ctx.__tak = true;
  e.ctx.__f.addOutsidePlayer(1);
  eq(e.ctx.__f.state().assigned.map((a) => a.player_id), [2]);
});

ok('zawodnik z drugiej drużyny meczu: pytanie o przeniesienie, po potwierdzeniu dodany', () => {
  const e = makeEnv(false, LISTA);
  e.ctx.__f.set(LISTA);
  e.ctx.__f.addOutsidePlayer(2);
  assert.ok(e.pytania[0].includes('drugiej drużyny tego meczu') && e.pytania[0].includes('Przenieść'));
  eq(e.ctx.__f.state().assigned.map((a) => a.player_id), [3]);
});

ok('Garbarnia: dodany awaryjnie trafia do rezerwowych', () => {
  const e = makeEnv(true, LISTA);
  e.ctx.__f.set(LISTA);
  e.ctx.__f.addOutsidePlayer(3);
  const st = e.ctx.__f.state();
  eq(st.substitutes.map((a) => [a.player_id, a.role]), [[4, 'substitute']]);
  eq(st.assigned, []);
  eq(e.posty[0].body.substitutes.map((a) => a.player_id), [4]);
  eq(e.posty[0].body.starters, []);
});

ok('zapytanie o listę niesie szukany tekst i tryb „tylko bez drużyny”', () => {
  const e = makeEnv(false, LISTA);
  const urls = [];
  const orig = e.ctx.fetch;
  e.ctx.fetch = (u, o) => { urls.push(u); return orig(u, o); };
  e.el('outside-search').value = ' ada ';
  e.el('mode-free').checked = true;
  e.ctx.__f.loadOutsidePlayers();
  assert.strictEqual(urls[0], '/api/assign/home-squad/outside?q=ada&only_free=1');
});

console.log('OK ' + wyniki.length + ' przypadków: ' + wyniki.join('; '));
