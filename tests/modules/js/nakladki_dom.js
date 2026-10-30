// Atrapa przeglądarki do uruchamiania PRAWDZIWEGO kodu nakładek (hub/overlays/<nakladka>/overlay.html + js/*.js) w Node, bez jsdom.
// Używana przez nakladki_null_test.js (W7f-null): ładuje stronę (HTML + skrypty w kolejności z overlay.html), wysyła komunikaty przez ws.onmessage
// i zapisuje każdy zapis tekstu (textContent / innerText / innerHTML) oraz zmiany struktury (appendChild, classList.add).
// Zachowanie ustawień tekstu jak w przeglądarce: textContent = null/undefined -> "", innerText/innerHTML = null -> "" (undefined -> "undefined").
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const OVERLAYS_DIR = process.env.BM_OVERLAYS_DIR ? path.resolve(process.env.BM_OVERLAYS_DIR) : path.resolve(__dirname, '..', '..', '..', 'hub', 'overlays');      // BM_OVERLAYS_DIR: kod nakładek z innego miejsca (wzorzec z commitu sprzed zmiany)
const VOID = new Set(['img', 'br', 'hr', 'input', 'meta', 'link', 'source', 'area', 'base', 'col', 'embed', 'wbr']);

const camel = (s) => s.replace(/-([a-z])/g, (_, c) => c.toUpperCase());

function parseStyle(text) {
  const st = {};
  String(text || '').split(';').forEach((d) => {
    const i = d.indexOf(':');
    if (i > 0) st[camel(d.slice(0, i).trim())] = d.slice(i + 1).trim();
  });
  return st;
}

function makeStyle(init) {
  const st = Object.assign({}, init || {});
  Object.defineProperty(st, 'setProperty', { value: (k, v) => { st[camel(k)] = v; }, enumerable: false });
  Object.defineProperty(st, 'getPropertyValue', { value: (k) => st[camel(k)] || '', enumerable: false });
  Object.defineProperty(st, 'removeProperty', { value: (k) => { const o = st[camel(k)]; delete st[camel(k)]; return o || ''; }, enumerable: false });
  return st;
}

// ── selektory (podzbiór CSS używany w nakładkach) ────────────────────────────
function splitTop(s, sep) {
  const out = []; let depth = 0; let cur = '';
  for (const ch of s) {
    if (ch === '[' || ch === '(') depth++;
    if (ch === ']' || ch === ')') depth--;
    if (ch === sep && depth === 0) { out.push(cur); cur = ''; } else cur += ch;
  }
  out.push(cur);
  return out.map((x) => x.trim()).filter(Boolean);
}

