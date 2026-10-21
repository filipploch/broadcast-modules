// Test PRAWDZIWEGO kodu modules/static/js/core/offline-guard.js w Node (bez przeglądarki): atrapa socket.io i atrapa dokumentu.
// Uruchomienie: node offline_guard_test.js   (kod wyjścia 0 = wszystko przeszło)
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const src = fs.readFileSync(path.resolve(__dirname, '..', '..', '..', 'modules', 'static', 'js', 'core', 'offline-guard.js'), 'utf8');

function makeDoc() {
  const els = {};
  const doc = {
    body: { appendChild(el) { els[el.id] = el; } },
    getElementById: (id) => els[id] || null,
    createElement: () => ({ style: {}, setAttribute() {}, textContent: '', id: '' }),
    els,
  };
  return doc;
}

function makeSocket(connected) {
  const handlers = {};
  const sent = [];
  return {
    connected,
    sent,
    emit(...args) { sent.push(args); return this; },
    on(ev, fn) { (handlers[ev] = handlers[ev] || []).push(fn); },
    fire(ev) { (handlers[ev] || []).forEach((f) => f()); },
  };
}

function load(extra) {
  const ctx = { globalThis: null, ...extra };
  ctx.globalThis = ctx;
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return ctx;
}

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('połączony: akcja przechodzi', () => {
  const g = load({}).OfflineGuard;
  const s = makeSocket(true);
  g.guardSocket(s, { document: makeDoc(), reload() {} });
  s.emit('timer_start', { id: 1 });
  assert.deepStrictEqual(s.sent, [['timer_start', { id: 1 }]]);
});

test('rozłączony: akcja nie jest wysyłana ani przechowywana, jest pasek', () => {
  const g = load({}).OfflineGuard;
  const doc = makeDoc();
  const s = makeSocket(false);
  g.guardSocket(s, { document: doc, reload() {} });
  s.emit('timer_start', { id: 1 });
  s.emit('start_recording');
  assert.deepStrictEqual(s.sent, [], 'akcje nie mogą trafić do klienta socket.io (przechowa je i wyśle po powrocie)');
  const bar = doc.els[g.BAR_ID];
  assert.ok(bar, 'pasek istnieje');
  assert.strictEqual(bar.textContent, 'MODUŁ: brak połączenia');
  assert.strictEqual(bar.style.display, 'block');
});

test('rozłączony: zapytania o stan przechodzą', () => {
  const g = load({}).OfflineGuard;
  const s = makeSocket(false);
  g.guardSocket(s, { document: makeDoc(), reload() {} });
  ['get_obs_record_status', 'request_initial_data', 'request_ui_monitor_content', 'timer_plugin_request_all_timers', 'search_interview_person']
    .forEach((ev) => s.emit(ev));
  assert.strictEqual(s.sent.length, 5);
});

test('request_camera_replay to akcja mimo nazwy "request_"', () => {
  const g = load({}).OfflineGuard;
  assert.strictEqual(g.isReadOnly('request_camera_replay'), false);
  assert.strictEqual(g.isReadOnly('request_initial_data'), true);
  assert.strictEqual(g.isReadOnly('show_overlay_container'), false);
  assert.strictEqual(g.isReadOnly('trigger_sequence'), false);
  assert.strictEqual(g.isReadOnly('dismiss_service_notice'), false);
});

test('powrót po rozłączeniu: pasek znika, strona przeładowana raz (stan od nowa)', () => {
  const g = load({}).OfflineGuard;
  const doc = makeDoc();
  let reloads = 0;
  const s = makeSocket(true);
  g.guardSocket(s, { document: doc, reload() { reloads++; } });
  s.connected = false; s.fire('disconnect');
  assert.strictEqual(doc.els[g.BAR_ID].style.display, 'block');
  s.emit('timer_start');                       // w czasie rozłączenia: odrzucone
  s.connected = true; s.fire('connect');
  assert.strictEqual(doc.els[g.BAR_ID].style.display, 'none');
  assert.strictEqual(reloads, 1);
  assert.deepStrictEqual(s.sent, [], 'nic z odrzuconych akcji nie zostaje odtworzone');
  s.fire('connect');                           // kolejne "connect" bez rozłączenia nie przeładowuje
  assert.strictEqual(reloads, 1);
});

test('pierwsze połączenie strony nie przeładowuje', () => {
  const g = load({}).OfflineGuard;
  let reloads = 0;
  const s = makeSocket(false);
  g.guardSocket(s, { document: makeDoc(), reload() { reloads++; } });
  s.connected = true; s.fire('connect');
  assert.strictEqual(reloads, 0);
});

test('błąd połączenia pokazuje pasek', () => {
  const g = load({}).OfflineGuard;
  const doc = makeDoc();
  const s = makeSocket(false);
  g.guardSocket(s, { document: doc, reload() {} });
  s.fire('connect_error');
  assert.strictEqual(doc.els[g.BAR_ID].style.display, 'block');
});

test('zabezpieczanie jest idempotentne', () => {
  const g = load({}).OfflineGuard;
  const s = makeSocket(true);
  const doc = makeDoc();
  g.guardSocket(s, { document: doc, reload() {} });
  const emit1 = s.emit;
  g.guardSocket(s, { document: doc, reload() {} });
  assert.strictEqual(s.emit, emit1);
});

test('io() jest opakowane: każde połączenie strony jest chronione, własności io zostają', () => {
  let created = 0;
  const io = function () { created++; return makeSocket(false); };
  io.protocol = 5;
  io.Manager = function Manager() {};
  const ctx = load({ io, document: makeDoc() });
  const s = ctx.io();
  assert.strictEqual(created, 1);
  assert.strictEqual(ctx.io.protocol, 5);
  assert.strictEqual(ctx.io.Manager, io.Manager);
  s.emit('timer_start');
  assert.deepStrictEqual(s.sent, []);
  assert.ok(ctx.OfflineGuard);
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); console.log('OK   ' + name); } catch (e) { failed++; console.log('FAIL ' + name + '\n     ' + e.message); }
}
process.exit(failed ? 1 : 0);
