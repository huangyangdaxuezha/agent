from meeting_agent.config import Config, load_config


def test_defaults_are_offline_safe():
    config = load_config(env={})
    assert config.provider == "echo"
    assert config.max_steps > 0
    assert config.max_history > 0


def test_reads_environment_with_prefix():
    env = {
        "MEETING_AGENT_PROVIDER": "openai_compatible",
        "MEETING_AGENT_MODEL": "gpt-4o-mini",
        "MEETING_AGENT_BASE_URL": "https://api.example.com/v1",
        "MEETING_AGENT_API_KEY": "sk-test",
        "MEETING_AGENT_TEMPERATURE": "0.9",
        "MEETING_AGENT_MAX_STEPS": "3",
    }
    config = load_config(env=env)
    assert config.provider == "openai_compatible"
    assert config.model == "gpt-4o-mini"
    assert config.temperature == 0.9
    assert config.max_steps == 3


def test_blank_values_fall_back_to_defaults():
    config = load_config(env={"MEETING_AGENT_PROVIDER": "   ", "MEETING_AGENT_MAX_STEPS": "abc"})
    assert config.provider == "echo"
    assert config.max_steps == 8


def test_overrides_ignore_none_values():
    config = load_config(env={"MEETING_AGENT_MODEL": "from-env"}, model=None, provider="echo")
    assert config.model == "from-env"


def test_with_overrides_keeps_immutability():
    original = Config(model="a")
    changed = original.with_overrides(model="b")
    assert original.model == "a"
    assert changed.model == "b"
