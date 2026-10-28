"""LlamaIndex 自动插桩器（V0.2）。

通过 ``wrapt`` patch LlamaIndex 核心类，生成三类标准 Span：

1. **LLM Span（chat）**：包裹 ``LLM.chat / complete / achat / acomplete``
2. **检索 Span（retrieval）**：包裹 ``BaseRetriever._retrieve / _aretrieve``
3. **工具 Span（execute_tool）**：包裹 ``BaseTool.call / AsyncBaseTool.acall``

同时复用 MetricsReporter 上报 token、耗时、状态。LlamaIndex 若不返回
token，则由 token_estimate 插件兜底。
"""

from __future__ import annotations

import json
import time
from typing import Any

import wrapt
from opentelemetry.trace import Status, StatusCode

from ..semconv import attributes as A
from ..metrics import get_metrics
from ..metrics.meter import STATUS_OK, STATUS_ERROR
from .base import BaseAgentInstrumentor


class LlamaIndexInstrumentor(BaseAgentInstrumentor):
    """LlamaIndex 自动插桩器。"""

    instrumentation_dependencies = ("llama_index.core",)

    # ==================================================================
    def _instrument(self, **kwargs) -> None:
        # ---- LLM：同步 / 异步的 chat 与 complete ----
        wrapt.wrap_function_wrapper(
            "llama_index.core.llms", "LLM.chat", self._llm_sync("chat"))
        wrapt.wrap_function_wrapper(
            "llama_index.core.llms", "LLM.complete", self._llm_sync("complete"))
        wrapt.wrap_function_wrapper(
            "llama_index.core.llms", "LLM.achat", self._llm_async("chat"))
        wrapt.wrap_function_wrapper(
            "llama_index.core.llms", "LLM.acomplete", self._llm_async("complete"))

        # ---- Retriever ----
        wrapt.wrap_function_wrapper(
            "llama_index.core.base.base_retriever",
            "BaseRetriever._retrieve", self._retrieve_sync)
        wrapt.wrap_function_wrapper(
            "llama_index.core.base.base_retriever",
            "BaseRetriever._aretrieve", self._retrieve_async)

        # ---- Tool ----
        wrapt.wrap_function_wrapper(
            "llama_index.core.tools.types", "BaseTool.call", self._tool_sync)
        wrapt.wrap_function_wrapper(
            "llama_index.core.tools.types", "AsyncBaseTool.acall", self._tool_async)

    def _uninstrument(self, **kwargs) -> None:
        from llama_index.core import llms
        from llama_index.core.base.base_retriever import BaseRetriever
        from llama_index.core.tools import types as tool_types
        wrapt.unwrap(llms.LLM, "chat")
        wrapt.unwrap(llms.LLM, "complete")
        wrapt.unwrap(llms.LLM, "achat")
        wrapt.unwrap(llms.LLM, "acomplete")
        wrapt.unwrap(BaseRetriever, "_retrieve")
        wrapt.unwrap(BaseRetriever, "_aretrieve")
        wrapt.unwrap(tool_types.BaseTool, "call")
        wrapt.unwrap(tool_types.AsyncBaseTool, "acall")

    # ==================================================================
    # LLM
    # ==================================================================
    def _start_llm_span(self, instance):
        model = getattr(instance, "model", "unknown")
        cm = self.tracer.start_as_current_span(f"chat llamaindex {model}")
        span = cm.__enter__()
        span.set_attribute(A.OPERATION_NAME, A.OPERATION_CHAT)
        span.set_attribute(A.REQUEST_MODEL, model)
        return span, cm, model

    def _llm_sync(self, kind: str):
        def wrapper(wrapped, instance, args, kwargs):
            span, cm, model = self._start_llm_span(instance)
            start = time.time()
            exc = None
            try:
                response = wrapped(*args, **kwargs)
                self._record_llm_response(span, response)
                return response
            except Exception as e:
                exc = e
                span.record_exception(e)
                raise
            finally:
                self._finish_llm(span, cm, model, start, exc)
        return wrapper

    def _llm_async(self, kind: str):
        async def wrapper(wrapped, instance, args, kwargs):
            span, cm, model = self._start_llm_span(instance)
            start = time.time()
            exc = None
            try:
                response = await wrapped(*args, **kwargs)
                self._record_llm_response(span, response)
                return response
            except Exception as e:
                exc = e
                span.record_exception(e)
                raise
            finally:
                self._finish_llm(span, cm, model, start, exc)
        return wrapper

    def _record_llm_response(self, span, response: Any) -> None:
        """从 LlamaIndex ChatResponse / CompletionResponse 提取文本。"""
        text = ""
        if hasattr(response, "message"):                 # ChatResponse
            text = getattr(response.message, "content", "") or ""
        elif hasattr(response, "text"):                 # CompletionResponse
            text = response.text or ""
        if self.config.capture_message_content:
            span.set_attribute(
                A.OUTPUT_MESSAGES,
                json.dumps([{"role": "assistant",
                             "parts": [{"type": "text", "content": text}]}],
                           ensure_ascii=False),
            )

    def _finish_llm(self, span, cm, model, start, exc) -> None:
        duration_ms = (time.time() - start) * 1000
        span.set_attribute(A.APP_DURATION_MS, duration_ms)
        reporter = get_metrics()
        if reporter is not None:
            reporter.record_llm(
                model=model, provider="llamaindex",
                duration_ms=duration_ms,
                status=STATUS_OK if exc is None else STATUS_ERROR,
            )
        if exc is None:
            span.set_status(Status(StatusCode.OK))
        else:
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
        cm.__exit__(type(exc) if exc else None, exc, None)

    # ==================================================================
    # Retriever
    # ==================================================================
    def _start_retrieval_span(self, instance):
        cm = self.tracer.start_as_current_span("retrieval llamaindex")
        span = cm.__enter__()
        span.set_attribute(A.OPERATION_NAME, A.OPERATION_RETRIEVAL)
        span.set_attribute(A.DATA_SOURCE_ID, "llamaindex")
        return span, cm

    def _retrieve_sync(self, wrapped, instance, args, kwargs):
        span, cm = self._start_retrieval_span(instance)
        start = time.time()
        exc = None
        try:
            nodes = wrapped(*args, **kwargs)
            self._record_nodes(span, nodes)
            return nodes
        except Exception as e:
            exc = e
            span.record_exception(e)
            raise
        finally:
            self._finish_retrieval(span, cm, start, exc)

    async def _retrieve_async(self, wrapped, instance, args, kwargs):
        span, cm = self._start_retrieval_span(instance)
        start = time.time()
        exc = None
        try:
            nodes = await wrapped(*args, **kwargs)
            self._record_nodes(span, nodes)
            return nodes
        except Exception as e:
            exc = e
            span.record_exception(e)
            raise
        finally:
            self._finish_retrieval(span, cm, start, exc)

    def _record_nodes(self, span, nodes) -> None:
        count = len(nodes) if nodes is not None else 0
        span.set_attribute(A.APP_RETRIEVAL_DOC_COUNT, count)

    def _finish_retrieval(self, span, cm, start, exc) -> None:
        duration_ms = (time.time() - start) * 1000
        reporter = get_metrics()
        if reporter is not None:
            reporter.record_retrieval(
                data_source="llamaindex",
                duration_ms=duration_ms,
                doc_count=span.attributes.get(A.APP_RETRIEVAL_DOC_COUNT, 0),
                status=STATUS_OK if exc is None else STATUS_ERROR,
            )
        if exc is None:
            span.set_status(Status(StatusCode.OK))
        else:
            span.set_status(Status(StatusCode.ERROR, description=str(exc)))
        cm.__exit__(type(exc) if exc else None, exc, None)

    # ==================================================================
    # Tool
    # ==================================================================
    def _tool_sync(self, wrapped, instance, args, kwargs):
        return self._run_tool(wrapped, instance, args, kwargs, is_async=False)

    def _tool_async(self, wrapped, instance, args, kwargs):
        return self._run_tool(wrapped, instance, args, kwargs, is_async=True)

    def _run_tool(self, wrapped, instance, args, kwargs, is_async: bool):
        tool_name = getattr(instance, "metadata", None)
        name = getattr(tool_name, "name", "llamaindex-tool")
        cm = self.tracer.start_as_current_span(f"execute_tool {name}")
        span = cm.__enter__()
        span.set_attribute(A.OPERATION_NAME, A.OPERATION_EXECUTE_TOOL)
        span.set_attribute(A.TOOL_NAME, name)
        start = time.time()
        exc = None

        async def _arun():
            try:
                return await wrapped(*args, **kwargs)
            except Exception as e:
                span.record_exception(e)
                raise

        def _run():
            try:
                return wrapped(*args, **kwargs)
            except Exception as e:
                span.record_exception(e)
                raise

        try:
            if is_async:
                return _arun()
            return _run()
        except Exception as e:
            exc = e
            raise
        finally:
            duration_ms = (time.time() - start) * 1000
            reporter = get_metrics()
            if reporter is not None:
                reporter.record_tool(
                    tool_name=name,
                    duration_ms=duration_ms,
                    status=STATUS_OK if exc is None else STATUS_ERROR,
                )
            if exc is None:
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(Status(StatusCode.ERROR, description=str(exc)))
            cm.__exit__(type(exc) if exc else None, exc, None)
