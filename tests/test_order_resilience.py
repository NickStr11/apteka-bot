"""Offline regression checks using production function bodies, without service imports."""
import ast
import asyncio
import logging
import re
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]


def load_functions(path, names, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    assert len(nodes) == len(names)
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), path, "exec"), namespace)
    return namespace


class ResilienceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.ns = dict(asyncio=asyncio, partial=partial, _SHEETS_EXECUTOR=self.executor, re=re, logger=Mock(), datetime=datetime)
        load_functions("src/database/sheets.py", {"run_sheet_call", "add_order"}, self.ns)
        load_functions("src/bot/telegram_bot.py", {"notify_order_saved", "notify_browser_order", "api_handle_order", "save_order_to_sheet"}, self.ns)
        self.ns.update(OrderRow=lambda **kwargs: SimpleNamespace(**kwargs), get_main_keyboard=lambda: "main", get_order_control_keyboard=lambda: "controls")
        self.order = SimpleNamespace(date="date", order_number="order", phone="phone", products="product", total=0, wa_status="", sms_status="", sent="", note="", contact_status="")

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
        context = SimpleNamespace(bot_data={"sheet": object()}, user_data={"last_row_index": 99})
        await self.ns["save_order_to_sheet"]("70000000000", "Product", SimpleNamespace(message=message), context)
        self.ns["add_order"].assert_called_once()
        message.reply_text.assert_awaited_once()
        self.assertIn("Заказ сохранён", message.reply_text.call_args.args[0])
        self.assertEqual(message.reply_text.call_args.kwargs["reply_markup"], "main")
        self.assertIsNone(context.user_data["last_row_index"])
        self.ns["logger"].error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
