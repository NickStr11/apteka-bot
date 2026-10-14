// Офлайн-тест extension/apteka-hook.js: подставной Vue-app с хранилищем и клиентом сайта.
// Запуск: node tests/extension_apteka_hook.test.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');
// объекты из vm-контекста — сравниваем по JSON (другие прототипы)
const sameJson = (a, b) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b));

const SRC = fs.readFileSync(path.join(__dirname, '..', 'extension', 'apteka-hook.js'), 'utf8');
const ITEM = '630f536b260509b64b8d8e89';
const OTHER = '111111111111111111111111';
const FARMATEK = '5e3281c8f5a9ae0001418615';

function setup({ cart = [], price = 752, cartPrice, vitInfo, orderFails = false, dryRun = false, loggedIn = true, autodestOk = true } = {}) {
    const calls = [];
    let items = cart.map(i => Object.assign({}, i));
    let vitUsed = 0;
    const vit = vitInfo === undefined
        ? { vitBalance: 2862, vitaminsUsed: 0, vitaminsPerPercent: 100, minDiscount: 1, maxDiscount: 15, currentDiscount: 0 }
        : vitInfo;
    const unitInCart = cartPrice == null ? price : cartPrice;
    const cartData = () => {
        const active = items.filter(i => !i.deferred);
        const sum = active.reduce((a, i) => a + i.price * i.amount, 0);
        return {
            items: items.map(i => Object.assign({}, i)),
            totalSum: Math.round(sum * (1 - vitUsed / 100)),
            vitaminsInfo: vit && Object.assign({}, vit, { vitaminsUsed: vitUsed * vit.vitaminsPerPercent }),
        };
    };
    const client = {
        async get(url) { calls.push(['GET', url]); if (url === '/Cart') return { data: cartData() }; throw new Error('unexpected GET ' + url); },
        async put(url, body) {
            calls.push(['PUT', url, body]);
            if (url === '/Cart') {
                for (const it of body.items) {
                    items = items.filter(i => i.itemId !== it.itemId);
                    if (it.amount > 0) items.push({ itemId: it.itemId, amount: it.amount, price: unitInCart, itemName: 'Магне в6', deferred: false });
                }
                return { data: cartData() };
            }
            if (url === '/Cart/UseVitamins') { vitUsed = body.vitaminsCount / (vit ? vit.vitaminsPerPercent : 1); return { data: cartData() }; }
            if (url === '/Order') {
                if (orderFails) { const e = new Error('fail'); e.response = { status: 400, data: { message: 'Товар закончился' } }; throw e; }
                const d = cartData();
                items = [];
                return { data: { order: { id: 'o1', orderNum: 'MA-123', totalSum: d.totalSum, autoDestAddr: 'Ленина 161' } } };
            }
            throw new Error('unexpected PUT ' + url);
        },
    };
    const dispatched = [];
    const store = {
        state: {
            user: loggedIn ? { login: '+70000000000' } : { login: null },
            product: { selected: ITEM, products: { [ITEM]: { id: ITEM, name: 'Магне в6 60 шт.', price, type: 'Base', typeKey: null, outOfStock: false } } },
        },
        getters: {},
        async dispatch(name, arg) {
            dispatched.push([name, arg]);
            if (name === 'autodest/submitAutoDest') return autodestOk && arg === FARMATEK ? { id: 'city' } : null;
            return null;
        },
    };
    const app = { config: { globalProperties: { $store: store } }, _context: { provides: { client } } };
    const posted = [];
    const listeners = [];
    const win = {
        __aptekaHelperTest: {},
        postMessage(msg) { posted.push(msg); },
        addEventListener(type, fn) { if (type === 'message') listeners.push(fn); },
    };
    const ctx = {
        window: win,
        document: { getElementById: id => (id === 'app-container' ? { __vue_app__: app } : null), querySelectorAll: () => [] },
        location: { pathname: `/product/magne-v6-60-sht-${ITEM}/`, origin: 'https://apteka.ru' },
        localStorage: { getItem: k => (k === 'aptekaHelperDryRun' && dryRun ? '1' : null) },
        console: { info() {}, warn() {}, log() {} },
        setTimeout, Promise, Date, Math, Number, String, Object, Array, Error,
    };
    vm.createContext(ctx);
    vm.runInContext(SRC, ctx);
    const hook = win.__aptekaHelperTest.hook;
    const order = async (extra) => {
        await hook.placeOrder(Object.assign({ reqId: 'r', itemId: ITEM, count: 2, expectedUnit: price, vitamins: '0' }, extra));
        return posted.filter(m => m.type === 'order-result').pop();
    };
    const orderPut = () => calls.filter(c => c[0] === 'PUT' && c[1] === '/Order');
    const itemsNow = () => items;
    return { hook, order, calls, orderPut, itemsNow, dispatched, posted };
}

