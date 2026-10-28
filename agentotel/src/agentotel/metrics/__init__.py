"""Metrics 子包。

封装 OTel Metrics 上报，Instrumentor 只依赖 ``MetricsReporter`` 的
语义化方法，无需直接操作 Counter / Histogram。
"""

from .meter import MetricsReporter, get_metrics, set_metrics

__all__ = ["MetricsReporter", "get_metrics", "set_metrics"]
