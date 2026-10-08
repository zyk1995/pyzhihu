#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用假的 HTTP 响应验证分页抓取、断点续传和拒绝访问提示。"""

import json
import unittest
from urllib.parse import parse_qs, urlparse

from spider.answers.client import ZhihuClient
from spider.answers.crawl import crawl_answers
from spider.answers.errors import ZhihuBlockedError
from spider.answers.storage import AnswerStore


def _answer(answer_id: int, text: str) -> dict:
    return {
        "id": answer_id,
        "content": f"<p>{text}</p>",
        "voteup_count": answer_id,
        "comment_count": 0,
        "created_time": 1600000000 + answer_id,
        "updated_time": 1600001000 + answer_id,
        "author": {"name": f"用户{answer_id}", "url_token": f"user-{answer_id}"},
    }


def _page(items: list[dict], *, offset: int, limit: int, is_end: bool, total: int = 3) -> dict:
    next_offset = None if is_end else offset + limit
    paging = {"is_end": is_end, "totals": total}
    if next_offset is not None:
        paging["next"] = f"https://www.zhihu.com/api/v4/questions/77/answers?limit={limit}&offset={next_offset}"
    return {"data": items, "paging": paging}


class _Response:
    def __init__(self, status: int, payload: dict, headers: dict | None = None) -> None:
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)
        self.headers = headers or {"content-type": "application/json"}


class _Session:
    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls: list[str] = []

    def get(self, url, headers=None, timeout=None, proxies=None, allow_redirects=None):
        self.calls.append(url)
        return self.handler(url, headers or {})


class CrawlFlowTest(unittest.TestCase):
    def _client(self, handler, sleeps: list[float]) -> tuple[ZhihuClient, _Session]:
        session = _Session(handler)
        client = ZhihuClient(
            "d_c0=abc|1",
            delay=0,
            allow_fast=True,
            retries=2,
            session=session,
            sleep=sleeps.append,
        )
        return client, session

    def test_paginates_then_resumes_without_duplicates(self) -> None:
        pages = {
            0: _page([_answer(1, "一"), _answer(2, "二")], offset=0, limit=2, is_end=False),
            2: _page([_answer(3, "三")], offset=2, limit=2, is_end=True),
        }

        def handler(url, _headers):
            offset = int(parse_qs(urlparse(url).query)["offset"][0])
            return _Response(200, pages[offset])

        sleeps: list[float] = []
        client, session = self._client(handler, sleeps)
        store = AnswerStore(self._tmp(), "77")
        question = {"id": "77", "title": "测试题", "answer_count": None, "follower_count": 6}
        first = crawl_answers(client, store, question, page_limit=2, max_answers=1)
        self.assertEqual(first, 1)
        self.assertFalse(store.load_progress()["done"])
        self.assertEqual(store.load_progress()["next_offset"], 0)

        second = crawl_answers(client, store, question, page_limit=2)
        self.assertEqual(second, 2)
        self.assertTrue(store.load_progress()["done"])
        saved = store.jsonl_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(saved), 3)
        ids = [json.loads(line)["answer_id"] for line in saved]
        self.assertEqual(ids, ["1", "2", "3"])
        self.assertEqual(crawl_answers(client, store, question, page_limit=2), 0)
        # 第一轮只写下半页，续传会重拉这一页再拉末页；完成后不再请求。
        answer_calls = [url for url in session.calls if "/answers?" in url]
        self.assertEqual(len(answer_calls), 3)
        raw_csv = store.csv_path.read_bytes()
        self.assertTrue(raw_csv.startswith(b"\xef\xbb\xbf"))
        self.assertIn("用户1".encode("utf-8"), raw_csv)
        stored_question = store.load_question()
        assert stored_question is not None
        self.assertEqual(stored_question["title"], "测试题")
        self.assertEqual(stored_question["answer_count"], 3)
        self.assertEqual(stored_question["follower_count"], 6)

    def test_empty_page_does_not_loop(self) -> None:
        def handler(_url, _headers):
            return _Response(200, {"data": [], "paging": {"is_end": False, "next": "https://www.zhihu.com/api/v4/questions/1/answers?offset=0"}})

        sleeps: list[float] = []
        client, session = self._client(handler, sleeps)
        store = AnswerStore(self._tmp(), "1")
        written = crawl_answers(client, store, {"id": "1", "title": "空", "answer_count": 0, "follower_count": 0}, page_limit=5)
        self.assertEqual(written, 0)
        self.assertEqual(len(session.calls), 1)
        self.assertFalse(store.load_progress()["done"])

    def test_blocked_response_is_not_retried(self) -> None:
        def handler(_url, headers):
            self.assertTrue(headers["x-zse-96"].startswith("2.0_"))
            self.assertIn("d_c0=", headers["cookie"])
            return _Response(
                403,
                {"error": {"code": 40362, "message": "您当前请求存在异常，暂时限制本次访问。"}},
            )

        sleeps: list[float] = []
        client, session = self._client(handler, sleeps)
        with self.assertRaises(ZhihuBlockedError) as caught:
            client.get_question("19581624")
        self.assertEqual(len(session.calls), 1)
        self.assertIn("40362", str(caught.exception))
        self.assertIn("ZHIHU_COOKIE", str(caught.exception))
        self.assertIn("您当前请求存在异常", str(caught.exception))

    def test_risk_control_stops_and_keeps_offset(self) -> None:
        def handler(url, _headers):
            offset = int(parse_qs(urlparse(url).query)["offset"][0])
            if offset >= 2:
                return _Response(403, {"error": {"code": 40362, "message": "您当前请求存在异常，暂时限制本次访问。"}})
            return _Response(200, _page([_answer(1, "一")], offset=0, limit=2, is_end=False, total=4))

        sleeps: list[float] = []
        client, _session = self._client(handler, sleeps)
        store = AnswerStore(self._tmp(), "77")
        with self.assertRaises(ZhihuBlockedError) as caught:
            crawl_answers(client, store, {"id": "77", "title": "风控", "answer_count": 4, "follower_count": 1}, page_limit=2)
        self.assertIn("40362", str(caught.exception))
        self.assertIn("继续", str(caught.exception))
        self.assertEqual(store.load_progress()["next_offset"], 2)
        self.assertFalse(store.load_progress()["done"])
        self.assertEqual(store.load_saved_ids(), {"1"})

    def test_retries_server_error(self) -> None:
        state = {"n": 0}

        def handler(_url, _headers):
            state["n"] += 1
            if state["n"] == 1:
                return _Response(503, {"error": {"message": "busy"}})
            return _Response(200, {"id": 8, "title": "重试后成功", "answer_count": 1, "follower_count": 1})

        sleeps: list[float] = []
        client, session = self._client(handler, sleeps)
        question = client.get_question("8")
        self.assertEqual(question["title"], "重试后成功")
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(sleeps, [1.0])

    def _tmp(self) -> str:
        import tempfile

        return tempfile.mkdtemp(prefix="zhihu-answers-")


if __name__ == "__main__":
    unittest.main()
