"""全局配置管理。

用不可变 dataclass 描述 AgentOTel 的所有运行期配置，支持：
- 代码构造（``AgentOTelConfig(...)``）
- 环境变量覆盖（便于容器化部署，不写死在代码里）

设计原则：敏感内容采集默认关闭，必须显式 opt-in。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Tuple


def _env_bool(key: str, default: bool) -> bool:
    """读取布尔型环境变量；支持 1/true/yes/on 为真。"""
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class AgentOTelConfig:
    """AgentOTel 运行配置（不可变，避免多线程下被中途篡改）。"""

    # ---- 服务身份 ----
    service_name: str = "agentotel-app"
    service_version: str = "0.0.0"
    environment: str = "dev"

    # ---- 导出 ----
    otlp_endpoint: str = "http://127.0.0.1:4317"   # otel-collector gRPC 地址
    insecure: bool = True                          # 是否禁用 TLS（本地开发）

    # ---- 采样 ----
    sampler_ratio: float = 1.0                     # 头部采样比例（0~1）；错误链路始终建议保留
    # 已启用的插件名（空元组=不启用任何插件）
    enabled_plugins: Tuple[str, ...] = field(default_factory=tuple)

    # ---- 敏感内容采集（默认全部关闭，合规友好）----
    capture_message_content: bool = False          # input/output messages 原文
    capture_tool_content: bool = False             # tool arguments / result 原文

    # ---- 插件开关 ----
    pii_mask_enabled: bool = False                 # PII 脱敏
    token_estimate_enabled: bool = False           # 本地 token 估算兜底

    # ---- 业务标签（可选，注入到根 Span）----
    default_session_id: Optional[str] = None
    default_user_id: Optional[str] = None

    @classmethod
    def from_env(cls, **overrides) -> "AgentOTelConfig":
        """用环境变量构造配置，``overrides`` 优先级最高。

        支持的环境变量：
            AGENTOTEL_SERVICE_NAME / AGENTOTEL_OTLP_ENDPOINT
            AGENTOTEL_SAMPLER_RATIO
            AGENTOTEL_CAPTURE_MESSAGE_CONTENT / AGENTOTEL_CAPTURE_TOOL_CONTENT
            AGENTOTEL_PII_MASK / AGENTOTEL_TOKEN_ESTIMATE
        """
        base = dict(
            service_name=os.environ.get("AGENTOTEL_SERVICE_NAME", cls.service_name),
            service_version=os.environ.get("AGENTOTEL_SERVICE_VERSION", cls.service_version),
            environment=os.environ.get("AGENTOTEL_ENVIRONMENT", cls.environment),
            otlp_endpoint=os.environ.get("AGENTOTEL_OTLP_ENDPOINT", cls.otlp_endpoint),
            sampler_ratio=float(os.environ.get("AGENTOTEL_SAMPLER_RATIO", cls.sampler_ratio)),
            capture_message_content=_env_bool("AGENTOTEL_CAPTURE_MESSAGE_CONTENT", False),
            capture_tool_content=_env_bool("AGENTOTEL_CAPTURE_TOOL_CONTENT", False),
            pii_mask_enabled=_env_bool("AGENTOTEL_PII_MASK", False),
            token_estimate_enabled=_env_bool("AGENTOTEL_TOKEN_ESTIMATE", False),
            default_session_id=os.environ.get("AGENTOTEL_SESSION_ID"),
            default_user_id=os.environ.get("AGENTOTEL_USER_ID"),
        )
        base.update(overrides)
        return cls(**base)
