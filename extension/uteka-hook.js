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

    // ---------- заказ с карточки: orders.Calculate → orders.Create ----------
    // Те же вызовы, что делает сайт на странице «Оформление заказа» (быстрый заказ одного
    // товара): покупатель — профиль аккаунта, корзина не трогается.
    // localStorage aptekaHelperDryRun=1 — тест: только Calculate, заказ не создаётся.

    function orderNumberOf(created) {
        if (created == null) return '';
        if (typeof created !== 'object') return String(created);
        for (const k of ['code', 'number', 'orderNumber', 'orderCode', 'id', 'orderId']) {
            if (created[k] != null && created[k] !== '') return String(created[k]);
        }
        if (created.order && typeof created.order === 'object') return orderNumberOf(created.order);
        return '';
    }

    async function placeOrder(d) {
        const reply = extra => post(Object.assign({ type: 'order-result', reqId: d.reqId }, extra));
        try {
            const api = await waitApi(10000);
            if (!api || !api.orders || typeof api.orders.create !== 'function') { reply({ error: 'сайт Ютеки ещё не загрузился' }); return; }
            const cart = [{ count: Number(d.count) || 1, productId: Number(d.productId) }];
            const pharmacyId = Number(d.pharmacyId);
            const pharmacyNetworkId = Number(d.networkId);
            const calc = await api.orders.calculate({ pharmacyId, cart, pharmacyNetworkId });
            if (!calc || !calc.isValid) {
                const why = ((calc && calc.items) || []).map(i => i && i.error).filter(Boolean).join('; ');
                reply({ error: 'Ютека не даёт оформить' + (why ? ': ' + why : ' (товара нет у поставщика)') });
                return;
            }
            if (Math.round(Number(calc.price)) !== Math.round(Number(d.expectedTotal))) {
                reply({ priceChanged: Number(calc.price) });
                return;
            }
            let dryRun = false;
            try { dryRun = localStorage.getItem('aptekaHelperDryRun') === '1'; } catch (e) { /* нет доступа */ }
            if (dryRun) { reply({ ok: true, dryRun: true, price: Number(calc.price) }); return; }
            const created = await api.orders.create({ source: 1, cart, pharmacyId, isPartial: false, cartId: null, pharmacyNetworkId });
            console.info('[apteka-helper] orders.Create', created);
            reply({ ok: true, price: Number(calc.price), orderNumber: orderNumberOf(created) });
        } catch (e) {
            reply({ error: String((e && (e.message || e.data && e.data.message)) || e) });
        }
    }

    window.addEventListener('message', ev => {
        const d = ev.data;
        if (ev.source !== window || !d || d.source !== SOURCE) return;
        if (d.type === 'fetch-prices') fetchPrices(Number(d.productId), Number(d.cityId), d.view);
        else if (d.type === 'place-order') placeOrder(d);
    });
})();
