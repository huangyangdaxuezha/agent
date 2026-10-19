"""可观测层：统一日志配置。Agent 出问题时没有日志几乎无法排查。"""

from __future__ import annotations

import logging

PACKAGE_LOGGER = "meeting_agent"


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, str(level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def get_logger(name: str) -> logging.Logger:
    suffix = name.replace(f"{PACKAGE_LOGGER}.", "")
    return logging.getLogger(f"{PACKAGE_LOGGER}.{suffix}")
