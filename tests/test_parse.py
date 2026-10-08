#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析与分页逻辑的单元测试，不访问网络。"""

import unittest

from spider.answers.parse import (
    html_to_text,
    parse_answer,
    parse_answers_page,
    parse_question,
    parse_search_questions,
)


class HtmlTextTest(unittest.TestCase):
    def test_keeps_paragraphs_and_drops_script(self) -> None:
        html = "<p>第一段</p><p>第二段 <b>加粗</b></p><script>alert(1)</script>"
        self.assertEqual(html_to_text(html), "第一段\n第二段 加粗")

    def test_empty(self) -> None:
        self.assertEqual(html_to_text(""), "")


class ParseAnswerTest(unittest.TestCase):
    def test_required_fields(self) -> None:
        raw = {
            "id": 1001,
            "content": "<p>你好</p>",
            "voteup_count": 12,
            "comment_count": 3,
            "created_time": 1500000000,
            "updated_time": 1500001000,
            "author": {"name": "张三", "url_token": "zhangsan"},
        }
        parsed = parse_answer(raw, "42")
        self.assertEqual(parsed["answer_id"], "1001")
        self.assertEqual(parsed["author_name"], "张三")
        self.assertEqual(parsed["author_url_token"], "zhangsan")
        self.assertEqual(parsed["content_text"], "你好")
        self.assertEqual(parsed["content_html"], "<p>你好</p>")
        self.assertEqual(parsed["voteup_count"], 12)
        self.assertEqual(parsed["comment_count"], 3)
        self.assertEqual(parsed["created_time"], 1500000000)
        self.assertEqual(parsed["updated_time"], 1500001000)
        self.assertEqual(parsed["answer_url"], "https://www.zhihu.com/question/42/answer/1001")
        self.assertEqual(parsed["question_id"], "42")

    def test_anonymous_author(self) -> None:
        parsed = parse_answer({"id": 7, "author": {}}, "9")
        self.assertEqual(parsed["author_name"], "")
        self.assertEqual(parsed["author_url_token"], "")
        self.assertEqual(parsed["content_text"], "")


class ParseQuestionTest(unittest.TestCase):
    def test_flat_and_wrapped(self) -> None:
        flat = parse_question({"id": 5, "title": "标题", "answer_count": 8, "follower_count": 2})
        self.assertEqual(flat["id"], "5")
        self.assertEqual(flat["title"], "标题")
        self.assertEqual(flat["answer_count"], 8)
        self.assertEqual(flat["follower_count"], 2)
        wrapped = parse_question({"data": {"id": 6, "name": "别名"}})
        self.assertEqual(wrapped["title"], "别名")
        self.assertEqual(wrapped["id"], "6")


class SearchParseTest(unittest.TestCase):
    def test_dedup_question_embedded_in_answer(self) -> None:
        payload = {
            "data": [
                {
                    "type": "search_result",
                    "object": {
                        "type": "answer",
                        "question": {"id": "11", "name": "如何入门", "answer_count": 4},
                    },
                },
                {
                    "type": "search_result",
                    "object": {
                        "type": "question",
                        "id": "11",
                        "title": "如何入门",
                        "follower_count": 9,
                    },
                },
                {
                    "type": "search_result",
                    "object": {"type": "question", "id": "22", "title": "另一题", "answer_count": 1, "follower_count": 0},
                },
            ]
        }
        found = parse_search_questions(payload, limit=10)
        self.assertEqual([item["id"] for item in found], ["11", "22"])
        self.assertEqual(found[0]["title"], "如何入门")
        self.assertEqual(found[0]["answer_count"], 4)
        self.assertEqual(found[0]["follower_count"], 9)

    def test_limit(self) -> None:
        payload = {
            "data": [
                {"object": {"type": "question", "id": str(index), "title": f"题{index}"}}
                for index in range(1, 6)
            ]
        }
        self.assertEqual(len(parse_search_questions(payload, limit=2)), 2)


class PaginationTest(unittest.TestCase):
    def test_follows_next_offset(self) -> None:
        payload = {
            "data": [{"id": 1, "content": "<p>甲</p>", "author": {"name": "甲", "url_token": "a"}}],
            "paging": {
                "is_end": False,
                "next": "https://www.zhihu.com/api/v4/questions/9/answers?limit=20&offset=20",
                "totals": 41,
            },
        }
        answers, next_offset, is_end = parse_answers_page(payload, "9", 0, 20)
        self.assertEqual(len(answers), 1)
        self.assertEqual(answers[0]["content_text"], "甲")
        self.assertEqual(next_offset, 20)
        self.assertFalse(is_end)

    def test_is_end_stops(self) -> None:
        payload = {
            "data": [{"id": 2, "content": "纯文本", "author": {"name": "乙", "url_token": "b"}}],
            "paging": {"is_end": True, "next": "https://www.zhihu.com/api/v4/questions/9/answers?offset=999"},
        }
        answers, next_offset, is_end = parse_answers_page(payload, "9", 20, 20)
        self.assertEqual(answers[0]["answer_id"], "2")
        self.assertIsNone(next_offset)
        self.assertTrue(is_end)

    def test_missing_next_uses_limit(self) -> None:
        payload = {"data": [{"id": 3}], "paging": {"is_end": False}}
        _answers, next_offset, is_end = parse_answers_page(payload, "9", 5, 10)
        self.assertEqual(next_offset, 15)
        self.assertFalse(is_end)


if __name__ == "__main__":
    unittest.main()
