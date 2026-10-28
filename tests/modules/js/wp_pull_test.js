// Test PRAWDZIWEGO kodu modules/static/js/pages/wp-pull-view.js w Node: model widoku podsumowania podglądu i pobrania pary z WP (W7a).
// Uruchomienie: node wp_pull_test.js   (kod wyjścia 0 = wszystko przeszło)
const assert = require('assert');
const path = require('path');

const v = require(path.resolve(__dirname, '..', '..', '..', 'modules', 'static', 'js', 'pages', 'wp-pull-view.js'));

const NOW = Date.parse('2026-10-28T12:00:00');
const base = (over) => Object.assign({enabled: true, connected: true, pulling: false, items: [{key: '1:10'}], pull: null, last_apply_at: ''}, over);
const raport = (over) => Object.assign({
  liczniki: {druzyny: {dodano: 4, zaktualizowano: 0, bez_zmian: 0, pominieto: 0}, zawodnicy: {dodano: 9, zaktualizowano: 1, bez_zmian: 2, pominieto: 1},
    mecze: {dodano: 3, zaktualizowano: 0, bez_zmian: 0, pominieto: 1}},
  pominiete: [], korekty: [], rozbieznosci: [], brak_logo: [], skroty_wyliczone: [], dolaczono: [], nieobecne: [], zablokowane: [], zmiany: [],
  do_ustalenia_liczba: 0}, over);
const pull = (over) => Object.assign({ok: true, zapisano: true, apply: true, key: '1:10', label: 'Dywizja A — Jesień 2026', at: '2026-10-28T11:00:00', raport: raport()}, over);

const tests = [];
const t = (name, fn) => tests.push([name, fn]);

t('moduł bez WP: nic do pokazania, przyciski nieaktywne', () => {
  const vm = v.wpPullViewModel({enabled: false}, NOW);
  assert.strictEqual(vm.canPull, false);
  assert.strictEqual(vm.hasResult, false);
});

t('przyciski aktywne tylko przy połączeniu, bez trwającego pobierania i z niepustą listą', () => {
  assert.strictEqual(v.wpPullViewModel(base(), NOW).canPull, true);
  assert.strictEqual(v.wpPullViewModel(base({connected: false}), NOW).canPull, false);
  assert.strictEqual(v.wpPullViewModel(base({pulling: true}), NOW).canPull, false);
  assert.strictEqual(v.wpPullViewModel(base({pulling: true}), NOW).busy, true);
  assert.strictEqual(v.wpPullViewModel(base({items: []}), NOW).canPull, false);
});

t('ostrzeżenie o starym pobraniu: brak pobrania, ponad 24 godziny, świeże', () => {
  assert.ok(v.wpPullViewModel(base(), NOW).staleWarning.includes('nie pobrano jeszcze'));
  assert.ok(v.wpPullViewModel(base({last_apply_at: '2026-10-27T11:00:00'}), NOW).staleWarning.includes('ponad 24 godziny'));
  assert.strictEqual(v.wpPullViewModel(base({last_apply_at: '2026-10-28T08:00:00'}), NOW).staleWarning, '');
});

t('tabelka: dodano, zaktualizowano, bez zmian, pominięto dla drużyn, zawodników i meczów', () => {
  const vm = v.wpPullViewModel(base({pull: pull()}), NOW);
  assert.deepStrictEqual(vm.table.map(r => r.label), ['Drużyny', 'Zawodnicy', 'Mecze']);
  assert.deepStrictEqual(vm.table[1], {label: 'Zawodnicy', added: 9, updated: 1, same: 2, skipped: 1});
  assert.ok(vm.title.startsWith('Pobranie: Dywizja A — Jesień 2026'));
});

t('podgląd ma inny tytuł i listę zmian, pobranie jej nie ma', () => {
  const p = pull({apply: false, zapisano: false, raport: raport({zmiany: ['dodano drużynę „A”']})});
  const vm = v.wpPullViewModel(base({pull: p}), NOW);
  assert.ok(vm.title.startsWith('Podgląd zmian'));
  assert.deepStrictEqual(vm.changes, ['dodano drużynę „A”']);
  assert.deepStrictEqual(v.wpPullViewModel(base({pull: pull({raport: raport({zmiany: ['x']})})}), NOW).changes, []);
});

t('sekcje pojawiają się tylko, gdy mają wpisy, w ustalonej kolejności', () => {
  const r = raport({korekty: ['A – B: korekta wyniku'], pominiete: ['C – D: mecz trwa'], nieobecne: ['mecz E – F']});
  const vm = v.wpPullViewModel(base({pull: pull({raport: r})}), NOW);
  assert.deepStrictEqual(vm.sections.map(s => s.key), ['pominiete', 'korekty', 'nieobecne']);
});

t('mecze „Do ustalenia”: osobny komunikat z liczbą mnogą', () => {
  assert.ok(v.wpPullViewModel(base({pull: pull({raport: raport({do_ustalenia_liczba: 7})})}), NOW).waiting.includes('7 meczów'));
  assert.ok(v.wpPullViewModel(base({pull: pull({raport: raport({do_ustalenia_liczba: 1})})}), NOW).waiting.includes('1 mecz '));
  assert.strictEqual(v.wpPullViewModel(base({pull: pull()}), NOW).waiting, '');
});

t('błąd pobrania: komunikat i brak tabeli', () => {
  const vm = v.wpPullViewModel(base({pull: {ok: false, zapisano: false, apply: true, key: '1:10', at: '2026-10-28T11:00:00', blad: 'Pobieranie przerwane, baza bez zmian: x'}}), NOW);
  assert.strictEqual(vm.error, 'Pobieranie przerwane, baza bez zmian: x');
  assert.deepStrictEqual(vm.table, []);
});

t('pobranie bez zmian jest tak opisane', () => {
  const vm = v.wpPullViewModel(base({pull: pull({zapisano: false})}), NOW);
  assert.ok(vm.title.endsWith('brak zmian do zapisania'));
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); console.log('OK   ' + name); } catch (e) { failed++; console.log('FAIL ' + name + '\n     ' + e.message); }
}
process.exit(failed ? 1 : 0);
