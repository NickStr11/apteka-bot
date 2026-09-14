"""Offline PTB dispatcher/HTTP transport regression: no real Telegram or Sheets calls."""
import asyncio
import json
import logging
import sys
import unittest
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs

import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TimedOut, NetworkError, BadRequest
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters
from telegram.request import HTTPXRequest

sys.path.insert(0, str(Path(__file__).parent))
from test_order_resilience import load_functions


class DispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_blocked_delivery_does_not_block_next_order_or_duplicate_confirmation(self):
        blocked = asyncio.Event()
        started = asyncio.Event()
        calls = []
        edited = set()

        async def transport(request):
            method = request.url.path.rsplit('/', 1)[-1]
            params = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            calls.append((method, params))
            if method == 'getMe':
                result = {'id': 99, 'is_bot': True, 'first_name': 'Test', 'username': 'test_bot'}
            else:
                if method == 'sendMessage' and params.get('text', '').endswith('First'):
                    started.set()
                    await blocked.wait()
                if method == 'answerCallbackQuery':
                    # Same wrapped error as the production connection timeout.
                    raise httpx.ConnectTimeout('offline injected timeout', request=request)
                if method == 'editMessageText':
                    key = (params['message_id'], params['text'])
                    if key in edited:
                        return httpx.Response(400, json={'ok': False, 'error_code': 400, 'description': 'Bad Request: message is not modified'})
                    edited.add(key)
                result = {'message_id': int(params.get('message_id', 10)), 'date': 1,
                          'chat': {'id': 1, 'type': 'private'}, 'text': params.get('text', '')}
            return httpx.Response(200, json={'ok': True, 'result': result})

        req = HTTPXRequest(httpx_kwargs={'transport': httpx.MockTransport(transport)})
        app = Application.builder().token('99:offline_test').request(req).build()
        tasks = []
        original_create_task = app.create_task
        def track(coro, **kwargs):
            task = original_create_task(coro, **kwargs)
            tasks.append(task)
            return task
        # Context delegates to this facade while real dispatcher/user_data remain PTB-owned.
        ns = dict(asyncio=asyncio, uuid=uuid, datetime=datetime, logger=logging.getLogger('test'),
                  TimedOut=TimedOut, NetworkError=NetworkError, BadRequest=BadRequest,
                  InlineKeyboardButton=InlineKeyboardButton, InlineKeyboardMarkup=InlineKeyboardMarkup,
                  get_main_keyboard=lambda: None, OrderRow=lambda **kw: SimpleNamespace(**kw),
                  add_order=object(), update_order_row=object(), run_sheet_call=AsyncMock(side_effect=[42, 43]))
        load_functions('src/bot/telegram_bot.py', {'save_order_to_sheet', 'get_order_control_keyboard',
                       'saved_order_keyboard', 'schedule_reply', 'notify_order_saved', 'send_telegram_with_retry',
                       'answer_callback_safely', 'confirm_saved_message', 'schedule_confirmation'}, ns)
        async def save(update, context):
            facade = SimpleNamespace(application=SimpleNamespace(create_task=track),
                                     user_data=context.user_data, bot_data=context.bot_data)
            await ns['save_order_to_sheet']('70000000000', update.message.text, update, facade)
        async def confirm(update, context):
            facade = SimpleNamespace(application=SimpleNamespace(create_task=track), bot_data=context.bot_data)
            ns['schedule_confirmation'](facade, update.callback_query)
        app.bot_data['sheet'] = object()
        app.add_handler(MessageHandler(filters.TEXT, save))
        app.add_handler(CallbackQueryHandler(confirm))
        errors = []
        async def error(update, context):
            errors.append(context.error)
        app.add_error_handler(error)
        def message_update(uid, text):
            return Update.de_json({'update_id': uid, 'message': {'message_id': uid, 'date': 1,
                'from': {'id': 1, 'is_bot': False, 'first_name': 'Test'},
                'chat': {'id': 1, 'type': 'private'}, 'text': text}}, app.bot)
        def callback_update(uid):
            return Update.de_json({'update_id': uid, 'callback_query': {'id': str(uid), 'chat_instance': 'offline',
                'data': 'confirm_order', 'from': {'id': 1, 'is_bot': False, 'first_name': 'Test'},
                'message': {'message_id': 10, 'date': 1, 'chat': {'id': 1, 'type': 'private'},
                            'text': 'Saved'}}}, app.bot)
        async with app:
            await app.start()
            try:
                await asyncio.wait_for(app.process_update(message_update(1, 'First')), 1)
                await asyncio.wait_for(started.wait(), 1)
                await asyncio.wait_for(app.process_update(message_update(2, 'Second')), 1)
                self.assertEqual(ns['run_sheet_call'].await_count, 2)
                self.assertEqual(app.user_data[1]['last_row_index'], 43)
                await app.process_update(callback_update(3))
                await app.process_update(callback_update(4))
                blocked.set()
                await asyncio.gather(*tasks)
                self.assertEqual(len([c for c in calls if c[0] == 'editMessageText']), 1)
                await app.process_update(callback_update(5))
                await asyncio.gather(*tasks)
                self.assertEqual(len(edited), 1)
                self.assertEqual(len([c for c in calls if c[0] == 'sendMessage']), 2)
                self.assertFalse(errors)
            finally:
                blocked.set()
                await app.stop()


if __name__ == '__main__':
    unittest.main()
