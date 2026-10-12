// Ютека: цены нашей аптеки (Фарматек, Ленина 161) с наценкой — на карточке товара,
// на карте аптек и в корзине. Цены берутся из ответов map.Cluster (см. uteka-hook.js):
// на карточке товара — автозапросом через API-клиент самого сайта, на карте — когда
// выбран Фарматек. С карточки можно сразу оформить заказ у выбранного поставщика:
// заказ на Ютеке (orders.Calculate → orders.Create в uteka-hook.js) + строка в таблицу
// через бот (background.js).
(() => {
    const PHARMACY_ID = 29723;
    const CITY_ID = 16; // Краснодарский край
    // кадр карты вокруг Фарматека, как при клике по его метке
    const PHARMACY_VIEW = {
        outsideBox: 0, myLat: 45.2675, myLon: 38.158333,
        neLat: 45.2685, neLon: 38.1595, swLat: 45.2665, swLon: 38.1572,
        pharmacyId: PHARMACY_ID, zoomLevel: 17,
    };
    const FRESH_MS = 10 * 60 * 1000;
    const FETCH_TIMEOUT_MS = 25 * 1000;
    const PHARMACY_LABEL = 'Фарматек · Ленина 161';
    const MARKUP = 0.05;
    const SOURCE = 'apteka-helper-uteka';
    const PRODUCT_PREFIX = 'utekaProd:';
    const LAST_KEY = 'utekaLast';
    const COLLAPSED_KEY = 'utekaPanelCollapsed';
    const TITLES_KEY = 'utekaTitles';
    const IMAGES_KEY = 'utekaImages'; // productId -> og:image карточки (фото для вкладки «Заказы»)
    const MAX_PRODUCTS = 300;
    const PCT = Math.round(MARKUP * 100);

    const withMarkup = price => Math.ceil(price * (1 + MARKUP));
    const rub = n => Number(n).toLocaleString('ru-RU') + ' ₽';

    // ---------- приём данных ----------

    window.addEventListener('message', ev => {
        const d = ev.data;
        if (ev.source !== window || !d || d.source !== SOURCE) return;
        if (d.type === 'cluster') {
            try { handleCluster(d.result, d.request, !!d.auto); } catch (e) { console.warn('[apteka-helper] uteka', e); }
        } else if (d.type === 'fetch-result') {
            const pid = Number(d.productId);
            if (d.error) fetchState[pid] = 'error';
            else delete fetchState[pid];
            render();
        } else if (d.type === 'order-result') {
            onOrderResult(d);
        }
    });

    // auto — ответ на наш запрос с карточки товара: корзину он не описывает
    function handleCluster(result, request, auto) {
        if (!result || Number((result.view || {}).pharmacyId) !== PHARMACY_ID) return;

        const params = (request && request.params) || {};
        const cart = normalizeCart((params.data || {}).cart);
        const ts = Date.now();

        // extendedPickups — поставщики всех аптек в кадре карты; какие из них возят
        // в Фарматек, сказано в extendedPickupIds его метки. Нет метки — товара там нет.
        const pin = ((result.map || {}).items || []).find(i => Number(i.pharmacyId) === PHARMACY_ID);
        const ourIds = new Set(((pin && pin.extendedPickupIds) || []).map(Number));

        const offers = Object.entries(result.extendedPickups || {})
            .filter(([id, e]) => ourIds.has(Number(id)) && e && e.network && e.active !== false && Number(e.price) > 0)
            .map(([id, e]) => ({
                networkId: Number(id),
                supplier: e.network.title || ('#' + e.network.id),
                total: Number(e.price),
                text: e.pickupDateText || '',
                partial: !!e.isPartial,
                items: normalizeCart(e.cart),
            }));

        // Собственная бронь в аптеке, если Ютека её показывает
        if (pin && pin.hasPickup && Number(pin.price) > 0) {
            offers.push({
                networkId: null, // бронь в самой аптеке этим путём не оформляем
                supplier: 'Бронь в аптеке',
                total: Number(pin.price),
                text: pin.pickupText || '',
                partial: !!pin.isPartial,
                items: normalizeCart(pin.cart),
            });
        }
        if (!offers.length) {
            // запрос по одному товару без предложений — запоминаем, что в Фарматек его не везут
            if (cart.length === 1) chrome.storage.local.set({ [PRODUCT_PREFIX + cart[0].productId]: { ts, offers: [] } });
            return;
        }
        offers.sort((a, b) => a.total - b.total);

        const toSave = auto ? {} : { [LAST_KEY]: { ts, cart, offers } };

        const byProduct = {};
        for (const o of offers) {
            for (const it of o.items) {
                (byProduct[it.productId] = byProduct[it.productId] || []).push({
                    supplier: o.supplier, price: it.price, text: o.text, networkId: o.networkId,
                });
            }
        }
        for (const [pid, list] of Object.entries(byProduct)) {
            list.sort((a, b) => a.price - b.price);
            toSave[PRODUCT_PREFIX + pid] = { ts, offers: list };
        }
        chrome.storage.local.set(toSave, prune);
    }

    function normalizeCart(cart) {
        return (Array.isArray(cart) ? cart : [])
            .map(c => ({ productId: Number(c.productId), count: Number(c.count) || 1, price: Number(c.price) || 0 }))
            .filter(c => c.productId);
    }

    function prune() {
        chrome.storage.local.get(null, all => {
            const keys = Object.keys(all).filter(k => k.startsWith(PRODUCT_PREFIX));
            if (keys.length <= MAX_PRODUCTS) return;
            keys.sort((a, b) => (all[a].ts || 0) - (all[b].ts || 0));
            chrome.storage.local.remove(keys.slice(0, keys.length - MAX_PRODUCTS));
        });
    }

    // ---------- автозапрос цен для карточки товара ----------

    const fetchState = {};          // productId -> 'loading' | 'error'
    const requestedThisPage = new Set();

    function requestPrices(productId) {
        if (fetchState[productId] === 'loading') return;
        fetchState[productId] = 'loading';
        window.postMessage({
            source: SOURCE, type: 'fetch-prices', productId, cityId: CITY_ID, view: PHARMACY_VIEW,
        }, location.origin);
        setTimeout(() => {
            if (fetchState[productId] === 'loading') { fetchState[productId] = 'error'; render(); }
        }, FETCH_TIMEOUT_MS);
    }

    // ---------- заказ с карточки ----------

    // одна открытая форма заказа на вкладку
    const order = { productId: null, idx: null, phone: '', comment: '', count: 1, unit: null,
                    busy: false, msg: '', kind: '', focus: null };
    const pendingOrders = {};

    function resetOrderForm(keepMsg) {
        Object.assign(order, { idx: null, phone: '', comment: '', count: 1, unit: null, busy: false, focus: null });
        if (!keepMsg) { order.msg = ''; order.kind = ''; }
    }

    function setMsg(text, kind) {
        order.msg = text;
        order.kind = kind || '';
        render();
    }

    function currentImage(productId) {
        if (productIdFromPath(location.pathname) !== productId) return '';
        const meta = document.querySelector('meta[property="og:image"]');
        const url = meta ? String(meta.content || '') : '';
        return url.startsWith('https://') ? url : '';
    }

    function currentTitle(productId) {
        const h1 = document.querySelector('h1');
        const fromPage = h1 && productIdFromPath(location.pathname) === productId
            ? normText(h1).replace(/^Купить\s+/i, '') : '';
        return fromPage || String(document.title || '').split(' – ')[0].trim() || ('товар #' + productId);
    }

    function placeOrder(productId, offer) {
        if (order.busy) return;
        const phone = order.phone.trim();
        const comment = order.comment.trim();
        if (!phone && !comment) { setMsg('Введи номер клиента (или комментарий).', 'err'); return; }
        const unit = order.unit || offer.price;
        const count = order.count;
        const reqId = Math.random().toString(36).slice(2);
        pendingOrders[reqId] = { productId, supplier: offer.supplier, networkId: offer.networkId, unit, count, phone, comment };
        order.busy = true;
        setMsg('Оформляю заказ на Ютеке…', '');
        window.postMessage({
            source: SOURCE, type: 'place-order', reqId, productId, count,
            pharmacyId: PHARMACY_ID, networkId: offer.networkId, expectedTotal: unit * count,
        }, location.origin);
        setTimeout(() => {
            if (!pendingOrders[reqId]) return;
            delete pendingOrders[reqId];
            order.busy = false;
            setMsg('Ютека не ответила. Перед повтором проверь вкладку «Заказы» — заказ мог создаться.', 'err');
        }, 30000);
    }

    function onOrderResult(d) {
        const p = pendingOrders[d.reqId];
        if (!p) return;
        delete pendingOrders[d.reqId];
        order.busy = false;
        if (d.priceChanged) {
            order.unit = d.priceChanged / p.count;
            setMsg(`Цена у ${p.supplier} изменилась: ${rub(d.priceChanged)} на Ютеке, клиенту ${rub(withMarkup(order.unit) * p.count)}. Нажми «Заказать» ещё раз, если подходит.`, 'err');
            return;
        }
        if (d.error) { setMsg('Заказ не оформлен: ' + d.error, 'err'); return; }
        if (d.dryRun) {
            setMsg(`ТЕСТ: Ютека подтвердила ${rub(d.price)} у ${p.supplier}. Заказ не создан, в таблицу не отправлено.`, 'ok');
            return;
        }
        const num = d.orderNumber ? ` №${d.orderNumber}` : '';
        const clientTotal = withMarkup(p.unit) * p.count;
        const title = currentTitle(p.productId);
        const payload = {
            phone: p.phone, comment: p.comment, source: 'uteka',
            url: location.origin + '/product/' + location.pathname.split('/product/')[1],
            product: p.count > 1 ? `${title} × ${p.count}` : title,
            supplier: p.supplier, price: clientTotal,
            image: currentImage(p.productId),
        };
        resetOrderForm(true);
        setMsg(`Заказ на Ютеке оформлен${num}. Записываю в таблицу…`, 'ok');
        chrome.runtime.sendMessage({ type: 'bot-order', payload }, resp => {
            const err = chrome.runtime.lastError ? chrome.runtime.lastError.message
                : !resp ? 'нет ответа' : !resp.ok ? (resp.error || (resp.data && resp.data.message) || 'ошибка бота') : '';
            if (err) {
                setMsg(`Заказ на Ютеке оформлен${num}, но в таблицу НЕ записан (${err}). Отправь вручную через окно расширения.`, 'err');
            } else {
                setMsg(`✅ Заказ${num} оформлен у ${p.supplier} и записан в таблицу: ${p.phone || p.comment}, ${rub(clientTotal)}.`, 'ok');
            }
        });
    }

    function orderFormHtml(offer) {
        const unit = order.unit || offer.price;
        const total = withMarkup(unit) * order.count;
        return `<div class="order">
            <div class="ohead">Заказ у <b>${esc(offer.supplier)}</b> · клиенту <b class="client">${rub(total)}</b>
                ${order.count > 1 ? `<span class="muted">(${order.count} × ${rub(withMarkup(unit))})</span>` : ''}</div>
            <input data-f="phone" type="tel" placeholder="Номер клиента" value="${esc(order.phone)}">
            <input data-f="comment" type="text" placeholder="Комментарий (необязательно)" value="${esc(order.comment)}">
            <div class="orow">
                <span class="muted">Кол-во</span>
                <button class="qbtn" data-act="minus">−</button><b>${order.count}</b><button class="qbtn" data-act="plus">+</button>
                <span class="grow"></span>
                <button class="link" data-act="cancel">отмена</button>
            </div>
            <button class="btn obtn" data-act="order" ${order.busy ? 'disabled' : ''}>${order.busy ? 'Оформляю…' : 'Заказать на Ютеке'}</button>
        </div>`;
    }

    function wireOrderForm(productId, offers) {
        shadow.querySelectorAll('tr[data-idx]').forEach(tr => tr.addEventListener('click', () => {
            const idx = Number(tr.dataset.idx);
            if (order.busy || (order.productId === productId && order.idx === idx)) return;
            resetOrderForm();
            Object.assign(order, { productId, idx, focus: 'phone' });
            render();
        }));
        const form = shadow.querySelector('.order');
        if (!form) return;
        const offer = offers[order.idx];
        form.querySelectorAll('input[data-f]').forEach(inp => {
            inp.addEventListener('input', () => { order[inp.dataset.f] = inp.value; });
            inp.addEventListener('focus', () => { order.focus = inp.dataset.f; });
            // хоткеи сайта не должны срабатывать при наборе
            inp.addEventListener('keydown', ev => {
                ev.stopPropagation();
                if (ev.key === 'Enter') placeOrder(productId, offer);
            });
            inp.addEventListener('keyup', ev => ev.stopPropagation());
            inp.addEventListener('keypress', ev => ev.stopPropagation());
        });
        const act = (name, fn) => { const b = form.querySelector(`[data-act="${name}"]`); if (b) b.addEventListener('click', fn); };
        act('minus', () => { if (order.count > 1) { order.count--; render(); } });
        act('plus', () => { if (order.count < 20) { order.count++; render(); } });
        act('cancel', () => { if (!order.busy) { resetOrderForm(); render(); } });
        act('order', () => placeOrder(productId, offer));
        if (order.focus) {
            const inp = form.querySelector(`input[data-f="${order.focus}"]`);
            if (inp) { inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); }
        }
    }

    // ---------- панель ----------

    let host = null;
    let pickerOpenedAt = 0;
    let shadow = null;

    function ensurePanel() {
        if (host && document.body.contains(host)) return;
        host = document.createElement('div');
        host.id = 'apteka-helper-uteka';
        host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483646;';
        shadow = host.attachShadow({ mode: 'open' });
        document.body.appendChild(host);
    }

    function hidePanel() {
        if (host) host.style.display = 'none';
    }

    function age(ts) {
        const min = Math.round((Date.now() - ts) / 60000);
        if (min < 1) return 'только что';
        if (min < 60) return min + ' мин назад';
        const d = new Date(ts);
        const hh = String(d.getHours()).padStart(2, '0');
        const mm = String(d.getMinutes()).padStart(2, '0');
        if (min < 24 * 60) return 'сегодня в ' + hh + ':' + mm;
        return d.toLocaleDateString('ru-RU') + ' ' + hh + ':' + mm;
    }

    function esc(s) {
        return String(s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
    }

    function rowsHtml(list, priceKey) {
        return list.map(o => `
            <tr>
                <td class="sup">${esc(o.supplier)}${o.partial ? ' <span class="muted">(не всё)</span>' : ''}</td>
                <td class="num muted">${rub(o[priceKey])}</td>
                <td class="num client">${rub(withMarkup(o[priceKey]))}</td>
            </tr>`).join('');
    }

    function tableHtml(list, priceKey) {
        return `<table>
            <tr><th>Поставщик</th><th class="num">Ютека</th><th class="num">Клиенту +${PCT}%</th></tr>
            ${rowsHtml(list, priceKey)}
        </table>`;
    }

    function paint(bodyHtml, collapsed) {
        ensurePanel();
        host.style.display = '';
        shadow.innerHTML = `
            <style>
                :host { all: initial; }
                .box { font: 13px/1.35 system-ui, -apple-system, 'Segoe UI', sans-serif; color: #1f2937;
                       background: #fff; border: 2px solid #16a34a; border-radius: 12px;
                       box-shadow: 0 6px 24px rgba(0,0,0,.18); width: 340px; max-width: calc(100vw - 32px); }
                .head { display: flex; justify-content: space-between; align-items: center; gap: 8px;
                        padding: 8px 12px; background: #16a34a; color: #fff; border-radius: 9px 9px 0 0;
                        cursor: pointer; font-weight: 700; user-select: none; }
                .collapsed .head { border-radius: 9px; }
                .body { padding: 10px 12px; }
                .collapsed .body { display: none; }
                table { width: 100%; border-collapse: collapse; }
                th { font-weight: 600; color: #6b7280; font-size: 12px; text-align: left; padding: 2px 0 4px; }
                td { padding: 4px 0; border-top: 1px solid #f1f5f9; vertical-align: top; }
                .num { text-align: right; white-space: nowrap; padding-left: 8px; }
                .client { font-weight: 800; font-size: 15px; color: #c2410c; }
                .muted { color: #6b7280; }
                .note { color: #6b7280; font-size: 12px; margin-top: 8px; }
                .warn { color: #b45309; }
                ul.cart { margin: 2px 0 8px; padding-left: 18px; }
                .btn { display: inline-block; margin-top: 8px; padding: 6px 10px; border-radius: 8px; border: 0;
                       background: #16a34a; color: #fff; text-decoration: none; font: 600 13px system-ui, sans-serif; cursor: pointer; }
                .link { margin-left: 10px; color: #16a34a; font-size: 12px; background: none; border: 0; cursor: pointer; text-decoration: underline; padding: 0; }
                tr.pick { cursor: pointer; }
                tr.pick:hover td { background: #f0fdf4; }
                tr.sel td { background: #dcfce7; }
                .hint { color: #6b7280; font-size: 11px; margin-top: 4px; }
                .order { margin-top: 8px; padding: 8px; border: 1px solid #16a34a; border-radius: 8px; background: #f0fdf4; }
                .ohead { margin-bottom: 6px; }
                .order input { display: block; box-sizing: border-box; width: 100%; margin: 0 0 6px; padding: 6px 8px;
                               border: 1px solid #d1d5db; border-radius: 6px; font: 14px system-ui, sans-serif; background: #fff; color: #111; }
                .orow { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; }
                .orow .grow { flex: 1; }
                .qbtn { width: 24px; height: 24px; border: 1px solid #d1d5db; border-radius: 6px; background: #fff; cursor: pointer; font: 600 14px system-ui; }
                .obtn { display: block; width: 100%; margin-top: 6px; font-size: 14px; padding: 8px; }
                .obtn[disabled] { opacity: .6; cursor: default; }
                .omsg { margin-top: 8px; padding: 6px 8px; border-radius: 6px; font-size: 12px; background: #f1f5f9; }
                .omsg.ok { background: #dcfce7; color: #14532d; }
                .omsg.err { background: #fff7ed; color: #9a3412; }
            </style>
            <div class="box ${collapsed ? 'collapsed' : ''}">
                <div class="head"><span>💊 ${esc(PHARMACY_LABEL)} · +${PCT}%</span><span>${collapsed ? '▲' : '▼'}</span></div>
                <div class="body">${bodyHtml}</div>
            </div>`;
        shadow.querySelector('.head').addEventListener('click', () => {
            chrome.storage.local.set({ [COLLAPSED_KEY]: !collapsed });
        });
    }

    function productIdFromPath(path) {
        const m = path.match(/^\/product\/[^/]*?-(\d+)\/?$/);
        return m ? Number(m[1]) : null;
    }

    function render() {
        if (!document.body) return;
        const path = location.pathname;
        const productId = productIdFromPath(path);
        const isPicker = path.startsWith('/checkout/pickup/picker');
        const isCart = path.startsWith('/cart');

        if (!productId && !isPicker && !isCart) {
            hidePanel();
            return;
        }

        const keys = [LAST_KEY, COLLAPSED_KEY, TITLES_KEY];
        if (productId) keys.push(PRODUCT_PREFIX + productId);

        chrome.storage.local.get(keys, data => {
            if (location.pathname !== path) return; // пока читали storage, ушли на другую страницу
            const collapsed = !!data[COLLAPSED_KEY];

            if (productId) {
                const entry = data[PRODUCT_PREFIX + productId];
                // кэш до версии 2.5 без networkId — по нему нельзя заказать, обновляем сразу
                const legacy = entry && (entry.offers || []).some(o => o.networkId === undefined);
                const fresh = entry && !legacy && Date.now() - entry.ts < FRESH_MS;
                if (!fresh && !requestedThisPage.has(productId)) {
                    requestedThisPage.add(productId);
                    requestPrices(productId);
                }
                const state = fetchState[productId];
                const pickerUrl = `/checkout/pickup/picker/?fastOrderProductCount=1&fastOrderProductId=${productId}`;
                const status = state === 'loading' ? ' Обновляю…'
                    : state === 'error' ? ' Не удалось обновить.' : '';
                const actions = `<button class="btn" data-act="refresh">Обновить</button>
                    <a class="link" href="${pickerUrl}">карта аптек</a>`;
                let html;
                if (order.productId !== productId) { resetOrderForm(); order.productId = productId; }
                const offers = (entry && entry.offers) || [];
                if (order.idx !== null && !(offers[order.idx] && offers[order.idx].networkId)) resetOrderForm(true);
                const msgHtml = order.msg ? `<div class="omsg ${order.kind}">${esc(order.msg)}</div>` : '';
                if (offers.length) {
                    const rows = offers.map((o, i) => {
                        const orderable = !!o.networkId;
                        const cls = [orderable ? 'pick' : '', order.idx === i ? 'sel' : ''].join(' ');
                        return `<tr class="${cls}" ${orderable ? `data-idx="${i}"` : ''}>
                            <td class="sup">${esc(o.supplier)}</td>
                            <td class="num muted">${rub(o.price)}</td>
                            <td class="num client">${rub(withMarkup(o.price))}</td>
                        </tr>`;
                    }).join('');
                    const canOrder = offers.some(o => o.networkId);
                    html = `<table>
                            <tr><th>Поставщик</th><th class="num">Ютека</th><th class="num">Клиенту +${PCT}%</th></tr>
                            ${rows}
                        </table>
                        ${order.idx !== null ? orderFormHtml(offers[order.idx])
                            : canOrder ? '<div class="hint">Нажми на поставщика, чтобы заказать.</div>'
                            : '<div class="hint">Чтобы заказать отсюда, нажми «Обновить».</div>'}
                        ${msgHtml}
                        <div class="note">Цена за 1 шт. Обновлено ${esc(age(entry.ts))}.${status}</div>${actions}`;
                } else if (entry && !state) {
                    html = `<div>В Фарматек этот товар сейчас не привезут.</div>
                        <div class="note">Ютека не даёт по нему поставщиков для Ленина 161. Проверено ${esc(age(entry.ts))}.</div>${actions}`;
                } else if (state === 'loading') {
                    html = `<div class="muted">Загружаю цены Фарматека…</div>`;
                } else {
                    html = `<div>Не удалось получить цены Фарматека.</div>
                        <div class="note">Возможно, Ютека просит капчу. Пройди её и нажми «Обновить», или открой карту и выбери Фарматек.</div>${actions}`;
                }
                paint(html, collapsed);
                const btn = shadow.querySelector('[data-act="refresh"]');
                if (btn) btn.addEventListener('click', () => { requestPrices(productId); render(); });
                wireOrderForm(productId, offers);
                return;
            }

            const last = data[LAST_KEY];
            const titles = data[TITLES_KEY] || {};
            const askMap = `<div class="note">Выбери на карте Фарматек (Ленина 161) — тут появятся итоговые цены по корзине с наценкой.</div>`;
            if (!last || !last.offers || !last.offers.length) {
                paint(askMap, collapsed);
                return;
            }

            const lastIds = new Set(last.cart.map(c => c.productId));
            let verified = false;
            if (isPicker) {
                // на карте — только то, что пришло после её открытия
                if (last.ts < pickerOpenedAt) { paint(askMap, collapsed); return; }
                verified = true;
            } else {
                const pageIds = cartIdsOnPage();
                if (pageIds.size) {
                    const same = pageIds.size === lastIds.size && [...pageIds].every(id => lastIds.has(id));
                    if (!same) {
                        paint(`<div>Для этой корзины цен Фарматека ещё нет.</div>
                            <div class="note">Нажми «Выбрать аптеку» и выбери на карте Фарматек (Ленина 161).</div>`, collapsed);
                        return;
                    }
                    verified = true;
                }
            }

            const list = last.cart.map(c => `<li>${esc(titles[c.productId] || 'товар #' + c.productId)} × ${c.count}</li>`).join('');
            const stale = Date.now() - last.ts > 30 * 60 * 1000;
            paint(`<div class="muted">Итого за корзину:</div>
                <ul class="cart">${list}</ul>
                ${tableHtml(last.offers, 'total')}
                <div class="note ${stale || !verified ? 'warn' : ''}">Обновлено ${esc(age(last.ts))}.${
                    !verified ? ' Не смог сверить с корзиной на странице — проверь состав выше.'
                    : stale ? ' Если менял количество — открой Фарматек на карте ещё раз.' : ''}</div>`, collapsed);
        });
    }

    // ---------- товары на странице ----------

    function firstSkipHeading() {
        return [...document.querySelectorAll('h1,h2,h3,h4')].find(h => SKIP_SECTIONS_RE.test(h.textContent || '')) || null;
    }

    // элемент стоит выше блока рекомендаций («С этим берут» и т.п.)
    function beforeSkip(el, heading) {
        return !heading || !!(el.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING);
    }

    function cartIdsOnPage() {
        const heading = firstSkipHeading();
        const ids = new Set();
        for (const a of document.querySelectorAll('main a[href*="/product/"], body a[href*="/product/"]')) {
            if (!beforeSkip(a, heading)) continue;
            const id = productIdFromPath(new URL(a.href, location.href).pathname);
            if (id) ids.add(id);
        }
        return ids;
    }

    function rememberTitle() {
        const productId = productIdFromPath(location.pathname);
        const h1 = document.querySelector('h1');
        if (!productId || !h1) return;
        const title = normText(h1).replace(/^Купить\s+/i, '');
        if (!title) return;
        const image = currentImage(productId);
        chrome.storage.local.get([TITLES_KEY, IMAGES_KEY], d => {
            const t = d[TITLES_KEY] || {};
            const im = d[IMAGES_KEY] || {};
            if (t[productId] === title && (!image || im[productId] === image)) return;
            t[productId] = title;
            if (image) im[productId] = image;
            for (const map of [t, im]) {
                const ids = Object.keys(map);
                if (ids.length > 500) delete map[ids[0]];
            }
            chrome.storage.local.set({ [TITLES_KEY]: t, [IMAGES_KEY]: im });
        });
    }

    // ---------- +5% рядом с ценами в корзине ----------

    const PRICE_RE = /^(от )?(\d[\d ]*) ?₽$/;
    const SKIP_SECTIONS_RE = /С этим берут|Похожие товары|Вы смотрели|Рекомендуем/i;

    function normText(el) {
        return (el.innerText || '').replace(/[\s  ]+/g, ' ').trim();
    }

    function annotateCartPrices() {
        if (!location.pathname.startsWith('/cart') || !document.body) return;
        const heading = firstSkipHeading();
        const candidates = document.querySelectorAll('body span, body div, body p, body b, body strong');
        for (const el of candidates) {
            if (el.dataset.aptekaBadge || el.childElementCount > 8) continue;
            if (host && host.contains(el)) continue;
            if (el.closest('button, a[href*="/product/"], [class*="swiper"], [class*="carousel"], [class*="slider"]')) continue;
            if (!beforeSkip(el, heading)) continue;

            const text = normText(el);
            const m = text.match(PRICE_RE);
            // «от …» — минимум Ютеки по региону, а не цена Фарматека: не размечаем
            if (!m || m[1]) continue;
            // берём самый глубокий элемент с ценой
            if ([...el.children].some(ch => PRICE_RE.test(normText(ch)))) continue;

            const price = Number(m[2].replace(/\D/g, ''));
            if (!price) continue;
            const label = `+${PCT}%: ${rub(withMarkup(price))}`;

            let badge = el.nextElementSibling;
            if (!badge || !badge.dataset.aptekaBadge) {
                badge = document.createElement('span');
                badge.dataset.aptekaBadge = '1';
                badge.style.cssText = 'display:inline-block;margin:2px 0 0 8px;padding:1px 7px;border-radius:6px;' +
                    'background:#fff7ed;color:#c2410c;font:700 14px/1.4 system-ui,sans-serif;white-space:nowrap;';
                el.insertAdjacentElement('afterend', badge);
            }
            if (badge.textContent !== label) badge.textContent = label;
        }
    }

    // ---------- запуск ----------

    let annotateTimer = null;
    let lastCartSig = '';
    function onDomSettled() {
        annotateCartPrices();
        rememberTitle();
        if (location.pathname.startsWith('/cart')) {
            // корзина подгружается позже панели — перерисовать, когда появились товары
            const sig = [...cartIdsOnPage()].sort().join(',');
            if (sig !== lastCartSig) { lastCartSig = sig; render(); }
        }
    }
    function scheduleAnnotate() {
        if (annotateTimer) return;
        annotateTimer = setTimeout(() => { annotateTimer = null; onDomSettled(); }, 400);
    }

    function start() {
        if (location.pathname.startsWith('/checkout/pickup/picker')) pickerOpenedAt = Date.now();
        render();
        onDomSettled();
        new MutationObserver(scheduleAnnotate).observe(document.body, { childList: true, subtree: true, characterData: true });

        let lastHref = location.href;
        setInterval(() => {
            if (location.href !== lastHref) {
                lastHref = location.href;
                requestedThisPage.clear();
                if (location.pathname.startsWith('/checkout/pickup/picker')) pickerOpenedAt = Date.now();
                lastCartSig = '';
                render();
                scheduleAnnotate();
            }
        }, 250);

        chrome.storage.onChanged.addListener((changes, area) => {
            if (area === 'local') render();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start, { once: true });
    } else {
        start();
    }
})();
