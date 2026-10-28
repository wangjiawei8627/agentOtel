"""OpenAI 原生 SDK 自动插桩器。

Patch ``chat.completions.create``（同步 / 异步），为每次 LLM 调用生成
标准 GenAI Chat Span，自动采集：
- model / temperature / max_tokens / stream
- usage（input/output/total tokens）
- finish_reasons
- 输入输出消息原文（opt-in，受 capture_message_content 控制）

支持通过官方 OpenAI SDK 直接调用的场景；LangChain 的 ChatOpenAI
建议配合 LangChain instrumentor（V0.2 提供），本插桩器亦可兜底。
"""

from __future__ import annotations

import json
import time
from typing import Any

import wrapt
from opentelemetry.trace import Status, StatusCode

from ..semconv import attributes as A
from ..semconv.mapping import apply_mapping
from ..metrics import get_metrics
from ..metrics.meter import STATUS_OK, STATUS_ERROR
from .base import BaseAgentInstrumentor


class OpenAIInstrumentor(BaseAgentInstrumentor):
    """OpenAI SDK 自动插桩器。"""

    instrumentation_dependencies = ("openai",)

    def _instrument(self, **kwargs) -> None:
        # 同步 chat completions
        wrapt.wrap_function_wrapper(
            "openai.resources.chat.completions",
            "Completions.create",
            self._patched_create,
        )
        # 异步 chat completions
        wrapt.wrap_function_wrapper(
            "openai.resources.chat.completions",
            "AsyncCompletions.create",
            self._patched_async_create,
        )

    def _uninstrument(self, **kwargs) -> None:
        from openai.resources.chat import completions as mod
        wrapt.unwrap(mod.Completions, "create")
        wrapt.unwrap(mod.AsyncCompletions, "create")

    # ==================================================================
    def _start_span(self, kwargs_call: dict):
        """根据请求参数创建 Chat Span。"""
        model = kwargs_call.get("model", "unknown")
        cm = self.tracer.start_as_current_span(f"chat openai {model}")
        span = cm.__enter__()

        span.set_attribute(A.OPERATION_NAME, A.OPERATION_CHAT)
        span.set_attribute(A.PROVIDER_NAME, A.PROVIDER_OPENAI)
        span.set_attribute(A.REQUEST_MODEL, model)
        if kwargs_call.get("temperature") is not None:
            span.set_attribute(A.REQUEST_TEMPERATURE, kwargs_call["temperature"])
        if kwargs_call.get("max_tokens") is not None:
            span.set_attribute(A.REQUEST_MAX_TOKENS, kwargs_call["max_tokens"])
        span.set_attribute(A.REQUEST_STREAM, bool(kwargs_call.get("stream", False)))

        if self.config.capture_message_content:
            # 标准化输入消息：[{role, parts:[{type:text,content}]}]
            normalized = [
                {
                    "role": m.get("role"),
                    "parts": [{"type": "text", "content": _content_to_text(m.get("content"))}],
                }
                for m in kwargs_call.get("messages", [])
            ]
            span.set_attribute(A.INPUT_MESSAGES, json.dumps(normalized, ensure_ascii=False))
        return span, cm

    def _fill_response(self, span, response: Any) -> None:
        """把响应对象映射为标准属性。"""
        # 用映射表统一处理 usage / finish_reason / id
        mapped = apply_mapping("openai", model_to_dict(response))
        for key, value in mapped.items():
            span.set_attribute(key, value)

        if self.config.capture_message_content:
            choices = getattr(response, "choices", []) or []
            output = []
            for choice in choices:
                msg = getattr(choice, "message", None)
                content = getattr(msg, "content", "") if msg else ""
                output.append({
                    "role": "assistant",
                    "parts": [{"type": "text", "content": content}] if content else [],
                    "finish_reason": getattr(choice, "finish_reason", None),
                })
            span.set_attribute(A.OUTPUT_MESSAGES, json.dumps(output, ensure_ascii=False))

    # ==================================================================
    def _patched_create(self, wrapped, instance, args, kwargs):
        span, cm = self._start_span(kwargs)
        start = time.time()
        exc = None
        model = kwargs.get("model", "unknown")
        in_tok = out_tok = 0
        try:
            response = wrapped(*args, **kwargs)
            self._fill_response(span, response)
            # 从响应读取真实 token 用于 metrics
            d = model_to_dict(response)
            usage = d.get("usage", {}) or {}
            in_tok = usage.get("prompt_tokens", 0)
            out_tok = usage.get("completion_tokens", 0)
            return response
        except Exception as e:
            exc = e
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, description=str(e)))
            raise
        finally:
            duration_ms = (time.time() - start) * 1000
            span.set_attribute(A.APP_DURATION_MS, duration_ms)
            reporter = get_metrics()
            if reporter is not None:
                reporter.record_llm(
                    model=model, provider=A.PROVIDER_OPENAI,
                    input_tokens=in_tok, output_tokens=out_tok,
                    duration_ms=duration_ms,
                    status=STATUS_OK if exc is None else STATUS_ERROR,
                )
            if exc is None:
                span.set_status(Status(StatusCode.OK))
            cm.__exit__(type(exc) if exc else None, exc, None)

    async def _patched_async_create(self, wrapped, instance, args, kwargs):
        span, cm = self._start_span(kwargs)
        start = time.time()
        exc = None
        model = kwargs.get("model", "unknown")
        in_tok = out_tok = 0
        try:
            response = await wrapped(*args, **kwargs)
            self._fill_response(span, response)
            d = model_to_dict(response)
            usage = d.get("usage", {}) or {}
            in_tok = usage.get("prompt_tokens", 0)
            out_tok = usage.get("completion_tokens", 0)
            return response
        except Exception as e:
            exc = e
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, description=str(e)))
            raise
        finally:
            duration_ms = (time.time() - start) * 1000
            span.set_attribute(A.APP_DURATION_MS, duration_ms)
            reporter = get_metrics()
            if reporter is not None:
                reporter.record_llm(
                    model=model, provider=A.PROVIDER_OPENAI,
                    input_tokens=in_tok, output_tokens=out_tok,
                    duration_ms=duration_ms,
                    status=STATUS_OK if exc is None else STATUS_ERROR,
                )
            if exc is None:
                span.set_status(Status(StatusCode.OK))
            cm.__exit__(type(exc) if exc else None, exc, None)


# ----------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------
def _content_to_text(content: Any) -> str:
    """OpenAI 消息 content 可能是字符串或多模态 parts 数组，统一转文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(part.get("text", ""))
        return "\n".join(texts)
    return str(content)


def model_to_dict(obj: Any) -> Any:
    """把 Pydantic 模型（OpenAI 响应）转成 dict，便于映射表取值。"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict"):
        return obj.dict()
    return obj
