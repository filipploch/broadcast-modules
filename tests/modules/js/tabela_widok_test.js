// W8b: PRAWDZIWA funkcja _renderStandingsTab z modules/static/js/pages/ui-jinja.js (wyciągnięta z pliku) razem z prawdziwym wp-tabela.js, w Node z atrapą DOM:
// błąd WP = czerwony komunikat bez przycisku wysyłania; sukces = nagłówek, ostrzeżenia (nie blokują), przycisk wysyłania i wiersze; tabela wirtualna pobiera final i live.
// Uruchomienie: node tabela_widok_test.js   (kod wyjścia 0 = wszystko przeszło)
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const kat = path.resolve(__dirname, '..', '..', '..', 'modules', 'static', 'js', 'pages');
const uij = fs.readFileSync(path.join(kat, 'ui-jinja.js'), 'utf8');
const a = uij.indexOf('function _renderStandingsTab');
const b = uij.indexOf('// ── BANERY', a);
assert.ok(a > 0 && b > a, 'nie znaleziono funkcji _renderStandingsTab w ui-jinja.js');
const funkcja = uij.slice(a, b);
const wpTabela = fs.readFileSync(path.join(kat, 'wp-tabela.js'), 'utf8');

function el() {
  const e = { children: [], style: {}, dataset: {}, _html: '', textContent: '', id: '' };
  e.appendChild = (c) => { e.children.push(c); return c; };
  Object.defineProperty(e, 'innerHTML', { get: () => e._html, set: (v) => { e._html = v; if (v === '') e.children = []; } });
  return e;
}

function uruchom(odpowiedzi) {
  const wyslane = [];
  const zadania = [];
  const ctx = {
    document: { createElement: () => el() },
    console: { log() {}, warn() {}, error() {} },
    fetch: (url) => { zadania.push(url); const o = odpowiedzi(url); return Promise.resolve({ status: o.status || 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(o.json))) }); },
    encodeURIComponent, Promise, JSON,
    _gamesTab: { maxGroupNr: 1 },
    _sendStandingsToOverlay: (t, d) => wyslane.push([t, d]),
  };
  ctx.window = ctx;
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(wpTabela, ctx);
  vm.runInContext(funkcja, ctx);
  return { ctx, wyslane, zadania };
}

const wiersz = (n, nazwa) => ({ position: n, team_name: nazwa, team_name_14: nazwa, team_short_name: nazwa.slice(0, 3).toUpperCase(), games: 2, wins: 1, draws: 1, loses: 0, goals_scored: 3, goals_lost: 1, goal_difference: 2, points: 4 });
const ok = (rows, warnings = [], live = 0) => ({ json: { ok: true, mode: 'final', rows, warnings, computed_at: '2026-11-05T12:34:56+00:00', engine: 'SAH2H', live_matches: live } });
const eq = (x, y) => assert.deepStrictEqual(JSON.parse(JSON.stringify(x)), JSON.parse(JSON.stringify(y)));
const czeka = () => new Promise((r) => setTimeout(r, 20));
const wyniki = [];
const przypadek = async (nazwa, fn) => { await fn(); wyniki.push(nazwa); };

(async () => {
await przypadek('WP nie odpowiada: czerwony komunikat, brak przycisku wysyłania i tabeli', async () => {
  const e = uruchom(() => ({ status: 503, json: { ok: false, kind: 'connection', error: 'Tabela niedostępna: WP nie odpowiada (brak połączenia).' } }));
  const kontener = el();
  e.ctx._renderStandingsTab('table', { league_id: 7 }, kontener);
  await czeka();
  eq(kontener.children.length, 1);
  assert.strictEqual(kontener.children[0].id, 'wp-tabela-blad');
  assert.ok(kontener.children[0].textContent.includes('WP nie odpowiada'));
  eq(e.wyslane, []);
});

await przypadek('tabela oficjalna: nagłówek z godziną, przycisk wysyłania, wiersze; ostrzeżenia nie blokują wysłania', async () => {
  const e = uruchom(() => ok([wiersz(1, 'Alfa'), wiersz(2, 'Beta')], [{ mecz: 'A - B', opis: 'Duplikat.', wplyw: 'liczona 2 razy' }]));
  const kontener = el();
  e.ctx._renderStandingsTab('table', { league_id: 7 }, kontener);
  await czeka();
  const ids = kontener.children.map((c) => c.id || c.tagName || c.textContent.slice(0, 20));
  assert.ok(kontener.children.some((c) => c.id === 'wp-tabela-info' && c.textContent.includes('12:34:56')));
  const ostrz = kontener.children.find((c) => c.id === 'wp-tabela-ostrzezenia');
  assert.ok(ostrz && ostrz.textContent.includes('Ostrzeżenia (1), nie blokują wysłania') && ostrz.textContent.includes('A - B: Duplikat. [liczona 2 razy]'));
  const przycisk = kontener.children.find((c) => c.textContent === '▶ Wyślij do overlay');
  assert.ok(przycisk, 'brak przycisku wysyłania: ' + ids.join(','));
  przycisk.onclick();
  eq(e.wyslane.length, 1);
  eq(e.wyslane[0][0], 'table');
  eq(e.wyslane[0][1].official.map((r) => r.team_name), ['Alfa', 'Beta']);
  const tabela = kontener.children.find((c) => c.children && c.children.length === 2);
  assert.ok(tabela, 'brak tabeli');
  eq(tabela.children[1].children.length, 2);                           // tbody z dwoma wierszami
  eq(e.zadania, ['/api/wp-tabela?league_id=7&mode=final']);
});

await przypadek('tabela wirtualna: pobiera final i live, ma notkę o trwających meczach i wysyła obie listy', async () => {
  const e = uruchom((url) => (url.includes('mode=live') ? ok([wiersz(1, 'Beta'), wiersz(2, 'Alfa')], [], 1) : ok([wiersz(1, 'Alfa'), wiersz(2, 'Beta')])));
  const kontener = el();
  e.ctx._renderStandingsTab('virtual', { league_id: 7 }, kontener);
  await czeka();
  eq(e.zadania, ['/api/wp-tabela?league_id=7&mode=final', '/api/wp-tabela?league_id=7&mode=live']);
  const przycisk = kontener.children.find((c) => c.textContent === '▶ Wyślij do overlay');
  przycisk.onclick();
  eq(e.wyslane[0][0], 'virtual');
  eq([e.wyslane[0][1].official[0].team_name, e.wyslane[0][1].virtual[0].team_name], ['Alfa', 'Beta']);
  assert.ok(kontener.children.some((c) => (c.textContent || '').includes('trwających meczów')) || kontener._html.includes('trwających meczów'));
});

await przypadek('brak wybranej ligi: komunikat bez żądań do WP', async () => {
  const e = uruchom(() => ok([]));
  const kontener = el();
  e.ctx._renderStandingsTab('table', { league_id: null }, kontener);
  await czeka();
  assert.ok(kontener._html.includes('Brak wybranej ligi'));
  eq(e.zadania, []);
});

console.log('OK ' + wyniki.length + ' przypadków: ' + wyniki.join('; '));
})().catch((e) => { console.error(e); process.exit(1); });