function parseCompound(text) {
  const c = { tag: null, id: null, classes: [], attrs: [] };
  const re = /([#.]?)([A-Za-z0-9_-]+)|\[([^\]=^$*~|]+)(?:([=^$*~|]+)"?'?([^\]"']*)"?'?)?\]|(:[A-Za-z-]+(?:\([^)]*\))?)|(\*)/g;
  let m;
  let consumed = 0;
  while ((m = re.exec(text))) {
    consumed += m[0].length;
    if (m[6]) {
      const ps = m[6];
      if (ps === ':first-child' || ps === ':last-child') c.pseudos = (c.pseudos || []).concat(ps.slice(1));
      else if (ps.startsWith(':not(') && ps.endsWith(')')) c.nots = (c.nots || []).concat([parseCompound(ps.slice(5, -1))]);
      else throw new Error('selektor nieobsługiwany w atrapie DOM: ' + text);
      continue;
    }
    if (m[3]) c.attrs.push({ name: m[3], op: m[4] || null, value: m[5] });
    else if (m[1] === '#') c.id = m[2];
    else if (m[1] === '.') c.classes.push(m[2]);
    else if (m[2]) c.tag = m[2].toLowerCase();
  }
  if (consumed !== text.length) throw new Error('selektor nieobsługiwany w atrapie DOM: ' + text);
  return c;
}

function parseSelector(sel) {
  return splitTop(sel, ',').map((one) => {
    const parts = []; let comb = ' '; let cur = ''; let depth = 0;
    const flush = () => { if (cur) { parts.push({ comb, compound: parseCompound(cur) }); cur = ''; } };
    for (const ch of one) {
      if (ch === '[' || ch === '(') depth++;
      if (ch === ']' || ch === ')') depth--;
      if (depth === 0 && (ch === ' ' || ch === '>' || ch === '+' || ch === '~')) {
        flush();
        if (ch !== ' ') comb = ch; else if (!cur && parts.length) comb = comb === '>' ? '>' : ' ';
        continue;
      }
      cur += ch;
    }
    flush();
    return parts;
  });
}

function matchCompound(el, c) {
  if (!el || el.nodeType !== 1) return false;
  if (c.tag && el.tagName.toLowerCase() !== c.tag) return false;
  if (c.id && el.id !== c.id) return false;
  for (const cl of c.classes) if (!el.classList.contains(cl)) return false;
  for (const ps of c.pseudos || []) {
    const sib = el.parentNode ? el.parentNode.children : [];
    if (ps === 'first-child' && sib[0] !== el) return false;
    if (ps === 'last-child' && sib[sib.length - 1] !== el) return false;
  }
  for (const n of c.nots || []) if (matchCompound(el, n)) return false;
  for (const a of c.attrs) {
    const v = el.getAttribute(a.name);
    if (v === null) return false;
    if (a.op === '=' && v !== a.value) return false;
    if (a.op === '^=' && !v.startsWith(a.value)) return false;
    if (a.op === '$=' && !v.endsWith(a.value)) return false;
    if (a.op === '*=' && !v.includes(a.value)) return false;
  }
  return true;
}

function matchParts(el, parts, idx) {
  const { comb, compound } = parts[idx];
  if (!matchCompound(el, compound)) return false;
  if (idx === 0) return true;
  if (comb === '>') return !!el.parentNode && matchParts(el.parentNode, parts, idx - 1);
  if (comb === ' ') {
    for (let p = el.parentNode; p; p = p.parentNode) if (matchParts(p, parts, idx - 1)) return true;
    return false;
  }
  throw new Error('kombinator nieobsługiwany w atrapie DOM');
}

function matchesSelector(el, selector) {
  return parseSelector(selector).some((parts) => matchParts(el, parts, parts.length - 1));
}

// ── elementy ─────────────────────────────────────────────────────────────────
function createDomEnvironment(log) {
  class TextNode {
    constructor(text) { this.nodeType = 3; this.text = text; this.parentNode = null; }
    get textContent() { return this.text; }
  }

  class El {
    constructor(tag) {
      this.nodeType = 1;
      this.tagName = tag.toUpperCase();
      this.childNodes = [];
      this.parentNode = null;
      this._attrs = {};
      this._classes = [];
      this.style = makeStyle();
      this.dataset = {};
      this._listeners = {};
      this.classList = {
        add: (...c) => { c.forEach((x) => { if (!this._classes.includes(x)) { this._classes.push(x); log.push(`${this.key()}\t+class\t${x}`); } }); },
        remove: (...c) => { this._classes = this._classes.filter((x) => !c.includes(x)); },
        contains: (c) => this._classes.includes(c),
        toggle: (c, force) => { const on = force === undefined ? !this._classes.includes(c) : force; if (on) this.classList.add(c); else this.classList.remove(c); return on; },
        replace: (a, b) => { this.classList.remove(a); this.classList.add(b); },
      };
      for (const p of ['src', 'href', 'alt', 'title', 'value', 'placeholder', 'type', 'name']) this[p] = '';
      this._innerHTMLSet = null;
      this.sheet = { insertRule() { return 0; }, deleteRule() {}, cssRules: [] };      // element <style>: style-override.js dopisuje reguły CSS
    }

    get id() { return this._attrs.id || ''; }
    set id(v) { this._attrs.id = String(v); }
    get className() { return this._classes.join(' '); }
    set className(v) { this._classes = String(v).split(/\s+/).filter(Boolean); }
    key() {
      const id = this._attrs.id ? '#' + this._attrs.id : '';
      const cl = this._classes.length ? '.' + this._classes.join('.') : '';
      return this.tagName.toLowerCase() + id + cl;
    }

    // atrybuty
    getAttribute(n) { if (n === 'class') return this._classes.join(' ') || null; return Object.prototype.hasOwnProperty.call(this._attrs, n) ? this._attrs[n] : null; }
    setAttribute(n, v) {
      if (n === 'class') this.className = v;
      else if (n === 'style') this.style = makeStyle(parseStyle(v));
      else if (n.startsWith('data-')) { this.dataset[camel(n.slice(5))] = String(v); this._attrs[n] = String(v); } else this._attrs[n] = String(v);
    }
    removeAttribute(n) { delete this._attrs[n]; }
    hasAttribute(n) { return this.getAttribute(n) !== null; }

    // drzewo
    get children() { return this.childNodes.filter((c) => c.nodeType === 1); }
    get firstChild() { return this.childNodes[0] || null; }
    get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
    get firstElementChild() { return this.children[0] || null; }
    get lastElementChild() { const c = this.children; return c[c.length - 1] || null; }
    get parentElement() { return this.parentNode; }
    get nextSibling() { const s = this.parentNode ? this.parentNode.childNodes : []; return s[s.indexOf(this) + 1] || null; }
    get previousSibling() { const s = this.parentNode ? this.parentNode.childNodes : []; return s[s.indexOf(this) - 1] || null; }
    get nextElementSibling() { let n = this.nextSibling; while (n && n.nodeType !== 1) n = n.nextSibling; return n; }
    get previousElementSibling() { let n = this.previousSibling; while (n && n.nodeType !== 1) n = n.previousSibling; return n; }
    _detach(child) { if (child.parentNode) child.parentNode.childNodes.splice(child.parentNode.childNodes.indexOf(child), 1); child.parentNode = null; }
    appendChild(child) {
      if (child.nodeType === 11) { child.childNodes.slice().forEach((c) => this.appendChild(c)); return child; }
      this._detach(child);
      this.childNodes.push(child);
      child.parentNode = this;
      if (child.nodeType === 1) log.push(`${this.key()}\t+child\t${child.key()}`);
      return child;
    }
    append(...nodes) { nodes.forEach((n) => this.appendChild(typeof n === 'string' ? new TextNode(n) : n)); }
    prepend(...nodes) { nodes.reverse().forEach((n) => { this._detach(n); this.childNodes.unshift(n); n.parentNode = this; if (n.nodeType === 1) log.push(`${this.key()}\t+child\t${n.key()}`); }); }
    insertBefore(child, ref) {
      if (!ref) return this.appendChild(child);
      this._detach(child);
      this.childNodes.splice(this.childNodes.indexOf(ref), 0, child);
      child.parentNode = this;
      if (child.nodeType === 1) log.push(`${this.key()}\t+child\t${child.key()}`);
      return child;
    }
    removeChild(child) { this._detach(child); return child; }
    replaceChild(n, o) { this.insertBefore(n, o); this.removeChild(o); return o; }
    remove() { if (this.parentNode) this._detach(this); }
    contains(other) { for (let n = other; n; n = n.parentNode) if (n === this) return true; return false; }
    cloneNode(deep) {
      const c = new El(this.tagName);
      Object.assign(c._attrs, this._attrs);
      c._classes = this._classes.slice();
      c.style = makeStyle(Object.assign({}, this.style));
      Object.assign(c.dataset, this.dataset);
      if (deep) this.childNodes.forEach((n) => { if (n.nodeType === 1) { c.childNodes.push(n.cloneNode(true)); c.childNodes[c.childNodes.length - 1].parentNode = c; } else { const t = new TextNode(n.text); t.parentNode = c; c.childNodes.push(t); } });
      return c;
    }

    // tekst
    _text() { return this.childNodes.map((n) => (n.nodeType === 3 ? n.text : n._text())).join(''); }
    get textContent() { return this._text(); }
    set textContent(v) {
      const s = (v === null || v === undefined) ? '' : String(v);
      log.push(`${this.key()}\ttextContent\t${JSON.stringify(s)}`);
      this.childNodes.forEach((n) => { n.parentNode = null; });
      this.childNodes = s ? [Object.assign(new TextNode(s), { parentNode: this })] : [];
    }
    get innerText() { return this._text(); }
    set innerText(v) {
      const s = v === null ? '' : String(v);
      log.push(`${this.key()}\tinnerText\t${JSON.stringify(s)}`);
      this.childNodes.forEach((n) => { n.parentNode = null; });
      this.childNodes = s ? [Object.assign(new TextNode(s), { parentNode: this })] : [];
    }
    get innerHTML() { return this._innerHTMLSet !== null && this.childNodes.length === 0 ? this._innerHTMLSet : this.childNodes.map((n) => (n.nodeType === 3 ? n.text : n.outerHTML)).join(''); }
    set innerHTML(v) {
      const s = v === null ? '' : String(v);
      log.push(`${this.key()}\tinnerHTML\t${JSON.stringify(s)}`);
      this.childNodes.forEach((n) => { n.parentNode = null; });
      this.childNodes = [];
      this._innerHTMLSet = s;
      if (s) parseHtmlInto(this, s, false);
    }
    get outerHTML() { return `<${this.tagName.toLowerCase()}>${this.innerHTML}</${this.tagName.toLowerCase()}>`; }

    // wyszukiwanie
    _all(out) { this.children.forEach((c) => { out.push(c); c._all(out); }); return out; }
    querySelectorAll(sel) { return this._all([]).filter((e) => matchesSelector(e, sel)); }
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
    matches(sel) { return matchesSelector(this, sel); }
    closest(sel) { for (let n = this; n && n.nodeType === 1; n = n.parentNode) if (matchesSelector(n, sel)) return n; return null; }
    getElementsByClassName(c) { return this._all([]).filter((e) => e.classList.contains(c)); }
    getElementsByTagName(t) { return this._all([]).filter((e) => e.tagName === t.toUpperCase()); }

    // układ / zdarzenia (stałe, bez prawdziwego renderowania)
    get offsetWidth() { return 100; }
    get offsetHeight() { return 20; }
    get offsetTop() { return 0; }
    get offsetLeft() { return 0; }
    get clientWidth() { return 100; }
    get clientHeight() { return 20; }
    get scrollWidth() { return 100; }
    get scrollHeight() { return 20; }
    getBoundingClientRect() { return { top: 0, left: 0, width: 100, height: 20, right: 100, bottom: 20, x: 0, y: 0 }; }
    getAnimations() { return []; }
    animate() { return { finished: Promise.resolve(), cancel() {}, onfinish: null }; }
    addEventListener(t, fn) { (this._listeners[t] = this._listeners[t] || []).push(fn); }
    removeEventListener() {}
    dispatchEvent() { return true; }
    focus() {} blur() {} scrollIntoView() {} click() {}
    insertAdjacentHTML(pos, html) { const tmp = new El('div'); parseHtmlInto(tmp, html, false); tmp.childNodes.slice().forEach((c) => this.appendChild(c)); }
  }

  function parseHtmlInto(parent, html, record) {
    const stack = [parent];
    const re = /<!--[\s\S]*?-->|<\/([A-Za-z0-9-]+)\s*>|<([A-Za-z][A-Za-z0-9-]*)((?:\s+[^\s=>\/]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*(\/?)>|([^<]+)/g;
    let m;
    while ((m = re.exec(html))) {
      const top = stack[stack.length - 1];
      if (m[0].startsWith('<!--')) continue;
      if (m[1]) {
        const tag = m[1].toLowerCase();
        for (let i = stack.length - 1; i > 0; i--) { if (stack[i].tagName.toLowerCase() === tag) { stack.length = i; break; } }
      } else if (m[2]) {
        const tag = m[2].toLowerCase();
        const el = new El(tag);
        const attrRe = /([^\s=>\/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
        let a;
        while ((a = attrRe.exec(m[3]))) el.setAttribute(a[1], a[2] !== undefined ? a[2] : a[3] !== undefined ? a[3] : a[4] !== undefined ? a[4] : '');
        el.parentNode = top;
        top.childNodes.push(el);
        if (tag === 'script' || tag === 'style') {
          const close = html.indexOf('</' + tag, re.lastIndex);
          const body = html.slice(re.lastIndex, close < 0 ? html.length : close);
          if (body.trim()) { const t = new TextNode(body); t.parentNode = el; el.childNodes.push(t); }
          re.lastIndex = close < 0 ? html.length : html.indexOf('>', close) + 1;
        } else if (!VOID.has(tag) && !m[4]) stack.push(el);
      } else if (m[5]) {
        if (m[5].trim() || top !== parent) { const t = new TextNode(m[5].replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"')); t.parentNode = top; top.childNodes.push(t); }
      }
    }
  }

  return { El, TextNode, parseHtmlInto };
}

// ── strona nakładki ─────────────────────────────────────────────────────────
function loadOverlayPage(overlayName, opts = {}) {
  const log = [];
  const { El, parseHtmlInto } = createDomEnvironment(log);
  const dir = path.join(OVERLAYS_DIR, overlayName);
  const html = fs.readFileSync(path.join(dir, 'overlay.html'), 'utf8');

  const root = new El('html');
  parseHtmlInto(root, html, false);
  const htmlEl = root.children.find((c) => c.tagName === 'HTML') || root;
  const body = htmlEl.querySelector('body') || htmlEl;
  log.length = 0;                                                    // parsowanie HTML to nie zapisy nakładki

  // zegary wirtualne
  let now = 0; let seq = 0;
  const timeouts = [];
  const intervals = new Map();
  const setTimeoutF = (fn, ms = 0, ...a) => { const id = ++seq; timeouts.push({ id, at: now + (+ms || 0), fn: () => fn(...a), order: id }); return id; };
  const clearTimeoutF = (id) => { const i = timeouts.findIndex((t) => t.id === id); if (i >= 0) timeouts.splice(i, 1); intervals.delete(id); };
  const setIntervalF = (fn, ms = 0) => { const id = ++seq; intervals.set(id, { fn, ms: Math.max(1, +ms || 1), next: now + Math.max(1, +ms || 1) }); return id; };
  function advance(ms) {
    const end = now + ms;
    for (let guard = 0; guard < 5000; guard++) {
      timeouts.sort((a, b) => a.at - b.at || a.order - b.order);
      const nextT = timeouts.length ? timeouts[0].at : Infinity;
      let nextI = Infinity; let nextIid = null;
      intervals.forEach((v, id) => { if (v.next < nextI) { nextI = v.next; nextIid = id; } });
      const t = Math.min(nextT, nextI);
      if (t > end) break;
      now = Math.max(now, t);
      if (nextT <= nextI) { const job = timeouts.shift(); try { job.fn(); } catch (e) { errors.push('timeout: ' + e.message); } } else {
        const iv = intervals.get(nextIid); iv.next += iv.ms;
        try { iv.fn(); } catch (e) { errors.push('interval: ' + e.message); }
      }
    }
    now = end;
  }

  const errors = [];
  const windowListeners = {};
  const sockets = [];
  class FakeWebSocket {
    constructor(url) { this.url = url; this.readyState = 1; this.sent = []; sockets.push(this); }
    send(d) { this.sent.push(d); }
    close() { this.readyState = 3; }
  }
  FakeWebSocket.OPEN = 1; FakeWebSocket.CONNECTING = 0; FakeWebSocket.CLOSING = 2; FakeWebSocket.CLOSED = 3;

  const FixedDate = class extends Date {
    constructor(...a) { if (a.length) super(...a); else super(2026, 9, 30, 12, 0, 0); }
    static now() { return new Date(2026, 9, 30, 12, 0, 0).getTime(); }
  };

  const chain = new Proxy(function () {}, { get: (t, p) => (p === 'then' ? undefined : chain), apply: () => chain });
  const store = () => { const m = new Map(); return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) }; };
  const noopObserver = class { observe() {} disconnect() {} unobserve() {} takeRecords() { return []; } };

  const document = {
    documentElement: htmlEl, body, head: htmlEl.querySelector('head') || new El('head'), readyState: 'complete',
    fonts: { ready: Promise.resolve() },
    _listeners: {},
    getElementById: (id) => htmlEl._all([]).find((e) => e.id === id) || null,
    querySelector: (s) => htmlEl.querySelector(s),
    querySelectorAll: (s) => htmlEl.querySelectorAll(s),
    getElementsByClassName: (c) => htmlEl.getElementsByClassName(c),
    getElementsByTagName: (t) => htmlEl.getElementsByTagName(t),
    createElement: (t) => new El(t),
    createElementNS: (ns, t) => new El(t),
    createTextNode: (t) => ({ nodeType: 3, text: String(t), parentNode: null, get textContent() { return this.text; } }),
    createDocumentFragment: () => { const f = new El('#fragment'); f.nodeType = 11; return f; },
    addEventListener(t, fn) { (document._listeners[t] = document._listeners[t] || []).push(fn); },
    removeEventListener() {},
  };

  const sandbox = {
    console: { log() {}, info() {}, debug() {}, warn() {}, error: (...a) => errors.push('console.error: ' + a.map(String).join(' ')) },
    document, WebSocket: FakeWebSocket, Date: FixedDate,
    setTimeout: setTimeoutF, clearTimeout: clearTimeoutF, setInterval: setIntervalF, clearInterval: clearTimeoutF,
    requestAnimationFrame: (fn) => setTimeoutF(fn, 16), cancelAnimationFrame: clearTimeoutF,
    performance: { now: () => now }, localStorage: store(), sessionStorage: store(),
    location: { hostname: 'localhost', port: '8080', search: '', href: 'http://localhost:8080/overlays/' + overlayName + '/overlay.html', reload() {} },
    history: { replaceState() {} }, navigator: { userAgent: 'node' },
    getComputedStyle: () => ({ getPropertyValue: () => '', animationName: 'none', display: 'block' }),
    matchMedia: () => ({ matches: false, addEventListener() {}, addListener() {} }),
    fetch: () => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}), text: () => Promise.resolve('') }),
    gsap: chain, TweenMax: chain, TimelineMax: chain, Power1: chain, Power2: chain, Linear: chain,
    MutationObserver: noopObserver, ResizeObserver: noopObserver, IntersectionObserver: noopObserver,
    Image: class { constructor() { this.src = ''; } }, Audio: class { play() { return Promise.resolve(); } pause() {} },
    CustomEvent: class { constructor(t, o) { this.type = t; this.detail = o && o.detail; } }, Event: class { constructor(t) { this.type = t; } },
    URL, URLSearchParams, innerWidth: 1920, innerHeight: 1080, devicePixelRatio: 1,
    addEventListener(t, fn) { (windowListeners[t] = windowListeners[t] || []).push(fn); }, removeEventListener() {}, dispatchEvent() { return true; },
    io: () => ({ on() {}, emit() {}, connected: true }),
  };
  sandbox.window = sandbox; sandbox.self = sandbox; sandbox.globalThis = sandbox; sandbox.parent = sandbox; sandbox.top = sandbox;
  Object.assign(sandbox, opts.globals || {});
  vm.createContext(sandbox);

  // skrypty w kolejności z overlay.html
  const scripts = htmlEl._all([]).filter((e) => e.tagName === 'SCRIPT');
  const loaded = [];
  scripts.forEach((s) => {
    const src = s.getAttribute('src');
    let code; let name;
    if (src) {
      if (/^https?:/.test(src)) return;                                // biblioteki z CDN (gsap) zastępuje atrapa
      name = src;
      const file = path.join(OVERLAYS_DIR, src.replace(/^\/overlays\//, ''));
      if (!fs.existsSync(file)) return;
      code = fs.readFileSync(file, 'utf8');
    } else {
      name = 'inline'; code = s.childNodes.map((n) => n.text).join('');
    }
    try { vm.runInContext(code, sandbox, { filename: name }); loaded.push(name); } catch (e) { errors.push(`ładowanie ${name}: ${e.message}`); }
  });
  (document._listeners.DOMContentLoaded || []).forEach((fn) => { try { fn(); } catch (e) { errors.push('DOMContentLoaded: ' + e.message); } });
  (document._listeners.load || []).forEach((fn) => { try { fn(); } catch (e) { errors.push('load: ' + e.message); } });
  ['DOMContentLoaded', 'load'].forEach((t) => (windowListeners[t] || []).forEach((fn) => { try { fn(); } catch (e) { errors.push('window ' + t + ': ' + e.message); } }));

  const ws = sockets[0];
  function send(type, payload) {
    const msg = { type, payload };
    try { ws.onmessage({ data: JSON.stringify(msg) }); } catch (e) { errors.push(`komunikat ${type}: ${e.message}`); }
  }
  return { sandbox, log, errors, send, advance, document, body, loaded, ws, evalIn: (code) => vm.runInContext(code, sandbox), visibleText: () => body._text().replace(/\s+/g, ' ').trim() };
}

module.exports = { loadOverlayPage, matchesSelector, OVERLAYS_DIR };
