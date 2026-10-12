document.addEventListener('DOMContentLoaded', async () => {
    const phoneInput = document.getElementById('phone');
    const commentInput = document.getElementById('comment');
    const sendBtn = document.getElementById('send-btn');
    const statusDiv = document.getElementById('status');
    const formContainer = document.getElementById('form-container');

    // Ютека: название и цену (Фарматек +5%) берём из данных панели uteka.js —
    // бот на VPS страницу Ютеки скачать не может
    const UTEKA_MARKUP = 0.05;
    const utekaPreview = document.getElementById('uteka-preview');
    let utekaOrder = null;   // { product, price } для отправки
    let utekaBlocked = '';   // причина, почему с этой карточки отправлять нельзя

    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const utekaProductId = utekaProductIdFromUrl(activeTab && activeTab.url);
    if (utekaProductId) await prepareUteka(activeTab, utekaProductId);

    function utekaProductIdFromUrl(url) {
        const m = String(url || '').match(/^https:\/\/([a-z0-9-]+\.)?uteka\.ru\/product\/[^/?#]*?-(\d+)\/?(?:[?#]|$)/);
        return m ? Number(m[2]) : null;
    }

    async function prepareUteka(tab, productId) {
        const data = await chrome.storage.local.get(['utekaProd:' + productId, 'utekaTitles']);
        const entry = data['utekaProd:' + productId];
        const title = (data.utekaTitles || {})[productId] || String(tab.title || '').split(' – ')[0].trim();
        const offers = (entry && entry.offers) || [];
        utekaPreview.style.display = 'block';
        if (!offers.length) {
            utekaBlocked = entry
                ? 'В Фарматек этот товар сейчас не привезут — отправлять нечего.'
                : 'Цены Фарматека ещё не загрузились. Дождись зелёной панели на странице и открой окно снова.';
            utekaPreview.className = 'warn';
            utekaPreview.innerHTML = `💊 ${escapeHtml(title)}<br><br>⚠️ ${utekaBlocked}`;
            return;
        }
        const best = offers[0]; // offers отсортированы по цене
        const clientPrice = Math.ceil(best.price * (1 + UTEKA_MARKUP));
        utekaOrder = { product: title, price: clientPrice };
        utekaPreview.className = '';
        utekaPreview.innerHTML = `💊 ${escapeHtml(title)}<br>
            <span class="price">${clientPrice.toLocaleString('ru-RU')} ₽</span>
            — клиенту (${escapeHtml(best.supplier)} ${best.price.toLocaleString('ru-RU')} ₽ +5%)`;
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

            const isUteka = !!utekaProductIdFromUrl(url);
            if (isUteka && !utekaOrder) {
                showStatus(`🛑 ${utekaBlocked || 'Нет цены Фарматека для этого товара'}`, 'error');
                sendBtn.disabled = false;
                sendBtn.innerHTML = originalText;
                return;
            }
            if (!isUteka && (!url || !url.includes('apteka.ru/product/'))) {
                showStatus('🛑 Это не страница товара Apteka.ru или Ютеки', 'error');
                sendBtn.disabled = false;
                sendBtn.innerHTML = originalText;
                return;
            }

            // Send to local bot API
            const payload = isUteka
                ? { phone, url, comment, product: utekaOrder.product, price: utekaOrder.price, source: 'uteka' }
                : { phone, url, comment };
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
