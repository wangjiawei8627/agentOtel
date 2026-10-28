"""LangGraph 自动插桩器（V0.1 核心）。

通过 ``wrapt`` 对 LangGraph 做非侵入式 monkey patch，自动生成两类 Span：

1. **根 Span（invoke_agent）**：包裹 ``CompiledStateGraph.invoke / ainvoke``，
   代表一次完整 Agent 任务。
2. **节点 Span（node.<key>）**：包裹 ``StateGraph.add_node`` 注册的每个节点，
   自动识别同步函数 / 异步函数 / Runnable（如 ToolNode），记录节点名、
   耗时、状态。

LLM 与工具的细粒度 Span 由 OpenAIInstrumentor / LangChain instrumentor 负责，
本插桩器专注“图的执行结构”，两者互补。
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import time
from typing import Any

import wrapt
from opentelemetry.trace import Status, StatusCode

from ..semconv import attributes as A
from ..metrics import get_metrics
from ..metrics.meter import STATUS_OK, STATUS_ERROR
from .base import BaseAgentInstrumentor


def _is_runnable(action: Any) -> bool:
    """判断是否为 LangChain Runnable（同时具备 invoke / ainvoke）。"""
    return hasattr(action, "invoke") and hasattr(action, "ainvoke")


class LangGraphInstrumentor(BaseAgentInstrumentor):
    """LangGraph 自动插桩器。"""

    instrumentation_dependencies = ("langgraph",)

    # ==================================================================
    # 生命周期
    # ==================================================================
    def _instrument(self, **kwargs) -> None:
        # 1) 包装节点注册：add_node 时自动给节点加 Span
        wrapt.wrap_function_wrapper(
            "langgraph.graph.state",
            "StateGraph.add_node",
            self._patched_add_node,
        )
        # 2) 包装同步执行入口
        wrapt.wrap_function_wrapper(
            "langgraph.graph.state",
            "CompiledStateGraph.invoke",
            self._patched_invoke,
        )
        # 3) 包装异步执行入口
        wrapt.wrap_function_wrapper(
            "langgraph.graph.state",
            "CompiledStateGraph.ainvoke",
            self._patched_ainvoke,
        )

    def _uninstrument(self, **kwargs) -> None:
        import langgraph.graph.state as mod  # 延迟导入，保证依赖检查先执行
        wrapt.unwrap(mod.StateGraph, "add_node")
        wrapt.unwrap(mod.CompiledStateGraph, "invoke")
        wrapt.unwrap(mod.CompiledStateGraph, "ainvoke")

    # ==================================================================
    # 根 Span：invoke / ainvoke
    # ==================================================================
    def _open_root_span(self, graph_input: Any):
        """创建根 Span 并写入标准属性，返回 (span, ctx_manager)。"""
        cm = self.tracer.start_as_current_span("invoke_agent langgraph")
        span = cm.__enter__()
        span.set_attribute(A.OPERATION_NAME, A.OPERATION_INVOKE_AGENT)
        span.set_attribute(A.WORKFLOW_NAME, "langgraph")
        span.set_attribute(A.PROVIDER_NAME, A.PROVIDER_OPENAI)
        if self.config.capture_message_content:
            # 输入可能是 dict（含 messages）；只记录摘要，避免大对象
            span.set_attribute(A.APP_USER_QUERY, str(graph_input)[:1000])
        return span, cm

    def _patched_invoke(self, wrapped, instance, args, kwargs):
        graph_input = args[0] if args else kwargs.get("input")
        span, cm = self._open_root_span(graph_input)
        start = time.time()
        exc = None
        try:
            result = wrapped(*args, **kwargs)
            if self.config.capture_message_content:
                span.set_attribute(A.APP_FINAL_ANSWER, str(result)[:1000])
            span.set_status(Status(StatusCode.OK))
            return result
        except Exception as e:
            exc = e
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, description=str(e)))
            raise
        finally:
            reporter = get_metrics()
            if reporter is not None:
                reporter.record_agent(
                    agent_name="langgraph",
                    duration_ms=(time.time() - start) * 1000,
                    status=STATUS_OK if exc is None else STATUS_ERROR,
                )
            cm.__exit__(type(exc) if exc else None, exc, None)

    async def _patched_ainvoke(self, wrapped, instance, args, kwargs):
        graph_input = args[0] if args else kwargs.get("input")
        span, cm = self._open_root_span(graph_input)
        start = time.time()
        exc = None
        try:
            result = await wrapped(*args, **kwargs)
            if self.config.capture_message_content:
                span.set_attribute(A.APP_FINAL_ANSWER, str(result)[:1000])
            span.set_status(Status(StatusCode.OK))
            return result
        except Exception as e:
            exc = e
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, description=str(e)))
            raise
        finally:
            reporter = get_metrics()
            if reporter is not None:
                reporter.record_agent(
                    agent_name="langgraph",
                    duration_ms=(time.time() - start) * 1000,
                    status=STATUS_OK if exc is None else STATUS_ERROR,
                )
            cm.__exit__(type(exc) if exc else None, exc, None)

    # ==================================================================
    # 节点 Span：add_node
    # ==================================================================
    def _patched_add_node(self, wrapped, instance, args, kwargs):
        """拦截 add_node，把传入的 action 替换成带 Span 的包装。"""
        key, action = self._parse_add_node_args(args, kwargs)
        wrapped_action = self._wrap_action(key, action)
        # 统一用 (key, action) 形式调用原方法
        return wrapped(key, wrapped_action)

    @staticmethod
    def _parse_add_node_args(args, kwargs):
        """兼容两种调用：add_node(key, action) 与 add_node(action)。"""
        if len(args) == 1 and "action" not in kwargs:
            action = args[0]
            key = getattr(action, "__name__", "node")
            return key, action
        if len(args) >= 2:
            return args[0], args[1]
        return kwargs.get("key"), kwargs.get("action")

    def _wrap_action(self, key: str, action: Any) -> Any:
        """根据节点类型选择包装方式；无法识别则原样返回。"""
        if action is None:
            return action
        if _is_runnable(action):
            return self._wrap_runnable(key, action)
        if asyncio.iscoroutinefunction(action) or inspect.isasyncgenfunction(action):
            return self._wrap_async_func(key, action)
        if callable(action):
            return self._wrap_sync_func(key, action)
        return action

    # ------------------------------------------------------------------
    def _start_node_span(self, key: str):
        """创建一个节点 Span 并返回上下文管理器。"""
        cm = self.tracer.start_as_current_span(f"node {key}")
        span = cm.__enter__()
        span.set_attribute(A.APP_NODE_NAME, key)
        return span, cm

    def _finish_node_span(self, span, cm, exc):
        """统一收尾：执行插件管道、写状态、关闭上下文。"""
        if exc is None:
            span.set_status(Status(StatusCode.OK))
        else:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
        cm.__exit__(type(exc) if exc else None, exc, None)

    def _wrap_sync_func(self, key: str, func):
        """包装同步函数节点。"""
        @functools.wraps(func)
        def wrapper(*fargs, **fkwargs):
            span, cm = self._start_node_span(key)
            start = time.time()
            exc = None
            try:
                return func(*fargs, **fkwargs)
            except Exception as e:
                exc = e
                raise
            finally:
                span.set_attribute(A.APP_DURATION_MS, (time.time() - start) * 1000)
                self._finish_node_span(span, cm, exc)
        return wrapper

    def _wrap_async_func(self, key: str, func):
        """包装异步函数节点。"""
        @functools.wraps(func)
        async def wrapper(*fargs, **fkwargs):
            span, cm = self._start_node_span(key)
            start = time.time()
            exc = None
            try:
                return await func(*fargs, **fkwargs)
            except Exception as e:
                exc = e
                raise
            finally:
                span.set_attribute(A.APP_DURATION_MS, (time.time() - start) * 1000)
                self._finish_node_span(span, cm, exc)
        return wrapper

    def _wrap_runnable(self, key: str, runnable):
        """包装 Runnable 节点（如 ToolNode）：替换其 invoke / ainvoke。"""
        original_invoke = runnable.invoke
        original_ainvoke = runnable.ainvoke

        @functools.wraps(original_invoke)
        def sync_invoke(*iargs, **ikwargs):
            span, cm = self._start_node_span(key)
            start = time.time()
            exc = None
            try:
                return original_invoke(*iargs, **ikwargs)
            except Exception as e:
                exc = e
                raise
            finally:
                span.set_attribute(A.APP_DURATION_MS, (time.time() - start) * 1000)
                self._finish_node_span(span, cm, exc)

        @functools.wraps(original_ainvoke)
        async def async_invoke(*iargs, **ikwargs):
            span, cm = self._start_node_span(key)
            start = time.time()
            exc = None
            try:
                return await original_ainvoke(*iargs, **ikwargs)
            except Exception as e:
                exc = e
                raise
            finally:
                span.set_attribute(A.APP_DURATION_MS, (time.time() - start) * 1000)
                self._finish_node_span(span, cm, exc)

        runnable.invoke = sync_invoke
        runnable.ainvoke = async_invoke
        return runnable
