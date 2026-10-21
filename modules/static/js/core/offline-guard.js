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
 *    akcji nie jest odtwarzane;
 *  - dotyczy wszystkich ramek panelu: skrypt opakowuje io(), więc każde połączenie socket.io na stronie jest chronione.
 * Ładować zaraz po socket.io.min.js, przed skryptami strony.
 */
(function (global) {
    'use strict';

    var BAR_ID = 'module-offline-bar';
    var BAR_TEXT = 'MODUŁ: brak połączenia';

    // Zapytania o stan. Wyjątki: nazwa wygląda na zapytanie, ale to akcja.
    var READ_ONLY = /^(get_|request_|search_|list_|fetch_)|_request_all_/;
    var ACTIONS_LOOKING_LIKE_READS = { request_camera_replay: true };

    function isReadOnly(eventName) {
        var name = String(eventName);
        if (ACTIONS_LOOKING_LIKE_READS[name]) return false;
        return READ_ONLY.test(name);
    }

    function showBar(doc) {
        if (!doc || !doc.body) return;
        var bar = doc.getElementById(BAR_ID);
        if (!bar) {
            bar = doc.createElement('div');
            bar.id = BAR_ID;
            bar.setAttribute('role', 'alert');
            bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:100000;padding:6px 12px;text-align:center;' +
                'font:600 14px sans-serif;color:#fff;background:#b02a37;';
            bar.textContent = BAR_TEXT;
            doc.body.appendChild(bar);
        }
        bar.style.display = 'block';
    }

    function hideBar(doc) {
        if (!doc) return;
        var bar = doc.getElementById(BAR_ID);
        if (bar) bar.style.display = 'none';
    }

    /**
     * Zabezpiecza jedno połączenie socket.io. opts (do testów): document, reload.
     */
    function guardSocket(socket, opts) {
        opts = opts || {};
        if (!socket || socket.__offlineGuarded) return socket;
        socket.__offlineGuarded = true;
        var doc = opts.document || global.document;
        var reload = opts.reload || function () { global.location.reload(); };
        var wasDown = false;
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
            showBar(doc);
        });
        socket.on('connect_error', function () {
            showBar(doc);
        });
        socket.on('connect', function () {
            hideBar(doc);
            if (wasDown) {
                wasDown = false;
                reload();          // stan od nowa; nic z przechowanych akcji nie jest odtwarzane
            }
        });
        return socket;
    }

    var exported = { guardSocket: guardSocket, isReadOnly: isReadOnly, BAR_ID: BAR_ID, BAR_TEXT: BAR_TEXT };
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
