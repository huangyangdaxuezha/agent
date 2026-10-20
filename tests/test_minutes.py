import json

from meeting_agent.core.minutes import (
    MinutesGenerator,
    extract_json,
    fallback_title,
    normalize_todos,
)
from meeting_agent.core.types import LLMResponse

from .fakes import ExplodingLLM, FakeLLM

VALID_JSON = json.dumps(
    {
        "title": "产品周会",
        "summary": "确定上线时间",
        "content": "## 结论\n下周一上线",
        "todos": [{"content": "准备材料", "owner": "张三", "due_date": "2026-10-25"}],
    },
    ensure_ascii=False,
)


def test_extract_json_from_code_block():
    text = '好的：\n```json\n{"title": "a", "content": "b"}\n```'
    assert extract_json(text) == {"title": "a", "content": "b"}


def test_extract_json_with_surrounding_text():
    assert extract_json('说明一下 {"title": "a", "content": "b"} 结束')["title"] == "a"


def test_extract_json_returns_none_for_garbage():
    assert extract_json("这不是 JSON") is None
    assert extract_json("") is None


def test_normalize_todos_accepts_dicts_and_strings():
    result = normalize_todos(
        [{"content": "写文档", "owner": "李四", "due_date": ""}, "买咖啡", {"content": "  "}]
    )
    assert result == [
        {"content": "写文档", "owner": "李四", "due_date": ""},
        {"content": "买咖啡", "owner": "", "due_date": ""},
    ]


def test_fallback_title_uses_first_non_empty_line():
    assert fallback_title("\n\n产品周会 2026\n内容") == "产品周会 2026"
    assert fallback_title("   ") == "未命名会议"


def test_generate_parses_valid_json():
    llm = FakeLLM([LLMResponse(content=VALID_JSON)])
    draft = MinutesGenerator(llm).generate("原文内容")

    assert draft.structured is True
    assert draft.title == "产品周会"
    assert draft.todos[0]["owner"] == "张三"
    assert llm.call_count == 1


def test_generate_retries_once_after_bad_json():
    llm = FakeLLM([LLMResponse(content="我先想想…"), LLMResponse(content=VALID_JSON)])
    draft = MinutesGenerator(llm).generate("原文内容")

    assert draft.structured is True
    assert llm.call_count == 2


def test_generate_falls_back_without_losing_content():
    llm = FakeLLM([LLMResponse(content="模型胡言乱语"), LLMResponse(content="还是不行")])
    draft = MinutesGenerator(llm).generate("原始会议记录")

    assert draft.structured is False
    assert draft.note
    # 降级时优先保留模型最后一次输出，用户粘贴的内容不会凭空消失在流程外
    assert draft.content == "还是不行"
    assert draft.title == "原始会议记录"


def test_generate_falls_back_to_raw_text_when_model_returns_nothing():
    llm = FakeLLM([LLMResponse(content="")])
    draft = MinutesGenerator(llm).generate("原始会议记录")

    assert draft.structured is False
    assert draft.content == "原始会议记录"


def test_generate_handles_model_error():
    draft = MinutesGenerator(ExplodingLLM()).generate("原始会议记录")

    assert draft.structured is False
    assert draft.content == "原始会议记录"
    assert "模型调用失败" in draft.note
