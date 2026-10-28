"""pytest 全局夹具与配置。

- 把 src 加入 sys.path（兼容未 pip install 的场景）
- 提供隔离的配置、资源、内存版 MetricsReporter
- 每个测试结束后清理，避免全局单例与上下文串扰
"""

import os
import sys

import pytest

# 确保能从 src 导入（CI 里可能直接 checkout 而未安装）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from agentotel.config import AgentOTelConfig  # noqa: E402
from opentelemetry.sdk.resources import Resource  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402
from agentotel.metrics import MetricsReporter  # noqa: E402


@pytest.fixture
def config():
    """一个稳定的测试配置：不连真实 collector（reporter 用内存 reader）。"""
    return AgentOTelConfig(
        service_name="test-service",
        service_version="test",
        environment="test",
        capture_message_content=True,
        capture_tool_content=True,
    )


@pytest.fixture
def resource(config):
    return Resource.create({"service.name": config.service_name})


@pytest.fixture
def metric_reader():
    """内存 reader：收集指标但不导出，测试可断言其内容。"""
    return InMemoryMetricReader()


@pytest.fixture
def reporter(config, resource, metric_reader):
    """用内存 reader 构造的 MetricsReporter，无网络、无后台线程。"""
    r = MetricsReporter(config, resource, metric_reader=metric_reader)
    yield r
    r.provider.shutdown()
