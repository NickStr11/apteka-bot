"""Offline regression checks using production function bodies, without service imports."""
import ast
import asyncio
import logging
import re
import threading
import unittest
import uuid
import inspect
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class DeliveryNetworkError(Exception):
    pass


class DeliveryBadRequest(DeliveryNetworkError):
    pass


class DeliveryTimedOut(DeliveryNetworkError):
    pass


def load_functions(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    assert len(nodes) == len(names)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), path, "exec"), namespace)
    return namespace


class ResilienceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tasks = []
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.delete_order = Mock()
        modules = patch.dict(sys.modules, {"database": SimpleNamespace(), "database.sheets": SimpleNamespace(delete_order_row=self.delete_order)})
        modules.start()
        self.addCleanup(modules.stop)
        self.ns = dict(asyncio=asyncio, partial=partial, _SHEETS_EXECUTOR=self.executor, re=re, logger=Mock(), datetime=datetime)
        load_functions("src/database/sheets.py", {"run_sheet_call", "add_order"}, self.ns)
        self.ns.update(TimedOut=DeliveryTimedOut, NetworkError=DeliveryNetworkError, BadRequest=DeliveryBadRequest, uuid=uuid, is_authorized=lambda user_id: True)
        load_functions("src/bot/telegram_bot.py", {"send_telegram_with_retry", "notify_order_saved", "notify_browser_order", "api_handle_order", "save_order_to_sheet", "handle_text", "schedule_reply", "saved_order_keyboard", "answer_callback_safely", "confirm_saved_message", "schedule_confirmation", "handle_callback", "get_order_control_keyboard"}, self.ns)
        self.ns.update(OrderRow=lambda **kwargs: SimpleNamespace(**kwargs), get_main_keyboard=lambda: "main", InlineKeyboardButton=lambda text, **kwargs: SimpleNamespace(text=text, **kwargs), InlineKeyboardMarkup=lambda rows: rows)
        self.order = SimpleNamespace(date="date", order_number="order", phone="phone", products="product", total=0, wa_status="", sms_status="", sent="", note="", contact_status="")

    def context(self, user_data=None):
        def track(coro):
            task = asyncio.create_task(coro)
            self.tasks.append(task)
            return task
        return SimpleNamespace(bot_data={"sheet": object()}, user_data=user_data or {}, application=SimpleNamespace(create_task=track))

    async def drain(self):
        await asyncio.gather(*self.tasks)

    def callback(self, data="confirm_order", text="Saved", message_id=1):
        message = SimpleNamespace(chat_id=1, message_id=message_id, text=text, reply_text=AsyncMock())
        query = SimpleNamespace(data=data, message=message, answer=AsyncMock(), edit_message_text=AsyncMock())
        return SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(id=1))

    def tearDown(self):
        self.executor.shutdown(wait=True)

    async def test_append_uses_own_response_and_never_reads_table(self):
        sheet = Mock()
        sheet.append_row.side_effect = [{"updates": {"updatedRange": "'Заказы'!A42:J42"}}, {"updates": {"updatedRange": "'Заказы'!A43:J43"}}]
        rows = await asyncio.gather(*(self.ns["run_sheet_call"](self.ns["add_order"], sheet, self.order) for _ in range(2)))
        self.assertEqual(rows, [42, 43])
        sheet.get_all_values.assert_not_called()

    async def test_missing_append_metadata_preserves_success(self):
        for response in (None, {}, {"updates": None}, {"updates": {"updatedRange": 4}}, {"updates": {"updatedRange": "bad"}}):
            sheet = Mock()
            sheet.append_row.return_value = response
            self.assertIsNone(self.ns["add_order"](sheet, self.order))
            sheet.append_row.assert_called_once()
            sheet.get_all_values.assert_not_called()

    async def test_sheet_worker_does_not_block_loop_and_serializes_calls(self):
        started, release, second_started = threading.Event(), threading.Event(), threading.Event()
        def first():
            started.set()
            release.wait(2)
            return 1
        tasks = [asyncio.create_task(self.ns["run_sheet_call"](first))]
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(.005)
            self.assertTrue(started.is_set())
            tasks.append(asyncio.create_task(self.ns["run_sheet_call"](second_started.set)))
            await asyncio.sleep(.02)
            self.assertFalse(second_started.is_set())
            self.assertFalse(tasks[0].done())
        finally:
            release.set()
            await asyncio.gather(*tasks)
        self.assertTrue(second_started.is_set())

    async def test_browser_returns_before_notification_and_catches_delivery_failure(self):
        tasks = []
        blocked = asyncio.Event()
        async def send(**kwargs):
            await blocked.wait()
            raise TimeoutError("Telegram unavailable")
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=send))
        app = SimpleNamespace(bot=bot, bot_data={"sheet": object(), "config": SimpleNamespace(telegram_admin_id="1")})
        def track(coro):
            task = asyncio.create_task(coro)
            tasks.append(task)
            return task
        app.create_task = track
        self.ns.update(extract_product_with_price=lambda url: SimpleNamespace(name="Product", price=1), add_order=Mock(return_value=42), web=SimpleNamespace(json_response=lambda data, status=200: (status, data)))
        request = SimpleNamespace(json=AsyncMock(return_value={"phone": "9000000000", "url": "https://apteka.ru/product/example/"}), app={"bot_app": app})
        response = await asyncio.wait_for(self.ns["api_handle_order"](request), timeout=1)
        self.assertEqual(response[0], 200)
        self.assertEqual(response[1]["status"], "ok")
        self.ns["add_order"].assert_called_once()
        self.assertEqual(len(tasks), 1)
        self.assertFalse(tasks[0].done())
        blocked.set()
        await asyncio.gather(*tasks)
        self.ns["logger"].exception.assert_called_once()

    async def test_uteka_order_uses_product_and_price_from_extension(self):
        tasks = []
        sent = AsyncMock()
        app = SimpleNamespace(bot=SimpleNamespace(send_message=sent), bot_data={"sheet": object(), "config": SimpleNamespace(telegram_admin_id="1")})
        def track(coro):
            task = asyncio.create_task(coro)
            tasks.append(task)
            return task
        app.create_task = track
        parser = Mock(side_effect=AssertionError("Uteka page must not be fetched"))
        self.ns.update(extract_product_with_price=parser, add_order=Mock(return_value=42), web=SimpleNamespace(json_response=lambda data, status=200: (status, data)))
        payload = {"phone": "89181234567", "comment": "Оля", "url": "https://krasnodar.uteka.ru/product/ksefomielin-392534/",
                   "product": "КСЕФОмиелин, таблетки, 30 шт.", "price": 1214}
        request = SimpleNamespace(json=AsyncMock(return_value=payload), app={"bot_app": app})
        response = await asyncio.wait_for(self.ns["api_handle_order"](request), timeout=1)
        await asyncio.gather(*tasks)
        self.assertEqual(response, (200, {"status": "ok", "product": "КСЕФОмиелин, таблетки, 30 шт."}))
        parser.assert_not_called()
        order = self.ns["add_order"].call_args.args[1]
        self.assertEqual((order.phone, order.products, order.total, order.note),
                         ("79181234567", "КСЕФОмиелин, таблетки, 30 шт.", 1214.0, "🌐 Ютека · Оля"))
        self.assertIn("с Ютеки", sent.call_args.kwargs["text"])

        self.ns["add_order"].reset_mock()
        request = SimpleNamespace(json=AsyncMock(return_value={"phone": "9181234567", "url": payload["url"]}), app={"bot_app": app})
        response = await asyncio.wait_for(self.ns["api_handle_order"](request), timeout=1)
        self.assertEqual(response[0], 400)
        self.ns["add_order"].assert_not_called()

    async def test_browser_blocked_parser_leaves_event_loop_responsive(self):
        started, release = threading.Event(), threading.Event()
        notifications = []
        def parse(url):
            started.set()
            release.wait(2)
            return SimpleNamespace(name="Product", price=1)
        def track(coro):
            task = asyncio.create_task(coro)
            notifications.append(task)
            return task
        app = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()), bot_data={"sheet": object(), "config": SimpleNamespace(telegram_admin_id="1")}, create_task=track)
        self.ns.update(extract_product_with_price=parse, add_order=Mock(return_value=42), web=SimpleNamespace(json_response=lambda data, status=200: (status, data)))
        request = SimpleNamespace(json=AsyncMock(return_value={"phone": "9000000000", "url": "https://apteka.ru/product/example/"}), app={"bot_app": app})
        task = asyncio.create_task(self.ns["api_handle_order"](request))
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(.005)
            self.assertTrue(started.is_set())
            # This independent tick must complete while parser I/O is blocked.
            tick = asyncio.create_task(asyncio.sleep(.01, result="responsive"))
            self.assertEqual(await tick, "responsive")
            self.assertFalse(task.done())
            self.ns["add_order"].assert_not_called()
        finally:
            release.set()
            response = await task
            await asyncio.gather(*notifications)
        self.assertEqual(response[0], 200)

    async def test_browser_schedule_failure_still_returns_saved(self):
        app = SimpleNamespace(bot=object(), bot_data={"sheet": object(), "config": SimpleNamespace(telegram_admin_id="1")}, create_task=Mock(side_effect=RuntimeError("stopping")))
        self.ns.update(extract_product_with_price=lambda url: SimpleNamespace(name="Product", price=1), add_order=Mock(return_value=42), web=SimpleNamespace(json_response=lambda data, status=200: (status, data)))
        request = SimpleNamespace(json=AsyncMock(return_value={"phone": "9000000000", "url": "https://apteka.ru/product/example/"}), app={"bot_app": app})
        response = await self.ns["api_handle_order"](request)
        self.assertEqual(response[0], 200)
        self.ns["add_order"].assert_called_once()
        self.ns["logger"].exception.assert_called_once()

    async def test_manual_saved_order_does_not_emit_save_error_after_reply_timeout(self):
        self.ns["OrderRow"] = lambda **kwargs: SimpleNamespace(**kwargs)
        self.ns["add_order"] = Mock(return_value=None)
        message = SimpleNamespace(reply_text=AsyncMock(side_effect=TimeoutError("Telegram unavailable")))
        context = self.context({"last_row_index": 99})
        await self.ns["save_order_to_sheet"]("70000000000", "Product", SimpleNamespace(message=message), context)
        await self.drain()
        self.ns["add_order"].assert_called_once()
        message.reply_text.assert_awaited_once()
        self.assertIn("Заказ сохранён", message.reply_text.call_args.args[0])
        self.assertEqual(message.reply_text.call_args.kwargs["reply_markup"], "main")
        self.assertIsNone(context.user_data["last_row_index"])
        self.ns["logger"].error.assert_not_called()

    async def test_confirmation_retries_without_writing_order_twice(self):
        self.ns["asyncio"] = SimpleNamespace(sleep=AsyncMock())
        self.ns["run_sheet_call"] = AsyncMock(return_value=42)
        message = SimpleNamespace(reply_text=AsyncMock(side_effect=[DeliveryTimedOut(), "delivered"]))
        context = self.context()
        await self.ns["save_order_to_sheet"]("70000000000", "Product", SimpleNamespace(message=message), context)
        await self.drain()
        self.ns["run_sheet_call"].assert_awaited_once()
        self.assertEqual(message.reply_text.await_count, 2)
        self.assertEqual(message.reply_text.call_args_list[0], message.reply_text.call_args_list[1])
        self.assertEqual(context.user_data["last_row_index"], 42)
        self.ns["logger"].exception.assert_not_called()

    async def test_delivery_retries_are_bounded(self):
        sleep = AsyncMock()
        self.ns["asyncio"] = SimpleNamespace(sleep=sleep)
        send = AsyncMock(side_effect=DeliveryTimedOut())
        with self.assertRaises(DeliveryTimedOut):
            await self.ns["send_telegram_with_retry"](send, "text")
        self.assertEqual(send.await_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])

    async def test_delivery_does_not_retry_permanent_error_or_cancellation(self):
        for error in (ValueError("invalid message"), asyncio.CancelledError()):
            send = AsyncMock(side_effect=error)
            with self.assertRaises(type(error)):
                await self.ns["send_telegram_with_retry"](send, "text")
            send.assert_awaited_once()

    async def test_new_order_prompt_retries_without_creating_order(self):
        self.ns["asyncio"] = SimpleNamespace(sleep=AsyncMock())
        self.ns["is_authorized"] = lambda user_id: True
        self.ns["process_order_text"] = AsyncMock()
        message = SimpleNamespace(text="📝 Новый заказ", reply_text=AsyncMock(side_effect=[DeliveryTimedOut(), None]))
        await self.ns["handle_text"](SimpleNamespace(effective_user=SimpleNamespace(id=1), message=message), self.context())
        await self.drain()
        self.assertEqual(message.reply_text.await_count, 2)
        self.ns["process_order_text"].assert_not_awaited()

    async def test_browser_notification_retries(self):
        self.ns["asyncio"] = SimpleNamespace(sleep=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock(side_effect=[DeliveryTimedOut(), None]))
        await self.ns["notify_browser_order"](bot, 1, "Saved")
        self.assertEqual(bot.send_message.await_count, 2)
        self.ns["logger"].exception.assert_not_called()

    async def test_blocked_confirmation_does_not_delay_second_save(self):
        release, started = asyncio.Event(), asyncio.Event()
        async def delayed(*args, **kwargs):
            started.set()
            await release.wait()
        first = SimpleNamespace(reply_text=AsyncMock(side_effect=delayed))
        second = SimpleNamespace(reply_text=AsyncMock())
        self.ns["run_sheet_call"] = AsyncMock(side_effect=[42, 43])
        context = self.context()
        try:
            await asyncio.wait_for(self.ns["save_order_to_sheet"]("70000000000", "First", SimpleNamespace(message=first), context), .5)
            await asyncio.wait_for(started.wait(), .5)
            first_revision = context.user_data["order_revision"]
            await asyncio.wait_for(self.ns["save_order_to_sheet"]("70000000001", "Second", SimpleNamespace(message=second), context), .5)
            self.assertEqual(self.ns["run_sheet_call"].await_count, 2)
            self.assertEqual(context.user_data["last_row_index"], 43)
            self.assertNotEqual(context.user_data["order_revision"], first_revision)
            self.assertFalse(self.tasks[0].done())
            # Already scheduled controls carry the original revision, not later state.
            self.assertEqual(first.reply_text.call_args.kwargs["reply_markup"][0][1].callback_data, "delete_order:" + first_revision)
        finally:
            release.set()
            await self.drain()

    async def test_pending_and_completed_confirm_are_idempotent(self):
        release, started = asyncio.Event(), asyncio.Event()
        async def edit(*args, **kwargs):
            started.set()
            await release.wait()
        context = self.context()
        update = self.callback()
        update.callback_query.edit_message_text.side_effect = edit
        try:
            await self.ns["handle_callback"](update, context)
            await asyncio.wait_for(started.wait(), .5)
            await self.ns["handle_callback"](update, context)
            self.assertEqual(len(self.tasks), 1)
        finally:
            release.set()
            await self.drain()
        original_text = update.callback_query.edit_message_text.call_args.args[0]
        self.assertEqual(original_text.count("🚀 Принято!"), 1)
        repeated = self.callback(text=original_text)
        repeated.callback_query.edit_message_text.side_effect = DeliveryBadRequest("Message is not modified")
        await self.ns["handle_callback"](repeated, context)
        await self.drain()
        self.assertEqual(repeated.callback_query.edit_message_text.call_args.args[0], original_text)
        update.callback_query.message.reply_text.assert_not_awaited()
        repeated.callback_query.message.reply_text.assert_not_awaited()
        self.delete_order.assert_not_called()
        self.ns["logger"].exception.assert_not_called()
        self.assertFalse(context.bot_data["_pending_confirmations"])

    async def test_callback_ack_timeout_does_not_abort_confirmation(self):
        update, context = self.callback(), self.context()
        update.callback_query.answer.side_effect = DeliveryTimedOut()
        await self.ns["handle_callback"](update, context)
        await self.drain()
        update.callback_query.edit_message_text.assert_awaited_once()
        self.ns["logger"].exception.assert_not_called()

    async def test_unexpected_confirmation_bad_request_is_reported(self):
        update, context = self.callback(), self.context()
        update.callback_query.edit_message_text.side_effect = DeliveryBadRequest("Message can't be edited")
        await self.ns["handle_callback"](update, context)
        await self.drain()
        self.ns["logger"].exception.assert_called_once()

    async def test_stale_and_legacy_edit_delete_do_not_mutate_current_order(self):
        context = self.context({"last_row_index": 43, "order_revision": "current"})
        self.ns["run_sheet_call"] = AsyncMock()
        for data in ("delete_order:old", "edit_last_order:old", "delete_order", "edit_last_order"):
            await self.ns["handle_callback"](self.callback(data), context)
        await self.drain()
        self.assertEqual(context.user_data, {"last_row_index": 43, "order_revision": "current"})
        self.ns["run_sheet_call"].assert_not_awaited()
        self.delete_order.assert_not_called()

    async def test_delete_storage_once_despite_notification_failure_and_repeat(self):
        context = self.context({"last_row_index": 43, "order_revision": "current"})
        update = self.callback("delete_order:current")
        update.callback_query.message.reply_text.side_effect = RuntimeError("delivery failed")
        await self.ns["handle_callback"](update, context)
        await self.drain()
        await self.ns["handle_callback"](update, context)
        await self.drain()
        self.delete_order.assert_called_once_with(context.bot_data["sheet"], 43)
        self.assertIsNone(context.user_data["last_row_index"])
        self.assertNotIn("order_revision", context.user_data)
        self.assertNotIn("Ошибка удаления", update.callback_query.message.reply_text.call_args_list[0].args[0])

    async def test_scheduling_failure_closes_reply_and_confirmation_coroutines(self):
        context = self.context()
        captured = []
        def reject(coro):
            captured.append(coro)
            raise RuntimeError("application stopped")
        context.application.create_task = reject
        self.ns["schedule_reply"](context, SimpleNamespace(reply_text=AsyncMock()), "Saved")
        self.ns["schedule_confirmation"](context, self.callback().callback_query)
        self.assertEqual(len(captured), 2)
        self.assertTrue(all(inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED for coro in captured))
        self.assertFalse(context.bot_data["_pending_confirmations"])


if __name__ == "__main__":
    unittest.main()
