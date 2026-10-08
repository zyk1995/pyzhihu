#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令行：python -m spider.answers \"问题标题\""""

from __future__ import annotations

import argparse
import sys

from spider.answers.client import ZhihuClient
from spider.answers.cookie import load_cookie
from spider.answers.crawl import crawl_answers
from spider.answers.errors import ZhihuBlockedError, ZhihuError
from spider.answers.resolve import choose_candidate, classify_query
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
    parser.add_argument("--delay", type=float, default=1.0, help="两次成功请求之间的等待秒数，默认 1")
    parser.add_argument("--retries", type=int, default=4, help="网络错误或 5xx 的重试次数，默认 4")
    parser.add_argument("--timeout", type=float, default=20.0, help="单次请求超时秒数，默认 20")
    parser.add_argument("--page-size", type=int, default=20, help="每页回答数，1 到 20，默认 20")
    parser.add_argument("--max-answers", type=int, default=None, help="最多新写入多少条，默认不限制")
    parser.add_argument("--proxy", default=None, help="可选 HTTP 代理，例如 http://127.0.0.1:7890")
    parser.add_argument("--force", action="store_true", help="忽略已完成标记，从偏移 0 再扫一遍，已保存的回答会跳过")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.max_answers is not None and args.max_answers < 1:
            raise ZhihuError("--max-answers 必须是正整数")
        cookie = load_cookie(args.cookie_file)
        client = ZhihuClient(
            cookie,
            delay=args.delay,
            retries=args.retries,
            timeout=args.timeout,
            proxy=args.proxy,
        )
        if client.generated_d_c0:
            print(
                "没有读到包含 d_c0 的浏览器 Cookie，将只用本地生成的 d_c0 尝试。"
                "知乎目前多半会拒绝。请设置 ZHIHU_COOKIE 或 --cookie-file。",
                file=sys.stderr,
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
            print(
                f"使用问题 [{question_id}] {chosen.get('title') or ''}",
                file=sys.stderr,
            )
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
            logger=lambda message: print(message, file=sys.stderr),
        )
    except (ZhihuBlockedError, ZhihuError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中断。已写入的回答和 progress.json 会在下次运行时继续。", file=sys.stderr)
        return 130
    print(f"本次新写入 {written} 条，目录：{store.directory}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
