#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""识别用户输入是标题、链接还是问题 ID，并在多个结果里做选择。"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable

from spider.answers.errors import ZhihuError

_QUESTION_URL = re.compile(r"zhihu\.com/question/(\d+)", re.IGNORECASE)
_NUMERIC_ID = re.compile(r"^\d+$")


def classify_query(text: str) -> tuple[str, str]:
    """返回 ``("id", 问题ID)`` 或 ``("title", 标题)``。"""
    query = (text or "").strip()
    if not query:
        raise ZhihuError("请提供问题标题、问题链接或数字 ID")
    matched = _QUESTION_URL.search(query)
    if matched:
        return "id", matched.group(1)
    if _NUMERIC_ID.fullmatch(query):
        return "id", query
    return "title", query


def format_candidates(candidates: list[dict]) -> str:
    lines = []
    for index, item in enumerate(candidates, start=1):
        title = item.get("title") or "(无标题)"
        lines.append(
            f"{index}. [{item.get('id')}] {title}"
            f"  回答 {item.get('answer_count')}  关注 {item.get('follower_count')}"
        )
    return "\n".join(lines)


def choose_candidate(
    candidates: list[dict],
    pick: int | None = None,
    *,
    interactive: bool = False,
    input_func: Callable[[str], str] | None = None,
    output: Callable[[str], None] | None = None,
) -> dict:
    """多个搜索结果时列出候选。不在交互终端里静默猜一个。"""
    if not candidates:
        raise ZhihuError("没有搜到标题对应的问题")
    if pick is None and len(candidates) == 1:
        return candidates[0]
    if pick is not None:
        if pick < 1 or pick > len(candidates):
            raise ZhihuError(f"--pick 必须是 1 到 {len(candidates)} 之间的整数")
        return candidates[pick - 1]
    message = "搜索到多个问题，请用 --pick N 选择序号：\n" + format_candidates(candidates)
    if output is not None:
        output(message)
    else:
        print(message, file=sys.stderr)
    if not interactive:
        raise ZhihuError("当前不是交互终端，请加上 --pick N 后再运行")
    reader = input_func or input
    raw = reader("请输入序号: ").strip()
    if not raw.isdigit():
        raise ZhihuError("请输入候选列表中的数字序号")
    selected = int(raw)
    if selected < 1 or selected > len(candidates):
        raise ZhihuError(f"序号必须是 1 到 {len(candidates)} 之间的整数")
    return candidates[selected - 1]
