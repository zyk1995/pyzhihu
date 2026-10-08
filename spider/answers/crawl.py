#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按页拉取回答并立刻落盘，中断后可从进度文件继续。"""

from __future__ import annotations

from collections.abc import Callable

from spider.answers.client import ZhihuClient
from spider.answers.errors import ZhihuBlockedError, ZhihuError
from spider.answers.pace import RequestCapError
from spider.answers.parse import paging_total, parse_answers_page
from spider.answers.progress import format_progress, resume_notice
from spider.answers.storage import AnswerStore


def crawl_answers(
    client: ZhihuClient,
    store: AnswerStore,
    question: dict,
    *,
    page_limit: int = 20,
    max_answers: int | None = None,
    force: bool = False,
    logger: Callable[[str], None] | None = None,
) -> int:
    """抓取问题下的回答。返回本次新写入的条数。"""
    if page_limit < 1 or page_limit > 20:
        raise ZhihuError("每页条数必须在 1 到 20 之间，知乎单页上限是 20")
    log = logger or (lambda _message: None)
    progress = store.load_progress()
    if progress.get("done") and not force:
        log(f"问题 {store.question_id} 已抓取完成。要重新检查请加上 --force")
        return 0
    offset = 0 if force else int(progress.get("next_offset") or 0)
    saved_ids = store.load_saved_ids()
    written = 0
    question_id = str(question.get("id") or store.question_id)
    store.save_question(question)
    log(f"开始抓取问题 {question_id}「{question.get('title') or ''}」，从偏移 {offset} 继续，已有 {len(saved_ids)} 条")

    while True:
        try:
            payload = client.get_answers_page(question_id, offset, page_limit)
        except (ZhihuBlockedError, RequestCapError) as exc:
            store.save_progress(offset, done=False, saved_count=len(saved_ids))
            notice = str(exc) + "\n" + resume_notice(offset)
            if isinstance(exc, ZhihuBlockedError):
                raise ZhihuBlockedError(
                    notice,
                    status_code=exc.status_code,
                    error_code=exc.error_code,
                    body=exc.body,
                ) from exc
            raise RequestCapError(notice) from exc
        total = paging_total(payload)
        if total is not None and question.get("answer_count") in (None, ""):
            question["answer_count"] = total
            store.save_question(question)
        answers, next_offset, is_end = parse_answers_page(payload, question_id, offset, page_limit)
        if not answers:
            done = bool(is_end or next_offset is None)
            store.save_progress(offset, done=done, saved_count=len(saved_ids))
            if done:
                log(f"已到末页，问题 {question_id} 抓取完成")
            else:
                log("本页没有回答，但接口没有声明结束，已停止以免空转。可以稍后重试。")
            break
        fresh = [item for item in answers if item["answer_id"] and item["answer_id"] not in saved_ids]
        if max_answers is not None:
            room = max_answers - written
            if room <= 0:
                store.save_progress(offset, done=False)
                break
            page_complete = len(fresh) <= room
            to_write = fresh if page_complete else fresh[:room]
        else:
            page_complete = True
            to_write = fresh
        for item in to_write:
            store.append_answer(item)
            saved_ids.add(item["answer_id"])
        written += len(to_write)
        total_known = question.get("answer_count") if isinstance(question.get("answer_count"), int) else None
        log(
            format_progress(len(saved_ids), total_known)
            + f"  偏移 {offset}，本页新写入 {len(to_write)} 条，本次累计 {written} 条"
        )
        if not page_complete:
            store.save_progress(offset, done=False, saved_count=len(saved_ids))
            break
        if is_end or next_offset is None:
            store.save_progress(offset, done=True, saved_count=len(saved_ids))
            log(f"已到末页，问题 {question_id} 抓取完成")
            break
        if next_offset <= offset:
            store.save_progress(offset, done=False, saved_count=len(saved_ids))
            log("下一页偏移没有前进，停止以免死循环。可以稍后重试。")
            break
        offset = next_offset
        store.save_progress(offset, done=False, saved_count=len(saved_ids))
        if max_answers is not None and written >= max_answers:
            break
    return written
