"""框架字段 -> 标准 ``gen_ai.*`` 属性的映射规则。

不同 Agent 框架对同一概念的字段命名不同（例如 LangChain 的
``usage_metadata``、OpenAI 原生 SDK 的 ``usage``）。本模块维护一份
声明式映射表，Instrumentor 据此把框架数据翻译成标准属性，
从而屏蔽框架差异，保证全链路口径统一。

V0.1 内置最常用的映射；后续可改为从外部 YAML 加载，便于不改代码扩展。
"""

from __future__ import annotations

from typing import Any, Dict

from . import attributes as A

# 类型别名：映射表 = { 框架字段路径: 标准属性 key }
FieldMapping = Dict[str, str]


# -----------------------------------------------------------------------------
# OpenAI 原生 SDK（chat.completions.create 返回的 ChatCompletion）
# -----------------------------------------------------------------------------
OPENAI_MAPPING: FieldMapping = {
    "model": A.REQUEST_MODEL,
    "usage.prompt_tokens": A.USAGE_INPUT_TOKENS,
    "usage.completion_tokens": A.USAGE_OUTPUT_TOKENS,
    "usage.total_tokens": A.USAGE_TOTAL_TOKENS,
    "choices[].finish_reason": A.RESPONSE_FINISH_REASONS,
    "id": A.RESPONSE_ID,
}


# -----------------------------------------------------------------------------
# LangChain / LangGraph（AIMessage）
# -----------------------------------------------------------------------------
LANGCHAIN_MAPPING: FieldMapping = {
    "usage_metadata.input_tokens": A.USAGE_INPUT_TOKENS,
    "usage_metadata.output_tokens": A.USAGE_OUTPUT_TOKENS,
    "usage_metadata.total_tokens": A.USAGE_TOTAL_TOKENS,
    "response_metadata.finish_reason": A.RESPONSE_FINISH_REASONS,
    "response_metadata.model_name": A.RESPONSE_MODEL,
    "id": A.RESPONSE_ID,
}


# 汇总注册表：Instrumentor 按框架名取对应映射
REGISTRY: Dict[str, FieldMapping] = {
    "openai": OPENAI_MAPPING,
    "langchain": LANGCHAIN_MAPPING,
    "langgraph": LANGCHAIN_MAPPING,  # LangGraph 复用 LangChain 消息模型
}


def get_mapping(framework: str) -> FieldMapping:
    """按框架名返回映射表；未知框架返回空表（不报错，降级为不映射）。"""
    return REGISTRY.get(framework, {})


def _dig(obj: Any, path: str) -> Any:
    """极简路径取值，支持 ``a.b.c`` 与 ``a[0].b``（取第 0 个元素）。

    生产环境可替换成 jmespath；V0.1 为避免额外依赖，自行实现够用的子集。
    支持的片段形式：``name``、``[idx]``、``name[idx]``。
    """
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        # 处理带数组索引的片段：name[idx]、[idx] 或 name[]（空索引默认 0）
        if "[" in part and part.endswith("]"):
            name, idx_part = part.split("[", 1)
            idx_raw = idx_part[:-1]
            idx = int(idx_raw) if idx_raw else 0
            if name:  # 形如 choices[0]，先取属性 choices
                cur = cur.get(name) if isinstance(cur, dict) else getattr(cur, name, None)
            if isinstance(cur, (list, tuple)) and len(cur) > idx:
                cur = cur[idx]
            else:
                cur = None
        else:
            cur = cur.get(part) if isinstance(cur, dict) else getattr(cur, part, None)
    return cur


def apply_mapping(framework: str, source: Any) -> Dict[str, Any]:
    """按映射表把一个框架响应对象翻译成 ``{标准属性: 值}``。

    - 数组型标准属性（如 finish_reasons）会自动包成单元素列表。
    - 值为 None 的字段直接跳过，避免写入空属性。
    """
    out: Dict[str, Any] = {}
    for src_path, dst_key in get_mapping(framework).items():
        value = _dig(source, src_path)
        if value is None:
            continue
        # finish_reason 标准要求是字符串数组
        if dst_key == A.RESPONSE_FINISH_REASONS and isinstance(value, str):
            value = [value]
        out[dst_key] = value
    return out
