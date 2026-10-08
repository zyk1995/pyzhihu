#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""请求间隔、长停和次数上限。不访问网络。"""

import argparse
import tempfile
import unittest
from pathlib import Path

from spider.answers.cli import build_pace
from spider.answers.errors import ZhihuError
from spider.answers.pace import Pace, RequestCapError
from spider.answers.progress import format_progress, format_summary


class PaceTest(unittest.TestCase):
    def test_floor_blocks_fast_delay(self) -> None:
        with self.assertRaises(ZhihuError):
            Pace(0.2, 0.2)
        Pace(0.2, 0.2, allow_fast=True, pause_every=0)

    def test_jitter_and_periodic_pause(self) -> None:
        sleeps: list[float] = []
        pace = Pace(
            3,
            8,
            pause_every=2,
            pause_min=10,
            pause_max=10,
            rng=lambda: 0.5,
            sleep=sleeps.append,
        )
        self.assertEqual(pace.before("answer"), 0)
        self.assertEqual(pace.before("answer"), 5.5)
        self.assertEqual(pace.before("answer"), 15.5)
        self.assertEqual(sleeps, [5.5, 15.5])

    def test_run_and_daily_caps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "request-count.json"
            pace = Pace(
                0,
                0,
                pause_every=0,
                allow_fast=True,
                max_requests=2,
                max_requests_per_day=1,
                budget_path=path,
                today=lambda: "2026-10-08",
                sleep=lambda _seconds: None,
            )
            pace.before("other")
            with self.assertRaises(RequestCapError) as daily:
                pace.before("other")
            self.assertIn("今天", str(daily.exception))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

        pace = Pace(0, 0, pause_every=0, allow_fast=True, max_requests=1, sleep=lambda _seconds: None)
        pace.before("answer")
        with self.assertRaises(RequestCapError) as run_cap:
            pace.before("answer")
        self.assertIn("这次运行", str(run_cap.exception))

    def test_cli_delay_override(self) -> None:
        with self.assertRaises(ZhihuError):
            build_pace(argparse.Namespace(
                delay=0.2,
                delay_min=3,
                delay_max=8,
                pause_every=5,
                pause_min=15,
                pause_max=30,
                allow_fast=False,
                max_requests=None,
                max_requests_per_day=None,
            ))
        pace = build_pace(argparse.Namespace(
            delay=2,
            delay_min=3,
            delay_max=8,
            pause_every=5,
            pause_min=15,
            pause_max=30,
            allow_fast=False,
            max_requests=None,
            max_requests_per_day=None,
        ))
        self.assertEqual((pace.delay_min, pace.delay_max, pace.pause_every), (2, 2, 0))


class ProgressTextTest(unittest.TestCase):
    def test_bar_and_summary(self) -> None:
        self.assertIn("进度 1/4", format_progress(1, 4))
        self.assertIn("█", format_progress(1, 4))
        text = format_summary(
            title="题",
            question_id="9",
            written=1,
            saved=1,
            total=4,
            directory="output/9",
            seconds=1.2,
        )
        self.assertIn("抓取结束", text)
        self.assertIn("本次新写入：1 条", text)


if __name__ == "__main__":
    unittest.main()
