// Отправка заказа в бот по просьбе uteka.js: со страницы Ютеки (https) запрос
// к боту (http) браузер заблокирует как mixed content, из расширения — можно.
importScripts('config.js');

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || msg.type !== 'bot-order') return;
    fetch(CONFIG.API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(msg.payload),
    })
        .then(async response => {
            const data = await response.json().catch(() => ({}));
            sendResponse({ ok: response.ok, data, error: response.ok ? '' : (data.message || 'HTTP ' + response.status) });
        })
        .catch(error => sendResponse({ ok: false, error: 'бот не отвечает: ' + String(error && error.message || error) }));
    return true; // ответ асинхронный
});
