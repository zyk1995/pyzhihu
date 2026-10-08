#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行：python -m spider.answers \"问题标题\""""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from spider.answers.client import ZhihuClient
from spider.answers.cookie import load_cookie
from spider.answers.crawl import crawl_answers
from spider.answers.errors import ZhihuBlockedError, ZhihuError, is_login_failure
from spider.answers.login import HttpQrApi, run_qr_login
from spider.answers.pace import Pace
from spider.answers.progress import format_summary
from spider.answers.resolve import choose_candidate, classify_query
from spider.answers.session_store import default_session_path, has_login_cookie, load_session, save_session
from spider.answers.storage import AnswerStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m spider.answers",
        description="抓取一个知乎问题下的全部回答，保存为 JSON Lines 和 CSV。",
    )
    parser.add_argument("query", help="问题标题、问题 URL，或纯数字问题 ID")
    parser.add_argument("--pick", type=int, default=None, help="标题命中多个问题时选择第 N 个，从 1 开始")
    parser.add_argument("--output", default="output", help="输出根目录，实际文件在该目录下的问题 ID 文件夹中")
    parser.add_argument("--cookie-file", default=None, help="浏览器 Cookie 文件。也可用环境变量 ZHIHU_COOKIE")
    parser.add_argument("--session-file", default=None, help="扫码会话保存路径，默认 ~/.config/zhihu-spider/session.cookie")
    parser.add_argument("--login", action="store_true", help="忽略已有会话，重新扫码登录")
    parser.add_argument("--login-timeout", type=float, default=300, help="扫码总等待秒数，默认 300。0 表示一直等到 Ctrl+C")
    parser.add_argument("--delay", type=float, default=None, help="固定请求间隔秒数。低于 1 需要 --allow-fast")
    parser.add_argument("--delay-min", type=float, default=3.0, help="随机间隔下限秒数，默认 3")
    parser.add_argument("--delay-max", type=float, default=8.0, help="随机间隔上限秒数，默认 8")
    parser.add_argument("--pause-every", type=int, default=5, help="每抓多少页回答额外长停一次，默认 5。0 表示不额外停")
    parser.add_argument("--pause-min", type=float, default=15.0, help="额外长停的下限秒数，默认 15")
    parser.add_argument("--pause-max", type=float, default=30.0, help="额外长停的上限秒数，默认 30")
    parser.add_argument("--allow-fast", action="store_true", help="允许把间隔设到 1 秒以下。默认不允许")
    parser.add_argument("--max-requests", type=int, default=None, help="这次运行最多发多少次接口请求")
    parser.add_argument("--max-requests-per-day", type=int, default=None, help="今天最多发多少次接口请求，计数在本机配置目录")
    parser.add_argument("--retries", type=int, default=3, help="网络错误或 5xx 的重试次数，默认 3。429 最多再试 1 次")
    parser.add_argument("--timeout", type=float, default=20.0, help="单次请求超时秒数，默认 20")
    parser.add_argument("--page-size", type=int, default=20, help="每页回答数，1 到 20，默认 20")
    parser.add_argument("--max-answers", type=int, default=None, help="最多新写入多少条，默认不限制")
    parser.add_argument("--proxy", default=None, help="可选 HTTP 代理，例如 http://127.0.0.1:7890")
    parser.add_argument("--force", action="store_true", help="忽略已完成标记，从偏移 0 再扫一遍，已保存的回答会跳过")
    return parser


def build_pace(args: argparse.Namespace) -> Pace:
    delay_min = args.delay if args.delay is not None else args.delay_min
    delay_max = args.delay if args.delay is not None else args.delay_max
    return Pace(
        delay_min,
        delay_max,
        pause_every=0 if args.delay is not None else args.pause_every,
        pause_min=args.pause_min,
        pause_max=args.pause_max,
        allow_fast=args.allow_fast,
        max_requests=args.max_requests,
        max_requests_per_day=args.max_requests_per_day,
    )


def _emit(message: str) -> None:
    print(message, file=sys.stderr, end="" if message.endswith("\n") else "\n")


def login_and_save(args: argparse.Namespace, session_path: Path) -> str:
    png_path = session_path.with_name("login-qr.png")
    _emit("没有可用的登录会话，开始获取知乎官方二维码。请用手机知乎 App 扫描。")
    cookie = run_qr_login(
        HttpQrApi(timeout=args.timeout, proxy=args.proxy),
        png_path,
        timeout=args.login_timeout,
        emit=_emit,
        session_path=session_path,
    )
    save_session(session_path, cookie)
    return cookie


def session_still_valid(cookie: str, args: argparse.Namespace, pace: Pace) -> bool:
    client = ZhihuClient(
        cookie,
        pace=pace,
        retries=args.retries,
        timeout=args.timeout,
        proxy=args.proxy,
    )
    try:
        me = client.get_me()
    except ZhihuBlockedError as exc:
        if is_login_failure(exc):
            return False
        raise
    return bool(me.get("name") or me.get("uid") or me.get("id") or me.get("url_token"))


def resolve_cookie(args: argparse.Namespace, pace: Pace) -> str:
    session_path = Path(args.session_file) if args.session_file else default_session_path()
    explicit = load_cookie(args.cookie_file)
    if args.login:
        return login_and_save(args, session_path)
    if explicit:
        _emit("使用命令行或环境变量里的 Cookie，不读取本地扫码会话。")
        return explicit
    saved = load_session(session_path)
    if saved and has_login_cookie(saved):
        _emit(f"检查本地会话：{session_path}")
        if session_still_valid(saved, args, pace):
            _emit("本地会话仍然有效，直接继续。")
            return saved
        _emit("本地会话已过期，需要重新扫码。")
        return login_and_save(args, session_path)
    return login_and_save(args, session_path)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    started = time.time()
    try:
        if args.max_answers is not None and args.max_answers < 1:
            raise ZhihuError("--max-answers 必须是正整数")
        pace = build_pace(args)
        cookie = resolve_cookie(args, pace)
        client = ZhihuClient(
            cookie,
            pace=pace,
            retries=args.retries,
            timeout=args.timeout,
            proxy=args.proxy,
        )
        kind, value = classify_query(args.query)
        if kind == "title":
            candidates = client.search_questions(value)
            chosen = choose_candidate(
                candidates,
                args.pick,
                interactive=sys.stdin.isatty(),
            )
            question_id = chosen["id"]
            _emit(f"使用问题 [{question_id}] {chosen.get('title') or ''}")
        else:
            question_id = value
        question = client.get_question(question_id)
        store = AnswerStore(args.output, question_id)
        written = crawl_answers(
            client,
            store,
            question,
            page_limit=args.page_size,
            max_answers=args.max_answers,
            force=args.force,
            logger=_emit,
        )
    except (ZhihuBlockedError, ZhihuError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中断。已写入的回答和 progress.json 会在下次运行时继续。", file=sys.stderr)
        return 130
    saved = len(store.load_saved_ids())
    total = question.get("answer_count") if isinstance(question.get("answer_count"), int) else None
    print(
        format_summary(
            title=str(question.get("title") or ""),
            question_id=str(question_id),
            written=written,
            saved=saved,
            total=total,
            directory=str(store.directory),
            seconds=time.time() - started,
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
