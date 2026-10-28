"""告警规则测试：校验结构、必填字段与关键告警覆盖。"""

import os

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_PATH = os.path.join(ROOT, "deploy", "alert_rules.yml")


@pytest.fixture(scope="module")
def rules_doc():
    with open(RULES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_rules(doc):
    return [r for g in doc["groups"] for r in g["rules"]]


def test_groups_exist(rules_doc):
    assert len(rules_doc["groups"]) >= 1
    assert len(_all_rules(rules_doc)) == 7


def test_each_alert_has_required_fields(rules_doc):
    for rule in _all_rules(rules_doc):
        assert "alert" in rule
        assert rule.get("expr", "").strip(), f"{rule['alert']} 缺少 expr"
        assert "severity" in rule.get("labels", {}), f"{rule['alert']} 缺少 severity"
        assert "summary" in rule.get("annotations", {}), f"{rule['alert']} 缺少 summary"


def test_expected_alerts_present(rules_doc):
    names = {r["alert"] for r in _all_rules(rules_doc)}
    expected = {
        "AgentSuccessRateLow",     # 成功率
        "LLMP95LatencyHigh",        # P95 耗时
        "ToolP95LatencyHigh",
        "TokenUsageSpike",          # token 暴涨
        "TokenBudgetGuard",
        "ToolFailureRateHigh",
    }
    assert expected.issubset(names)


def test_severity_values_valid(rules_doc):
    allowed = {"critical", "warning", "info"}
    for rule in _all_rules(rules_doc):
        assert rule["labels"]["severity"] in allowed


def test_latency_alerts_have_thresholds(rules_doc):
    # 耗时类告警 expr 中应包含数值阈值（毫秒）
    for rule in _all_rules(rules_doc):
        if "Latency" in rule["alert"]:
            assert any(ch.isdigit() for ch in rule["expr"])
