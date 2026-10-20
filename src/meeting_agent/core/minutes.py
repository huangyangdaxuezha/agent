"""原文 → 会议纪要：提示词、JSON 校验、失败重试与降级。

原文只用于生成，不落库；生成结果交给仓储持久化。
模型不总是输出合法 JSON，这里保证：解析失败最多重试一次，仍失败则整段降级保存，
**绝不丢失用户粘贴的内容**。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..llm.base import LLMClient, LLMError
from .types import Message

MINUTES_SYSTEM_PROMPT = (
    "你是会议纪要助手。根据用户提供的会议原文，输出严格符合下列结构的 JSON，"
    "不要输出 JSON 之外的任何内容：\n"
    '{"title": "会议标题", '
    '"summary": "一句话摘要", '
    '"content": "Markdown 纪要正文：结论 / 待办 / 风险与分歧（缺失项请写明缺失）", '
    '"todos": [{"content": "待办内容", "owner": "负责人", "due_date": "截止时间"}]}\n'
    "要求：只基于原文，不编造未提及的信息；负责人与截止时间缺失时填空字符串。"
)

RETRY_HINT = "上一次输出无法解析为 JSON（错误：{error}）。请只输出 JSON，不要加说明或代码块。"

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


@dataclass(frozen=True)
class MinutesDraft:
    title: str
    summary: str
    content: str
    todos: list[dict] = field(default_factory=list)
    structured: bool = True
    note: str = ""


def extract_json(text: str) -> dict | None:
    """从模型输出里抠出第一个 JSON 对象，容忍 ```json 代码块和前后废话。"""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"```\s*$", "", cleaned)
    match = _JSON_BLOCK.search(cleaned)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def normalize_todos(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    result: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            result.append(
                {
                    "content": str(item.get("content", "")).strip(),
                    "owner": str(item.get("owner", "")).strip(),
                    "due_date": str(item.get("due_date", "")).strip(),
                }
            )
        elif isinstance(item, str) and item.strip():
            result.append({"content": item.strip(), "owner": "", "due_date": ""})
    return [item for item in result if item["content"]]


def fallback_title(raw_text: str, limit: int = 30) -> str:
    first_line = next((line.strip() for line in raw_text.splitlines() if line.strip()), "")
    title = first_line or "未命名会议"
    return title[:limit]


class MinutesGenerator:
    def __init__(self, llm: LLMClient, max_attempts: int = 2) -> None:
        self.llm = llm
        self.max_attempts = max(1, max_attempts)

    def generate(self, raw_text: str) -> MinutesDraft:
        messages = [
            Message(role="system", content=MINUTES_SYSTEM_PROMPT),
            Message(role="user", content=raw_text),
        ]
        last_output = ""
        last_error = "模型未返回内容"

        for attempt in range(1, self.max_attempts + 1):
            if attempt > 1:
                messages.append(Message(role="assistant", content=last_output))
                messages.append(
                    Message(role="user", content=RETRY_HINT.format(error=last_error))
                )
            try:
                response = self.llm.chat(messages)
            except LLMError as exc:
                last_output, last_error = "", f"模型调用失败：{exc}"
                break

            last_output = response.content or ""
            data = extract_json(last_output)
            if data is None:
                last_error = "未找到合法的 JSON 对象"
                continue
            title = str(data.get("title", "")).strip()
            content = str(data.get("content", "")).strip()
            if not title or not content:
                last_error = "JSON 缺少 title 或 content"
                continue
            return MinutesDraft(
                title=title,
                summary=str(data.get("summary", "")).strip(),
                content=content,
                todos=normalize_todos(data.get("todos")),
                structured=True,
            )

        # 降级：整段文本原样保留，绝不丢用户输入
        body = last_output.strip() or raw_text.strip()
        return MinutesDraft(
            title=fallback_title(raw_text),
            summary="",
            content=body,
            todos=[],
            structured=False,
            note=f"未结构化（{last_error}），已原文保存",
        )
