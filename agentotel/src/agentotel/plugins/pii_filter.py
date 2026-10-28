"""PII（个人敏感信息）脱敏插件。

对 Span 中的字符串型属性做正则脱敏，覆盖：
- 手机号、座机号
- 身份证号
- 银行卡号
- 邮箱地址

只处理字符串属性；JSON 字符串会先整体替换其中命中的片段。
"""

from __future__ import annotations

import re
from typing import Any, Dict, TYPE_CHECKING

from .base import AgentotelPlugin

if TYPE_CHECKING:
    from opentelemetry.trace import Span


# 规则表：(名称, 正则, 替换模板)。
# 注意：不能用 \b 做边界——Python re 默认 UNICODE 模式下中文也属于 \w，
# 导致“中文+数字”之间不构成单词边界，手机号/身份证在中文句子里会漏匹配。
# 改用“数字边界” (?<!\d) ... (?!\d)，只要求前后不是数字即可。
# 顺序上“身份证/银行卡”要放在“手机号”之前，避免长数字被手机号规则先截断。
_PATTERNS = [
    ("id_card", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "***ID_CARD***"),
    ("bank_card", re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "***BANK_CARD***"),
    ("phone", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "***PHONE***"),
    ("landline", re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)"), "***LANDLINE***"),
    ("email", re.compile(r"(?<![\w.@\-])[\w.\-]+@[\w\-]+\.[\w.\-]+(?![\w.@\-])"), "***EMAIL***"),
]


def mask_text(text: str) -> str:
    """对单个字符串应用全部脱敏规则。"""
    masked = text
    for _name, pattern, repl in _PATTERNS:
        masked = pattern.sub(repl, masked)
    return masked


class PIIFilterPlugin(AgentotelPlugin):
    """遍历属性，对字符串值做 PII 脱敏。"""

    name = "pii_filter"

    def process(self, span: "Span", attributes: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for key, value in attributes.items():
            if isinstance(value, str):
                out[key] = mask_text(value)
            elif isinstance(value, list):
                # 字符串数组（如 finish_reasons）逐个脱敏
                out[key] = [mask_text(v) if isinstance(v, str) else v for v in value]
            else:
                out[key] = value
        return out
