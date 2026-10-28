"""OpenTelemetry 初始化与全局门面。

``AgentOTel`` 是整个框架的核心入口，负责：
1. 构造 Resource（服务身份）
2. 配置采样器
3. 配置 OTLP 导出器与批量处理器
4. 组装插件管道
5. 暴露 ``Tracer`` 供 Instrumentor / 装饰器使用

典型用法::

    from agentotel import init_agentotel
    sdk = init_agentotel(service_name="my-agent", capture_message_content=True)
    # 之后 instrument 各框架即可
"""

from __future__ import annotations

import os
from typing import List, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from ..config import AgentOTelConfig
from ..plugins import (
    AgentotelPlugin,
    PluginPipeline,
    PIIFilterPlugin,
    TokenEstimatorPlugin,
)
from ..metrics import MetricsReporter
from ..metrics.meter import set_metrics

# 开启最新实验性 GenAI 语义约定（幂等，重复设置无副作用）
os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")


class AgentOTel:
    """框架运行时门面：持有 provider、tracer、插件管道。"""

    def __init__(self, config: AgentOTelConfig) -> None:
        self.config = config

        # 1) 服务身份
        self.resource = Resource.create({
            "service.name": config.service_name,
            "service.version": config.service_version,
            "deployment.environment": config.environment,
        })

        # 2) 采样器：父级采样（有上游则跟随）+ 比例采样
        ratio = max(0.0, min(1.0, config.sampler_ratio))
        sampler = ParentBased(TraceIdRatioBased(ratio))

        # 3) TracerProvider
        self.provider = TracerProvider(resource=self.resource, sampler=sampler)

        # 4) OTLP 导出
        exporter = OTLPSpanExporter(
            endpoint=config.otlp_endpoint,
            insecure=config.insecure,
        )
        self.provider.add_span_processor(BatchSpanProcessor(exporter))

        # 记录是否已全局注册，避免重复 set_tracer_provider
        self._registered = False
        self._register_global()

        # 5) 插件管道
        self.plugins = PluginPipeline(self._build_default_plugins())

        # 6) Tracer
        self.tracer = self.provider.get_tracer(
            "agentotel",
            schema_url="https://opentelemetry.io/schemas/1.30.0",
        )

        # 7) Metrics 上报器（复用同一份 Resource），并注册为全局
        self.metrics = MetricsReporter(config, self.resource)
        set_metrics(self.metrics)

    # ------------------------------------------------------------------
    def _register_global(self) -> None:
        """把 provider 注册为全局单例；已注册则跳过（OTel 全局只允许一次）。"""
        if self._registered:
            return
        try:
            trace.set_tracer_provider(self.provider)
            self._registered = True
        except Exception:
            # 已经存在全局 provider 时，直接复用
            self.provider = trace.get_tracer_provider()

    def _build_default_plugins(self) -> List[AgentotelPlugin]:
        """根据配置装配默认插件。"""
        plugins: List[AgentotelPlugin] = []
        if self.config.pii_mask_enabled:
            plugins.append(PIIFilterPlugin())
        if self.config.token_estimate_enabled:
            plugins.append(TokenEstimatorPlugin())
        return plugins

    # ------------------------------------------------------------------
    def add_plugin(self, plugin: AgentotelPlugin) -> "AgentOTel":
        """运行期追加自定义插件。"""
        self.plugins.add(plugin)
        return self

    def shutdown(self) -> None:
        """进程退出前 flush，防止批量处理器丢失最后一批 Span / Metric。"""
        try:
            self.metrics.shutdown()
        except Exception:
            pass
        try:
            self.provider.shutdown()
        except Exception:
            pass


# 全局单例，方便 init_agentotel 后各处直接引用
_GLOBAL: Optional[AgentOTel] = None


def init_agentotel(config: Optional[AgentOTelConfig] = None,
                   **kwargs) -> AgentOTel:
    """初始化全局 AgentOTel 单例。

    - 可直接传 ``AgentOTelConfig``；
    - 也可传关键字参数（先 ``from_env`` 再覆盖）；
    - 重复调用返回同一个单例（幂等）。
    """
    global _GLOBAL
    if _GLOBAL is not None:
        return _GLOBAL

    if config is None:
        config = AgentOTelConfig.from_env(**kwargs)
    _GLOBAL = AgentOTel(config)
    return _GLOBAL


def get_agentotel() -> AgentOTel:
    """获取已初始化的全局单例；未初始化时用默认配置兜底初始化。"""
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = AgentOTel(AgentOTelConfig.from_env())
    return _GLOBAL
