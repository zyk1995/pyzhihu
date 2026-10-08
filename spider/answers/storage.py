#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把问题和回答写到以问题 ID 命名的目录。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from spider.answers.parse import ANSWER_FIELDS


class AnswerStore:
    """JSON Lines 与带 BOM 的 CSV 同步追加，并记录分页进度。"""

    def __init__(self, root: str | Path, question_id: str) -> None:
        self.question_id = str(question_id)
        self.directory = Path(root) / self.question_id
        self.directory.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.directory / "answers.jsonl"
        self.csv_path = self.directory / "answers.csv"
        self.question_path = self.directory / "question.json"
        self.progress_path = self.directory / "progress.json"

    def save_question(self, question: dict) -> None:
        self.question_path.write_text(
            json.dumps(question, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def load_question(self) -> dict | None:
        if not self.question_path.exists():
            return None
        return json.loads(self.question_path.read_text(encoding="utf-8"))

    def load_saved_ids(self) -> set[str]:
        saved: set[str] = set()
        if not self.jsonl_path.exists():
            return saved
        with self.jsonl_path.open(encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    saved.add(str(json.loads(text)["answer_id"]))
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
        return saved

    def load_progress(self) -> dict:
        if not self.progress_path.exists():
            return {"question_id": self.question_id, "next_offset": 0, "done": False}
        data = json.loads(self.progress_path.read_text(encoding="utf-8"))
        data.setdefault("next_offset", 0)
        data.setdefault("done", False)
        return data

    def save_progress(self, next_offset: int, *, done: bool, saved_count: int | None = None) -> None:
        if saved_count is None:
            if self.jsonl_path.exists():
                saved_count = sum(
                    1 for line in self.jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()
                )
            else:
                saved_count = 0
        payload = {
            "question_id": self.question_id,
            "next_offset": next_offset,
            "done": done,
            "saved_count": saved_count,
        }
        self.progress_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def append_answer(self, answer: dict) -> None:
        with self.jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(answer, ensure_ascii=False) + "\n")
        new_file = not self.csv_path.exists() or self.csv_path.stat().st_size == 0
        # 只有新建文件时写 BOM。追加模式再用 utf-8-sig 会把 BOM 写进文件中间。
        encoding = "utf-8-sig" if new_file else "utf-8"
        with self.csv_path.open("a", encoding=encoding, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(ANSWER_FIELDS), extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow({field: answer.get(field, "") for field in ANSWER_FIELDS})
