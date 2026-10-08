#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把请求拉开到接近人工浏览的间隔，并限制单次、单日次数。"""

from __future__ import annotations

import json
import os
import random
from collections.abc import Callable
from datetime import date
from pathlib import Path

from spider.answers.errors import ZhihuError

# 不带 --allow-fast 时，页与页之间至少隔这么多秒。
DELAY_FLOOR = 1.0
DEFAULT_DELAY_MIN = 3.0
DEFAULT_DELAY_MAX = 8.0
DEFAULT_PAUSE_EVERY = 5
DEFAULT_PAUSE_MIN = 15.0
DEFAULT_PAUSE_MAX = 30.0


class RequestCapError(ZhihuError):
    """达到本次运行或当天的请求上限。"""


def default_budget_path() -> Path:
    return Path.home() / ".config" / "zhihu-spider" / "request-count.json"


class Pace:
    """回答页之间随机等待，每隔若干页再多停一会儿。"""

    def __init__(
        self,
        delay_min: float = DEFAULT_DELAY_MIN,
        delay_max: float = DEFAULT_DELAY_MAX,
        *,
        pause_every: int = DEFAULT_PAUSE_EVERY,
        pause_min: float = DEFAULT_PAUSE_MIN,
        pause_max: float = DEFAULT_PAUSE_MAX,
        allow_fast: bool = False,
        max_requests: int | None = None,
        max_requests_per_day: int | None = None,
        budget_path: Path | None = None,
        today: Callable[[], str] | None = None,
        rng: Callable[[], float] = random.random,
        sleep: Callable[[float], None] = __import__("time").sleep,
    ) -> None:
        if delay_min < 0 or delay_max < 0 or pause_min < 0 or pause_max < 0:
            raise ZhihuError("等待时间不能为负数")
        if delay_max < delay_min:
            raise ZhihuError("--delay-max 不能小于 --delay-min")
        if pause_max < pause_min:
            raise ZhihuError("--pause-max 不能小于 --pause-min")
        if pause_every < 0:
            raise ZhihuError("--pause-every 不能为负数")
        if max_requests is not None and max_requests < 1:
            raise ZhihuError("--max-requests 必须是正整数")
        if max_requests_per_day is not None and max_requests_per_day < 1:
            raise ZhihuError("--max-requests-per-day 必须是正整数")
        if not allow_fast and delay_min < DELAY_FLOOR:
            raise ZhihuError(
                f"请求间隔不能低于 {DELAY_FLOOR:.0f} 秒，当前 --delay-min 是 {delay_min}。"
                "默认是 3 到 8 秒。确认要更快时才加 --allow-fast。"
            )
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.pause_every = pause_every
        self.pause_min = pause_min
        self.pause_max = pause_max
        self.max_requests = max_requests
        self.max_requests_per_day = max_requests_per_day
        self.budget_path = budget_path or default_budget_path()
        self.today = today or (lambda: date.today().isoformat())
        self.rng = rng
        self.sleep = sleep
        self.sent = 0
        self.answer_pages = 0
        self.run_count = 0

    def before(self, kind: str) -> float:
        """发请求前调用。返回实际等待的秒数。达到上限时不发请求。"""
        self._enforce_cap()
        wait = 0.0
        if self.sent:
            wait = self._uniform(self.delay_min, self.delay_max)
            if (
                kind == "answer"
                and self.pause_every
                and self.answer_pages
                and self.answer_pages % self.pause_every == 0
            ):
                wait += self._uniform(self.pause_min, self.pause_max)
        if wait > 0:
            self.sleep(wait)
        if kind == "answer":
            self.answer_pages += 1
        self.sent += 1
        self._record()
        return wait

    def _uniform(self, low: float, high: float) -> float:
        if high <= low:
            return low
        return low + (high - low) * self.rng()

    def _enforce_cap(self) -> None:
        if self.max_requests is not None and self.run_count >= self.max_requests:
            raise RequestCapError(
                f"这次运行的请求已达到上限 {self.max_requests}。"
                "进度会保留。把 --max-requests 调大，或稍后再执行同一条命令即可继续。"
            )
        if self.max_requests_per_day is None:
            return
        used = self._daily_count()
        if used >= self.max_requests_per_day:
            raise RequestCapError(
                f"今天的请求已达到上限 {self.max_requests_per_day}（已记录 {used} 次）。"
                "进度会保留。明天再执行同一条命令会接着抓，也可以调大 --max-requests-per-day。"
            )

    def _record(self) -> None:
        self.run_count += 1
        if self.max_requests_per_day is None:
            return
        used = self._daily_count() + 1
        self._write_daily(used)

    def _daily_count(self) -> int:
        path = self.budget_path
        if not path.exists():
            return 0
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        if payload.get("date") != self.today():
            return 0
        count = payload.get("count") or 0
        return int(count) if isinstance(count, int) else 0

    def _write_daily(self, count: int) -> None:
        path = self.budget_path
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
        payload = json.dumps({"date": self.today(), "count": count}, ensure_ascii=False) + "\n"
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
