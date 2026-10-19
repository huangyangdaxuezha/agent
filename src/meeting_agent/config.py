"""配置加载：统一从环境变量（或注入的字典）读取，避免 Key 散落各处。

环境变量前缀：MEETING_AGENT_
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

ENV_PREFIX = "MEETING_AGENT_"
DEFAULT_PROVIDER = "echo"


@dataclass(frozen=True)
class Config:
    provider: str = DEFAULT_PROVIDER
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    temperature: float = 0.3
    max_steps: int = 5
    max_history: int = 40
    log_level: str = "INFO"

    def with_overrides(self, **overrides: object) -> "Config":
        """返回只覆盖非 None 字段的新配置，保持原配置不可变。"""
        values = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **values)


def _read_str(env: Mapping[str, str], key: str, default: str) -> str:
    value = env.get(ENV_PREFIX + key)
    return value.strip() if isinstance(value, str) and value.strip() else default


def _read_number(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(ENV_PREFIX + key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        return default


def load_config(env: Mapping[str, str] | None = None, **overrides: object) -> Config:
    """读取配置。env 缺省使用 os.environ，便于测试注入。

    overrides 中值为 None 的项会被忽略，用于“命令行未指定时不覆盖环境变量”的场景。
    """
    import os

    source = os.environ if env is None else env
    config = Config(
        provider=_read_str(source, "PROVIDER", DEFAULT_PROVIDER),
        model=_read_str(source, "MODEL", ""),
        base_url=_read_str(source, "BASE_URL", ""),
        api_key=_read_str(source, "API_KEY", ""),
        temperature=_read_number(source, "TEMPERATURE", 0.3),
        # 至少允许 1 步，避免误配成 0/负数后一轮对话什么都不做
        max_steps=max(1, int(_read_number(source, "MAX_STEPS", 5))),
        max_history=int(_read_number(source, "MAX_HISTORY", 40)),
        log_level=_read_str(source, "LOG_LEVEL", "INFO"),
    )
    return config.with_overrides(**overrides)
