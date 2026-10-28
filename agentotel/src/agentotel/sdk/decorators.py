"""极简手动埋点装饰器。

面向自研 / 小众框架 Agent，用户无需理解 Tracer、Span、Attribute 细节，
用装饰器即可声明各节点，自动：
- 创建对应类型的 Span（同步 / 异步通用）
- 填充标准 ``gen_ai.*`` 属性
- 捕获异常、记录耗时
- 执行插件管道

用法::

    from agentotel.sdk import agent_span, llm_span, tool_span

    @agent_span(agent_name="my-agent")
    def run(query):
        return chat(query)

    @llm_span(model="gpt-4o-mini", provider="openai")
    def chat(prompt):
        return client.chat.completions.create(...)

    @tool_span(tool_name="search")
    def search(q):
        ...
"""

from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable, Optional

from opentelemetry.trace import Status, StatusCode

from ..semconv import attributes as A
from ..otel.setup import get_agentotel
from ..metrics import get_metrics
from ..metrics.meter import STATUS_OK, STATUS_ERROR


def _build_span(span_name: str, base_attrs: dict):
    """创建 Span 并写入基础属性，返回 (span, ctx_manager)。"""
    sdk = get_agentotel()
    cm = sdk.tracer.start_as_current_span(span_name)
    span = cm.__enter__()
    for key, value in base_attrs.items():
        if value is not None:
            span.set_attribute(key, value)
    return sdk, span, cm


def _decorate(span_name: str, base_attrs: dict, capture_result: bool = False,
              metric_fn: Optional[Callable[[float, str], None]] = None):
    """通用装饰器工厂：自动适配同步函数与异步函数。

    :param metric_fn: 可选回调 ``metric_fn(duration_ms, status)``，结束时上报指标
    """

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def awrapper(*args, **kwargs):
                sdk, span, cm = _build_span(span_name, base_attrs)
                start = time.time()
                exc = None
                try:
                    result = await func(*args, **kwargs)
                    if capture_result and sdk.config.capture_tool_content:
                        span.set_attribute(A.TOOL_CALL_RESULT, str(result)[:1000])
                    return result
                except Exception as e:
                    exc = e
                    raise
                finally:
                    duration_ms = (time.time() - start) * 1000
                    span.set_attribute(A.APP_DURATION_MS, duration_ms)
                    if metric_fn:
                        metric_fn(duration_ms, STATUS_OK if exc is None else STATUS_ERROR)
                    _finalize(sdk, span, cm, exc)
            return awrapper

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            sdk, span, cm = _build_span(span_name, base_attrs)
            start = time.time()
            exc = None
            try:
                result = func(*args, **kwargs)
                if capture_result and sdk.config.capture_tool_content:
                    span.set_attribute(A.TOOL_CALL_RESULT, str(result)[:1000])
                return result
            except Exception as e:
                exc = e
                raise
            finally:
                duration_ms = (time.time() - start) * 1000
                span.set_attribute(A.APP_DURATION_MS, duration_ms)
                if metric_fn:
                    metric_fn(duration_ms, STATUS_OK if exc is None else STATUS_ERROR)
                _finalize(sdk, span, cm, exc)
        return wrapper

    return decorator


def _finalize(sdk, span, cm, exc: Optional[BaseException]) -> None:
    """统一收尾：跑插件管道、写状态、关闭 Span。"""
    if exc is None:
        span.set_status(Status(StatusCode.OK))
    else:
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, description=str(exc)))
    cm.__exit__(type(exc) if exc else None, exc, None)


# ======================================================================
# 语义化装饰器
# ======================================================================
def agent_span(agent_name: str = "agent", **extra):
    """一次 Agent 任务根 Span（invoke_agent）。"""
    attrs = {
        A.OPERATION_NAME: A.OPERATION_INVOKE_AGENT,
        A.APP_AGENT_NAME: agent_name,
        **extra,
    }

    def metric_fn(duration_ms, status):
        reporter = get_metrics()
        if reporter:
            reporter.record_agent(agent_name, duration_ms, status)

    return _decorate(f"invoke_agent {agent_name}", attrs, metric_fn=metric_fn)


def llm_span(model: str, provider: str = "openai", **extra):
    """一次 LLM 调用 Span（chat）。"""
    attrs = {
        A.OPERATION_NAME: A.OPERATION_CHAT,
        A.PROVIDER_NAME: provider,
        A.REQUEST_MODEL: model,
        **extra,
    }

    def metric_fn(duration_ms, status):
        reporter = get_metrics()
        if reporter:
            reporter.record_llm(model, provider, duration_ms=duration_ms, status=status)

    return _decorate(f"chat {provider} {model}", attrs, metric_fn=metric_fn)


def tool_span(tool_name: str, tool_type: str = "function", **extra):
    """一次工具调用 Span（execute_tool）。"""
    attrs = {
        A.OPERATION_NAME: A.OPERATION_EXECUTE_TOOL,
        A.TOOL_NAME: tool_name,
        A.TOOL_TYPE: tool_type,
        **extra,
    }

    def metric_fn(duration_ms, status):
        reporter = get_metrics()
        if reporter:
            reporter.record_tool(tool_name, tool_type, duration_ms, status)

    return _decorate(f"execute_tool {tool_name}", attrs, capture_result=True,
                     metric_fn=metric_fn)


def retrieval_span(data_source_id: str = "knowledge_base", **extra):
    """一次检索 Span（retrieval）。"""
    attrs = {
        A.OPERATION_NAME: A.OPERATION_RETRIEVAL,
        A.DATA_SOURCE_ID: data_source_id,
        **extra,
    }

    def metric_fn(duration_ms, status):
        reporter = get_metrics()
        if reporter:
            reporter.record_retrieval(data_source_id, duration_ms=duration_ms, status=status)

    return _decorate(f"retrieval {data_source_id}", attrs, metric_fn=metric_fn)


def span(name: str, **extra):
    """通用 Span：用于任意自定义步骤（如规划、反思、重排等）。"""
    return _decorate(name, extra)
