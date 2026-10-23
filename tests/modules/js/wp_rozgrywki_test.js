// Test PRAWDZIWEGO kodu modules/static/js/pages/wp-competitions.js w Node (bez przeglądarki): model widoku karty "Rozgrywki WP".
// Uruchomienie: node wp_rozgrywki_test.js   (kod wyjścia 0 = wszystko przeszło)
const assert = require('assert');
const path = require('path');

const wp = require(path.resolve(__dirname, '..', '..', '..', 'modules', 'static', 'js', 'pages', 'wp-competitions.js'));

const item = (l, s, ln, sn, events, a, b) => ({key: `${l}:${s}`, league_id: l, season_id: s, league_name: ln, season_name: sn,
  events, first_date: a, last_date: b});
const base = (over) => Object.assign({enabled: true, problem: '', title: 'NALF', url: 'http://127.0.0.1:8091', has_auth: true,
  connected: true, error: '', from_cache: false, fetched_at: '', items: [], unassigned: 0, default: null, default_missing: false,
  needs_choice: false, no_competitions: false}, over);

const tests = [];
const t = (name, fn) => tests.push([name, fn]);

t('liczba mnoga: 1 mecz, 2-4 mecze, 5 i 12-14 meczów, 22 mecze', () => {
  assert.strictEqual(wp.wpPluralMatches(1), '1 mecz');
  assert.strictEqual(wp.wpPluralMatches(3), '3 mecze');
  assert.strictEqual(wp.wpPluralMatches(5), '5 meczów');
  assert.strictEqual(wp.wpPluralMatches(12), '12 meczów');
  assert.strictEqual(wp.wpPluralMatches(22), '22 mecze');
  assert.strictEqual(wp.wpPluralMatches(43), '43 mecze');
});

t('pozycja listy: nazwa, liczba meczów i zakres dat dd.mm.rrrr', () => {
  const vm = wp.wpViewModel(base({items: [item(1, 10, 'Dywizja A', 'Jesień 2026', 43, '2026-01-02', '2026-12-12')]}));
  assert.strictEqual(vm.rows[0].label, 'Dywizja A — Jesień 2026');
  assert.strictEqual(vm.rows[0].detail, '43 mecze · 02.01.2026 – 12.12.2026');
  const one = wp.wpViewModel(base({items: [item(1, 10, 'A', 'S', 1, '2026-03-01', '2026-03-01')]}));
  assert.strictEqual(one.rows[0].detail, '1 mecz · 01.03.2026');
});

t('wybrana domyślna jest zaznaczona i oznaczona; brak domyślnej: nic nie zaznaczone, prośba o wybór', () => {
  const items = [item(1, 10, 'A', 'S', 3, '', ''), item(2, 10, 'B', 'S', 2, '', '')];
  let vm = wp.wpViewModel(base({items, default: {key: '2:10', league_name: 'B', season_name: 'S', auto: false}}));
  assert.strictEqual(vm.selectedKey, '2:10');
  assert.deepStrictEqual(vm.rows.map(r => r.isDefault), [false, true]);
  assert.strictEqual(vm.hint, 'Domyślne rozgrywki modułu: B — S');
  vm = wp.wpViewModel(base({items, needs_choice: true}));
  assert.strictEqual(vm.selectedKey, null);
  assert.ok(vm.notes.some(n => n.text === 'Wybierz rozgrywki domyślne modułu.'));
  assert.strictEqual(vm.hint, 'Domyślne rozgrywki modułu: nie wybrano');
});

t('jedyna rozgrywka przypisana automatycznie: informacja o automacie', () => {
  const vm = wp.wpViewModel(base({items: [item(1, 10, 'A', 'S', 3, '', '')], default: {key: '1:10', league_name: 'A', season_name: 'S', auto: true}}));
  assert.ok(vm.notes.some(n => n.text.startsWith('Przypisano automatycznie')));
});

t('zapisana para, której nie ma w WP: ostrzeżenie, bez zaznaczenia', () => {
  const vm = wp.wpViewModel(base({items: [item(1, 11, 'A', 'W', 1, '', '')], default: {key: '2:10', league_name: 'B', season_name: 'S', auto: false},
    default_missing: true}));
  assert.strictEqual(vm.selectedKey, null);
  assert.ok(vm.notes.some(n => n.level === 'warning' && n.text.includes('nie ma już w WP')));
  assert.strictEqual(vm.hint, 'Domyślne rozgrywki modułu: nie wybrano');
});

t('brak połączenia: czerwony status z powodem i lista z ostatniego pobrania', () => {
  const vm = wp.wpViewModel(base({connected: false, error: 'brak połączenia z WP', from_cache: true, fetched_at: '2026-10-23T10:00:00',
    items: [item(1, 10, 'A', 'S', 3, '', '')]}));
  assert.strictEqual(vm.statusClass, 'wp-bad');
  assert.ok(vm.status.includes('brak połączenia z WP'));
  assert.strictEqual(vm.rows.length, 1);
  assert.ok(vm.notes.some(n => n.text.includes('2026-10-23 10:00:00')));
});

t('połączony, pusta instancja i mecze bez kategorii: komunikaty', () => {
  const vm = wp.wpViewModel(base({no_competitions: true, unassigned: 3}));
  assert.strictEqual(vm.statusClass, 'wp-ok');
  assert.strictEqual(vm.canSave, false);
  assert.ok(vm.notes.some(n => n.text.startsWith('W WP nie ma meczów z przypisaną ligą i sezonem')));
  assert.ok(vm.notes.some(n => n.text === '3 mecze bez ligi lub sezonu nie są na liście.'));
  assert.ok(wp.wpViewModel(base({unassigned: 1})).notes.some(n => n.text === '1 mecz bez ligi lub sezonu nie jest na liście.'));
});

t('brak danych logowania: informacja; moduł bez bloku wp: wyjaśnienie', () => {
  assert.ok(wp.wpViewModel(base({has_auth: false})).notes.some(n => n.text.startsWith('Brak danych logowania do WP')));
  const off = wp.wpViewModel({enabled: false, problem: ''});
  assert.ok(off.status.includes('brak bloku „wp”'));
  assert.deepStrictEqual(off.rows, []);
  const bad = wp.wpViewModel({enabled: false, problem: 'blok wp: nieprawidłowy port 80'});
  assert.ok(bad.notes.some(n => n.level === 'error'));
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); console.log('OK   ' + name); } catch (e) { failed++; console.log('FAIL ' + name + '\n     ' + e.message); }
}
process.exit(failed ? 1 : 0);
