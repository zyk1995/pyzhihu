#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""访问知乎 v4 接口。带签名、间隔、退避重试。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from urllib.parse import quote, urlencode

import requests

from spider.answers.cookie import ensure_d_c0
from spider.answers.errors import ZhihuBlockedError, ZhihuError, explain_block, explain_rate_limit
from spider.answers.pace import Pace
from spider.answers.parse import parse_question, parse_search_questions
from spider.answers.sign import sign_path

BASE_URL = "https://www.zhihu.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
ANSWER_INCLUDE = "data[*].content,voteup_count,comment_count,created_time,updated_time,author"
QUESTION_INCLUDE = "answer_count,follower_count,title,detail"
# 这些错误码表示环境或登录态被拒绝，重试同一出口没有意义。
_HARD_BLOCK_CODES = {40352, 40362, 4039}


class ZhihuClient:
    def __init__(
        self,
        cookie: str = "",
        *,
        delay: float | None = None,
        allow_fast: bool = False,
        pace: Pace | None = None,
        retries: int = 4,
        timeout: float = 20.0,
        proxy: str | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if retries < 1:
            raise ZhihuError("--retries 至少为 1")
        if pace is not None:
            self.pace = pace
        elif delay is None:
            self.pace = Pace(sleep=sleep)
        else:
            self.pace = Pace(delay, delay, pause_every=0, allow_fast=allow_fast, sleep=sleep)
        self.retries = retries
        self.timeout = timeout
        self.sleep = self.pace.sleep
        self.cookie, self.generated_d_c0 = ensure_d_c0(cookie)
        self.session = session or requests.Session()
        self.proxies = {"http": proxy, "https": proxy} if proxy else None

    def search_questions(self, keyword: str, limit: int = 10) -> list[dict]:
        payload = self.get_json(
            "/api/v4/search_v3",
            [
                ("t", "general"),
                ("q", keyword),
                ("correction", "1"),
                ("offset", "0"),
                ("limit", "20"),
                ("filter_fields", ""),
                ("lc_idx", "0"),
                ("show_all_topics", "0"),
                ("search_source", "Normal"),
            ],
            referer="https://www.zhihu.com/search?type=content&q=" + quote(keyword),
        )
        return parse_search_questions(payload, limit=limit)

    def get_question(self, question_id: str) -> dict:
        payload = self.get_json(
            f"/api/v4/questions/{question_id}",
            [("include", QUESTION_INCLUDE)],
            referer=f"https://www.zhihu.com/question/{question_id}",
        )
        question = parse_question(payload, fallback_id=str(question_id))
        if not question["id"]:
            raise ZhihuError(f"问题 {question_id} 的响应里没有 ID")
        return question

    def get_answers_page(self, question_id: str, offset: int, limit: int) -> dict:
        return self.get_json(
            f"/api/v4/questions/{question_id}/answers",
            [
                ("include", ANSWER_INCLUDE),
                ("limit", str(limit)),
                ("offset", str(offset)),
                ("platform", "desktop"),
                ("sort_by", "default"),
            ],
            referer=f"https://www.zhihu.com/question/{question_id}",
        )

    def get_me(self) -> dict:
        """当前登录用户。用来判断本地会话是否还有效。"""
        return self.get_json(
            "/api/v4/me",
            [("include", "name,url_token,uid")],
            referer="https://www.zhihu.com/",
        )

    def get_json(self, path: str, params: list[tuple[str, str]], *, referer: str) -> dict:
        query = urlencode(params)
        path_and_query = f"{path}?{query}" if query else path
        url = BASE_URL + path_and_query
        self.pace.before("answer" if path.rstrip("/").endswith("/answers") else "other")
        last_error: Exception | None = None
        rate_hits = 0
        for attempt in range(1, self.retries + 1):
            headers = self._headers(path_and_query, referer)
            try:
                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=self.timeout,
                    proxies=self.proxies,
                    allow_redirects=False,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.retries:
                    break
                self.sleep(self._backoff(attempt))
                continue
            try:
                payload = self._decode(response)
            except ZhihuBlockedError:
                raise
            except _Retryable as exc:
                last_error = exc
                if exc.status == 429:
                    rate_hits += 1
                    if rate_hits >= 2 or attempt >= self.retries:
                        raise ZhihuBlockedError(
                            explain_rate_limit(rate_hits) + "已停止继续请求，避免把风控打得更严。",
                            status_code=429,
                            error_code=429,
                        )
                    self.sleep(max(20.0, self.pace.pause_min))
                    continue
                if attempt >= self.retries:
                    break
                self.sleep(self._backoff(attempt))
                continue
            return payload
        raise ZhihuError(f"请求失败，已重试 {self.retries} 次：{url} ({last_error})")

    def _headers(self, path_and_query: str, referer: str) -> dict[str, str]:
        signed = sign_path(path_and_query, self.cookie)
        return {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": referer,
            "x-requested-with": "fetch",
            "x-zse-93": signed["x-zse-93"],
            "x-zse-96": signed["x-zse-96"],
            "x-zst-81": signed["x-zst-81"],
            "cookie": self.cookie,
        }

    def _decode(self, response: requests.Response) -> dict:
        status = response.status_code
        text = response.text or ""
        content_type = response.headers.get("content-type", "")
        if status in (301, 302, 303, 307, 308):
            location = response.headers.get("Location", "")
            raise self._blocked(status, "redirect", f"被重定向到 {location}", text)
        if "zh-zse-ck" in text:
            raise self._blocked(
                status,
                "zse-ck",
                "返回了反爬校验页（HTML 中含 meta id=zh-zse-ck），匿名访问被拦截",
                text,
            )
        if status in (429, 500, 502, 503, 504):
            raise _Retryable(f"HTTP {status}", status=status)
        payload = _load_json(text)
        if payload is None:
            if status >= 400:
                raise ZhihuError(f"HTTP {status}，响应不是 JSON：{text[:180]}")
            raise ZhihuError(f"响应不是 JSON：{text[:180]}")
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict) or status >= 400:
            message = ""
            code: int | str | None = status
            if isinstance(error, dict):
                message = str(error.get("message") or "")
                code = error.get("code", status)
            blocked = status in (401, 403) or (isinstance(code, int) and code in _HARD_BLOCK_CODES)
            if isinstance(error, dict) and error.get("need_login"):
                blocked = True
            if "验证码" in message or "安全验证" in message:
                blocked = True
            if blocked:
                raise self._blocked(status, code, message or "访问被拒绝", text)
            if status == 404:
                raise ZhihuError(message or "内容不存在或当前账号不可见")
            raise ZhihuError(message or f"HTTP {status}")
        if not isinstance(payload, dict):
            raise ZhihuError("知乎返回的 JSON 不是对象")
        return payload

    def _blocked(self, status: int, code: int | str | None, raw_message: str, body: str) -> ZhihuBlockedError:
        return ZhihuBlockedError(
            explain_block(status, code, raw_message),
            status_code=status,
            error_code=code,
            body=body[:500],
        )

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(30.0, float(2 ** (attempt - 1)))


class _Retryable(ZhihuError):
    """5xx / 429，由客户端内部重试。"""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _load_json(text: str) -> dict | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        return data
    return None