const tests = {
    async 'успешный заказ без витаминок'() {
        const t = setup();
        const r = await t.order();
        assert.strictEqual(r.ok, true);
        assert.strictEqual(r.orderNum, 'MA-123');
        assert.strictEqual(r.totalBefore, 1504);
        assert.strictEqual(r.total, 1504);
        assert.strictEqual(r.vitaminsPercent, 0);
        assert.strictEqual(t.orderPut().length, 1);
        sameJson(t.orderPut()[0][2], { customName: null, device: 'DesktopSite' });
        assert.ok(t.dispatched.some(([n, a]) => n === 'autodest/submitAutoDest' && a === FARMATEK));
        const cartPut = t.calls.find(c => c[1] === '/Cart' && c[0] === 'PUT');
        sameJson(cartPut[2].items[0], { itemId: ITEM, amount: 2, type: 'Base', typeKey: null, deferred: false });
    },
    async 'чужие товары в корзине — отказ, корзину не трогаем'() {
        const t = setup({ cart: [{ itemId: OTHER, amount: 1, price: 100, itemName: 'Чужой товар', deferred: false }] });
        const r = await t.order();
        assert.ok(r.error.includes('Чужой товар'));
        assert.strictEqual(t.calls.filter(c => c[0] === 'PUT').length, 0);
    },
    async 'отложенные товары не мешают'() {
        const t = setup({ cart: [{ itemId: OTHER, amount: 1, price: 100, itemName: 'Отложенный', deferred: true }] });
        const r = await t.order();
        assert.strictEqual(r.ok, true);
    },
    async 'цена изменилась — товар убран, заказ не создан'() {
        const t = setup({ cartPrice: 790 });
        const r = await t.order();
        assert.strictEqual(r.priceChanged, 790);
        assert.strictEqual(t.orderPut().length, 0);
        assert.strictEqual(t.itemsNow().length, 0);
    },
    async 'витаминки max ограничены корзиной'() {
        const t = setup({ vitInfo: { vitBalance: 2862, vitaminsUsed: 0, vitaminsPerPercent: 286, minDiscount: 1, maxDiscount: 15, currentDiscount: 0 } });
        const r = await t.order({ vitamins: 'max' });
        assert.strictEqual(r.vitaminsPercent, 10); // floor(2862 / 286)
        const vitPut = t.calls.find(c => c[1] === '/Cart/UseVitamins');
        sameJson(vitPut[2], { vitaminsCount: 2860 });
        assert.strictEqual(r.total, Math.round(1504 * 0.9));
    },
    async 'витаминки N% больше допустимого — урезаны'() {
        const t = setup({ vitInfo: { vitBalance: 5000, vitaminsUsed: 0, vitaminsPerPercent: 100, minDiscount: 1, maxDiscount: 8, currentDiscount: 3 } });
        const r = await t.order({ vitamins: '9' });
        assert.strictEqual(r.vitaminsPercent, 5);
    },
    async 'без vitaminsInfo — заказ без витаминок'() {
        const t = setup({ vitInfo: null });
        const r = await t.order({ vitamins: 'max' });
        assert.strictEqual(r.ok, true);
        assert.strictEqual(r.vitaminsPercent, 0);
        assert.ok(!t.calls.some(c => c[1] === '/Cart/UseVitamins'));
    },
    async 'тестовый режим — без PUT /Order, корзина и витаминки сброшены'() {
        const t = setup({ dryRun: true });
        const r = await t.order({ vitamins: '5' });
        assert.strictEqual(r.dryRun, true);
        assert.strictEqual(r.totalBefore, 1504);
        assert.strictEqual(r.totalAfter, Math.round(1504 * 0.95));
        assert.strictEqual(t.orderPut().length, 0);
        assert.strictEqual(t.itemsNow().length, 0);
        const vitPuts = t.calls.filter(c => c[1] === '/Cart/UseVitamins').map(c => c[2].vitaminsCount);
        assert.deepStrictEqual(vitPuts, [500, 0]);
    },
    async 'ошибка оформления — корзина очищена, текст ошибки'() {
        const t = setup({ orderFails: true });
        const r = await t.order();
        assert.ok(r.error.includes('Товар закончился'));
        assert.strictEqual(r.orderUnknown, true);
        assert.strictEqual(t.itemsNow().length, 0);
    },
    async 'не залогинен — отказ до корзины'() {
        const t = setup({ loggedIn: false });
        const r = await t.order();
        assert.ok(r.error.includes('войди'));
        assert.strictEqual(t.calls.length, 0);
    },
    async 'Фарматек не выбрался — заказа нет'() {
        const t = setup({ autodestOk: false });
        const r = await t.order();
        assert.ok(r.error.includes('Фарматек'));
        assert.strictEqual(t.orderPut().length, 0);
    },
    async 'данные карточки для панели'() {
        const t = setup({ cart: [{ itemId: OTHER, amount: 1, price: 100, itemName: 'Чужой', deferred: false }] });
        await t.hook.sendProductInfo({ reqId: 'p' });
        const r = t.posted.find(m => m.type === 'product-info');
        assert.strictEqual(r.ok, true);
        assert.strictEqual(r.info.price, 752);
        assert.deepStrictEqual(r.otherItems, ['Чужой']);
        assert.strictEqual(r.vitBalance, 2862);
    },
};

(async () => {
    let failed = 0;
    for (const [name, fn] of Object.entries(tests)) {
        try { await fn(); console.log('ok  ', name); } catch (e) { failed++; console.log('FAIL', name, '\n     ', e.message); }
    }
    console.log(`${Object.keys(tests).length - failed}/${Object.keys(tests).length} passed`);
    process.exit(failed ? 1 : 0);
})();
