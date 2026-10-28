"""AgentOTel —— OpenTelemetry 原生、可插拔的 AI Agent 埋点监控框架。

快速开始::

    from agentotel import init_agentotel, LangGraphInstrumentor

    init_agentotel(service_name="my-agent", capture_message_content=True)
    LangGraphInstrumentor().instrument()

公共 API：
- 初始化：``init_agentotel`` / ``get_agentotel``
- 自动插桩：``LangGraphInstrumentor`` / ``OpenAIInstrumentor`` /
  ``LlamaIndexInstrumentor``
- 网关插桩：``AgentOTelMiddleware``（FastAPI）
- 质量评估：``RuleBasedQualityEvaluator`` / ``LLMJudgeEvaluator``
- 管理后台：``create_console_app``
- 手动埋点：``agent_span`` / ``llm_span`` / ``tool_span`` / ``retrieval_span``
- 配置：``AgentOTelConfig``
"""

from __future__ import annotations

from .config import AgentOTelConfig
from .context import AgentContext, use_context, get_context
from .otel import AgentOTel, init_agentotel, get_agentotel
from .instrumentors import (
    BaseAgentInstrumentor,
    LangGraphInstrumentor,
    OpenAIInstrumentor,
    LlamaIndexInstrumentor,
)
from .middleware import AgentOTelMiddleware
from .quality import (
    BaseQualityEvaluator,
    RuleBasedQualityEvaluator,
    LLMJudgeEvaluator,
    QualitySignals,
    QualityResult,
)
from .console import create_console_app, console_app
from .sdk import (
    agent_span,
    llm_span,
    tool_span,
    retrieval_span,
    span,
)

__version__ = "0.3.0"

__all__ = [
    "__version__",
    # 配置 / 上下文
    "AgentOTelConfig",
    "AgentContext",
    "use_context",
    "get_context",
    # 初始化
    "AgentOTel",
    "init_agentotel",
    "get_agentotel",
    # 自动插桩
    "BaseAgentInstrumentor",
    "LangGraphInstrumentor",
    "OpenAIInstrumentor",
    "LlamaIndexInstrumentor",
    # 网关插桩
    "AgentOTelMiddleware",
    # 质量评估
    "BaseQualityEvaluator",
    "RuleBasedQualityEvaluator",
    "LLMJudgeEvaluator",
    "QualitySignals",
    "QualityResult",
    # 管理后台
    "create_console_app",
    "console_app",
    # 手动埋点
    "agent_span",
    "llm_span",
    "tool_span",
    "retrieval_span",
    "span",
]
