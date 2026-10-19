import os

from meeting_agent import cli
from meeting_agent.cli import build_parser, confirm_sensitive, create_llm, load_dotenv, main
from meeting_agent.config import Config
from meeting_agent.llm import EchoLLM, OpenAICompatibleClient
from meeting_agent.tools.registry import ToolSpec


def test_parser_defaults():
    args = build_parser().parse_args([])
    assert args.once is None
    assert args.provider is None


def test_parser_reads_options():
    args = build_parser().parse_args(
        ["--once", "总结会议", "--model", "m1", "--max-steps", "5", "--base-url", "https://x/v1"]
    )
    assert args.once == "总结会议"
    assert args.model == "m1"
    assert args.max_steps == 5
    assert args.base_url == "https://x/v1"


def test_create_llm_echo_by_default():
    assert isinstance(create_llm(Config(provider="echo")), EchoLLM)


def test_create_llm_http_provider():
    llm = create_llm(
        Config(provider="openai_compatible", model="m", base_url="https://x/v1", api_key="k")
    )
    assert isinstance(llm, OpenAICompatibleClient)


def test_confirm_sensitive_accepts_yes(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert confirm_sensitive(ToolSpec(name="d", sensitive=True), {"path": "a"}) is True
    assert "[需要确认]" in capsys.readouterr().out


def test_confirm_sensitive_rejects_other_answers(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert confirm_sensitive(ToolSpec(name="d", sensitive=True), {}) is False


def test_confirm_sensitive_rejects_on_interrupt(monkeypatch):
    def raise_eof(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert confirm_sensitive(ToolSpec(name="d", sensitive=True), {}) is False


def test_load_dotenv_fills_missing_only(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "# 注释\nMEETING_AGENT_MODEL=from-file\nMEETING_AGENT_PROVIDER=echo\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_AGENT_MODEL", "already-set")

    load_dotenv()

    assert os.environ["MEETING_AGENT_MODEL"] == "already-set"
    assert os.environ["MEETING_AGENT_PROVIDER"] == "echo"


def test_load_dotenv_missing_file_is_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    load_dotenv()


def test_main_once_prints_answer(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_AGENT_PROVIDER", "echo")

    exit_code = main(["--once", "帮我整理会议纪要"])

    assert exit_code == 0
    assert "助手>" in capsys.readouterr().out
    assert (tmp_path / ".sessions" / "default.json").exists()


def test_main_repl_exits_and_saves(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MEETING_AGENT_PROVIDER", "echo")
    answers = iter(["/help", "/history", "你好", "/exit"])

    def fake_input(_):
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)

    assert main([]) == 0
    assert (tmp_path / ".sessions" / "default.json").exists()
    assert "会议小助手已启动" in capsys.readouterr().out


def test_cli_module_has_main():
    assert callable(cli.main)
