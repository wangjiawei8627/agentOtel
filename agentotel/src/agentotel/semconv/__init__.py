"""GenAI 语义约定（Semantic Conventions）子包。

- ``attributes``：标准属性 key 常量，全框架统一引用，禁止散落硬编码字符串。
- ``mapping``：各 Agent 框架字段 -> 标准 ``gen_ai.*`` 属性的映射规则。
"""

from . import attributes, mapping  # noqa: F401

__all__ = ["attributes", "mapping"]
