document.addEventListener('DOMContentLoaded', async () => {
    const phoneInput = document.getElementById('phone');
    const commentInput = document.getElementById('comment');
    const sendBtn = document.getElementById('send-btn');
    const statusDiv = document.getElementById('status');
    const formContainer = document.getElementById('form-container');

    // Ютека: бот на VPS страницу Ютеки скачать не может — название товара
    // передаём сами (из заголовка карточки, который запомнила панель uteka.js)
    function utekaProductIdFromUrl(url) {
        const m = String(url || '').match(/^https:\/\/([a-z0-9-]+\.)?uteka\.ru\/product\/[^/?#]*?-(\d+)\/?(?:[?#]|$)/);
        return m ? Number(m[2]) : null;
    }

    async function utekaProductTitle(tab, productId) {
        const data = await chrome.storage.local.get(['utekaTitles']);
        return (data.utekaTitles || {})[productId] || String(tab.title || '').split(' – ')[0].trim();
    }

    // Apteka.ru: название с карточки даёт панель apteka.js; если она ещё не
    // загрузила товар (или вкладка открыта до обновления расширения) — заголовок вкладки
    async function aptekaProductInfo(tab) {
        let info = null;
        try {
            info = await chrome.tabs.sendMessage(tab.id, { type: 'apteka-product' });
        } catch (e) { /* на вкладке нет content script */ }
        if (info && info.name) return info;
        // «Торбад … 90 шт. капсулы массой 500 мг - цена 472 руб., купить в интернет аптеке …»
        const raw = String(tab.title || '');
        const title = raw.split(/\s+[—–-]\s+(?:цена|купить)/i)[0].trim();
        const price = Number(((raw.match(/цена\s+(\d+(?:[.,]\d+)?)\s*руб/i) || [])[1] || '').replace(',', '.')) || 0;
        if (!/[а-яё]/i.test(title)) return { name: '' };
        return price > 0 ? { name: title, price } : { name: title };
    }

    // Поставщики Фарматека для этой карточки (их подтягивает панель uteka.js):
    // выбираешь, у кого заказываешь, — в таблицу уйдут поставщик и цена +5%
    const UTEKA_MARKUP = 0.05;
    const suppliersBox = document.getElementById('uteka-suppliers');
    let utekaOffers = [];
    const [openedTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const openedUtekaId = utekaProductIdFromUrl(openedTab && openedTab.url);
    if (openedUtekaId) {
        const data = await chrome.storage.local.get(['utekaProd:' + openedUtekaId]);
        const entry = data['utekaProd:' + openedUtekaId];
        utekaOffers = ((entry && entry.offers) || []).map(o => ({
            supplier: o.supplier, base: o.price, client: Math.ceil(o.price * (1 + UTEKA_MARKUP)),
        }));
        suppliersBox.style.display = 'block';
        if (utekaOffers.length) {
            suppliersBox.innerHTML = '<label>У кого заказываем (Фарматек, цена клиенту +5%)</label>' +
                utekaOffers.map((o, i) => `
                    <label class="opt">
                        <input type="radio" name="uteka-supplier" value="${i}" ${i === 0 ? 'checked' : ''}>
                        <span class="sup">${escapeHtml(o.supplier)}</span>
                        <span class="price">${o.client.toLocaleString('ru-RU')} ₽</span>
                    </label>`).join('');
        } else {
            suppliersBox.innerHTML = `<div class="note">${entry
                ? '⚠️ Ютека не даёт поставщиков для Фарматека по этому товару.'
                : '⚠️ Цены Фарматека ещё не загрузились (дождись зелёной панели и открой окно снова).'}
                Заказ уйдёт без поставщика и цены.</div>`;
        }
    }

    function selectedUtekaOffer() {
        const checked = suppliersBox.querySelector('input[name="uteka-supplier"]:checked');
        return checked ? utekaOffers[Number(checked.value)] : null;
    }

    function escapeHtml(s) {
        return String(s).replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
    }

    // Force clear inputs (browser autofill fix)
    setTimeout(() => {
        phoneInput.value = '';
        commentInput.value = '';
        phoneInput.setAttribute('autocomplete', 'off');
        commentInput.setAttribute('autocomplete', 'off');
    }, 100);

    sendBtn.addEventListener('click', async () => {
        const phone = phoneInput.value.trim();
        const comment = commentInput.value.trim();
        if (!phone && !comment) {
            showStatus('⚠️ Введите номер телефона или комментарий', 'error');
            return;
        }



        sendBtn.disabled = true;
        const originalText = sendBtn.innerHTML;
        sendBtn.innerHTML = '<span class="loader"></span> Отправка...';

        try {
            // Get current tab URL
            const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
            const url = tab.url;

            const utekaId = utekaProductIdFromUrl(url);
            const isUteka = !!utekaId;
            if (!isUteka && (!url || !url.includes('apteka.ru/product/'))) {
                showStatus('🛑 Это не страница товара Apteka.ru или Ютеки', 'error');
                sendBtn.disabled = false;
                sendBtn.innerHTML = originalText;
                return;
            }

            // Send to local bot API
            let payload = { phone, url, comment };
            if (isUteka) {
                const offer = utekaId === openedUtekaId ? selectedUtekaOffer() : null;
                const images = (await chrome.storage.local.get(['utekaImages'])).utekaImages || {};
                payload = { phone, url, comment, product: await utekaProductTitle(tab, utekaId), source: 'uteka' };
                if (images[utekaId]) payload.image = images[utekaId];
                if (offer) Object.assign(payload, { supplier: offer.supplier, price: offer.client });
            } else {
                // Apteka.ru банит IP сервера (ошибка 432) — без названия отсюда бот
                // собрал бы его транслитом из ссылки
                const info = await aptekaProductInfo(tab);
                if (info.name) {
                    payload = { phone, url, comment, product: info.name, source: 'apteka' };
                    if (info.price) payload.price = info.price;
                    if (info.image) payload.image = info.image;
                }
            }
            const response = await fetch(CONFIG.API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (response.ok) {
                showStatus(`✅ <b>Заказ принят!</b><br><br>💊 ${result.product}`, 'success');
                formContainer.style.display = 'none';
            } else {
                showStatus(`❌ <b>Ошибка:</b><br>${result.message}`, 'error');
            }
        } catch (error) {
            console.error(error);
            showStatus(`🔌 <b>Бот не отвечает</b><br>Убедитесь, что скрипт бота запущен на этом компьютере.`, 'error');
        } finally {
            sendBtn.disabled = false;
            sendBtn.innerHTML = '🚀 Отправить в Бот';
        }
    });

    function showStatus(text, type) {
        statusDiv.innerHTML = text;
        statusDiv.className = type;
    }
});
