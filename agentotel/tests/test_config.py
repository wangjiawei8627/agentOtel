"""配置模块测试。"""

import os

from agentotel.config import AgentOTelConfig, _env_bool


def test_defaults():
    cfg = AgentOTelConfig()
    assert cfg.service_name == "agentotel-app"
    assert cfg.sampler_ratio == 1.0
    # 合规相关默认关闭
    assert cfg.capture_message_content is False
    assert cfg.capture_tool_content is False
    assert cfg.pii_mask_enabled is False


def test_config_is_frozen():
    cfg = AgentOTelConfig()
    import pytest
    with pytest.raises(Exception):
        cfg.service_name = "hack"


def test_env_bool():
    os.environ["TMP_BOOL"] = "true"
    assert _env_bool("TMP_BOOL", False) is True
    os.environ["TMP_BOOL"] = "0"
    assert _env_bool("TMP_BOOL", True) is False
    assert _env_bool("TMP_MISSING", True) is True


def test_from_env(monkeypatch):
    monkeypatch.setenv("AGENTOTEL_SERVICE_NAME", "from-env")
    monkeypatch.setenv("AGENTOTEL_SAMPLER_RATIO", "0.3")
    monkeypatch.setenv("AGENTOTEL_PII_MASK", "true")
    cfg = AgentOTelConfig.from_env()
    assert cfg.service_name == "from-env"
    assert cfg.sampler_ratio == 0.3
    assert cfg.pii_mask_enabled is True


def test_from_env_override_wins(monkeypatch):
    monkeypatch.setenv("AGENTOTEL_SERVICE_NAME", "from-env")
    cfg = AgentOTelConfig.from_env(service_name="explicit")
    assert cfg.service_name == "explicit"
