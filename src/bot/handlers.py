"""Telegram bot handlers for manual input and admin features."""

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, ContentType
from aiogram.filters import Command

from ..extractors import extract_phone, extract_order_number
from ..parsers import parse_pdf_bytes, parse_docx_bytes


router = Router()


def create_bot(token: str) -> tuple[Bot, Dispatcher]:
    """Create bot and dispatcher."""
    bot = Bot(token=token)
    dp = Dispatcher()
    dp.include_router(router)
    return bot, dp


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Handle /start command."""
    await message.answer(
        "👋 Бот уведомлений аптеки\n\n"
        "Отправь текст письма или PDF/DOCX — извлеку телефон и номер заказа."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    await message.answer(
        "📖 **Использование:**\n\n"
        "• Отправь текст письма от apteka.ru\n"
        "• Или прикрепи PDF/DOCX файл\n"
        "• Бот найдёт телефон и номер заказа\n\n"
        "/start - Начать\n"
        "/help - Справка",
        parse_mode="Markdown"
    )


@router.message(F.content_type == ContentType.DOCUMENT)
async def handle_document(message: Message) -> None:
    """Handle document uploads (PDF, DOCX)."""
    if not message.document:
        return
    
    filename = message.document.file_name or ""
    filename_lower = filename.lower()
    
    if not filename_lower.endswith((".pdf", ".docx")):
        await message.answer("⚠️ Поддерживаются только PDF и DOCX")
        return
    
    await message.answer("📄 Обрабатываю...")
    
    try:
        bot = message.bot
        assert bot is not None
        
        file = await bot.get_file(message.document.file_id)
        assert file.file_path is not None
        
        file_bytes = await bot.download_file(file.file_path)
        assert file_bytes is not None
        
        content = file_bytes.read()
        
        if filename_lower.endswith(".pdf"):
            text = parse_pdf_bytes(content)
        else:
            text = parse_docx_bytes(content)
        
        await send_result(message, text)
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(F.text)
async def handle_text(message: Message) -> None:
    """Handle text messages."""
    if not message.text or message.text.startswith('/'):
        return
    
    await send_result(message, message.text)


async def send_result(message: Message, text: str) -> None:
    """Extract and display phone/order from text."""
    phone = extract_phone(text)
    order = extract_order_number(text)
    
    if not phone and not order:
        await message.answer("❌ Телефон и номер заказа не найдены")
        return
    
    lines = ["📋 **Найдено:**"]
    if order:
        lines.append(f"🔢 Заказ: №{order}")
    if phone:
        lines.append(f"📱 Телефон: {phone}")
    
    if phone and order:
        lines.append("\n✅ Данные готовы для отправки")
    
    await message.answer("\n".join(lines), parse_mode="Markdown")
