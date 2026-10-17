// Apteka.ru, MAIN world: заказ с карточки товара в один клик.
// Сайт — Vue 3 + Vuex; запросы к api.apteka.ru он подписывает заголовками сессии,
// поэтому всё делаем через его собственный axios-клиент (app._context.provides.client)
// и действия хранилища — как сам сайт при «Купить» → «Оформить заказ».
// Цепочка: аптека Фарматек → PUT /Cart (наш товар) → витаминки → PUT /Order.
// PUT /Order оформляет ВСЮ неотложенную корзину, поэтому чужие товары в корзине
// не трогаем и не оформляем — просим разобрать корзину.
// localStorage aptekaHelperDryRun=1 — тест: всё, кроме PUT /Order, затем корзина очищается.
(() => {
    const SOURCE = 'apteka-helper-apteka';
    const FARMATEK_ID = '5e3281c8f5a9ae0001418615'; // ПОЛТАВСКАЯ,ООО *ФАРМАТЕК*, Ленина 161
    const MAX_COUNT = 20;
    let busy = false;

    function post(msg) {
        window.postMessage(Object.assign({ source: SOURCE }, msg), location.origin);
    }

    function vueApp() {
        const root = document.getElementById('app-container');
        if (root && root.__vue_app__) return root.__vue_app__;
        for (const el of document.querySelectorAll('body > div, body > div > div')) {
            if (el.__vue_app__) return el.__vue_app__;
        }
        return null;
    }

    function site() {
        try {
            const app = vueApp();
            if (!app) return null;
            const store = app.config && app.config.globalProperties && app.config.globalProperties.$store;
            const provides = (app._context && app._context.provides) || {};
            const client = provides.client || (store && store.getters && store.getters.$client);
            if (!store || !client || typeof client.put !== 'function' || typeof client.get !== 'function') return null;
            return { store, client };
        } catch (e) { return null; }
    }

    async function waitFor(fn, timeoutMs) {
        const until = Date.now() + timeoutMs;
        for (;;) {
            const v = fn();
            if (v) return v;
            if (Date.now() >= until) return null;
            await new Promise(r => setTimeout(r, 250));
        }
    }

    const sameId = (a, b) => String(a || '').toLowerCase() === String(b || '').toLowerCase();

    function itemIdFromPath(path) {
        const m = String(path || '').match(/^\/product\/[^/]*?-([0-9a-f]{24})\/?$/i);
        return m ? m[1].toLowerCase() : null;
    }

    const values = o => (o && typeof o === 'object' ? Object.values(o) : []);

    // Цена, type/typeKey и наличие: с 10.2026 сайт держит их в product.groupItems[].itemInfos[],
    // описание (полное имя, рецептурность) — в product.iteminfo[id]; раньше всё было в product.products[id]
    function productOffer(p, id) {
        const old = (p.products || {})[p.selected];
        if (old && sameId(old.id, id)) return old;
        for (const g of values(p.groupItems)) {
            const hit = values(g && g.itemInfos).find(i => i && sameId(i.id, id) && 'price' in i);
            if (hit) return hit;
        }
        return null;
    }

    // карточка грузится асинхронно (SPA): ждём, пока в хранилище окажется именно этот товар
    function productInfo(s) {
        const id = itemIdFromPath(location.pathname);
        const p = (s.store.state && s.store.state.product) || {};
        if (!id || !sameId(p.selected, id)) return null;
        const pr = productOffer(p, id);
        if (!pr) return null;
        const desc = values(p.iteminfo).find(i => i && sameId(i.id, id)) || {};
        return {
            itemId: String(pr.id),
            name: String(desc.name || pr.name || ''),
            price: Number(pr.price) || 0,
            type: pr.type || 'Base',
            typeKey: pr.typeKey == null ? null : pr.typeKey,
            outOfStock: !!pr.outOfStock,
            prescription: !!(pr.prescriptionDrug || desc.prescriptionDrug),
        };
    }

    function loggedIn(s) {
        const u = s.store.state && s.store.state.user;
        return !!(u && u.login);
    }

    function errText(e) {
        const resp = e && e.response;
        const d = resp && resp.data;
        if (typeof d === 'string' && d.trim()) return d.trim().slice(0, 300);
        if (d && typeof d === 'object') {
            const m = d.message || d.Message || d.detail || d.title || d.type;
            if (m) return String(m).slice(0, 300);
        }
        if (resp && resp.status) return 'HTTP ' + resp.status;
        return String((e && e.message) || e || 'неизвестная ошибка').slice(0, 300);
    }

    const activeItems = cart => ((cart && cart.items) || []).filter(i => i && !i.deferred);
    const itemName = i => String(i.itemName || i.name || 'товар');

    async function getCart(s) {
        const r = await s.client.get('/Cart');
        return (r && r.data) || {};
    }

    async function setAmount(s, info, amount) {
        const r = await s.client.put('/Cart', {
            items: [{ itemId: info.itemId, amount, type: info.type, typeKey: info.typeKey, deferred: false }],
        });
        return (r && r.data) || null;
    }

    async function setVitamins(s, vitaminsCount) {
        const r = await s.client.put('/Cart/UseVitamins', { vitaminsCount });
        return (r && r.data) || null;
    }

    // Как в корзине сайта: проценты от minDiscount до (maxDiscount − currentDiscount + уже списанные),
    // но не больше, чем хватает витаминок (vitBalance / vitaminsPerPercent)
    function vitaminsLimit(cart) {
        const v = cart && cart.vitaminsInfo;
        const per = v ? Number(v.vitaminsPerPercent) : 0;
        if (!v || !(per > 0)) return { min: 0, max: 0, per: 0, balance: v ? Number(v.vitBalance) || 0 : null };
        const usedPct = (Number(v.vitaminsUsed) || 0) / per;
        let max = (Number(v.maxDiscount) || 0) - (Number(v.currentDiscount) || 0) + usedPct;
        max = Math.min(max, Math.floor((Number(v.vitBalance) || 0) / per));
        return {
            min: Math.max(1, Number(v.minDiscount) || 1),
            max: Math.max(0, Math.floor(max)),
            per,
            balance: Number(v.vitBalance) || 0,
        };
    }

    function refreshSiteCart(s) {
        try { const p = s.store.dispatch('basket/load'); if (p && p.catch) p.catch(() => {}); } catch (e) { /* не мешаем */ }
    }

    // ---------- данные для панели ----------

    async function sendProductInfo(d) {
        const reply = extra => post(Object.assign({ type: 'product-info', reqId: d.reqId }, extra));
        const s = await waitFor(site, 15000);
        if (!s) { reply({ error: 'сайт Apteka.ru ещё не загрузился' }); return; }
        const info = await waitFor(() => productInfo(s), 15000);
        if (!info) { reply({ error: 'не нашёл данные товара на странице' }); return; }
        const extra = { ok: true, info, loggedIn: loggedIn(s) };
        if (extra.loggedIn) {
            try {
                const cart = await getCart(s);
                extra.otherItems = activeItems(cart).filter(i => !sameId(i.itemId, info.itemId)).map(itemName);
                const lim = vitaminsLimit(cart);
                if (lim.balance != null) extra.vitBalance = lim.balance;
            } catch (e) { /* корзина не прочиталась — панель обойдётся без неё */ }
        }
        reply(extra);
    }

    // ---------- заказ ----------

    async function placeOrder(d) {
        const reply = extra => post(Object.assign({ type: 'order-result', reqId: d.reqId }, extra));
        if (busy) { reply({ error: 'предыдущий заказ ещё оформляется' }); return; }
        busy = true;
        let s = null, info = null, prevAmount = 0, cartTouched = false, vitApplied = false, orderSent = false;

        async function cleanup() {
            if (!s || !info) return;
            try { if (vitApplied) await setVitamins(s, 0); } catch (e) { /* дальше всё равно убираем товар */ }
            try { if (cartTouched) await setAmount(s, info, prevAmount); } catch (e) { /* сообщим общей ошибкой */ }
            refreshSiteCart(s);
        }

        try {
            s = await waitFor(site, 10000);
            if (!s) { reply({ error: 'сайт Apteka.ru ещё не загрузился' }); return; }
            if (!loggedIn(s)) { reply({ error: 'войди на apteka.ru (вход по SMS)' }); return; }
            info = productInfo(s);
            if (!info || !sameId(info.itemId, d.itemId)) { info = null; reply({ error: 'карточка сменилась — обнови страницу' }); return; }
            const count = Math.max(1, Math.min(MAX_COUNT, Math.floor(Number(d.count) || 1)));

            const before = await getCart(s);
            const others = activeItems(before).filter(i => !sameId(i.itemId, info.itemId));
            if (others.length) {
                reply({ error: 'в корзине уже есть: ' + others.map(itemName).join('; ') + '. Оформи или отложи их — заказ оформляет всю корзину.' });
                return;
            }
            const mineBefore = activeItems(before).find(i => sameId(i.itemId, info.itemId));
            prevAmount = mineBefore ? Number(mineBefore.amount) || 0 : 0;

            const shop = await s.store.dispatch('autodest/submitAutoDest', FARMATEK_ID);
            if (!shop) { reply({ error: 'не удалось выбрать аптеку Фарматек для самовывоза' }); return; }

            cartTouched = true;
            let cart = await setAmount(s, info, count);
            const mine = activeItems(cart).find(i => sameId(i.itemId, info.itemId));
            if (!mine || Number(mine.amount) !== count) {
                await cleanup();
                reply({ error: 'Apteka.ru не положила товар в корзину (нет в Фарматеке или ограничение количества)' });
                return;
            }
            const unit = Number(mine.price) || Math.round((Number(cart.totalSum) || 0) / count);
            if (Math.round(unit) !== Math.round(Number(d.expectedUnit) || 0)) {
                await cleanup();
                reply({ priceChanged: unit });
                return;
            }
            const totalBefore = Number(cart.totalSum) || unit * count;

            const lim = vitaminsLimit(cart);
            const wanted = d.vitamins === 'max' ? lim.max : Math.max(0, Math.floor(Number(d.vitamins) || 0));
            let pct = Math.min(wanted, lim.max);
            if (pct > 0 && pct < lim.min) pct = lim.min <= lim.max ? lim.min : 0;
            if (pct > 0) {
                vitApplied = true;
                const withVit = await setVitamins(s, pct * lim.per);
                if (!withVit) throw new Error('Apteka.ru не применила витаминки');
                cart = withVit;
            }
            const totalAfter = Number(cart.totalSum) || totalBefore;
            const vitInfo = { vitaminsPercent: pct, vitaminsWanted: d.vitamins, vitaminsMax: lim.max };

            let dryRun = false;
            try { dryRun = localStorage.getItem('aptekaHelperDryRun') === '1'; } catch (e) { /* нет доступа */ }
            if (dryRun) {
                await cleanup();
                reply(Object.assign({ ok: true, dryRun: true, unit, totalBefore, totalAfter }, vitInfo));
                return;
            }

            orderSent = true;
            const r = await s.client.put('/Order', { customName: null, device: 'DesktopSite' });
            const created = r && r.data && r.data.order;
            if (!created) {
                await cleanup();
                reply({ error: 'Apteka.ru не вернула заказ', orderUnknown: true });
                return;
            }
            // заказ забрал корзину — убирать нечего
            cartTouched = false;
            vitApplied = false;
            refreshSiteCart(s);
            console.info('[apteka-helper] PUT /Order', created);
            reply(Object.assign({
                ok: true,
                orderNum: String(created.orderNum || ''),
                orderId: String(created.id || ''),
                total: Number(created.totalSum) || totalAfter,
                totalBefore, unit,
                address: String(created.autoDestAddr || ''),
            }, vitInfo));
        } catch (e) {
            await cleanup();
            reply({ error: errText(e), orderUnknown: orderSent });
        } finally {
            busy = false;
        }
    }

    window.addEventListener('message', ev => {
        const d = ev.data;
        if (ev.source !== window || !d || d.source !== SOURCE) return;
        if (d.type === 'get-product') sendProductInfo(d);
        else if (d.type === 'place-order') placeOrder(d);
    });

    // для офлайн-теста (tests/extension_apteka_hook.test.js)
    if (window.__aptekaHelperTest) window.__aptekaHelperTest.hook = { placeOrder, sendProductInfo, vitaminsLimit, itemIdFromPath };
})();
