"""Telegram bot for manual order entry."""

import logging
import re
import sys
import os
from pathlib import Path
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import asyncio
from aiohttp import web
import aiohttp_cors
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config
from database.sheets import get_client, get_sheet, add_order, update_order_row, OrderRow, get_orders_by_date, update_contact_status
from extractors.phone import extract_phone
from extractors.apteka_parser import extract_product_from_url

logger = logging.getLogger(__name__)


# Authorized users
AUTHORIZED_USERS = set()


def is_authorized(user_id: int) -> bool:
    """Check if user is authorized."""
    return user_id in AUTHORIZED_USERS


def get_main_keyboard():
    """Get main menu keyboard."""
    keyboard = [
        [KeyboardButton("📝 Новый заказ")],
        [KeyboardButton("📋 Заказы сегодня"), KeyboardButton("📊 История")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_order_control_keyboard():
    """Get keyboard with OK, Delete, Edit buttons (icons only)."""
    keyboard = [
        [
            InlineKeyboardButton("✅", callback_data="confirm_order"),
            InlineKeyboardButton("❌", callback_data="delete_order"),
            InlineKeyboardButton("✏️", callback_data="edit_last_order")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    await update.message.reply_text(
        "👋 Привет! Я помогу записывать заказы.\n\n"
        "Отправь мне:\n"
        "• Текст: `79991234567 Аспирин`\n"
        "• Голосовое сообщение\n\n"
        "Или используй кнопки ниже:",
        reply_markup=get_main_keyboard(),
    )


async def process_order_text(text: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Common logic for processing order text (from text or voice)."""
    # Try to parse order
    phone = extract_phone(text)
    
    if not phone:
        await update.message.reply_text(
            "❌ Не нашёл номер телефона.\n"
            "Попробуй ещё раз: `79991234567 Аспирин`"
        )
        return
    
    # Extract product name more carefully
    from extractors.phone import PHONE_PATTERNS
    product_part = text
    for pattern in PHONE_PATTERNS:
        match = pattern.search(text)
        if match:
            # Remove only the part of text that matched the phone pattern
            start, end = match.span()
            product_part = text[:start] + " " + text[end:]
            break
            
    # Clean up common filler words/phrases from voice input
    stop_phrases = [
        "а номер телефона", "номер телефона", "номер", "телефона", "телефон",
        "на номер", "на телефон", "по номеру", "запиши", "заказ", "заказ на",
        "пожалуйста", "клиент", "звонить", "номерчик", "такс", "лекарство",
        "препарат", "добавь", "впиши", "нужен", "нужно", "смотри", 
        "на который отправить это", "отправь это все на номер", "отправь на номер", 
        "отправь на", "отправь это все", "отправь", "слушай", "давай", 
        "протестируем", "мне нужен на", "мне нужен", "мне нужна", "мне на", 
        "привет", "привет бот", "алло", "слушаю", "так", "еще", "тест", 
        "это все", "это", "все", "дозировка"
    ]
    
    # Process products
    cleaned_text = product_part
    
    # 1. Clean up stop phrases first
    sorted_stop_phrases = sorted(stop_phrases, key=len, reverse=True)
    for phrase in sorted_stop_phrases:
        cleaned_text = re.sub(r'\b' + re.escape(phrase) + r'\b', "", cleaned_text, flags=re.IGNORECASE)
    
    # 2. Smart Splitting logic
    # List of known units to avoid splitting between number and unit
    units_pattern = r'(пач\w+|упак\w+|шт\w+|мг|гр|мл|пак\w+|таб\w+|капс\w+|флак\w+|амп\w+|пластинк\w+)'
    
    # First, protect number+unit combinations by temporarily replacing space with underscore
    cleaned_text = re.sub(
        r'(\d+)\s+' + units_pattern, 
        r'\1_\2', 
        cleaned_text, 
        flags=re.IGNORECASE
    )
    
    # Split AFTER a "number_unit" or just "number" if followed by another word
    # (that isn't a known separator or stop word we haven't removed)
    cleaned_text = re.sub(
        r'(\d+(?:_\w+)?)\s+([а-яёA-Z]{3,})', 
        r'\1 | \2', 
        cleaned_text, 
        flags=re.IGNORECASE
    )
    
    # 3. Split by all separators
    separators = [
        r'\s+и\s+', 
        r'\s+еще\s+', 
        r'(?<!\d),(?!\d)', 
        r'\s+а\s+также\s+', 
        r'\s+а\s+',
        r'\|'
    ]
    combined_sep = '|'.join(separators)
    items = re.split(combined_sep, cleaned_text, flags=re.IGNORECASE)
    
    # Clean up each item and format as bulleted list
    final_items = []
    for item in items:
        # Restore spaces in number+unit
        item = item.replace('_', ' ')
        # Final trim and clean
        item = re.sub(r'\s+', ' ', item).strip(' ,.:;-+|')
        # Remove any remaining stop words at the start/end
        for sw in ["мне", "на", "для", "и", "а"]:
            item = re.sub(r'^\b' + sw + r'\b', "", item, flags=re.IGNORECASE).strip()
            item = re.sub(r'\b' + sw + r'\b$', "", item, flags=re.IGNORECASE).strip()
            
        if item and len(item) > 1:
            final_items.append(f"• {item}")
            
    if not final_items:
        await update.message.reply_text(
            "❌ Не нашёл название препарата.\n"
            "Попробуй ещё раз: `79991234567 Аспирин`"
        )
        return
    
    product = "\n".join(final_items)
    
    # Save order
    sheet = context.bot_data['sheet']
    is_editing = context.user_data.get('is_editing', False)
    last_row = context.user_data.get('last_row_index')
    
    order = OrderRow(
        date=datetime.now().strftime("%d.%m.%Y %H:%M"),
        order_number="Ручной",
        phone=phone,
        products=product,
        total=0,
        wa_status="",
        sms_status="",
        sent="",
        note="Telegram бот (исправлен)" if is_editing else "Telegram бот",
    )
    
    try:
        if is_editing and last_row:
            update_order_row(sheet, last_row, order)
            context.user_data['is_editing'] = False
            await update.message.reply_text(
                f"🔄 Заказ исправлен!\n\n"
                f"📞 {phone}\n"
                f"💊 {product}",
                reply_markup=get_order_control_keyboard(),
            )
        else:
            row_index = add_order(sheet, order)
            context.user_data['last_row_index'] = row_index
            await update.message.reply_text(
                f"✅ Заказ сохранён!\n\n"
                f"📞 {phone}\n"
                f"💊 {product}",
                reply_markup=get_order_control_keyboard(),
            )
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {e}",
            reply_markup=get_main_keyboard(),
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        return
    
    text = update.message.text
    
    # Check for button presses first
    if text == "📝 Новый заказ":
        await update.message.reply_text(
            "Отправь номер телефона и название препарата:\n"
            "Например: `79991234567 Аспирин`"
        )
        return
    
    if text == "📋 Заказы сегодня":
        await show_today_orders(update, context)
        return
    
    if text == "📊 История":
        await show_history(update, context)
        return
    
    # Check if we are waiting for a phone number for a previous link
    if context.user_data.get('waiting_for_phone_for_product'):
        product = context.user_data.pop('waiting_for_phone_for_product')
        phone = extract_phone(text)
        if phone:
            # Manually process the order with extracted phone and stored product
            await save_order_to_sheet(phone, product, update, context)
        else:
            # Re-store product and ask again
            context.user_data['waiting_for_phone_for_product'] = product
            await update.message.reply_text(
                "❌ Не похоже на номер телефона. Пришли номер для заказа препарата:\n"
                f"💊 {product}"
            )
        return

    # Check for Apteka.ru links
    if 'apteka.ru/product/' in text:
        status_msg = await update.message.reply_text("🔎 Извлекаю данные по ссылке...")
        product = extract_product_from_url(text)
        if product:
            context.user_data['waiting_for_phone_for_product'] = product
            await status_msg.edit_text(
                f"📦 Нашёл: `{product}`\n\n"
                "Теперь пришли номер телефона клиента, на который оформить заказ."
            )
        else:
            await status_msg.edit_text("❌ Не удалось извлечь название по ссылке. Попробуй продиктовать голосом.")
        return
    
    await process_order_text(text, update, context)


async def save_order_to_sheet(phone: str, product: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Refactored helper to save order to sheet and show controls."""
    sheet = context.bot_data['sheet']
    is_editing = context.user_data.get('is_editing', False)
    last_row = context.user_data.get('last_row_index')
    
    order = OrderRow(
        date=datetime.now().strftime("%d.%m.%Y %H:%M"),
        order_number="Ручной",
        phone=phone,
        products=product,
        total=0,
        wa_status="",
        sms_status="",
        sent="",
        note="Telegram бот (исправлен)" if is_editing else "Telegram бот",
    )
    
    try:
        if is_editing and last_row:
            update_order_row(sheet, last_row, order)
            context.user_data['is_editing'] = False
            await update.message.reply_text(
                f"🔄 Заказ исправлен!\n\n"
                f"📞 {phone}\n"
                f"💊 {product}",
                reply_markup=get_order_control_keyboard(),
            )
        else:
            row_index = add_order(sheet, order)
            context.user_data['last_row_index'] = row_index
            await update.message.reply_text(
                f"✅ Заказ сохранён!\n\n"
                f"📞 {phone}\n"
                f"💊 {product}",
                reply_markup=get_order_control_keyboard(),
            )
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        await update.message.reply_text(
            f"❌ Ошибка: {e}",
            reply_markup=get_main_keyboard(),
        )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages."""
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        return
    
    config = context.bot_data['config']
    if not config.yandex_speechkit_api_key:
        await update.message.reply_text("❌ Голосовой ввод не настроен (нет API ключа)")
        return
    
    status_msg = await update.message.reply_text("🎤 Слушаю...")
    
    try:
        # Download voice file
        voice_file = await update.message.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
        
        # Recognize text
        from bot.speech_kit import YandexSpeechKit
        sk = YandexSpeechKit(config.yandex_speechkit_api_key)
        text = sk.speech_to_text(bytes(voice_bytes))
        
        if not text:
            await status_msg.edit_text("❌ Не удалось распознать речь")
            return
        
        await status_msg.edit_text(f"📝 Распознано: `{text}`")
        
        # Check if we are waiting for a phone number for a previous link
        if context.user_data.get('waiting_for_phone_for_product'):
            product = context.user_data.pop('waiting_for_phone_for_product')
            phone = extract_phone(text)
            if phone:
                await save_order_to_sheet(phone, product, update, context)
            else:
                # Re-store product and ask again
                context.user_data['waiting_for_phone_for_product'] = product
                await update.message.reply_text(
                    "❌ Не нашёл номер телефона в голосовом сообщении. Пришли номер для заказа препарата:\n"
                    f"💊 {product}"
                )
            return

        # Process recognized text as a standard order
        await process_order_text(text, update, context)
        
    except Exception as e:
        logger.error(f"Ошибка голосового ввода: {e}")
        await status_msg.edit_text(f"❌ Ошибка обработки голоса: {e}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks."""
    from database.sheets import delete_order_row
    
    query = update.callback_query
    
    # Check if this is a contact callback - handle it first
    if query.data.startswith("contact_"):
        await handle_contact_callback(update, context)
        return
    
    await query.answer()
    
    last_row = context.user_data.get('last_row_index')
    sheet = context.bot_data['sheet']
    
    if query.data == "confirm_order":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("🚀 Принято!")
        
    elif query.data == "delete_order":
        if last_row:
            try:
                delete_order_row(sheet, last_row)
                context.user_data['last_row_index'] = None
                await query.edit_message_reply_markup(reply_markup=None)
                await query.message.reply_text("🗑️ Заказ удалён из таблицы.")
            except Exception as e:
                await query.message.reply_text(f"❌ Ошибка удаления: {e}")
        else:
            await query.message.reply_text("❌ Не нашел заказ для удаления.")
            
    elif query.data == "edit_last_order":
        context.user_data['is_editing'] = True
        await query.message.reply_text(
            "Принято! Отправь правильные данные (текстом или голосом), "
            "и я заменю ими последнюю запись."
        )


async def show_today_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show today's orders with contact action buttons."""
    sheet = context.bot_data['sheet']
    
    # Get today's date
    today = datetime.now().strftime("%d.%m.%Y")
    orders = get_orders_by_date(sheet, today)
    
    if not orders:
        await update.message.reply_text("📭 Сегодня заказов нет")
        return
    
    await update.message.reply_text(f"📅 Заказы за {today} ({len(orders)} шт.):\n\nНажмите для действий:")
    
    # Send each order as a separate message with buttons
    for row_num, order in orders:
        status_icon = order.contact_status if order.contact_status else "❌ Не обработан"
        
        text = (
            f"📦 #{order.order_number}\n"
            f"💊 {order.products}\n"
            f"📞 {order.phone}\n"
            f"📅 {order.date}\n"
            f"📋 {status_icon}"
        )
        
        # If already processed, show reset button; otherwise show action buttons
        if "❌" in status_icon:
            keyboard = get_contact_keyboard(row_num)
        else:
            keyboard = get_reset_keyboard(row_num)
        
        await update.message.reply_text(text, reply_markup=keyboard)


async def api_handle_order(request):
    """Handle incoming order from Chrome extension."""
    try:
        data = await request.json()
        phone = data.get('phone')
        url = data.get('url')
        
        if not phone or not url:
            return web.json_response({'status': 'error', 'message': 'Missing phone or url'}, status=400)
            
        logger.info(f"🚀 API Order received: {phone} - {url}")
        
        # Extract product
        product = extract_product_from_url(url)
        if not product:
            return web.json_response({'status': 'error', 'message': 'Could not parse product from URL'}, status=400)
            
        # Get sheet and config from bot_data
        app_tg = request.app['bot_app']
        sheet = app_tg.bot_data['sheet']
        config = app_tg.bot_data['config']
        
        # Create order
        order = OrderRow(
            date=datetime.now().strftime("%d.%m.%Y %H:%M"),
            order_number="Chrome Extension",
            phone=phone,
            products=product,
            total=0,
            wa_status="",
            sms_status="",
            sent="",
            note="Chrome Расширение",
        )
        
        # Save to Google Sheets
        row_index = add_order(sheet, order)
        
        # Notify ADMIN in Telegram
        admin_id = int(config.telegram_admin_id.split(',')[0].strip())
        await app_tg.bot.send_message(
            chat_id=admin_id,
            text=f"🌐 **Новый заказ из браузера!**\n\n"
                 f"📞 {phone}\n"
                 f"💊 {product}\n\n"
                 f"Записано в таблицу (строка {row_index})",
            parse_mode='Markdown'
        )
        
        return web.json_response({'status': 'ok', 'product': product})
        
    except Exception as e:
        logger.error(f"❌ API Error: {e}")
        return web.json_response({'status': 'error', 'message': str(e)}, status=500)


async def start_web_server(app_tg):
    """Start the aiohttp web server."""
    app_web = web.Application()
    app_web['bot_app'] = app_tg
    
    # Setup CORS
    cors = aiohttp_cors.setup(app_web, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
            allow_methods="*",
        )
    })
    
    resource = app_web.router.add_resource("/api/order")
    cors.add(resource.add_route("POST", api_handle_order))
    
    runner = web.AppRunner(app_web)
    await runner.setup()
    
    # Use PORT from env (for Cloud hosting) or default to 5000
    port = int(os.environ.get('PORT', 5000))
    host = '0.0.0.0' # Mandatory for most cloud providers
    
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(f"🌐 API сервер запущен на {host}:{port}")


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show order history."""
    sheet = context.bot_data['sheet']
    
    # Get last 20 orders
    all_values = sheet.get_all_values()
    recent = all_values[-20:]  # Last 20 rows
    
    if len(recent) <= 1:  # Only header
        await update.message.reply_text("📭 История пуста")
        return
    
    message = "📊 История заказов (последние 20)\n\n"
    for row in reversed(recent[1:]):  # Skip header, reverse order
        if len(row) >= 4:
            message += f"• {row[0]} — {row[2]} — {row[3]}\n"
    
    await update.message.reply_text(message)


def get_contact_keyboard(row_number: int):
    """Get keyboard with contact action buttons."""
    keyboard = [
        [
            InlineKeyboardButton("📞", callback_data=f"contact_call_{row_number}"),
            InlineKeyboardButton("💬", callback_data=f"contact_sms_{row_number}"),
            InlineKeyboardButton("📱", callback_data=f"contact_wa_{row_number}"),
        ],
        [
            InlineKeyboardButton("✈️ TG", callback_data=f"contact_tg_{row_number}"),
            InlineKeyboardButton("🟦 Max", callback_data=f"contact_max_{row_number}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_reset_keyboard(row_number: int):
    """Get keyboard with reset button."""
    keyboard = [
        [InlineKeyboardButton("↩️ Сбросить", callback_data=f"contact_reset_{row_number}")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show yesterday's orders with contact action buttons."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Доступ запрещён")
        return
    
    sheet = context.bot_data['sheet']
    
    # Get yesterday's date
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")
    orders = get_orders_by_date(sheet, yesterday)
    
    if not orders:
        await update.message.reply_text(f"📭 Заказов за {yesterday} нет")
        return
    
    await update.message.reply_text(f"📅 Заказы за {yesterday}:\n\nНажмите на заказ для действий:")
    
    # Send each order as a separate message with buttons
    for row_num, order in orders:
        status_icon = order.contact_status if order.contact_status else "❌ Не обработан"
        
        text = (
            f"📦 #{order.order_number}\n"
            f"💊 {order.products}\n"
            f"📞 {order.phone}\n"
            f"📅 {order.date}\n"
            f"📋 {status_icon}"
        )
        
        # If already processed, show reset button; otherwise show action buttons
        if "❌" in status_icon:
            keyboard = get_contact_keyboard(row_num)
        else:
            keyboard = get_reset_keyboard(row_num)
        
        await update.message.reply_text(text, reply_markup=keyboard)


async def handle_contact_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle contact action button press."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    sheet = context.bot_data['sheet']
    
    if not data.startswith("contact_"):
        return False  # Not a contact callback
    
    parts = data.split("_")
    action = parts[1]  # call, sms, wa, tg, max, reset
    row_num = int(parts[2])
    
    now = datetime.now().strftime("%d.%m %H:%M")
    
    status_map = {
        "call": f"📞 Позвонил ({now})",
        "sms": f"💬 SMS ({now})",
        "wa": f"📱 WhatsApp ({now})",
        "tg": f"✈️ Telegram ({now})",
        "max": f"🟦 Max ({now})",
        "reset": "❌ Не обработан",
    }
    
    new_status = status_map.get(action, "❌ Не обработан")
    
    # Update in Google Sheets
    update_contact_status(sheet, row_num, new_status)
    
    # Extract phone from message
    old_text = query.message.text
    lines = old_text.split("\n")
    phone = ""
    for line in lines:
        if line.startswith("📞"):
            phone = line.replace("📞 ", "").replace("+", "").replace(" ", "").strip()
            break
    
    # Clean phone for links (digits only)
    phone_digits = ''.join(c for c in phone if c.isdigit())
    
    # Replace the status line
    new_lines = []
    for line in lines:
        if line.startswith("📋"):
            new_lines.append(f"📋 {new_status}")
        else:
            new_lines.append(line)
    
    new_text = "\n".join(new_lines)
    
    # Update keyboard
    if action == "reset":
        keyboard = get_contact_keyboard(row_num)
    else:
        keyboard = get_reset_keyboard(row_num)
    
    await query.edit_message_text(new_text, reply_markup=keyboard)
    
    # Send clickable link if action is not reset
    if action != "reset" and phone_digits:
        link_map = {
            "call": f"tel:+{phone_digits}",
            "sms": f"sms:+{phone_digits}",
            "wa": f"https://wa.me/{phone_digits}",
            "tg": f"https://t.me/+{phone_digits}",
            "max": f"https://max.ru/im?phone={phone_digits}",
        }
        link = link_map.get(action, "")
        action_name = {
            "call": "📞 Позвонить",
            "sms": "💬 Отправить SMS",
            "wa": "📱 Открыть WhatsApp",
            "tg": "✈️ Открыть Telegram",
            "max": "🟦 Открыть Max",
        }.get(action, "")
        
        if link:
            await query.message.reply_text(
                f"✅ Статус: {new_status}\n\n"
                f"☎️ Номер: `+{phone_digits}`\n\n"
                f"👉 [{action_name}]({link})",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
    
    return True


def main():
    """Run the bot."""
    # Load config
    config = load_config()
    
    # Setup authorized users
    global AUTHORIZED_USERS
    admin_ids = [int(id.strip()) for id in config.telegram_admin_id.split(',') if id.strip()]
    AUTHORIZED_USERS = set(admin_ids)
    
    # Initialize Google Sheets
    client = get_client(config.google_credentials_path)
    sheet = get_sheet(client)
    
    # Create application
    app = Application.builder().token(config.telegram_bot_token).build()
    
    # Store config and sheet in bot_data
    app.bot_data['config'] = config
    app.bot_data['sheet'] = sheet
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Start bot and web server
    logger.info("🤖 Бот запускается...")
    
    async def run_all():
        # Start API server
        await start_web_server(app)
        
        # Start bot polling
        async with app:
            await app.initialize()
            await app.start()
            logger.info("🤖 Бот запущен!")
            await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
            
            # Keep running until interrupted
            while True:
                await asyncio.sleep(3600)

    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен.")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    main()
