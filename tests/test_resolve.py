#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入识别、多结果选择和 Cookie 读取。"""

import tempfile
import unittest
from pathlib import Path

from spider.answers.cookie import ensure_d_c0, read_cookie_file
from spider.answers.errors import ZhihuError
from spider.answers.resolve import choose_candidate, classify_query
from spider.answers.sign import sign_path


class ClassifyTest(unittest.TestCase):
    def test_url_id_and_title(self) -> None:
        self.assertEqual(classify_query("https://www.zhihu.com/question/12345/answer/9"), ("id", "12345"))
        self.assertEqual(classify_query(" 67890 "), ("id", "67890"))
        self.assertEqual(classify_query("如何评价 Python"), ("title", "如何评价 Python"))

    def test_blank(self) -> None:
        with self.assertRaises(ZhihuError):
            classify_query("  ")


class ChooseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.candidates = [
            {"id": "1", "title": "甲", "answer_count": 2, "follower_count": 3},
            {"id": "2", "title": "乙", "answer_count": 4, "follower_count": 5},
        ]

    def test_single_candidate_is_used(self) -> None:
        chosen = choose_candidate(self.candidates[:1], None, interactive=False)
        self.assertEqual(chosen["id"], "1")

    def test_noninteractive_requires_pick(self) -> None:
        messages: list[str] = []
        with self.assertRaises(ZhihuError):
            choose_candidate(self.candidates, None, interactive=False, output=messages.append)
        self.assertIn("[1]", messages[0])
        self.assertIn("甲", messages[0])

    def test_pick_flag(self) -> None:
        chosen = choose_candidate(self.candidates, 2, interactive=False)
        self.assertEqual(chosen["id"], "2")

    def test_interactive_input(self) -> None:
        chosen = choose_candidate(
            self.candidates,
            None,
            interactive=True,
            input_func=lambda _prompt: "1",
            output=lambda _message: None,
        )
        self.assertEqual(chosen["id"], "1")


class CookieAndSignTest(unittest.TestCase):
    def test_cookie_file_comments_and_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cookies.txt"
            path.write_text("# 注释\n\nd_c0=\"abc|1\"\nz_c0=token\n", encoding="utf-8")
            cookie = read_cookie_file(path)
        self.assertEqual(cookie, 'd_c0="abc|1"; z_c0=token')
        kept, generated = ensure_d_c0(cookie)
        self.assertFalse(generated)
        self.assertIn('d_c0="abc|1"', kept)

    def test_missing_d_c0_is_generated(self) -> None:
        cookie, generated = ensure_d_c0("z_c0=only")
        self.assertTrue(generated)
        self.assertIn("d_c0=", cookie)
        self.assertIn("z_c0=only", cookie)

    def test_sign_matches_known_vector(self) -> None:
        signed = sign_path(
            "/api/v4/questions/19581624/answers?limit=20&offset=0&platform=desktop&sort_by=default",
            'd_c0="AIAf1GdgbRSPTtoYPsJrpvRp_MB-_8SxwGQ=|1643717522"; _xsrf=abc',
            rng=lambda: 0.42,
        )
        self.assertEqual(signed["x-zse-93"], "101_3_3.0")
        self.assertEqual(
            signed["x-zse-96"],
            "2.0_RX7f6X2AInoPC=ZR9PYC=lPxH=T+AhiZtz6cqDNQ+p1IHu6j5Vw1+bs+/sFqYH12",
        )


if __name__ == "__main__":
    unittest.main()
