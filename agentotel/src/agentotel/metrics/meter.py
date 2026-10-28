"""OTel Metrics 上报器。

设计要点：
- 指标名用下划线且已含单位（``_ms``），这样经 Prometheus exporter 后
  得到确定的名字：Counter 加 ``_total``、Histogram 加 ``_bucket``。
- 指标全部通过 OTLP 周期上报给 Collector，再由 Collector 的
  prometheus exporter 暴露给 Prometheus 抓取。
- Reporter 提供语义化方法，Instrumentor 一处调用即可，异常不影响主流程。

最终 Prometheus 指标：
    agentotel_llm_tokens_total{type,model,provider}
    agentotel_llm_duration_ms_bucket{model,provider}
    agentotel_tool_calls_total{tool,type,status}
    agentotel_tool_duration_ms_bucket{tool}
    agentotel_agent_calls_total{agent,status}
    agentotel_agent_duration_ms_bucket{agent}
    agentotel_retrieval_duration_ms_bucket{data_source}
    agentotel_retrieval_doc_count_bucket{data_source}
"""

from __future__ import annotations

from typing import Optional

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

# 状态取值统一用这两个字符串，保证 Dashboard 聚合口径一致
STATUS_OK = "ok"
STATUS_ERROR = "error"


class MetricsReporter:
    """持有 Meter 与全部指标仪器，提供记录方法。"""

    def __init__(self, config, resource, metric_reader=None) -> None:
        self.config = config

        # 允许注入 reader（测试用 InMemoryMetricReader，避免网络与后台线程）；
        # 未注入时默认走 OTLP 周期导出。
        if metric_reader is None:
            # 周期导出 reader：每 15s 把指标通过 OTLP 发给 collector
            exporter = OTLPMetricExporter(
                endpoint=config.otlp_endpoint,
                insecure=config.insecure,
            )
            metric_reader = PeriodicExportingMetricReader(
                exporter,
                export_interval_millis=15000,
            )
        self.provider = MeterProvider(metric_readers=[metric_reader], resource=resource)
        try:
            metrics.set_meter_provider(self.provider)
        except Exception:
            pass

        self.meter = self.provider.get_meter(
            "agentotel",
            schema_url="https://opentelemetry.io/schemas/1.30.0",
        )
        self._init_instruments()

    # ------------------------------------------------------------------
    def _init_instruments(self) -> None:
        """创建全部 Counter / Histogram。"""
        # LLM
        self.llm_tokens = self.meter.create_counter(
            name="agentotel_llm_tokens",
            description="Number of LLM tokens consumed",
        )
        self.llm_duration = self.meter.create_histogram(
            name="agentotel_llm_duration_ms",
            description="LLM call duration in milliseconds",
        )
        # Tool
        self.tool_calls = self.meter.create_counter(
            name="agentotel_tool_calls",
            description="Number of tool calls by status",
        )
        self.tool_duration = self.meter.create_histogram(
            name="agentotel_tool_duration_ms",
            description="Tool execution duration in milliseconds",
        )
        # Agent（整体）
        self.agent_calls = self.meter.create_counter(
            name="agentotel_agent_calls",
            description="Number of agent runs by status",
        )
        self.agent_duration = self.meter.create_histogram(
            name="agentotel_agent_duration_ms",
            description="Agent end-to-end duration in milliseconds",
        )
        # Retrieval
        self.retrieval_duration = self.meter.create_histogram(
            name="agentotel_retrieval_duration_ms",
            description="Retrieval duration in milliseconds",
        )
        self.retrieval_doc_count = self.meter.create_histogram(
            name="agentotel_retrieval_doc_count",
            description="Number of retrieved documents",
        )
        # HTTP（网关侧）
        self.http_calls = self.meter.create_counter(
            name="agentotel_http_calls",
            description="Number of HTTP requests by status",
        )
        self.http_duration = self.meter.create_histogram(
            name="agentotel_http_duration_ms",
            description="HTTP request duration in milliseconds",
        )
        # Quality（质量评估）
        self.quality_score = self.meter.create_histogram(
            name="agentotel_quality_score",
            description="Agent answer quality score (0-100)",
        )
        self.quality_feedback = self.meter.create_counter(
            name="agentotel_quality_feedback",
            description="User feedback counts by sentiment",
        )

    # ------------------------------------------------------------------
    # 语义化记录方法（每个都做异常兜底，绝不影响业务）
    # ------------------------------------------------------------------
    def record_llm(self,
                   model: str,
                   provider: str,
                   input_tokens: int = 0,
                   output_tokens: int = 0,
                   duration_ms: float = 0.0,
                   status: str = STATUS_OK) -> None:
        """记录一次 LLM 调用：token 与耗时。"""
        try:
            attrs = {"model": model, "provider": provider}
            if input_tokens:
                self.llm_tokens.add(input_tokens, {**attrs, "type": "input"})
            if output_tokens:
                self.llm_tokens.add(output_tokens, {**attrs, "type": "output"})
            self.llm_duration.record(duration_ms, attrs)
        except Exception:
            pass

    def record_tool(self,
                    tool_name: str,
                    tool_type: str = "function",
                    duration_ms: float = 0.0,
                    status: str = STATUS_OK) -> None:
        """记录一次工具调用：状态计数与耗时。"""
        try:
            attrs = {"tool": tool_name, "type": tool_type, "status": status}
            self.tool_calls.add(1, attrs)
            self.tool_duration.record(duration_ms, {"tool": tool_name})
        except Exception:
            pass

    def record_agent(self,
                     agent_name: str,
                     duration_ms: float = 0.0,
                     status: str = STATUS_OK) -> None:
        """记录一次 Agent 整体运行。"""
        try:
            attrs = {"agent": agent_name, "status": status}
            self.agent_calls.add(1, attrs)
            self.agent_duration.record(duration_ms, {"agent": agent_name})
        except Exception:
            pass

    def record_retrieval(self,
                         data_source: str,
                         duration_ms: float = 0.0,
                         doc_count: int = 0,
                         status: str = STATUS_OK) -> None:
        """记录一次检索：耗时与召回文档数。"""
        try:
            attrs = {"data_source": data_source, "status": status}
            self.retrieval_duration.record(duration_ms, attrs)
            self.retrieval_doc_count.record(doc_count, {"data_source": data_source})
        except Exception:
            pass

    def record_http(self,
                    method: str,
                    route: str,
                    status_code: int,
                    duration_ms: float = 0.0) -> None:
        """记录一次 HTTP 请求（网关侧）：状态计数与耗时。

        status 标签按 HTTP 状态码归类：2xx/3xx 为 ok，其余为 error。
        """
        try:
            status = STATUS_OK if status_code < 400 else STATUS_ERROR
            attrs = {"method": method, "route": route, "status": status}
            self.http_calls.add(1, attrs)
            self.http_duration.record(
                duration_ms, {"method": method, "route": route})
        except Exception:
            pass

    def record_quality(self,
                       agent: str,
                       score: float,
                       evaluator: str = "rule") -> None:
        """记录一次质量评分（0-100）。"""
        try:
            self.quality_score.record(
                float(score), {"agent": agent, "evaluator": evaluator})
        except Exception:
            pass

    def record_feedback(self,
                        agent: str,
                        sentiment: str = "positive") -> None:
        """记录一次用户反馈（positive / negative）。"""
        try:
            self.quality_feedback.add(
                1, {"agent": agent, "sentiment": sentiment})
        except Exception:
            pass

    def shutdown(self) -> None:
        """flush 指标，进程退出前调用。"""
        try:
            self.provider.shutdown()
        except Exception:
            pass


# 全局引用：setup 初始化后注入，Instrumentor 通过 get_metrics 取用
_GLOBAL: Optional[MetricsReporter] = None


def set_metrics(reporter: MetricsReporter) -> None:
    """注册全局 reporter（由 otel setup 调用）。"""
    global _GLOBAL
    _GLOBAL = reporter


def get_metrics() -> Optional[MetricsReporter]:
    """获取全局 reporter；未初始化返回 None（调用方应降级）。"""
    return _GLOBAL
