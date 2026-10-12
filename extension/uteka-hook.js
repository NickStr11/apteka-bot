// Ютека: читает ответы map.Cluster, которые сайт сам получает при открытии карты аптек.
// Своих запросов не делает. Работает в MAIN world, данные передаёт в uteka.js через postMessage.
(() => {
    const WATCH = /[?&]method=map\.Cluster\b/;
    const SOURCE = 'apteka-helper-uteka';

    function forward(text, body) {
        try {
            const json = JSON.parse(text);
            if (!json || !json.result) return;
            let request = null;
            try { request = body ? JSON.parse(body) : null; } catch (e) { /* body не JSON */ }
            window.postMessage({ source: SOURCE, type: 'cluster', result: json.result, request }, location.origin);
        } catch (e) { /* не JSON — пропускаем */ }
    }

    const origFetch = window.fetch;
    window.fetch = function (input, init) {
        const promise = origFetch.apply(this, arguments);
        try {
            const url = typeof input === 'string' ? input : (input && input.url) || '';
            if (WATCH.test(url)) {
                const body = init && typeof init.body === 'string' ? init.body : null;
                promise.then(r => r.clone().text()).then(t => forward(t, body)).catch(() => {});
            }
        } catch (e) { /* не мешаем сайту */ }
        return promise;
    };

    const origOpen = XMLHttpRequest.prototype.open;
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
        this.__aptekaUrl = String(url || '');
        return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function (body) {
        if (WATCH.test(this.__aptekaUrl || '')) {
            this.addEventListener('load', () => {
                try { forward(String(this.responseText), typeof body === 'string' ? body : null); } catch (e) { /* ignore */ }
            });
        }
        return origSend.apply(this, arguments);
    };
})();
