"""命令行入口：交互式 REPL / 单次问答。

交互形态唯一入口，换成桌面端或 Web 时只需替换这一层，核心代码不动。
"""

from __future__ import annotations

import argparse

from .bootstrap import create_llm, load_dotenv
from .config import load_config
from .core import DEFAULT_SYSTEM_PROMPT, AgentLoop
from .memory.short_term import ConversationMemory
from .memory.store import JsonSessionStore
from .observability.logger import get_logger, setup_logging
from .tools.registry import ToolRegistry, ToolSpec

DEFAULT_SESSION_PATH = ".sessions/default.json"

logger = get_logger("cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meeting-agent",
        description="会议小助手（CLI）：通用会议问答、纪要整理、待办抽取",
    )
    parser.add_argument("--once", metavar="问题", help="只问一次并退出，不进入交互")
    parser.add_argument("--provider", choices=["echo", "openai_compatible"], help="模型供应商")
    parser.add_argument("--model", help="模型名称")
    parser.add_argument("--base-url", dest="base_url", help="OpenAI 兼容接口地址")
    parser.add_argument("--api-key", dest="api_key", help="接口密钥（也可用环境变量）")
    parser.add_argument("--temperature", type=float, help="采样温度")
    parser.add_argument("--max-steps", type=int, dest="max_steps", help="单轮最大步数")
    parser.add_argument("--session", help=f"会话文件路径，默认 {DEFAULT_SESSION_PATH}")
    parser.add_argument("--log-level", dest="log_level", help="日志级别：DEBUG/INFO/WARNING/ERROR")
    return parser


def confirm_sensitive(spec: ToolSpec, arguments: dict) -> bool:
    """敏感操作的护栏：未获人工确认一律不执行。"""
    print(f"\n[需要确认] 敏感工具 {spec.name} 参数={arguments}")
    try:
        answer = input("是否执行？[y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes"}


def _print_history(memory: ConversationMemory) -> None:
    for index, message in enumerate(memory.messages, start=1):
        prefix = {"user": "你", "assistant": "助手", "tool": "工具", "system": "系统"}.get(
            message.role, message.role
        )
        print(f"{index}. {prefix}: {message.content}")


def run_repl(loop: AgentLoop, memory: ConversationMemory, store: JsonSessionStore | None) -> int:
    print("会议小助手已启动。输入 /help 查看命令，/exit 退出。")
    while True:
        try:
            text = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not text:
            continue
        if text in {"/exit", "/quit"}:
            print("再见。")
            break
        if text == "/help":
            print("命令：/help 帮助  /history 历史  /clear 清空  /save [路径] 保存  /exit 退出")
            continue
        if text == "/history":
            _print_history(memory)
            continue
        if text == "/clear":
            memory.clear()
            print("已清空历史。")
            continue
        if text.startswith("/save"):
            target = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else None
            if store is None and target is None:
                print("未指定会话文件，请用 /save <路径>。")
                continue
            target_store = JsonSessionStore(target) if target else store
            target_store.save(memory.messages)
            print(f"已保存到 {target_store.path}")
            continue

        print(f"\n助手> {loop.run(text)}")

    if store is not None:
        store.save(memory.messages)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()

    config = load_config(
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        temperature=args.temperature,
        max_steps=args.max_steps,
        log_level=args.log_level,
    )
    setup_logging(config.log_level)

    memory = ConversationMemory(max_messages=config.max_history)
    store = JsonSessionStore(args.session or DEFAULT_SESSION_PATH)
    if store.exists():
        for message in store.load():
            memory.add(message)

    loop = AgentLoop(
        llm=create_llm(config),
        memory=memory,
        tools=ToolRegistry(),
        config=config,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        confirm=confirm_sensitive,
        logger=logger.info,
    )

    if args.once:
        print(f"助手> {loop.run(args.once)}")
        store.save(memory.messages)
        return 0

    return run_repl(loop, memory, store)


if __name__ == "__main__":
    raise SystemExit(main())
