"""Agent 会话上下文（异步安全）。

Agent 常见痛点：多轮对话、多线程、并发工具调用时，session_id / user_id
容易串号或丢失。本模块用 ``contextvars`` 保存当前执行上下文，
asyncio 下每个任务独立，不会互相污染；同时把这些业务标签注入到
Span 属性，保证整条链路可按会话/用户检索。
"""

from __future__ import annotations

import contextlib
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass(frozen=True)
class AgentContext:
    """一次 Agent 执行的业务上下文（不可变）。"""

    session_id: str                              # 会话 ID（同一会话多轮共享）
    user_id: Optional[str] = None                # 用户 ID
    agent_name: Optional[str] = None             # Agent 名称
    trace_id: Optional[str] = None               # 期望的 trace 标识（一般由 OTel 生成）

    @staticmethod
    def new(session_id: Optional[str] = None,
            user_id: Optional[str] = None,
            agent_name: Optional[str] = None) -> "AgentContext":
        """便捷构造：未给 session_id 时自动生成。"""
        return AgentContext(
            session_id=session_id or f"sess_{uuid.uuid4().hex[:16]}",
            user_id=user_id,
            agent_name=agent_name,
        )


# 当前协程/线程的上下文。未设置时为 None，调用方应降级处理而非报错。
_current: ContextVar[Optional[AgentContext]] = ContextVar("agentotel_context", default=None)


def get_context() -> Optional[AgentContext]:
    """获取当前上下文；不存在返回 None。"""
    return _current.get()


def set_context(ctx: AgentContext) -> contextlib.Token:
    """设置当前上下文，返回 Token（可用于 reset）。"""
    return _current.set(ctx)


def reset_context(token: contextlib.Token) -> None:
    """根据 set_context 返回的 Token 恢复上一个上下文。"""
    _current.reset(token)


@contextlib.contextmanager
def use_context(ctx: AgentContext) -> Iterator[AgentContext]:
    """上下文管理器：进入时生效，退出时自动恢复，避免上下文泄漏。

    用法::

        with use_context(AgentContext.new(user_id="u1")):
            graph.invoke(...)
    """
    token = set_context(ctx)
    try:
        yield ctx
    finally:
        reset_context(token)
