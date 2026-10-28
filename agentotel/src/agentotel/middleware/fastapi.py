"""FastAPI / Starlette 网关插桩中间件（V0.2）。

价值：当 Agent 以 HTTP 服务形式部署时，无需在业务代码里埋点，
只需挂载本中间件即可为每个请求生成一个 HTTP Span，并上报指标。

链路结构（内部若同时插桩则自动成为子 Span）::

    http POST /agent
    └── invoke_agent langgraph
        └── ...

采集内容：
- 标准 HTTP 语义：http.request.method、http.response.status_code、url.path
- 耗时、状态
- 可选：请求体（用于识别 Agent 入参，默认关闭；读取后会重放，不影响下游）
"""

from __future__ import annotations

import time
from typing import Any, Callable, Tuple

from opentelemetry.trace import Status, StatusCode

from ..semconv import attributes as A
from ..metrics import get_metrics
from ..otel.setup import get_agentotel


class AgentOTelMiddleware:
    """纯 ASGI 中间件（不依赖 BaseHTTPMiddleware，性能与兼容性更好）。

    用法::

        from fastapi import FastAPI
        from agentotel.middleware import AgentOTelMiddleware

        app = FastAPI()
        app.add_middleware(AgentOTelMiddleware, capture_request_body=False)
    """

    def __init__(self,
                 app,
                 capture_request_body: bool = False,
                 body_max_length: int = 2000) -> None:
        self.app = app
        self.capture_request_body = capture_request_body
        self.body_max_length = body_max_length
        self._sdk = get_agentotel()
        self.tracer = self._sdk.tracer
        self.config = self._sdk.config

    # ------------------------------------------------------------------
    async def __call__(self, scope, receive, send):
        # 只处理 HTTP 请求；websocket / lifespan 直接透传
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        start = time.time()

        # 可选：排空并缓存请求体，返回可重放的 receive，保证下游仍能读到
        if self.capture_request_body:
            body_bytes, receive = await self._drain_and_cache(receive)
        else:
            body_bytes = b""

        cm = self.tracer.start_as_current_span(f"http {method} {path}")
        span = cm.__enter__()
        span.set_attribute("http.request.method", method)
        span.set_attribute("url.path", path)

        if self.capture_request_body and body_bytes:
            text = body_bytes.decode("utf-8", errors="replace")[: self.body_max_length]
            span.set_attribute(A.APP_USER_QUERY, text)

        status_holder = {"code": 0}

        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                status_holder["code"] = message.get("status", 0)
            await send(message)

        exc = None
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            exc = e
            span.record_exception(e)
            raise
        finally:
            duration_ms = (time.time() - start) * 1000
            code = status_holder["code"]
            if code:
                span.set_attribute("http.response.status_code", code)
            span.set_attribute(A.APP_DURATION_MS, duration_ms)

            reporter = get_metrics()
            if reporter is not None:
                reporter.record_http(method, path, code, duration_ms)

            if exc is None and code < 500:
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(
                    Status(StatusCode.ERROR,
                           description=str(exc) if exc else f"HTTP {code}"))
            cm.__exit__(type(exc) if exc else None, exc, None)

    # ------------------------------------------------------------------
    async def _drain_and_cache(self, receive: Callable
                               ) -> Tuple[bytes, Callable]:
        """读取完整请求体，并构造一个可重放的 receive。

        这样既拿到了 body 用于埋点，又不影响下游再次读取。
        """
        messages: list = []
        chunks: list = []
        while True:
            msg = await receive()
            messages.append(msg)
            if msg.get("type") == "http.request":
                chunks.append(msg.get("body", b"") or b"")
                if not msg.get("more_body", False):
                    break
            else:
                # 非 http.request（如 http.disconnect），停止收集
                break

        body = b"".join(chunks)
        replay_queue = list(messages)

        async def replay_receive():
            if replay_queue:
                return replay_queue.pop(0)
            return {"type": "http.disconnect"}

        return body, replay_receive
