#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端进度和结束摘要。"""

from __future__ import annotations


def format_progress(saved: int, total: int | None) -> str:
    if isinstance(total, int) and total > 0:
        ratio = min(1.0, saved / total)
        width = 20
        filled = int(round(ratio * width))
        bar = "█" * filled + "░" * (width - filled)
        return f"进度 {saved}/{total} {bar} {ratio:.0%}"
    return f"进度 {saved} 条（总数未知）"


def format_summary(
    *,
    title: str,
    question_id: str,
    written: int,
    saved: int,
    total: int | None,
    directory: str,
    seconds: float,
) -> str:
    lines = [
        "抓取结束",
        f"问题：{title or '（无标题）'}（{question_id}）",
        f"本次新写入：{written} 条",
        f"目录中共有：{saved} 条",
    ]
    if isinstance(total, int):
        lines.append(f"问题回答总数：{total}")
    lines.append(f"输出目录：{directory}")
    lines.append(f"耗时：{seconds:.1f} 秒")
    return "\n".join(lines)


def resume_notice(offset: int) -> str:
    return (
        f"已停止继续请求，没有接着打接口。进度已保存，下次从偏移 {offset} 继续。"
        "直接重新执行同一条命令即可续传。"
    )
