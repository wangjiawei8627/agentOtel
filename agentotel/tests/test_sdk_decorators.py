"""手动埋点装饰器测试（同步 + 异步）。"""

import pytest
from types import SimpleNamespace

from agentotel.sdk import agent_span, llm_span, tool_span, retrieval_span
from agentotel.config import AgentOTelConfig
from agentotel.metrics import MetricsReporter, set_metrics
from agentotel.otel import setup as setup_mod
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics.export import InMemoryMetricReader


@pytest.fixture
def sdk_env():
    cfg = AgentOTelConfig(service_name="dec-test", capture_tool_content=True)
    resource = Resource.create({"service.name": cfg.service_name})

    # 无 exporter 的 TracerProvider：只创建 span，不导出，零网络噪音
    trace_provider = TracerProvider(resource=resource)
    tracer = trace_provider.get_tracer("test")

    # 用轻量 stub 替换全局 AgentOTel（装饰器只需要 .tracer / .config）
    stub = SimpleNamespace(tracer=tracer, config=cfg)
    setup_mod._GLOBAL = stub

    # 内存 metrics
    reader = InMemoryMetricReader()
    mem = MetricsReporter(cfg, resource, metric_reader=reader)
    set_metrics(mem)

    yield stub, reader

    mem.shutdown()
    trace_provider.shutdown()
    setup_mod._GLOBAL = None


def test_tool_decorator_sync(sdk_env):
    @tool_span("demo_tool")
    def fn(x):
        return "ok-" + x

    assert fn("x") == "ok-x"


def test_agent_decorator_sync(sdk_env):
    @agent_span("my-agent")
    def fn():
        return 42

    assert fn() == 42


def test_llm_decorator_sync(sdk_env):
    @llm_span("gpt-4o-mini", "openai")
    def fn():
        return "hi"

    assert fn() == "hi"


def test_retrieval_decorator_sync(sdk_env):
    @retrieval_span("kb")
    def fn():
        return ["d1"]

    assert fn() == ["d1"]


def test_decorator_records_error(sdk_env):
    @tool_span("boom")
    def fn():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        fn()


@pytest.mark.asyncio
async def test_decorator_async(sdk_env):
    @tool_span("async_tool")
    async def fn(x):
        return "ok-" + x

    assert await fn("x") == "ok-x"


@pytest.mark.asyncio
async def test_agent_decorator_async(sdk_env):
    @agent_span("async-agent")
    async def fn():
        return 1

    assert await fn() == 1


@pytest.mark.asyncio
async def test_async_decorator_records_error(sdk_env):
    @tool_span("async_boom")
    async def fn():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await fn()
