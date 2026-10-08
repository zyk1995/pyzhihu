#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把知乎接口 JSON 解析成稳定字段。不发起网络请求。"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

ANSWER_FIELDS = (
    "answer_id",
    "author_name",
    "author_url_token",
    "content_text",
    "content_html",
    "voteup_count",
    "comment_count",
    "created_time",
    "updated_time",
    "answer_url",
    "question_id",
)


def html_to_text(html: str) -> str:
    """把回答 HTML 收成保留段落的纯文本。"""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "div", "li", "tr", "h1", "h2", "h3", "h4", "blockquote", "pre", "figure"]):
        block.insert_after("\n")
    text = soup.get_text("")
    lines = []
    for line in text.splitlines():
        cleaned = re.sub(r"[ \t\r\f\v]+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def answer_url(question_id: str, answer_id: str) -> str:
    return f"https://www.zhihu.com/question/{question_id}/answer/{answer_id}"


def parse_answer(raw: dict, question_id: str) -> dict:
    """抽出一条回答。缺字段时用空字符串或 0，避免写入失败。"""
    author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
    content_html = raw.get("content") or ""
    if not isinstance(content_html, str):
        content_html = str(content_html)
    answer_id = str(raw.get("id") or "")
    question = str(question_id)
    return {
        "answer_id": answer_id,
        "author_name": author.get("name") or "",
        "author_url_token": author.get("url_token") or "",
        "content_text": html_to_text(content_html),
        "content_html": content_html,
        "voteup_count": raw.get("voteup_count") or 0,
        "comment_count": raw.get("comment_count") or 0,
        "created_time": raw.get("created_time"),
        "updated_time": raw.get("updated_time"),
        "answer_url": answer_url(question, answer_id) if answer_id else "",
        "question_id": question,
    }


def parse_question(payload: dict, fallback_id: str = "") -> dict:
    """解析问题详情。有的接口把对象包在 data 里。"""
    raw = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(raw, dict):
        raw = {}
    question_id = str(raw.get("id") or fallback_id or "")
    return {
        "id": question_id,
        "title": raw.get("title") or raw.get("name") or "",
        "answer_count": raw.get("answer_count"),
        "follower_count": raw.get("follower_count"),
        "url": f"https://www.zhihu.com/question/{question_id}" if question_id else "",
    }


def _question_record(raw: dict) -> dict | None:
    question_id = str(raw.get("id") or "")
    if not question_id.isdigit():
        return None
    return {
        "id": question_id,
        "title": raw.get("title") or raw.get("name") or "",
        "answer_count": raw.get("answer_count"),
        "follower_count": raw.get("follower_count"),
        "url": raw.get("url") or f"https://www.zhihu.com/question/{question_id}",
    }


def _merge_question(current: dict, incoming: dict) -> dict:
    merged = dict(current)
    for key, value in incoming.items():
        if merged.get(key) in (None, "") and value not in (None, ""):
            merged[key] = value
    return merged


def parse_search_questions(payload: dict, limit: int = 10) -> list[dict]:
    """从搜索结果里抽出问题，按出现顺序去重。"""
    found: dict[str, dict] = {}
    order: list[str] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        obj = item.get("object") if isinstance(item.get("object"), dict) else item
        pieces: list[dict] = []
        if obj.get("type") == "question":
            pieces.append(obj)
        nested = obj.get("question")
        if isinstance(nested, dict):
            pieces.append(nested)
        for piece in pieces:
            record = _question_record(piece)
            if record is None:
                continue
            question_id = record["id"]
            if question_id not in found:
                found[question_id] = record
                order.append(question_id)
            else:
                found[question_id] = _merge_question(found[question_id], record)
            if len(order) >= limit:
                return [found[question_id] for question_id in order]
    return [found[question_id] for question_id in order]


def parse_answers_page(
    payload: dict,
    question_id: str,
    offset: int,
    limit: int,
) -> tuple[list[dict], int | None, bool]:
    """解析一页回答。

    返回 ``(回答列表, 下一页偏移, 是否已经到末页)``。
    ``is_end`` 为真时下一页偏移为 None。
    """
    answers = []
    for item in payload.get("data") or []:
        if isinstance(item, dict):
            answers.append(parse_answer(item, question_id))
    paging = payload.get("paging") if isinstance(payload.get("paging"), dict) else {}
    if paging.get("is_end"):
        return answers, None, True
    next_offset = _offset_from_next(paging.get("next"))
    if next_offset is None:
        next_offset = offset + limit
    return answers, next_offset, False


def _offset_from_next(next_url: object) -> int | None:
    if not isinstance(next_url, str) or not next_url:
        return None
    query = parse_qs(urlparse(next_url).query)
    values = query.get("offset") or []
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


def paging_total(payload: dict) -> int | None:
    paging = payload.get("paging") if isinstance(payload.get("paging"), dict) else {}
    total = paging.get("totals")
    if isinstance(total, int):
        return total
    return None
