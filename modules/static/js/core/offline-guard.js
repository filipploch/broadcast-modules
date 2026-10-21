/* offline-guard.js — panel nie wysyła akcji bez połączenia z modułem (E2e, decyzja właściciela 2026-10-09).
 *
 * Powód: klient socket.io przechowuje zdarzenia wysłane w czasie rozłączenia i wysyła je po ponownym połączeniu, więc kliknięcie
 * z czasu restartu modułu mogłoby wykonać się po jego powrocie (np. START zegara z karty sprzed restartu).
 *
 * Zasady:
 *  - akcja (każde zdarzenie, które nie jest zapytaniem o stan) przy braku połączenia NIE jest wysyłana ani przechowywana;
 *    zamiast tego pasek "MODUŁ: brak połączenia" (stałe miejsce na pasek: U1/U2 z punktu 16 koncepcji, E2f);
 *  - zapytania o stan (get_*, request_*, search_*...) przechodzą normalnie (mogą być przechowane: to odczyty);
 *  - po ponownym połączeniu (po wcześniejszym rozłączeniu) panel pobiera stan od nowa przez przeładowanie strony; nic z przechowanych
 *    akcji nie jest odtwarzane. WYJĄTEK: gdy jest otwarte okno z formularzem (opcje meczu, edycja zdarzenia, składy) albo operator
 *    właśnie pisze w polu, strona NIE jest przeładowywana (przepadłyby wpisane dane): przeładowanie czeka do zamknięcia okna,
 *    a pasek zmienia się na informację;
 *  - dotyczy wszystkich ramek panelu: skrypt opakowuje io(), więc każde połączenie socket.io na stronie jest chronione.
 * Ładować zaraz po socket.io.min.js, przed skryptami strony.
 */
