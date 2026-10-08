#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫码状态和终端二维码。不访问知乎。"""

import os
import tempfile
import unittest
from pathlib import Path

from spider.answers.errors import ZhihuBlockedError
from spider.answers.login import QrTicket, ScanPoll, interpret_scan, run_qr_login
from spider.answers.qr_view import render_terminal_qr, write_qr_png
from spider.answers.session_store import has_login_cookie, load_session, save_session


class InterpretScanTest(unittest.TestCase):
    def test_status_mapping(self) -> None:
        self.assertEqual(interpret_scan(ScanPoll(200, {"status": 0}, False)), "waiting")
        self.assertEqual(interpret_scan(ScanPoll(200, {"status": 1, "user_id": 3}, False)), "scanned")
        self.assertEqual(interpret_scan(ScanPoll(200, {"status": 1}, True)), "success")
        self.assertEqual(interpret_scan(ScanPoll(400, {"error": {"message": "二维码已过期"}}, False)), "expired")
        blocked = interpret_scan(ScanPoll(403, {"error": {"code": 40352, "message": "安全验证"}}, False))
        self.assertEqual(blocked, "blocked")


class QrViewTest(unittest.TestCase):
    def test_terminal_and_png_without_viewer(self) -> None:
        link = "https://www.zhihu.com/account/scan/login/abc?/api/login/qrcode"
        text = render_terminal_qr(link)
        self.assertIn("█", text)
        self.assertGreater(text.count("\n"), 5)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "login-qr.png"
            write_qr_png(link, path)
            self.assertTrue(path.read_bytes().startswith(b"\x89PNG"))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class SessionFileTest(unittest.TestCase):
    def test_roundtrip_is_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.cookie"
            save_session(path, 'd_c0="abc"; z_c0=secret')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(has_login_cookie(load_session(path)))
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


class LoginLoopTest(unittest.TestCase):
    def test_refresh_then_confirm(self) -> None:
        clock = [0.0]

        class FakeApi:
            def __init__(self) -> None:
                self.hits = 0

            def bootstrap(self) -> None:
                return None

            def fetch_ticket(self) -> QrTicket:
                token = "t1" if clock[0] < 5 else "t2"
                expires = 5 if token == "t1" else 100
                return QrTicket(token, f"https://www.zhihu.com/account/scan/login/{token}", expires)

            def official_image(self, _token: str) -> None:
                return None

            def poll(self, token: str) -> ScanPoll:
                if token == "t1":
                    return ScanPoll(200, {"status": 0}, False)
                self.hits += 1
                if self.hits == 1:
                    return ScanPoll(200, {"status": 1}, False)
                return ScanPoll(200, {"access_token": "x"}, True)

            def cookie_header(self) -> str:
                return "d_c0=abc; z_c0=ok"

        messages: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session.cookie"
            png = Path(tmp) / "login-qr.png"
            cookie = run_qr_login(
                FakeApi(),
                png,
                timeout=30,
                poll_interval=2,
                now=lambda: clock[0],
                sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
                emit=messages.append,
                session_path=session,
            )
        text = "\n".join(messages)
        self.assertIn("等待扫码", text)
        self.assertIn("二维码过期自动刷新", text)
        self.assertIn("已扫码请在手机确认", text)
        self.assertIn("登录成功", text)
        self.assertIn("█", text)
        self.assertIn("不会打开图片查看器", text)
        self.assertEqual(cookie, "d_c0=abc; z_c0=ok")

    def test_blocked_poll_stops(self) -> None:
        class FakeApi:
            def bootstrap(self) -> None:
                return None

            def fetch_ticket(self) -> QrTicket:
                return QrTicket("t", "https://www.zhihu.com/account/scan/login/t", 100)

            def official_image(self, _token: str) -> None:
                return None

            def poll(self, _token: str) -> ScanPoll:
                return ScanPoll(403, {"error": {"code": 40352, "message": "系统监测到您的网络环境存在异常"}}, False)

            def cookie_header(self) -> str:
                return ""

        messages: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ZhihuBlockedError) as caught:
                run_qr_login(
                    FakeApi(),
                    Path(tmp) / "login-qr.png",
                    timeout=10,
                    poll_interval=1,
                    now=lambda: 0,
                    sleep=lambda _seconds: None,
                    emit=messages.append,
                )
        self.assertIn("等待扫码", "\n".join(messages))
        self.assertIn("40352", str(caught.exception))
        self.assertNotIn("登录成功", "\n".join(messages))


if __name__ == "__main__":
    unittest.main()
