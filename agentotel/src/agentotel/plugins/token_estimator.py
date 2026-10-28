"""Token 估算插件（兜底）。

当 LLM 响应没有返回 usage（部分自建模型、代理、离线场景）时，
用本地方式估算输入/输出 token，保证成本大盘不缺数据。

优先使用 tiktoken（更准确）；未安装 tiktoken 时降级为
“字符数 / 4”的粗略估算，并在属性中标记为估算值，便于后续区分。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from .base import AgentotelPlugin
from ..semconv import attributes as A

if TYPE_CHECKING:
    from opentelemetry.trace import Span


def _get_encoder(model: str):
    """尝试获取 tiktoken 编码器；不可用返回 None。"""
    try:
        import tiktoken  # 延迟导入，tiktoken 是可选依赖
    except Exception:
        return None
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None


def _count(text: str, encoder: Any) -> int:
    """统计 token 数；有 encoder 用 encoder，否则按字符数/4 估算。"""
    if not text:
        return 0
    if encoder is not None:
        return len(encoder.encode(text))
    # 经验近似：英文约 4 字符/token；中文偏多，这里给一个保守口径
    return max(1, len(text) // 4)


class TokenEstimatorPlugin(AgentotelPlugin):
    """在缺少 usage 时，从 input/output 消息文本估算 token。"""

    name = "token_estimator"

    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self.model = model
        self._encoder: Optional[Any] = _get_encoder(model)

    def process(self, span: "Span", attributes: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(attributes)

        # 只在缺失 token 时才估算，避免覆盖真实 usage
        need_input = A.USAGE_INPUT_TOKENS not in out
        need_output = A.USAGE_OUTPUT_TOKENS not in out
        if not (need_input or need_output):
            return out

        # 从 input/output messages（JSON 字符串）里抽取文本
        input_text = self._extract_text(out.get(A.INPUT_MESSAGES))
        output_text = self._extract_text(out.get(A.OUTPUT_MESSAGES))

        if need_input and input_text:
            out[A.USAGE_INPUT_TOKENS] = _count(input_text, self._encoder)
            out["app.token.estimated"] = True
        if need_output and output_text:
            out[A.USAGE_OUTPUT_TOKENS] = _count(output_text, self._encoder)
            out["app.token.estimated"] = True
        return out

    @staticmethod
    def _extract_text(messages_raw: Any) -> str:
        """从标准消息结构（JSON 字符串或对象）中拼接所有文本片段。"""
        if not messages_raw:
            return ""
        import json
        try:
            messages = json.loads(messages_raw) if isinstance(messages_raw, str) else messages_raw
        except Exception:
            return str(messages_raw)

        parts = []
        for msg in messages or []:
            for part in msg.get("parts", []) if isinstance(msg, dict) else []:
                if part.get("type") == "text" and part.get("content"):
                    parts.append(part["content"])
        return "\n".join(parts)