(function (global) {
    'use strict';

    var BAR_ID = 'module-offline-bar';
    var BAR_TEXT = 'MODUŁ: brak połączenia';
    var BAR_TEXT_DEFERRED = 'Połączenie z modułem wróciło. Strona odświeży się po zamknięciu okna.';
    var BUSY_POLL_MS = 500;

    // Okna z formularzami (wspólne dla stron panelu): widoczny element pasujący do jednego z selektorów albo pole w trakcie edycji.
    var MODAL_SELECTORS = ['.modal-content:not(.invisible)', '[id$="modal-overlay"]', '[id$="-modal"]', 'dialog[open]', '[role="dialog"]'];
    var FIELD_TAGS = { INPUT: true, TEXTAREA: true, SELECT: true };
    var NON_TEXT_INPUTS = { button: true, submit: true, checkbox: true, radio: true, range: true, reset: true, image: true };

    // Zapytania o stan. Wyjątki: nazwa wygląda na zapytanie, ale to akcja.
    var READ_ONLY = /^(get_|request_|search_|list_|fetch_)|_request_all_/;
    var ACTIONS_LOOKING_LIKE_READS = { request_camera_replay: true };

    function isReadOnly(eventName) {
        var name = String(eventName);
        if (ACTIONS_LOOKING_LIKE_READS[name]) return false;
        return READ_ONLY.test(name);
    }

    function isShown(el, doc) {
        if (!el) return false;
        var view = doc && doc.defaultView;
        if (view && view.getComputedStyle) {
            var cs = view.getComputedStyle(el);
            return cs.display !== 'none' && cs.visibility !== 'hidden';
        }
        return !(el.style && el.style.display === 'none') && !el.hidden;
    }

    /** Czy jest otwarte okno z formularzem albo operator pisze w polu (wtedy nie wolno przeładować strony). */
    function isBusy(doc) {
        if (!doc) return false;
        for (var i = 0; i < MODAL_SELECTORS.length; i++) {
            var found = doc.querySelectorAll ? doc.querySelectorAll(MODAL_SELECTORS[i]) : [];
            for (var j = 0; j < found.length; j++) {
                if (isShown(found[j], doc)) return true;
            }
        }
        var active = doc.activeElement;
        if (active && FIELD_TAGS[active.tagName]) {
            var type = String(active.type || '').toLowerCase();
            if (!NON_TEXT_INPUTS[type]) return true;
        }
        return false;
    }

    function showBar(doc, text) {
        if (!doc || !doc.body) return;
        var bar = doc.getElementById(BAR_ID);
        if (!bar) {
            bar = doc.createElement('div');
            bar.id = BAR_ID;
            bar.setAttribute('role', 'alert');
            bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:100000;padding:6px 12px;text-align:center;' +
                'font:600 14px sans-serif;color:#fff;background:#b02a37;';
            doc.body.appendChild(bar);
        }
        bar.textContent = text || BAR_TEXT;
        bar.style.background = text === BAR_TEXT_DEFERRED ? '#0d6efd' : '#b02a37';
        bar.style.display = 'block';
    }

    function hideBar(doc) {
        if (!doc) return;
        var bar = doc.getElementById(BAR_ID);
        if (bar) bar.style.display = 'none';
    }

    /**
     * Zabezpiecza jedno połączenie socket.io. opts (do testów i stron): document, reload, isBusy, setInterval, clearInterval.
     */
    function guardSocket(socket, opts) {
        opts = opts || {};
        if (!socket || socket.__offlineGuarded) return socket;
        socket.__offlineGuarded = true;
        var doc = opts.document || global.document;
        var reload = opts.reload || function () { global.location.reload(); };
        var busy = opts.isBusy || function () { return isBusy(doc); };
        var setTimer = opts.setInterval || function (fn, ms) { return global.setInterval(fn, ms); };
        var clearTimer = opts.clearInterval || function (h) { global.clearInterval(h); };
        var wasDown = false;
        var pendingReload = null;           // uchwyt sondowania, gdy przeładowanie czeka na zamknięcie okna

        function reloadWhenFree() {
            if (!busy()) {
                if (pendingReload !== null) {              // oczekujące sondowanie nie może przeładować drugi raz
                    clearTimer(pendingReload);
                    pendingReload = null;
                }
                reload();
                return;
            }
            showBar(doc, BAR_TEXT_DEFERRED);
            if (pendingReload !== null) return;
            pendingReload = setTimer(function () {
                if (!socket.connected) return;            // połączenie znów padło: czekamy dalej (pasek błędu pokaże rozłączenie)
                if (busy()) return;
                clearTimer(pendingReload);
                pendingReload = null;
                hideBar(doc);
                reload();
            }, BUSY_POLL_MS);
        }
        var originalEmit = socket.emit;

        socket.emit = function (eventName) {
            if (socket.connected || isReadOnly(eventName)) {
                return originalEmit.apply(socket, arguments);
            }
            showBar(doc);          // akcja bez połączenia: nie wysyłamy i nie przechowujemy
            return socket;
        };

        socket.on('disconnect', function () {
            wasDown = true;
            showBar(doc);                 // także gdy przeładowanie czeka na zamknięcie okna: znów brak połączenia
        });
        socket.on('connect_error', function () {
            showBar(doc);
        });
        socket.on('connect', function () {
            if (wasDown) {
                wasDown = false;
                hideBar(doc);
                reloadWhenFree();  // stan od nowa; nic z przechowanych akcji nie jest odtwarzane
            } else if (pendingReload === null) {
                hideBar(doc);
            }
        });
        return socket;
    }

    var exported = { guardSocket: guardSocket, isReadOnly: isReadOnly, isBusy: isBusy, BAR_ID: BAR_ID, BAR_TEXT: BAR_TEXT,
                     BAR_TEXT_DEFERRED: BAR_TEXT_DEFERRED };
    global.guardSocket = guardSocket;
    global.OfflineGuard = exported;

    // Opakowanie io(): każde połączenie utworzone przez strony jest chronione automatycznie.
    var originalIo = global.io;
    if (typeof originalIo === 'function' && !originalIo.__offlineGuarded) {
        var wrapped = function () {
            return guardSocket(originalIo.apply(this, arguments));
        };
        for (var key in originalIo) {
            if (Object.prototype.hasOwnProperty.call(originalIo, key)) wrapped[key] = originalIo[key];
        }
        wrapped.__offlineGuarded = true;
        global.io = wrapped;
    }

    if (typeof module !== 'undefined' && module.exports) module.exports = exported;
})(typeof window !== 'undefined' ? window : globalThis);
