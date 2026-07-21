// ---------------------------------------------------------------------------
// Scraper cascade — wspólny "split button" (Scrapuj X + rozwijana lista
// scraperów) dla drużyn/meczów/zawodników. Wybrane scrapery uruchamiane są
// sekwencyjnie (kaskadowo) — kolejny startuje dopiero gdy poprzedni skończy,
// błąd jednego nie przerywa reszty kolejki.
// ---------------------------------------------------------------------------
const ScraperCascade = (function () {
    const registry = {};

    function register(key, scrapers, onComplete) {
        registry[key] = { scrapers: scrapers, onComplete: onComplete };
    }

    function toggleMenu(key) {
        const menu = document.getElementById('cascade-menu-' + key);
        if (!menu) return;
        menu.style.display = (menu.style.display === 'none' || !menu.style.display) ? 'block' : 'none';
    }

    function getSelectedIds(key) {
        const checked = document.querySelectorAll('#cascade-menu-' + key + ' input[type=checkbox]:checked');
        return Array.prototype.map.call(checked, function (cb) { return cb.value; });
    }

    function setStatus(key, text) {
        const el = document.getElementById('cascade-status-' + key);
        if (!el) return;
        if (text) {
            el.textContent = text;
            el.style.display = 'block';
        } else {
            el.style.display = 'none';
        }
    }

    function run(key) {
        const entry = registry[key];
        if (!entry) return;

        const selectedIds = getSelectedIds(key);
        const scrapers = entry.scrapers.filter(function (s) { return selectedIds.indexOf(s.id) !== -1; });
        if (!scrapers.length) {
            alert('Wybierz przynajmniej jeden scraper');
            return;
        }

        const menu = document.getElementById('cascade-menu-' + key);
        if (menu) menu.style.display = 'none';

        const runBtn = document.getElementById('cascade-run-' + key);
        if (runBtn) runBtn.disabled = true;

        const results = [];
        let chain = Promise.resolve();
        scrapers.forEach(function (scraper) {
            chain = chain.then(function () {
                setStatus(key, '⏳ ' + scraper.label + '...');
                return scraper.run()
                    .then(function () {
                        results.push({ label: scraper.label, ok: true });
                    })
                    .catch(function (e) {
                        results.push({ label: scraper.label, ok: false, message: e.message || 'nieznany błąd' });
                    });
            });
        });

        chain.then(function () {
            if (runBtn) runBtn.disabled = false;
            setStatus(key, null);

            const failed = results.filter(function (r) { return !r.ok; });
            if (failed.length) {
                alert('Błędy scrapowania:\n' + failed.map(function (r) {
                    return '• ' + r.label + ': ' + r.message;
                }).join('\n'));
            }

            if (entry.onComplete) entry.onComplete(results);
        });
    }

    // ── Helpery do budowania scraper.run() ──────────────────────────────────

    function fetchJson(url) {
        return fetch(url, { headers: { 'X-Scraper-Cascade': '1' } })
            .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, data: d }; }); })
            .then(function (res) {
                if (!res.ok) throw new Error(res.data.error || 'błąd');
                return res.data;
            });
    }

    function runAsyncJobAndPoll(startUrl, statusUrl, pollIntervalMs) {
        pollIntervalMs = pollIntervalMs || 1500;
        return fetch(startUrl, { headers: { 'X-Scraper-Cascade': '1' } })
            .then(function (r) { return r.json().then(function (d) { return { status: r.status, data: d }; }); })
            .then(function (res) {
                if (res.status !== 202) throw new Error(res.data.error || 'błąd');
                return new Promise(function (resolve, reject) {
                    (function poll() {
                        fetch(statusUrl)
                            .then(function (r) { return r.json(); })
                            .then(function (data) {
                                if (data.status === 'in_progress') {
                                    setTimeout(poll, pollIntervalMs);
                                } else if (data.status === 'error') {
                                    reject(new Error(data.error || 'błąd scrapowania'));
                                } else {
                                    resolve(data);
                                }
                            })
                            .catch(function () { setTimeout(poll, pollIntervalMs); });
                    })();
                });
            });
    }

    return {
        register: register,
        toggleMenu: toggleMenu,
        run: run,
        fetchJson: fetchJson,
        runAsyncJobAndPoll: runAsyncJobAndPoll,
    };
})();

// Zamknij otwarte menu scraperów przy kliknięciu poza nim
document.addEventListener('click', function (e) {
    document.querySelectorAll('.cascade-menu').forEach(function (menu) {
        if (menu.style.display === 'none') return;
        const wrapper = menu.closest('.scraper-cascade');
        if (wrapper && !wrapper.contains(e.target)) menu.style.display = 'none';
    });
});
