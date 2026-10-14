// Apteka.ru: панель на карточке товара — заказ в один клик на самовывоз в Фарматек
// (Ленина 161): количество, номер клиента, комментарий, витаминки → «Заказать».
// Сам заказ оформляет apteka-hook.js (MAIN world) через клиент сайта; после успеха
// строка уходит в бот через background.js (как у Ютеки).
(() => {
    const SOURCE = 'apteka-helper-apteka';
    const COLLAPSED_KEY = 'aptekaPanelCollapsed';
    const VITAMINS_KEY = 'aptekaVitamins';
    const MAX_COUNT = 20;
    const ORDER_TIMEOUT_MS = 45000;
    const VIT_OPTIONS = [['0', 'не списывать'], ...Array.from({ length: 10 }, (_, i) => [String(i + 1), `${i + 1}%`]), ['max', 'максимум']];

    const rub = n => Number(n).toLocaleString('ru-RU') + ' ₽';

    const st = {
        itemId: null, info: null, infoError: '', loggedIn: true, otherItems: [], vitBalance: null,
        phone: '', comment: '', count: 1, vitamins: '0', unit: null,
        busy: false, msg: '', kind: '', focus: null, collapsed: false,
    };
    const pending = {};

    function itemIdFromPath(path) {
        const m = String(path || '').match(/^\/product\/[^/]*?-([0-9a-f]{24})\/?$/i);
        return m ? m[1].toLowerCase() : null;
    }

    function dryRun() {
        try { return localStorage.getItem('aptekaHelperDryRun') === '1'; } catch (e) { return false; }
    }

    function reqId() { return Math.random().toString(36).slice(2); }

    // ---------- связь с apteka-hook.js ----------

    window.addEventListener('message', ev => {
        const d = ev.data;
        if (ev.source !== window || !d || d.source !== SOURCE) return;
        if (d.type === 'product-info') onProductInfo(d);
        else if (d.type === 'order-result') onOrderResult(d);
    });

    function requestProduct() {
        const id = reqId();
        pending[id] = { kind: 'product', itemId: st.itemId };
        window.postMessage({ source: SOURCE, type: 'get-product', reqId: id }, location.origin);
    }

    function onProductInfo(d) {
        const p = pending[d.reqId];
        if (!p || p.kind !== 'product') return;
        delete pending[d.reqId];
        if (p.itemId !== st.itemId) return; // пока ждали, ушли на другой товар
        if (d.error || !d.info) { st.infoError = d.error || 'нет данных товара'; render(); return; }
        st.info = d.info;
        st.infoError = '';
        st.loggedIn = d.loggedIn !== false;
        st.otherItems = d.otherItems || [];
        st.vitBalance = d.vitBalance == null ? null : d.vitBalance;
        if (!st.unit) st.unit = d.info.price;
        render();
    }

    // ---------- заказ ----------

    function setMsg(text, kind) {
        st.msg = text;
        st.kind = kind || '';
        render();
    }

    function resetForm(keepMsg) {
        Object.assign(st, { phone: '', comment: '', count: 1, unit: st.info ? st.info.price : null, busy: false, focus: null });
        if (!keepMsg) { st.msg = ''; st.kind = ''; }
    }

    function currentImage() {
        const meta = document.querySelector('meta[property="og:image"]');
        const url = meta ? String(meta.content || '') : '';
        return url.startsWith('https://') ? url : '';
    }

    function placeOrder() {
        if (st.busy || !st.info) return;
        const phone = st.phone.trim();
        const comment = st.comment.trim();
        if (!phone && !comment) { setMsg('Введи номер клиента (или комментарий).', 'err'); return; }
        const id = reqId();
        const unit = st.unit || st.info.price;
        pending[id] = { kind: 'order', itemId: st.itemId, name: st.info.name, unit, count: st.count, phone, comment, vitamins: st.vitamins };
        st.busy = true;
        setMsg(dryRun() ? 'ТЕСТ: считаю корзину…' : 'Оформляю заказ на Apteka.ru…', '');
        window.postMessage({
            source: SOURCE, type: 'place-order', reqId: id,
            itemId: st.info.itemId, count: st.count, expectedUnit: unit, vitamins: st.vitamins,
        }, location.origin);
        setTimeout(() => {
            if (!pending[id]) return;
            delete pending[id];
            st.busy = false;
            setMsg('Apteka.ru не ответила. Перед повтором проверь «Мои заказы» — заказ мог создаться.', 'err');
        }, ORDER_TIMEOUT_MS);
    }

    function vitText(d) {
        if (!d.vitaminsPercent) {
            return d.vitaminsWanted && d.vitaminsWanted !== '0' ? ' Витаминки не списаны: корзина не позволила.' : '';
        }
        const capped = d.vitaminsWanted !== 'max' && Number(d.vitaminsWanted) > d.vitaminsPercent ? ` (больше нельзя, макс. ${d.vitaminsMax}%)` : '';
        return ` Витаминки −${d.vitaminsPercent}%${capped}.`;
    }

    function onOrderResult(d) {
        const p = pending[d.reqId];
        if (!p || p.kind !== 'order') return;
        delete pending[d.reqId];
        st.busy = false;
        if (d.priceChanged) {
            st.unit = d.priceChanged;
            setMsg(`Цена в Фарматеке изменилась: ${rub(d.priceChanged)} за шт., итого ${rub(d.priceChanged * p.count)}. Нажми «Заказать» ещё раз, если подходит.`, 'err');
            return;
        }
        if (d.error) {
            setMsg((d.orderUnknown ? 'Ошибка при оформлении — проверь «Мои заказы», заказ мог создаться: ' : 'Заказ не оформлен: ') + d.error, 'err');
            return;
        }
        if (d.dryRun) {
            setMsg(`ТЕСТ: корзина посчитала ${rub(d.totalBefore)}` +
                (d.vitaminsPercent ? `, с витаминками ${rub(d.totalAfter)}` : '') + '.' + vitText(d) +
                ' Заказ не создан, корзина очищена, в таблицу не отправлено.', 'ok');
            return;
        }
        const num = d.orderNum ? ` №${d.orderNum}` : '';
        const clientTotal = d.totalBefore || p.unit * p.count; // клиенту — без витаминок
        const payload = {
            phone: p.phone, comment: p.comment, source: 'apteka',
            url: location.origin + location.pathname,
            product: p.count > 1 ? `${p.name} × ${p.count}` : p.name,
            price: clientTotal,
            order_number: d.orderNum || '',
            vitamins_percent: d.vitaminsPercent || 0,
            paid_total: d.total || clientTotal,
            image: currentImage(),
        };
        resetForm(true);
        const paid = d.vitaminsPercent ? `, оплатим ${rub(payload.paid_total)}` : '';
        setMsg(`Заказ${num} оформлен.${vitText(d)} Записываю в таблицу…`, 'ok');
        chrome.runtime.sendMessage({ type: 'bot-order', payload }, resp => {
            const err = chrome.runtime.lastError ? chrome.runtime.lastError.message
                : !resp ? 'нет ответа' : !resp.ok ? (resp.error || (resp.data && resp.data.message) || 'ошибка бота') : '';
            if (err) {
                setMsg(`Заказ${num} оформлен, но в таблицу НЕ записан (${err}). Отправь вручную через окно расширения.`, 'err');
            } else {
                setMsg(`✅ Заказ${num} оформлен и записан в таблицу: ${p.phone || p.comment}, ${rub(clientTotal)}${paid}.`, 'ok');
            }
        });
    }

    // ---------- панель ----------

    let host = null;
    let shadow = null;

    function esc(s) {
        return String(s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
    }

    function ensurePanel() {
        if (host && document.body.contains(host)) return;
        host = document.createElement('div');
        host.id = 'apteka-helper-apteka';
        host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483646;';
        shadow = host.attachShadow({ mode: 'open' });
        document.body.appendChild(host);
    }

    function bodyHtml() {
        if (!st.info) {
            return st.infoError
                ? `<div>Не удалось прочитать товар: ${esc(st.infoError)}.</div><button class="btn" data-act="retry">Повторить</button>`
                : '<div class="muted">Загружаю товар…</div>';
        }
        const info = st.info;
        const unit = st.unit || info.price;
        const warn = [];
        if (!st.loggedIn) warn.push('Не выполнен вход на apteka.ru — войди по SMS.');
        if (info.outOfStock) warn.push('Нет в наличии — заказать нельзя.');
        if (info.prescription) warn.push('Рецептурный препарат.');
        if (st.otherItems.length) warn.push('В корзине уже есть: ' + st.otherItems.join('; ') + '. Оформи или отложи их — иначе заказ не пройдёт.');
        const disabled = st.busy || info.outOfStock || !st.loggedIn;
        const vitOpts = VIT_OPTIONS.map(([v, label]) => `<option value="${v}" ${st.vitamins === v ? 'selected' : ''}>${label}</option>`).join('');
        return `
            <div class="name">${esc(info.name)}</div>
            <div class="price">${rub(unit)}${st.count > 1 ? ` × ${st.count} = <b class="total">${rub(unit * st.count)}</b>` : ''}</div>
            ${warn.map(w => `<div class="warn">⚠️ ${esc(w)}</div>`).join('')}
            <div class="order">
                <input data-f="phone" type="tel" placeholder="Номер клиента" value="${esc(st.phone)}">
                <input data-f="comment" type="text" placeholder="Комментарий (необязательно)" value="${esc(st.comment)}">
                <div class="orow">
                    <span class="muted">Кол-во</span>
                    <button class="qbtn" data-act="minus">−</button><b>${st.count}</b><button class="qbtn" data-act="plus">+</button>
                    <span class="grow"></span>
                    <span class="muted">Витаминки</span>
                    <select data-f="vitamins">${vitOpts}</select>
                </div>
                ${st.vitBalance != null ? `<div class="hint">Баланс: ${Number(st.vitBalance).toLocaleString('ru-RU')} витаминок. Процент ограничит корзина сайта.</div>` : ''}
                <button class="btn obtn ${dryRun() ? 'test' : ''}" data-act="order" ${disabled ? 'disabled' : ''}>${
                    st.busy ? 'Оформляю…' : dryRun() ? 'ТЕСТ: посчитать без заказа' : 'Заказать на Apteka.ru'}</button>
            </div>
            ${st.msg ? `<div class="omsg ${st.kind}">${esc(st.msg)}</div>` : ''}
            <div class="note">Самовывоз: Фарматек, Ленина 161. Заказ оформляет всю корзину apteka.ru.</div>`;
    }

    function paint() {
        ensurePanel();
        host.style.display = '';
        const collapsed = st.collapsed;
        shadow.innerHTML = `
            <style>
                :host { all: initial; }
                .box { font: 13px/1.35 system-ui, -apple-system, 'Segoe UI', sans-serif; color: #1f2937;
                       background: #fff; border: 2px solid #2563eb; border-radius: 12px;
                       box-shadow: 0 6px 24px rgba(0,0,0,.18); width: 340px; max-width: calc(100vw - 32px); }
                .head { display: flex; justify-content: space-between; align-items: center; gap: 8px;
                        padding: 8px 12px; background: #2563eb; color: #fff; border-radius: 9px 9px 0 0;
                        cursor: pointer; font-weight: 700; user-select: none; }
                .collapsed .head { border-radius: 9px; }
                .body { padding: 10px 12px; }
                .collapsed .body { display: none; }
                .name { font-weight: 600; margin-bottom: 2px; }
                .price { margin-bottom: 6px; }
                .total { color: #c2410c; font-size: 15px; }
                .muted { color: #6b7280; }
                .note { color: #6b7280; font-size: 11px; margin-top: 8px; }
                .hint { color: #6b7280; font-size: 11px; margin-top: 2px; }
                .warn { color: #b45309; font-size: 12px; margin: 2px 0 4px; }
                .order { margin-top: 6px; padding: 8px; border: 1px solid #2563eb; border-radius: 8px; background: #eff6ff; }
                .order input { display: block; box-sizing: border-box; width: 100%; margin: 0 0 6px; padding: 6px 8px;
                               border: 1px solid #d1d5db; border-radius: 6px; font: 14px system-ui, sans-serif; background: #fff; color: #111; }
                .order select { padding: 3px 4px; border: 1px solid #d1d5db; border-radius: 6px; font: 13px system-ui, sans-serif; background: #fff; color: #111; }
                .orow { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; white-space: nowrap; }
                .orow .grow { flex: 1; }
                .qbtn { width: 24px; height: 24px; border: 1px solid #d1d5db; border-radius: 6px; background: #fff; cursor: pointer; font: 600 14px system-ui; }
                .btn { display: inline-block; margin-top: 8px; padding: 6px 10px; border-radius: 8px; border: 0;
                       background: #2563eb; color: #fff; font: 600 13px system-ui, sans-serif; cursor: pointer; }
                .obtn { display: block; width: 100%; margin-top: 8px; font-size: 14px; padding: 8px; }
                .obtn.test { background: #7c3aed; }
                .obtn[disabled] { opacity: .6; cursor: default; }
                .omsg { margin-top: 8px; padding: 6px 8px; border-radius: 6px; font-size: 12px; background: #f1f5f9; }
                .omsg.ok { background: #dcfce7; color: #14532d; }
                .omsg.err { background: #fff7ed; color: #9a3412; }
            </style>
            <div class="box ${collapsed ? 'collapsed' : ''}">
                <div class="head"><span>💊 Apteka.ru · Фарматек${dryRun() ? ' · ТЕСТ' : ''}</span><span>${collapsed ? '▲' : '▼'}</span></div>
                <div class="body">${bodyHtml()}</div>
            </div>`;
        shadow.querySelector('.head').addEventListener('click', () => {
            chrome.storage.local.set({ [COLLAPSED_KEY]: !collapsed });
        });
        wire();
    }

    function wire() {
        const act = (name, fn) => { const b = shadow.querySelector(`[data-act="${name}"]`); if (b) b.addEventListener('click', fn); };
        act('retry', () => { st.infoError = ''; requestProduct(); render(); });
        act('minus', () => { if (st.count > 1 && !st.busy) { st.count--; render(); } });
        act('plus', () => { if (st.count < MAX_COUNT && !st.busy) { st.count++; render(); } });
        act('order', placeOrder);
        shadow.querySelectorAll('input[data-f]').forEach(inp => {
            inp.addEventListener('input', () => { st[inp.dataset.f] = inp.value; });
            inp.addEventListener('focus', () => { st.focus = inp.dataset.f; });
            // хоткеи сайта не должны срабатывать при наборе
            inp.addEventListener('keydown', ev => {
                ev.stopPropagation();
                if (ev.key === 'Enter') placeOrder();
            });
            inp.addEventListener('keyup', ev => ev.stopPropagation());
            inp.addEventListener('keypress', ev => ev.stopPropagation());
        });
        const sel = shadow.querySelector('select[data-f="vitamins"]');
        if (sel) sel.addEventListener('change', () => {
            st.vitamins = sel.value;
            chrome.storage.local.set({ [VITAMINS_KEY]: sel.value });
        });
        if (st.focus) {
            const inp = shadow.querySelector(`input[data-f="${st.focus}"]`);
            if (inp) { inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length); }
        }
    }

    function render() {
        if (!document.body) return;
        if (!st.itemId) { if (host) host.style.display = 'none'; return; }
        paint();
    }

    // ---------- запуск ----------

    function onLocation() {
        const id = itemIdFromPath(location.pathname);
        if (id === st.itemId) return;
        st.itemId = id;
        st.info = null;
        st.infoError = '';
        st.otherItems = [];
        st.unit = null;
        resetForm();
        if (id) requestProduct();
        render();
    }

    function start() {
        chrome.storage.local.get([COLLAPSED_KEY, VITAMINS_KEY], d => {
            st.collapsed = !!d[COLLAPSED_KEY];
            const v = d[VITAMINS_KEY];
            if (VIT_OPTIONS.some(([val]) => val === v)) st.vitamins = v;
            onLocation();
        });
        let lastHref = location.href;
        setInterval(() => {
            if (location.href !== lastHref) { lastHref = location.href; onLocation(); }
        }, 250);
        chrome.storage.onChanged.addListener((changes, area) => {
            if (area !== 'local' || !changes[COLLAPSED_KEY]) return;
            st.collapsed = !!changes[COLLAPSED_KEY].newValue;
            render();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start, { once: true });
    } else {
        start();
    }
})();
