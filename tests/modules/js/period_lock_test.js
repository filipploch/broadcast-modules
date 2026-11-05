// Zakończona część nie ma aktywnych przycisków zegara ani oznaczenia biegu (modules/static/js/pages/period-lock.js, prawdziwy kod w Node).
// Sprawdza też, że szablon strony głównej ładuje skrypt przed index.js. Uruchomienie: node period_lock_test.js
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const src = fs.readFileSync(path.join(ROOT, 'modules', 'static', 'js', 'pages', 'period-lock.js'), 'utf8');

function el(attrs) {
  const klasy = new Set(attrs.klasy || []);
  return { disabled: false, onclick: () => 1, attrs: { onclick: 'x()' }, dataset: attrs.dataset || {},
    classList: { add: (k) => klasy.add(k), remove: (k) => klasy.delete(k), contains: (k) => klasy.has(k) },
    setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; } };
}
function strona() {
  const przyciski = ['idle', 'running', 'paused'].map((s) => el({ klasy: s === 'paused' ? ['nodisplayed'] : [], dataset: { timerState: s } }));
  const naglowek = el({ klasy: ['timer-state-running'] });
  return { przyciski, naglowek, doc: { querySelectorAll: (sel) => (sel === '.timer-main-controller' ? przyciski : sel === '[data-state-for]' ? [naglowek] : []) } };
}
function PL() {
  const ctx = { console, document: undefined };
  ctx.window = ctx; ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return ctx.PeriodLock;
}

const wyniki = [];
const ok = (n, f) => { f(); wyniki.push(n); };

ok('część zakończona: wszystkie przyciski zegara wyłączone i ukryte, bez onclick; nagłówek nie sugeruje biegu', () => {
  const s = strona();
  assert.strictEqual(PL().zablokuj(s.doc, { status: 2 }), true);
  for (const b of s.przyciski) {
    assert.ok(b.disabled && b.attrs.disabled === 'disabled' && b.onclick === null && !('onclick' in b.attrs));
    assert.ok(b.classList.contains('nodisplayed') && b.classList.contains('period-finished'));
  }
  assert.ok(!s.naglowek.classList.contains('timer-state-running') && s.naglowek.classList.contains('timer-state-paused') && s.naglowek.classList.contains('timer-state-finished'));
});

ok('część nierozpoczęta, trwająca albo brak części: nic się nie zmienia (przyciski działają)', () => {
  for (const p of [{ status: 0 }, { status: 1 }, null, undefined]) {
    const s = strona();
    assert.strictEqual(PL().zablokuj(s.doc, p), false);
    assert.ok(s.przyciski.every((b) => !b.disabled && typeof b.onclick === 'function' && !b.classList.contains('period-finished')));
    assert.ok(s.naglowek.classList.contains('timer-state-running'));
  }
});

ok('szablon strony głównej ładuje period-lock.js przed index.js; index.js stosuje blokadę po zmianie stanu zegara i po zakończeniu części', () => {
  const html = fs.readFileSync(path.join(ROOT, 'modules', 'templates', 'index.html'), 'utf8');
  assert.ok(html.indexOf('pages/period-lock.js') > 0 && html.indexOf('pages/period-lock.js') < html.indexOf('pages/index.js'));
  const js = fs.readFileSync(path.join(ROOT, 'modules', 'static', 'js', 'pages', 'index.js'), 'utf8');
  assert.strictEqual((js.match(/PeriodLock\.zastosuj\(\)/g) || []).length, 2);
  assert.ok(js.includes('window.period.status = 2'));
});

console.log('OK ' + wyniki.length + ' przypadków: ' + wyniki.join('; '));
