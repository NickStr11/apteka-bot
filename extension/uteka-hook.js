// Ютека, MAIN world:
// 1) читает ответы map.Cluster, которые сайт сам получает при открытии карты аптек;
// 2) по просьбе uteka.js запрашивает цены Фарматека для карточки товара через
//    собственный API-клиент сайта (useNuxtApp().$api.map.cluster) — сайт сам подписывает
//    запрос и сам показывает капчу, если она нужна.
// Данные передаются в uteka.js через postMessage.
(() => {
    const WATCH = /[?&]method=map\.Cluster\b/;
    const SOURCE = 'apteka-helper-uteka';
    const autoProducts = new Set(); // ответы по этим товарам перехват не пересылает: их отдаёт fetchPrices
    const inFlight = new Set();

    function post(msg) {
        window.postMessage(Object.assign({ source: SOURCE }, msg), location.origin);
    }

    function isOwnAutoRequest(request) {
        try {
            const cart = request.params.data.cart;
            return cart.length === 1 && autoProducts.has(Number(cart[0].productId));
        } catch (e) { return false; }
    }

    function forward(text, body) {
        try {
            const json = JSON.parse(text);
            if (!json || !json.result) return;
            let request = null;
            try { request = body ? JSON.parse(body) : null; } catch (e) { /* body не JSON */ }
            if (request && isOwnAutoRequest(request)) return; // его отдаёт fetchPrices
            post({ type: 'cluster', result: json.result, request });
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

    // ---------- автозапрос для карточки товара ----------

    function siteApi() {
        try {
            const app = window.useNuxtApp && window.useNuxtApp();
            return app && app.$api && app.$api.map && typeof app.$api.map.cluster === 'function' ? app.$api : null;
        } catch (e) { return null; }
    }

    async function waitApi(timeoutMs) {
        const until = Date.now() + timeoutMs;
        while (Date.now() < until) {
            const api = siteApi();
            if (api) return api;
            await new Promise(r => setTimeout(r, 300));
        }
        return null;
    }

    async function fetchPrices(productId, cityId, view) {
        const reply = extra => post(Object.assign({ type: 'fetch-result', productId }, extra));
        if (!productId || inFlight.has(productId)) return;
        inFlight.add(productId);
        autoProducts.add(productId);
        try {
            const api = await waitApi(15000);
            if (!api) { reply({ error: 'api-not-ready' }); return; }
            const params = {
                data: { cart: [{ count: 1, productId }], multiPickup: true, cityId, withPartial: true, deliveryType: 11 },
                view,
                filters: { inViewOnly: true, pickupOnly: false, fullCartOnly: false, pickupTomorrowOnly: false, favoritesOnly: false },
            };
            const result = await api.map.cluster(params);
            if (!result) { reply({ error: 'empty' }); return; }
            post({ type: 'cluster', result, request: { params }, auto: true });
            reply({ ok: true });
        } catch (e) {
            reply({ error: String((e && e.message) || e) });
        } finally {
            inFlight.delete(productId);
            // перехват fetch дочитывает тот же ответ асинхронно — снимаем метку чуть позже
            setTimeout(() => autoProducts.delete(productId), 3000);
        }
    }

    window.addEventListener('message', ev => {
        const d = ev.data;
        if (ev.source !== window || !d || d.source !== SOURCE || d.type !== 'fetch-prices') return;
        fetchPrices(Number(d.productId), Number(d.cityId), d.view);
    });
})();
