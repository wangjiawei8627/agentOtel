"""质量评估测试。"""

import pytest

from agentotel.quality import (
    RuleBasedQualityEvaluator,
    LLMJudgeEvaluator,
    QualitySignals,
)


def test_perfect_run():
    ev = RuleBasedQualityEvaluator()
    r = ev.evaluate(QualitySignals(success=True, tool_calls=2, tool_errors=0))
    assert r.score == 100.0
    assert r.grade == "A"
    assert r.deductions == {}


def test_failed_task_heavily_penalized():
    ev = RuleBasedQualityEvaluator()
    r = ev.evaluate(QualitySignals(success=False))
    assert r.score <= 60
    assert "task_failed" in r.deductions


def test_tool_failure_rate_penalty():
    ev = RuleBasedQualityEvaluator()
    # 一半工具失败
    r = ev.evaluate(QualitySignals(tool_calls=10, tool_errors=5))
    assert "tool_failure_rate" in r.deductions
    assert r.score < 100


def test_too_many_rounds_penalty():
    ev = RuleBasedQualityEvaluator(max_expected_rounds=3)
    r = ev.evaluate(QualitySignals(rounds=10))
    assert "too_many_rounds" in r.deductions


def test_negative_feedback_penalty():
    ev = RuleBasedQualityEvaluator()
    r = ev.evaluate(QualitySignals(user_feedback="negative"))
    assert "negative_feedback" in r.deductions
    assert r.score == 90


def test_score_clamped():
    ev = RuleBasedQualityEvaluator()
    r = ev.evaluate(QualitySignals(
        success=False, agent_errors=100, tool_calls=10,
        tool_errors=10, rounds=100, user_feedback="negative"))
    assert 0.0 <= r.score <= 100.0


def test_grade_boundaries():
    ev = RuleBasedQualityEvaluator()
    assert ev.evaluate(QualitySignals()).grade == "A"
    # 构造 B：失败 40 分 -> 60 分 C
    r = ev.evaluate(QualitySignals(success=False))
    assert r.grade in {"C", "D"}


def test_llm_judge():
    ev = LLMJudgeEvaluator(judge_fn=lambda i, o: 85.0)
    r = ev.evaluate(QualitySignals(), "q", "a")
    assert r.score == 85.0


def test_llm_judge_failure_caps():
    def bad(i, o):
        raise RuntimeError("judge down")
    ev = LLMJudgeEvaluator(judge_fn=bad)
    r = ev.evaluate(QualitySignals(success=True), "q", "a")
    assert "judge_error" in r.deductions


def test_llm_judge_failed_task_capped():
    ev = LLMJudgeEvaluator(judge_fn=lambda i, o: 99.0)
    r = ev.evaluate(QualitySignals(success=False), "q", "a")
    assert r.score <= 40.0
