# -*- coding: utf-8 -*-
"""Agent 质量评估器。

提供两类评估：
- ``RuleBasedQualityEvaluator``：基于可观测信号（成功/错误/工具失败率/轮次）
  计算 0-100 分，零依赖、可解释，默认使用。
- ``LLMJudgeEvaluator``：注入一个 judge 函数（通常是更强的 LLM），
  对「输入 + 输出」做语义打分，适合评估相关性/幻觉等内容质量。

评估结果可通过 ``MetricsReporter.record_quality`` 上报，
在 Grafana 形成质量趋势。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional


@dataclass
class QualitySignals:
    """一次 Agent 运行的可观测信号（由埋点链路汇总）。"""

    success: bool = True
    llm_calls: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    agent_errors: int = 0
    rounds: int = 0
    latency_ms: float = 0.0
    # 可选用户反馈：positive / negative
    user_feedback: Optional[str] = None


@dataclass
class QualityResult:
    """评估结果。"""

    score: float
    grade: str
    signals: QualitySignals
    # 各维度扣分明细（可解释：为什么扣分）
    deductions: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "grade": self.grade,
            "deductions": self.deductions,
        }


def _grade(score: float) -> str:
    """分数转等级。"""
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    return "D"


class BaseQualityEvaluator:
    """评估器基类。"""

    name = "base"

    def evaluate(self, signals: QualitySignals,
                 user_input: str = "", output: str = "") -> QualityResult:
        raise NotImplementedError


class RuleBasedQualityEvaluator(BaseQualityEvaluator):
    """规则评估：从可靠性与效率两个维度打分。"""

    name = "rule"

    def __init__(self,
                 max_expected_rounds: int = 6,
                 error_penalty: float = 15.0,
                 failure_rate_weight: float = 30.0,
                 round_penalty: float = 3.0) -> None:
        self.max_expected_rounds = max_expected_rounds
        self.error_penalty = error_penalty
        self.failure_rate_weight = failure_rate_weight
        self.round_penalty = round_penalty

    def evaluate(self, signals: QualitySignals,
                 user_input: str = "", output: str = "") -> QualityResult:
        score = 100.0
        deductions: Dict[str, float] = {}

        # 1) 未成功完成：重扣
        if not signals.success:
            deductions["task_failed"] = 40.0
            score -= 40.0

        # 2) Agent 内部错误：每个错误扣分
        if signals.agent_errors:
            pen = min(30.0, signals.agent_errors * self.error_penalty)
            deductions["agent_errors"] = pen
            score -= pen

        # 3) 工具失败率：失败率越高扣分越多
        if signals.tool_calls:
            failure_rate = signals.tool_errors / signals.tool_calls
            if failure_rate > 0:
                pen = round(failure_rate * self.failure_rate_weight, 1)
                deductions["tool_failure_rate"] = pen
                score -= pen

        # 4) 效率：轮次超过预期，每多一轮扣分（疑似绕路/循环）
        if signals.rounds > self.max_expected_rounds:
            extra = signals.rounds - self.max_expected_rounds
            pen = min(15.0, extra * self.round_penalty)
            deductions["too_many_rounds"] = pen
            score -= pen

        # 5) 负反馈额外扣分
        if signals.user_feedback == "negative":
            deductions["negative_feedback"] = 10.0
            score -= 10.0

        score = max(0.0, min(100.0, round(score, 1)))
        return QualityResult(
            score=score, grade=_grade(score),
            signals=signals, deductions=deductions,
        )


# judge 函数签名：(user_input, output) -> 0-100 分数
JudgeFn = Callable[[str, str], float]


class LLMJudgeEvaluator(BaseQualityEvaluator):
    """LLM 裁判评估：注入 judge 函数，对内容质量打分。

    judge 函数可由调用方实现（调用更强模型，按相关性/忠实度/完整性
    给出分数），框架不绑定具体模型。
    """

    name = "llm_judge"

    def __init__(self, judge_fn: JudgeFn) -> None:
        self.judge_fn = judge_fn

    def evaluate(self, signals: QualitySignals,
                 user_input: str = "", output: str = "") -> QualityResult:
        deductions: Dict[str, float] = {}
        try:
            score = float(self.judge_fn(user_input, output))
        except Exception as exc:
            # judge 失败时降级为规则评估
            deductions["judge_error"] = str(exc)
            score = 0.0
        score = max(0.0, min(100.0, score))
        # 任务失败硬性拉低
        if not signals.success:
            score = min(score, 40.0)
        return QualityResult(
            score=round(score, 1), grade=_grade(score),
            signals=signals, deductions=deductions,
        )
#（注：内容由AI生成）
