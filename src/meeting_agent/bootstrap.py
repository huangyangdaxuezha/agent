"""入口层共用逻辑：加载 .env、创建模型客户端。

CLI（cli.py）与 Web（api.py）都从这里取，避免出现两份互相漂移的实现。
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import Config
from .llm import EchoLLM, OpenAICompatibleClient


def load_dotenv(path: str | Path = ".env") -> None:
    """极简 .env 加载：只补充尚未设置的环境变量，避免覆盖真实环境。"""
    file = Path(path)
    if not file.exists():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def create_llm(config: Config) -> EchoLLM | OpenAICompatibleClient:
    if config.provider == "openai_compatible":
        return OpenAICompatibleClient(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            temperature=config.temperature,
        )
    return EchoLLM(model=config.model)
