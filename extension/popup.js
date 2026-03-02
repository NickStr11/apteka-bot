document.addEventListener('DOMContentLoaded', async () => {
    const phoneInput = document.getElementById('phone');
    const commentInput = document.getElementById('comment');
    const sendBtn = document.getElementById('send-btn');
    const statusDiv = document.getElementById('status');
    const formContainer = document.getElementById('form-container');

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

            if (!url || !url.includes('apteka.ru/product/')) {
                showStatus('🛑 Это не страница товара Apteka.ru', 'error');
                sendBtn.disabled = false;
                sendBtn.innerHTML = originalText;
                return;
            }

            // Send to local bot API
            const response = await fetch(CONFIG.API_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phone, url, comment })
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
